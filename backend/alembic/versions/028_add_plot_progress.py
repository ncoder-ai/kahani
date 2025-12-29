"""Add plot_progress to chapters

Revision ID: 028
Revises: 027
Create Date: 2024-12-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '028_add_plot_progress'
down_revision = '027_add_story_arc_and_chapter_brainstorm'
branch_labels = None
depends_on = None


def upgrade():
    # Add plot_progress column to chapters table
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plot_progress', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.drop_column('plot_progress')

