"""Add prose_style to writing_style_presets

Revision ID: 023_add_prose_style_to_presets
Revises: 022_add_extraction_summary
Create Date: 2025-12-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023_add_prose_style_to_presets'
down_revision = '022_add_extraction_summary'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('writing_style_presets', sa.Column('prose_style', sa.String(length=50), nullable=True, server_default='balanced'))


def downgrade():
    op.drop_column('writing_style_presets', 'prose_style')

