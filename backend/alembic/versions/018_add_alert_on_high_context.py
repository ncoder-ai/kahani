"""Add alert_on_high_context to user_settings for context warning control

Revision ID: 018_add_alert_on_high_context
Revises: 017_add_scene_batch_size
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '018_add_alert_on_high_context'
down_revision = '017_add_scene_batch_size'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_settings', sa.Column('alert_on_high_context', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('user_settings', 'alert_on_high_context')


