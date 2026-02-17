"""add extraction model settings

Revision ID: 007
Revises: 006
Create Date: 2025-01-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add extraction model settings fields"""
    
    # Add extraction model settings to user_settings table
    op.add_column('user_settings', sa.Column('extraction_model_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('user_settings', sa.Column('extraction_model_url', sa.String(500), nullable=True, server_default='http://localhost:1234/v1'))
    op.add_column('user_settings', sa.Column('extraction_model_api_key', sa.String(500), nullable=True, server_default=''))
    op.add_column('user_settings', sa.Column('extraction_model_name', sa.String(200), nullable=True, server_default='qwen2.5-3b-instruct'))
    op.add_column('user_settings', sa.Column('extraction_model_temperature', sa.Float(), nullable=True, server_default='0.3'))
    op.add_column('user_settings', sa.Column('extraction_model_max_tokens', sa.Integer(), nullable=True, server_default='1000'))
    op.add_column('user_settings', sa.Column('extraction_fallback_to_main', sa.Boolean(), nullable=True, server_default='1'))


def downgrade() -> None:
    """Remove extraction model settings fields"""
    
    # Remove extraction model settings from user_settings
    op.drop_column('user_settings', 'extraction_fallback_to_main')
    op.drop_column('user_settings', 'extraction_model_max_tokens')
    op.drop_column('user_settings', 'extraction_model_temperature')
    op.drop_column('user_settings', 'extraction_model_name')
    op.drop_column('user_settings', 'extraction_model_api_key')
    op.drop_column('user_settings', 'extraction_model_url')
    op.drop_column('user_settings', 'extraction_model_enabled')









