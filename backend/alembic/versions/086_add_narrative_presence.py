"""add narrative_presence to story_characters (Feature 3)

Revision ID: 086_add_narrative_presence
Revises: 085_add_stt_language
Create Date: 2026-05-16

Per-story per-character narrative presence:
{"presence": "low"|"normal"|"high", "expression": "internal"|"balanced"|"spoken"}
Nullable; null (or normal+balanced) is a no-op. Parallels voice_style_override.
"""
from alembic import op
import sqlalchemy as sa


revision = '086_add_narrative_presence'
down_revision = '085_add_stt_language'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'story_characters',
        sa.Column('narrative_presence', sa.JSON(), nullable=True)
    )


def downgrade():
    op.drop_column('story_characters', 'narrative_presence')
