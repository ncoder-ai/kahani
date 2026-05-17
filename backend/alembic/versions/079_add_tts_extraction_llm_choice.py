"""Add tts_extraction_llm_choice column

Revision ID: 079
Revises: 078
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '079_tts_extraction_llm_choice'
down_revision = '078_tts_segment_extraction'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Which LLM the TTS scene-segment extractor should call.
    # 'extraction' (default) = use the user's extraction LLM (local, cheap, slow)
    # 'main'                 = force the user's main LLM (cloud, costs credits, fast)
    op.add_column(
        'tts_settings',
        sa.Column('tts_extraction_llm_choice', sa.String(20),
                  nullable=False, server_default='extraction'),
    )


def downgrade() -> None:
    op.drop_column('tts_settings', 'tts_extraction_llm_choice')
