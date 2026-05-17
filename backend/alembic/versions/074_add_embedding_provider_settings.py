"""Add embedding provider settings and embedding_text column

Revision ID: 074
Revises: 073
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '074_embedding_provider_settings'
down_revision = '073_extraction_provider_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add embedding provider columns to user_settings
    op.add_column('user_settings', sa.Column('embedding_provider', sa.String(100), nullable=True))
    op.add_column('user_settings', sa.Column('embedding_api_url', sa.String(500), nullable=True))
    op.add_column('user_settings', sa.Column('embedding_api_key', sa.String(500), nullable=True))
    op.add_column('user_settings', sa.Column('embedding_model_name', sa.String(200), nullable=True))
    op.add_column('user_settings', sa.Column('embedding_dimensions', sa.Integer(), nullable=True))
    op.add_column('user_settings', sa.Column('embedding_needs_reembed', sa.Boolean(), nullable=True, server_default='false'))

    # Add embedding_text to scene_embeddings (stores the text that was embedded)
    op.add_column('scene_embeddings', sa.Column('embedding_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('scene_embeddings', 'embedding_text')
    op.drop_column('user_settings', 'embedding_needs_reembed')
    op.drop_column('user_settings', 'embedding_dimensions')
    op.drop_column('user_settings', 'embedding_model_name')
    op.drop_column('user_settings', 'embedding_api_key')
    op.drop_column('user_settings', 'embedding_api_url')
    op.drop_column('user_settings', 'embedding_provider')
