"""Задание — серия съёмок по маршруту.

Плановое окно задаёт постановщик, фактическое выводится из времён съёмок.
Отдельно проверяем разделение отображаемого и хранимого названия: в этом месте
уже был дефект, когда автозаголовок молча становился постоянным.

Заводят и правят задание только в админ-панели — сценарии пароля живут в
test_admin_auth.py, здесь клиент ходит с ним по умолчанию. Скрытие проверяется
в TestHiding: удаления у задания нет и не будет, на нём висят съёмки с CASCADE.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import payload


@pytest.fixture
def assignments_url(city_route) -> str:
    city_slug, route_slug = city_route
    return f"/api/v1/cities/{city_slug}/routes/{route_slug}/assignments"


@pytest.fixture
def author(client) -> dict:
    return payload(client.post("/api/v1/users", json={"full_name": "Иванов Иван"}))


def test_creates_with_full_details(client, assignments_url, author):
    response = client.post(
        assignments_url,
        json={
            "title": "Летний замер",
            "description": "Первая неделя августа",
            "planned_start_at": "2026-08-01T06:00:00Z",
            "planned_end_at": "2026-08-05T18:00:00Z",
            "author_user_id": author["id"],
        },
    )
    assert response.status_code == 201
    created = payload(response)
    assert created["title"] == "Летний замер"
    assert created["author"]["full_name"] == "Иванов Иван"
    assert created["description"] == "Первая неделя августа"


def test_creates_without_details(client, assignments_url):
    """Реквизиты необязательны: маршрут и номер и так известны."""
    assert client.post(assignments_url, json={}).status_code == 201


def test_numbers_are_sequential_within_route(client, assignments_url):
    numbers = [
        payload(client.post(assignments_url, json={}))["sequence_number"]
        for _ in range(3)
    ]
    assert numbers == [1, 2, 3]


def test_parallel_creation_does_not_duplicate_numbers(client, assignments_url):
    """Номер аллоцируется под блокировкой строки маршрута."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(assignments_url, json={}), range(4)))

    assert [r.status_code for r in responses] == [201] * 4
    numbers = sorted(payload(r)["sequence_number"] for r in responses)
    assert numbers == [1, 2, 3, 4]


def test_planned_window_must_not_be_inverted(client, assignments_url):
    response = client.post(
        assignments_url,
        json={
            "planned_start_at": "2026-08-05T00:00:00Z",
            "planned_end_at": "2026-08-01T00:00:00Z",
        },
    )
    assert response.status_code == 400


def test_naive_datetime_rejected(client, assignments_url):
    """Даты уходят в DWH: молча додумывать зону нельзя, сдвиг вскроется поздно."""
    response = client.post(
        assignments_url, json={"planned_start_at": "2026-08-01T06:00:00"}
    )
    assert response.status_code == 422


