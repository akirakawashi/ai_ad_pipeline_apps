"""add geozone description

Revision ID: a3d94f1c6b52
Revises: c7b2e91a4d38
Create Date: 2026-07-27 18:40:12.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3d94f1c6b52'
down_revision: Union[str, Sequence[str], None] = 'c7b2e91a4d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Пустая строка вместо NULL: текста может не быть, но «незаданного» поля у
    # участка не бывает. server_default заодно заполняет существующие строки.
    op.add_column(
        'route_geozones',
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('route_geozones', 'description')
