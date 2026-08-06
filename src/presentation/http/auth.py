"""Сессия в cookie и проверка прав. Заменяет прежний пароль админ-панели.

Токен Keycloak в браузер не попадает: браузер держит непрозрачный ключ сессии,
всё остальное живёт на backend. Так решаются сразу три вещи, каждая из которых
одна по себе потянула бы на обходной путь.

**Размер.** В корпоративном AD человек состоит в десятках групп, и токен с ними
распухает до килобайтов. Заголовок `Authorization` упирается в лимиты nginx и
uvicorn, cookie — в четыре килобайта. Обе границы задевают не среднего
сотрудника, а самого «тяжёлого»: ломается у одного человека из ста, и
воспроизвести это на своей учётке нельзя.

**Отзыв.** Токен в IC-GROUP живёт 8 часов и не отзывается: сотрудника отключили в
AD в девять утра, а его пропуск действителен до пяти вечера. Строка в
`user_sessions` — единственное место, где такого человека можно выкинуть сразу.

**Хранение.** Токен в `sessionStorage` читается любым скриптом на странице.
Ключ сессии лежит в `HttpOnly`-cookie, до которой JavaScript не дотягивается.
"""

from __future__ import annotations

from fastapi import Depends, Query, Request, Response

from application.common.dto import AuthenticatedUserDTO
from application.exceptions import PermissionDeniedError, SessionExpiredError
from application.services.auth_service import AuthService
from domain.auth import Permission
from presentation.http.dependencies import get_auth_service

SESSION_COOKIE = "ai_ad_session"

# Имя cookie с `state`. Она короткоживущая и нужна ровно между уходом на форму
# Keycloak и возвратом.
STATE_COOKIE = "ai_ad_auth_state"

# Столько живёт cookie со `state`. Пять минут — это «человек успел ввести пароль»,
# и при этом брошенная попытка входа не оставляет мусора на весь день.
STATE_TTL_SECONDS = 300


def set_session_cookie(response: Response, key: str, *, max_age: int) -> None:
    """Cookie сессии.

    `secure` намеренно не выставляется. Приложение живёт внутри корпоративной
    сети и на стенде открывается по `http://` — cookie с `secure` браузер в этом
    случае просто не сохранит, и вход перестанет работать вовсе. Когда появится
    HTTPS, флаг надо поднять, и это единственная строка, которую придётся тронуть.

    `samesite=lax`, а не `strict`: возврат с формы Keycloak — это переход с
    чужого домена, и при `strict` браузер не отдал бы cookie на первом же
    запросе после входа.
    """
    response.set_cookie(
        SESSION_COOKIE,
        key,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def set_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_state_cookie(response: Response) -> None:
    response.delete_cookie(STATE_COOKIE, path="/")


def current_user(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUserDTO:
    """Человек за запросом. Нет живой сессии — 401 и уход на форму входа."""
    key = request.cookies.get(SESSION_COOKIE)
    if not key:
        raise SessionExpiredError()
    return service.user_for_session(key)


def optional_user(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUserDTO | None:
    """То же, но без 401: для ручек, которым важно лишь, админ ли перед ними."""
    key = request.cookies.get(SESSION_COOKIE)
    if not key:
        return None
    try:
        return service.user_for_session(key)
    except (SessionExpiredError, PermissionError):
        return None


def require_admin(
    user: AuthenticatedUserDTO = Depends(current_user),
) -> AuthenticatedUserDTO:
    """Право на админ-панель: правка городов, маршрутов, заданий, каталога и людей.

    Граница ровно та же, что была у пароля, и это осознанно. Она проведена по
    цене ошибки, а не по сложности действия: администрирование меняет рамку, в
    которой все работают, а операционная работа — съёмки, загрузка видео,
    геозоны — остаётся открытой любому вошедшему, иначе продукт становится
    неработоспособным.
    """
    if not user.has(Permission.ADMIN):
        raise PermissionDeniedError(str(Permission.ADMIN))
    return user


def allow_hidden(
    include_inactive: bool = Query(
        default=False,
        description="Показывать скрытые — только для админ-панели",
    ),
    user: AuthenticatedUserDTO | None = Depends(optional_user),
) -> bool:
    """`include_inactive` — админский режим просмотра, и он под правом.

    Флаг молча гасится для неадминов, а не отвергается ошибкой. Скрытые города и
    задания — не тайна, а мусор в интерфейсе; человек, дописавший параметр в
    адресную строку, должен увидеть обычный список, а не сообщение об отказе.
    """
    if not include_inactive:
        return False
    return user is not None and user.has(Permission.ADMIN)


__all__ = [
    "SESSION_COOKIE",
    "STATE_COOKIE",
    "STATE_TTL_SECONDS",
    "allow_hidden",
    "clear_session_cookie",
    "clear_state_cookie",
    "current_user",
    "optional_user",
    "require_admin",
    "set_session_cookie",
    "set_state_cookie",
]
