"""add use_main_llm_for_decomposition setting

Revision ID: 062_decomposition_llm
Revises: 061_scene_events
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = '062_decomposition_llm'
down_revision = '061_scene_events'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_settings', sa.Column('use_main_llm_for_decomposition', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'use_main_llm_for_decomposition')
