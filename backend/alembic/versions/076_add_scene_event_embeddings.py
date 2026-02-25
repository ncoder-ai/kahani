"""Add embedding column to scene_events

Revision ID: 076
Revises: 075
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers
revision = '076_scene_event_embeddings'
down_revision = '075_configured_providers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add embedding column (nullable — backfilled separately)
    op.add_column('scene_events', sa.Column('embedding', Vector(768), nullable=True))

    # HNSW index for cosine similarity search
    op.execute(
        "CREATE INDEX ix_scene_events_embedding_hnsw ON scene_events "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scene_events_embedding_hnsw")
    op.drop_column('scene_events', 'embedding')
