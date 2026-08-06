from __future__ import annotations

import re

from application.common.dto import UserDTO
from application.exceptions import (
    CatalogNotFoundError,
    InvalidUserError,
    UserAlreadyExistsError,
)
from application.interfaces import UserRepository


def normalize_full_name(value: str) -> str:
    """Схлопывает пробелы: «Иванов  Иван » и «Иванов Иван» — один человек.

    Без этого уникальность по имени не работает, а в селекторе заводятся
    близнецы, отличающиеся невидимым пробелом.
    """
    return re.sub(r"\s+", " ", value).strip()


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def list_users(self, *, include_inactive: bool = False) -> list[UserDTO]:
        return self._repository.list_users(include_inactive=include_inactive)

    def create_user(self, *, full_name: str) -> UserDTO:
        name = normalize_full_name(full_name)
        if not name:
            raise InvalidUserError("Укажите ФИО.")
        if self._repository.find_by_name(name) is not None:
            raise UserAlreadyExistsError("Такой человек уже есть в справочнике.")
        user = self._repository.create_user(full_name=name)
        self._repository.commit()
        return user

    def update_user(
        self,
        user_id: str,
        *,
        full_name: str | None = None,
        is_active: bool | None = None,
    ) -> UserDTO:
        name = normalize_full_name(full_name) if full_name is not None else None
        if name is not None:
            if not name:
                raise InvalidUserError("Укажите ФИО.")
            existing = self._repository.find_by_name(name)
            if existing is not None and existing.id != user_id:
                raise UserAlreadyExistsError("Такой человек уже есть в справочнике.")

        user = self._repository.update_user(
            user_id,
            full_name=name,
            is_active=is_active,
        )
        if user is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Человек не найден в справочнике.")
        self._repository.commit()
        return user
