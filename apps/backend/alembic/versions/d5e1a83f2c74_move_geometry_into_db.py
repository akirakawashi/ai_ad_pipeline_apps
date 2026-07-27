"""move route and roads geometry into db

Revision ID: d5e1a83f2c74
Revises: a3d94f1c6b52
Create Date: 2026-07-27 21:05:33.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd5e1a83f2c74'
down_revision: Union[str, Sequence[str], None] = 'a3d94f1c6b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Геометрия переезжает из файлов внутри фронтенда в базу. Данные миграция не
    # переносит: alembic крутится в контейнере бэкенда, где папки
    # apps/frontend/public не существует. Заливка — разовым скриптом
    # scripts/import_geometry.py после накатывания схемы.
    op.add_column(
        'cities',
        sa.Column('roads_geometry', postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        'routes',
        sa.Column('geometry', postgresql.JSONB(), nullable=True),
    )
    op.drop_column('cities', 'roads_geojson_path')
    op.drop_column('routes', 'geojson_path')


def downgrade() -> None:
    # Пути назад не восстановить — они удалены вместе с колонками. Возвращаем
    # структуру, а не содержимое: маршрутам придётся прописать путь заново.
    op.add_column(
        'routes',
        sa.Column('geojson_path', sa.String(length=512), nullable=False, server_default=''),
    )
    op.add_column(
        'cities',
        sa.Column('roads_geojson_path', sa.String(length=512), nullable=True),
    )
    op.drop_column('routes', 'geometry')
    op.drop_column('cities', 'roads_geometry')
