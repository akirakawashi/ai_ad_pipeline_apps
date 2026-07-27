"""seed_city

Симферополь и его четыре маршрута. Значения перенесены один в один из
удалённых frontend/src/data/cities.ts и data/routes.ts.

UUID заданы литералами, а не сгенерированы: id совпадут между dev/staging/prod,
поэтому данные можно копировать между окружениями и отлаживать по id.

Пути к geojson — относительно apps/frontend/public/, без ведущего слэша;
слэш добавляет фронтенд. Файлы остаются статикой, в БД лежит только путь.

Revision ID: b1f4c07a2e91
Revises: 0b5053bd16ee
Create Date: 2026-07-16 09:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'b1f4c07a2e91'
down_revision: Union[str, Sequence[str], None] = '0b5053bd16ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CITY_ID = '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a01'

ROUTES: list[dict[str, object]] = [
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a11',
        'slug': 'route-1',
        'name': 'Севастопольская | пр. Победы',
        'color_label': 'Красная линия',
        'color_hex': '#ff3b3f',
        'geojson_path': 'routes/simferopol/route_1.geojson',
        'display_order': 1,
    },
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a12',
        'slug': 'route-2',
        'name': 'Московская | Киевская',
        'color_label': 'Синяя линия',
        'color_hex': '#3b8cff',
        'geojson_path': 'routes/simferopol/route_2.geojson',
        'display_order': 2,
    },
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a13',
        'slug': 'route-3',
        'name': 'Объездная дорога',
        'color_label': 'Зелёная линия',
        'color_hex': '#32c26b',
        'geojson_path': 'routes/simferopol/route_3.geojson',
        'display_order': 3,
    },
    {
        'routes_id': '0f8f9b1e-3a4d-4c7a-9f21-6b0d5e8c1a14',
        'slug': 'route-4',
        'name': 'Евпаторийское шоссе',
        'color_label': 'Жёлтая линия',
        'color_hex': '#f3c944',
        'geojson_path': 'routes/simferopol/route_4.geojson',
        'display_order': 4,
    },
]


def upgrade() -> None:
    cities = sa.table(
        'cities',
        sa.column('cities_id', sa.String),
        sa.column('slug', sa.String),
        sa.column('name', sa.String),
        sa.column('region', sa.String),
        sa.column('roads_geojson_path', sa.String),
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
        sa.column('geojson_path', sa.String),
        sa.column('display_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )

    op.bulk_insert(
        cities,
        [
            {
                'cities_id': CITY_ID,
                'slug': 'simferopol',
                'name': 'Симферополь',
                'region': 'Республика Крым',
                'roads_geojson_path': 'routes/simferopol/export.geojson',
                'display_order': 1,
                'is_active': True,
            }
        ],
    )
    op.bulk_insert(
        routes,
        [{**route, 'cities_id': CITY_ID, 'is_active': True} for route in ROUTES],
    )


def downgrade() -> None:
    # Порядок важен: маршруты ссылаются на город.
    op.execute(
        sa.text('DELETE FROM routes WHERE cities_id = :city').bindparams(city=CITY_ID)
    )
    op.execute(
        sa.text('DELETE FROM cities WHERE cities_id = :city').bindparams(city=CITY_ID)
    )
