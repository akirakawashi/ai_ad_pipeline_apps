from __future__ import annotations

from typing import Protocol

from application.common.dto import UserDTO


class UserRepository(Protocol):
    def list_users(self, *, include_inactive: bool) -> list[UserDTO]: ...

    def find_by_name(self, full_name: str) -> UserDTO | None: ...

    def create_user(self, *, full_name: str) -> UserDTO: ...

    def update_user(
        self,
        user_id: str,
        *,
        full_name: str | None,
        is_active: bool | None,
    ) -> UserDTO | None:
        """Возвращает None, если человека нет. Поля со значением None не трогает."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
