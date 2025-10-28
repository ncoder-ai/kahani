"""add scenario field to stories

Revision ID: 005
Revises: 004
Create Date: 2025-10-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

def upgrade():
    # Add scenario column to stories table
    op.add_column('stories', sa.Column('scenario', sa.Text(), nullable=True))

def downgrade():
    # Remove scenario column from stories table
    op.drop_column('stories', 'scenario')
