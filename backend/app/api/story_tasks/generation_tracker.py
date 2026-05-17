"""
In-memory tracker for active scene generations.

Decouples LLM generation from the SSE stream so that if the client disconnects
(e.g. iOS Safari backgrounding the tab), the generation task continues running
and saves the scene to DB. A recovery endpoint lets the frontend retrieve the result.
"""
import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Key: "{user_id}:{story_id}"
_active_generations: Dict[str, "GenerationState"] = {}


@dataclass
class GenerationState:
    """Tracks the state of an in-flight scene generation."""
    task: Optional[asyncio.Task] = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=0))
    status: str = "generating"  # "generating" | "completed" | "error"
    scene_id: Optional[int] = None
    variant_id: Optional[int] = None
    choices: list = field(default_factory=list)
    content: str = ""  # Accumulated content (for recovery)
    chapter_id: Optional[int] = None
    auto_play: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


def _key(user_id: int, story_id: int) -> str:
    return f"{user_id}:{story_id}"


def register_generation(user_id: int, story_id: int) -> GenerationState:
    """Create and register a new generation state. Replaces any existing entry."""
    key = _key(user_id, story_id)
    old = _active_generations.get(key)
    if old and old.task and not old.task.done():
        logger.warning(f"[GEN_TRACKER] Replacing still-running generation for {key}")
    state = GenerationState()
    _active_generations[key] = state
    return state


def get_generation(user_id: int, story_id: int) -> Optional[GenerationState]:
    """Get the current generation state, if any."""
    return _active_generations.get(_key(user_id, story_id))


def remove_generation(user_id: int, story_id: int) -> None:
    """Remove a generation entry."""
    _active_generations.pop(_key(user_id, story_id), None)


def cleanup_stale_generations(max_age: float = 300.0) -> int:
    """Remove entries older than max_age seconds. Returns count removed."""
    now = time.time()
    stale_keys = [
        k for k, v in _active_generations.items()
        if (now - v.created_at) > max_age and v.status != "generating"
    ]
    # Also clean up very old generating entries (stuck tasks)
    stale_keys.extend(
        k for k, v in _active_generations.items()
        if (now - v.created_at) > max_age * 2 and k not in stale_keys
    )
    for k in stale_keys:
        _active_generations.pop(k, None)
    if stale_keys:
        logger.info(f"[GEN_TRACKER] Cleaned up {len(stale_keys)} stale generation entries")
    return len(stale_keys)
