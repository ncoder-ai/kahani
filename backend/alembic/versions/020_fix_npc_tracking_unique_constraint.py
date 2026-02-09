"""Fix NPC tracking unique constraint to include branch_id

Revision ID: 020_fix_npc_unique
Revises: 019_add_story_branches
Create Date: 2024-12-03

The original unique constraint on npc_tracking was (story_id, character_name),
but with story branching, we need (story_id, branch_id, character_name) to allow
the same character to exist in different branches.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020_fix_npc_unique'
down_revision = '019_add_story_branches'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # For SQLite, we need to recreate the table to change constraints
    # First, check if the constraint exists and drop it
    
    # Get connection
    connection = op.get_bind()
    
    # Check if we're using SQLite
    if connection.dialect.name == 'sqlite':
        # SQLite doesn't support ALTER TABLE to drop constraints
        # We need to recreate the table
        
        # Create a new table WITHOUT the problematic UNIQUE constraint
        # We'll use partial unique indexes instead to handle NULL branch_id correctly
        op.execute("""
            CREATE TABLE npc_tracking_new (
                id INTEGER PRIMARY KEY,
                story_id INTEGER NOT NULL,
                branch_id INTEGER,
                character_name VARCHAR(255) NOT NULL,
                entity_type VARCHAR(50) DEFAULT 'CHARACTER',
                total_mentions INTEGER DEFAULT 0,
                scene_count INTEGER DEFAULT 0,
                first_appearance_scene INTEGER,
                last_appearance_scene INTEGER,
                has_dialogue_count INTEGER DEFAULT 0,
                has_actions_count INTEGER DEFAULT 0,
                significance_score FLOAT DEFAULT 0.0,
                importance_score FLOAT DEFAULT 0.0,
                frequency_score FLOAT DEFAULT 0.0,
                extracted_profile TEXT,
                crossed_threshold BOOLEAN DEFAULT 0,
                user_prompted BOOLEAN DEFAULT 0,
                profile_extracted BOOLEAN DEFAULT 0,
                converted_to_character BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                last_calculated DATETIME DEFAULT (CURRENT_TIMESTAMP),
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE
            )
        """)
        
        # Copy data from old table to new
        op.execute("""
            INSERT INTO npc_tracking_new 
            SELECT id, story_id, branch_id, character_name, entity_type,
                   total_mentions, scene_count, first_appearance_scene, last_appearance_scene,
                   has_dialogue_count, has_actions_count, significance_score, importance_score,
                   frequency_score, extracted_profile, crossed_threshold, user_prompted,
                   profile_extracted, converted_to_character, created_at, last_calculated
            FROM npc_tracking
        """)
        
        # Drop old table
        op.execute("DROP TABLE npc_tracking")
        
        # Rename new table
        op.execute("ALTER TABLE npc_tracking_new RENAME TO npc_tracking")
        
        # Recreate indexes
        op.create_index('ix_npc_tracking_story_id', 'npc_tracking', ['story_id'])
        op.create_index('ix_npc_tracking_character_name', 'npc_tracking', ['character_name'])
        op.create_index('ix_npc_tracking_importance_score', 'npc_tracking', ['importance_score'])
        op.create_index('ix_npc_tracking_branch_id', 'npc_tracking', ['branch_id'])
        
        # Create partial unique indexes to handle NULL branch_id correctly
        # For rows with branch_id IS NOT NULL: enforce (story_id, branch_id, character_name) uniqueness
        op.execute("""
            CREATE UNIQUE INDEX idx_npc_tracking_story_branch_name_not_null
            ON npc_tracking(story_id, branch_id, character_name)
            WHERE branch_id IS NOT NULL
        """)
        
        # For rows with branch_id IS NULL: enforce (story_id, character_name) uniqueness
        op.execute("""
            CREATE UNIQUE INDEX idx_npc_tracking_story_name_null_branch
            ON npc_tracking(story_id, character_name)
            WHERE branch_id IS NULL
        """)
    else:
        # For PostgreSQL, use partial unique constraints to handle NULL branch_id correctly
        # Drop the old constraint if it exists
        try:
            op.drop_constraint('idx_npc_tracking_story_name', 'npc_tracking', type_='unique')
        except Exception:
            # Constraint might not exist, that's okay
            pass
        
        # Create partial unique index for rows with branch_id IS NOT NULL
        # This enforces (story_id, branch_id, character_name) uniqueness when branch_id is not NULL
        op.execute("""
            CREATE UNIQUE INDEX idx_npc_tracking_story_branch_name_not_null
            ON npc_tracking(story_id, branch_id, character_name)
            WHERE branch_id IS NOT NULL
        """)
        
        # Create partial unique index for rows with branch_id IS NULL
        # This enforces (story_id, character_name) uniqueness when branch_id is NULL
        op.execute("""
            CREATE UNIQUE INDEX idx_npc_tracking_story_name_null_branch
            ON npc_tracking(story_id, character_name)
            WHERE branch_id IS NULL
        """)


def downgrade() -> None:
    connection = op.get_bind()
    
    if connection.dialect.name == 'sqlite':
        # Recreate table with original constraint
        op.execute("""
            CREATE TABLE npc_tracking_new (
                id INTEGER PRIMARY KEY,
                story_id INTEGER NOT NULL,
                branch_id INTEGER,
                character_name VARCHAR(255) NOT NULL,
                entity_type VARCHAR(50) DEFAULT 'CHARACTER',
                total_mentions INTEGER DEFAULT 0,
                scene_count INTEGER DEFAULT 0,
                first_appearance_scene INTEGER,
                last_appearance_scene INTEGER,
                has_dialogue_count INTEGER DEFAULT 0,
                has_actions_count INTEGER DEFAULT 0,
                significance_score FLOAT DEFAULT 0.0,
                importance_score FLOAT DEFAULT 0.0,
                frequency_score FLOAT DEFAULT 0.0,
                extracted_profile TEXT,
                crossed_threshold BOOLEAN DEFAULT 0,
                user_prompted BOOLEAN DEFAULT 0,
                profile_extracted BOOLEAN DEFAULT 0,
                converted_to_character BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                last_calculated DATETIME DEFAULT (CURRENT_TIMESTAMP),
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE,
                UNIQUE (story_id, character_name)
            )
        """)
        
        op.execute("""
            INSERT INTO npc_tracking_new 
            SELECT id, story_id, branch_id, character_name, entity_type,
                   total_mentions, scene_count, first_appearance_scene, last_appearance_scene,
                   has_dialogue_count, has_actions_count, significance_score, importance_score,
                   frequency_score, extracted_profile, crossed_threshold, user_prompted,
                   profile_extracted, converted_to_character, created_at, last_calculated
            FROM npc_tracking
        """)
        
        op.execute("DROP TABLE npc_tracking")
        op.execute("ALTER TABLE npc_tracking_new RENAME TO npc_tracking")
        
        op.create_index('ix_npc_tracking_story_id', 'npc_tracking', ['story_id'])
        op.create_index('ix_npc_tracking_character_name', 'npc_tracking', ['character_name'])
        op.create_index('ix_npc_tracking_importance_score', 'npc_tracking', ['importance_score'])
        op.create_index('ix_npc_tracking_branch_id', 'npc_tracking', ['branch_id'])  # Recreate index from migration 019
        # Note: The UNIQUE constraint on (story_id, character_name) is already in the table definition above
    else:
        # Drop the partial unique indexes
        try:
            op.execute("DROP INDEX IF EXISTS idx_npc_tracking_story_branch_name_not_null")
            op.execute("DROP INDEX IF EXISTS idx_npc_tracking_story_name_null_branch")
        except Exception:
            # Indexes might not exist, that's okay
            pass
        
        # Recreate the original unique constraint
        op.create_unique_constraint(
            'idx_npc_tracking_story_name', 
            'npc_tracking', 
            ['story_id', 'character_name']
        )

