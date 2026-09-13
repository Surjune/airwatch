"""add official sub indices

Revision ID: 03c435e12a17
Revises: 83d490cb50ea
Create Date: 2026-09-13 14:50:10.785994

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '03c435e12a17'
down_revision: Union[str, Sequence[str], None] = '83d490cb50ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store CPCB's published sub-indices apart from hourly measurements."""
    # The pollutant type already exists; creating it again would fail.
    pollutant = postgresql.ENUM(
        'pm25', 'pm10', 'no2', 'so2', 'o3', 'co', 'nh3', name='pollutant', create_type=False
    )
    op.create_table('official_sub_indices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('station_name', sa.String(length=256), nullable=False),
    sa.Column('city', sa.String(length=128), nullable=False),
    sa.Column('state', sa.String(length=128), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('pollutant', pollutant, nullable=False),
    sa.Column('reported_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sub_index', sa.Float(), nullable=False),
    sa.Column('sub_index_min', sa.Float(), nullable=True),
    sa.Column('sub_index_max', sa.Float(), nullable=True),
    sa.CheckConstraint('sub_index >= 0', name='ck_official_sub_index_non_negative'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('station_name', 'pollutant', 'reported_at', name='uq_official_station_pollutant_time')
    )
    op.create_index('ix_official_city_reported', 'official_sub_indices', ['city', 'reported_at'], unique=False)


def downgrade() -> None:
    """Drop the table. The pollutant type is shared, so it stays."""
    op.drop_index('ix_official_city_reported', table_name='official_sub_indices')
    op.drop_table('official_sub_indices')
