"""Helpers for loading the saved scene-gen prompt snapshot off a SceneVariant.

The snapshot is written by `UnifiedLLMService._save_prompt_snapshot` at the
end of every cache-friendly generation method and persisted on
`scene_variants.context_snapshot` by `SceneVariantServiceAdapter`. Reloading
it lets downstream LLM calls (variant regeneration, TTS segment polish, etc.)
replay the exact prefix that was sent during scene generation — giving near-
100% main-LLM KV cache hit.
"""
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def load_saved_messages_for_variant(variant_id: int) -> Optional[List[Dict[str, Any]]]:
    """Load the cache-friendly message list saved on `SceneVariant.context_snapshot`.

    Returns the full message list (prefix + the original scene-gen task as the
    final user message). Callers that want to reuse this as a *prefix* should
    drop the last message and append their own task.

    Returns None when the variant has no snapshot (legacy scenes pre-F1), the
    JSON is malformed, or the variant row does not exist.
    """
    from ...database import SessionLocal
    from ...models import SceneVariant

    db = SessionLocal()
    try:
        v = db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
        if not v or not v.context_snapshot:
            return None
        raw = json.loads(v.context_snapshot)
        if not isinstance(raw, dict) or raw.get("v") != 2:
            return None
        messages = raw.get("messages")
        if not isinstance(messages, list) or not messages:
            return None
        return messages
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse context_snapshot for variant {variant_id}: {e}")
        return None
    finally:
        db.close()
