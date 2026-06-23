from __future__ import annotations

from functools import lru_cache

from settings.app import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Backward compatibility for Alembic configuration maintained separately.
ConfigFactory = Settings
