"""add chapter metadata and character associations

Revision ID: 009
Revises: 008
Create Date: 2025-01-XX

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add chapter metadata fields and chapter-character association table"""
    
    # Add new fields to chapters table
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('time_period', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('scenario', sa.Text(), nullable=True))
    
    # Create chapter_characters junction table
    op.create_table('chapter_characters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('story_character_id', sa.Integer(), nullable=False),
        sa.Column('perspective', sa.String(length=50), nullable=True),  # For future use (POV, main, supporting)
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_character_id'], ['story_characters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chapter_id', 'story_character_id', name='uq_chapter_character')
    )
    
    # Create indexes
    op.create_index('ix_chapter_characters_chapter_id', 'chapter_characters', ['chapter_id'])
    op.create_index('ix_chapter_characters_story_character_id', 'chapter_characters', ['story_character_id'])


def downgrade() -> None:
    """Remove chapter metadata fields and chapter-character association table"""
    
    # Drop chapter_characters table
    op.drop_index('ix_chapter_characters_story_character_id', table_name='chapter_characters')
    op.drop_index('ix_chapter_characters_chapter_id', table_name='chapter_characters')
    op.drop_table('chapter_characters')
    
    # Remove columns from chapters table
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.drop_column('scenario')
        batch_op.drop_column('time_period')
        batch_op.drop_column('location_name')

