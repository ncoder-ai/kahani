"""Add configured_providers column and backfill from existing settings

Revision ID: 075
Revises: 074
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers
revision = '075_configured_providers'
down_revision = '074_embedding_provider_settings'
branch_labels = None
depends_on = None


def _backfill_configured_providers(row) -> str:
    """Build configured_providers JSON from a user_settings row.

    Scans legacy columns + engine_settings/extraction_engine_settings JSON blobs
    to assemble the new unified provider registry.
    """
    providers: dict = {}

    def _ensure_provider(pid: str):
        if pid not in providers:
            providers[pid] = {}

    def _set_creds(pid: str, key: str, url: str):
        _ensure_provider(pid)
        # Prefer non-empty values (don't overwrite existing non-empty with empty)
        if key and not providers[pid].get("api_key"):
            providers[pid]["api_key"] = key
        if url and not providers[pid].get("api_url"):
            providers[pid]["api_url"] = url

    # --- Main LLM flat columns ---
    llm_provider = row.llm_api_type or ""
    if llm_provider:
        _set_creds(llm_provider, row.llm_api_key or "", row.llm_api_url or "")

    # --- Extraction flat columns ---
    ext_provider = row.extraction_model_api_type or ""
    if ext_provider:
        _set_creds(ext_provider, row.extraction_model_api_key or "", row.extraction_model_url or "")

    # --- Embedding flat columns ---
    emb_provider = row.embedding_provider or "local"
    if emb_provider and emb_provider != "local":
        _set_creds(emb_provider, row.embedding_api_key or "", row.embedding_api_url or "")

    # --- Parse engine_settings JSON (per-engine main LLM settings) ---
    engine_settings = {}
    if row.engine_settings:
        try:
            engine_settings = json.loads(row.engine_settings)
        except (json.JSONDecodeError, TypeError):
            pass

    for eng_id, eng_data in engine_settings.items():
        if not isinstance(eng_data, dict):
            continue
        _ensure_provider(eng_id)
        # Merge credentials
        eng_key = eng_data.get("api_key", "")
        eng_url = eng_data.get("api_url", "")
        _set_creds(eng_id, eng_key, eng_url)
        # Extract LLM role params
        llm_params = {}
        for field in ["model_name", "temperature", "top_p", "top_k",
                       "repetition_penalty", "max_tokens", "completion_mode",
                       "reasoning_effort", "thinking_model_type",
                       "thinking_enabled_generation", "text_completion_template",
                       "text_completion_preset"]:
            if field in eng_data and field not in ("api_key", "api_url", "api_type"):
                llm_params[field] = eng_data[field]
        if llm_params:
            providers[eng_id]["llm"] = llm_params

    # Include sampler_settings in the active LLM provider's role params
    if llm_provider and row.sampler_settings:
        try:
            sampler_data = json.loads(row.sampler_settings)
            if sampler_data:
                _ensure_provider(llm_provider)
                if "llm" not in providers[llm_provider]:
                    providers[llm_provider]["llm"] = {}
                providers[llm_provider]["llm"]["sampler_settings"] = sampler_data
        except (json.JSONDecodeError, TypeError):
            pass

    # --- Parse extraction_engine_settings JSON ---
    ext_engine_settings = {}
    if row.extraction_engine_settings:
        try:
            ext_engine_settings = json.loads(row.extraction_engine_settings)
        except (json.JSONDecodeError, TypeError):
            pass

    for eng_id, eng_data in ext_engine_settings.items():
        if not isinstance(eng_data, dict):
            continue
        _ensure_provider(eng_id)
        eng_key = eng_data.get("api_key", "")
        eng_url = eng_data.get("url", "") or eng_data.get("api_url", "")
        _set_creds(eng_id, eng_key, eng_url)
        # Extract extraction role params
        ext_params = {}
        for field in ["model_name", "temperature", "max_tokens", "top_p",
                       "repetition_penalty", "min_p", "thinking_disable_method",
                       "thinking_disable_custom", "thinking_enabled_extractions",
                       "thinking_enabled_memory"]:
            if field in eng_data and field not in ("api_key", "api_url", "url", "api_type"):
                ext_params[field] = eng_data[field]
        if ext_params:
            providers[eng_id]["extraction"] = ext_params

    # --- Embedding role params for the active embedding provider ---
    if emb_provider:
        _ensure_provider(emb_provider)
        emb_params = {}
        if row.embedding_model_name:
            emb_params["model_name"] = row.embedding_model_name
        if row.embedding_dimensions:
            emb_params["dimensions"] = row.embedding_dimensions
        if emb_params:
            providers[emb_provider]["embedding"] = emb_params

    # Always include local provider (for embedding)
    _ensure_provider("local")

    return json.dumps(providers)


def upgrade() -> None:
    # 1. Add column
    op.add_column('user_settings', sa.Column('configured_providers', sa.Text(), nullable=True))

    # 2. Backfill from existing data
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, llm_api_type, llm_api_key, llm_api_url, "
        "extraction_model_api_type, extraction_model_api_key, extraction_model_url, "
        "embedding_provider, embedding_api_key, embedding_api_url, "
        "embedding_model_name, embedding_dimensions, "
        "engine_settings, extraction_engine_settings, sampler_settings "
        "FROM user_settings"
    )).fetchall()

    for row in rows:
        try:
            configured = _backfill_configured_providers(row)
            conn.execute(
                sa.text("UPDATE user_settings SET configured_providers = :cp WHERE id = :id"),
                {"cp": configured, "id": row.id}
            )
        except Exception:
            # Skip problematic rows — they'll get populated on next settings save
            pass


def downgrade() -> None:
    op.drop_column('user_settings', 'configured_providers')
