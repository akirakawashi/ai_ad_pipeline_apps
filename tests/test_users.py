"""Справочник людей: постановщики заданий и операторы съёмок.

Заглушка под будущую авторизацию, поэтому проверяем именно справочные
свойства: нормализацию имени, защиту от дублей и деактивацию вместо удаления.
"""

from __future__ import annotations

from conftest import payload


def create_user(client, full_name: str):
    return client.post("/api/v1/users", json={"full_name": full_name})


def test_creates_person(client):
    response = create_user(client, "Иванов Иван Иванович")
    assert response.status_code == 201
    assert payload(response)["is_active"] is True


def test_collapses_whitespace_in_name(client):
    """Иначе в справочнике заводятся близнецы с невидимым лишним пробелом."""
    person = payload(create_user(client, "  Иванов   Иван Иванович "))
    assert person["full_name"] == "Иванов Иван Иванович"


def test_duplicate_name_rejected(client):
    create_user(client, "Иванов Иван")
    assert create_user(client, "Иванов Иван").status_code == 409


def test_duplicate_detected_after_normalisation(client):
    create_user(client, "Иванов Иван")
    assert create_user(client, "Иванов    Иван  ").status_code == 409


def test_blank_name_rejected(client):
    assert create_user(client, "   ").status_code == 400


def test_list_sorted_by_name(client):
    for name in ("Яковлев Яков", "Алексеев Алексей", "Миронов Мирон"):
        create_user(client, name)
    names = [person["full_name"] for person in payload(client.get("/api/v1/users"))]
    assert names == sorted(names)


def test_deactivated_person_hidden_from_list(client):
    person = payload(create_user(client, "Петров Пётр"))
    client.patch(f"/api/v1/users/{person['id']}", json={"is_active": False})

    assert payload(client.get("/api/v1/users")) == []
    assert len(payload(client.get("/api/v1/users?include_inactive=true"))) == 1


def test_patch_touches_only_given_fields(client):
    person = payload(create_user(client, "Петров Пётр"))
    updated = payload(client.patch(f"/api/v1/users/{person['id']}", json={"is_active": False}))
    assert updated["full_name"] == "Петров Пётр"


def test_rename_to_existing_name_rejected(client):
    create_user(client, "Иванов Иван")
    other = payload(create_user(client, "Петров Пётр"))
    response = client.patch(
        f"/api/v1/users/{other['id']}", json={"full_name": "Иванов Иван"}
    )
    assert response.status_code == 409


def test_rename_to_own_name_allowed(client):
    person = payload(create_user(client, "Иванов Иван"))
    response = client.patch(
        f"/api/v1/users/{person['id']}", json={"full_name": "Иванов Иван"}
    )
    assert response.status_code == 200


def test_unknown_person_is_404(client):
    response = client.patch(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        json={"full_name": "Кто-то"},
    )
    assert response.status_code == 404
