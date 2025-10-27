"""Add scene container style setting

Revision ID: 008
Revises: 007
Create Date: 2025-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_settings', sa.Column('scene_container_style', sa.String(20), default='lines'))
    op.execute("UPDATE user_settings SET scene_container_style = 'lines'")

def downgrade():
    op.drop_column('user_settings', 'scene_container_style')
