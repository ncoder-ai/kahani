"""remove_scene_container_style

Revision ID: bbf4e254a824
Revises: ec1f4e1c996a
Create Date: 2025-10-27 13:56:28.287617

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bbf4e254a824'
down_revision = 'ec1f4e1c996a'
branch_labels = None
depends_on = None


def upgrade():
    # Remove scene_container_style column from user_settings table
    # Check if column exists before trying to drop it (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    if 'scene_container_style' in columns:
        op.drop_column('user_settings', 'scene_container_style')
    # If column doesn't exist, the migration effect is already applied


def downgrade():
    # Add back scene_container_style column
    op.add_column('user_settings', sa.Column('scene_container_style', sa.String(20), default='lines'))
