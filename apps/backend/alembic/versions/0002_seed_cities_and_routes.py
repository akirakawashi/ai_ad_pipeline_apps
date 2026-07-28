"""Справочные данные: два города и семь маршрутов вместе с их геометрией.

Отдельно от схемы намеренно: схему заменяет следующая миграция, а эти строки
однажды заменит админка городов и маршрутов — она уже есть на `/admin`. Пока
города и маршруты курируются, а не заводятся пользователями, они приходят сюда.

UUID заданы литералами, а не генерируются: идентификаторы совпадают между
окружениями, поэтому данные можно переносить и отлаживать по id. На эти же
сиды опираются тесты — они создают задания и съёмки на `simferopol/route-1`
и не заводят города сами.

**Геометрия входит в сид, и это главное в этой миграции.** Раньше линии и
дорожные слои лежали файлами внутри фронтенда, а в базу их переносили руками
разовым скриптом. Один раз этого не сделали — и карта осталась пустой, хотя
города, маршруты и вся навигация выглядели рабочими: справочник был засеян
наполовину. Теперь пустая база после `alembic upgrade head` сразу рисует карту,
и забыть шаг больше нельзя, потому что шага нет.

Файлы лежат рядом, в `alembic/seed_data/geometry/`, и являются частью миграции —
удалять их нельзя, иначе пересоздание базы с нуля перестанет работать. Поэтому
при отсутствии файла миграция падает громко, а не сеет NULL молча: тихо
недосеянный справочник — ровно то, что здесь и чинится.

Рамка города считается **из того же файла**, а не проставляется числами: иначе
она разъедется с дорожным слоем при его замене. Ту же рамку пересчитывает
заливка слоя через админку, её читает парсер каталога, чтобы отбрасывать точки
чужого города.

Revision ID: 0002_seed
Revises: 0001_schema
Create Date: 2026-07-28
"""

import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0002_seed'
down_revision: Union[str, Sequence[str], None] = '0001_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SIMFEROPOL_ID = '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a01'
SEVASTOPOL_ID = '10cc5690-7e52-4559-bfb4-f3e465894a6b'

CITIES: list[dict[str, object]] = [
    {
        'cities_id': SIMFEROPOL_ID,
        'slug': 'simferopol',
        'name': 'Симферополь',
        'region': 'Республика Крым',
        'display_order': 1,
    },
    {
        'cities_id': SEVASTOPOL_ID,
        'slug': 'sevastopol',
        'name': 'Севастополь',
        'region': 'Город федерального значения',
        'display_order': 2,
    },
]

# Маршруты Симферополя — по названиям улиц, вдоль которых идёт проезд.
# Маршруты Севастополя — реальные пути дорожного графа длиной 21–40 км,
# названы по двум самым протяжённым улицам маршрута.
ROUTES: list[dict[str, object]] = [
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a11',
        'cities_id': SIMFEROPOL_ID,
        'slug': 'route-1',
        'name': 'Севастопольская | пр. Победы',
        'color_label': 'Красная линия',
        'color_hex': '#ff3b3f',
        'display_order': 1,
    },
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a12',
        'cities_id': SIMFEROPOL_ID,
        'slug': 'route-2',
        'name': 'Московская | Киевская',
        'color_label': 'Синяя линия',
        'color_hex': '#3b8cff',
        'display_order': 2,
    },
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a13',
        'cities_id': SIMFEROPOL_ID,
        'slug': 'route-3',
        'name': 'Объездная дорога',
        'color_label': 'Зелёная линия',
        'color_hex': '#32c26b',
        'display_order': 3,
    },
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a14',
        'cities_id': SIMFEROPOL_ID,
        'slug': 'route-4',
        'name': 'Евпаторийское шоссе',
        'color_label': 'Жёлтая линия',
        'color_hex': '#f3c944',
        'display_order': 4,
    },
    {
        'routes_id': '433a22d9-3bf8-4c58-a01a-3c0b64644b82',
        'cities_id': SEVASTOPOL_ID,
        'slug': 'route-1',
        'name': 'Камышовое шоссе | Лабораторное шоссе',
        'color_label': 'Красная линия',
        'color_hex': '#ff3b3f',
        'display_order': 1,
    },
    {
        'routes_id': 'b9bfc74c-7de5-49de-b276-acc9360d2138',
        'cities_id': SEVASTOPOL_ID,
        'slug': 'route-2',
        'name': 'Симферопольское шоссе | Чернореченская',
        'color_label': 'Синяя линия',
        'color_hex': '#3b8cff',
        'display_order': 2,
    },
    {
        'routes_id': 'bd05c3a9-7d4e-4058-8d13-3f0fac0dfe9f',
        'cities_id': SEVASTOPOL_ID,
        'slug': 'route-3',
        'name': 'Руднева | Второй обороны',
        'color_label': 'Зелёная линия',
        'color_hex': '#32c26b',
        'display_order': 3,
    },
]


