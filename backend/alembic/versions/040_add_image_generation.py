"""Add image generation support

Creates generated_images table, adds portrait_image_id to characters,
and adds image generation settings to user_settings.

Revision ID: 040
Revises: 039_fill_remaining_context
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '040_add_image_generation'
down_revision = '039_fill_remaining_context'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    """Check if a table exists in the database."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name}
    )
    return result.fetchone() is not None


def _column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]
    return column_name in columns


def upgrade():
    # Create generated_images table (skip if already exists from partial migration)
    if not _table_exists('generated_images'):
        op.create_table(
            'generated_images',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('story_id', sa.Integer(), nullable=False),
            sa.Column('branch_id', sa.Integer(), nullable=True),
            sa.Column('scene_id', sa.Integer(), nullable=True),
            sa.Column('character_id', sa.Integer(), nullable=True),
            sa.Column('image_type', sa.String(length=50), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('thumbnail_path', sa.String(length=500), nullable=True),
            sa.Column('prompt', sa.Text(), nullable=True),
            sa.Column('negative_prompt', sa.Text(), nullable=True),
            sa.Column('generation_params', sa.JSON(), nullable=True),
            sa.Column('width', sa.Integer(), nullable=True),
            sa.Column('height', sa.Integer(), nullable=True),
            sa.Column('provider', sa.String(length=50), server_default='comfyui', nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['branch_id'], ['story_branches.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for generated_images
        op.create_index(op.f('ix_generated_images_id'), 'generated_images', ['id'], unique=False)
        op.create_index(op.f('ix_generated_images_story_id'), 'generated_images', ['story_id'], unique=False)
        op.create_index(op.f('ix_generated_images_branch_id'), 'generated_images', ['branch_id'], unique=False)
        op.create_index(op.f('ix_generated_images_scene_id'), 'generated_images', ['scene_id'], unique=False)
        op.create_index(op.f('ix_generated_images_character_id'), 'generated_images', ['character_id'], unique=False)
        op.create_index('ix_generated_images_story_type', 'generated_images', ['story_id', 'image_type'], unique=False)

    # Add portrait_image_id to characters table (skip if already exists)
    if not _column_exists('characters', 'portrait_image_id'):
        with op.batch_alter_table('characters') as batch_op:
            batch_op.add_column(sa.Column('portrait_image_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_characters_portrait_image_id',
                'generated_images',
                ['portrait_image_id'], ['id'],
                ondelete='SET NULL'
            )

    # Add image generation settings to user_settings table
    image_columns = [
        ('image_gen_enabled', sa.Boolean()),
        ('comfyui_server_url', sa.String(length=500)),
        ('comfyui_api_key', sa.String(length=500)),
        ('comfyui_checkpoint', sa.String(length=200)),
        ('comfyui_model_type', sa.String(length=50)),
        ('image_gen_width', sa.Integer()),
        ('image_gen_height', sa.Integer()),
        ('image_gen_steps', sa.Integer()),
        ('image_gen_cfg_scale', sa.Float()),
        ('image_gen_default_style', sa.String(length=50)),
        ('use_extraction_llm_for_image_prompts', sa.Boolean()),
    ]
    for col_name, col_type in image_columns:
        if not _column_exists('user_settings', col_name):
            op.add_column('user_settings', sa.Column(col_name, col_type, nullable=True))


def downgrade():
    # Remove image generation settings from user_settings
    op.drop_column('user_settings', 'use_extraction_llm_for_image_prompts')
    op.drop_column('user_settings', 'image_gen_default_style')
    op.drop_column('user_settings', 'image_gen_cfg_scale')
    op.drop_column('user_settings', 'image_gen_steps')
    op.drop_column('user_settings', 'image_gen_height')
    op.drop_column('user_settings', 'image_gen_width')
    op.drop_column('user_settings', 'comfyui_model_type')
    op.drop_column('user_settings', 'comfyui_checkpoint')
    op.drop_column('user_settings', 'comfyui_api_key')
    op.drop_column('user_settings', 'comfyui_server_url')
    op.drop_column('user_settings', 'image_gen_enabled')

    # Remove portrait_image_id from characters (use batch mode for SQLite compatibility)
    with op.batch_alter_table('characters') as batch_op:
        batch_op.drop_constraint('fk_characters_portrait_image_id', type_='foreignkey')
        batch_op.drop_column('portrait_image_id')

    # Drop indexes for generated_images
    op.drop_index('ix_generated_images_story_type', table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_character_id'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_scene_id'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_branch_id'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_story_id'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_id'), table_name='generated_images')

    # Drop generated_images table
    op.drop_table('generated_images')
