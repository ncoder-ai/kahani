"""Add composite indexes for branch-filtered queries

Revision ID: 021_add_branch_indexes
Revises: 020_fix_npc_unique
Create Date: 2025-01-07

This migration adds composite indexes to optimize branch-filtered queries
and prevent performance degradation as branches are created.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '021_add_branch_indexes'
down_revision = '020_fix_npc_unique'
branch_labels = None
depends_on = None


def upgrade():
    # Add composite indexes for frequently queried tables with branch_id
    
    # Scenes: (story_id, branch_id) and (chapter_id, branch_id)
    op.create_index(
        'ix_scenes_story_branch',
        'scenes',
        ['story_id', 'branch_id'],
        unique=False
    )
    op.create_index(
        'ix_scenes_chapter_branch',
        'scenes',
        ['chapter_id', 'branch_id'],
        unique=False
    )
    
    # Chapters: (story_id, branch_id)
    op.create_index(
        'ix_chapters_story_branch',
        'chapters',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # StoryCharacters: (story_id, branch_id)
    op.create_index(
        'ix_story_characters_story_branch',
        'story_characters',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # CharacterState: (story_id, branch_id)
    op.create_index(
        'ix_character_states_story_branch',
        'character_states',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # LocationState: (story_id, branch_id)
    op.create_index(
        'ix_location_states_story_branch',
        'location_states',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # ObjectState: (story_id, branch_id)
    op.create_index(
        'ix_object_states_story_branch',
        'object_states',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # StoryFlow: (story_id, branch_id)
    op.create_index(
        'ix_story_flows_story_branch',
        'story_flows',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # NPCMention: (story_id, branch_id)
    op.create_index(
        'ix_npc_mentions_story_branch',
        'npc_mentions',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # NPCTracking: (story_id, branch_id)
    op.create_index(
        'ix_npc_tracking_story_branch',
        'npc_tracking',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # CharacterMemory: (story_id, branch_id)
    op.create_index(
        'ix_character_memories_story_branch',
        'character_memories',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # PlotEvent: (story_id, branch_id)
    op.create_index(
        'ix_plot_events_story_branch',
        'plot_events',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # SceneEmbedding: (story_id, branch_id)
    op.create_index(
        'ix_scene_embeddings_story_branch',
        'scene_embeddings',
        ['story_id', 'branch_id'],
        unique=False
    )
    
    # EntityStateBatch: (story_id, branch_id)
    op.create_index(
        'ix_entity_state_batches_story_branch',
        'entity_state_batches',
        ['story_id', 'branch_id'],
        unique=False
    )


def downgrade():
    # Remove composite indexes
    op.drop_index('ix_entity_state_batches_story_branch', table_name='entity_state_batches')
    op.drop_index('ix_scene_embeddings_story_branch', table_name='scene_embeddings')
    op.drop_index('ix_plot_events_story_branch', table_name='plot_events')
    op.drop_index('ix_character_memories_story_branch', table_name='character_memories')
    op.drop_index('ix_npc_tracking_story_branch', table_name='npc_tracking')
    op.drop_index('ix_npc_mentions_story_branch', table_name='npc_mentions')
    op.drop_index('ix_story_flows_story_branch', table_name='story_flows')
    op.drop_index('ix_object_states_story_branch', table_name='object_states')
    op.drop_index('ix_location_states_story_branch', table_name='location_states')
    op.drop_index('ix_character_states_story_branch', table_name='character_states')
    op.drop_index('ix_story_characters_story_branch', table_name='story_characters')
    op.drop_index('ix_chapters_story_branch', table_name='chapters')
    op.drop_index('ix_scenes_chapter_branch', table_name='scenes')
    op.drop_index('ix_scenes_story_branch', table_name='scenes')

