"""add current_position and items_in_hand to character_states

Revision ID: 058_add_position_tracking_fields
Revises: 057_main_llm_plot
Create Date: 2026-02-05
"""
from alembic import op
import sqlalchemy as sa


revision = '058_position_tracking'
down_revision = '057_main_llm_plot'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('character_states', sa.Column('current_position', sa.Text(), nullable=True))
    op.add_column('character_states', sa.Column('items_in_hand', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('character_states', 'items_in_hand')
    op.drop_column('character_states', 'current_position')
