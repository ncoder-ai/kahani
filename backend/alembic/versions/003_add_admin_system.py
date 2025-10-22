"""add admin system with user permissions and system settings

Revision ID: 003_add_admin_system
Revises: 002_add_semantic_memory_models
Create Date: 2025-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, Boolean, DateTime


# revision identifiers, used by Alembic.
revision = '003_add_admin_system'
down_revision = '002_add_semantic_memory_models'
branch_labels = None
depends_on = None


def upgrade():
    # Add new permission columns to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Admin approval system
        batch_op.add_column(sa.Column('is_approved', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('approved_by_id', sa.Integer(), nullable=True))
        
        # Content permissions
        batch_op.add_column(sa.Column('allow_nsfw', sa.Boolean(), nullable=False, server_default='0'))
        
        # Feature permissions
        batch_op.add_column(sa.Column('can_change_llm_provider', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('can_change_tts_settings', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('can_use_stt', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('can_use_image_generation', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('can_export_stories', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('can_import_stories', sa.Boolean(), nullable=False, server_default='1'))
        
        # Resource limits
        batch_op.add_column(sa.Column('max_stories', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_images_per_story', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_stt_minutes_per_month', sa.Integer(), nullable=True))
        
        # Add foreign key for approved_by_id
        batch_op.create_foreign_key('fk_users_approved_by', 'users', ['approved_by_id'], ['id'])
    
    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        
        # Default permissions
        sa.Column('default_allow_nsfw', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('default_can_change_llm_provider', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('default_can_change_tts_settings', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('default_can_use_stt', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('default_can_use_image_generation', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('default_can_export_stories', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('default_can_import_stories', sa.Boolean(), nullable=False, server_default='1'),
        
        # Default resource limits
        sa.Column('default_max_stories', sa.Integer(), nullable=True),
        sa.Column('default_max_images_per_story', sa.Integer(), nullable=True),
        sa.Column('default_max_stt_minutes_per_month', sa.Integer(), nullable=True),
        
        # Default LLM configuration
        sa.Column('default_llm_api_url', sa.String(500), nullable=True),
        sa.Column('default_llm_api_key', sa.String(500), nullable=True),
        sa.Column('default_llm_model_name', sa.String(200), nullable=True),
        sa.Column('default_llm_temperature', sa.Float(), nullable=False, server_default='0.7'),
        
        # Registration settings
        sa.Column('registration_requires_approval', sa.Boolean(), nullable=False, server_default='1'),
        
        # Metadata
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name='fk_system_settings_updated_by')
    )
    
    # Create default system_settings record (singleton)
    system_settings_table = table('system_settings',
        column('id', Integer),
        column('default_allow_nsfw', Boolean),
        column('default_can_change_llm_provider', Boolean),
        column('default_can_change_tts_settings', Boolean),
        column('default_can_use_stt', Boolean),
        column('default_can_use_image_generation', Boolean),
        column('default_can_export_stories', Boolean),
        column('default_can_import_stories', Boolean),
        column('default_llm_temperature', sa.Float),
        column('registration_requires_approval', Boolean),
    )
    
    op.bulk_insert(system_settings_table, [
        {
            'id': 1,
            'default_allow_nsfw': False,
            'default_can_change_llm_provider': True,
            'default_can_change_tts_settings': True,
            'default_can_use_stt': True,
            'default_can_use_image_generation': True,
            'default_can_export_stories': True,
            'default_can_import_stories': True,
            'default_llm_temperature': 0.7,
            'registration_requires_approval': True,
        }
    ])
    
    # Make first user (if exists) an admin and auto-approve them
    # This handles fresh installs where the first user becomes admin automatically
    connection = op.get_bind()
    
    # Get the first user by ID (lowest ID = first registered)
    result = connection.execute(sa.text("SELECT id FROM users ORDER BY id ASC LIMIT 1"))
    first_user = result.fetchone()
    
    if first_user:
        first_user_id = first_user[0]
        # Update first user to be admin, approved, and have all permissions
        connection.execute(
            sa.text("""
                UPDATE users 
                SET is_admin = 1,
                    is_approved = 1,
                    allow_nsfw = 1,
                    approved_at = CURRENT_TIMESTAMP
                WHERE id = :user_id
            """),
            {"user_id": first_user_id}
        )


def downgrade():
    # Drop system_settings table
    op.drop_table('system_settings')
    
    # Remove permission columns from users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_approved_by', type_='foreignkey')
        
        # Drop all new columns
        batch_op.drop_column('max_stt_minutes_per_month')
        batch_op.drop_column('max_images_per_story')
        batch_op.drop_column('max_stories')
        batch_op.drop_column('can_import_stories')
        batch_op.drop_column('can_export_stories')
        batch_op.drop_column('can_use_image_generation')
        batch_op.drop_column('can_use_stt')
        batch_op.drop_column('can_change_tts_settings')
        batch_op.drop_column('can_change_llm_provider')
        batch_op.drop_column('allow_nsfw')
        batch_op.drop_column('approved_by_id')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('is_approved')

