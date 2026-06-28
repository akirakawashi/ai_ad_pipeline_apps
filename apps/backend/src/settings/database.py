from __future__ import annotations

from urllib.parse import quote_plus

from settings.base import SettingsModel


class DatabaseSettings(SettingsModel):
    url: str


def build_database_settings(
    *,
    postgres_db: str,
    postgres_user: str,
    postgres_password: str,
    postgres_host: str,
    postgres_port: int,
) -> DatabaseSettings:
    user = quote_plus(postgres_user)
    password = quote_plus(postgres_password)
    database = quote_plus(postgres_db)
    return DatabaseSettings(
        url=(
            f"postgresql+psycopg://{user}:{password}"
            f"@{postgres_host}:{postgres_port}/{database}"
        )
    )
