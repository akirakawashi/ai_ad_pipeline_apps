"""Границы доступа: кто вошёл и что ему можно.

Границ теперь две, и они разной природы — это главное, что фиксирует набор.

**Первая — вход.** Приложение целиком за доменной авторизацией: без сессии не
проходит ничего, включая чтения, которыми живёт продукт. Раньше было наоборот —
всё открыто, паролем отгорожена правка справочников, — и половина этого файла
проверяла ровно обратное утверждение.

**Вторая — права.** Вошедший сотрудник работает: смотрит города и маршруты,
грузит видео, выбирает задание. Администрирование — правка городов, маршрутов,
заданий, каталога и справочника людей — требует группы из `AUTH_ADMIN_GROUPS`.
Линия проведена по цене ошибки, а не по сложности действия: администрирование
меняет рамку, в которой все работают, а операционная работа должна оставаться
доступной, иначе продукт неработоспособен.

Отличать 401 от 403 здесь принципиально. 401 — «войди», и фронт уводит на
Keycloak. 403 — «ты вошёл, но тебе нельзя», и повторный вход тем же человеком
ничего не изменит; отправлять его на форму было бы бесконечной каруселью.

Личность в тестах подменяется на границе `current_user`: живой Keycloak не
нужен, а корпоративный из сети разработчика и не виден. Проверяется то, что
решает приложение, а не то, что умеет Keycloak.
"""

from __future__ import annotations

import io
import json

import pytest

from conftest import payload

CITIES = "/api/v1/cities"
USERS = "/api/v1/users"
ME = "/api/v1/auth/me"

# Идентификатор заведомо несуществующий: до поиска в базе дело не доходит, права
# проверяются раньше. Если ручку однажды откроют, тест упадёт на 404 — и это
# правильный сигнал, а не ложное срабатывание.
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


# --- первая граница: без сессии не проходит ничего ---------------------------


@pytest.mark.parametrize(
    "url",
    [
        CITIES,
        f"{CITIES}/simferopol",
        f"{CITIES}/simferopol/roads-geometry",
        "/api/v1/runs",
        USERS,
        "/api/v1/catalog/structures?city=simferopol",
        ME,
    ],
    ids=[
        "список городов",
        "город",
        "дорожный слой",
        "съёмки",
        "справочник людей",
        "каталог конструкций",
        "кто я",
    ],
)
def test_reads_require_a_session(anonymous_client, url: str):
    """Чтения тоже закрыты — в этом и состоит переход на доменный вход.

    До SSO они были открыты сознательно: пароль был один на всех, и закрыть им
    продуктовые экраны значило закрыть продукт. С личным входом такого выбора
    больше нет — человек и так представился, чтобы работать.
    """
    assert anonymous_client.get(url).status_code == 401


def test_unauthorized_answer_is_a_russian_sentence_without_a_browser_prompt(
    anonymous_client,
):
    """Причина — человеку, и никакого `WWW-Authenticate`.

    Заголовок заставил бы браузер открыть системное окно ввода пароля, а паролей
    приложение не спрашивает вовсе: вход живёт на стороне Keycloak, и это окно
    было бы приглашением ввести доменный пароль неизвестно куда.
    """
    response = anonymous_client.get(CITIES)
    assert response.status_code == 401
    assert response.json()["detail"] == "Нужно войти под доменной учётной записью."
    assert "WWW-Authenticate" not in response.headers


def test_healthcheck_stays_open(anonymous_client):
    """Мониторинг не умеет логиниться и не должен."""
    assert anonymous_client.get("/healthcheck").status_code == 200


# --- вторая граница: вошёл, но не админ --------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", CITIES, {"slug": "kerch", "name": "Керчь"}),
        ("patch", f"{CITIES}/simferopol", {"name": "Другое имя"}),
        ("patch", f"{CITIES}/simferopol", {"is_active": False}),
        ("post", f"{CITIES}/simferopol/routes", {"slug": "route-9", "name": "Новый"}),
        ("patch", f"{CITIES}/simferopol/routes/route-1", {"name": "Другое имя"}),
        ("post", f"{CITIES}/simferopol/routes/route-1/assignments", {}),
        ("patch", f"/api/v1/assignments/{MISSING_ID}", {"description": "x"}),
        ("patch", f"/api/v1/assignments/{MISSING_ID}", {"is_active": False}),
        ("post", USERS, {"full_name": "Кто угодно"}),
        ("patch", f"{USERS}/{MISSING_ID}", {"full_name": "Кто угодно"}),
    ],
    ids=[
        "создать город",
        "правка города",
        "скрыть город",
        "создать маршрут",
        "правка маршрута",
        "создать задание",
        "правка задания",
        "скрыть задание",
        "завести человека",
        "правка человека",
    ],
)
def test_admin_writes_are_403_for_a_plain_user(user_client, method, url, body):
    """403, а не 401: человек вошёл, и на форму входа его гнать бессмысленно."""
    assert getattr(user_client, method)(url, json=body).status_code == 403


def test_geometry_writes_need_admin(user_client):
    """Обе двери к геометрии под правами, хотя ведут себя по-разному.

    Дорожный слой города заливают файлом, а линию маршрута рисуют мышью и
    присылают точками. Ручки разные, глаголы разные — проверять надо обе.
    """
    assert _upload(user_client, f"{CITIES}/simferopol/roads-geometry").status_code == 403
    assert (
        user_client.post(
            f"{CITIES}/simferopol/routes/route-1/geometry",
            json={"stroke": [[34.10, 44.95], [34.11, 44.96]]},
        ).status_code
        == 403
    )


