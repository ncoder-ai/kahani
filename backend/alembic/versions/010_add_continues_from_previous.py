"""Add continues_from_previous to chapters

Revision ID: 010_add_continues_from_previous
Revises: 009_add_chapter_metadata
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010_add_continues_from_previous'
down_revision = '009'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('chapters', sa.Column('continues_from_previous', sa.Boolean(), nullable=False, server_default='1'))

def downgrade():
    op.drop_column('chapters', 'continues_from_previous')

