"""Scene segment extraction for multi-voice TTS playback.

Splits a generated scene into ordered per-speaker segments
[{speaker, text, emotion}, ...] using the configured extraction LLM.
The TTS pipeline then dispatches each segment with the matching
character's voice and the segment's emotion as a per-utterance
`instructions` hint (Qwen3-TTS and similar).

Design notes (mirrors chronicle_extraction_service patterns):
- Single LLM call per scene; result cached on SceneVariant.tts_segments
  so subsequent plays skip the call.
- Falls back to a single-narrator segment list on any failure (parse
  error, LLM down, malformed schema). The caller decides whether to
  proceed with multi-voice or fall back to the legacy text-chunker.
- Emits a debug log to logs/tts_segment_extraction.json for the most
  recent extraction (overwrites — same convention as chronicle).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .llm.extraction_service import extract_json_robust
from .llm.prompts import prompt_manager
from .llm.service import UnifiedLLMService

logger = logging.getLogger(__name__)


# In-flight extraction tracking. The key is the variant_id; the value
# is an asyncio.Event that gets set when the cache write completes (or
# when the extraction fails). The TTS playback path calls
# `wait_for_in_flight` before kicking off its own lazy extraction so we
# don't duplicate the LLM call when a background task is already running
# for the same variant.
_in_flight: Dict[int, asyncio.Event] = {}
_in_flight_lock = asyncio.Lock()


async def wait_for_in_flight(variant_id: int, timeout: float = 25.0) -> bool:
    """Block until any in-flight extraction for `variant_id` finishes.

    Returns True if there was an in-flight extraction (caller should
    re-read the cache after this returns), False if there wasn't.
    Times out cleanly so the lazy path can fall through to its own
    extraction call rather than hang indefinitely.
    """
    async with _in_flight_lock:
        event = _in_flight.get(variant_id)
    if event is None:
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(f"[TTS_SEGMENT] wait_for_in_flight timed out for variant {variant_id}")
        return True  # caller should still re-read cache before falling through


def _debug_log_path() -> str:
    """Mirror the path strategy used elsewhere (Docker /app vs baremetal)."""
    if os.path.exists("/app") and os.getcwd().startswith("/app"):
        return "/app/root_logs/tts_segment_extraction.json"
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return os.path.join(logs_dir, "tts_segment_extraction.json")


def _write_debug(payload: dict) -> None:
    try:
        with open(_debug_log_path(), "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
    except Exception as e:
        logger.warning(f"[TTS_SEGMENT] Could not write debug log: {e}")


def _fallback_segments(scene_text: str) -> List[Dict[str, Any]]:
    """Single narrator segment — preserves the scene as-is when extraction fails."""
    return [{
        "speaker": "narrator",
        "text": scene_text.strip(),
        "emotion": None,
    }]


def _resolve_speaker(raw: str, name_index: Dict[str, str]) -> Optional[str]:
    """Resolve a speaker name returned by the LLM to its canonical cast name.

    `name_index` maps each lookup variant (full name, first name, last
    name — all lowercased) → the canonical display name. The LLM
    sometimes uses just the first name even when the cast list has the
    full name, so we accept any of those resolutions before giving up.
    Returns None if no match (caller coerces to narrator).
    """
    key = (raw or "").strip().lower()
    if not key:
        return None
    # Trim parenthesised role suffixes the LLM occasionally tacks on.
    if "(" in key:
        key = key.split("(", 1)[0].strip()
    return name_index.get(key)


def _validate_segment(seg: Any, name_index: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Coerce one raw segment into the canonical shape, dropping junk."""
    if not isinstance(seg, dict):
        return None
    speaker = seg.get("speaker")
    text = seg.get("text")
    emotion = seg.get("emotion")
    if not isinstance(speaker, str) or not isinstance(text, str):
        return None
    speaker = speaker.strip()
    text = text.strip()
    if not text:
        return None
    if not speaker or speaker.lower() == "narrator":
        canonical_speaker = "narrator"
    else:
        resolved = _resolve_speaker(speaker, name_index)
        if resolved is None:
            logger.info(f"[TTS_SEGMENT] Unknown speaker '{speaker}' — coercing to narrator")
            canonical_speaker = "narrator"
            emotion = None
        else:
            canonical_speaker = resolved
    if emotion is not None and not isinstance(emotion, str):
        emotion = None
    if isinstance(emotion, str):
        emotion = emotion.strip() or None
    return {"speaker": canonical_speaker, "text": text, "emotion": emotion}


