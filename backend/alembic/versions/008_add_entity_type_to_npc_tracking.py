"""add entity_type to npc_tracking

Revision ID: 008
Revises: 007
Create Date: 2025-01-XX

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add entity_type column to npc_tracking table"""
    
    # Check if column already exists (in case migration was partially run)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('npc_tracking')]
    
    if 'entity_type' not in columns:
        # SQLite doesn't support ALTER COLUMN ... SET NOT NULL
        # Add column as nullable (model has default='CHARACTER' for new rows)
        op.add_column('npc_tracking', sa.Column('entity_type', sa.String(length=50), nullable=True))
    
    # Set default value for all existing rows
    op.execute("UPDATE npc_tracking SET entity_type = 'CHARACTER' WHERE entity_type IS NULL")
    
    # Create index for entity_type (check if it exists first)
    indexes = [idx['name'] for idx in inspector.get_indexes('npc_tracking')]
    if 'idx_npc_tracking_entity_type' not in indexes:
        op.create_index('idx_npc_tracking_entity_type', 'npc_tracking', ['story_id', 'entity_type'])


def downgrade() -> None:
    """Remove entity_type column from npc_tracking table"""
    
    # Drop index
    op.drop_index('idx_npc_tracking_entity_type', table_name='npc_tracking')
    
    # Drop column
    op.drop_column('npc_tracking', 'entity_type')

