"""Add character interactions table and interaction_types to stories

Revision ID: 037
Revises: 036_add_sampler_settings
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '037_add_character_interactions'
down_revision = '036_add_sampler_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Add interaction_types column to stories table
    op.add_column('stories', sa.Column('interaction_types', sa.JSON(), nullable=True))
    
    # Create character_interactions table
    op.create_table(
        'character_interactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('character_a_id', sa.Integer(), nullable=False),
        sa.Column('character_b_id', sa.Integer(), nullable=False),
        sa.Column('interaction_type', sa.String(length=100), nullable=False),
        sa.Column('first_occurrence_scene', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['branch_id'], ['story_branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['character_a_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['character_b_id'], ['characters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_character_interactions_id'), 'character_interactions', ['id'], unique=False)
    op.create_index(op.f('ix_character_interactions_story_id'), 'character_interactions', ['story_id'], unique=False)
    op.create_index(op.f('ix_character_interactions_branch_id'), 'character_interactions', ['branch_id'], unique=False)
    op.create_index(op.f('ix_character_interactions_character_a_id'), 'character_interactions', ['character_a_id'], unique=False)
    op.create_index(op.f('ix_character_interactions_character_b_id'), 'character_interactions', ['character_b_id'], unique=False)
    op.create_index(op.f('ix_character_interactions_interaction_type'), 'character_interactions', ['interaction_type'], unique=False)
    
    # Composite indexes for efficient lookups
    op.create_index('ix_character_interactions_story_chars', 'character_interactions', ['story_id', 'character_a_id', 'character_b_id'], unique=False)
    op.create_index('ix_character_interactions_story_type', 'character_interactions', ['story_id', 'interaction_type'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index('ix_character_interactions_story_type', table_name='character_interactions')
    op.drop_index('ix_character_interactions_story_chars', table_name='character_interactions')
    op.drop_index(op.f('ix_character_interactions_interaction_type'), table_name='character_interactions')
    op.drop_index(op.f('ix_character_interactions_character_b_id'), table_name='character_interactions')
    op.drop_index(op.f('ix_character_interactions_character_a_id'), table_name='character_interactions')
    op.drop_index(op.f('ix_character_interactions_branch_id'), table_name='character_interactions')
    op.drop_index(op.f('ix_character_interactions_story_id'), table_name='character_interactions')
    op.drop_index(op.f('ix_character_interactions_id'), table_name='character_interactions')
    
    # Drop table
    op.drop_table('character_interactions')
    
    # Drop column from stories
    op.drop_column('stories', 'interaction_types')



