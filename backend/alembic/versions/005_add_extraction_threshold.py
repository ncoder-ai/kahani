"""add extraction threshold tracking

Revision ID: 005
Revises: 004
Create Date: 2025-01-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add extraction threshold tracking fields"""
    
    # Add last_extraction_scene_count to chapters table
    op.add_column('chapters', sa.Column('last_extraction_scene_count', sa.Integer(), nullable=True, server_default='0'))
    
    # Add character_extraction_threshold to user_settings table
    op.add_column('user_settings', sa.Column('character_extraction_threshold', sa.Integer(), nullable=True, server_default='5'))


def downgrade() -> None:
    """Remove extraction threshold tracking fields"""
    
    # Remove last_extraction_scene_count from chapters
    op.drop_column('chapters', 'last_extraction_scene_count')
    
    # Remove character_extraction_threshold from user_settings
    op.drop_column('user_settings', 'character_extraction_threshold')

