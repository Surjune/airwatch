"""add citizen reports

Revision ID: 601e9ab6385e
Revises: ee1245ae70d1
Create Date: 2026-09-12 21:45:25.497667

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '601e9ab6385e'
down_revision: Union[str, Sequence[str], None] = 'ee1245ae70d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the citizen-report table.

    No derived concentration is stored, only the haze index the photograph
    yielded and the nearby reference reading it can be paired with. The
    conversion between them is a fitted relation that changes when it is
    rebuilt, so persisting a concentration would freeze one version of the fit
    into the record and make a published figure impossible to reproduce.
    """
    op.create_table('citizen_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('h3_cell', sa.String(length=15), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('device_id', sa.String(length=128), nullable=False),
    sa.Column('haze_index', sa.Float(), nullable=False),
    sa.Column('transmission', sa.Float(), nullable=False),
    sa.Column('mean_luminance', sa.Float(), nullable=False),
    sa.Column('sharpness', sa.Float(), nullable=False),
    sa.Column('reference_station_id', sa.Integer(), nullable=True),
    sa.Column('reference_value', sa.Float(), nullable=True),
    sa.Column('reference_distance_m', sa.Float(), nullable=True),
    sa.Column('trust_score', sa.Float(), nullable=False),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint('haze_index >= 0 AND haze_index <= 1', name='ck_citizen_haze_range'),
    sa.CheckConstraint('trust_score >= 0 AND trust_score <= 1', name='ck_citizen_trust_range'),
    sa.ForeignKeyConstraint(['reference_station_id'], ['stations.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_citizen_reports_captured', 'citizen_reports', ['captured_at'], unique=False)
    op.create_index(op.f('ix_citizen_reports_device_id'), 'citizen_reports', ['device_id'], unique=False)
    op.create_index('ix_citizen_reports_geom', 'citizen_reports', ['geom'], unique=False, postgresql_using='gist')
    op.create_index(op.f('ix_citizen_reports_h3_cell'), 'citizen_reports', ['h3_cell'], unique=False)


def downgrade() -> None:
    """Drop the citizen-report table."""
    op.drop_index(op.f('ix_citizen_reports_h3_cell'), table_name='citizen_reports')
    op.drop_index('ix_citizen_reports_geom', table_name='citizen_reports', postgresql_using='gist')
    op.drop_index(op.f('ix_citizen_reports_device_id'), table_name='citizen_reports')
    op.drop_index('ix_citizen_reports_captured', table_name='citizen_reports')
    op.drop_table('citizen_reports')
