"""Add llm_timeout_total to user_settings

Revision ID: 016_add_llm_timeout_total
Revises: 015_add_npc_tracking_snapshots
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '016_add_llm_timeout_total'
down_revision = '015_add_npc_tracking_snapshots'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_settings', sa.Column('llm_timeout_total', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('user_settings', 'llm_timeout_total')

