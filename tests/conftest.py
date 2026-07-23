"""Общие фикстуры: временная БД со схемой из миграций и клиент API.

Тестам нужен только поднятый postgres. Хранилище подменяется заглушкой:
зависеть от живого MinIO ради проверки бизнес-логики незачем.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# Всё до импорта приложения: настройки читаются из окружения, а session.py
# создаёт движок прямо на импорте модуля — подменить базу позже уже нельзя.
load_dotenv(ROOT / "apps" / "backend" / ".env")
TEST_DB = os.environ.get("POSTGRES_TEST_DB", "ad_pipeline_test")
ADMIN_DB = "postgres"
os.environ["POSTGRES_DB"] = TEST_DB

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, text  # noqa: E402

from infrastructure.database.session import engine  # noqa: E402
from main import app  # noqa: E402
from presentation.http.dependencies import get_object_storage  # noqa: E402

# Города и маршруты приходят из сид-миграций и переживают тесты: сущности
# курируемые, тесты их не создают. Всё остальное чистим между тестами.
MUTABLE_TABLES = (
    "pipeline_run_events",
    "pipeline_artifacts",
    "pipeline_runs",
    "assignments",
    "users",
)


class FakeObjectStorage:
    """Presigned-ссылки подписываются локально, но сеть не нужна и для stat."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def ensure_bucket(self) -> None:
        return None

    def presigned_put(self, object_key: str, **_: object) -> str:
        return f"https://storage.test/{object_key}?upload"

    def presigned_get(self, object_key: str, **_: object) -> str:
        return f"https://storage.test/{object_key}"

    def stat(self, object_key: str) -> SimpleNamespace:
        return SimpleNamespace(size=len(self.objects.get(object_key, b"x" * 1024)))

    def read_bytes(self, object_key: str) -> bytes:
        return self.objects.get(object_key, b"")

    def read_text(self, object_key: str) -> str:
        return self.read_bytes(object_key).decode("utf-8")


def _admin_dsn() -> str:
    """Подключение к служебной базе: из неё создаём и сносим тестовую.

    Собираем из окружения, а не из DatabaseSettings: там лежит только готовый
    URL с уже подставленной базой, а нам нужна другая.
    """
    user = quote_plus(os.environ["POSTGRES_USER"])
    password = quote_plus(os.environ["POSTGRES_PASSWORD"])
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{ADMIN_DB}"


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    """Создаёт базу под тесты, накатывает миграции, в конце сносит.

    Схема берётся из тех же миграций, что поедут в прод, — иначе тесты
    проверяли бы схему, которой не существует.
    """
    try:
        connection = psycopg.connect(_admin_dsn(), autocommit=True)
    except psycopg.OperationalError as error:
        pytest.exit(
            "Тестам нужен поднятый postgres: docker compose up -d postgres\n"
            f"Подключение не удалось: {error}",
            returncode=1,
        )
    with connection as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')

    config = Config(str(ROOT / "apps" / "backend" / "alembic.ini"))
    command.upgrade(config, "head")

    yield

    engine.dispose()
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')


@pytest.fixture(autouse=True)
def clean_tables(database: None) -> None:
    """Каждый тест начинает с пустых изменяемых таблиц, но с сидами каталога."""
    yield
    with Session(engine) as session:
        session.exec(text(f"TRUNCATE {', '.join(MUTABLE_TABLES)} CASCADE"))
        session.commit()


@pytest.fixture
def storage() -> FakeObjectStorage:
    return FakeObjectStorage()


@pytest.fixture
def client(storage: FakeObjectStorage) -> TestClient:
    """Клиент без запуска lifespan: подключение к MinIO тестам не нужно."""
    app.dependency_overrides[get_object_storage] = lambda: storage
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def city_route() -> tuple[str, str]:
    """Город и маршрут из сид-миграции — точка входа почти всех сценариев."""
    return "simferopol", "route-1"


def payload(response) -> object:
    """Разворачивает конверт {"data": ...} ответа API."""
    return response.json()["data"]
