"""add brainstorm sessions

Revision ID: 025_add_brainstorm_sessions
Revises: 024_add_separate_choice
Create Date: 2025-01-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '025_add_brainstorm_sessions'
down_revision = '024_add_separate_choice'
branch_labels = None
depends_on = None


def upgrade():
    # Create brainstorm_sessions table
    op.create_table(
        'brainstorm_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('messages', sa.JSON(), nullable=False),
        sa.Column('extracted_elements', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_brainstorm_sessions_id'), 'brainstorm_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_brainstorm_sessions_user_id'), 'brainstorm_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_brainstorm_sessions_status'), 'brainstorm_sessions', ['status'], unique=False)
    op.create_index(op.f('ix_brainstorm_sessions_story_id'), 'brainstorm_sessions', ['story_id'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_brainstorm_sessions_story_id'), table_name='brainstorm_sessions')
    op.drop_index(op.f('ix_brainstorm_sessions_status'), table_name='brainstorm_sessions')
    op.drop_index(op.f('ix_brainstorm_sessions_user_id'), table_name='brainstorm_sessions')
    op.drop_index(op.f('ix_brainstorm_sessions_id'), table_name='brainstorm_sessions')
    
    # Drop table
    op.drop_table('brainstorm_sessions')

