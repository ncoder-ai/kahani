"""Add world_id to scene_embeddings and scene_events

Revision ID: 069_world_id_embeddings
Revises: 068_branch_snapshots
Create Date: 2026-02-15
"""
from alembic import op
import sqlalchemy as sa

revision = '069_world_id_embeddings'
down_revision = '068_branch_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    # Add world_id to scene_embeddings
    op.add_column('scene_embeddings', sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_scene_embeddings_world_id', 'scene_embeddings', ['world_id'])

    # Add world_id to scene_events
    op.add_column('scene_events', sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_scene_events_world_id', 'scene_events', ['world_id'])

    # Backfill world_id from stories table
    op.execute("""
        UPDATE scene_embeddings se
        SET world_id = s.world_id
        FROM stories s
        WHERE se.story_id = s.id AND s.world_id IS NOT NULL
    """)

    op.execute("""
        UPDATE scene_events sev
        SET world_id = s.world_id
        FROM stories s
        WHERE sev.story_id = s.id AND s.world_id IS NOT NULL
    """)


def downgrade():
    op.drop_index('ix_scene_events_world_id', table_name='scene_events')
    op.drop_column('scene_events', 'world_id')
    op.drop_index('ix_scene_embeddings_world_id', table_name='scene_embeddings')
    op.drop_column('scene_embeddings', 'world_id')
