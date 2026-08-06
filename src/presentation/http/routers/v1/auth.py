from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from application.common.dto import AuthenticatedUserDTO
from application.exceptions import AuthenticationError
from application.services.auth_service import AuthService
from presentation.http.auth import (
    SESSION_COOKIE,
    STATE_COOKIE,
    clear_session_cookie,
    clear_state_cookie,
    current_user,
    set_session_cookie,
    set_state_cookie,
)
from presentation.http.dependencies import get_auth_service
from presentation.http.dto.response import (
    AuthModeResponse,
    CurrentUserResponse,
    OkResponse,
)
from settings.factory import get_settings

router = APIRouter(prefix="/auth", tags=["Auth"])

# Вход происходит не у нас. Человек уходит на корпоративный Keycloak, вводит там
# доменный пароль и возвращается — приложение формы пароля не показывает и
# паролей не видит. Логин и выход поэтому редиректы, а не JSON-ручки: их конечный
# потребитель — адресная строка браузера, а не `fetch`.


@router.get("/login")
def login(
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Кнопка «Войти»: уводит браузер на форму Keycloak.

    Адрес собирается здесь, а не зашивается ссылкой во фронт, из-за `state`. Это
    случайная строка, которая кладётся в cookie и сверяется на возврате: без неё
    злоумышленник может подсунуть человеку свой callback-адрес и привязать чужую
    сессию к своей учётке. Выдать и запомнить `state` может только сервер, так что
    статическая ссылка в разметке эту защиту потеряла бы.

    307, а не 302: браузер обязан сохранить метод, а не превратить запрос в GET
    по своему усмотрению.

    В режиме `AUTH_USE_KEYCLOAK=false` уводить браузер некуда, и ручка отвечает
    503 с внятной причиной, а не редиректом на пустой адрес. До этого дело
    обычно не доходит: интерфейс в этом режиме показывает форму, а не кнопку, —
    но ручка обязана отвечать осмысленно и когда её позвали напрямую.
    """
    if not get_settings().auth.use_keycloak:
        raise HTTPException(
            status_code=503,
            detail="Вход через Keycloak выключен.",
        )
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(service.authorization_url(state=state), status_code=307)
    set_state_cookie(response, state)
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Возврат из Keycloak: код в обмен на сессию.

    Ответ — всегда редирект на фронт, в том числе при отказе. Человек здесь не
    видит нашего JSON: он в адресной строке, и единственный осмысленный для него
    исход — вернуться в приложение, с сессией или с объяснением в параметре.

    Токен наружу не отдаётся ни в каком виде. В браузер уходит только
    непрозрачный ключ сессии в `HttpOnly`-cookie.
    """
    frontend = get_settings().auth.frontend_url

    if error:
        # Keycloak отказал сам — например, человек закрыл форму или его учётка
        # заблокирована в домене. Текст ошибки в адрес не тащим: он от чужого
        # сервиса и в интерфейсе бесполезен.
        return _back_to_frontend(frontend, "denied")

    expected_state = request.cookies.get(STATE_COOKIE)
    if not state or not expected_state or not secrets.compare_digest(
        state, expected_state
    ):
        # Сравнение постоянного времени — `state` секрет на время входа.
        return _back_to_frontend(frontend, "state")

    if not code:
        return _back_to_frontend(frontend, "denied")

    try:
        _, key, expires_at = service.complete_login(code=code)
    except AuthenticationError:
        return _back_to_frontend(frontend, "failed")

    response = _back_to_frontend(frontend, None)
    # Cookie живёт ровно столько же, сколько сессия в базе, — до `exp` токена.
    # В IC-GROUP это 8 часов без обновления: один рабочий день на один вход.
    now = datetime.now(tz=timezone.utc).timestamp()
    max_age = max(int(expires_at.timestamp() - now), 0)
    set_session_cookie(response, key, max_age=max_age)
    clear_state_cookie(response)
    return response


class DevLoginRequest(BaseModel):
    username: str
    password: str


@router.get("/mode", response_model=OkResponse[AuthModeResponse])
def mode() -> OkResponse[AuthModeResponse]:
    """Каким способом входят. Единственная ручка, открытая без сессии.

    Нужна фронту до входа: по ней он решает, показать кнопку «Войти» (уводит на
    Keycloak) или форму логина и пароля. Иначе экран входа пришлось бы
    зашивать под режим на сборке, и одна и та же сборка не смогла бы работать в
    обоих.

    Наружу отдаётся один флаг и ничего больше. Адрес Keycloak, client_id и тем
    более секрет здесь не нужны: браузер к Keycloak сам не ходит, его уводит
    `/auth/login`.
    """
    return OkResponse(data=AuthModeResponse(keycloak=get_settings().auth.use_keycloak))


@router.post("/dev-login", response_model=OkResponse[CurrentUserResponse])
def dev_login(
    payload: DevLoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> OkResponse[CurrentUserResponse]:
    """Вход по логину и паролю: режим `AUTH_USE_KEYCLOAK=false`.

    В режиме Keycloak отвечает 404, а не 403: ручки, которой нет, не должно
    быть видно и в отказах.

    В отличие от настоящего входа это обычный JSON, а не редирект: уходить
    некуда, форма здесь же. Ответ — тот же `CurrentUserResponse`, что у `/me`,
    чтобы фронт после входа не ходил за собой вторым запросом.
    """
    if get_settings().auth.use_keycloak:
        raise HTTPException(status_code=404, detail="Not Found")
    user, key, expires_at = service.dev_login(
        username=payload.username,
        password=payload.password,
    )
    now = datetime.now(tz=timezone.utc).timestamp()
    set_session_cookie(response, key, max_age=max(int(expires_at.timestamp() - now), 0))
    return OkResponse(data=CurrentUserResponse.model_validate(user))


@router.get("/logout")
def logout(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Гасит нашу сессию и возвращает на фронт.

    В Keycloak выход не транслируется намеренно: его SSO-сессия живёт своей
    жизнью, и вошедший заново не увидит формы пароля, пока она не истекла. Это
    ожидаемое поведение корпоративного входа, а backchannel-logout заодно выкинул
    бы человека из соседних приложений того же realm.
    """
    key = request.cookies.get(SESSION_COOKIE)
    if key:
        service.logout(key)
    response = _back_to_frontend(get_settings().auth.frontend_url, None)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=OkResponse[CurrentUserResponse])
def me(
    user: AuthenticatedUserDTO = Depends(current_user),
) -> OkResponse[CurrentUserResponse]:
    """Кто вошёл и что ему можно. Единственная JSON-ручка входа.

    Фронт зовёт её на старте: 200 — показываем приложение и по `permissions`
    решаем, рисовать ли админ-панель; 401 — показываем кнопку «Войти».
    """
    return OkResponse(data=CurrentUserResponse.model_validate(user))


def _back_to_frontend(frontend: str, reason: str | None) -> RedirectResponse:
    target = frontend if reason is None else f"{frontend}/?auth_error={reason}"
    return RedirectResponse(target, status_code=307)