GEOMETRY_DIR = Path(__file__).resolve().parents[1] / 'seed_data' / 'geometry'


def _geometry(city_slug: str, file_name: str) -> dict:
    """Файл сида → FeatureCollection. Нет файла — падаем с внятной причиной."""
    path = GEOMETRY_DIR / city_slug / file_name
    if not path.is_file():
        raise RuntimeError(
            f'Нет файла геометрии {path}. Это часть миграции, а не временные '
            f'данные: без него база с нуля поднимется с пустой картой.'
        )
    return json.loads(path.read_text(encoding='utf-8'))


def _walk(node: object, found: list[tuple[float, float]]) -> None:
    """Пары [долгота, широта] с любой глубины вложенности.

    Копия обхода из domain/geometry.py, а не импорт: миграция обязана считать
    так же и через год, когда домен уже поменяется.
    """
    if not isinstance(node, list):
        return
    if (
        len(node) >= 2
        and isinstance(node[0], (int, float))
        and not isinstance(node[0], bool)
        and isinstance(node[1], (int, float))
        and not isinstance(node[1], bool)
    ):
        found.append((float(node[0]), float(node[1])))
        return
    for item in node:
        _walk(item, found)


def _bounds(collection: dict) -> dict[str, float]:
    """Прямоугольник города по его дорожному слою — им каталог отсекает чужое."""
    points: list[tuple[float, float]] = []
    for feature in collection.get('features', []):
        if isinstance(feature, dict) and isinstance(feature.get('geometry'), dict):
            _walk(feature['geometry'].get('coordinates'), points)
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return {
        'bounds_min_latitude': min(latitudes),
        'bounds_max_latitude': max(latitudes),
        'bounds_min_longitude': min(longitudes),
        'bounds_max_longitude': max(longitudes),
    }


def upgrade() -> None:
    cities = sa.table(
        'cities',
        sa.column('cities_id', sa.String),
        sa.column('slug', sa.String),
        sa.column('name', sa.String),
        sa.column('region', sa.String),
        sa.column('roads_geometry', postgresql.JSONB),
        sa.column('bounds_min_latitude', sa.Float),
        sa.column('bounds_max_latitude', sa.Float),
        sa.column('bounds_min_longitude', sa.Float),
        sa.column('bounds_max_longitude', sa.Float),
        sa.column('display_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )
    routes = sa.table(
        'routes',
        sa.column('routes_id', sa.String),
        sa.column('cities_id', sa.String),
        sa.column('slug', sa.String),
        sa.column('name', sa.String),
        sa.column('color_label', sa.String),
        sa.column('color_hex', sa.String),
        sa.column('geometry', postgresql.JSONB),
        sa.column('display_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )

    city_rows = []
    for city in CITIES:
        roads = _geometry(str(city['slug']), 'export.geojson')
        city_rows.append(
            {**city, 'is_active': True, 'roads_geometry': roads, **_bounds(roads)}
        )

    city_slugs = {str(city['cities_id']): str(city['slug']) for city in CITIES}
    route_rows = []
    for route in ROUTES:
        # В базе слаг route-1, в файле route_1 — так их назвали при выгрузке.
        file_name = f"{str(route['slug']).replace('-', '_')}.geojson"
        route_rows.append(
            {
                **route,
                'is_active': True,
                'geometry': _geometry(city_slugs[str(route['cities_id'])], file_name),
            }
        )

    op.bulk_insert(cities, city_rows)
    op.bulk_insert(routes, route_rows)


def downgrade() -> None:
    # Порядок важен: маршруты ссылаются на город.
    city_ids = (SIMFEROPOL_ID, SEVASTOPOL_ID)
    op.execute(
        sa.text('DELETE FROM routes WHERE cities_id IN :cities').bindparams(
            sa.bindparam('cities', value=city_ids, expanding=True)
        )
    )
    op.execute(
        sa.text('DELETE FROM cities WHERE cities_id IN :cities').bindparams(
            sa.bindparam('cities', value=city_ids, expanding=True)
        )
    )
