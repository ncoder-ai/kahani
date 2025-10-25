"""add role to story_characters

Revision ID: 006
Revises: 005
Create Date: 2025-10-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

def upgrade():
    # Add role column to story_characters table
    op.add_column('story_characters', sa.Column('role', sa.String(100), nullable=True))

def downgrade():
    # Remove role column from story_characters table
    op.drop_column('story_characters', 'role')
