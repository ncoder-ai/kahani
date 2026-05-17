"""add pgvector extension and embedding vector columns

Revision ID: 064_pgvector
Revises: 063_thinking_toggles
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '064_pgvector'
down_revision = '063_thinking_toggles'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # 2. Add vector columns to existing tables (nullable — existing rows have NULL until backfill)
    op.add_column('scene_embeddings',
        sa.Column('embedding', Vector(768), nullable=True))
    op.add_column('character_memories',
        sa.Column('embedding', Vector(768), nullable=True))
    op.add_column('plot_events',
        sa.Column('embedding', Vector(768), nullable=True))

    # 3. Create HNSW indexes for cosine similarity search
    op.execute('''
        CREATE INDEX ix_scene_embeddings_embedding_hnsw
        ON scene_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')
    op.execute('''
        CREATE INDEX ix_character_memories_embedding_hnsw
        ON character_memories
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')
    op.execute('''
        CREATE INDEX ix_plot_events_embedding_hnsw
        ON plot_events
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')


def downgrade():
    op.drop_index('ix_plot_events_embedding_hnsw', table_name='plot_events')
    op.drop_index('ix_character_memories_embedding_hnsw', table_name='character_memories')
    op.drop_index('ix_scene_embeddings_embedding_hnsw', table_name='scene_embeddings')
    op.drop_column('plot_events', 'embedding')
    op.drop_column('character_memories', 'embedding')
    op.drop_column('scene_embeddings', 'embedding')
    op.execute('DROP EXTENSION IF EXISTS vector')
