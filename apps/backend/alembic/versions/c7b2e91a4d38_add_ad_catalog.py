"""add ad catalog: catalog_imports, ad_structures, city bounds

Каталог рекламных конструкций. Загружается паками файлов на город; каждый
применённый пак — ревизия, актуальная ровно одна. Прямоугольник города нужен,
чтобы отсекать точки, попавшие в файл по ошибке за десятки километров от
города; значения посчитаны по дорожным слоям в apps/frontend/public.

Revision ID: c7b2e91a4d38
Revises: 68f3d316db7e
Create Date: 2026-07-27 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c7b2e91a4d38'
down_revision: Union[str, Sequence[str], None] = '68f3d316db7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Границы по дорожным слоям городов: (slug, min_lat, max_lat, min_lon, max_lon).
CITY_BOUNDS: list[tuple[str, float, float, float, float]] = [
    ('sevastopol', 44.512165, 44.687838, 33.382234, 33.649528),
    ('simferopol', 44.903778, 44.996313, 34.018246, 34.190558),
]


def upgrade() -> None:
    op.add_column('cities', sa.Column('bounds_min_latitude', sa.Float(), nullable=True))
    op.add_column('cities', sa.Column('bounds_max_latitude', sa.Float(), nullable=True))
    op.add_column(
        'cities', sa.Column('bounds_min_longitude', sa.Float(), nullable=True)
    )
    op.add_column(
        'cities', sa.Column('bounds_max_longitude', sa.Float(), nullable=True)
    )

    connection = op.get_bind()
    for slug, min_lat, max_lat, min_lon, max_lon in CITY_BOUNDS:
        connection.execute(
            sa.text(
                'UPDATE cities SET bounds_min_latitude = :min_lat,'
                ' bounds_max_latitude = :max_lat,'
                ' bounds_min_longitude = :min_lon,'
                ' bounds_max_longitude = :max_lon'
                ' WHERE slug = :slug'
            ),
            {
                'slug': slug,
                'min_lat': min_lat,
                'max_lat': max_lat,
                'min_lon': min_lon,
                'max_lon': max_lon,
            },
        )

    op.create_table(
        'catalog_imports',
        sa.Column('catalog_imports_id', sa.String(length=36), nullable=False),
        sa.Column('cities_id', sa.String(length=36), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column(
            'file_names',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='[]',
            nullable=False,
        ),
        sa.Column('rows_read', sa.Integer(), nullable=False),
        sa.Column('rows_rejected', sa.Integer(), nullable=False),
        sa.Column('points_total', sa.Integer(), nullable=False),
        sa.Column('files_rejected', sa.Integer(), nullable=False),
        sa.Column('uploaded_by_users_id', sa.String(length=36), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['cities_id'], ['cities.cities_id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['uploaded_by_users_id'], ['users.users_id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('catalog_imports_id'),
        sa.UniqueConstraint(
            'cities_id', 'revision', name='uq_catalog_imports_city_revision'
        ),
    )
    op.create_index(
        op.f('ix_catalog_imports_cities_id'),
        'catalog_imports',
        ['cities_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_catalog_imports_status'), 'catalog_imports', ['status'], unique=False
    )
    op.create_index(
        op.f('ix_catalog_imports_uploaded_by_users_id'),
        'catalog_imports',
        ['uploaded_by_users_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_catalog_imports_created_at'),
        'catalog_imports',
        ['created_at'],
        unique=False,
    )
    op.create_index(
        'ix_catalog_imports_city_current',
        'catalog_imports',
        ['cities_id', 'is_current'],
        unique=False,
    )

    op.create_table(
        'ad_structures',
        sa.Column('ad_structures_id', sa.String(length=36), nullable=False),
        sa.Column('catalog_imports_id', sa.String(length=36), nullable=False),
        sa.Column('cities_id', sa.String(length=36), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('surfaces_count', sa.Integer(), nullable=False),
        sa.Column(
            'source_rows',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='[]',
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['catalog_imports_id'],
            ['catalog_imports.catalog_imports_id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['cities_id'], ['cities.cities_id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('ad_structures_id'),
    )
    op.create_index(
        op.f('ix_ad_structures_catalog_imports_id'),
        'ad_structures',
        ['catalog_imports_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_ad_structures_cities_id'),
        'ad_structures',
        ['cities_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ad_structures_cities_id'), table_name='ad_structures')
    op.drop_index(
        op.f('ix_ad_structures_catalog_imports_id'), table_name='ad_structures'
    )
    op.drop_table('ad_structures')

    op.drop_index('ix_catalog_imports_city_current', table_name='catalog_imports')
    op.drop_index(op.f('ix_catalog_imports_created_at'), table_name='catalog_imports')
    op.drop_index(
        op.f('ix_catalog_imports_uploaded_by_users_id'), table_name='catalog_imports'
    )
    op.drop_index(op.f('ix_catalog_imports_status'), table_name='catalog_imports')
    op.drop_index(op.f('ix_catalog_imports_cities_id'), table_name='catalog_imports')
    op.drop_table('catalog_imports')

    op.drop_column('cities', 'bounds_max_longitude')
    op.drop_column('cities', 'bounds_min_longitude')
    op.drop_column('cities', 'bounds_max_latitude')
    op.drop_column('cities', 'bounds_min_latitude')
