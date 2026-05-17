"""Add tts_segments cache + use_segment_extraction toggle

Revision ID: 078
Revises: 077
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '078_tts_segment_extraction'
down_revision = '077_tts_character_voices'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-variant cache of the LLM-extracted per-speaker segment list.
    # Cleared whenever the variant content changes.
    op.add_column(
        'scene_variants',
        sa.Column('tts_segments', sa.JSON(), nullable=True),
    )

    # User opt-in for the multi-voice + emotion extraction pipeline.
    # Default False — preserves the existing single-voice behaviour for
    # everyone until they explicitly turn it on in the Voice settings.
    op.add_column(
        'tts_settings',
        sa.Column('use_segment_extraction', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('tts_settings', 'use_segment_extraction')
    op.drop_column('scene_variants', 'tts_segments')
