"""add separate_choice_generation setting

Revision ID: 024_add_separate_choice
Revises: 023_add_prose_style_to_presets
Create Date: 2025-01-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024_add_separate_choice'
down_revision = '023_add_prose_style_to_presets'
branch_labels = None
depends_on = None


def upgrade():
    """Add separate_choice_generation column to user_settings table"""
    op.add_column('user_settings', sa.Column('separate_choice_generation', sa.Boolean(), nullable=True))


def downgrade():
    """Remove separate_choice_generation column from user_settings table"""
    op.drop_column('user_settings', 'separate_choice_generation')

