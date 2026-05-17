"""Add use_cache_friendly_prompts to user_settings

Revision ID: 071_cache_friendly_prompts
Revises: 070_cleanup_entity_type_npcs
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '071_cache_friendly_prompts'
down_revision = '070_cleanup_entity_type_npcs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('use_cache_friendly_prompts', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'use_cache_friendly_prompts')
