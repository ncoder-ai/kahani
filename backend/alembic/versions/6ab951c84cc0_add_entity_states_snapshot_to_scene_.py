"""Add entity_states_snapshot to scene_variant

Revision ID: 6ab951c84cc0
Revises: 055_add_enable_streaming
Create Date: 2026-02-04 20:56:24.655690

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6ab951c84cc0'
down_revision = '055_add_enable_streaming'
branch_labels = None
depends_on = None


def upgrade():
    # Add entity_states_snapshot column to scene_variants table
    # Stores entity states text (~1-2KB) at generation time for cache consistency
    op.add_column('scene_variants', sa.Column('entity_states_snapshot', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('scene_variants', 'entity_states_snapshot')
