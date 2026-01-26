"""Add relationship graph tables

Revision ID: 047_add_relationship_graph
Revises: 046_add_memory_settings
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa


revision = '047_add_relationship_graph'
down_revision = '046_add_memory_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Character relationships (event log)
    op.create_table(
        'character_relationships',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True),
        sa.Column('character_a', sa.String(255), nullable=False),
        sa.Column('character_b', sa.String(255), nullable=False),
        sa.Column('relationship_type', sa.String(50)),
        sa.Column('strength', sa.Float(), default=0.0),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('scene_sequence', sa.Integer(), nullable=False),
        sa.Column('change_description', sa.Text()),
        sa.Column('change_sentiment', sa.String(20)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_relationship_story_chars', 'character_relationships',
                    ['story_id', 'character_a', 'character_b'])
    op.create_index('idx_relationship_story_branch', 'character_relationships',
                    ['story_id', 'branch_id'])
    op.create_index('idx_relationship_scene_seq', 'character_relationships',
                    ['story_id', 'scene_sequence'])

    # Relationship summaries (current state)
    op.create_table(
        'relationship_summaries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True),
        sa.Column('character_a', sa.String(255), nullable=False),
        sa.Column('character_b', sa.String(255), nullable=False),
        sa.Column('current_type', sa.String(50)),
        sa.Column('current_strength', sa.Float(), default=0.0),
        sa.Column('initial_type', sa.String(50)),
        sa.Column('initial_strength', sa.Float()),
        sa.Column('trajectory', sa.String(20)),
        sa.Column('total_interactions', sa.Integer(), default=0),
        sa.Column('last_scene_sequence', sa.Integer()),
        sa.Column('last_change', sa.Text()),
        sa.Column('arc_summary', sa.Text()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_relsummary_story_chars', 'relationship_summaries',
                    ['story_id', 'branch_id', 'character_a', 'character_b'], unique=True)
    op.create_index('idx_relsummary_story_branch', 'relationship_summaries',
                    ['story_id', 'branch_id'])

    # User setting for relationship graph
    op.add_column('user_settings', sa.Column('enable_relationship_graph', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'enable_relationship_graph')
    op.drop_index('idx_relsummary_story_branch', 'relationship_summaries')
    op.drop_index('idx_relsummary_story_chars', 'relationship_summaries')
    op.drop_table('relationship_summaries')
    op.drop_index('idx_relationship_scene_seq', 'character_relationships')
    op.drop_index('idx_relationship_story_branch', 'character_relationships')
    op.drop_index('idx_relationship_story_chars', 'character_relationships')
    op.drop_table('character_relationships')
