"""Add content_rating to stories

Revision ID: 030_content_rating
Revises: 029_plot_tracking_setting
Create Date: 2026-01-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '030_content_rating'
down_revision = '029_plot_tracking_setting'
branch_labels = None
depends_on = None


def upgrade():
    # Add content_rating column to stories table with default 'sfw'
    with op.batch_alter_table('stories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_rating', sa.String(10), nullable=True, server_default='sfw'))


def downgrade():
    with op.batch_alter_table('stories', schema=None) as batch_op:
        batch_op.drop_column('content_rating')

