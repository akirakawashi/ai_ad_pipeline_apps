"""seed_city_sevastopol

Севастополь без маршрутов — маршруты добавятся отдельной миграцией, когда
появятся геоданные по ним. Формат идентичен b1f4c07a2e91_seed_city.py.

Путь к geojson — относительно apps/frontend/public/, без ведущего слэша;
слэш добавляет фронтенд. Файл уже лежит в public/routes/sevastopol/export.geojson.

Revision ID: 027f1cf6ca20
Revises: b1f4c07a2e91
Create Date: 2026-07-16 18:14:09.224210
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '027f1cf6ca20'
down_revision: Union[str, Sequence[str], None] = 'b1f4c07a2e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CITY_ID = '10cc5690-7e52-4559-bfb4-f3e465894a6b'


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

    op.bulk_insert(
        cities,
        [
            {
                'cities_id': CITY_ID,
                'slug': 'sevastopol',
                'name': 'Севастополь',
                'region': 'Город федерального значения',
                'roads_geojson_path': 'routes/sevastopol/export.geojson',
                'display_order': 2,
                'is_active': True,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text('DELETE FROM cities WHERE cities_id = :city').bindparams(city=CITY_ID)
    )
