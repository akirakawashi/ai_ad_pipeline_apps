"""Пароль админ-панели: проверка на бэкенде, а не ширма на фронте.

Одна пара логин/пароль на всех — это не авторизация и не роли. Задача узкая:
внутри корпоративной сети отгородить правку городов и маршрутов от сотрудников,
которым туда не надо. Кто полезет целенаправленно — пройдёт, и это принято.

Проверка живёт на бэкенде принципиально. Форма на фронте отгораживает только
страницу, а `PATCH /cities/...` из консоли браузера прошёл бы мимо неё — то
есть защищала бы она ровно от тех, кто и так ничего бы не сломал.

Пароль может быть на любом языке. Это не прихоть: продукт русский, и владелец
скорее поставит русский пароль, чем латинский. Штатный `HTTPBasic` из FastAPI
так не умеет — он декодирует заголовок как ASCII, — поэтому разбор здесь свой
(см. `_Utf8HTTPBasic`).
"""

from __future__ import annotations

import binascii
from base64 import b64decode
from secrets import compare_digest

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from settings.factory import get_settings


class _Utf8HTTPBasic(HTTPBasic):
    """HTTP Basic, читающий заголовок как UTF-8, а не как ASCII.

    Штатная реализация делает `b64decode(param).decode("ascii")` и на первой же
    нелатинской букве отвечает своей ошибкой — безусловно, `auto_error` она при
    этом не спрашивает. Последствий два, и оба плохие: с русским паролем в
    панель нельзя войти вовсе (верный пароль не переживает декод, а неверный
    роняет сравнение), а человек, промахнувшийся раскладкой, видит английское
    «Not authenticated» вместо нашего текста.

    Поэтому наследуемся, а не пишем зависимость с нуля: базовый класс держит
    описание схемы для OpenAPI, и в `/docs` замок остаётся на месте.

    Ни одна ветка здесь не бросает исключение — всё непонятное отдаётся как
    `None`, а решение принимает `_verify`. Так единственный ответ про пароль
    формируется в одном месте и всегда по-русски.
    """

    # Подавление на сигнатуре — как у самого FastAPI: общий предок HTTPBase
    # обещает другой тип учётных данных, и штатный HTTPBasic глушит это ровно
    # так же.
    async def __call__(  # type: ignore[override]
        self, request: Request
    ) -> HTTPBasicCredentials | None:
        authorization = request.headers.get("Authorization")
        scheme, _, param = (authorization or "").partition(" ")
        if scheme.lower() != "basic" or not param:
            return None
        try:
            decoded = b64decode(param).decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
        username, separator, password = decoded.partition(":")
        # Разделителя нет — это не пара «логин:пароль», а мусор.
        if not separator:
            return None
        return HTTPBasicCredentials(username=username, password=password)


# auto_error=False честно описывает поведение: наш разбор не бросает сам, а
# возвращает None, и русский ответ формирует `_verify`.
_basic = _Utf8HTTPBasic(auto_error=False)

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

    Сравниваем байты, а не строки: `compare_digest` на строках требует чистого
    ASCII и на русском пароле падает с TypeError, то есть отдаёт 500 вместо 401.
    На байтах он работает с любым содержимым.
    """
    if credentials is None:
        raise _UNAUTHORIZED
    settings = get_settings()
    login_ok = compare_digest(
        credentials.username.encode("utf-8"),
        settings.admin_username.encode("utf-8"),
    )
    password_ok = compare_digest(
        credentials.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )
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
