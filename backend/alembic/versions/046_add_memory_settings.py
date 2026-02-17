"""Add memory settings to user_settings

Revision ID: 046_add_memory_settings
Revises: 045_add_contradictions
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '046_add_memory_settings'
down_revision = '045_add_contradictions'
branch_labels = None
depends_on = None


def upgrade():
    # Add memory & continuity settings columns to user_settings
    op.add_column('user_settings', sa.Column('enable_working_memory', sa.Boolean(), nullable=True))
    op.add_column('user_settings', sa.Column('enable_contradiction_detection', sa.Boolean(), nullable=True))
    op.add_column('user_settings', sa.Column('contradiction_severity_threshold', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'contradiction_severity_threshold')
    op.drop_column('user_settings', 'enable_contradiction_detection')
    op.drop_column('user_settings', 'enable_working_memory')
