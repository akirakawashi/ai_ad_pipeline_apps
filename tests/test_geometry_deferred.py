"""Дорожный слой города не уезжает в запросы, которым он не нужен.

Правило записано в AGENTS.md §10 и до сих пор держалось на дисциплине: `defer`
руками в каждом запросе, который грузит `City`. Дисциплина один раз не
сработала — репозиторий каталога выпал из правила целиком, и `GET /ad-structures`
поднимал 755 КБ JSONB, чтобы взять из города один идентификатор. Снаружи это не
ломается никак, просто тихо становится медленнее, поэтому заметить это можно
было только чтением кода.

Тест переводит правило из соглашения в проверку: слушает SQL, реально ушедший в
Postgres, и требует, чтобы имени колонки в нём не было. Контрольный случай
(эндпоинт геометрии) обязан её грузить — тест, который зелёный всегда, не стоит
ничего.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event

from conftest import payload
from infrastructure.database.session import engine
from test_ad_catalog import LENINA_ROWS, build_xlsx, header_and

CITY = "sevastopol"

# Эндпоинты, которым дорожный слой не нужен ни при каких условиях: список и
# карточка города отдают только признак `has_roads_geometry`, каталогу от города
# нужен идентификатор, а разбору пака — ещё название и рамка.
GEOMETRY_FREE_READS = (
    "/api/v1/cities",
    f"/api/v1/cities/{CITY}",
    f"/api/v1/cities/{CITY}/ad-structures",
    f"/api/v1/cities/{CITY}/catalog/imports",
)


@contextmanager
def captured_sql():
    """SQL, реально ушедший в базу за время блока.

    Слушаем движок, а не сессию: запросы уходят из пула потоков FastAPI, и
    привязка к конкретной сессии их бы не поймала.
    """
    statements: list[str] = []

    def listener(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", listener)


# Проверка на NULL — законное упоминание колонки: так считается признак
# `has_roads_geometry`, и наружу из базы едет булево, а не сам слой. Отличить
# «сослались на колонку» от «загрузили колонку» по одной подстроке нельзя,
# поэтому проверки на NULL вырезаем до сравнения.
NULL_TEST = re.compile(r"\S*roads_geometry\s+IS\s+(?:NOT\s+)?NULL", re.IGNORECASE)


def geometry_loads(statements: list[str]) -> list[str]:
    return [item for item in statements if "roads_geometry" in NULL_TEST.sub("", item)]


# Те же строки, что и в наборе про каталог, но с расширенным типом: список
# инвариантен, и `list[tuple[str, str, str]]` не подходит там, где ждут
# `list[tuple[str, ...]]`.
PACK_ROWS: list[tuple[str, ...]] = list(LENINA_ROWS)


def make_uploader(client) -> str:
    created: Any = payload(
        client.post("/api/v1/users", json={"full_name": "Сторожева И."})
    )
    return created["id"]


def upload_pack(client, uploader_id: str):
    return client.post(
        f"/api/v1/cities/{CITY}/catalog/imports",
        files=[
            (
                "files",
                (
                    "pack.xlsx",
                    build_xlsx(header_and(PACK_ROWS)),
                    "application/vnd.ms-excel",
                ),
            )
        ],
        data={"uploaded_by_user_id": uploader_id},
    )


@pytest.mark.parametrize("path", GEOMETRY_FREE_READS)
def test_reads_do_not_load_roads_geometry(client, path: str) -> None:
    with captured_sql() as statements:
        response = client.get(path)

    assert response.status_code == 200
    assert geometry_loads(statements) == [], (
        f"{path} поднимает дорожный слой города — нужен defer(City.roads_geometry)"
    )


def test_catalog_upload_does_not_load_roads_geometry(client) -> None:
    """Разбору пака нужны название города и рамка, но не сам дорожный слой."""
    uploader_id = make_uploader(client)

    with captured_sql() as statements:
        response = upload_pack(client, uploader_id)

    assert response.status_code == 201
    assert geometry_loads(statements) == []


def test_revision_switch_does_not_load_roads_geometry(client) -> None:
    """Переключение ревизии блокирует строку города — и больше ничего от неё.

    Здесь defer важнее, чем на чтении: без него слой едет по сети внутри уже
    взятой блокировки и растягивает критическую секцию.
    """
    uploader_id = make_uploader(client)
    report: Any = payload(upload_pack(client, uploader_id))
    import_id = report["catalog_import"]["id"]

    with captured_sql() as statements:
        applied = client.post(f"/api/v1/catalog/imports/{import_id}/apply")
        hidden = client.post(f"/api/v1/catalog/imports/{import_id}/hide")
        restored = client.post(f"/api/v1/catalog/imports/{import_id}/restore")

    assert (applied.status_code, hidden.status_code, restored.status_code) == (
        200,
        200,
        200,
    )
    assert geometry_loads(statements) == []


def test_geometry_endpoint_still_loads_it(client) -> None:
    """Контрольный случай: тест обязан отличать «не грузим» от «не смотрим».

    Без него любая опечатка в имени колонки превратила бы весь файл в набор
    вечнозелёных проверок.
    """
    with captured_sql() as statements:
        response = client.get(f"/api/v1/cities/{CITY}/roads-geometry")

    assert response.status_code == 200
    assert geometry_loads(statements), (
        "эндпоинт геометрии обязан грузить дорожный слой — иначе проверки выше"
        " ничего не доказывают"
    )
