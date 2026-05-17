"""Add chapter_summary_batches table

Revision ID: 011_add_chapter_summary_batches
Revises: 010_add_continues_from_previous
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_add_chapter_summary_batches'
down_revision = '010_add_continues_from_previous'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'chapter_summary_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=False),
        sa.Column('start_scene_sequence', sa.Integer(), nullable=False),
        sa.Column('end_scene_sequence', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chapter_summary_batches_id'), 'chapter_summary_batches', ['id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_chapter_summary_batches_id'), table_name='chapter_summary_batches')
    op.drop_table('chapter_summary_batches')

