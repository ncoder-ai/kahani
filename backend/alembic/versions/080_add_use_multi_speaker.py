"""Add use_multi_speaker column to tts_settings

Revision ID: 080
Revises: 079
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '080_use_multi_speaker'
down_revision = '079_tts_extraction_llm_choice'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # When True and the configured provider supports it (VibeVoice/F5-TTS),
    # the TTS dispatcher renders the whole scene in one inference call as
    # a multi-speaker script with seamless turn-taking. Falls back to
    # per-utterance chunking transparently when not applicable.
    op.add_column(
        'tts_settings',
        sa.Column('use_multi_speaker', sa.Boolean(),
                  nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('tts_settings', 'use_multi_speaker')
