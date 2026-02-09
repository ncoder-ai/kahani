"""Add contradiction injection and inline check settings

Adds three new columns to user_settings:
- enable_contradiction_injection: Inject warnings into prompt
- enable_inline_contradiction_check: Run extraction + check every scene
- auto_regenerate_on_contradiction: Auto-regen once if contradiction found

Revision ID: 049_contradiction_injection
Revises: 048_fix_entity_state_branches
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = '049_contradiction_injection'
down_revision = '048_fix_entity_state_branches'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('enable_contradiction_injection', sa.Boolean(), nullable=True))
    op.add_column('user_settings', sa.Column('enable_inline_contradiction_check', sa.Boolean(), nullable=True))
    op.add_column('user_settings', sa.Column('auto_regenerate_on_contradiction', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'auto_regenerate_on_contradiction')
    op.drop_column('user_settings', 'enable_inline_contradiction_check')
    op.drop_column('user_settings', 'enable_contradiction_injection')
