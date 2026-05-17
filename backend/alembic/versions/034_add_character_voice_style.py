"""Add voice_style to characters and story_characters

Revision ID: 034
Revises: 033_structured_elements
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '034_add_character_voice_style'
down_revision = '033_structured_elements'
branch_labels = None
depends_on = None


def upgrade():
    # Add voice_style column to characters table (character's default speaking style)
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('voice_style', sa.JSON(), nullable=True))
    
    # Add voice_style_override column to story_characters table (per-story override)
    with op.batch_alter_table('story_characters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('voice_style_override', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('story_characters', schema=None) as batch_op:
        batch_op.drop_column('voice_style_override')
    
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('voice_style')

