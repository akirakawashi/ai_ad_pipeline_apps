"""Сквозной поток доменного входа: кнопка → редирект → возврат → сессия.

Единственное место, где путь Keycloak выполняется целиком, а не описывается в
докстрингах. Проверять его больше негде: Keycloak в компании только продовый,
копии для разработки нет, и до развёртывания сервиса живого обмена кода не
случится ни разу.

Поэтому подменяется ровно одна вещь — `IdentityProvider`. Всё остальное
настоящее: роутер, сверка `state`, cookie, запись в справочник, строка сессии,
проверка сессии на следующем запросе. Граница проведена там, где кончается наш
код и начинается чужой сервис, — ради этого интерфейс и заводился.

Что здесь **не** проверяется и проверено быть не может: подпись токена, формат
claim'ов IC-GROUP, работа `redirect_uri` на стороне Keycloak. Это выяснится на
первом развёртывании, и `AUTH_CLAIMS_DUMP_PATH` существует ровно для этого.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from application.exceptions import AuthenticationError
from conftest import ADMIN_GROUP, payload
from domain.auth import IdentityClaims
from main import app
from presentation.http.auth import SESSION_COOKIE, STATE_COOKIE
from presentation.http.dependencies import get_identity_provider
from settings.factory import get_settings as real_settings

LOGIN = "/api/v1/auth/login"
CALLBACK = "/api/v1/auth/callback"
ME = "/api/v1/auth/me"
CITIES = "/api/v1/cities"

ISSUER = "https://ssoc.ic-group.ru/realms/IC-GROUP"
FRONTEND = "http://localhost:5173"

# Похоже на то, что ожидается из IC-GROUP: полный путь групп, лишние группы,
# кириллица. Осмысленная для приложения здесь одна.
CLAIMS = IdentityClaims(
    subject="f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
    username="i.obychny",
    full_name="Иван Обычный",
    email="i.obychny@ic-group.ru",
    groups=("/Departments/Marketing", "/Рассылки/Все сотрудники", ADMIN_GROUP),
    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=8),
    raw={"sub": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"},
)


class FakeKeycloak:
    """Keycloak, который всегда отвечает одинаково. Или не отвечает вовсе."""

    def __init__(self, *, claims: IdentityClaims | None = CLAIMS) -> None:
        self._claims = claims
        self.codes: list[str] = []

    def authorization_url(self, *, state: str) -> str:
        return f"{ISSUER}/protocol/openid-connect/auth?state={state}"

    def claims_for_code(self, *, code: str) -> IdentityClaims:
        self.codes.append(code)
        if self._claims is None:
            raise AuthenticationError("Keycloak отклонил код авторизации.")
        return self._claims


class _Settings:
    """Настройки в режиме Keycloak.

    Подменяются, а не берутся из окружения: `get_settings` кэширован на первом
    обращении, а conftest ставит парольный режим до импорта приложения — иначе
    тесты требовали бы настоящих реквизитов.
    """

    use_keycloak = True
    configured = True
    frontend_url = FRONTEND
    admin_groups = frozenset({ADMIN_GROUP})
    claims_dump_path = None


class _Root:
    """Настройки целиком, но с подменённым разделом входа.

    Остальное отдаём настоящее: те же ручки по дороге просят `object_storage` и
    `database`, и заглушка на весь объект уронила бы их с `AttributeError`.
    """

    auth = _Settings()

    def __getattr__(self, name: str) -> object:
        return getattr(real_settings(), name)


@pytest.fixture
def keycloak(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeKeycloak]:
    provider = FakeKeycloak()
    monkeypatch.setattr(
        "presentation.http.routers.v1.auth.get_settings", lambda: _Root()
    )
    monkeypatch.setattr("presentation.http.dependencies.get_settings", lambda: _Root())
    app.dependency_overrides[get_identity_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_identity_provider, None)


@pytest.fixture
def browser(keycloak: FakeKeycloak) -> TestClient:
    """Клиент, сохраняющий cookie между запросами, — как настоящий браузер.

    Без этого `state` не пережил бы дорогу до `/callback`, и поток проверялся бы
    вхолостую.
    """
    return TestClient(app, follow_redirects=False)


def _start_login(browser: TestClient) -> str:
    """Проходит `/login` и возвращает `state`, который уехал бы на Keycloak."""
    response = browser.get(LOGIN)
    assert response.status_code == 307
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query["state"][0]


# --- поток целиком ------------------------------------------------------------


def test_full_login_creates_a_working_session(browser, keycloak):
    """Главный сценарий: от кнопки до работающего запроса к API.

    Проверяется не «ручки отвечают», а что после возврата из Keycloak человек
    действительно может пользоваться приложением: сессия найдена, права
    посчитаны из групп, закрытый API отвечает данными.
    """
    state = _start_login(browser)
    assert browser.cookies[STATE_COOKIE] == state

    done = browser.get(CALLBACK, params={"code": "abc123", "state": state})
    assert done.status_code == 307
    assert done.headers["location"] == FRONTEND
    assert keycloak.codes == ["abc123"]

    # Метка одноразовая: отработала — гасится.
    assert browser.cookies.get(STATE_COOKIE) is None
    assert browser.cookies.get(SESSION_COOKIE)

    me = payload(browser.get(ME))
    assert me["full_name"] == "Иван Обычный"
    assert me["username"] == "i.obychny"
    # Три группы приехали, право дала одна — та, что в белом списке.
    assert me["permissions"] == ["admin"]

    assert browser.get(CITIES).status_code == 200


def test_login_puts_state_into_both_the_address_and_the_cookie(browser):
    """Метка уезжает двумя путями — иначе сверять на возврате было бы нечего."""
    state = _start_login(browser)
    assert len(state) >= 32
    assert browser.cookies[STATE_COOKIE] == state


def test_person_appears_in_the_directory_on_first_login(browser, client):
    """Запись заводится сама: справочник больше не ведут руками.

    Смотрим справочник админским клиентом, а не через `/auth/me`: важно, что
    человек появился именно в том списке, из которого выбирают «кто загрузил».
    """
    state = _start_login(browser)
    browser.get(CALLBACK, params={"code": "abc123", "state": state})

    people = payload(client.get("/api/v1/users?include_inactive=true"))
    assert [person["full_name"] for person in people] == ["Иван Обычный"]


def test_second_login_updates_instead_of_duplicating(browser, client):
    """Связь по `sub`, а не по ФИО: второй вход не плодит близнеца."""
    for _ in range(2):
        state = _start_login(browser)
        browser.get(CALLBACK, params={"code": "abc123", "state": state})

    people = payload(client.get("/api/v1/users?include_inactive=true"))
    assert len(people) == 1


# --- отказы -------------------------------------------------------------------


def test_foreign_state_is_refused(browser):
    """Подменённая метка — вход не проходит.

    Без этой проверки человеку можно подсунуть чужой код и залогинить его в
    чужую учётную запись, а он бы не заметил.
    """
    _start_login(browser)
    response = browser.get(CALLBACK, params={"code": "abc123", "state": "чужой"})
    assert response.status_code == 307
    assert response.headers["location"] == f"{FRONTEND}/?auth_error=state"
    assert browser.cookies.get(SESSION_COOKIE) is None


def test_callback_without_cookie_is_refused(browser):
    """Cookie нет — сверять не с чем. Так выглядит попытка старше пяти минут."""
    response = browser.get(CALLBACK, params={"code": "abc123", "state": "любой"})
    assert response.headers["location"] == f"{FRONTEND}/?auth_error=state"


def test_keycloak_refusal_comes_back_as_a_reason_not_a_json(browser):
    """Человек в адресной строке: он должен вернуться в приложение, а не в JSON."""
    state = _start_login(browser)
    response = browser.get(CALLBACK, params={"error": "access_denied", "state": state})
    assert response.status_code == 307
    assert response.headers["location"] == f"{FRONTEND}/?auth_error=denied"


def test_broken_exchange_comes_back_as_a_reason(browser, keycloak, monkeypatch):
    """Keycloak недоступен или отверг код — тоже возврат, а не 502 с JSON."""
    monkeypatch.setattr(keycloak, "_claims", None)
    state = _start_login(browser)
    response = browser.get(CALLBACK, params={"code": "abc123", "state": state})
    assert response.headers["location"] == f"{FRONTEND}/?auth_error=failed"
    assert browser.cookies.get(SESSION_COOKIE) is None


def test_hidden_person_cannot_sign_in(browser, client):
    """Домен пустил, а мы скрыли — и это возврат с причиной, а не голый 403.

    Раньше `InactiveUserError` пролетала до обработчика, и человек в адресной
    строке видел `{"detail": ...}` вместо приложения.
    """
    state = _start_login(browser)
    browser.get(CALLBACK, params={"code": "abc123", "state": state})

    person = payload(client.get("/api/v1/users?include_inactive=true"))[0]
    client.patch(f"/api/v1/users/{person['id']}", json={"is_active": False})

    browser.cookies.clear()
    state = _start_login(browser)
    response = browser.get(CALLBACK, params={"code": "abc123", "state": state})
    assert response.headers["location"] == f"{FRONTEND}/?auth_error=inactive"
    assert browser.cookies.get(SESSION_COOKIE) is None


# --- чего в этом режиме быть не должно ---------------------------------------


def test_password_login_does_not_exist_in_keycloak_mode(browser):
    """404, а не 403: ручки, которой нет, не должно быть видно и в отказах."""
    response = browser.post(
        "/api/v1/auth/dev-login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 404


def test_logout_clears_our_session_only(browser):
    """Выход гасит нашу сессию. В Keycloak он не транслируется намеренно."""
    state = _start_login(browser)
    browser.get(CALLBACK, params={"code": "abc123", "state": state})
    assert browser.get(ME).status_code == 200

    browser.get("/api/v1/auth/logout")
    assert browser.get(ME).status_code == 401
