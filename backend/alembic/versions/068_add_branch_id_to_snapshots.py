"""Add branch_id to character_snapshots

Revision ID: 068_branch_snapshots
Revises: 067_character_snapshots
Create Date: 2026-02-14
"""
from alembic import op
import sqlalchemy as sa

revision = '068_branch_snapshots'
down_revision = '067_character_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    # Delete existing snapshots — they were generated without branch scoping
    op.execute("DELETE FROM character_snapshots")

    # Add branch_id column
    op.add_column('character_snapshots', sa.Column(
        'branch_id', sa.Integer(),
        sa.ForeignKey('story_branches.id'), nullable=True,
    ))
    op.create_index('ix_character_snapshots_branch_id', 'character_snapshots', ['branch_id'])

    # Drop old unique index
    op.drop_index('idx_snapshot_world_character', table_name='character_snapshots')

    # Create new unique constraint (NULL branch_id treated as distinct by PostgreSQL default)
    op.create_unique_constraint(
        'idx_snapshot_world_character_branch',
        'character_snapshots',
        ['world_id', 'character_id', 'branch_id'],
    )


def downgrade():
    op.drop_constraint('idx_snapshot_world_character_branch', 'character_snapshots', type_='unique')
    op.drop_index('ix_character_snapshots_branch_id', table_name='character_snapshots')
    op.drop_column('character_snapshots', 'branch_id')

    # Recreate old unique index
    op.create_index('idx_snapshot_world_character', 'character_snapshots', ['world_id', 'character_id'], unique=True)
