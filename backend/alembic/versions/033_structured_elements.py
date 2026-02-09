"""Add structured_elements to chapter_brainstorm_sessions

Revision ID: 033_structured_elements
Revises: 032_reasoning_effort
Create Date: 2026-01-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '033_structured_elements'
down_revision = '032_reasoning_effort'
branch_labels = None
depends_on = None


def upgrade():
    # Add structured_elements column to store confirmed brainstorm elements
    # Structure: {overview: str, characters: [...], tone: str, key_events: [...], ending: str}
    op.add_column('chapter_brainstorm_sessions', sa.Column('structured_elements', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('chapter_brainstorm_sessions', 'structured_elements')

