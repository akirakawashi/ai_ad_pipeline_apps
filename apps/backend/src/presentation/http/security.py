"""Пароль админ-панели: проверка на бэкенде, а не ширма на фронте.

Одна пара логин/пароль на всех — это не авторизация и не роли. Задача узкая:
внутри корпоративной сети отгородить правку городов и маршрутов от сотрудников,
которым туда не надо. Кто полезет целенаправленно — пройдёт, и это принято.

Проверка живёт на бэкенде принципиально. Форма на фронте отгораживает только
страницу, а `PATCH /cities/...` из консоли браузера прошёл бы мимо неё — то
есть защищала бы она ровно от тех, кто и так ничего бы не сломал.
"""

from __future__ import annotations

from secrets import compare_digest

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from settings.factory import get_settings

# auto_error=False: заголовка может не быть вовсе, и тогда мы хотим отдать свой
# ответ с русской причиной, а не стандартный текст библиотеки.
_basic = HTTPBasic(auto_error=False)

# Заголовок обязателен по RFC 7235, но realm намеренно без браузерного окна:
# фронт показывает свою форму, а системный диалог поверх неё сбивал бы с толку.
_UNAUTHORIZED = HTTPException(
    status_code=401,
    detail="Админ-панель под паролем. Введите логин и пароль.",
    headers={"WWW-Authenticate": 'Basic realm="admin", charset="UTF-8"'},
)


def _verify(credentials: HTTPBasicCredentials | None) -> None:
    """Сравнение постоянного времени: иначе пароль подбирается по задержке.

    Обе половины сравниваем всегда, без короткого замыкания на логине, — по той
    же причине.
    """
    if credentials is None:
        raise _UNAUTHORIZED
    settings = get_settings()
    login_ok = compare_digest(credentials.username, settings.admin_username)
    password_ok = compare_digest(credentials.password, settings.admin_password)
    if not (login_ok and password_ok):
        raise _UNAUTHORIZED


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    """Зависимость для всего, что меняет города и маршруты."""
    _verify(credentials)


def allow_hidden(
    include_inactive: bool = Query(
        default=False,
        description="Показывать скрытые — только для админ-панели, под паролем",
    ),
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> bool:
    """`include_inactive` — админский режим просмотра, поэтому тоже под паролем.

    Пароль спрашивается только когда флаг поднят: обычный список городов должен
    оставаться открытым, его читает весь интерфейс.
    """
    if include_inactive:
        _verify(credentials)
    return include_inactive
