"""
Chronicle Extraction Service

Two-pass pipeline:
  1. Main LLM extracts character chronicle + location lorebook entries (generous)
  2. Extraction LLM validates candidates (critical — hallucination, durability, redundancy)
  3. Programmatic checks: name matching, type validation, embedding dedup

All raw candidates + validation verdicts logged to logs/chronicle_extraction.json.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from ..models import (
    Story, Scene, SceneVariant, StoryFlow, Chapter,
    Character, StoryCharacter, StoryBranch,
    CharacterChronicle, LocationLorebook, ChronicleEntryType,
    CharacterSnapshot,
)

logger = logging.getLogger(__name__)

# Valid entry type values from enum
VALID_ENTRY_TYPES = {e.value for e in ChronicleEntryType}

LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "chronicle_extraction.json"
)


def _write_debug_log(data: dict):
    """Append extraction log entry to chronicle_extraction.json."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[CHRONICLE] Failed to write debug log: {e}")


async def extract_chronicle_and_lorebook(
    story_id: int,
    chapter_id: int,
    from_sequence: int,
    to_sequence: int,
    user_id: int,
    user_settings: dict,
    db: Session,
    branch_id: Optional[int] = None,
    scene_generation_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """
    Extract character chronicle entries and location lorebook events from a scene batch.

    Returns dict with counts: chronicle_entries, lorebook_entries, validated, rejected, embeddings.
    """
    result = {
        "chronicle_entries": 0,
        "lorebook_entries": 0,
        "validated": 0,
        "rejected": 0,
        "embeddings": 0,
    }

    # --- Pre-checks ---
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story or not story.world_id:
        logger.warning(f"[CHRONICLE] Story {story_id} has no world_id, skipping")
        return result

    world_id = story.world_id

    if not scene_generation_context:
        logger.warning(f"[CHRONICLE] No scene_generation_context, skipping")
        return result

    # --- Get scene contents ---
    scenes_query = db.query(Scene).join(StoryFlow).filter(
        StoryFlow.story_id == story_id,
        StoryFlow.is_active == True,
        Scene.chapter_id == chapter_id,
        Scene.is_deleted == False,
        Scene.sequence_number > from_sequence,
        Scene.sequence_number <= to_sequence,
    )
    if branch_id:
        scenes_query = scenes_query.filter(
            Scene.branch_id == branch_id,
            StoryFlow.branch_id == branch_id,
        )
    scenes = scenes_query.order_by(Scene.sequence_number).all()

    if not scenes:
        logger.warning(f"[CHRONICLE] No scenes in range ({from_sequence}, {to_sequence}]")
        return result

    # Build scene content text
    scenes_content_parts = []
    scene_id_for_sequence: Dict[int, int] = {}  # sequence -> scene_id

    for scene in scenes:
        flow_query = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True,
        )
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        flow_entry = flow_query.first()

        if not flow_entry or not flow_entry.scene_variant_id:
            continue

        variant = db.query(SceneVariant).filter(
            SceneVariant.id == flow_entry.scene_variant_id
        ).first()

        if not variant or not variant.content:
            continue

        scenes_content_parts.append(f"--- Scene {scene.sequence_number} ---\n{variant.content}")
        scene_id_for_sequence[scene.sequence_number] = scene.id

    if not scenes_content_parts:
        logger.warning(f"[CHRONICLE] No scene content found in range")
        return result

    scenes_content = "\n\n".join(scenes_content_parts)

    # --- Get chapter location for qualifying location names ---
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    chapter_location = chapter.location_name if chapter and chapter.location_name else ""

    # --- Get character names ---
    story_characters = db.query(StoryCharacter).filter(
        StoryCharacter.story_id == story_id,
    ).all()
    char_id_map: Dict[str, int] = {}  # lowercase name -> character_id
    char_names = []
    for sc in story_characters:
        char = db.query(Character).filter(Character.id == sc.character_id).first()
        if char:
            char_names.append(char.name)
            char_id_map[char.name.lower()] = char.id

    character_names_str = ", ".join(char_names) if char_names else "None"

    # --- Build existing state section (delta extraction) ---
    existing_section = _build_existing_state_section(db, world_id, story_id, branch_id, char_id_map)

    # === PASS 1: Extraction (main LLM, generous) ===
    logger.warning(f"[CHRONICLE] Pass 1: Extracting from scenes {from_sequence+1}-{to_sequence} "
                   f"({len(scenes_content_parts)} scenes, {len(char_names)} characters)")

    from .llm.service import UnifiedLLMService
    llm_service = UnifiedLLMService()

    try:
        raw_response = await llm_service.extract_chronicle_cache_friendly(
            scenes_content=scenes_content,
            character_names=character_names_str,
            existing_state_section=existing_section,
            context=scene_generation_context,
            user_id=user_id,
            user_settings=user_settings,
            db=db,
            chapter_location=chapter_location,
        )
    except Exception as e:
        logger.error(f"[CHRONICLE] Extraction LLM call failed: {e}")
        return result

    # Parse extraction response
    from .llm.extraction_service import extract_json_robust
    try:
        raw_data = extract_json_robust(raw_response)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[CHRONICLE] Failed to parse extraction response: {e}")
        _write_debug_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "story_id": story_id,
            "chapter_id": chapter_id,
            "scene_range": [from_sequence + 1, to_sequence],
            "error": f"JSON parse failed: {e}",
            "raw_response": raw_response[:2000] if raw_response else None,
        })
        return result

    raw_chronicle = raw_data.get("character_chronicle", [])
    raw_lorebook = raw_data.get("location_lorebook", [])

    logger.warning(f"[CHRONICLE] Pass 1 results: {len(raw_chronicle)} chronicle, {len(raw_lorebook)} lorebook candidates")

    if not raw_chronicle and not raw_lorebook:
        _write_debug_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "story_id": story_id,
            "chapter_id": chapter_id,
            "scene_range": [from_sequence + 1, to_sequence],
            "raw_candidates": raw_data,
            "validation_verdicts": [],
            "programmatic_rejections": [],
            "stored": {"chronicle": 0, "lorebook": 0},
        })
        return result

    # === PASS 2: Validation agent (extraction LLM, critical) ===
    all_candidates = []
    for entry in raw_chronicle:
        all_candidates.append({
            "type": "chronicle",
            "character_name": entry.get("character_name", ""),
            "entry_type": entry.get("entry_type", ""),
            "description": entry.get("description", ""),
        })
    for entry in raw_lorebook:
        all_candidates.append({
            "type": "lorebook",
            "location_name": entry.get("location_name", ""),
            "event_description": entry.get("event_description", ""),
        })

    candidate_entries_json = json.dumps(all_candidates, indent=2, ensure_ascii=False)
    validation_verdicts = []

    try:
        logger.warning(f"[CHRONICLE] Pass 2: Validating {len(all_candidates)} candidates")
        validation_response = await llm_service.validate_chronicle_cache_friendly(
            scenes_content=scenes_content,
            candidate_entries_json=candidate_entries_json,
            context=scene_generation_context,
            user_id=user_id,
            user_settings=user_settings,
            db=db,
            existing_chronicle_section=existing_section,
        )

        validation_data = extract_json_robust(validation_response)
        # Handle both {"validated": [...]} and bare list formats
        if isinstance(validation_data, list):
            validation_verdicts = validation_data
        else:
            validation_verdicts = validation_data.get("validated", [])
        logger.warning(f"[CHRONICLE] Pass 2 results: {len(validation_verdicts)} verdicts")

    except Exception as e:
        logger.error(f"[CHRONICLE] Validation failed: {e}")
        # If validation fails, accept only lorebook candidates (harder to get)
        # and reject chronicle candidates (too much noise without validation)
        for entry in raw_lorebook:
            validation_verdicts.append({
                "location_name": entry.get("location_name", ""),
                "event_description": entry.get("event_description", ""),
                "keep": True,
                "reason": "Validation unavailable, lorebook accepted by default",
            })
        logger.warning(f"[CHRONICLE] Validation failed — accepting {len(raw_lorebook)} lorebook, "
                       f"dropping {len(raw_chronicle)} chronicle candidates")

    # Build lookup of kept entries
    kept_chronicles = []
    kept_lorebooks = []
    rejected_entries = []

    for verdict in validation_verdicts:
        if verdict.get("keep", False):
            result["validated"] += 1
            # Determine if chronicle or lorebook based on fields present
            # Check location_name FIRST — lorebook entries may also have character_name
            if verdict.get("location_name"):
                kept_lorebooks.append(verdict)
            elif verdict.get("event_description"):
                kept_lorebooks.append(verdict)
            elif verdict.get("character_name"):
                kept_chronicles.append(verdict)
            else:
                kept_chronicles.append(verdict)
        else:
            result["rejected"] += 1
            rejected_entries.append(verdict)

    logger.warning(f"[CHRONICLE] Validation: {result['validated']} kept, {result['rejected']} rejected, "
                   f"{len(all_candidates) - len(validation_verdicts)} unmatched (dropped)")

    # === PASS 3: Programmatic checks + storage ===
    programmatic_rejections = []

    # Get max sequence for scene_id lookup
    max_scene_seq = max(scene_id_for_sequence.keys()) if scene_id_for_sequence else to_sequence
    default_scene_id = scene_id_for_sequence.get(max_scene_seq)

    # Get existing embeddings for dedup
    from .semantic_memory import get_semantic_memory_service
    try:
        semantic_memory = get_semantic_memory_service()
    except RuntimeError:
        semantic_memory = None

    stored_chronicle_count = 0
    stored_lorebook_count = 0
    embedding_count = 0

    # --- Store chronicle entries ---
    for entry in kept_chronicles:
        char_name = entry.get("character_name", "").strip()
        entry_type_str = entry.get("entry_type", "").strip().lower()
        description = entry.get("description", "").strip()

        # Validate character name
        char_id = char_id_map.get(char_name.lower())
        if not char_id:
            programmatic_rejections.append({
                **entry, "rejection": f"Unknown character: {char_name}"
            })
            continue

        # Validate entry type
        if entry_type_str not in VALID_ENTRY_TYPES:
            programmatic_rejections.append({
                **entry, "rejection": f"Invalid entry_type: {entry_type_str}"
            })
            continue

        # Minimum description length
        if len(description) < 15:
            programmatic_rejections.append({
                **entry, "rejection": f"Description too short ({len(description)} chars)"
            })
            continue

        # Embedding-based dedup: check against existing entries for this character
        if semantic_memory:
            is_dup = await _check_chronicle_duplicate(
                db, semantic_memory, world_id, char_id, story_id, branch_id,
                char_name, entry_type_str, description
            )
            if is_dup:
                programmatic_rejections.append({
                    **entry, "rejection": "Duplicate (embedding similarity > 0.78)"
                })
                continue
        else:
            # Fallback: text-based dedup when semantic memory unavailable
            is_dup = _check_chronicle_duplicate_text(
                db, world_id, char_id, story_id, branch_id, description
            )
            if is_dup:
                programmatic_rejections.append({
                    **entry, "rejection": "Duplicate (text similarity)"
                })
                continue

        # Store entry
        chronicle_entry = CharacterChronicle(
            world_id=world_id,
            character_id=char_id,
            story_id=story_id,
            branch_id=branch_id,
            scene_id=default_scene_id,
            sequence_order=max_scene_seq,
            entry_type=ChronicleEntryType(entry_type_str),
            description=description,
            is_defining=False,
        )
        db.add(chronicle_entry)
        db.flush()  # Get the ID

        # Generate embedding
        if semantic_memory:
            try:
                embed_text = f"{char_name} - {entry_type_str}: {description}"
                embedding = await semantic_memory.generate_embedding(embed_text)
                chronicle_entry.embedding = embedding
                chronicle_entry.embedding_id = f"chronicle_{chronicle_entry.id}"
                embedding_count += 1
            except Exception as e:
                logger.warning(f"[CHRONICLE] Failed to generate embedding for chronicle {chronicle_entry.id}: {e}")

        stored_chronicle_count += 1

    # --- Build existing location name map for normalization ---
    existing_location_names = _get_existing_location_names(db, world_id, story_id, branch_id)

    # --- Store lorebook entries ---
    for entry in kept_lorebooks:
        location_name = entry.get("location_name", "").strip()
        event_desc = entry.get("event_description", "").strip()

        if not location_name or not event_desc:
            programmatic_rejections.append({
                **entry, "rejection": "Missing location_name or event_description"
            })
            continue

        if len(event_desc) < 15:
            programmatic_rejections.append({
                **entry, "rejection": f"Description too short ({len(event_desc)} chars)"
            })
            continue

        # Normalize location name to match existing entries
        location_name = _normalize_location_name(location_name, existing_location_names)

        # Embedding-based dedup for lorebook
        if semantic_memory:
            is_dup = await _check_lorebook_duplicate(
                db, semantic_memory, world_id, location_name, story_id, branch_id,
                event_desc
            )
            if is_dup:
                programmatic_rejections.append({
                    **entry, "rejection": "Duplicate (embedding similarity > 0.78)"
                })
                continue
        else:
            is_dup = _check_lorebook_duplicate_text(
                db, world_id, location_name, story_id, branch_id, event_desc
            )
            if is_dup:
                programmatic_rejections.append({
                    **entry, "rejection": "Duplicate (text similarity)"
                })
                continue

        lorebook_entry = LocationLorebook(
            world_id=world_id,
            story_id=story_id,
            branch_id=branch_id,
            scene_id=default_scene_id,
            sequence_order=max_scene_seq,
            location_name=location_name,
            event_description=event_desc,
        )
        db.add(lorebook_entry)
        db.flush()

        # Generate embedding
        if semantic_memory:
            try:
                embed_text = f"{location_name}: {event_desc}"
                embedding = await semantic_memory.generate_embedding(embed_text)
                lorebook_entry.embedding = embedding
                lorebook_entry.embedding_id = f"lorebook_{lorebook_entry.id}"
                embedding_count += 1
            except Exception as e:
                logger.warning(f"[CHRONICLE] Failed to generate embedding for lorebook {lorebook_entry.id}: {e}")

        stored_lorebook_count += 1

    result["chronicle_entries"] = stored_chronicle_count
    result["lorebook_entries"] = stored_lorebook_count
    result["embeddings"] = embedding_count

    logger.warning(f"[CHRONICLE] Stored: {stored_chronicle_count} chronicle, {stored_lorebook_count} lorebook, "
                   f"{embedding_count} embeddings, {len(programmatic_rejections)} programmatic rejections")

    # --- Write debug log ---
    _write_debug_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "story_id": story_id,
        "chapter_id": chapter_id,
        "scene_range": [from_sequence + 1, to_sequence],
        "raw_candidates": {"character_chronicle": raw_chronicle, "location_lorebook": raw_lorebook},
        "validation_verdicts": validation_verdicts,
        "programmatic_rejections": programmatic_rejections,
        "stored": {"chronicle": stored_chronicle_count, "lorebook": stored_lorebook_count},
    })

    return result


