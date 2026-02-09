"""Add sampler_settings to user_settings

Revision ID: 036_add_sampler_settings
Revises: 035_add_prior_chapter_summary
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '036_add_sampler_settings'
down_revision = '035_add_prior_chapter_summary'
branch_labels = None
depends_on = None


def upgrade():
    """Add sampler_settings column to user_settings table.
    
    This column stores a JSON blob containing all advanced sampler configurations
    for TabbyAPI and other OpenAI-compatible APIs. Each sampler can be individually
    enabled/disabled and configured.
    """
    op.add_column(
        'user_settings',
        sa.Column('sampler_settings', sa.Text(), nullable=True)
    )


def downgrade():
    """Remove sampler_settings column."""
    op.drop_column('user_settings', 'sampler_settings')

