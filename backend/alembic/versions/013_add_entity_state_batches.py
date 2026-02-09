"""Add entity_state_batches table

Revision ID: 013_add_entity_state_batches
Revises: 011_add_chapter_summary_batches
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013_add_entity_state_batches'
down_revision = '011_add_chapter_summary_batches'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'entity_state_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('start_scene_sequence', sa.Integer(), nullable=False),
        sa.Column('end_scene_sequence', sa.Integer(), nullable=False),
        sa.Column('character_states_snapshot', sa.JSON(), nullable=False),
        sa.Column('location_states_snapshot', sa.JSON(), nullable=False),
        sa.Column('object_states_snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entity_state_batches_id'), 'entity_state_batches', ['id'], unique=False)
    op.create_index(op.f('ix_entity_state_batches_story_id'), 'entity_state_batches', ['story_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_entity_state_batches_story_id'), table_name='entity_state_batches')
    op.drop_index(op.f('ix_entity_state_batches_id'), table_name='entity_state_batches')
    op.drop_table('entity_state_batches')