def _build_name_index(cast: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build lookup index: every reasonable variant of a cast name →
    the canonical display name. Includes:
      - full name (canonical)
      - first token only (e.g. "Marcus" → "Marcus Reed")
      - last token only (e.g. "Reed" → "Marcus Reed")
    Conflicts: first/last-name aliases with multiple matches are dropped
    (ambiguity → fall back to narrator rather than guessing wrong).
    """
    index: Dict[str, str] = {}
    alias_counts: Dict[str, int] = {}
    canonical_names: List[str] = []
    for c in cast or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        if name.lower() in {n.lower() for n in canonical_names}:
            continue  # dedupe
        canonical_names.append(name)
        index[name.lower()] = name  # full
        tokens = name.split()
        if len(tokens) >= 2:
            for variant in (tokens[0], tokens[-1]):
                v = variant.lower()
                if v == name.lower():
                    continue
                alias_counts[v] = alias_counts.get(v, 0) + 1
                if v not in index:
                    index[v] = name
    # Drop ambiguous aliases (two characters share a first or last name).
    for alias, count in alias_counts.items():
        if count > 1 and alias in index and index[alias].lower() != alias:
            logger.info(f"[TTS_SEGMENT] Dropping ambiguous name alias '{alias}'")
            del index[alias]
    return index


def _build_polish_messages(
    polish_prompt: str,
    force_main_llm: bool,
    use_cache: bool,
    variant_id: Optional[int],
) -> List[Dict[str, Any]]:
    """Assemble the message payload for the TTS polish LLM call.

    When routing to the main LLM AND the user has cache-friendly prompts
    enabled AND the scene variant has a saved `context_snapshot` from scene
    generation, we replay the saved prefix (dropping its final task message)
    and append our TTS-polish task. This gives near-100% KV cache hit on the
    main LLM since the scene-gen prefix is still hot in the cache.

    Otherwise (extraction LLM target, cache disabled, no variant_id, or
    legacy scene with NULL snapshot) we fall back to the bare single-message
    form — correct for Ministral's strict template, and the only viable form
    when no saved prefix exists.
    """
    bare: List[Dict[str, Any]] = [{"role": "user", "content": polish_prompt}]
    if not (force_main_llm and use_cache and variant_id):
        return bare
    try:
        from .llm.context_snapshot import load_saved_messages_for_variant
        saved = load_saved_messages_for_variant(variant_id)
        if not saved or len(saved) < 2:
            return bare
        prefix = saved[:-1]  # drop the original scene-gen task
        prefix.append({"role": "user", "content": polish_prompt})
        logger.info(
            f"[TTS_SEGMENT] Cache-friendly polish: reusing variant {variant_id} "
            f"snapshot ({len(prefix)} messages incl. polish task)"
        )
        return prefix
    except Exception as e:
        logger.warning(
            f"[TTS_SEGMENT] Could not load snapshot for variant {variant_id}: {e}; "
            f"falling back to bare prompt"
        )
        return bare


async def extract_scene_segments(
    scene_text: str,
    cast: List[Dict[str, Any]],
    user_id: int,
    user_settings: Dict[str, Any],
    force_main_llm: bool = False,
    gender_hints: Optional[Dict[str, str]] = None,
    variant_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Split `scene_text` into per-speaker segments via the v2 pipeline.

    Stage 1 (code, ~1ms): regex-extract dialogue + thought spans from
    the source for 100% verbatim integrity. Detect tag-name speakers
    ("Mira said"), pronoun-tag speakers ("she said" + gender map), and
    verb-cued emotions ("whispered", "shouted").

    Stage 2 (LLM, ~3-12s): one targeted call. The LLM gets the full
    scene + numbered list of dialogues/thoughts + code's hints, and
    returns indexed verdicts (speaker, emotion) plus a scene_mood for
    narrator default. Override-friendly — code hints are starting points,
    LLM has full context.

    Stage 3 (code merge, <10ms): apply LLM verdicts on top of code's
    deterministic skeleton. Narrator segments get scene_mood as default
    emotion. Returns canonical [{speaker, text, emotion}, ...] dicts —
    the same shape every TTS dispatch path consumes.

    On any LLM failure: falls back to the code-only verdicts (still
    correct, just less expressive emotion). On total failure: returns a
    single narrator segment covering the whole scene — never silently
    truncates content.
    """
    scene_text = scene_text or ""
    scene_text_stripped = scene_text.strip()
    if not scene_text_stripped:
        return []

    cast_names = [(c.get("name") or "").strip() for c in (cast or []) if c]
    cast_names = [n for n in cast_names if n]

    started = datetime.now(timezone.utc)
    import time as _time
    t0 = _time.monotonic()

    # ---- Stage 1: deterministic extraction ----
    try:
        from .tts.segment_extraction_v2 import (
            run_code_stage,
            build_polish_prompt,
            parse_polish_response,
            merge_verdicts,
            fix_split_quotes,
            gender_consistency_unset,
            to_canonical_segments,
        )
        v2_segments, gender_map, code_pov, item_indices = run_code_stage(
            scene_text, cast_names,
        )
    except Exception as e:
        logger.error(f"[TTS_SEGMENT] v2 code stage crashed: {e}", exc_info=True)
        return _fallback_segments(scene_text_stripped)

    # Apply authoritative DB gender hints on top of pronoun-window
    # inference. The DB column is high-confidence; per-scene pronoun
    # inference is a fallback for cast members whose `Character.gender`
    # is null.
    if gender_hints:
        for n, g in gender_hints.items():
            if g in ("m", "f"):
                gender_map[n] = g
    confident_genders: set = set((gender_hints or {}).keys())

    code_elapsed = _time.monotonic() - t0
    logger.info(
        f"[TTS_SEGMENT] v2 code stage: {code_elapsed*1000:.0f}ms, "
        f"segments={len(v2_segments)}, items_to_classify={len(item_indices)}"
    )

    # ---- Stage 2: LLM polish (skipped if no items to classify) ----
    llm_meta: Dict[str, Any] = {}
    llm_elapsed = 0.0
    if item_indices:
        prompt = build_polish_prompt(
            scene_text, cast_names, gender_map, v2_segments, item_indices,
        )
        # Build the message payload. When the polish call routes to the main
        # LLM AND the user has cache-friendly prompts enabled, try to reuse
        # the variant's saved scene-gen prompt as the cache prefix — that gives
        # near-100% cache hit on the prefix. Fallback to bare prompt if the
        # variant has no saved snapshot (legacy scenes pre-F1) or if we're
        # routing to the extraction LLM (Ministral can't handle multi-message).
        messages = _build_polish_messages(
            polish_prompt=prompt,
            force_main_llm=force_main_llm,
            use_cache=user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True),
            variant_id=variant_id,
        )
        t1 = _time.monotonic()
        try:
            llm_service = UnifiedLLMService()
            from .llm.prompts import prompt_manager as _pm
            polish_max_tokens = _pm.get_max_tokens("tts_polish", user_settings)
            raw_response = await llm_service.generate_for_task(
                messages=messages,
                user_id=user_id,
                user_settings=user_settings,
                max_tokens=polish_max_tokens,
                task_type="extraction",
                force_main_llm=force_main_llm,
            )
            llm_elapsed = _time.monotonic() - t1
            logger.info(
                f"[TTS_SEGMENT] v2 LLM polish: {llm_elapsed:.2f}s "
                f"(force_main_llm={force_main_llm})"
            )
        except Exception as e:
            logger.error(f"[TTS_SEGMENT] v2 LLM polish failed: {e}")
            raw_response = None

        llm_obj = parse_polish_response(raw_response or "")
        if llm_obj is None and raw_response:
            logger.warning(
                f"[TTS_SEGMENT] v2 LLM polish returned unparseable JSON; "
                f"using code-only verdicts. Preview: {raw_response[:300]!r}"
            )
        llm_meta = merge_verdicts(v2_segments, item_indices, llm_obj, code_pov, cast=cast_names)
    else:
        # No dialogue/thoughts in the scene — pure narration. Apply a
        # default scene_mood manually since LLM wasn't called.
        llm_meta = merge_verdicts(v2_segments, [], None, code_pov, cast=cast_names)

    # ---- Stage 2.5a: gender consistency unset (Layer F) ----
    # If the LLM assigned a speaker whose DB gender clashes with the
    # adjacent `<pronoun> <speech_verb>` tag (e.g. assigned a male cast
    # member to a `"...," she gasped` line), unset that speaker so the
    # split-quote pass below can re-resolve. Confidence-gated by the
    # DB-derived gender set — pronoun-window inference is too unreliable
    # to act on, since cross-character anatomical references pollute it.
    if confident_genders:
        gender_unsets = gender_consistency_unset(
            v2_segments, cast_names, gender_map,
            confident_genders=confident_genders,
        )
        if gender_unsets:
            logger.info(f"[TTS_SEGMENT] gender consistency unset {gender_unsets} mis-attributed dialogues")

    # ---- Stage 2.5b: deterministic split-quote tag-following pass ----
    # Catches `"X," he said. "Y."` patterns where the LLM/code mis-attributed
    # the opener or closer to the wrong speaker. Cheap, conservative, no LLM cost.
    split_quote_fixes = fix_split_quotes(v2_segments, cast_names, gender_map)
    if split_quote_fixes:
        logger.info(f"[TTS_SEGMENT] split-quote post-process corrected {split_quote_fixes} segments")

    # ---- Stage 3: canonicalize for downstream consumers ----
    cleaned = to_canonical_segments(v2_segments)

    if not cleaned:
        logger.warning("[TTS_SEGMENT] v2 produced empty cleaned list, falling back")
        _write_debug({
            "timestamp": started.isoformat(),
            "scene_chars": len(scene_text),
            "cast": cast_names,
            "error": "v2 cleaned segments empty",
        })
        return _fallback_segments(scene_text_stripped)

    logger.info(
        f"[TTS_SEGMENT] v2 extracted {len(cleaned)} segments "
        f"(code={code_elapsed*1000:.0f}ms, llm={llm_elapsed:.2f}s, "
        f"cast={cast_names}, scene_chars={len(scene_text)}, "
        f"speaker_overrides={llm_meta.get('overrides_speaker', 0)}, "
        f"emotion_overrides={llm_meta.get('overrides_emotion', 0)})"
    )
    _write_debug({
        "timestamp": started.isoformat(),
        "scene_chars": len(scene_text),
        "cast": cast_names,
        "pipeline": "v2",
        "code_stage_ms": round(code_elapsed * 1000, 1),
        "llm_stage_s": round(llm_elapsed, 2),
        "gender_map": gender_map,
        "code_pov": code_pov,
        "llm_meta": llm_meta,
        "segment_count": len(cleaned),
        "segments_preview": cleaned[:8],
    })
    return cleaned


