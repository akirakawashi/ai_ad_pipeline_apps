"""Общие фикстуры: временная БД со схемой из миграций и клиент API.

Тестам нужен только поднятый postgres. Хранилище подменяется заглушкой:
зависеть от живого MinIO ради проверки бизнес-логики незачем.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# Всё до импорта приложения: настройки читаются из окружения, а session.py
# создаёт движок прямо на импорте модуля — подменить базу позже уже нельзя.
load_dotenv(ROOT / ".env")
TEST_DB = os.environ.get("POSTGRES_TEST_DB", "ad_pipeline_test")
ADMIN_DB = "postgres"
os.environ["POSTGRES_DB"] = TEST_DB

# Группа, дающая права админа. Фиксируем здесь, а не берём из .env: иначе смена
# состава групп у владельца молча роняла бы половину набора. Настройки кэшируются
# на первом обращении, поэтому переменные ставим до импорта приложения.
ADMIN_GROUP = "/AI-AD-Admins"
os.environ["AUTH_ADMIN_GROUPS"] = ADMIN_GROUP
# Настоящего Keycloak в тестах нет и быть не может — он только продовый.
# Личность подменяется на границе `current_user`, но приложение должно
# импортироваться, а с AUTH_USE_KEYCLOAK=true это требовало бы реквизитов.
os.environ["AUTH_USE_KEYCLOAK"] = "false"
PROCESSING_TOKEN = "test-processing-token"
os.environ["PROCESSING_SERVICE_TOKEN"] = PROCESSING_TOKEN

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from sqlmodel import Session, text  # noqa: E402

from application.common.dto import AuthenticatedUserDTO  # noqa: E402
from domain.auth import Permission  # noqa: E402
from infrastructure.database.session import engine  # noqa: E402
from main import app  # noqa: E402
from presentation.http.auth import current_user, optional_user  # noqa: E402
from presentation.http.dependencies import get_object_storage  # noqa: E402

# Города и маршруты приходят из сид-миграций и переживают тесты: сущности
# курируемые, тесты их не создают. Всё остальное чистим между тестами.
MUTABLE_TABLES = (
    "pipeline_run_events",
    "pipeline_artifacts",
    "dwh_video_metrics",
    "pipeline_runs",
    "route_geozones",
    "ad_structures",
    "catalog_imports",
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
def database() -> Iterator[None]:
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

    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    yield

    engine.dispose()
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')


@pytest.fixture(autouse=True)
def clean_tables(database: None) -> Iterator[None]:
    """Каждый тест начинает с пустых изменяемых таблиц, но с сидами каталога."""
    yield
    with Session(engine) as session:
        # route_geozones появляется только после миграции под новую модель;
        # до неё её нет в схеме — чистим лишь реально существующие таблицы.
        existing = set(inspect(engine).get_table_names())
        tables = [name for name in MUTABLE_TABLES if name in existing]
        if tables:
            # execute, а не exec: exec у SQLModel — типизированная обёртка под
            # select, сырой SQL по её сигнатуре не проходит.
            session.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
            session.commit()


@pytest.fixture
def geozone_schema() -> None:
    """Пропускает тест, если миграция route_geozones ещё не накатана.

    Схему тестовой БД строят те же миграции, что поедут в прод. Таблица
    появится, когда владелец сгенерирует и применит миграцию под новую модель;
    до тех пор геозонные интеграционные тесты пропускаются, а не краснеют.
    """
    if not inspect(engine).has_table("route_geozones"):
        pytest.skip("Нет таблицы route_geozones — примените миграцию.")


@pytest.fixture
def storage() -> FakeObjectStorage:
    return FakeObjectStorage()


def admin_user() -> AuthenticatedUserDTO:
    """Вошедший админ, каким его собрал бы вход из групп токена."""
    return AuthenticatedUserDTO(
        id="00000000-0000-0000-0000-0000000000ad",
        full_name="Тестовый Админ",
        username="test.admin",
        email="test.admin@example.test",
        permissions=[str(Permission.ADMIN)],
    )


def plain_user() -> AuthenticatedUserDTO:
    """Вошедший сотрудник без прав администратора."""
    return AuthenticatedUserDTO(
        id="00000000-0000-0000-0000-0000000000aa",
        full_name="Тестовый Сотрудник",
        username="test.user",
        email="test.user@example.test",
        permissions=[],
    )


@pytest.fixture
def client(storage: FakeObjectStorage) -> Iterator[TestClient]:
    """Клиент без запуска lifespan: подключение к MinIO тестам не нужно.

    Ходит как вошедший админ. Личность подменяется на границе `current_user`, а
    не настоящей сессией: Keycloak в компании только продовый, и завести его для
    тестов негде. Что именно закрыто правами, проверяет `test_access_control.py`
    — остальным тестам интересна бизнес-логика.
    """
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[current_user] = admin_user
    app.dependency_overrides[optional_user] = admin_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def user_client(storage: FakeObjectStorage) -> Iterator[TestClient]:
    """Вошедший, но не админ — им проверяется 403 против 401."""
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[current_user] = plain_user
    app.dependency_overrides[optional_user] = plain_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(storage: FakeObjectStorage) -> Iterator[TestClient]:
    """Тот же клиент, но без сессии — им проверяется, что закрыто именно то."""
    app.dependency_overrides[get_object_storage] = lambda: storage
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def city_route() -> tuple[str, str]:
    """Город и маршрут из сид-миграции — точка входа почти всех сценариев."""
    return "simferopol", "route-1"


def payload(response) -> Any:
    """Разворачивает конверт {"data": ...} ответа API.

    `Any`, а не `object`: внутри — JSON произвольной формы, и тесты сразу лезут
    в него по ключу. С `object` каждое `payload(...)["id"]` становится ошибкой
    типов, хотя проверять там нечего — форму ответа держат DTO на бэкенде.
    """
    return response.json()["data"]
