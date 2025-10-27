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
    op.drop_column('user_settings', 'scene_container_style')


def downgrade():
    # Add back scene_container_style column
    op.add_column('user_settings', sa.Column('scene_container_style', sa.String(20), default='lines'))