def _build_existing_state_section(
    db: Session, world_id: int, story_id: int,
    branch_id: Optional[int], char_id_map: Dict[str, int]
) -> str:
    """Build compact existing chronicle/lorebook section for delta extraction."""
    parts = []

    # Chronicle entries — most recent 40 per character (more context helps validator catch redundancy)
    for char_name_lower, char_id in char_id_map.items():
        query = db.query(CharacterChronicle).filter(
            CharacterChronicle.world_id == world_id,
            CharacterChronicle.character_id == char_id,
            CharacterChronicle.story_id == story_id,
        )
        if branch_id:
            query = query.filter(CharacterChronicle.branch_id == branch_id)

        entries = query.order_by(desc(CharacterChronicle.sequence_order)).limit(40).all()
        if entries:
            for e in entries:
                parts.append(f"- {e.character.name if e.character else char_name_lower} | "
                             f"{e.entry_type.value}: {e.description} (scene {e.sequence_order})")

    # Lorebook entries — most recent 10 per location
    lorebook_query = db.query(LocationLorebook).filter(
        LocationLorebook.world_id == world_id,
        LocationLorebook.story_id == story_id,
    )
    if branch_id:
        lorebook_query = lorebook_query.filter(LocationLorebook.branch_id == branch_id)

    lorebook_entries = lorebook_query.order_by(desc(LocationLorebook.sequence_order)).limit(30).all()
    # Group by location, take top 10 each
    location_groups: Dict[str, List] = {}
    for e in lorebook_entries:
        location_groups.setdefault(e.location_name, []).append(e)

    for loc_name, entries in location_groups.items():
        for e in entries[:10]:
            parts.append(f"- Location '{loc_name}': {e.event_description} (scene {e.sequence_order})")

    if parts:
        return "EXISTING CHRONICLE & LOREBOOK (do NOT re-extract these):\n" + "\n".join(parts)
    return "No existing chronicle or lorebook entries yet."


