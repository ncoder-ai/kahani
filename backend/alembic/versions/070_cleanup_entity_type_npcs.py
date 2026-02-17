"""Delete non-CHARACTER entity_type rows from npc_tracking and npc_mentions

Revision ID: 070_cleanup_entity_type_npcs
Revises: 069_add_world_id_to_embeddings
Create Date: 2026-02-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '070_cleanup_entity_type_npcs'
down_revision = '069_world_id_embeddings'
branch_labels = None
depends_on = None


def upgrade():
    # Delete npc_mentions for non-CHARACTER NPCs (linked by story_id + character_name)
    op.execute("""
        DELETE FROM npc_mentions
        WHERE (story_id, character_name) IN (
            SELECT story_id, character_name FROM npc_tracking
            WHERE entity_type IS NOT NULL AND entity_type != 'CHARACTER'
        )
    """)

    # Delete non-CHARACTER NPC tracking rows
    op.execute("""
        DELETE FROM npc_tracking
        WHERE entity_type IS NOT NULL AND entity_type != 'CHARACTER'
    """)


def downgrade():
    # Data deletion is not reversible
    pass
