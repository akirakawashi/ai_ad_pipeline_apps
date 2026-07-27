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


def test_route_exposes_geojson_and_description(client):
    """geojson_path — путь относительно public/, без ведущего слэша."""
    city = payload(client.get("/api/v1/cities/simferopol"))
    route = city["routes"][0]
    assert route["geojson_path"].startswith("routes/simferopol/")
    assert not route["geojson_path"].startswith("/")
    assert "description" in route


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