def _get_existing_location_names(
    db: Session, world_id: int, story_id: int, branch_id: Optional[int]
) -> List[str]:
    """Get all distinct location names already in the lorebook for this story."""
    from sqlalchemy import distinct, or_
    query = db.query(distinct(LocationLorebook.location_name)).filter(
        LocationLorebook.world_id == world_id,
        LocationLorebook.story_id == story_id,
    )
    if branch_id:
        query = query.filter(
            or_(LocationLorebook.branch_id == branch_id, LocationLorebook.branch_id.is_(None))
        )
    return [row[0] for row in query.all()]


def _extract_room_word(name: str) -> Optional[str]:
    """Extract the core room/place word from a location name.

    'Saran Family Kitchen' -> 'kitchen'
    'Nishant's Master Bedroom' -> 'master bedroom'
    'Nishant and Radhika's Master Bedroom' -> 'master bedroom'
    """
    lower = name.lower()
    # Strip possessive prefixes: "X's Y", "X Family Y", "X and Y's Z"
    for pattern in [
        "'s ",  # Nishant's Kitchen
        " family ",  # Saran Family Kitchen
    ]:
        idx = lower.find(pattern)
        if idx >= 0:
            return lower[idx + len(pattern):].strip()
    # "X and Y's Z" pattern
    if " and " in lower and "'s " in lower:
        idx = lower.rfind("'s ")
        if idx >= 0:
            return lower[idx + 3:].strip()
    return None


