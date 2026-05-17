"""Add scene_batch_size to user_settings for cache optimization

Revision ID: 017_add_scene_batch_size
Revises: 016_add_llm_timeout_total
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017_add_scene_batch_size'
down_revision = '016_add_llm_timeout_total'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_settings', sa.Column('scene_batch_size', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('user_settings', 'scene_batch_size')

