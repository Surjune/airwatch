"""add satellite observations

Revision ID: 83d490cb50ea
Revises: 69ea060f709c
Create Date: 2026-09-13 14:10:35.170633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83d490cb50ea'
down_revision: Union[str, Sequence[str], None] = '69ea060f709c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store daily Sentinel-5P column means per coarse H3 cell."""
    op.create_table('satellite_observations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('h3_cell', sa.String(length=15), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=False),
    sa.Column('product', sa.Enum('no2', 'so2', 'co', 'aerosol_index', name='satellite_product'), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('unit', sa.String(length=16), nullable=False),
    sa.Column('pixel_count', sa.Integer(), nullable=False),
    sa.CheckConstraint('pixel_count > 0', name='ck_satellite_pixels_positive'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('h3_cell', 'observed_on', 'product', name='uq_satellite_cell_day_product')
    )
    op.create_index('ix_satellite_product_day', 'satellite_observations', ['product', 'observed_on'], unique=False)


def downgrade() -> None:
    """Drop the table and the enum type it created."""
    op.drop_index('ix_satellite_product_day', table_name='satellite_observations')
    op.drop_table('satellite_observations')
    op.execute("DROP TYPE IF EXISTS satellite_product")
