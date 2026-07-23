from __future__ import annotations

from sqlmodel import Session, select

from application.common.dto import UserDTO
from infrastructure.database.models import User


def _user_to_dto(user: User) -> UserDTO:
    return UserDTO(
        id=user.users_id,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_users(self, *, include_inactive: bool) -> list[UserDTO]:
        statement = select(User)
        if not include_inactive:
            statement = statement.where(User.is_active.is_(True))
        users = self._session.exec(statement.order_by(User.full_name)).all()
        return [_user_to_dto(user) for user in users]

    def _get_model(self, user_id: str) -> User | None:
        return self._session.exec(
            select(User).where(User.users_id == user_id)
        ).first()

    def get_user(self, user_id: str) -> UserDTO | None:
        user = self._get_model(user_id)
        return None if user is None else _user_to_dto(user)

    def find_by_name(self, full_name: str) -> UserDTO | None:
        user = self._session.exec(
            select(User).where(User.full_name == full_name)
        ).first()
        return None if user is None else _user_to_dto(user)

    def create_user(self, *, full_name: str) -> UserDTO:
        user = User(full_name=full_name)
        self._session.add(user)
        self._session.flush()
        self._session.refresh(user)
        return _user_to_dto(user)

    def update_user(
        self,
        user_id: str,
        *,
        full_name: str | None,
        is_active: bool | None,
    ) -> UserDTO | None:
        user = self._get_model(user_id)
        if user is None:
            return None
        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        self._session.add(user)
        self._session.flush()
        self._session.refresh(user)
        return _user_to_dto(user)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


__all__ = ["SqlUserRepository"]
