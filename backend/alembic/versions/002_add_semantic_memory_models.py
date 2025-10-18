"""add semantic memory models

Revision ID: 002
Revises: 001
Create Date: 2025-10-18 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Create character_memories table
    op.create_table(
        'character_memories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('moment_type', sa.Enum('ACTION', 'DIALOGUE', 'DEVELOPMENT', 'RELATIONSHIP', name='momenttype'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.String(200), nullable=False),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=True),
        sa.Column('extracted_automatically', sa.Boolean(), nullable=True, default=True),
        sa.Column('confidence_score', sa.Integer(), nullable=True, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_character_memories_id', 'character_memories', ['id'])
    op.create_index('ix_character_memories_character_id', 'character_memories', ['character_id'])
    op.create_index('ix_character_memories_scene_id', 'character_memories', ['scene_id'])
    op.create_index('ix_character_memories_story_id', 'character_memories', ['story_id'])
    op.create_index('ix_character_memories_moment_type', 'character_memories', ['moment_type'])
    op.create_index('ix_character_memories_embedding_id', 'character_memories', ['embedding_id'], unique=True)
    op.create_index('ix_character_memories_sequence_order', 'character_memories', ['sequence_order'])
    
    # Create plot_events table
    op.create_table(
        'plot_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.Enum('INTRODUCTION', 'COMPLICATION', 'REVELATION', 'RESOLUTION', name='eventtype'), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.String(200), nullable=False),
        sa.Column('thread_id', sa.String(100), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=True, default=False),
        sa.Column('resolution_scene_id', sa.Integer(), nullable=True),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=True),
        sa.Column('involved_characters', sa.JSON(), nullable=True),
        sa.Column('extracted_automatically', sa.Boolean(), nullable=True, default=True),
        sa.Column('confidence_score', sa.Integer(), nullable=True, default=0),
        sa.Column('importance_score', sa.Integer(), nullable=True, default=50),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolution_scene_id'], ['scenes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_plot_events_id', 'plot_events', ['id'])
    op.create_index('ix_plot_events_story_id', 'plot_events', ['story_id'])
    op.create_index('ix_plot_events_scene_id', 'plot_events', ['scene_id'])
    op.create_index('ix_plot_events_event_type', 'plot_events', ['event_type'])
    op.create_index('ix_plot_events_embedding_id', 'plot_events', ['embedding_id'], unique=True)
    op.create_index('ix_plot_events_thread_id', 'plot_events', ['thread_id'])
    op.create_index('ix_plot_events_is_resolved', 'plot_events', ['is_resolved'])
    op.create_index('ix_plot_events_sequence_order', 'plot_events', ['sequence_order'])
    
    # Create scene_embeddings table
    op.create_table(
        'scene_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('embedding_id', sa.String(200), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=True),
        sa.Column('embedding_version', sa.String(20), nullable=True, default='v1'),
        sa.Column('content_length', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['scene_variants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_scene_embeddings_id', 'scene_embeddings', ['id'])
    op.create_index('ix_scene_embeddings_story_id', 'scene_embeddings', ['story_id'])
    op.create_index('ix_scene_embeddings_scene_id', 'scene_embeddings', ['scene_id'])
    op.create_index('ix_scene_embeddings_variant_id', 'scene_embeddings', ['variant_id'])
    op.create_index('ix_scene_embeddings_embedding_id', 'scene_embeddings', ['embedding_id'], unique=True)
    op.create_index('ix_scene_embeddings_sequence_order', 'scene_embeddings', ['sequence_order'])


def downgrade():
    # Drop scene_embeddings table
    op.drop_index('ix_scene_embeddings_sequence_order', 'scene_embeddings')
    op.drop_index('ix_scene_embeddings_embedding_id', 'scene_embeddings')
    op.drop_index('ix_scene_embeddings_variant_id', 'scene_embeddings')
    op.drop_index('ix_scene_embeddings_scene_id', 'scene_embeddings')
    op.drop_index('ix_scene_embeddings_story_id', 'scene_embeddings')
    op.drop_index('ix_scene_embeddings_id', 'scene_embeddings')
    op.drop_table('scene_embeddings')
    
    # Drop plot_events table
    op.drop_index('ix_plot_events_sequence_order', 'plot_events')
    op.drop_index('ix_plot_events_is_resolved', 'plot_events')
    op.drop_index('ix_plot_events_thread_id', 'plot_events')
    op.drop_index('ix_plot_events_embedding_id', 'plot_events')
    op.drop_index('ix_plot_events_event_type', 'plot_events')
    op.drop_index('ix_plot_events_scene_id', 'plot_events')
    op.drop_index('ix_plot_events_story_id', 'plot_events')
    op.drop_index('ix_plot_events_id', 'plot_events')
    op.drop_table('plot_events')
    
    # Drop character_memories table
    op.drop_index('ix_character_memories_sequence_order', 'character_memories')
    op.drop_index('ix_character_memories_embedding_id', 'character_memories')
    op.drop_index('ix_character_memories_moment_type', 'character_memories')
    op.drop_index('ix_character_memories_story_id', 'character_memories')
    op.drop_index('ix_character_memories_scene_id', 'character_memories')
    op.drop_index('ix_character_memories_character_id', 'character_memories')
    op.drop_index('ix_character_memories_id', 'character_memories')
    op.drop_table('character_memories')
    
    # Drop enums
    sa.Enum(name='momenttype').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='eventtype').drop(op.get_bind(), checkfirst=False)

