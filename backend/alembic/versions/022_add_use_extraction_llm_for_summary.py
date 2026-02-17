"""add use_extraction_llm_for_summary

Revision ID: 022_add_extraction_summary
Revises: 021_add_branch_indexes
Create Date: 2025-01-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '022_add_extraction_summary'
down_revision = '021_add_branch_indexes'
branch_labels = None
depends_on = None


def upgrade():
    """Add use_extraction_llm_for_summary column to user_settings table"""
    # Add the new column
    op.add_column('user_settings', sa.Column('use_extraction_llm_for_summary', sa.Boolean(), nullable=True))


def downgrade():
    """Remove use_extraction_llm_for_summary column from user_settings table"""
    op.drop_column('user_settings', 'use_extraction_llm_for_summary')
