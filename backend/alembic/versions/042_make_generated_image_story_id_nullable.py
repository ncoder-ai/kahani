"""Make generated_image story_id nullable for character portraits

Revision ID: 042_nullable_story_id
Revises: 041_add_show_scene_images
Create Date: 2026-01-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '042_nullable_story_id'
down_revision = '041_add_show_scene_images'
branch_labels = None
depends_on = None


def upgrade():
    # Make story_id nullable to support character portraits without a story
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.alter_column('story_id',
                              existing_type=sa.Integer(),
                              nullable=True)


def downgrade():
    # Revert to non-nullable (will fail if there are NULL values)
    with op.batch_alter_table('generated_images') as batch_op:
        batch_op.alter_column('story_id',
                              existing_type=sa.Integer(),
                              nullable=False)
