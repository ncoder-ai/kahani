"""Add manually_edited_fields to character_states

Revision ID: 051
Revises: 050_fix_all_null_branch_ids
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '051_add_manually_edited_fields'
down_revision = '050_fix_all_null_branch_ids'
branch_labels = None
depends_on = None


def upgrade():
    # Add manually_edited_fields column to track user-edited fields
    # that should not be overwritten by automatic extraction
    op.add_column('character_states', sa.Column('manually_edited_fields', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('character_states', 'manually_edited_fields')
