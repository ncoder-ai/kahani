"""Add use_streaming column to tts_settings

Revision ID: 081
Revises: 080
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '081_use_streaming'
down_revision = '080_use_multi_speaker'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # When True AND provider supports PCM frame streaming, send the whole
    # scene in ONE single-voice inference call and stream PCM frames as
    # the model generates. Falls back to chunking when not applicable.
    op.add_column(
        'tts_settings',
        sa.Column('use_streaming', sa.Boolean(),
                  nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('tts_settings', 'use_streaming')
