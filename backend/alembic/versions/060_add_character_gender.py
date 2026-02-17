"""Add gender field to characters table

Revision ID: 060_character_gender
Revises: 059_chapter_creation_step
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa


revision = '060_character_gender'
down_revision = '059_chapter_creation_step'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('characters', sa.Column('gender', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('characters', 'gender')
