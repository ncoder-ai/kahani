"""Add scene_events table for keyword-based event retrieval

Revision ID: 061_scene_events
Revises: 060_character_gender
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa


revision = '061_scene_events'
down_revision = '060_character_gender'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scene_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scene_sequence', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), sa.ForeignKey('chapters.id', ondelete='CASCADE'), nullable=True),
        sa.Column('event_text', sa.String(500), nullable=False),
        sa.Column('characters_involved', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Individual column indexes
    op.create_index('ix_scene_events_id', 'scene_events', ['id'])
    op.create_index('ix_scene_events_story_id', 'scene_events', ['story_id'])
    op.create_index('ix_scene_events_branch_id', 'scene_events', ['branch_id'])
    op.create_index('ix_scene_events_scene_id', 'scene_events', ['scene_id'])
    op.create_index('ix_scene_events_scene_sequence', 'scene_events', ['scene_sequence'])

    # Composite indexes
    op.create_index('ix_scene_events_story_sequence', 'scene_events', ['story_id', 'scene_sequence'])
    op.create_index('ix_scene_events_story_branch', 'scene_events', ['story_id', 'branch_id'])
    op.create_index('ix_scene_events_scene', 'scene_events', ['scene_id'])


def downgrade():
    op.drop_table('scene_events')