def test_unknown_author_is_not_500(client, assignments_url):
    response = client.post(
        assignments_url, json={"author_user_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert response.status_code == 400


class TestTitle:
    """Отображаемое имя и хранимое название — разные поля."""

    def test_auto_title_when_none_stored(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        assert created["custom_title"] is None
        assert created["title"].startswith("Задание №1")

    def test_saving_untouched_form_keeps_title_computed(self, client, assignments_url):
        """Форма правит custom_title; вернуть его как есть — ничего не менять."""
        created = payload(client.post(assignments_url, json={}))
        updated = payload(
            client.patch(
                f"/api/v1/assignments/{created['id']}",
                json={"title": created["custom_title"]},
            )
        )
        assert updated["custom_title"] is None
        assert updated["title"] == created["title"]

    def test_custom_title_wins(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        updated = payload(
            client.patch(
                f"/api/v1/assignments/{created['id']}", json={"title": "Своё имя"}
            )
        )
        assert updated["custom_title"] == "Своё имя"
        assert updated["title"] == "Своё имя"

    def test_clearing_title_restores_auto(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={"title": "Своё имя"}))
        updated = payload(
            client.patch(f"/api/v1/assignments/{created['id']}", json={"title": None})
        )
        assert updated["custom_title"] is None
        assert updated["title"].startswith("Задание №")


class TestPatch:
    def test_changes_only_given_fields(self, client, assignments_url, author):
        created = payload(
            client.post(
                assignments_url,
                json={
                    "title": "Летний замер",
                    "planned_start_at": "2026-08-01T06:00:00Z",
                    "author_user_id": author["id"],
                },
            )
        )
        updated = payload(
            client.patch(
                f"/api/v1/assignments/{created['id']}", json={"description": "Изменено"}
            )
        )
        assert updated["description"] == "Изменено"
        assert updated["title"] == "Летний замер"
        assert updated["author"]["id"] == author["id"]
        assert updated["planned_start_at"] is not None

    def test_rejects_window_broken_by_partial_update(self, client, assignments_url):
        """Проверяем окно целиком: вторая граница уже лежит в базе."""
        created = payload(
            client.post(assignments_url, json={"planned_start_at": "2026-08-05T00:00:00Z"})
        )
        response = client.patch(
            f"/api/v1/assignments/{created['id']}",
            json={"planned_end_at": "2026-08-01T00:00:00Z"},
        )
        assert response.status_code == 400

    def test_unknown_assignment_is_404(self, client):
        response = client.patch(
            "/api/v1/assignments/00000000-0000-0000-0000-000000000000",
            json={"description": "x"},
        )
        assert response.status_code == 404


class TestHiding:
    """Скрытие задания. Удаления нет: на нём висят съёмки с CASCADE.

    Проверяем обе половины двери. Скрытое исчезает отовсюду, включая прямую
    ссылку, — иначе «скрыто» означало бы лишь «убрано из списка», а сохранённая
    вкладка обходила бы это молча. И скрытое возвращается той же ручкой: скрытие
    без возврата — односторонняя дверь, на которой в этом проекте уже погорели
    города.
    """

    def test_disappears_from_route_list(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        client.patch(f"/api/v1/assignments/{created['id']}", json={"is_active": False})

        listed = payload(client.get(assignments_url))
        assert listed["total"] == 0
        assert listed["items"] == []

    def test_admin_sees_it_and_knows_it_is_hidden(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        client.patch(f"/api/v1/assignments/{created['id']}", json={"is_active": False})

        listed = payload(client.get(f"{assignments_url}?include_inactive=true"))
        assert [item["id"] for item in listed["items"]] == [created["id"]]
        assert listed["items"][0]["is_active"] is False

    def test_direct_link_is_404(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        client.patch(f"/api/v1/assignments/{created['id']}", json={"is_active": False})

        url = f"/api/v1/assignments/{created['id']}"
        assert client.get(url).status_code == 404
        assert client.get(f"{url}?include_inactive=true").status_code == 200
        # Сводка и список съёмок ходят через ту же проверку.
        assert client.get(f"{url}/summary").status_code == 404
        assert client.get(f"{url}/runs").status_code == 404

    def test_restore_brings_it_back(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        client.patch(f"/api/v1/assignments/{created['id']}", json={"is_active": False})

        restored = client.patch(
            f"/api/v1/assignments/{created['id']}", json={"is_active": True}
        )
        assert restored.status_code == 200
        assert payload(restored)["is_active"] is True
        assert payload(client.get(assignments_url))["total"] == 1

    def test_route_card_stops_counting_it(self, client, city_route, assignments_url):
        """Счётчик на карточке маршрута не должен спорить со списком под ней."""
        city_slug, route_slug = city_route
        created = payload(client.post(assignments_url, json={}))
        client.patch(f"/api/v1/assignments/{created['id']}", json={"is_active": False})

        city = payload(client.get(f"/api/v1/cities/{city_slug}"))
        route = next(item for item in city["routes"] if item["slug"] == route_slug)
        assert route["assignment_count"] == 0

    def test_null_is_refused(self, client, assignments_url):
        """Колонка NOT NULL: null должен отбиваться разбором, а не базой."""
        created = payload(client.post(assignments_url, json={}))
        response = client.patch(
            f"/api/v1/assignments/{created['id']}", json={"is_active": None}
        )
        assert response.status_code == 422

    def test_new_assignment_is_visible(self, client, assignments_url):
        assert payload(client.post(assignments_url, json={}))["is_active"] is True


class TestActualWindow:
    def test_empty_without_shootings(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        assert created["actual_start_at"] is None
        assert created["actual_end_at"] is None

    def test_derived_from_shootings(self, client, assignments_url):
        created = payload(client.post(assignments_url, json={}))
        for moment in ("2026-08-02T09:00:00Z", "2026-08-02T11:00:00Z"):
            client.post(
                "/api/v1/runs",
                json={
                    "file_name": f"{moment}.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 1024,
                    "assignment_id": created["id"],
                    "shot_started_at": moment,
                },
            )
        refreshed = payload(client.get(f"/api/v1/assignments/{created['id']}"))
        assert refreshed["actual_start_at"].startswith("2026-08-02T09:00")
        assert refreshed["actual_end_at"].startswith("2026-08-02T11:00")


def test_summary_counts_shootings(client, assignments_url):
    created = payload(client.post(assignments_url, json={}))
    client.post(
        "/api/v1/runs",
        json={
            "file_name": "pass.mp4",
            "content_type": "video/mp4",
            "size_bytes": 1024,
            "assignment_id": created["id"],
        },
    )
    summary = payload(client.get(f"/api/v1/assignments/{created['id']}/summary"))
    assert summary["totals"]["shootings_total"] == 1
    # Метрики появляются только у обработанных съёмок.
    assert summary["totals"]["shootings_completed"] == 0
