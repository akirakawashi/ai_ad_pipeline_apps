"""Справочники городов и маршрутов: правка через API вместо миграций.

Два теста здесь важнее прочих. Первый — что заливка дорожного слоя пересчитывает
рамку города: ею каталог отсекает точки чужого города, и слой без пересчёта
означал бы молчаливую потерю нормальных точек при следующем импорте. Второй — что
геометрия не приезжает в списки: там её объём (до 1.5 МБ) никому не нужен.
"""

from __future__ import annotations

import json

import pytest
from sqlmodel import Session, select

from conftest import payload
from infrastructure.database.models import City
from infrastructure.database.session import engine

CITIES = "/api/v1/cities"


def _collection(points: list[tuple[float, float]]) -> bytes:
    """FeatureCollection из одной линии. Координаты — [долгота, широта]."""
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"highway": "primary"},
                    "geometry": {"type": "LineString", "coordinates": points},
                }
            ],
        }
    ).encode("utf-8")


def _upload(client, url: str, content: bytes, name: str = "layer.geojson"):
    return client.put(
        url,
        files={"file": (name, content, "application/geo+json")},
    )


def _city_bounds(slug: str) -> tuple[float | None, ...]:
    with Session(engine) as session:
        city = session.exec(select(City).where(City.slug == slug)).first()
        return (
            city.bounds_min_latitude,
            city.bounds_max_latitude,
            city.bounds_min_longitude,
            city.bounds_max_longitude,
        )


def _drop_city(slug: str) -> None:
    """Убираем город физически: `cities` не в списке таблиц, которые чистит
    conftest — сидовые города и маршруты нужны остальным тестам целыми. Каскад
    по FK уносит маршруты и задания вместе с городом."""
    with Session(engine) as session:
        city = session.exec(select(City).where(City.slug == slug)).first()
        if city is not None:
            session.delete(city)
            session.commit()


@pytest.fixture
def city(client) -> str:
    """Свой город на каждый тест, с уборкой за собой."""
    created = payload(
        client.post(
            CITIES,
            json={"slug": "kerch", "name": "Керчь", "region": "Республика Крым"},
        )
    )
    yield created["slug"]
    _drop_city("kerch")
    _drop_city("kerch-2")


@pytest.fixture
def other_city(client) -> str:
    """Второй временный город: проверить, что слаги маршрутов не конфликтуют
    между городами, не трогая сидовые данные."""
    created = payload(client.post(CITIES, json={"slug": "yalta", "name": "Ялта"}))
    yield created["slug"]
    _drop_city("yalta")


# --- города ----------------------------------------------------------------


def test_creates_city_and_shows_it_in_list(client, city):
    slugs = [item["slug"] for item in payload(client.get(CITIES))]
    assert city in slugs


def test_duplicate_city_slug_is_409(client, city):
    assert (
        client.post(CITIES, json={"slug": city, "name": "Другая Керчь"}).status_code
        == 409
    )


def test_bad_slug_is_rejected(client):
    # Заглавные и пробелы ломают URL — до сервиса не доходят, режет Pydantic
    # только по длине, поэтому «ЯЛТА» валит сервис с 400.
    assert client.post(CITIES, json={"slug": "ЯЛТА", "name": "Ялта"}).status_code == 400
    assert client.post(CITIES, json={"slug": "a", "name": "Ялта"}).status_code == 422


def test_patch_changes_only_given_fields(client, city):
    updated = payload(client.patch(f"{CITIES}/{city}", json={"name": "Керчь-город"}))
    assert updated["name"] == "Керчь-город"
    assert updated["region"] == "Республика Крым"
    cleared = payload(client.patch(f"{CITIES}/{city}", json={"region": None}))
    assert cleared["region"] is None


def test_slug_cannot_be_changed(client, city):
    """Слаг не описан в модели PATCH: он в URL, правка ломала бы ссылки."""
    client.patch(f"{CITIES}/{city}", json={"slug": "kerch-2"})
    assert client.get(f"{CITIES}/{city}").status_code == 200
    assert client.get(f"{CITIES}/kerch-2").status_code == 404


def test_deactivated_city_disappears_from_list(client, city):
    assert client.delete(f"{CITIES}/{city}").status_code == 204
    slugs = [item["slug"] for item in payload(client.get(CITIES))]
    assert city not in slugs
    # Сама строка жива: карточка по слагу открывается, история не рвётся.
    assert client.get(f"{CITIES}/{city}").status_code == 200


# --- маршруты --------------------------------------------------------------


def test_creates_route_without_geometry(client, city):
    created = payload(
        client.post(
            f"{CITIES}/{city}/routes",
            json={"slug": "route-1", "name": "Кольцо", "color_hex": "#ff3b3f"},
        )
    )
    assert created["has_geometry"] is False
    assert created["color_hex"] == "#ff3b3f"
    detail = payload(client.get(f"{CITIES}/{city}"))
    assert [route["slug"] for route in detail["routes"]] == ["route-1"]


