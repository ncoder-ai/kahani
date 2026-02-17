"""Fix NULL branch_ids on entity states and deduplicate

Assigns branch_id to character_states, location_states, and object_states
that have NULL branch_id by looking up the scene's branch. Then deduplicates
records keeping the most recently created row per unique key.

Revision ID: 048_fix_entity_state_branches
Revises: 047_add_relationship_graph
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


revision = '048_fix_entity_state_branches'
down_revision = '047_add_relationship_graph'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # =========================================================================
    # STEP 1: Assign branch_id from the scene's branch
    # =========================================================================

    # 1a. character_states — join via story_id + last_updated_scene = sequence_number
    conn.execute(sa.text("""
        UPDATE character_states SET branch_id = (
            SELECT s.branch_id FROM scenes s
            WHERE s.story_id = character_states.story_id
              AND s.sequence_number = character_states.last_updated_scene
            LIMIT 1
        )
        WHERE branch_id IS NULL AND last_updated_scene IS NOT NULL
    """))

    # 1b. location_states
    conn.execute(sa.text("""
        UPDATE location_states SET branch_id = (
            SELECT s.branch_id FROM scenes s
            WHERE s.story_id = location_states.story_id
              AND s.sequence_number = location_states.last_updated_scene
            LIMIT 1
        )
        WHERE branch_id IS NULL AND last_updated_scene IS NOT NULL
    """))

    # 1c. object_states
    conn.execute(sa.text("""
        UPDATE object_states SET branch_id = (
            SELECT s.branch_id FROM scenes s
            WHERE s.story_id = object_states.story_id
              AND s.sequence_number = object_states.last_updated_scene
            LIMIT 1
        )
        WHERE branch_id IS NULL AND last_updated_scene IS NOT NULL
    """))

    # =========================================================================
    # STEP 1 FALLBACK: Assign remaining NULLs to the story's active branch,
    # then main branch as final fallback
    # =========================================================================

    for table in ['character_states', 'location_states', 'object_states']:
        # Try active branch first
        conn.execute(sa.text(f"""
            UPDATE {table} SET branch_id = (
                SELECT sb.id FROM story_branches sb
                WHERE sb.story_id = {table}.story_id
                  AND sb.is_active = true
                LIMIT 1
            )
            WHERE branch_id IS NULL
        """))

        # Then main branch for any still NULL
        conn.execute(sa.text(f"""
            UPDATE {table} SET branch_id = (
                SELECT sb.id FROM story_branches sb
                WHERE sb.story_id = {table}.story_id
                  AND sb.is_main = true
                LIMIT 1
            )
            WHERE branch_id IS NULL
        """))

    # =========================================================================
    # STEP 2: Deduplicate — keep the row with the highest id per unique key
    # =========================================================================

    # 2a. character_states: unique key = (character_id, story_id, branch_id)
    conn.execute(sa.text("""
        DELETE FROM character_states
        WHERE id NOT IN (
            SELECT MAX(id) FROM character_states
            GROUP BY character_id, story_id, branch_id
        )
    """))

    # 2b. location_states: unique key = (story_id, location_name, branch_id)
    conn.execute(sa.text("""
        DELETE FROM location_states
        WHERE id NOT IN (
            SELECT MAX(id) FROM location_states
            GROUP BY story_id, location_name, branch_id
        )
    """))

    # 2c. object_states: unique key = (story_id, object_name, branch_id)
    conn.execute(sa.text("""
        DELETE FROM object_states
        WHERE id NOT IN (
            SELECT MAX(id) FROM object_states
            GROUP BY story_id, object_name, branch_id
        )
    """))


def downgrade():
    # Data-only migration — cannot meaningfully reverse deleted duplicates
    # or restore original NULL branch_ids
    pass
