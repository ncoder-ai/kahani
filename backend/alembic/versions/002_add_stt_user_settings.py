"""add_stt_user_settings

Revision ID: 002_add_stt_user_settings
Revises: 001_initial_schema
Create Date: 2025-10-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Add STT settings columns to user_settings table
    op.add_column('user_settings', sa.Column('stt_enabled', sa.Boolean(), nullable=True, server_default='1'))
    op.add_column('user_settings', sa.Column('stt_model', sa.String(length=20), nullable=True, server_default='small'))


def downgrade():
    # Remove STT settings columns
    op.drop_column('user_settings', 'stt_model')
    op.drop_column('user_settings', 'stt_enabled')

