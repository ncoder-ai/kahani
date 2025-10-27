"""add_engine_specific_settings

Revision ID: ec1f4e1c996a
Revises: 008
Create Date: 2025-10-27 12:11:47.446152

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ec1f4e1c996a'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    # Check if columns exist before adding (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    # Add engine-specific settings columns
    if 'engine_settings' not in columns:
        op.add_column('user_settings', sa.Column('engine_settings', sa.Text(), server_default='{}', nullable=False))
    if 'current_engine' not in columns:
        op.add_column('user_settings', sa.Column('current_engine', sa.String(50), server_default='', nullable=False))


def downgrade():
    # Remove engine-specific settings columns
    op.drop_column('user_settings', 'current_engine')
    op.drop_column('user_settings', 'engine_settings')
