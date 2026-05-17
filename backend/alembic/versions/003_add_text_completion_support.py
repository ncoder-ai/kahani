"""add text completion support

Revision ID: 003
Revises: 002
Create Date: 2025-10-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add text completion support columns to user_settings table"""
    
    # Add completion_mode column (default to 'chat' for backwards compatibility)
    op.add_column('user_settings', 
        sa.Column('completion_mode', sa.String(20), nullable=False, server_default='chat')
    )
    
    # Add text_completion_template column (stores JSON template configuration)
    op.add_column('user_settings',
        sa.Column('text_completion_template', sa.Text(), nullable=True)
    )
    
    # Add text_completion_preset column (stores selected preset name)
    op.add_column('user_settings',
        sa.Column('text_completion_preset', sa.String(50), nullable=False, server_default='llama3')
    )


def downgrade() -> None:
    """Remove text completion support columns from user_settings table"""
    
    op.drop_column('user_settings', 'text_completion_preset')
    op.drop_column('user_settings', 'text_completion_template')
    op.drop_column('user_settings', 'completion_mode')

