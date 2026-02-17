"""Add npc_tracking_snapshots table

Revision ID: 015_add_npc_tracking_snapshots
Revises: 014_add_pov_to_writing_presets
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015_add_npc_tracking_snapshots'
down_revision = '014_add_pov_to_writing_presets'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'npc_tracking_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('scene_sequence', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_npc_tracking_snapshots_id', 'npc_tracking_snapshots', ['id'], unique=False)
    op.create_index('ix_npc_tracking_snapshots_scene_id', 'npc_tracking_snapshots', ['scene_id'], unique=False)
    op.create_index('ix_npc_tracking_snapshots_story_id', 'npc_tracking_snapshots', ['story_id'], unique=False)
    op.create_index('idx_npc_snapshot_story_sequence', 'npc_tracking_snapshots', ['story_id', 'scene_sequence'], unique=False)

def downgrade():
    op.drop_index('idx_npc_snapshot_story_sequence', table_name='npc_tracking_snapshots')
    op.drop_index('ix_npc_tracking_snapshots_story_id', table_name='npc_tracking_snapshots')
    op.drop_index('ix_npc_tracking_snapshots_scene_id', table_name='npc_tracking_snapshots')
    op.drop_index('ix_npc_tracking_snapshots_id', table_name='npc_tracking_snapshots')
    op.drop_table('npc_tracking_snapshots')



