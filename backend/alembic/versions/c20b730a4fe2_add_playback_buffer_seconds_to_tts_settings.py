"""Add playback_buffer_seconds to tts_settings

Pre-buffer (seconds) accumulated by the audio player before playback starts.
Lets users absorb upstream generation jitter when streaming RTF is close to
realtime. Range 0.0-10.0 in the UI; 0 effectively disables buffering.

Revision ID: c20b730a4fe2
Revises: 083_provider_id
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa


revision = "c20b730a4fe2"
down_revision = "083_provider_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tts_settings",
        sa.Column(
            "playback_buffer_seconds",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
    )


def downgrade():
    op.drop_column("tts_settings", "playback_buffer_seconds")