def test_duplicate_route_slug_is_409_within_city_only(client, city, other_city):
    body = {"slug": "route-1", "name": "Кольцо"}
    assert client.post(f"{CITIES}/{city}/routes", json=body).status_code == 201
    assert client.post(f"{CITIES}/{city}/routes", json=body).status_code == 409
    # В другом городе тот же слаг свободен — уникальность в пределах города.
    assert client.post(f"{CITIES}/{other_city}/routes", json=body).status_code == 201


def test_bad_color_is_422(client, city):
    assert client.post(
        f"{CITIES}/{city}/routes",
        json={"slug": "route-1", "name": "Кольцо", "color_hex": "красный"},
    ).status_code == 422


def test_deactivated_route_keeps_its_assignments(client, city):
    client.post(f"{CITIES}/{city}/routes", json={"slug": "route-1", "name": "Кольцо"})
    assignment = payload(
        client.post(f"{CITIES}/{city}/routes/route-1/assignments", json={})
    )
    assert client.delete(f"{CITIES}/{city}/routes/route-1").status_code == 204

    detail = payload(client.get(f"{CITIES}/{city}"))
    assert detail["routes"] == []
    # Задание на месте: деактивация прячет маршрут, а не рушит историю.
    assert client.get(f"/api/v1/assignments/{assignment['id']}").status_code == 200


def test_missing_targets_are_404(client, city):
    assert client.patch(f"{CITIES}/atlantis", json={"name": "X"}).status_code == 404
    assert client.delete(f"{CITIES}/atlantis").status_code == 404
    assert (
        client.patch(f"{CITIES}/{city}/routes/nope", json={"name": "X"}).status_code
        == 404
    )
    assert client.delete(f"{CITIES}/{city}/routes/nope").status_code == 404


# --- геометрия -------------------------------------------------------------


def test_roads_upload_recomputes_city_bounds(client, city):
    """Главный тест шага: рамка города обновляется вместе со слоем."""
    assert _city_bounds(city) == (None, None, None, None)

    response = _upload(
        client,
        f"{CITIES}/{city}/roads-geometry",
        _collection([[36.40, 45.30], [36.50, 45.36], [36.45, 45.33]]),
    )
    assert response.status_code == 200
    assert payload(response)["has_roads_geometry"] is True
    assert _city_bounds(city) == pytest.approx((45.30, 45.36, 36.40, 36.50))

    # Перезалили другой слой — рамка переехала, а не осталась от прошлого.
    _upload(
        client,
        f"{CITIES}/{city}/roads-geometry",
        _collection([[36.00, 45.00], [36.10, 45.05]]),
    )
    assert _city_bounds(city) == pytest.approx((45.00, 45.05, 36.00, 36.10))


def test_route_geometry_round_trip(client, city):
    client.post(f"{CITIES}/{city}/routes", json={"slug": "route-1", "name": "Кольцо"})
    url = f"{CITIES}/{city}/routes/route-1/geometry"
    assert client.get(url).status_code == 404

    points = [[36.40, 45.30], [36.41, 45.31]]
    assert _upload(client, url, _collection(points)).status_code == 200

    loaded = payload(client.get(url))
    assert loaded["features"][0]["geometry"]["coordinates"] == points
    assert payload(client.get(f"{CITIES}/{city}"))["routes"][0]["has_geometry"] is True


def test_geometry_is_revalidated_by_etag(client, city):
    client.post(f"{CITIES}/{city}/routes", json={"slug": "route-1", "name": "Кольцо"})
    url = f"{CITIES}/{city}/routes/route-1/geometry"
    _upload(client, url, _collection([[36.40, 45.30], [36.41, 45.31]]))

    first = client.get(url)
    etag = first.headers["etag"]
    again = client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


@pytest.mark.parametrize(
    "content",
    [
        b"not json at all",
        json.dumps({"type": "Feature"}).encode(),
        json.dumps({"type": "FeatureCollection", "features": []}).encode(),
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"geometry": {"type": "Point", "coordinates": [500.0, 45.0]}}
                ],
            }
        ).encode(),
    ],
    ids=["не json", "не коллекция", "пустая коллекция", "координаты не с Земли"],
)
def test_broken_geometry_is_400_and_changes_nothing(client, city, content):
    response = _upload(client, f"{CITIES}/{city}/roads-geometry", content)
    assert response.status_code == 400
    assert payload(client.get(f"{CITIES}/{city}"))["has_roads_geometry"] is False
    assert _city_bounds(city) == (None, None, None, None)
