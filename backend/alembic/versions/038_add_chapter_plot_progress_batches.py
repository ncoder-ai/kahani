"""Add chapter_plot_progress_batches table

Revision ID: 038_plot_progress_batches
Revises: 037_add_character_interactions
Create Date: 2026-01-14
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '038_plot_progress_batches'
down_revision = '037_add_character_interactions'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'chapter_plot_progress_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('start_scene_sequence', sa.Integer(), nullable=False),
        sa.Column('end_scene_sequence', sa.Integer(), nullable=False),
        sa.Column('completed_events', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chapter_plot_progress_batches_id'), 'chapter_plot_progress_batches', ['id'], unique=False)
    op.create_index(op.f('ix_chapter_plot_progress_batches_chapter_id'), 'chapter_plot_progress_batches', ['chapter_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_chapter_plot_progress_batches_chapter_id'), table_name='chapter_plot_progress_batches')
    op.drop_index(op.f('ix_chapter_plot_progress_batches_id'), table_name='chapter_plot_progress_batches')
    op.drop_table('chapter_plot_progress_batches')

