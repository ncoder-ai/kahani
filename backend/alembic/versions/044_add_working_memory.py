"""Add working memory table for scene-to-scene continuity

Revision ID: 044_add_working_memory
Revises: 043_extraction_quality_metrics
Create Date: 2026-01-25

Adds working_memory table to track:
- recent_focus: What was important in last few scenes
- pending_items: Concrete items mentioned but not acted on
- character_spotlight: Characters needing narrative attention
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '044_add_working_memory'
down_revision = '043_extraction_quality_metrics'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'working_memory',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('chapter_id', sa.Integer(), sa.ForeignKey('chapters.id', ondelete='SET NULL'), nullable=True),
        sa.Column('recent_focus', sa.JSON(), nullable=True),
        sa.Column('pending_items', sa.JSON(), nullable=True),
        sa.Column('character_spotlight', sa.JSON(), nullable=True),
        sa.Column('last_scene_sequence', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('working_memory')