def _normalize_location_name(new_name: str, existing_names: List[str]) -> str:
    """If new_name refers to the same room as an existing name, return the existing name.

    Matches by extracting the core room word (e.g., 'kitchen', 'master bedroom')
    and checking if it matches an existing entry.
    """
    if not existing_names:
        return new_name

    new_room = _extract_room_word(new_name)
    if not new_room:
        return new_name

    # Check exact match first
    if new_name in existing_names:
        return new_name

    # Find existing name with the same room word
    for existing in existing_names:
        existing_room = _extract_room_word(existing)
        if existing_room and existing_room == new_room:
            logger.info(f"[CHRONICLE] Normalized location '{new_name}' -> '{existing}' (same room: {new_room})")
            return existing

    return new_name


def _word_set(text: str) -> set:
    """Extract normalized word set for Jaccard similarity."""
    return set(text.lower().split())


def _jaccard_similarity(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    words_a = _word_set(a)
    words_b = _word_set(b)
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _check_chronicle_duplicate_text(
    db: Session, world_id: int, char_id: int,
    story_id: int, branch_id: Optional[int],
    description: str, threshold: float = 0.65,
) -> bool:
    """Text-based dedup fallback when semantic memory unavailable."""
    from sqlalchemy import or_
    query = db.query(CharacterChronicle).filter(
        CharacterChronicle.world_id == world_id,
        CharacterChronicle.character_id == char_id,
        CharacterChronicle.story_id == story_id,
    )
    if branch_id:
        query = query.filter(
            or_(CharacterChronicle.branch_id == branch_id, CharacterChronicle.branch_id.is_(None))
        )
    existing = query.all()
    for e in existing:
        sim = _jaccard_similarity(description, e.description)
        if sim > threshold:
            return True
    return False


def _check_lorebook_duplicate_text(
    db: Session, world_id: int, location_name: str,
    story_id: int, branch_id: Optional[int],
    event_description: str, threshold: float = 0.65,
) -> bool:
    """Text-based dedup fallback for lorebook when semantic memory unavailable."""
    from sqlalchemy import or_
    query = db.query(LocationLorebook).filter(
        LocationLorebook.world_id == world_id,
        LocationLorebook.story_id == story_id,
    )
    if branch_id:
        query = query.filter(
            or_(LocationLorebook.branch_id == branch_id, LocationLorebook.branch_id.is_(None))
        )
    existing = query.all()
    for e in existing:
        sim = _jaccard_similarity(event_description, e.event_description)
        if sim > threshold:
            return True
    return False


async def _check_chronicle_duplicate(
    db: Session, semantic_memory, world_id: int, char_id: int,
    story_id: int, branch_id: Optional[int],
    char_name: str, entry_type: str, description: str,
    threshold: float = 0.70,
) -> bool:
    """Check if a similar chronicle entry already exists via embedding similarity."""
    try:
        embed_text = f"{char_name} - {entry_type}: {description}"
        embedding = await semantic_memory.generate_embedding(embed_text)

        from pgvector.sqlalchemy import Vector
        from sqlalchemy import func

        query = db.query(
            CharacterChronicle.id,
            CharacterChronicle.embedding.cosine_distance(embedding).label("distance")
        ).filter(
            CharacterChronicle.world_id == world_id,
            CharacterChronicle.character_id == char_id,
            CharacterChronicle.story_id == story_id,
            CharacterChronicle.embedding.isnot(None),
        )
        if branch_id:
            query = query.filter(CharacterChronicle.branch_id == branch_id)

        closest = query.order_by("distance").limit(1).first()
        if closest and (1.0 - closest.distance) > threshold:
            return True
    except Exception as e:
        logger.warning(f"[CHRONICLE] Dedup check failed: {e}")
    return False


async def _check_lorebook_duplicate(
    db: Session, semantic_memory, world_id: int, location_name: str,
    story_id: int, branch_id: Optional[int],
    event_description: str,
    threshold: float = 0.78,
) -> bool:
    """Check if a similar lorebook entry already exists via embedding similarity."""
    try:
        embed_text = f"{location_name}: {event_description}"
        embedding = await semantic_memory.generate_embedding(embed_text)

        query = db.query(
            LocationLorebook.id,
            LocationLorebook.embedding.cosine_distance(embedding).label("distance")
        ).filter(
            LocationLorebook.world_id == world_id,
            LocationLorebook.story_id == story_id,
            LocationLorebook.embedding.isnot(None),
        )
        if branch_id:
            query = query.filter(LocationLorebook.branch_id == branch_id)

        closest = query.order_by("distance").limit(1).first()
        if closest and (1.0 - closest.distance) > threshold:
            return True
    except Exception as e:
        logger.warning(f"[CHRONICLE] Lorebook dedup check failed: {e}")
    return False


async def generate_character_snapshot(
    world_id: int,
    character_id: int,
    up_to_story_id: int,
    user_id: int,
    user_settings: dict,
    db: Session,
    branch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate a character snapshot by synthesizing chronicle entries across stories.

    When branch_id is provided, entries from that branch's story use only that branch
    (or NULL branch_id). Entries from other stories use their main branch (or NULL).

    Returns dict with snapshot data: snapshot_text, chronicle_entry_count, timeline_order, etc.
    """
    from sqlalchemy import or_, and_

    # Get the target story and its timeline_order
    up_to_story = db.query(Story).filter(Story.id == up_to_story_id).first()
    if not up_to_story:
        raise ValueError(f"Story {up_to_story_id} not found")
    if up_to_story.world_id != world_id:
        raise ValueError(f"Story {up_to_story_id} is not in world {world_id}")

    timeline_cutoff = up_to_story.timeline_order

    # Get the character
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise ValueError(f"Character {character_id} not found")

    # Get all stories in the world at or before the timeline cutoff
    stories_query = db.query(Story).filter(Story.world_id == world_id)
    if timeline_cutoff is not None:
        # Include stories with timeline_order <= cutoff, OR null timeline_order (unordered)
        stories_query = stories_query.filter(
            or_(
                Story.timeline_order <= timeline_cutoff,
                Story.timeline_order.is_(None),
            )
        )
    eligible_stories = stories_query.order_by(
        Story.timeline_order.asc().nullslast()
    ).all()
    eligible_story_ids = [s.id for s in eligible_stories]

    if not eligible_story_ids:
        raise ValueError("No eligible stories found")

    # Query chronicle entries for this character in eligible stories
    entries_query = db.query(CharacterChronicle).filter(
        CharacterChronicle.world_id == world_id,
        CharacterChronicle.character_id == character_id,
        CharacterChronicle.story_id.in_(eligible_story_ids),
    )

    # Branch-aware filtering
    if branch_id:
        branch = db.query(StoryBranch).filter(StoryBranch.id == branch_id).first()
        branch_story_id = branch.story_id if branch else None

        # Get main branch IDs for all OTHER eligible stories
        main_branch_ids = []
        for story in eligible_stories:
            if story.id != branch_story_id:
                main = db.query(StoryBranch).filter(
                    StoryBranch.story_id == story.id, StoryBranch.is_main == True
                ).first()
                if main:
                    main_branch_ids.append(main.id)

        # For target story: specific branch or NULL; for others: main branch or NULL
        branch_filter_parts = [
            and_(
                CharacterChronicle.story_id == branch_story_id,
                or_(CharacterChronicle.branch_id == branch_id, CharacterChronicle.branch_id.is_(None)),
            )
        ]
        if main_branch_ids:
            branch_filter_parts.append(
                and_(
                    CharacterChronicle.story_id != branch_story_id,
                    or_(CharacterChronicle.branch_id.in_(main_branch_ids), CharacterChronicle.branch_id.is_(None)),
                )
            )
        entries_query = entries_query.filter(or_(*branch_filter_parts))

    entries = entries_query.order_by(CharacterChronicle.sequence_order.asc()).all()

    if not entries:
        raise ValueError(f"No chronicle entries found for character {character.name} in eligible stories")

    # Group entries by story, maintaining story timeline order
    story_id_to_title = {s.id: s.title for s in eligible_stories}
    story_id_to_order = {s.id: (s.timeline_order if s.timeline_order is not None else 999999) for s in eligible_stories}

    entries_by_story: Dict[int, List] = {}
    for entry in entries:
        entries_by_story.setdefault(entry.story_id, []).append(entry)

    # Format entries grouped by story in timeline order
    sorted_story_ids = sorted(entries_by_story.keys(), key=lambda sid: story_id_to_order.get(sid, 999999))

    chronicle_text_parts = []
    for story_id in sorted_story_ids:
        story_title = story_id_to_title.get(story_id, f"Story #{story_id}")
        story_entries = entries_by_story[story_id]
        entry_lines = [f"- [{e.entry_type.value.replace('_', ' ')}] {e.description}" for e in story_entries]
        chronicle_text_parts.append(f"Story: {story_title}\n" + "\n".join(entry_lines))

    chronicle_entries_text = "\n\n".join(chronicle_text_parts)

    # Build the LLM prompt
    from .llm.prompts import prompt_manager

    user_prompt = prompt_manager.get_prompt(
        "character_snapshot_generation",
        "user",
        character_name=character.name,
        original_background=character.background or "No background provided.",
        chronicle_entries=chronicle_entries_text,
    )

    messages = [{"role": "user", "content": user_prompt}]

    # Call LLM via generate_for_task with main LLM + extraction settings
    from .llm.service import UnifiedLLMService
    llm_service = UnifiedLLMService()

    snapshot_text = await llm_service.generate_for_task(
        messages=messages,
        user_id=user_id,
        user_settings=user_settings,
        max_tokens=512,
        task_type="extraction",
        force_main_llm=True,
    )

    # Clean up the response (strip any stray quotes/whitespace)
    snapshot_text = snapshot_text.strip().strip('"').strip()

    # Upsert into CharacterSnapshot
    snapshot_query = db.query(CharacterSnapshot).filter(
        CharacterSnapshot.world_id == world_id,
        CharacterSnapshot.character_id == character_id,
    )
    if branch_id:
        snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id == branch_id)
    else:
        snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id.is_(None))
    existing = snapshot_query.first()

    entry_count = len(entries)

    if existing:
        existing.snapshot_text = snapshot_text
        existing.chronicle_entry_count = entry_count
        existing.timeline_order = timeline_cutoff
        existing.up_to_story_id = up_to_story_id
        snapshot = existing
    else:
        snapshot = CharacterSnapshot(
            world_id=world_id,
            character_id=character_id,
            branch_id=branch_id,
            snapshot_text=snapshot_text,
            chronicle_entry_count=entry_count,
            timeline_order=timeline_cutoff,
            up_to_story_id=up_to_story_id,
        )
        db.add(snapshot)

    db.commit()
    db.refresh(snapshot)

    return {
        "snapshot_text": snapshot.snapshot_text,
        "chronicle_entry_count": snapshot.chronicle_entry_count,
        "timeline_order": snapshot.timeline_order,
        "up_to_story_id": snapshot.up_to_story_id,
        "branch_id": snapshot.branch_id,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


async def maybe_generate_snapshots(
    story_id: int,
    user_id: int,
    user_settings: dict,
    db: Session,
    branch_id: Optional[int] = None,
    scene_generation_context: Optional[Dict[str, Any]] = None,
    snapshot_threshold: int = 15,
) -> Dict[str, Any]:
    """
    Generate snapshots for characters with enough new chronicle entries since last snapshot.

    Checks each character's current entry count vs their snapshot's chronicle_entry_count.
    If the difference >= snapshot_threshold, regenerates the snapshot using the cache-friendly
    LLM method.

    Returns dict with counts: snapshots_generated, snapshots_skipped.
    """
    result = {"snapshots_generated": 0, "snapshots_skipped": 0}

    story = db.query(Story).filter(Story.id == story_id).first()
    if not story or not story.world_id:
        return result

    world_id = story.world_id

    if not scene_generation_context:
        logger.warning("[SNAPSHOT] No scene_generation_context, skipping")
        return result

    # Get all characters with chronicle entries in this story/branch
    from sqlalchemy import func as sqlfunc
    entry_counts_query = db.query(
        CharacterChronicle.character_id,
        sqlfunc.count(CharacterChronicle.id).label("entry_count"),
    ).filter(
        CharacterChronicle.world_id == world_id,
        CharacterChronicle.story_id == story_id,
    )
    if branch_id:
        from sqlalchemy import or_
        entry_counts_query = entry_counts_query.filter(
            or_(CharacterChronicle.branch_id == branch_id, CharacterChronicle.branch_id.is_(None))
        )
    entry_counts = entry_counts_query.group_by(CharacterChronicle.character_id).all()

    if not entry_counts:
        return result

    from .llm.service import UnifiedLLMService
    llm_service = UnifiedLLMService()

    for char_id, current_count in entry_counts:
        # Check existing snapshot count
        snapshot_query = db.query(CharacterSnapshot).filter(
            CharacterSnapshot.world_id == world_id,
            CharacterSnapshot.character_id == char_id,
        )
        if branch_id:
            snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id == branch_id)
        else:
            snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id.is_(None))
        existing_snapshot = snapshot_query.first()

        last_count = existing_snapshot.chronicle_entry_count if existing_snapshot else 0
        if current_count - last_count < snapshot_threshold:
            result["snapshots_skipped"] += 1
            continue

        # Get character details
        character = db.query(Character).filter(Character.id == char_id).first()
        if not character:
            continue

        # Build original_background by merging Character model fields
        bg_parts = []
        if character.appearance:
            bg_parts.append(f"Appearance: {character.appearance}")
        if character.personality_traits:
            traits = character.personality_traits
            if isinstance(traits, list):
                traits = ", ".join(traits)
            bg_parts.append(f"Personality: {traits}")
        if character.background:
            bg_parts.append(f"Background: {character.background}")
        if character.goals:
            bg_parts.append(f"Goals: {character.goals}")
        if character.fears:
            bg_parts.append(f"Fears: {character.fears}")
        original_background = "\n".join(bg_parts) if bg_parts else "No background provided."

        # Format chronicle entries (chronological)
        from sqlalchemy import or_
        entries_query = db.query(CharacterChronicle).filter(
            CharacterChronicle.world_id == world_id,
            CharacterChronicle.character_id == char_id,
            CharacterChronicle.story_id == story_id,
        )
        if branch_id:
            entries_query = entries_query.filter(
                or_(CharacterChronicle.branch_id == branch_id, CharacterChronicle.branch_id.is_(None))
            )
        entries = entries_query.order_by(CharacterChronicle.sequence_order.asc()).all()

        entry_lines = [f"- [{e.entry_type.value.replace('_', ' ')}] {e.description}" for e in entries]
        chronicle_entries_text = "\n".join(entry_lines)

        # Call cache-friendly LLM generation
        try:
            snapshot_text = await llm_service.generate_snapshot_cache_friendly(
                character_name=character.name,
                original_background=original_background,
                chronicle_entries=chronicle_entries_text,
                context=scene_generation_context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            snapshot_text = snapshot_text.strip().strip('"').strip()

            if not snapshot_text or len(snapshot_text) < 30:
                logger.warning(f"[SNAPSHOT] Generated snapshot too short for {character.name}, skipping")
                result["snapshots_skipped"] += 1
                continue

            # Upsert snapshot
            if existing_snapshot:
                existing_snapshot.snapshot_text = snapshot_text
                existing_snapshot.chronicle_entry_count = current_count
                existing_snapshot.up_to_story_id = story_id
            else:
                new_snapshot = CharacterSnapshot(
                    world_id=world_id,
                    character_id=char_id,
                    branch_id=branch_id,
                    snapshot_text=snapshot_text,
                    chronicle_entry_count=current_count,
                    up_to_story_id=story_id,
                )
                db.add(new_snapshot)

            db.flush()
            result["snapshots_generated"] += 1
            logger.warning(f"[SNAPSHOT] Generated snapshot for {character.name} ({current_count} entries)")

        except Exception as e:
            logger.error(f"[SNAPSHOT] Failed to generate snapshot for {character.name}: {e}")
            result["snapshots_skipped"] += 1
            continue

    if result["snapshots_generated"] > 0:
        db.commit()

    logger.warning(f"[SNAPSHOT] Complete: {result}")
    return result
