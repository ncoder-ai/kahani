"""Add fill_remaining_context to user_settings

Revision ID: 039_fill_remaining_context
Revises: 038_plot_progress_batches
Create Date: 2026-01-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '039_fill_remaining_context'
down_revision = '038_plot_progress_batches'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_settings', sa.Column('fill_remaining_context', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('user_settings', 'fill_remaining_context')
