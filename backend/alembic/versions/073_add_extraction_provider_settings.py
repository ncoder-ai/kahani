"""Add extraction model provider settings columns

Revision ID: 073
Revises: 072
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '073_extraction_provider_settings'
down_revision = '072_add_roleplay_support'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_settings', sa.Column('extraction_model_api_type', sa.String(100), nullable=True))
    op.add_column('user_settings', sa.Column('extraction_engine_settings', sa.Text(), nullable=True))
    op.add_column('user_settings', sa.Column('current_extraction_engine', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'current_extraction_engine')
    op.drop_column('user_settings', 'extraction_engine_settings')
    op.drop_column('user_settings', 'extraction_model_api_type')
