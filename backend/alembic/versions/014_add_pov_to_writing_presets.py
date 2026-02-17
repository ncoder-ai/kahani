"""Add pov to writing_style_presets

Revision ID: 014_add_pov_to_writing_presets
Revises: 013_add_entity_state_batches
Create Date: 2025-11-19 15:47:07.613487

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014_add_pov_to_writing_presets'
down_revision = '013_add_entity_state_batches'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('writing_style_presets', sa.Column('pov', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('writing_style_presets', 'pov')

