"""add use_main_llm_for_plot_extraction column

Revision ID: 057_add_use_main_llm_for_plot_extraction
Revises: 056_add_context_snapshot
Create Date: 2026-02-05
"""
from alembic import op
import sqlalchemy as sa


revision = '057_main_llm_plot'
down_revision = '056_add_context_snapshot'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_settings', sa.Column('use_main_llm_for_plot_extraction', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'use_main_llm_for_plot_extraction')
