from __future__ import annotations

from datetime import datetime
from typing import Protocol

from application.common.dto import AuthenticatedUserDTO
from domain.auth import IdentityClaims


class IdentityProvider(Protocol):
    """Keycloak за интерфейсом.

    Не ради абстрактной чистоты: корпоративный `ssoc.ic-group.ru` из сети
    разработчика не виден, а клиент под это приложение в IC-GROUP ещё не заведён.
    Граница здесь позволяет тестам подставлять готовые claim'ы и не поднимать
    ничего, а `pytest` — не зависеть от живого Keycloak.
    """

    def authorization_url(self, *, state: str) -> str:
        """Адрес формы входа Keycloak, куда уводится браузер."""
        ...

    def claims_for_code(self, *, code: str) -> IdentityClaims:
        """Обмен кода на токен и разбор токена с проверкой подписи."""
        ...


class AuthRepository(Protocol):
    """Пользователи и сессии. Транзакцию открывает, но не коммитит."""

    def upsert_by_subject(
        self,
        *,
        subject: str,
        username: str,
        full_name: str,
        email: str | None,
        groups: list[str],
        permissions: list[str],
    ) -> AuthenticatedUserDTO: ...

    def create_session(
        self,
        *,
        token_hash: str,
        user_id: str,
        expires_at: datetime,
    ) -> None: ...

    def find_session_user(self, *, token_hash: str) -> AuthenticatedUserDTO | None:
        """Владелец живой сессии. None — сессии нет либо она истекла."""
        ...

    def delete_session(self, *, token_hash: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
