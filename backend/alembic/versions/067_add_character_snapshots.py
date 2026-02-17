"""Add character_snapshots table and timeline_order to stories

Revision ID: 067_character_snapshots
Revises: 066_chronicle_tracking
Create Date: 2026-02-14
"""
from alembic import op
import sqlalchemy as sa

revision = '067_character_snapshots'
down_revision = '066_chronicle_tracking'
branch_labels = None
depends_on = None


def upgrade():
    # Add timeline_order to stories
    op.add_column('stories', sa.Column('timeline_order', sa.Integer(), nullable=True))

    # Create character_snapshots table
    op.create_table(
        'character_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('world_id', sa.Integer(), sa.ForeignKey('worlds.id'), nullable=False),
        sa.Column('character_id', sa.Integer(), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('story_branches.id'), nullable=True),
        sa.Column('snapshot_text', sa.Text(), nullable=False),
        sa.Column('chronicle_entry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('timeline_order', sa.Integer(), nullable=True),
        sa.Column('up_to_story_id', sa.Integer(), sa.ForeignKey('stories.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_character_snapshots_id', 'character_snapshots', ['id'])
    op.create_index('ix_character_snapshots_world_id', 'character_snapshots', ['world_id'])
    op.create_index('ix_character_snapshots_character_id', 'character_snapshots', ['character_id'])
    op.create_index('ix_character_snapshots_branch_id', 'character_snapshots', ['branch_id'])
    op.create_unique_constraint('idx_snapshot_world_character_branch', 'character_snapshots', ['world_id', 'character_id', 'branch_id'])


def downgrade():
    op.drop_table('character_snapshots')
    op.drop_column('stories', 'timeline_order')
