"""Add color theme support

Revision ID: 007
Revises: 006
Create Date: 2025-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None

def upgrade():
    # For SQLite, we need to create a new table and copy data
    # First, add the new column
    op.add_column('user_settings', sa.Column('color_theme', sa.String(30), default='pure-dark'))
    
    # Copy existing theme values to color_theme
    op.execute("UPDATE user_settings SET color_theme = 'pure-dark' WHERE theme = 'dark'")
    op.execute("UPDATE user_settings SET color_theme = 'pure-dark' WHERE theme = 'light'")
    op.execute("UPDATE user_settings SET color_theme = 'pure-dark' WHERE theme = 'auto'")
    
    # Drop the old theme column
    op.drop_column('user_settings', 'theme')

def downgrade():
    # Add back the theme column
    op.add_column('user_settings', sa.Column('theme', sa.String(20), default='dark'))
    
    # Copy color_theme back to theme (simplified - all become 'dark')
    op.execute("UPDATE user_settings SET theme = 'dark'")
    
    # Drop the color_theme column
    op.drop_column('user_settings', 'color_theme')
