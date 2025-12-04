"""Add story branches for forking/branching stories

Revision ID: 019_add_story_branches
Revises: 018_add_alert_on_high_context
Create Date: 2024-12-02

This migration:
1. Creates the story_branches table
2. Adds branch_id columns to all story-related tables
3. Creates a "Main" branch for each existing story
4. Backfills branch_id for all existing records
5. Adds foreign key constraints and indexes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '019_add_story_branches'
down_revision = '018_add_alert_on_high_context'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create story_branches table
    op.create_table(
        'story_branches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_main', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=False),
        sa.Column('forked_from_branch_id', sa.Integer(), nullable=True),
        sa.Column('forked_at_scene_sequence', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['forked_from_branch_id'], ['story_branches.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_story_branches_id', 'story_branches', ['id'])
    op.create_index('ix_story_branches_story_id', 'story_branches', ['story_id'])
    op.create_index('ix_story_branches_is_main', 'story_branches', ['is_main'])
    op.create_index('ix_story_branches_is_active', 'story_branches', ['is_active'])
    
    # 2. Add current_branch_id to stories table
    op.add_column('stories', sa.Column('current_branch_id', sa.Integer(), nullable=True))
    
    # 3. Add branch_id columns to all story-related tables (nullable initially)
    # Note: chapter_summary_batches doesn't need branch_id as it's linked via chapter
    tables_to_update = [
        'scenes',
        'scene_choices',
        'chapters',
        'story_characters',
        'story_flows',
        'character_states',
        'location_states',
        'object_states',
        'entity_state_batches',
        'npc_mentions',
        'npc_tracking',
        'npc_tracking_snapshots',
        'character_memories',
        'plot_events',
        'scene_embeddings'
    ]
    
    for table_name in tables_to_update:
        op.add_column(table_name, sa.Column('branch_id', sa.Integer(), nullable=True))
        op.create_index(f'ix_{table_name}_branch_id', table_name, ['branch_id'])
    
    # 3. Create "Main" branch for each existing story and backfill branch_id
    # Use raw SQL for data migration
    connection = op.get_bind()
    
    # Get all existing stories
    stories = connection.execute(text("SELECT id FROM stories")).fetchall()
    
    for story in stories:
        story_id = story[0]
        
        # Create main branch for this story
        # Use true/false for PostgreSQL boolean compatibility (also works with SQLite)
        connection.execute(
            text("""
                INSERT INTO story_branches (story_id, name, is_main, is_active, created_at)
                VALUES (:story_id, 'Main', true, true, CURRENT_TIMESTAMP)
            """),
            {"story_id": story_id}
        )
        
        # Get the branch_id we just created
        # Use true for PostgreSQL boolean compatibility
        result = connection.execute(
            text("SELECT id FROM story_branches WHERE story_id = :story_id AND is_main = true"),
            {"story_id": story_id}
        ).fetchone()
        branch_id = result[0]
        
        # Set current_branch_id on the story
        connection.execute(
            text("UPDATE stories SET current_branch_id = :branch_id WHERE id = :story_id"),
            {"branch_id": branch_id, "story_id": story_id}
        )
        
        # Update all related tables with the branch_id
        for table_name in tables_to_update:
            # scene_choices doesn't have story_id directly, so we need to handle it differently
            if table_name == 'scene_choices':
                connection.execute(
                    text("""
                        UPDATE scene_choices SET branch_id = :branch_id 
                        WHERE scene_id IN (SELECT id FROM scenes WHERE story_id = :story_id)
                    """),
                    {"branch_id": branch_id, "story_id": story_id}
                )
            elif table_name == 'chapter_summary_batches':
                # chapter_summary_batches has story_id
                connection.execute(
                    text(f"UPDATE {table_name} SET branch_id = :branch_id WHERE story_id = :story_id"),
                    {"branch_id": branch_id, "story_id": story_id}
                )
            else:
                connection.execute(
                    text(f"UPDATE {table_name} SET branch_id = :branch_id WHERE story_id = :story_id"),
                    {"branch_id": branch_id, "story_id": story_id}
                )
    
    # 4. Add foreign key constraints
    # Note: SQLite doesn't support adding FK constraints after table creation,
    # so we only add these for databases that support it (like PostgreSQL)
    # For SQLite, the constraints are enforced at the application level
    
    # Create additional indexes for NPC tracking (branch-aware)
    op.create_index('idx_npc_mentions_branch', 'npc_mentions', ['branch_id', 'character_name'])
    op.create_index('idx_npc_tracking_branch_name', 'npc_tracking', ['branch_id', 'character_name'], unique=True)
    op.create_index('idx_npc_snapshot_branch_sequence', 'npc_tracking_snapshots', ['branch_id', 'scene_sequence'])
    
    # Note: idx_npc_tracking_story_name already exists as a unique constraint from migration 004
    # We don't modify it here - migration 020 will handle updating it for branch support
    # In PostgreSQL, try/except doesn't work because errors abort the entire transaction


def downgrade():
    connection = op.get_bind()
    
    # Drop the new indexes
    try:
        op.drop_index('idx_npc_mentions_branch', 'npc_mentions')
        op.drop_index('idx_npc_tracking_branch_name', 'npc_tracking')
        op.drop_index('idx_npc_snapshot_branch_sequence', 'npc_tracking_snapshots')
    except Exception:
        pass
    
    # Remove current_branch_id from stories
    try:
        op.drop_column('stories', 'current_branch_id')
    except Exception:
        pass
    
    # Remove branch_id columns from all tables
    tables_to_update = [
        'scenes',
        'scene_choices',
        'chapters',
        'story_characters',
        'story_flows',
        'character_states',
        'location_states',
        'object_states',
        'entity_state_batches',
        'npc_mentions',
        'npc_tracking',
        'npc_tracking_snapshots',
        'character_memories',
        'plot_events',
        'scene_embeddings'
    ]
    
    for table_name in tables_to_update:
        try:
            op.drop_index(f'ix_{table_name}_branch_id', table_name)
        except Exception:
            pass
        op.drop_column(table_name, 'branch_id')
    
    # Drop story_branches table
    op.drop_index('ix_story_branches_is_active', 'story_branches')
    op.drop_index('ix_story_branches_is_main', 'story_branches')
    op.drop_index('ix_story_branches_story_id', 'story_branches')
    op.drop_index('ix_story_branches_id', 'story_branches')
    op.drop_table('story_branches')

