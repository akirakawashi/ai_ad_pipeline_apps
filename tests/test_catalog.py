"""Каталог: города и маршруты приходят из сид-миграций и доступны только на чтение."""

from __future__ import annotations

from conftest import payload


def test_lists_seeded_cities(client):
    cities = payload(client.get("/api/v1/cities"))
    slugs = {city["slug"] for city in cities}
    assert {"simferopol", "sevastopol"} <= slugs


def test_city_detail_carries_routes(client):
    city = payload(client.get("/api/v1/cities/simferopol"))
    assert city["name"] == "Симферополь"
    assert len(city["routes"]) == 4


def test_geometry_reported_by_flag_not_content(client):
    """Геометрия в списки не попадает: строка отдаёт только признак наличия.

    Линия маршрута — десятки килобайт, дорожный слой города — полтора мегабайта;
    в карточке города им места нет. Проверяется на городе: у него слой засеян,
    поэтому виден интересный случай — признак True, а содержимого рядом нет.
    """
    city = payload(client.get("/api/v1/cities/simferopol"))
    assert city["has_roads_geometry"] is True
    assert "roads_geometry" not in city
    route = city["routes"][0]
    assert "geometry" not in route
    assert "description" in route


def test_seeded_route_has_no_line_until_it_is_drawn(client):
    """Сид заводит маршрут без линии — её рисуют поверх дорожного слоя.

    Признак должен быть именно False, а не True при пустой линии: колонка
    оставлена незаполненной, а не записана как JSON-литерал `null`, иначе
    `IS NOT NULL` истинно и карточка обещает линию, которой нет.
    """
    city = payload(client.get("/api/v1/cities/simferopol"))
    assert [route["has_geometry"] for route in city["routes"]] == [False] * 4


def test_unknown_city_is_404(client):
    assert client.get("/api/v1/cities/atlantis").status_code == 404


def test_counters_follow_assignments(client, city_route):
    city_slug, route_slug = city_route
    before = payload(client.get("/api/v1/cities"))
    simferopol = next(c for c in before if c["slug"] == city_slug)
    assert simferopol["assignment_count"] == 0

    client.post(f"/api/v1/cities/{city_slug}/routes/{route_slug}/assignments", json={})

    after = payload(client.get("/api/v1/cities"))
    simferopol = next(c for c in after if c["slug"] == city_slug)
    assert simferopol["assignment_count"] == 1
