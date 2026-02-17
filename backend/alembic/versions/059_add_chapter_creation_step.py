"""add creation_step to chapters for resumable chapter creation

Revision ID: 059_chapter_creation_step
Revises: 058_position_tracking
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa


revision = '059_chapter_creation_step'
down_revision = '058_position_tracking'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chapters', sa.Column('creation_step', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('chapters', 'creation_step')
