"""add stt_language to user_settings

Revision ID: 085_add_stt_language
Revises: 084_main_llm_scene_events
Create Date: 2026-05-14

"""
from alembic import op
import sqlalchemy as sa


revision = '085_add_stt_language'
down_revision = '084_main_llm_scene_events'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user_settings',
        sa.Column('stt_language', sa.String(length=16), nullable=True)
    )


def downgrade():
    op.drop_column('user_settings', 'stt_language')
