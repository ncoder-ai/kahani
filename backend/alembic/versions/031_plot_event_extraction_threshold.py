"""Add plot event extraction threshold and tracking

Revision ID: 031_plot_event_threshold
Revises: 030_content_rating
Create Date: 2026-01-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '031_plot_event_threshold'
down_revision = '030_content_rating'
branch_labels = None
depends_on = None


def upgrade():
    # Add plot_event_extraction_threshold to user_settings table
    op.add_column('user_settings', sa.Column('plot_event_extraction_threshold', sa.Integer(), nullable=True))
    
    # Add last_plot_extraction_scene_count to chapters table
    op.add_column('chapters', sa.Column('last_plot_extraction_scene_count', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    # Remove columns
    op.drop_column('chapters', 'last_plot_extraction_scene_count')
    op.drop_column('user_settings', 'plot_event_extraction_threshold')

