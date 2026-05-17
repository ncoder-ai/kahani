"""Add tts_character_voices column to stories

Revision ID: 077
Revises: 076
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '077_tts_character_voices'
down_revision = '076_scene_event_embeddings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-story character→voice mapping namespaced by TTS provider.
    # Nullable; defaults to no mapping (synthesis falls back to the
    # user's default voice from tts_settings).
    op.add_column(
        'stories',
        sa.Column('tts_character_voices', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('stories', 'tts_character_voices')
