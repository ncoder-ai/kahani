"""Expand string column sizes for AI-generated content

Revision ID: 026_expand_string_columns
Revises: 025_add_brainstorm_sessions
Create Date: 2025-12-28

This migration expands VARCHAR column sizes across multiple tables to accommodate
longer AI-generated content, particularly from the brainstorm feature.

Changes:
- stories.genre: VARCHAR(50) → VARCHAR(200)
- stories.tone: VARCHAR(50) → VARCHAR(200)
- user_settings.llm_api_type: VARCHAR(50) → VARCHAR(100)
- user_settings.text_completion_preset: VARCHAR(50) → VARCHAR(100)
- user_settings.preferred_scene_length: VARCHAR(50) → VARCHAR(100)
- user_settings.current_engine: VARCHAR(50) → VARCHAR(100)
- writing_style_presets.prose_style: VARCHAR(50) → VARCHAR(100)
- brainstorm_sessions.status: VARCHAR(50) → VARCHAR(100)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '026_expand_string_columns'
down_revision = '025_add_brainstorm_sessions'
branch_labels = None
depends_on = None


def upgrade():
    # Expand stories table columns
    with op.batch_alter_table('stories', schema=None) as batch_op:
        batch_op.alter_column('genre',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=200),
                              existing_nullable=True)
        batch_op.alter_column('tone',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=200),
                              existing_nullable=True)
    
    # Expand user_settings table columns
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.alter_column('llm_api_type',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=100),
                              existing_nullable=True)
        batch_op.alter_column('text_completion_preset',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=100),
                              existing_nullable=True)
        batch_op.alter_column('preferred_scene_length',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=100),
                              existing_nullable=True)
        batch_op.alter_column('current_engine',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=100),
                              existing_nullable=True)
    
    # Expand writing_style_presets table columns
    with op.batch_alter_table('writing_style_presets', schema=None) as batch_op:
        batch_op.alter_column('prose_style',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=100),
                              existing_nullable=True)
    
    # Expand brainstorm_sessions table columns
    with op.batch_alter_table('brainstorm_sessions', schema=None) as batch_op:
        batch_op.alter_column('status',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=100),
                              existing_nullable=False)


def downgrade():
    # Revert brainstorm_sessions table columns
    with op.batch_alter_table('brainstorm_sessions', schema=None) as batch_op:
        batch_op.alter_column('status',
                              existing_type=sa.String(length=100),
                              type_=sa.String(length=50),
                              existing_nullable=False)
    
    # Revert writing_style_presets table columns
    with op.batch_alter_table('writing_style_presets', schema=None) as batch_op:
        batch_op.alter_column('prose_style',
                              existing_type=sa.String(length=100),
                              type_=sa.String(length=50),
                              existing_nullable=True)
    
    # Revert user_settings table columns
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.alter_column('current_engine',
                              existing_type=sa.String(length=100),
                              type_=sa.String(length=50),
                              existing_nullable=True)
        batch_op.alter_column('preferred_scene_length',
                              existing_type=sa.String(length=100),
                              type_=sa.String(length=50),
                              existing_nullable=True)
        batch_op.alter_column('text_completion_preset',
                              existing_type=sa.String(length=100),
                              type_=sa.String(length=50),
                              existing_nullable=True)
        batch_op.alter_column('llm_api_type',
                              existing_type=sa.String(length=100),
                              type_=sa.String(length=50),
                              existing_nullable=True)
    
    # Revert stories table columns
    with op.batch_alter_table('stories', schema=None) as batch_op:
        batch_op.alter_column('tone',
                              existing_type=sa.String(length=200),
                              type_=sa.String(length=50),
                              existing_nullable=True)
        batch_op.alter_column('genre',
                              existing_type=sa.String(length=200),
                              type_=sa.String(length=50),
                              existing_nullable=True)

