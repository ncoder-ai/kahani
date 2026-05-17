"""add world, character_chronicles, and location_lorebooks tables

Revision ID: 065_world_chronicle
Revises: 064_pgvector
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '065_world_chronicle'
down_revision = '064_pgvector'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create worlds table
    op.create_table(
        'worlds',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('creator_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_worlds_id', 'worlds', ['id'])
    op.create_index('ix_worlds_creator_id', 'worlds', ['creator_id'])

    # 2. Create character_chronicles table
    op.create_table(
        'character_chronicles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id'), nullable=False),
        sa.Column('character_id', sa.Integer(), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('entry_type', sa.Enum(
            'personality_shift', 'knowledge_gained', 'secret', 'relationship_change',
            'trauma', 'physical_change', 'skill_gained', 'goal_change', 'other',
            name='chronicleentrytype'
        ), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('is_defining', sa.Boolean(), default=False),
        sa.Column('embedding_id', sa.String(200), nullable=True),
        sa.Column('embedding', Vector(768), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_character_chronicles_id', 'character_chronicles', ['id'])
    op.create_index('ix_character_chronicles_world_id', 'character_chronicles', ['world_id'])
    op.create_index('ix_character_chronicles_character_id', 'character_chronicles', ['character_id'])
    op.create_index('ix_character_chronicles_story_id', 'character_chronicles', ['story_id'])
    op.create_index('ix_character_chronicles_branch_id', 'character_chronicles', ['branch_id'])
    op.create_index('ix_character_chronicles_embedding_id', 'character_chronicles', ['embedding_id'])

    # HNSW index for chronicle embeddings
    op.execute('''
        CREATE INDEX ix_character_chronicles_embedding_hnsw
        ON character_chronicles
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')

    # 3. Create location_lorebooks table
    op.create_table(
        'location_lorebooks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id'), nullable=False),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('location_name', sa.String(200), nullable=False),
        sa.Column('event_description', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.String(200), nullable=True),
        sa.Column('embedding', Vector(768), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_location_lorebooks_id', 'location_lorebooks', ['id'])
    op.create_index('ix_location_lorebooks_world_id', 'location_lorebooks', ['world_id'])
    op.create_index('ix_location_lorebooks_story_id', 'location_lorebooks', ['story_id'])
    op.create_index('ix_location_lorebooks_branch_id', 'location_lorebooks', ['branch_id'])
    op.create_index('ix_location_lorebooks_location_name', 'location_lorebooks', ['location_name'])
    op.create_index('ix_location_lorebooks_embedding_id', 'location_lorebooks', ['embedding_id'])

    # HNSW index for lorebook embeddings
    op.execute('''
        CREATE INDEX ix_location_lorebooks_embedding_hnsw
        ON location_lorebooks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')

    # 4. Add world_id column to stories (nullable initially for backfill)
    op.add_column('stories', sa.Column('world_id', sa.Integer(),
                  sa.ForeignKey('worlds.id'), nullable=True))

    # 5. Backfill: create a default world for each existing story
    conn = op.get_bind()
    stories = conn.execute(
        sa.text("SELECT id, title, owner_id FROM stories WHERE world_id IS NULL")
    ).fetchall()

    for story in stories:
        result = conn.execute(
            sa.text(
                "INSERT INTO worlds (name, creator_id, created_at) "
                "VALUES (:name, :creator_id, NOW()) RETURNING id"
            ),
            {"name": f"{story.title} Universe", "creator_id": story.owner_id}
        )
        world_id = result.fetchone()[0]
        conn.execute(
            sa.text("UPDATE stories SET world_id = :world_id WHERE id = :story_id"),
            {"world_id": world_id, "story_id": story.id}
        )


def downgrade():
    op.drop_column('stories', 'world_id')

    op.drop_index('ix_location_lorebooks_embedding_hnsw', table_name='location_lorebooks')
    op.drop_index('ix_location_lorebooks_embedding_id', table_name='location_lorebooks')
    op.drop_index('ix_location_lorebooks_location_name', table_name='location_lorebooks')
    op.drop_index('ix_location_lorebooks_branch_id', table_name='location_lorebooks')
    op.drop_index('ix_location_lorebooks_story_id', table_name='location_lorebooks')
    op.drop_index('ix_location_lorebooks_world_id', table_name='location_lorebooks')
    op.drop_index('ix_location_lorebooks_id', table_name='location_lorebooks')
    op.drop_table('location_lorebooks')

    op.drop_index('ix_character_chronicles_embedding_hnsw', table_name='character_chronicles')
    op.drop_index('ix_character_chronicles_embedding_id', table_name='character_chronicles')
    op.drop_index('ix_character_chronicles_branch_id', table_name='character_chronicles')
    op.drop_index('ix_character_chronicles_story_id', table_name='character_chronicles')
    op.drop_index('ix_character_chronicles_character_id', table_name='character_chronicles')
    op.drop_index('ix_character_chronicles_world_id', table_name='character_chronicles')
    op.drop_index('ix_character_chronicles_id', table_name='character_chronicles')
    op.drop_table('character_chronicles')

    op.execute("DROP TYPE IF EXISTS chronicleentrytype")

    op.drop_index('ix_worlds_creator_id', table_name='worlds')
    op.drop_index('ix_worlds_id', table_name='worlds')
    op.drop_table('worlds')
