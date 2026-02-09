"""Add show_scene_images to user_settings

Revision ID: 041_add_show_scene_images
Revises: 040_add_image_generation
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '041_add_show_scene_images'
down_revision = '040_add_image_generation'
branch_labels = None
depends_on = None


def upgrade():
    # Add show_scene_images column to user_settings
    op.add_column('user_settings', sa.Column('show_scene_images', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user_settings', 'show_scene_images')
