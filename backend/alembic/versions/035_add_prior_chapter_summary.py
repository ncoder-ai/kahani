"""Add prior_chapter_summary to chapter_brainstorm_sessions

Revision ID: 035
Revises: 034
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade():
    """Add prior_chapter_summary column to chapter_brainstorm_sessions table."""
    # Add prior_chapter_summary column for storing user-provided context
    op.add_column(
        'chapter_brainstorm_sessions',
        sa.Column('prior_chapter_summary', sa.Text(), nullable=True)
    )


def downgrade():
    """Remove prior_chapter_summary column."""
    op.drop_column('chapter_brainstorm_sessions', 'prior_chapter_summary')

