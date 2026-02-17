"""Fix ALL remaining NULL branch_ids across all tables

This migration assigns the main branch ID to all records with branch_id=NULL
across all branch-aware tables. It completes the migration started in 048.

Tables affected:
- scene_choices (via scene -> story)
- plot_events
- character_memories
- npc_mentions
- npc_tracking
- npc_tracking_snapshots
- story_characters
- entity_state_batches
- character_interactions
- scene_embeddings
- story_flows
- chapters
- scenes
- contradictions
- working_memory
- character_relationships
- relationship_summaries
- generated_images

Revision ID: 050_fix_all_null_branch_ids
Revises: 049_add_contradiction_injection_settings
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa


revision = '050_fix_all_null_branch_ids'
down_revision = '049_contradiction_injection'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # =========================================================================
    # Tables with direct story_id column - assign main branch
    # =========================================================================

    tables_with_story_id = [
        'plot_events',
        'character_memories',
        'npc_mentions',
        'npc_tracking',
        'npc_tracking_snapshots',
        'story_characters',
        'entity_state_batches',
        'character_interactions',
        'scene_embeddings',
        'story_flows',
        'chapters',
        'scenes',
        'contradictions',
        'working_memory',
        'character_relationships',
        'relationship_summaries',
        'generated_images',
        # Also re-run for entity states in case any were missed
        'character_states',
        'location_states',
        'object_states',
    ]

    for table in tables_with_story_id:
        # Check if table exists and has story_id column
        result = conn.execute(sa.text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = 'story_id'
        """)).fetchone()

        if result:
            print(f"Fixing {table}...")
            # Update NULL branch_ids to the main branch for that story
            conn.execute(sa.text(f"""
                UPDATE {table} SET branch_id = (
                    SELECT sb.id FROM story_branches sb
                    WHERE sb.story_id = {table}.story_id
                      AND sb.is_main = true
                    LIMIT 1
                )
                WHERE branch_id IS NULL
            """))

            # Count remaining NULLs
            count = conn.execute(sa.text(f"""
                SELECT COUNT(*) FROM {table} WHERE branch_id IS NULL
            """)).scalar()
            if count > 0:
                print(f"  WARNING: {count} records in {table} still have NULL branch_id (story may lack main branch)")

    # =========================================================================
    # scene_choices - needs to go through scenes to get story_id
    # =========================================================================

    print("Fixing scene_choices...")
    conn.execute(sa.text("""
        UPDATE scene_choices SET branch_id = (
            SELECT sb.id FROM story_branches sb
            JOIN scenes s ON s.story_id = sb.story_id AND sb.is_main = true
            WHERE s.id = scene_choices.scene_id
            LIMIT 1
        )
        WHERE branch_id IS NULL
    """))

    # Check for remaining NULLs in scene_choices
    count = conn.execute(sa.text("""
        SELECT COUNT(*) FROM scene_choices WHERE branch_id IS NULL
    """)).scalar()
    if count > 0:
        print(f"  WARNING: {count} scene_choices still have NULL branch_id")

    # =========================================================================
    # Verification: Report final NULL counts
    # =========================================================================

    print("\n=== Final NULL branch_id counts ===")
    all_tables = tables_with_story_id + ['scene_choices']
    for table in all_tables:
        try:
            count = conn.execute(sa.text(f"""
                SELECT COUNT(*) FROM {table} WHERE branch_id IS NULL
            """)).scalar()
            status = "OK" if count == 0 else f"WARNING: {count} NULLs remain"
            print(f"  {table}: {status}")
        except Exception as e:
            print(f"  {table}: SKIP (error: {e})")


def downgrade():
    # Data-only migration — cannot meaningfully restore original NULL branch_ids
    # The NULL values were inconsistent anyway
    pass
