"""Пароль админ-панели: проверка живёт на бэкенде, а не в форме на фронте.

Смысл набора — зафиксировать границу. Форму входа обойти легко (это просто
экран), поэтому важно, что закрыты сами эндпоинты: без пароля правка городов,
маршрутов, ревизий каталога и справочника людей не проходит, чем бы её ни
вызывали.

Обратная половина не менее важна и проверяется здесь же: чтения, из которых
живёт продукт, остаются открытыми. Закрыть их паролем значило бы закрыть весь
интерфейс.
"""

from __future__ import annotations

import io
import json

import pytest

from conftest import ADMIN_LOGIN, ADMIN_PASSWORD, payload

CITIES = "/api/v1/cities"
SESSION = "/api/v1/admin/session"
USERS = "/api/v1/users"

# Идентификатор заведомо несуществующий: до поиска в базе дело не доходит,
# пароль проверяется раньше. Если ручку однажды откроют, тест упадёт на 404 —
# и это правильный сигнал, а не ложное срабатывание.
MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _geojson() -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[36.40, 45.30], [36.41, 45.31]],
                    },
                }
            ],
        }
    ).encode()


def _upload(client, url: str):
    return client.put(url, files={"file": ("layer.geojson", io.BytesIO(_geojson()))})


# --- сама проверка пароля ---------------------------------------------------


def test_session_rejects_missing_and_wrong_credentials(anonymous_client):
    assert anonymous_client.get(SESSION).status_code == 401
    assert anonymous_client.get(SESSION, auth=("admin", "неверный")).status_code == 401
    assert anonymous_client.get(SESSION, auth=("чужой", ADMIN_PASSWORD)).status_code == 401


def test_session_accepts_the_pair_and_says_nothing_else(anonymous_client):
    response = anonymous_client.get(SESSION, auth=(ADMIN_LOGIN, ADMIN_PASSWORD))
    assert response.status_code == 204
    assert response.content == b""


def test_unauthorized_answer_is_a_russian_sentence_with_the_scheme(anonymous_client):
    """Причина — человеку, заголовок — по RFC: без него это не 401, а просто отказ."""
    response = anonymous_client.get(SESSION)
    assert response.json()["detail"] == "Админ-панель под паролем. Введите логин и пароль."
    assert response.headers["WWW-Authenticate"].startswith("Basic")


# --- что закрыто ------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", CITIES, {"slug": "kerch", "name": "Керчь"}),
        ("patch", f"{CITIES}/simferopol", {"name": "Другое имя"}),
        ("patch", f"{CITIES}/simferopol", {"is_active": False}),
        ("post", f"{CITIES}/simferopol/routes", {"slug": "route-9", "name": "Новый"}),
        ("patch", f"{CITIES}/simferopol/routes/route-1", {"name": "Другое имя"}),
    ],
    ids=["создать город", "правка города", "скрыть город", "создать маршрут", "правка маршрута"],
)
def test_writes_are_closed_without_password(anonymous_client, method, url, body):
    assert getattr(anonymous_client, method)(url, json=body).status_code == 401


def test_geometry_upload_is_closed_without_password(anonymous_client):
    assert _upload(anonymous_client, f"{CITIES}/simferopol/roads-geometry").status_code == 401
    assert (
        _upload(anonymous_client, f"{CITIES}/simferopol/routes/route-1/geometry").status_code
        == 401
    )


def test_catalog_writes_are_closed_without_password(anonymous_client):
    """Каталог заменяется целиком: одна кнопка — и в городе другие конструкции."""
    upload = anonymous_client.post(
        f"{CITIES}/simferopol/catalog/imports",
        files={"files": ("catalog.csv", io.BytesIO(b"adress;lat;lon\n"))},
        data={"uploaded_by_user_id": MISSING_ID},
    )
    assert upload.status_code == 401
    assert (
        anonymous_client.post(f"/api/v1/catalog/imports/{MISSING_ID}/apply").status_code
        == 401
    )
    assert (
        anonymous_client.post(
            f"/api/v1/catalog/imports/{MISSING_ID}/restore"
        ).status_code
        == 401
    )
    assert (
        anonymous_client.delete(f"/api/v1/catalog/imports/{MISSING_ID}").status_code
        == 401
    )


def test_user_directory_is_closed_without_password(anonymous_client):
    """Справочник людей ведут в админ-панели: и заводят, и правят там же.

    Заведение закрыто вместе с правкой намеренно. Пока человека можно было
    создать из выпадашки «Кто загрузил», его создавал тот, кто в эту минуту
    грузил видео, — справочник копил близнецов быстрее, чем их успевали чистить.
    """
    assert anonymous_client.post(USERS, json={"full_name": "Кто угодно"}).status_code == 401
    assert (
        anonymous_client.patch(
            f"{USERS}/{MISSING_ID}", json={"full_name": "Кто угодно"}
        ).status_code
        == 401
    )
    assert anonymous_client.get(f"{USERS}?include_inactive=true").status_code == 401


def test_hidden_cities_are_closed_without_password(anonymous_client):
    """`include_inactive` — админский режим просмотра, значит тоже под паролем."""
    assert anonymous_client.get(f"{CITIES}?include_inactive=true").status_code == 401
    assert (
        anonymous_client.get(f"{CITIES}/simferopol?include_inactive=true").status_code == 401
    )


def test_closed_write_changes_nothing(anonymous_client, client):
    """401 обязан быть отказом, а не «приняли, но не показали»."""
    before = payload(client.get(f"{CITIES}/simferopol"))["name"]
    anonymous_client.patch(f"{CITIES}/simferopol", json={"name": "Взломано"})
    assert payload(client.get(f"{CITIES}/simferopol"))["name"] == before


# --- что осталось открытым --------------------------------------------------


def test_product_reads_stay_open(anonymous_client):
    """Весь продукт читает справочник городов. Пароль тут закрыл бы всё."""
    assert anonymous_client.get(CITIES).status_code == 200
    assert anonymous_client.get(f"{CITIES}/simferopol").status_code == 200
    assert anonymous_client.get(f"{CITIES}/simferopol/roads-geometry").status_code == 200
    assert (
        anonymous_client.get(f"{CITIES}/simferopol/routes/route-1/geometry").status_code
        == 200
    )
    assert anonymous_client.get("/api/v1/runs").status_code == 200


def test_catalog_reads_stay_open(anonymous_client):
    """Список конструкций — продуктовый экран, история ревизий даёт ему номер текущей."""
    assert anonymous_client.get(f"{CITIES}/simferopol/ad-structures").status_code == 200
    assert (
        anonymous_client.get(f"{CITIES}/simferopol/catalog/imports").status_code == 200
    )


def test_reading_the_people_directory_stays_open(anonymous_client):
    """Выпадашка «Кто загрузил» читает справочник на каждой форме загрузки."""
    assert anonymous_client.get(USERS).status_code == 200


def test_password_opens_everything_it_closed(anonymous_client):
    auth = (ADMIN_LOGIN, ADMIN_PASSWORD)
    assert anonymous_client.get(f"{CITIES}?include_inactive=true", auth=auth).status_code == 200
    assert (
        anonymous_client.patch(
            f"{CITIES}/simferopol",
            json={"name": "Симферополь"},
            auth=auth,
        ).status_code
        == 200
    )
    assert (
        anonymous_client.get(f"{USERS}?include_inactive=true", auth=auth).status_code
        == 200
    )
