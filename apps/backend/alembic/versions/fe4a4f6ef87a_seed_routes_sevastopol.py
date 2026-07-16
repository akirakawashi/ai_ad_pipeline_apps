"""seed_routes_sevastopol

Три маршрута для Севастополя — для наглядности, что город не единственный
в каталоге. Пути реального дорожного графа (кратчайший путь между случайной
парой точек, взвешенный по расстоянию), длина — от 21 до 40 км, чем длиннее,
тем заметнее на карте. Имена — по двум самым протяжённым улицам маршрута.

Формат идентичен b1f4c07a2e91_seed_city.py.

Revision ID: fe4a4f6ef87a
Revises: 027f1cf6ca20
Create Date: 2026-07-16 18:48:54.231520
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fe4a4f6ef87a'
down_revision: Union[str, Sequence[str], None] = '027f1cf6ca20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CITY_ID = '10cc5690-7e52-4559-bfb4-f3e465894a6b'

ROUTES: list[dict[str, object]] = [
    {
        'routes_id': '433a22d9-3bf8-4c58-a01a-3c0b64644b82',
        'slug': 'route-1',
        'name': 'Камышовое шоссе | Лабораторное шоссе',
        'color_label': 'Красная линия',
        'color_hex': '#ff3b3f',
        'geojson_path': 'routes/sevastopol/route_1.geojson',
        'display_order': 1,
    },
    {
        'routes_id': 'b9bfc74c-7de5-49de-b276-acc9360d2138',
        'slug': 'route-2',
        'name': 'Симферопольское шоссе | Чернореченская',
        'color_label': 'Синяя линия',
        'color_hex': '#3b8cff',
        'geojson_path': 'routes/sevastopol/route_2.geojson',
        'display_order': 2,
    },
    {
        'routes_id': 'bd05c3a9-7d4e-4058-8d13-3f0fac0dfe9f',
        'slug': 'route-3',
        'name': 'Руднева | Второй обороны',
        'color_label': 'Зелёная линия',
        'color_hex': '#32c26b',
        'geojson_path': 'routes/sevastopol/route_3.geojson',
        'display_order': 3,
    },
]


def upgrade() -> None:
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
        routes,
        [{**route, 'cities_id': CITY_ID, 'is_active': True} for route in ROUTES],
    )


def downgrade() -> None:
    op.execute(
        sa.text('DELETE FROM routes WHERE cities_id = :city').bindparams(city=CITY_ID)
    )
