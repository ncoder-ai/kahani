"""Add llm/extraction/embedding provider_id columns for multi-instance support

Adds three nullable VARCHAR columns to user_settings that store the active
provider's slug into configured_providers. Lets users have multiple
providers of the same api_type (e.g. two openai-compatible local engines)
selected independently per role.

Backwards-compat: existing rows have these as NULL. The model resolver
falls back to the legacy api_type fields when provider_id is NULL, so
existing single-provider setups continue to work transparently. No data
migration is required for behavior — but as a convenience we backfill
provider_id from the existing api_type when a matching configured_providers
entry exists, so the new code path is exercised from day one.

Revision ID: 083
Revises: 082_use_whole_scene
Create Date: 2026-05-02
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '083_provider_id'
down_revision = '082_use_whole_scene'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_settings',
        sa.Column('llm_provider_id', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'user_settings',
        sa.Column('extraction_provider_id', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'user_settings',
        sa.Column('embedding_provider_id', sa.String(length=100), nullable=True),
    )

    # Best-effort backfill: for each row, set <role>_provider_id = <role legacy api_type>
    # when configured_providers actually contains an entry for that key. This
    # makes the new code path immediately active for existing users without
    # changing any behavior — they just start being identified by slug instead
    # of by api_type.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, llm_api_type, extraction_model_api_type, embedding_provider, "
        "configured_providers FROM user_settings"
    )).fetchall()
    for row in rows:
        try:
            cp = json.loads(row.configured_providers) if row.configured_providers else {}
        except (json.JSONDecodeError, TypeError):
            cp = {}
        updates = {}
        if row.llm_api_type and row.llm_api_type in cp:
            updates['llm_provider_id'] = row.llm_api_type
        if row.extraction_model_api_type and row.extraction_model_api_type in cp:
            updates['extraction_provider_id'] = row.extraction_model_api_type
        if row.embedding_provider and row.embedding_provider in cp:
            updates['embedding_provider_id'] = row.embedding_provider
        if updates:
            set_clause = ', '.join(f"{k} = :{k}" for k in updates)
            conn.execute(
                sa.text(f"UPDATE user_settings SET {set_clause} WHERE id = :id"),
                {**updates, 'id': row.id},
            )


def downgrade() -> None:
    op.drop_column('user_settings', 'embedding_provider_id')
    op.drop_column('user_settings', 'extraction_provider_id')
    op.drop_column('user_settings', 'llm_provider_id')
