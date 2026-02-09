"""add enable_streaming to user_settings

Revision ID: 055_add_enable_streaming
Revises: 054_plot_check_mode
Create Date: 2026-02-01 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '055_add_enable_streaming'
down_revision = '054_plot_check_mode'
branch_labels = None
depends_on = None


def upgrade():
    # Add enable_streaming column to user_settings
    op.add_column('user_settings', sa.Column('enable_streaming', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'enable_streaming')
