"""Add advanced extraction model settings (top_p, repetition_penalty, min_p, thinking disable)

Revision ID: 053_extraction_advanced
Revises: 052_use_context_aware
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "053_extraction_advanced"
down_revision = "052_use_context_aware"
branch_labels = None
depends_on = None


def upgrade():
    # Add advanced sampling settings for extraction model
    op.add_column(
        "user_settings",
        sa.Column("extraction_model_top_p", sa.Float(), nullable=True)
    )
    op.add_column(
        "user_settings",
        sa.Column("extraction_model_repetition_penalty", sa.Float(), nullable=True)
    )
    op.add_column(
        "user_settings",
        sa.Column("extraction_model_min_p", sa.Float(), nullable=True)
    )
    # Thinking disable settings
    # Methods: "none", "qwen3", "deepseek", "mistral", "gemini", "openai", "kimi", "glm", "custom"
    op.add_column(
        "user_settings",
        sa.Column("extraction_model_thinking_disable_method", sa.String(50), nullable=True)
    )
    op.add_column(
        "user_settings",
        sa.Column("extraction_model_thinking_disable_custom", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("user_settings", "extraction_model_thinking_disable_custom")
    op.drop_column("user_settings", "extraction_model_thinking_disable_method")
    op.drop_column("user_settings", "extraction_model_min_p")
    op.drop_column("user_settings", "extraction_model_repetition_penalty")
    op.drop_column("user_settings", "extraction_model_top_p")
