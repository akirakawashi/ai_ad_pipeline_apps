from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, create_engine

from settings.factory import get_settings


config = get_settings()

engine = create_engine(
    config.database.url,
    pool_pre_ping=True,
)


def create_session() -> Session:
    return Session(
        engine,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db_session() -> Generator[Session, None, None]:
    with create_session() as session:
        yield session
