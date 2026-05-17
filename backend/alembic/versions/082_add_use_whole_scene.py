"""Add use_whole_scene column to tts_settings

Revision ID: 082
Revises: 081
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '082_use_whole_scene'
down_revision = '081_use_streaming'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # When True AND streaming is not being used, send the whole scene to
    # the TTS as ONE block call instead of chunking. No streaming benefit;
    # avoids chunk-boundary artifacts. Falls back to chunking on failure.
    op.add_column(
        'tts_settings',
        sa.Column('use_whole_scene', sa.Boolean(),
                  nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('tts_settings', 'use_whole_scene')
