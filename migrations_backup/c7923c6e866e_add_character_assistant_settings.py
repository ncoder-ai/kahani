"""add_character_assistant_settings

Revision ID: c7923c6e866e
Revises: bbf4e254a824
Create Date: 2025-10-27 15:55:00.166068

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7923c6e866e'
down_revision = 'bbf4e254a824'
branch_labels = None
depends_on = None


def upgrade():
    # Check if columns exist before adding (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    # Add character assistant settings to user_settings table
    # SQLite doesn't support ALTER COLUMN, so we add with defaults
    if 'enable_character_suggestions' not in columns:
        op.add_column('user_settings', sa.Column('enable_character_suggestions', sa.Boolean(), nullable=False, default=True))
    if 'character_importance_threshold' not in columns:
        op.add_column('user_settings', sa.Column('character_importance_threshold', sa.Integer(), nullable=False, default=70))
    if 'character_mention_threshold' not in columns:
        op.add_column('user_settings', sa.Column('character_mention_threshold', sa.Integer(), nullable=False, default=5))


def downgrade():
    # Remove character assistant settings columns
    op.drop_column('user_settings', 'character_mention_threshold')
    op.drop_column('user_settings', 'character_importance_threshold')
    op.drop_column('user_settings', 'enable_character_suggestions')
