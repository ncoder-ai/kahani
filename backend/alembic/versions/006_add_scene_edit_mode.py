"""add scene edit mode setting

Revision ID: 006
Revises: 005
Create Date: 2025-01-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add scene_edit_mode field to user_settings table"""
    
    # Add scene_edit_mode to user_settings table
    op.add_column('user_settings', sa.Column('scene_edit_mode', sa.String(20), nullable=True, server_default='textarea'))


def downgrade() -> None:
    """Remove scene_edit_mode field from user_settings table"""
    
    # Remove scene_edit_mode from user_settings
    op.drop_column('user_settings', 'scene_edit_mode')

