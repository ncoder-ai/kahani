"""add per-task thinking control settings

Revision ID: 063_thinking_toggles
Revises: 062_decomposition_llm
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = '063_thinking_toggles'
down_revision = '062_decomposition_llm'
branch_labels = None
depends_on = None


def upgrade():
    # Extraction model per-task thinking toggles
    op.add_column('user_settings', sa.Column('extraction_model_thinking_enabled_extractions', sa.Boolean(), nullable=True))
    op.add_column('user_settings', sa.Column('extraction_model_thinking_enabled_memory', sa.Boolean(), nullable=True))
    # Main LLM local thinking model settings
    op.add_column('user_settings', sa.Column('thinking_model_type', sa.String(50), nullable=True))
    op.add_column('user_settings', sa.Column('thinking_model_custom_pattern', sa.Text(), nullable=True))
    op.add_column('user_settings', sa.Column('thinking_enabled_generation', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'thinking_enabled_generation')
    op.drop_column('user_settings', 'thinking_model_custom_pattern')
    op.drop_column('user_settings', 'thinking_model_type')
    op.drop_column('user_settings', 'extraction_model_thinking_enabled_memory')
    op.drop_column('user_settings', 'extraction_model_thinking_enabled_extractions')
