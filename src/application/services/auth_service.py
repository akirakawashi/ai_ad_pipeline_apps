from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import compare_digest
from typing import Any

from application.common.dto import AuthenticatedUserDTO
from application.exceptions import InactiveUserError, SessionExpiredError
from application.interfaces.auth import AuthRepository, IdentityProvider
from domain.auth import Permission, permissions_for
from settings.auth import AuthSettings

# Длина ключа сессии в байтах. 32 — это 256 бит энтропии; ключ лежит в cookie и
# больше ничем не защищён, так что перебор должен быть безнадёжен.
_SESSION_KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class _DevAccount:
    password: str
    full_name: str
    is_admin: bool


# Учётки входа-заглушки. Пары простые намеренно: это не защита, а замена
# авторизации на время, пока Keycloak не подключён, и делать вид, что тут есть
# секрет, — хуже, чем честно написать `admin`/`admin`. Двух учёток достаточно:
# проверять надо обе стороны границы прав, а не только админскую.
_DEV_ACCOUNTS: dict[str, _DevAccount] = {
    "admin": _DevAccount("admin", "Локальный Админ", is_admin=True),
    "user": _DevAccount("user", "Локальный Сотрудник", is_admin=False),
}


def hash_session_key(key: str) -> str:
    """SHA-256 ключа сессии.

    В базе лежит хэш, а не сам ключ, по той же причине, по которой не хранят
    пароли: дамп `user_sessions` не должен давать возможности войти. Соль и
    медленный алгоритм здесь не нужны — ключ случайный и длинный, словарной атаки
    по нему не бывает.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class AuthService:
    """Вход, сессия и выход.

    Записи в справочнике заводятся сами при первом входе. Раньше человека заводил
    руками тот, кто в этот момент грузил видео, и справочник копил близнецов —
    «Иванов», «Иванов А.», «иванов». Теперь человек называет себя сам, доменной
    учёткой, и совпадение по `sub` делает дубли невозможными в принципе.
    """

    def __init__(
        self,
        repository: AuthRepository,
        provider: IdentityProvider,
        settings: AuthSettings,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._settings = settings

    def authorization_url(self, *, state: str) -> str:
        return self._provider.authorization_url(state=state)

    @staticmethod
    def new_session_key() -> str:
        return secrets.token_urlsafe(_SESSION_KEY_BYTES)

    def complete_login(self, *, code: str) -> tuple[AuthenticatedUserDTO, str, datetime]:
        """Обмен кода на сессию. Возвращает человека, ключ сессии и её срок.

        Срок берётся из `exp` токена, а не назначается своим: сессия приложения не
        должна переживать пропуск, по которому выдана. В IC-GROUP токен живёт
        8 часов и не обновляется — один рабочий день на один вход, после чего
        человек логинится заново.

        Сам токен никуда не сохраняется. Он нужен ровно здесь: узнать, кто пришёл
        и в каких он группах. Дальше приложение от имени человека никуда не ходит,
        и хранить живой пропуск было бы риском без применения.
        """
        claims = self._provider.claims_for_code(code=code)
        self._dump_claims(claims.raw)

        permissions = permissions_for(
            claims.groups,
            admin_groups=self._settings.admin_groups,
        )
        user = self._repository.upsert_by_subject(
            subject=claims.subject,
            username=claims.username,
            full_name=claims.full_name,
            email=claims.email,
            groups=list(claims.groups),
            permissions=sorted(str(item) for item in permissions),
        )
        if not user.is_active:
            # Человека скрыли в админ-панели — это ручной запрет работать, и он
            # должен пережить успешную проверку пароля в домене.
            raise InactiveUserError(user.full_name)

        key = self.new_session_key()
        self._repository.create_session(
            token_hash=hash_session_key(key),
            user_id=user.id,
            expires_at=claims.expires_at,
        )
        self._repository.commit()
        return user, key, claims.expires_at

    def dev_login(
        self, *, username: str, password: str
    ) -> tuple[AuthenticatedUserDTO, str, datetime]:
        """Вход без Keycloak: режим `AUTH_USE_KEYCLOAK=false`.

        Keycloak в компании только продовый, копии для разработки нет, — до
        развёртывания это единственный способ работать с приложением.

        Дальше по коду это неотличимо от настоящего входа: та же запись в
        справочнике, та же строка в `user_sessions`, тот же срок. Иначе
        отлаженный на заглушке экран вёл бы себя иначе на живом Keycloak, и
        смысл заглушки терялся бы.

        Работает только при `AUTH_USE_KEYCLOAK=false`. Проверка живёт и здесь,
        не только в роутере, — на случай, если метод однажды вызовут в обход
        HTTP-слоя.
        """
        if self._settings.use_keycloak:
            raise SessionExpiredError()
        expected = _DEV_ACCOUNTS.get(username)
        if expected is None or not compare_digest(password, expected.password):
            raise SessionExpiredError()

        permissions = [str(Permission.ADMIN)] if expected.is_admin else []
        user = self._repository.upsert_by_subject(
            # Префикс намеренно нечитаемый как UUID: если такая запись однажды
            # окажется в настоящей базе, видно сразу, откуда она.
            subject=f"dev-login:{username}",
            username=username,
            full_name=expected.full_name,
            email=None,
            groups=[],
            permissions=permissions,
        )
        key = self.new_session_key()
        # Те же 8 часов, что в IC-GROUP: срок сессии должен вести себя одинаково.
        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=8)
        self._repository.create_session(
            token_hash=hash_session_key(key),
            user_id=user.id,
            expires_at=expires_at,
        )
        self._repository.commit()
        return user, key, expires_at

    def user_for_session(self, key: str) -> AuthenticatedUserDTO:
        user = self._repository.find_session_user(token_hash=hash_session_key(key))
        if user is None:
            raise SessionExpiredError()
        if not user.is_active:
            raise InactiveUserError(user.full_name)
        return user

    def logout(self, key: str) -> None:
        """Гасит только нашу сессию.

        В Keycloak выход не транслируется намеренно. Его SSO-сессия живёт своей
        жизнью, и человек, вышедший из приложения, при следующем входе вернётся
        без формы пароля — ровно то поведение, которого ждут от корпоративного
        входа. Backchannel-logout сломал бы его и заодно выкинул человека из
        соседних приложений того же realm.
        """
        self._repository.delete_session(token_hash=hash_session_key(key))
        self._repository.commit()

    def _dump_claims(self, payload: dict[str, Any]) -> None:
        """Разведочная запись claim'ов: одна строка JSON на вход.

        Состав групп в IC-GROUP пока не известен, а настроить белый список
        вслепую нельзя — сначала надо увидеть, что реально приезжает. Пишется
        разобранный payload и никогда сам токен: токен до истечения это живой
        пропуск, и файл с ним стал бы связкой ключей.

        Внутри ФИО, доменные логины и оргструктура компании — персданные. Файл
        под `.gitignore` и в общий лог приложения не уезжает. Выключается пустым
        `AUTH_CLAIMS_DUMP_PATH`, как только группы известны.

        Сбой записи не мешает войти: разведка не повод не пускать человека
        работать.
        """
        target = self._settings.claims_dump_path
        if not target:
            return
        record = {
            "logged_at": datetime.now(tz=timezone.utc).isoformat(),
            "claims": payload,
        }
        try:
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            return


__all__ = ["AuthService", "Permission", "hash_session_key"]
