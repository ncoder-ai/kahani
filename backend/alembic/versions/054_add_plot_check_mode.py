"""Add plot_check_mode to stories and default_plot_check_mode to user_settings

Revision ID: 054_plot_check_mode
Revises: 053_extraction_advanced
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "054_plot_check_mode"
down_revision = "053_extraction_advanced"
branch_labels = None
depends_on = None


def upgrade():
    # Add plot_check_mode to stories table
    # Values: "1" (strict - next event only), "3" (next 3 events), "all" (all remaining)
    op.add_column(
        "stories",
        sa.Column("plot_check_mode", sa.String(10), nullable=True)
    )

    # Add default_plot_check_mode to user_settings table
    op.add_column(
        "user_settings",
        sa.Column("default_plot_check_mode", sa.String(10), nullable=True)
    )


def downgrade():
    op.drop_column("user_settings", "default_plot_check_mode")
    op.drop_column("stories", "plot_check_mode")
