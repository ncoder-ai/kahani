"""Add enable_chapter_plot_tracking to user_settings

Revision ID: 029_add_enable_chapter_plot_tracking
Revises: 028_add_plot_progress
Create Date: 2024-12-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '029_add_enable_chapter_plot_tracking'
down_revision = '028_add_plot_progress'
branch_labels = None
depends_on = None


def upgrade():
    # Add enable_chapter_plot_tracking column to user_settings table
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('enable_chapter_plot_tracking', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_column('enable_chapter_plot_tracking')

