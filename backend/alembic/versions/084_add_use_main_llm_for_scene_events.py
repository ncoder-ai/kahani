"""Add use_main_llm_for_scene_events to user_settings

Controls whether per-scene event extraction (recall index) routes to the
main LLM instead of the extraction LLM. Mirrors use_main_llm_for_plot_extraction.

Revision ID: 084_use_main_llm_for_scene_events
Revises: c20b730a4fe2
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa


revision = "084_main_llm_scene_events"
down_revision = "c20b730a4fe2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_settings",
        sa.Column("use_main_llm_for_scene_events", sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column("user_settings", "use_main_llm_for_scene_events")