async def extract_and_cache_for_variant(
    variant_id: int,
    user_id: int,
    user_settings: Dict[str, Any],
    delay_s: float = 0.3,
) -> None:
    """Background task: extract segments for `variant_id` and write to cache.

    Designed to be fired-and-forgotten via `asyncio.create_task` from the
    scene/variant generation completion paths. Cooperates with the lazy
    extraction in the TTS playback path via the in-flight lock — if a
    user clicks play while this task is running, the lazy path will
    `wait_for_in_flight` and reuse our result instead of double-extracting.

    Skips work in three cases (all logged but not raised):
    - The user's TTSSettings has `use_segment_extraction = False`.
    - The variant already has a cached `tts_segments`.
    - The variant has no content (or no longer exists).

    On extraction failure (LLM down, parse error) the cache is left NULL
    so the next play retries — we explicitly DON'T persist the
    single-narrator fallback that the synchronous lazy path uses (since
    here we have time to wait for transient failures to clear).
    """
    # Claim the in-flight slot IMMEDIATELY (before any sleep) so other
    # background tasks that defer behind this via wait_for_in_flight see
    # the registered event and properly wait. Previously the slot was
    # claimed AFTER a 300ms sleep, during which post-scene extractions
    # would race in and start hitting the LLM concurrently — defeating
    # the whole point of deferring them.
    async with _in_flight_lock:
        if variant_id in _in_flight:
            logger.info(f"[TTS_SEGMENT_BG] Variant {variant_id} already in flight, skipping duplicate")
            return
        event = asyncio.Event()
        _in_flight[variant_id] = event

    # Brief delay so the SceneVariant insert from the calling commit
    # is visible from a fresh session — mirrors the chronicle pattern.
    # Done AFTER registration so deferred tasks already see the in-flight
    # event during this window.
    if delay_s:
        try:
            await asyncio.sleep(delay_s)
        except asyncio.CancelledError:
            # Release the slot if we get cancelled mid-sleep.
            async with _in_flight_lock:
                _in_flight.pop(variant_id, None)
            event.set()
            return

    # Lazy imports to avoid a circular dep with app.models when this
    # module is imported from app.api.* during startup.
    from ..database import SessionLocal
    from ..models.scene_variant import SceneVariant
    from ..models.scene import Scene
    from ..models.story import Story
    from ..models.character import Character, StoryCharacter
    from ..models.tts_settings import TTSSettings

    try:
        db = SessionLocal()
        try:
            tts_settings = db.query(TTSSettings).filter(TTSSettings.user_id == user_id).first()
            if not tts_settings or not getattr(tts_settings, "use_segment_extraction", False):
                logger.debug(f"[TTS_SEGMENT_BG] use_segment_extraction off for user {user_id}, skipping")
                return
            if not tts_settings.tts_enabled:
                logger.debug(f"[TTS_SEGMENT_BG] TTS disabled for user {user_id}, skipping")
                return
            llm_choice = getattr(tts_settings, "tts_extraction_llm_choice", "extraction") or "extraction"
            force_main_for_bg = (llm_choice == "main")

            variant = db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
            if not variant:
                logger.warning(f"[TTS_SEGMENT_BG] Variant {variant_id} disappeared")
                return
            if variant.tts_segments:
                logger.info(f"[TTS_SEGMENT_BG] Variant {variant_id} already cached, skipping")
                return
            if not variant.content or not variant.content.strip():
                return

            scene = db.query(Scene).filter(Scene.id == variant.scene_id).first()
            if not scene:
                logger.warning(f"[TTS_SEGMENT_BG] Scene for variant {variant_id} missing")
                return
            story = db.query(Story).filter(Story.id == scene.story_id).first()
            if not story or story.owner_id != user_id:
                logger.warning(f"[TTS_SEGMENT_BG] Story for variant {variant_id} missing or wrong owner")
                return

            cast: List[Dict[str, Any]] = []
            gender_hints: Dict[str, str] = {}
            for sc in db.query(StoryCharacter).filter(StoryCharacter.story_id == story.id).all():
                char_obj = db.query(Character).filter(Character.id == sc.character_id).first()
                if not char_obj or not char_obj.name:
                    continue
                cast.append({"name": char_obj.name, "role": sc.role or ""})
                # Authoritative gender from the user-edited Character row.
                # Overrides per-scene pronoun-window inference, which can
                # be wrong when characters interact physically.
                g = (char_obj.gender or "").strip().lower()
                if g == "male":
                    gender_hints[char_obj.name] = "m"
                elif g == "female":
                    gender_hints[char_obj.name] = "f"

            scene_text_snapshot = variant.content
        finally:
            db.close()

        # Run extraction OUTSIDE the DB session — slow LLM call.
        segments = await extract_scene_segments(
            scene_text=scene_text_snapshot,
            cast=cast,
            user_id=user_id,
            user_settings=user_settings or {},
            force_main_llm=force_main_for_bg,
            gender_hints=gender_hints,
            variant_id=variant_id,
        )

        # Only cache "real" extractions. The fallback single-narrator
        # list signals failure — we leave the cache NULL so the next
        # playback can retry against a hopefully-recovered LLM.
        if not segments or len(segments) <= 1:
            logger.warning(f"[TTS_SEGMENT_BG] Variant {variant_id}: extraction produced "
                           f"<=1 segment (likely fallback) — leaving cache NULL")
            return

        # Re-open DB to persist; verify the variant still exists and
        # nobody else already wrote a cache while we were extracting.
        write_db = SessionLocal()
        try:
            v = write_db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
            if v is None:
                logger.warning(f"[TTS_SEGMENT_BG] Variant {variant_id} gone before write")
                return
            if v.tts_segments:
                logger.info(f"[TTS_SEGMENT_BG] Variant {variant_id} cached by someone else, skipping write")
                return
            v.tts_segments = {
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "model": (user_settings or {}).get("extraction_model_settings", {}).get("model_name", ""),
                "segments": segments,
                "source": "background",
            }
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(v, "tts_segments")
            write_db.commit()
            logger.info(f"[TTS_SEGMENT_BG] Cached {len(segments)} segments for variant {variant_id}")
        finally:
            write_db.close()
    except Exception as e:
        logger.error(f"[TTS_SEGMENT_BG] Variant {variant_id} background extraction crashed: {e}",
                     exc_info=True)
    finally:
        async with _in_flight_lock:
            _in_flight.pop(variant_id, None)
        event.set()
