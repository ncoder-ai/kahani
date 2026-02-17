"""Add use_context_aware_extraction column

Revision ID: 052_use_context_aware
Revises: 051_add_manually_edited_fields
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "052_use_context_aware"
down_revision = "051_add_manually_edited_fields"
branch_labels = None
depends_on = None


def upgrade():
    # Add use_context_aware_extraction column to user_settings
    op.add_column(
        "user_settings",
        sa.Column("use_context_aware_extraction", sa.Boolean(), nullable=True)
    )


def downgrade():
    op.drop_column("user_settings", "use_context_aware_extraction")
