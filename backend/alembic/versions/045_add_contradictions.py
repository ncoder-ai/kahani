"""Add contradictions table for continuity error tracking

Revision ID: 045_add_contradictions
Revises: 044_add_working_memory
Create Date: 2026-01-25

Tracks detected continuity errors:
- location_jump: Character moved without travel scene
- knowledge_leak: Character knows something they shouldn't
- state_regression: State reverted without explanation
- timeline_error: Event order inconsistency
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '045_add_contradictions'
down_revision = '044_add_working_memory'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'contradictions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('scene_sequence', sa.Integer(), nullable=False),
        sa.Column('contradiction_type', sa.String(50), nullable=False),
        sa.Column('character_name', sa.String(255), nullable=True),
        sa.Column('previous_value', sa.Text(), nullable=True),
        sa.Column('current_value', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(20), server_default='warning'),
        sa.Column('resolved', sa.Boolean(), server_default='false', index=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table('contradictions')
