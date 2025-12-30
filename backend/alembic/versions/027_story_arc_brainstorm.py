"""Add story arc and chapter brainstorm support

Revision ID: 027_story_arc_brainstorm
Revises: 026_expand_string_columns
Create Date: 2024-12-28

This migration adds:
1. story_arc JSON column to stories table for AI-generated narrative structure
2. chapter_brainstorm_sessions table for chapter-level brainstorming
3. chapter_plot, arc_phase_id, brainstorm_session_id columns to chapters table
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '027_story_arc_brainstorm'
down_revision = '026_expand_string_columns'
branch_labels = None
depends_on = None


def upgrade():
    # Add story_arc to stories table
    op.add_column('stories', sa.Column('story_arc', sa.JSON(), nullable=True))
    
    # Create chapter_brainstorm_sessions table
    op.create_table(
        'chapter_brainstorm_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('messages', sa.JSON(), default=list),
        sa.Column('extracted_plot', sa.JSON(), nullable=True),
        sa.Column('arc_phase_id', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), default='brainstorming'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create index on story_id for faster lookups
    op.create_index('ix_chapter_brainstorm_sessions_story_id', 'chapter_brainstorm_sessions', ['story_id'])
    op.create_index('ix_chapter_brainstorm_sessions_user_id', 'chapter_brainstorm_sessions', ['user_id'])
    
    # Add chapter plot fields to chapters table (without foreign key constraint for SQLite compatibility)
    op.add_column('chapters', sa.Column('chapter_plot', sa.JSON(), nullable=True))
    op.add_column('chapters', sa.Column('arc_phase_id', sa.String(100), nullable=True))
    op.add_column('chapters', sa.Column('brainstorm_session_id', sa.Integer(), nullable=True))


def downgrade():
    # Remove chapter plot fields from chapters
    op.drop_column('chapters', 'brainstorm_session_id')
    op.drop_column('chapters', 'arc_phase_id')
    op.drop_column('chapters', 'chapter_plot')
    
    # Drop indexes
    op.drop_index('ix_chapter_brainstorm_sessions_user_id', 'chapter_brainstorm_sessions')
    op.drop_index('ix_chapter_brainstorm_sessions_story_id', 'chapter_brainstorm_sessions')
    
    # Drop chapter_brainstorm_sessions table
    op.drop_table('chapter_brainstorm_sessions')
    
    # Remove story_arc from stories
    op.drop_column('stories', 'story_arc')
