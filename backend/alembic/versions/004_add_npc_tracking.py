"""add npc tracking

Revision ID: 004
Revises: 003
Create Date: 2025-01-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add NPC tracking tables"""
    
    # Create npc_mentions table
    op.create_table(
        'npc_mentions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('character_name', sa.String(length=255), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('mention_count', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('has_dialogue', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('has_actions', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('has_relationships', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('context_snippets', sa.JSON(), nullable=True),
        sa.Column('extracted_properties', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create npc_tracking table
    op.create_table(
        'npc_tracking',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('character_name', sa.String(length=255), nullable=False),
        sa.Column('total_mentions', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('scene_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('first_appearance_scene', sa.Integer(), nullable=True),
        sa.Column('last_appearance_scene', sa.Integer(), nullable=True),
        sa.Column('has_dialogue_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('has_actions_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('significance_score', sa.Float(), nullable=True, server_default='0'),
        sa.Column('importance_score', sa.Float(), nullable=True, server_default='0'),
        sa.Column('frequency_score', sa.Float(), nullable=True, server_default='0'),
        sa.Column('extracted_profile', sa.JSON(), nullable=True),
        sa.Column('crossed_threshold', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('user_prompted', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('profile_extracted', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('converted_to_character', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('last_calculated', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('story_id', 'character_name', name='idx_npc_tracking_story_name')
    )
    
    # Create indexes for npc_mentions
    op.create_index('ix_npc_mentions_story_id', 'npc_mentions', ['story_id'])
    op.create_index('ix_npc_mentions_scene_id', 'npc_mentions', ['scene_id'])
    op.create_index('ix_npc_mentions_character_name', 'npc_mentions', ['character_name'])
    op.create_index('idx_npc_mentions_story_name', 'npc_mentions', ['story_id', 'character_name'])
    op.create_index('idx_npc_mentions_story_scene', 'npc_mentions', ['story_id', 'scene_id'])
    
    # Create indexes for npc_tracking
    op.create_index('ix_npc_tracking_story_id', 'npc_tracking', ['story_id'])
    op.create_index('ix_npc_tracking_character_name', 'npc_tracking', ['character_name'])
    op.create_index('ix_npc_tracking_importance_score', 'npc_tracking', ['importance_score'])
    op.create_index('ix_npc_tracking_crossed_threshold', 'npc_tracking', ['crossed_threshold'])
    op.create_index('ix_npc_tracking_converted', 'npc_tracking', ['converted_to_character'])
    op.create_index('idx_npc_tracking_threshold', 'npc_tracking', ['story_id', 'crossed_threshold'])


def downgrade() -> None:
    """Remove NPC tracking tables"""
    
    # Drop indexes first
    op.drop_index('idx_npc_tracking_threshold', table_name='npc_tracking')
    op.drop_index('ix_npc_tracking_converted', table_name='npc_tracking')
    op.drop_index('ix_npc_tracking_crossed_threshold', table_name='npc_tracking')
    op.drop_index('ix_npc_tracking_importance_score', table_name='npc_tracking')
    op.drop_index('ix_npc_tracking_character_name', table_name='npc_tracking')
    op.drop_index('ix_npc_tracking_story_id', table_name='npc_tracking')
    
    op.drop_index('idx_npc_mentions_story_scene', table_name='npc_mentions')
    op.drop_index('idx_npc_mentions_story_name', table_name='npc_mentions')
    op.drop_index('ix_npc_mentions_character_name', table_name='npc_mentions')
    op.drop_index('ix_npc_mentions_scene_id', table_name='npc_mentions')
    op.drop_index('ix_npc_mentions_story_id', table_name='npc_mentions')
    
    # Drop tables
    op.drop_table('npc_tracking')
    op.drop_table('npc_mentions')

