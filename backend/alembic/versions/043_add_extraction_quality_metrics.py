"""Add extraction quality metrics to Story model

Revision ID: 043_extraction_quality_metrics
Revises: 042_make_generated_image_story_id_nullable
Create Date: 2026-01-25

Tracks extraction quality per story:
- extraction_success_rate: % of extractions with 2+ meaningful fields
- extraction_empty_rate: % of extractions that returned empty data
- extraction_total_count: total extractions performed
- last_extraction_quality_check: timestamp of last metrics update
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '043_extraction_quality_metrics'
down_revision = '042_nullable_story_id'
branch_labels = None
depends_on = None


def upgrade():
    # Add extraction quality metrics columns to stories table
    op.add_column('stories', sa.Column('extraction_success_rate', sa.Integer(), nullable=True))
    op.add_column('stories', sa.Column('extraction_empty_rate', sa.Integer(), nullable=True))
    op.add_column('stories', sa.Column('extraction_total_count', sa.Integer(), server_default='0', nullable=True))
    op.add_column('stories', sa.Column('last_extraction_quality_check', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('stories', 'last_extraction_quality_check')
    op.drop_column('stories', 'extraction_total_count')
    op.drop_column('stories', 'extraction_empty_rate')
    op.drop_column('stories', 'extraction_success_rate')
