"""add last_chronicle_scene_count to chapters

Revision ID: 066_chronicle_tracking
Revises: 065_world_chronicle
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

revision = '066_chronicle_tracking'
down_revision = '065_world_chronicle'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chapters', sa.Column(
        'last_chronicle_scene_count', sa.Integer(), server_default='0', nullable=True
    ))


def downgrade():
    op.drop_column('chapters', 'last_chronicle_scene_count')