def test_catalog_writes_need_admin(user_client):
    """Каталог заменяется целиком: одна кнопка — и в городе другие конструкции."""
    upload = user_client.post(
        f"{CITIES}/simferopol/catalog/imports",
        files={"files": ("catalog.csv", io.BytesIO(b"adress;lat;lon\n"))},
        data={"uploaded_by_user_id": MISSING_ID},
    )
    assert upload.status_code == 403
    for action in ("apply", "restore", "hide"):
        assert (
            user_client.post(
                f"/api/v1/catalog/imports/{MISSING_ID}/{action}"
            ).status_code
            == 403
        )
    assert (
        user_client.delete(f"/api/v1/catalog/imports/{MISSING_ID}").status_code == 403
    )


def test_closed_write_changes_nothing(user_client, client):
    """403 обязан быть отказом, а не «приняли, но не показали»."""
    before = payload(client.get(f"{CITIES}/simferopol"))["name"]
    user_client.patch(f"{CITIES}/simferopol", json={"name": "Взломано"})
    assert payload(client.get(f"{CITIES}/simferopol"))["name"] == before


# --- скрытые записи: режим просмотра админ-панели ----------------------------


def test_hidden_records_are_silently_ignored_for_a_plain_user(user_client):
    """`include_inactive` гасится молча, а не отвечает отказом.

    Скрытые города и задания — не тайна, а мусор в интерфейсе. Человек,
    дописавший параметр в адресную строку, должен увидеть обычный список, а не
    сообщение об отказе: отказ намекал бы, что там есть что-то интересное.
    """
    assert user_client.get(f"{CITIES}?include_inactive=true").status_code == 200
    assert user_client.get(f"{USERS}?include_inactive=true").status_code == 200
    assignments = f"{CITIES}/simferopol/routes/route-1/assignments"
    assert user_client.get(f"{assignments}?include_inactive=true").status_code == 200


def test_hidden_city_is_visible_to_admin_only(client, user_client):
    """Смысл флага: одна и та же ручка отвечает разным составом.

    Проверяется не код ответа, а содержимое, — иначе тест прошёл бы и на
    заглушке, которая флаг просто игнорирует.
    """
    client.post(CITIES, json={"slug": "hidden-town", "name": "Скрытый"})
    client.patch(f"{CITIES}/hidden-town", json={"is_active": False})

    def slugs(response):
        return {city["slug"] for city in payload(response)}

    assert "hidden-town" in slugs(client.get(f"{CITIES}?include_inactive=true"))
    assert "hidden-town" not in slugs(user_client.get(f"{CITIES}?include_inactive=true"))
    assert "hidden-town" not in slugs(user_client.get(CITIES))


# --- что вошедшему открыто ---------------------------------------------------


def test_product_reads_are_open_to_any_logged_in_user(user_client):
    """Весь продукт читает справочник городов — правами это не закрывают."""
    assert user_client.get(CITIES).status_code == 200
    assert user_client.get(f"{CITIES}/simferopol").status_code == 200
    assert user_client.get(f"{CITIES}/simferopol/roads-geometry").status_code == 200
    # 404, а не 200: у сидового маршрута линии нет, пока её не нарисуют. Здесь
    # важно ровно одно — что это не 401 и не 403.
    assert (
        user_client.get(f"{CITIES}/simferopol/routes/route-1/geometry").status_code
        == 404
    )
    assert user_client.get("/api/v1/runs").status_code == 200
    assert user_client.get(USERS).status_code == 200


def test_assignment_reads_and_uploading_stay_open_to_a_plain_user(user_client, client):
    """Граница проходит между «завести кампанию» и «сдать в неё проезд».

    Задание заводит ответственный, но выбирает его при загрузке водитель, и
    список заданий читает каждая форма загрузки. Закрыть это правами значило бы
    закрыть саму загрузку — операционную работу, ради которой продукт и есть.
    """
    assignments = f"{CITIES}/simferopol/routes/route-1/assignments"
    created = payload(client.post(assignments, json={}))

    assert user_client.get(assignments).status_code == 200
    assert user_client.get(f"/api/v1/assignments/{created['id']}").status_code == 200
    assert (
        user_client.post(
            "/api/v1/runs",
            json={
                "file_name": "pass.mp4",
                "content_type": "video/mp4",
                "size_bytes": 1024,
                "assignment_id": created["id"],
                "shot_started_at": "2026-08-02T09:30:00Z",
            },
        ).status_code
        == 201
    )


# --- кто вошёл ---------------------------------------------------------------


def test_me_reports_permissions_and_hides_raw_groups(client, user_client):
    """По этому ответу фронт решает, рисовать ли админ-панель.

    Сырых групп здесь нет намеренно: в них вся оргструктура компании — отделы,
    рассылки, доступы к шарам, — а интерфейсу нужны только права.
    """
    admin = payload(client.get(ME))
    assert admin["permissions"] == ["admin"]
    assert "groups_raw" not in admin
    assert "groups" not in admin

    plain = payload(user_client.get(ME))
    assert plain["permissions"] == []
    assert plain["full_name"]
