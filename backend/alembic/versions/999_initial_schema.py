"""Consolidate all previous migrations

Revision ID: 999
Revises: c7923c6e866e
Create Date: 2025-10-28 09:40:38.310838

This migration consolidates all previous migrations (001-008, and hash-named ones)
into a single revision. Since the database already has all tables from the previous
migrations, this is a no-op migration that just updates the alembic version.

This allows us to:
1. Clean up the migration history
2. Use a single consolidated migration going forward
3. Maintain all existing data and schema
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '999'
down_revision = 'c7923c6e866e'
branch_labels = None
depends_on = None


def upgrade():
    # This migration consolidates all previous migrations into a single revision
    # Since the database already has all tables from the previous migrations,
    # this is a no-op migration that just updates the alembic version
    pass


def downgrade():
    # This migration consolidates all previous migrations into a single revision
    # Since we're consolidating, we can't easily downgrade to individual migrations
    # In practice, you would restore from a backup if you need to rollback
    pass