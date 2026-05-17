"""Add roleplay support: StoryMode.ROLEPLAY enum value and StoryCharacter roleplay fields

Revision ID: 072_add_roleplay_support
Revises: 071_cache_friendly_prompts
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '072_add_roleplay_support'
down_revision = '071_cache_friendly_prompts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ROLEPLAY to story_mode enum
    # PostgreSQL requires explicit ALTER TYPE for enums
    op.execute("ALTER TYPE storymode ADD VALUE IF NOT EXISTS 'ROLEPLAY'")

    # Add roleplay fields to story_characters
    op.add_column('story_characters', sa.Column('source_story_id', sa.Integer(), sa.ForeignKey('stories.id'), nullable=True))
    op.add_column('story_characters', sa.Column('source_branch_id', sa.Integer(), sa.ForeignKey('story_branches.id'), nullable=True))
    op.add_column('story_characters', sa.Column('is_player_character', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('story_characters', 'is_player_character')
    op.drop_column('story_characters', 'source_branch_id')
    op.drop_column('story_characters', 'source_story_id')
    # Note: PostgreSQL does not support removing enum values
