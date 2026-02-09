"""Add context_snapshot to scene_variant

Revision ID: 056_add_context_snapshot
Revises: 6ab951c84cc0
Create Date: 2026-02-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '056_add_context_snapshot'
down_revision = '6ab951c84cc0'
branch_labels = None
depends_on = None


def upgrade():
    # Add context_snapshot column to scene_variants table
    # Stores full context JSON (entity_states_text, story_focus, relationship_context)
    # for complete cache consistency during variant regeneration
    op.add_column('scene_variants', sa.Column('context_snapshot', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('scene_variants', 'context_snapshot')
