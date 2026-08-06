from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, delete, select

from application.common.dto import AuthenticatedUserDTO
from infrastructure.database.models import User, UserSession


def _to_dto(user: User) -> AuthenticatedUserDTO:
    return AuthenticatedUserDTO(
        id=user.users_id,
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        permissions=list(user.permissions or []),
        is_active=user.is_active,
    )


class SqlAuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_by_subject(
        self,
        *,
        subject: str,
        username: str,
        full_name: str,
        email: str | None,
        groups: list[str],
        permissions: list[str],
    ) -> AuthenticatedUserDTO:
        """Запись справочника по `sub`: заводим при первом входе, обновляем при каждом.

        Имя, логин, почта и группы перезаписываются каждый раз намеренно: AD —
        источник правды по этим полям, и человек, сменивший фамилию, должен
        увидеть новую в тот же день, а не после обращения к администратору.

        `is_active` не трогаем. Это единственное поле, которое ставится здесь,
        руками, и означает ручной запрет работать — вход не повод его снимать.
        """
        user = self._session.exec(
            select(User).where(User.keycloak_subject == subject)
        ).first()
        if user is None:
            user = User(keycloak_subject=subject, full_name=full_name)
        user.full_name = full_name
        user.username = username
        user.email = email
        user.groups_raw = groups
        user.permissions = permissions
        user.last_login_at = datetime.now(tz=timezone.utc)
        self._session.add(user)
        self._session.flush()
        self._session.refresh(user)
        return _to_dto(user)

    def create_session(
        self,
        *,
        token_hash: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        self._session.add(
            UserSession(
                token_hash=token_hash,
                users_id=user_id,
                expires_at=expires_at,
            )
        )
        self._session.flush()

    def find_session_user(self, *, token_hash: str) -> AuthenticatedUserDTO | None:
        """Владелец живой сессии.

        Срок проверяется здесь, в запросе, а не после выборки: истёкшая сессия
        должна вести себя как отсутствующая, и решать это в двух местах — способ
        однажды забыть про одно из них.
        """
        row = self._session.exec(
            select(User)
            .join(UserSession, UserSession.users_id == User.users_id)  # type: ignore[arg-type]
            .where(UserSession.token_hash == token_hash)
            .where(UserSession.expires_at > datetime.now(tz=timezone.utc))
        ).first()
        return None if row is None else _to_dto(row)

    def delete_session(self, *, token_hash: str) -> None:
        self._session.exec(
            delete(UserSession).where(UserSession.token_hash == token_hash)  # type: ignore[arg-type]
        )
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


__all__ = ["SqlAuthRepository"]
