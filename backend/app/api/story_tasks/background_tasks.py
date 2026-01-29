"""
Background tasks for story operations.

Extracted from stories.py to improve maintainability.
Contains all long-running background tasks for:
- Interaction extraction
- Scene extractions (character moments, plot events, entity states)
- Plot extraction
- NPC tracking restoration
- Semantic data cleanup
- Entity state restoration
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Optional

from ...database import SessionLocal, get_background_db
from ...models import (
    Chapter, Scene, StoryFlow, SceneVariant, Character, StoryCharacter,
    CharacterInteraction, NPCTracking, NPCTrackingSnapshot,
    CharacterState, LocationState, ObjectState, UserSettings
)

logger = logging.getLogger(__name__)

# In-memory progress tracking for interaction extraction
# Format: {story_id: {batches_processed: int, total_batches: int, interactions_found: int}}
extraction_progress_store: Dict[int, Dict] = {}

# Per-chapter extraction locks to prevent concurrent plot extractions
_chapter_extraction_locks: Dict[int, asyncio.Lock] = {}
# Per-story entity extraction locks to prevent concurrent entity recalculations
_story_entity_extraction_locks: Dict[int, asyncio.Lock] = {}
# Per-story scene deletion locks to prevent concurrent deletions
_story_deletion_locks: Dict[int, asyncio.Lock] = {}
# Per-scene variant generation locks to prevent concurrent regenerations
_scene_variant_locks: Dict[int, asyncio.Lock] = {}
# Per-variant edit locks to prevent concurrent edits
_variant_edit_locks: Dict[int, asyncio.Lock] = {}
# Per-scene generation locks to prevent concurrent scene generation
_scene_generation_locks: Dict[int, asyncio.Lock] = {}
_lock_dict_lock = asyncio.Lock()


async def get_chapter_extraction_lock(chapter_id: int) -> asyncio.Lock:
    """Get or create a lock for the given chapter's plot extraction."""
    async with _lock_dict_lock:
        if chapter_id not in _chapter_extraction_locks:
            _chapter_extraction_locks[chapter_id] = asyncio.Lock()
        return _chapter_extraction_locks[chapter_id]


async def get_story_entity_extraction_lock(story_id: int) -> asyncio.Lock:
    """Get or create a lock for the given story's entity extraction."""
    async with _lock_dict_lock:
        if story_id not in _story_entity_extraction_locks:
            _story_entity_extraction_locks[story_id] = asyncio.Lock()
        return _story_entity_extraction_locks[story_id]


async def get_story_deletion_lock(story_id: int) -> asyncio.Lock:
    """Get or create a lock for the given story's scene deletion operations."""
    async with _lock_dict_lock:
        if story_id not in _story_deletion_locks:
            _story_deletion_locks[story_id] = asyncio.Lock()
        return _story_deletion_locks[story_id]


async def get_scene_variant_lock(scene_id: int) -> asyncio.Lock:
    """Get or create a lock for the given scene's variant generation."""
    async with _lock_dict_lock:
        if scene_id not in _scene_variant_locks:
            _scene_variant_locks[scene_id] = asyncio.Lock()
        return _scene_variant_locks[scene_id]


async def get_variant_edit_lock(variant_id: int) -> asyncio.Lock:
    """Get or create a lock for the given variant's edit operations."""
    async with _lock_dict_lock:
        if variant_id not in _variant_edit_locks:
            _variant_edit_locks[variant_id] = asyncio.Lock()
        return _variant_edit_locks[variant_id]


async def get_scene_generation_lock(story_id: int) -> asyncio.Lock:
    """Get or create a lock for scene generation on a story."""
    async with _lock_dict_lock:
        if story_id not in _scene_generation_locks:
            _scene_generation_locks[story_id] = asyncio.Lock()
        return _scene_generation_locks[story_id]


async def run_interaction_extraction_background(
    story_id: int,
    branch_id: int,
    user_id: int,
    user_settings: dict,
    interaction_types: list,
    batch_size: int = 10
):
    """
    Background task to extract interactions from scenes using BATCHED processing.

    Instead of sending 170 individual LLM requests, we:
    1. Group scenes into batches of 10
    2. Concatenate scene summaries (first 500 chars each)
    3. Send one LLM request per batch
    4. Result: ~17 requests instead of 170 for a 170-scene story

    Uses extraction LLM if configured, otherwise falls back to main LLM.
    """
    from ...services.llm.service import UnifiedLLMService
    from ...services.llm.extraction_service import ExtractionLLMService
    from ...config import settings
    from sqlalchemy import or_

    logger.info(f"[INTERACTION_EXTRACT] Starting BATCHED extraction for story {story_id} (batch_size={batch_size})")

    extraction_db = SessionLocal()

    # Try to use extraction LLM if configured
    extraction_service = None
    extraction_settings = user_settings.get('extraction_model_settings', {})
    if extraction_settings.get('enabled', False):
        try:
            ext_defaults = settings._yaml_config.get('extraction_model', {})
            url = extraction_settings.get('url', ext_defaults.get('url'))
            model = extraction_settings.get('model_name', ext_defaults.get('model_name'))
            api_key = extraction_settings.get('api_key', ext_defaults.get('api_key', ''))
            temperature = extraction_settings.get('temperature', ext_defaults.get('temperature', 0.3))
            max_tokens = extraction_settings.get('max_tokens', ext_defaults.get('max_tokens', 2048))

            if url and model:
                # Get timeout from user's LLM settings
                llm_settings = user_settings.get('llm_settings', {})
                timeout_total = llm_settings.get('timeout_total', 240)
                extraction_service = ExtractionLLMService(
                    url=url,
                    model=model,
                    api_key=api_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_total=timeout_total
                )
                logger.info(f"[INTERACTION_EXTRACT] Using extraction LLM: {model} at {url} (timeout={timeout_total}s)")
        except Exception as e:
            logger.warning(f"[INTERACTION_EXTRACT] Failed to init extraction service: {e}, falling back to main LLM")

    # Fallback to main LLM
    main_llm = UnifiedLLMService() if not extraction_service else None
    if main_llm:
        logger.info(f"[INTERACTION_EXTRACT] Using main LLM for extraction")

    try:
        # Get all scenes in order
        scene_query = extraction_db.query(Scene).filter(Scene.story_id == story_id)
        if branch_id:
            scene_query = scene_query.filter(Scene.branch_id == branch_id)
        scenes = scene_query.order_by(Scene.sequence_number).all()

        total_scenes = len(scenes)
        logger.info(f"[INTERACTION_EXTRACT] Found {total_scenes} scenes to process")

        # Get already-found interactions to avoid duplicates across batches (filtered by branch)
        existing_query = extraction_db.query(CharacterInteraction).filter(
            CharacterInteraction.story_id == story_id
        )
        if branch_id:
            existing_query = existing_query.filter(CharacterInteraction.branch_id == branch_id)
        existing_interactions = existing_query.all()

        # Build character name to ID mapping with multiple lookup keys
        # This handles cases where LLM returns partial names (e.g., "john" instead of "John Smith")
        char_query = extraction_db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
        if branch_id:
            char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
        story_characters = char_query.all()

        character_name_to_id = {}
        character_names = []

        # Add main story characters
        for sc in story_characters:
            char = extraction_db.query(Character).filter(Character.id == sc.character_id).first()
            if char:
                character_names.append(char.name)
                full_name_lower = char.name.lower()
                # Add full name
                character_name_to_id[full_name_lower] = char.id
                # Add first name only (for "John Smith" -> "john")
                first_name = full_name_lower.split()[0]
                if first_name not in character_name_to_id:
                    character_name_to_id[first_name] = char.id
                # Add last name only if it exists (for "Sharma" -> id)
                name_parts = full_name_lower.split()
                if len(name_parts) > 1:
                    last_name = name_parts[-1]
                    if last_name not in character_name_to_id:
                        character_name_to_id[last_name] = char.id

        # Also include significant NPCs (those with importance score > threshold or many mentions)
        # NPCs don't have character IDs, so we'll create virtual negative IDs for them
        npc_query = extraction_db.query(NPCTracking).filter(
            NPCTracking.story_id == story_id,
            NPCTracking.entity_type == "CHARACTER"  # Only character NPCs, not entities
        )
        if branch_id:
            npc_query = npc_query.filter(NPCTracking.branch_id == branch_id)
        # Get NPCs with at least 3 mentions or importance > 0.3
        significant_npcs = npc_query.filter(
            or_(
                NPCTracking.total_mentions >= 3,
                NPCTracking.importance_score >= 0.3
            )
        ).all()

        npc_virtual_id_counter = -1  # Use negative IDs for NPCs
        npc_name_to_virtual_id = {}

        for npc in significant_npcs:
            npc_name = npc.character_name
            if npc_name.lower() not in character_name_to_id:  # Don't override main characters
                character_names.append(f"{npc_name} (NPC)")
                full_name_lower = npc_name.lower()
                npc_name_to_virtual_id[full_name_lower] = npc_virtual_id_counter
                character_name_to_id[full_name_lower] = npc_virtual_id_counter
                # Add first name
                first_name = full_name_lower.split()[0]
                if first_name not in character_name_to_id:
                    character_name_to_id[first_name] = npc_virtual_id_counter
                    npc_name_to_virtual_id[first_name] = npc_virtual_id_counter
                npc_virtual_id_counter -= 1

        logger.info(f"[INTERACTION_EXTRACT] Character lookup keys: {list(character_name_to_id.keys())}")
        logger.info(f"[INTERACTION_EXTRACT] Including {len(significant_npcs)} significant NPCs")

        interactions_found = 0
        batches_processed = 0
        num_batches = (total_scenes + batch_size - 1) // batch_size

        # Initialize progress tracking
        extraction_progress_store[story_id] = {
            'batches_processed': 0,
            'total_batches': num_batches,
            'interactions_found': 0
        }

        # Process in batches
        for batch_start in range(0, total_scenes, batch_size):
            batch_end = min(batch_start + batch_size, total_scenes)
            batch_scenes = scenes[batch_start:batch_end]

            try:
                # Build batch content - summarize each scene
                batch_content_parts = []
                scene_sequence_map = {}  # Map scene index in batch to sequence number

                for idx, scene in enumerate(batch_scenes):
                    # Get scene content from active variant
                    flow = extraction_db.query(StoryFlow).filter(
                        StoryFlow.scene_id == scene.id,
                        StoryFlow.is_active == True
                    ).first()

                    if flow and flow.scene_variant:
                        scene_content = flow.scene_variant.content
                    else:
                        scene_content = scene.content

                    if not scene_content:
                        continue

                    # Truncate to first 1500 chars for batch efficiency
                    # (increased from 800 to capture more interaction-relevant content)
                    truncated = scene_content[:1500]
                    if len(scene_content) > 1500:
                        truncated += "..."

                    batch_content_parts.append(f"[SCENE {scene.sequence_number}]\n{truncated}")
                    scene_sequence_map[idx] = scene.sequence_number

                if not batch_content_parts:
                    continue

                # Build list of already-found interactions for this batch
                already_found_list = []
                for ei in existing_interactions:
                    # Get character names
                    char_a_name = None
                    char_b_name = None
                    for name, cid in character_name_to_id.items():
                        if cid == ei.character_a_id and not char_a_name:
                            char_a_name = name
                        if cid == ei.character_b_id and not char_b_name:
                            char_b_name = name

                    if char_a_name and char_b_name:
                        already_found_list.append(f"{ei.interaction_type} between {char_a_name} and {char_b_name}")

                already_found_text = ""
                if already_found_list:
                    already_found_text = f"\n\nALREADY FOUND IN PREVIOUS SCENES (do not report again):\n" + "\n".join(f"- {x}" for x in already_found_list)

                # Build batch prompt
                batch_prompt = f"""Analyze these scenes for ACTUAL character interactions that occur IN REALITY.

INTERACTION TYPES TO DETECT: {json.dumps(interaction_types)}

CHARACTERS: {', '.join(character_names)}
{already_found_text}

SCENES:
{''.join(batch_content_parts)}

CRITICAL RULES:
1. The interaction must be COMPLETED in the scene, not just started or implied
2. Do NOT infer what will happen next - only report what EXPLICITLY OCCURRED
3. "First X" means the FIRST time X actually happens, not the first time it's suggested
4. If a scene shows build-up to an action but cuts away before completion, do NOT report it
5. A polite exchange is NOT a reconciliation unless there was a prior argument AND an explicit apology

INSTRUCTIONS:
1. ONLY report interactions that EXPLICITLY HAPPEN and COMPLETE in the scene text
2. Return {{"interactions": []}} if NO interactions from the list occur - this is expected and correct
3. Do NOT report interactions that:
   - Occur in fantasies, dreams, or imagination
   - Are referenced from the past but not shown happening now
   - Are ambiguous, implied, or suggested but not shown
   - Could be interpreted multiple ways
   - Are about to happen but scene ends before completion
   - Are inferred from context rather than explicitly shown
4. Quality over quantity - if unsure, do NOT include it
5. Most batches should return few or no interactions - that is correct behavior

For valid interactions only, return:
{{
  "interactions": [
    {{
      "scene_number": <scene number from [SCENE X] marker>,
      "interaction_type": "exact type from list",
      "character_a": "character name",
      "character_b": "character name",
      "description": "One sentence describing what ACTUALLY happens and COMPLETES in the scene"
    }}
  ]
}}

CRITICAL: It is better to return an empty list than to include uncertain interactions.
Do NOT explain why an interaction does not occur - simply omit it from the list."""

                system_prompt = "You are a precise story analyst. Only extract interactions you are certain about. When in doubt, exclude. Return valid JSON only."

                # Use extraction service if available, otherwise main LLM
                if extraction_service:
                    try:
                        response = await extraction_service.generate(
                            prompt=batch_prompt,
                            system_prompt=system_prompt,
                            max_tokens=2048
                        )
                    except Exception as e:
                        logger.warning(f"[INTERACTION_EXTRACT] Extraction service failed: {e}, trying main LLM")
                        if main_llm:
                            response = await main_llm.generate(
                                prompt=batch_prompt,
                                user_id=user_id,
                                user_settings=user_settings,
                                system_prompt=system_prompt,
                                max_tokens=2048
                            )
                        else:
                            raise
                else:
                    response = await main_llm.generate(
                        prompt=batch_prompt,
                        user_id=user_id,
                        user_settings=user_settings,
                        system_prompt=system_prompt,
                        max_tokens=2048
                    )

                # Parse response
                response_clean = response.strip()
                if response_clean.startswith("```json"):
                    response_clean = response_clean[7:]
                if response_clean.startswith("```"):
                    response_clean = response_clean[3:]
                if response_clean.endswith("```"):
                    response_clean = response_clean[:-3]
                response_clean = response_clean.strip()

                result = json.loads(response_clean)

                # Phrases that indicate the LLM is reporting a non-interaction, uncertain, or inferred
                REJECTION_PHRASES = [
                    # Negation phrases
                    "does not occur",
                    "did not occur",
                    "not established",
                    "not confirmed",
                    "not described",
                    "not explicitly shown",
                    "not explicitly",
                    "no argument",
                    "no conflict",
                    "no declaration",
                    "no commitment",
                    "no physical",
                    "not a ",
                    "therefore, this interaction",
                    "is not ",
                    "however, ",
                    "there is no ",
                    "though the full",
                    "suggests a beginning",
                    "constitutes a first kiss as it is",  # thumb on lip misclassification
                    # Inference/prediction phrases - LLM inferring what will happen
                    "leads to",
                    "will ",
                    "about to",
                    "suggests ",
                    "implies ",
                    "building toward",
                    "setting up",
                    "foreshadows",
                    "heading toward",
                    "on the verge of",
                    "almost ",
                    "nearly ",
                    "seems to be",
                    "appears to be",
                    "could be interpreted",
                    "may indicate",
                    "might be",
                ]

                def is_valid_interaction(interaction_data: dict) -> bool:
                    """Check if the LLM actually found a real interaction vs reporting absence."""
                    desc = (interaction_data.get("description") or "").lower()
                    for phrase in REJECTION_PHRASES:
                        if phrase in desc:
                            return False
                    return True

                def normalize_interaction_type(raw_type: str, configured_types: list) -> str:
                    """
                    Normalize interaction type to match configured types.
                    Handles typos and case differences.
                    """
                    raw_lower = raw_type.lower().strip()

                    # Common typo corrections
                    typo_fixes = {
                        "complement": "compliment",
                        "complemented": "complimented",
                        "complementing": "complimenting",
                    }
                    for typo, fix in typo_fixes.items():
                        raw_lower = raw_lower.replace(typo, fix)

                    # Try exact match first
                    for configured in configured_types:
                        if configured.lower() == raw_lower:
                            return configured.lower()

                    # Try fuzzy match (check if configured type is contained in raw or vice versa)
                    for configured in configured_types:
                        conf_lower = configured.lower()
                        if conf_lower in raw_lower or raw_lower in conf_lower:
                            return conf_lower

                    # Return normalized version even if not in configured list
                    return raw_lower

                for interaction in result.get("interactions", []):
                    scene_number = interaction.get("scene_number", 0)
                    raw_interaction_type = interaction.get("interaction_type", "").strip()
                    interaction_type = normalize_interaction_type(raw_interaction_type, interaction_types)
                    char_a_name = interaction.get("character_a", "").strip().lower()
                    char_b_name = interaction.get("character_b", "").strip().lower()
                    description = interaction.get("description", "")

                    if not interaction_type or not char_a_name or not char_b_name or not scene_number:
                        continue

                    # Validate that the LLM actually found a real interaction
                    # (reject self-contradicting responses like "this interaction does not occur")
                    if not is_valid_interaction(interaction):
                        logger.info(f"[INTERACTION_EXTRACT] Rejected self-contradicting: {interaction_type} - '{description[:80]}...'")
                        continue

                    # Get character IDs
                    char_a_id = character_name_to_id.get(char_a_name)
                    char_b_id = character_name_to_id.get(char_b_name)

                    if not char_a_id or not char_b_id:
                        logger.warning(f"[INTERACTION_EXTRACT] Unknown character(s): {char_a_name}, {char_b_name}")
                        continue

                    # Check if either character is an NPC (negative ID)
                    # We can only store interactions between main characters (positive IDs)
                    if char_a_id < 0 or char_b_id < 0:
                        logger.info(f"[INTERACTION_EXTRACT] NPC interaction (not stored): {interaction_type} between {char_a_name} and {char_b_name} at scene {scene_number}")
                        continue

                    # Normalize order (lower ID first)
                    if char_a_id > char_b_id:
                        char_a_id, char_b_id = char_b_id, char_a_id

                    # Check if already exists (might have been found in earlier batch) - filter by branch
                    existing_check = extraction_db.query(CharacterInteraction).filter(
                        CharacterInteraction.story_id == story_id,
                        CharacterInteraction.character_a_id == char_a_id,
                        CharacterInteraction.character_b_id == char_b_id,
                        CharacterInteraction.interaction_type == interaction_type
                    )
                    if branch_id:
                        existing_check = existing_check.filter(CharacterInteraction.branch_id == branch_id)
                    existing = existing_check.first()

                    if not existing:
                        new_interaction = CharacterInteraction(
                            story_id=story_id,
                            branch_id=branch_id,
                            character_a_id=char_a_id,
                            character_b_id=char_b_id,
                            interaction_type=interaction_type,
                            first_occurrence_scene=scene_number,
                            description=description
                        )
                        extraction_db.add(new_interaction)
                        extraction_db.flush()
                        # Add to existing_interactions list so next batch knows about it
                        existing_interactions.append(new_interaction)
                        interactions_found += 1
                        logger.info(f"[INTERACTION_EXTRACT] Found: {interaction_type} at scene {scene_number}")
                    else:
                        logger.debug(f"[INTERACTION_EXTRACT] Already exists: {interaction_type}")

                batches_processed += 1
                extraction_db.commit()

                # Update progress tracking
                extraction_progress_store[story_id] = {
                    'batches_processed': batches_processed,
                    'total_batches': num_batches,
                    'interactions_found': interactions_found
                }

                logger.info(f"[INTERACTION_EXTRACT] Batch {batches_processed}/{num_batches} complete (scenes {batch_start+1}-{batch_end}), found {interactions_found} total")

                # Small delay between batches to avoid rate limiting
                await asyncio.sleep(0.5)

            except json.JSONDecodeError as e:
                logger.warning(f"[INTERACTION_EXTRACT] JSON parse error for batch {batches_processed+1}: {e}")
                continue
            except Exception as e:
                logger.warning(f"[INTERACTION_EXTRACT] Error processing batch {batches_processed+1}: {e}")
                import traceback
                logger.warning(f"[INTERACTION_EXTRACT] Traceback: {traceback.format_exc()}")
                continue

        extraction_db.commit()
        logger.info(f"[INTERACTION_EXTRACT] Complete! Processed {batches_processed} batches, found {interactions_found} interactions")

        # Clear progress tracking on completion
        if story_id in extraction_progress_store:
            del extraction_progress_store[story_id]

    except Exception as e:
        logger.error(f"[INTERACTION_EXTRACT] Failed: {e}")
        import traceback
        logger.error(f"[INTERACTION_EXTRACT] Traceback: {traceback.format_exc()}")
        # Clear progress tracking on error too
        if story_id in extraction_progress_store:
            del extraction_progress_store[story_id]
    finally:
        extraction_db.close()


async def run_extractions_in_background(
    story_id: int,
    chapter_id: int,
    from_sequence: int,
    to_sequence: int,
    user_id: int,
    user_settings: dict
):
    """Run extractions in background, independent of streaming response"""
    try:
        # Delay to ensure database commits from main session are visible
        # This helps with transaction isolation between sessions
        # Increased from 0.1s to 0.3s for better reliability under load
        await asyncio.sleep(0.3)

        extraction_db = SessionLocal()
        try:
            # Reload chapter to get fresh data (in case it was updated)
            extraction_chapter = extraction_db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not extraction_chapter:
                logger.error(f"[EXTRACTION] Chapter {chapter_id} not found in background task")
                return

            # Get actual sequence numbers of scenes in this chapter (not scenes_count which is just a count)
            scenes_in_chapter = extraction_db.query(Scene).join(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.is_active == True,
                Scene.chapter_id == chapter_id,
                Scene.is_deleted == False
            ).order_by(Scene.sequence_number).all()

            if not scenes_in_chapter:
                logger.warning(f"[EXTRACTION] No scenes found in chapter {chapter_id}, skipping extraction")
                return

            # Get actual sequence numbers
            scene_sequence_numbers = [s.sequence_number for s in scenes_in_chapter]
            max_sequence_in_chapter = max(scene_sequence_numbers)
            min_sequence_in_chapter = min(scene_sequence_numbers)

            # Use last_extraction_scene_count as from_sequence (it should be a sequence number, not a count)
            # But if it's 0 or greater than max, use min_sequence_in_chapter - 1
            actual_from_sequence = extraction_chapter.last_extraction_scene_count or 0
            if actual_from_sequence == 0 or actual_from_sequence >= max_sequence_in_chapter:
                actual_from_sequence = min_sequence_in_chapter - 1

            actual_to_sequence = max_sequence_in_chapter

            # Safety check: if from_sequence >= to_sequence, there are no scenes to process
            if actual_from_sequence >= actual_to_sequence:
                logger.warning(f"[EXTRACTION] No scenes to process: from_sequence ({actual_from_sequence}) >= to_sequence ({actual_to_sequence})")
                logger.warning(f"[EXTRACTION] Skipping extraction for chapter {chapter_id}")
                return

            logger.warning(f"[EXTRACTION] Background task - Reloaded chapter {chapter_id}:")
            logger.warning(f"  - Scenes in chapter: {len(scenes_in_chapter)} (sequences {min_sequence_in_chapter} to {max_sequence_in_chapter})")
            logger.warning(f"  - Using from_sequence={actual_from_sequence}, to_sequence={actual_to_sequence}")
            logger.warning(f"  - Original params: from={from_sequence}, to={to_sequence}")

            # Import here to avoid circular imports
            try:
                from ...services.semantic_integration import batch_process_scene_extractions
            except ImportError:
                logger.error("[EXTRACTION] Failed to import batch_process_scene_extractions")
                return

            batch_results = await batch_process_scene_extractions(
                story_id=story_id,
                chapter_id=chapter_id,
                from_sequence=actual_from_sequence,
                to_sequence=actual_to_sequence,
                user_id=user_id,
                user_settings=user_settings,
                db=extraction_db
            )

            # Only update last_extraction_scene_count if scenes were actually processed
            # This prevents loops when scenes are deleted and no scenes are found to process
            scenes_processed = batch_results.get('scenes_processed', 0)
            if scenes_processed > 0:
                # Update last extraction count with actual sequence number (not count)
                extraction_chapter.last_extraction_scene_count = actual_to_sequence
                extraction_db.commit()
                logger.warning(f"[EXTRACTION] Updated last_extraction_scene_count to {actual_to_sequence} for chapter {chapter_id}")
            else:
                # No scenes processed - don't update last_extraction_scene_count to prevent loops
                # This can happen if scenes were deleted or if there's a timing issue
                logger.warning(f"[EXTRACTION] No scenes processed, keeping last_extraction_scene_count at {extraction_chapter.last_extraction_scene_count} for chapter {chapter_id}")

            logger.warning(f"[EXTRACTION] Background extraction complete for chapter {chapter_id}")
            logger.warning(f"  - Scenes processed: {scenes_processed}")
            logger.warning(f"  - Character moments: {batch_results.get('character_moments', 0)}")
            logger.warning(f"  - Plot events: {batch_results.get('plot_events', 0)}")
            logger.warning(f"  - Entity states: {batch_results.get('entity_states', 0)}")
            logger.warning(f"  - NPC tracking: {batch_results.get('npc_tracking', 0)}")
            logger.warning(f"  - Scene embeddings: {batch_results.get('scene_embeddings', 0)}")

            # Note: Plot progress extraction now runs independently via run_plot_extraction_in_background
            # based on plot_event_extraction_threshold setting
        finally:
            extraction_db.close()
    except Exception as e:
        logger.error(f"[EXTRACTION] Background extraction failed: {e}")
        import traceback
        logger.error(f"[EXTRACTION] Traceback: {traceback.format_exc()}")


async def recalculate_entities_in_background(
    story_id: int,
    user_id: int,
    user_settings: dict,
    up_to_sequence: int,
    branch_id: int = None,
    force_extraction: bool = False
):
    """Recalculate entity states in background after scene edit.

    This runs asynchronously to avoid blocking the HTTP request when editing
    scenes at threshold boundaries (e.g., sequence % 5 == 0).

    Args:
        story_id: Story ID
        user_id: User ID
        user_settings: User settings dictionary
        up_to_sequence: Sequence number to recalculate up to
        branch_id: Optional branch ID
        force_extraction: If True, extract regardless of batch threshold (for edits)
    """
    try:
        # Acquire lock for this story to prevent concurrent entity extractions
        lock = await get_story_entity_extraction_lock(story_id)

        # Try to acquire lock without blocking - if already locked, skip this extraction
        if lock.locked():
            logger.warning(f"[BACKGROUND:ENTITY] Story {story_id} entity extraction already in progress, skipping")
            return

        async with lock:
            # Delay to ensure database commits from main session are visible
            await asyncio.sleep(0.3)

            from ...services.entity_state_service import EntityStateService

            extraction_db = SessionLocal()
            try:
                logger.info(f"[BACKGROUND:ENTITY] Starting entity recalculation for story {story_id} up to sequence {up_to_sequence}")

                entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
                result = await entity_service.recalculate_entity_states_from_batches(
                    extraction_db, story_id, user_id, user_settings,
                    up_to_sequence, branch_id=branch_id, force_extraction=force_extraction
                )

                extraction_db.commit()

                if result.get("recalculation_successful"):
                    logger.info(f"[BACKGROUND:ENTITY] Completed entity recalculation for story {story_id}: "
                               f"{result.get('scenes_processed', 0)} scenes processed, "
                               f"{result.get('characters_restored', 0)} characters restored")
                else:
                    logger.error(f"[BACKGROUND:ENTITY] Entity recalculation failed for story {story_id}")

            except Exception as e:
                logger.error(f"[BACKGROUND:ENTITY] Entity recalculation failed: {e}")
                import traceback
                logger.error(f"[BACKGROUND:ENTITY] Traceback: {traceback.format_exc()}")
                extraction_db.rollback()
            finally:
                extraction_db.close()

    except Exception as e:
        logger.error(f"[BACKGROUND:ENTITY] Failed to start entity recalculation: {e}")


async def run_plot_extraction_in_background(
    story_id: int,
    chapter_id: int,
    from_sequence: int,
    to_sequence: int,
    user_id: int,
    user_settings: dict
):
    """Run plot event extraction in background, independent of entity extraction.
    Uses per-chapter locking to prevent concurrent extractions and creates batches for rollback support."""
    try:
        # Acquire lock for this chapter to prevent concurrent extractions
        lock = await get_chapter_extraction_lock(chapter_id)

        # Try to acquire lock without blocking - if already locked, skip this extraction
        if lock.locked():
            logger.warning(f"[PLOT_EXTRACTION] Chapter {chapter_id} extraction already in progress, skipping")
            return

        async with lock:
            # Delay to ensure database commits from main session are visible
            await asyncio.sleep(0.3)

            extraction_db = SessionLocal()
            try:
                # Reload chapter to get fresh data
                extraction_chapter = extraction_db.query(Chapter).filter(Chapter.id == chapter_id).first()
                if not extraction_chapter:
                    logger.error(f"[PLOT_EXTRACTION] Chapter {chapter_id} not found in background task")
                    return

                if not extraction_chapter.chapter_plot:
                    logger.warning(f"[PLOT_EXTRACTION] Chapter {chapter_id} has no plot, skipping")
                    return

                # Get actual sequence numbers of scenes in this chapter
                # Filter by branch_id to ensure we only process scenes in the correct branch
                scenes_query = extraction_db.query(Scene).join(StoryFlow).filter(
                    StoryFlow.story_id == story_id,
                    StoryFlow.is_active == True,
                    Scene.chapter_id == chapter_id,
                    Scene.is_deleted == False
                )
                # Add branch filtering if chapter has a branch_id
                if extraction_chapter.branch_id:
                    scenes_query = scenes_query.filter(
                        Scene.branch_id == extraction_chapter.branch_id,
                        StoryFlow.branch_id == extraction_chapter.branch_id
                    )
                scenes_in_chapter = scenes_query.order_by(Scene.sequence_number).all()

                if not scenes_in_chapter:
                    logger.warning(f"[PLOT_EXTRACTION] No scenes found in chapter {chapter_id}, skipping")
                    return

                # Get actual sequence numbers
                scene_sequence_numbers = [s.sequence_number for s in scenes_in_chapter]
                max_sequence_in_chapter = max(scene_sequence_numbers)
                min_sequence_in_chapter = min(scene_sequence_numbers)

                # Use last_plot_extraction_scene_count as from_sequence
                actual_from_sequence = extraction_chapter.last_plot_extraction_scene_count or 0
                if actual_from_sequence == 0 or actual_from_sequence >= max_sequence_in_chapter:
                    actual_from_sequence = min_sequence_in_chapter - 1

                actual_to_sequence = max_sequence_in_chapter

                # Safety check
                if actual_from_sequence >= actual_to_sequence:
                    logger.warning(f"[PLOT_EXTRACTION] No scenes to process: from_sequence ({actual_from_sequence}) >= to_sequence ({actual_to_sequence})")
                    return

                logger.warning(f"[PLOT_EXTRACTION] Background task - Processing chapter {chapter_id}:")
                logger.warning(f"  - Scenes in chapter: {len(scenes_in_chapter)} (sequences {min_sequence_in_chapter} to {max_sequence_in_chapter})")
                logger.warning(f"  - Using from_sequence={actual_from_sequence}, to_sequence={actual_to_sequence}")

                # Extract plot progress for each scene in the range
                # Collect all extracted events first, then create a single batch
                from ...services.chapter_progress_service import ChapterProgressService
                from ...services.llm.service import UnifiedLLMService
                from ...services.semantic_integration import get_context_manager_for_user

                progress_service = ChapterProgressService(extraction_db)
                local_llm_service = UnifiedLLMService()

                # Check if context-aware extraction is enabled
                use_context_aware = user_settings.get('extraction_model_settings', {}).get('use_context_aware_extraction', False)
                context_manager = None
                if use_context_aware:
                    context_manager = get_context_manager_for_user(user_settings, user_id)
                    logger.info(f"[PLOT_EXTRACTION] Context-aware extraction enabled, will build context for each scene")

                key_events = extraction_chapter.chapter_plot.get("key_events", [])
                all_extracted_events = []
                scenes_processed = 0
                batch_start_sequence = None
                batch_end_sequence = None

                for scene in scenes_in_chapter:
                    if scene.sequence_number > actual_from_sequence and scene.sequence_number <= actual_to_sequence:
                        # Track batch range
                        if batch_start_sequence is None:
                            batch_start_sequence = scene.sequence_number
                        batch_end_sequence = scene.sequence_number

                        # Get the active variant content
                        flow_entry = extraction_db.query(StoryFlow).filter(
                            StoryFlow.scene_id == scene.id,
                            StoryFlow.is_active == True
                        ).first()
                        if flow_entry and flow_entry.scene_variant_id:
                            variant = extraction_db.query(SceneVariant).filter(
                                SceneVariant.id == flow_entry.scene_variant_id
                            ).first()
                            if variant and variant.content:
                                # Get already completed events to only check remaining
                                progress = extraction_chapter.plot_progress or {}
                                already_completed = set(progress.get("completed_events", []))
                                remaining_events = [e for e in key_events if e not in already_completed]

                                if remaining_events:
                                    # Build context if context-aware extraction is enabled
                                    scene_context = None
                                    if use_context_aware and context_manager:
                                        try:
                                            scene_context = await context_manager.build_scene_generation_context(
                                                story_id=story_id,
                                                db=extraction_db,
                                                chapter_id=chapter_id,
                                                branch_id=extraction_chapter.branch_id
                                            )
                                        except Exception as ctx_err:
                                            logger.warning(f"[PLOT_EXTRACTION] Failed to build context, falling back to basic extraction: {ctx_err}")
                                            scene_context = None

                                    # Extract events from this scene
                                    extracted = await progress_service.extract_completed_events(
                                        scene_content=variant.content,
                                        key_events=remaining_events,
                                        llm_service=local_llm_service,
                                        user_id=user_id,
                                        user_settings=user_settings,
                                        context=scene_context,
                                        db=extraction_db
                                    )
                                    all_extracted_events.extend(extracted)

                                scenes_processed += 1

                # Create a single batch with all extracted events
                if scenes_processed > 0 and batch_start_sequence is not None:
                    # Create batch with cumulative events
                    progress_service.create_plot_progress_batch(
                        chapter=extraction_chapter,
                        start_sequence=batch_start_sequence,
                        end_sequence=batch_end_sequence,
                        completed_events=all_extracted_events
                    )

                    # Update last_plot_extraction_scene_count
                    extraction_chapter.last_plot_extraction_scene_count = actual_to_sequence
                    extraction_db.commit()
                    logger.warning(f"[PLOT_EXTRACTION] Created batch for scenes {batch_start_sequence}-{batch_end_sequence} with {len(all_extracted_events)} new events")

                # Get updated progress for logging
                extraction_db.refresh(extraction_chapter)
                progress = extraction_chapter.plot_progress or {}
                completed_count = len(progress.get("completed_events", []))
                logger.info(f"[PLOT_EXTRACTION] Updated chapter {chapter_id} progress: {completed_count} events completed")

            finally:
                extraction_db.close()
    except Exception as e:
        logger.error(f"[PLOT_EXTRACTION] Background plot extraction failed: {e}")
        import traceback
        logger.error(f"[PLOT_EXTRACTION] Traceback: {traceback.format_exc()}")


async def restore_npc_tracking_in_background(
    story_id: int,
    sequence_number: int,
    branch_id: int = None
):
    """Background task to restore NPC tracking from snapshot after scene deletion.

    Includes retry logic with exponential backoff for DB connection pool exhaustion.
    """
    trace_id = f"npc-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()

    logger.info(f"[DELETE-BG:NPC:START] trace_id={trace_id} story_id={story_id} sequence_number={sequence_number} branch_id={branch_id}")

    # Retry configuration for DB connection pool exhaustion
    max_retries = 3
    base_delay = 1.0

    try:
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=delay_complete")

        # Retry loop for DB connection acquisition
        last_error = None
        for attempt in range(max_retries):
            try:
                with get_background_db() as bg_db:
                    logger.info(f"[DELETE-BG:NPC:DB] trace_id={trace_id} attempt={attempt+1}/{max_retries} connection_acquired")

                    # Phase 1: Find the last remaining scene's sequence number (filtered by branch)
                    phase_start = time.perf_counter()
                    last_remaining_scene_query = bg_db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.sequence_number < sequence_number
                    )
                    if branch_id is not None:
                        last_remaining_scene_query = last_remaining_scene_query.filter(Scene.branch_id == branch_id)
                    last_remaining_scene = last_remaining_scene_query.order_by(Scene.sequence_number.desc()).first()
                    logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=query_last_scene duration_ms={(time.perf_counter()-phase_start)*1000:.2f} found={last_remaining_scene is not None}")

                    if last_remaining_scene:
                        # Phase 2: Get snapshot for the last remaining scene (filtered by branch)
                        phase_start = time.perf_counter()
                        snapshot_query = bg_db.query(NPCTrackingSnapshot).filter(
                            NPCTrackingSnapshot.story_id == story_id,
                            NPCTrackingSnapshot.scene_sequence == last_remaining_scene.sequence_number
                        )
                        if branch_id is not None:
                            snapshot_query = snapshot_query.filter(NPCTrackingSnapshot.branch_id == branch_id)
                        snapshot = snapshot_query.first()
                        logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=query_snapshot duration_ms={(time.perf_counter()-phase_start)*1000:.2f} found={snapshot is not None}")

                        if snapshot:
                            # Restore NPCTracking from snapshot
                            snapshot_data = snapshot.snapshot_data or {}
                            npc_count = len(snapshot_data)
                            logger.info(f"[DELETE-BG:NPC:CONTEXT] trace_id={trace_id} snapshot_scene={last_remaining_scene.sequence_number} npcs_in_snapshot={npc_count}")

                            # Phase 3: Delete all existing NPC tracking records for this story and branch
                            phase_start = time.perf_counter()
                            npc_delete_query = bg_db.query(NPCTracking).filter(
                                NPCTracking.story_id == story_id
                            )
                            if branch_id is not None:
                                npc_delete_query = npc_delete_query.filter(NPCTracking.branch_id == branch_id)
                            deleted_count = npc_delete_query.delete()
                            logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=delete_existing duration_ms={(time.perf_counter()-phase_start)*1000:.2f} deleted={deleted_count}")

                            # Phase 4: Restore from snapshot
                            phase_start = time.perf_counter()
                            restored_count = 0
                            for character_name, npc_data in snapshot_data.items():
                                tracking = NPCTracking(
                                    story_id=story_id,
                                    branch_id=branch_id,
                                    character_name=character_name,
                                    entity_type=npc_data.get("entity_type", "CHARACTER"),
                                    total_mentions=npc_data.get("total_mentions", 0),
                                    scene_count=npc_data.get("scene_count", 0),
                                    importance_score=npc_data.get("importance_score", 0.0),
                                    frequency_score=npc_data.get("frequency_score", 0.0),
                                    significance_score=npc_data.get("significance_score", 0.0),
                                    first_appearance_scene=npc_data.get("first_appearance_scene"),
                                    last_appearance_scene=npc_data.get("last_appearance_scene"),
                                    has_dialogue_count=npc_data.get("has_dialogue_count", 0),
                                    has_actions_count=npc_data.get("has_actions_count", 0),
                                    crossed_threshold=npc_data.get("crossed_threshold", False),
                                    user_prompted=npc_data.get("user_prompted", False),
                                    profile_extracted=npc_data.get("profile_extracted", False),
                                    converted_to_character=npc_data.get("converted_to_character", False),
                                    extracted_profile=npc_data.get("extracted_profile", {})
                                )
                                bg_db.add(tracking)
                                restored_count += 1
                            logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=restore_npcs duration_ms={(time.perf_counter()-phase_start)*1000:.2f} restored={restored_count}")

                            # Phase 5: Commit
                            phase_start = time.perf_counter()
                            bg_db.commit()
                            logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=commit duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")

                            total_duration = (time.perf_counter() - task_start) * 1000
                            logger.info(f"[DELETE-BG:NPC:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} restored_from_scene={last_remaining_scene.sequence_number} npcs_restored={restored_count}")
                        else:
                            logger.warning(f"[DELETE-BG:NPC:WARNING] trace_id={trace_id} no_snapshot_found scene={last_remaining_scene.sequence_number}")
                    else:
                        # No remaining scenes - delete all NPC tracking for this branch
                        phase_start = time.perf_counter()
                        npc_delete_query = bg_db.query(NPCTracking).filter(
                            NPCTracking.story_id == story_id
                        )
                        if branch_id is not None:
                            npc_delete_query = npc_delete_query.filter(NPCTracking.branch_id == branch_id)
                        deleted_count = npc_delete_query.delete()
                        bg_db.commit()

                        total_duration = (time.perf_counter() - task_start) * 1000
                        logger.info(f"[DELETE-BG:NPC:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} no_remaining_scenes npcs_deleted={deleted_count}")

                    # Success - exit retry loop
                    return

            except Exception as e:
                last_error = e
                error_str = str(e)
                # Check if it's a pool exhaustion error
                if "QueuePool limit" in error_str or "timeout" in error_str.lower():
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"[DELETE-BG:NPC:RETRY] trace_id={trace_id} attempt={attempt+1}/{max_retries} "
                                     f"pool_exhausted, retrying in {delay:.1f}s error={error_str[:100]}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[DELETE-BG:NPC:EXHAUSTED] trace_id={trace_id} all {max_retries} retries failed error={error_str}")
                        raise
                else:
                    # Not a pool error, re-raise immediately
                    raise

    except Exception as e:
        total_duration = (time.perf_counter() - task_start) * 1000
        logger.error(f"[DELETE-BG:NPC:ERROR] trace_id={trace_id} duration_ms={total_duration:.2f} error={e}")
        import traceback
        logger.error(f"[DELETE-BG:NPC:TRACEBACK] trace_id={trace_id} {traceback.format_exc()}")


async def cleanup_semantic_data_in_background(
    scene_ids: list,
    story_id: int
):
    """Background task to clean up semantic data for deleted scenes.

    Includes retry logic with exponential backoff for DB connection pool exhaustion.
    """
    trace_id = f"semantic-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()
    total_scenes = len(scene_ids)

    logger.info(f"[DELETE-BG:SEMANTIC:START] trace_id={trace_id} story_id={story_id} scene_count={total_scenes} scene_ids={scene_ids[:5]}{'...' if total_scenes > 5 else ''}")

    # Retry configuration for DB connection pool exhaustion
    max_retries = 3
    base_delay = 1.0

    try:
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[DELETE-BG:SEMANTIC:PHASE] trace_id={trace_id} phase=delay_complete")

        from ...services.semantic_integration import cleanup_scene_embeddings

        # Retry loop for DB connection acquisition
        last_error = None
        for attempt in range(max_retries):
            try:
                with get_background_db() as bg_db:
                    logger.info(f"[DELETE-BG:SEMANTIC:DB] trace_id={trace_id} attempt={attempt+1}/{max_retries} connection_acquired")

                    # Determine logging interval (every 10% or every scene if < 10)
                    batch_log_interval = max(1, total_scenes // 10) if total_scenes > 10 else 1

                    cleanup_start = time.perf_counter()
                    cleaned_count = 0
                    failed_count = 0

                    for i, scene_id in enumerate(scene_ids):
                        scene_start = time.perf_counter()
                        try:
                            await cleanup_scene_embeddings(scene_id, bg_db)
                            cleaned_count += 1
                            scene_duration = (time.perf_counter() - scene_start) * 1000

                            # Log progress at intervals or if cleanup takes > 500ms
                            if (i + 1) % batch_log_interval == 0 or scene_duration > 500:
                                elapsed_ms = (time.perf_counter() - cleanup_start) * 1000
                                logger.info(f"[DELETE-BG:SEMANTIC:PROGRESS] trace_id={trace_id} progress={i+1}/{total_scenes} ({((i+1)/total_scenes*100):.1f}%) elapsed_ms={elapsed_ms:.2f} last_scene_ms={scene_duration:.2f} scene_id={scene_id}")
                        except Exception as e:
                            failed_count += 1
                            logger.warning(f"[DELETE-BG:SEMANTIC:SCENE_ERROR] trace_id={trace_id} scene_id={scene_id} error={e}")
                            # Continue with other scenes even if one fails

                    cleanup_duration = (time.perf_counter() - cleanup_start) * 1000
                    total_duration = (time.perf_counter() - task_start) * 1000

                    if failed_count > 0:
                        logger.warning(f"[DELETE-BG:SEMANTIC:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} cleanup_duration_ms={cleanup_duration:.2f} cleaned={cleaned_count} failed={failed_count}")
                    else:
                        logger.info(f"[DELETE-BG:SEMANTIC:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} cleanup_duration_ms={cleanup_duration:.2f} cleaned={cleaned_count} avg_per_scene_ms={cleanup_duration/max(1,cleaned_count):.2f}")

                    # Success - exit retry loop
                    return

            except Exception as e:
                last_error = e
                error_str = str(e)
                # Check if it's a pool exhaustion error
                if "QueuePool limit" in error_str or "timeout" in error_str.lower():
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"[DELETE-BG:SEMANTIC:RETRY] trace_id={trace_id} attempt={attempt+1}/{max_retries} "
                                     f"pool_exhausted, retrying in {delay:.1f}s error={error_str[:100]}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[DELETE-BG:SEMANTIC:EXHAUSTED] trace_id={trace_id} all {max_retries} retries failed error={error_str}")
                        raise
                else:
                    # Not a pool error, re-raise immediately
                    raise

    except Exception as e:
        total_duration = (time.perf_counter() - task_start) * 1000
        logger.error(f"[DELETE-BG:SEMANTIC:ERROR] trace_id={trace_id} duration_ms={total_duration:.2f} error={e}")
        import traceback
        logger.error(f"[DELETE-BG:SEMANTIC:TRACEBACK] trace_id={trace_id} {traceback.format_exc()}")


async def restore_entity_states_in_background(
    story_id: int,
    sequence_number: int,
    min_deleted_seq: int,
    max_deleted_seq: int,
    user_id: int,
    user_settings: dict,
    branch_id: int = None
):
    """Background task to restore entity states after scene deletion.

    Includes retry logic with exponential backoff for DB connection pool exhaustion.
    """
    trace_id = f"entity-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()

    logger.info(f"[DELETE-BG:ENTITY:START] trace_id={trace_id} story_id={story_id} sequence_number={sequence_number} seq_range={min_deleted_seq}-{max_deleted_seq} branch_id={branch_id}")

    # Retry configuration for DB connection pool exhaustion
    max_retries = 3
    base_delay = 1.0

    try:
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=delay_complete")

        from ...services.entity_state_service import EntityStateService

        # Retry loop for DB connection acquisition
        last_error = None
        for attempt in range(max_retries):
            try:
                with get_background_db() as bg_db:
                    logger.info(f"[DELETE-BG:ENTITY:DB] trace_id={trace_id} attempt={attempt+1}/{max_retries} connection_acquired")

                    # Phase 1: Get user settings if not provided
                    phase_start = time.perf_counter()
                    local_user_settings = user_settings
                    if not local_user_settings:
                        user_settings_obj = bg_db.query(UserSettings).filter(
                            UserSettings.user_id == user_id
                        ).first()
                        if user_settings_obj:
                            local_user_settings = user_settings_obj.to_dict()
                        else:
                            logger.warning(f"[DELETE-BG:ENTITY:WARNING] trace_id={trace_id} no_user_settings user_id={user_id}")
                            return
                    logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=get_settings duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")

                    entity_service = EntityStateService(
                        user_id=user_id,
                        user_settings=local_user_settings
                    )

                    # Phase 2: Invalidate batches that overlap with deleted scenes (filtered by branch)
                    phase_start = time.perf_counter()
                    entity_service.invalidate_entity_batches_for_scenes(
                        bg_db, story_id, min_deleted_seq, max_deleted_seq, branch_id=branch_id
                    )
                    logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=invalidate_batches duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")

                    # Phase 3: Check if remaining scenes form a complete batch (filtered by branch)
                    phase_start = time.perf_counter()
                    last_remaining_scene_query = bg_db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.sequence_number < sequence_number
                    )
                    if branch_id is not None:
                        last_remaining_scene_query = last_remaining_scene_query.filter(Scene.branch_id == branch_id)
                    last_remaining_scene = last_remaining_scene_query.order_by(Scene.sequence_number.desc()).first()
                    logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=query_last_scene duration_ms={(time.perf_counter()-phase_start)*1000:.2f} found={last_remaining_scene is not None}")

                    if last_remaining_scene:
                        # Phase 4a: Restore from last complete batch
                        phase_start = time.perf_counter()
                        logger.info(f"[DELETE-BG:ENTITY:CONTEXT] trace_id={trace_id} last_scene_seq={last_remaining_scene.sequence_number}")
                        entity_service.restore_from_last_complete_batch(
                            bg_db, story_id, max_deleted_seq, branch_id=branch_id
                        )
                        logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=restore_from_batch duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")

                        total_duration = (time.perf_counter() - task_start) * 1000
                        logger.info(f"[DELETE-BG:ENTITY:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} action=restored_from_batch")
                    else:
                        # Phase 4b: No remaining scenes - just clear entity states for this branch
                        phase_start = time.perf_counter()
                        char_delete_query = bg_db.query(CharacterState).filter(CharacterState.story_id == story_id)
                        loc_delete_query = bg_db.query(LocationState).filter(LocationState.story_id == story_id)
                        obj_delete_query = bg_db.query(ObjectState).filter(ObjectState.story_id == story_id)
                        if branch_id is not None:
                            char_delete_query = char_delete_query.filter(CharacterState.branch_id == branch_id)
                            loc_delete_query = loc_delete_query.filter(LocationState.branch_id == branch_id)
                            obj_delete_query = obj_delete_query.filter(ObjectState.branch_id == branch_id)
                        char_deleted = char_delete_query.delete()
                        loc_deleted = loc_delete_query.delete()
                        obj_deleted = obj_delete_query.delete()
                        bg_db.commit()
                        logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=clear_states duration_ms={(time.perf_counter()-phase_start)*1000:.2f} char={char_deleted} loc={loc_deleted} obj={obj_deleted}")

                        total_duration = (time.perf_counter() - task_start) * 1000
                        logger.info(f"[DELETE-BG:ENTITY:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} action=cleared_all_states")

                    # Success - exit retry loop
                    return

            except Exception as e:
                last_error = e
                error_str = str(e)
                # Check if it's a pool exhaustion error
                if "QueuePool limit" in error_str or "timeout" in error_str.lower():
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"[DELETE-BG:ENTITY:RETRY] trace_id={trace_id} attempt={attempt+1}/{max_retries} "
                                     f"pool_exhausted, retrying in {delay:.1f}s error={error_str[:100]}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[DELETE-BG:ENTITY:EXHAUSTED] trace_id={trace_id} all {max_retries} retries failed error={error_str}")
                        raise
                else:
                    # Not a pool error, re-raise immediately
                    raise

    except Exception as e:
        total_duration = (time.perf_counter() - task_start) * 1000
        logger.error(f"[DELETE-BG:ENTITY:ERROR] trace_id={trace_id} duration_ms={total_duration:.2f} error={e}")
        import traceback
        logger.error(f"[DELETE-BG:ENTITY:TRACEBACK] trace_id={trace_id} {traceback.format_exc()}")


async def update_working_memory_in_background(
    story_id: int,
    branch_id: int,
    chapter_id: Optional[int],
    scene_sequence: int,
    scene_content: str,
    user_id: int,
    user_settings: dict
):
    """Update working memory after scene generation.

    Tracks scene-to-scene continuity:
    - recent_focus: What was narratively important
    - pending_items: Things mentioned but not acted on
    - character_spotlight: Who needs attention next
    """
    # Check if working memory is enabled in user settings
    context_settings = user_settings.get('context_settings', {})
    if not context_settings.get('enable_working_memory', True):
        logger.debug(f"[WORKING_MEMORY:BG] Disabled for user {user_id}, skipping")
        return

    try:
        # Small delay for database consistency
        await asyncio.sleep(0.2)

        wm_db = SessionLocal()
        try:
            from ...services.entity_state_service import EntityStateService

            entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)

            result = await entity_service.update_working_memory(
                db=wm_db,
                story_id=story_id,
                branch_id=branch_id,
                chapter_id=chapter_id,
                scene_sequence=scene_sequence,
                scene_content=scene_content
            )

            if result:
                logger.info(f"[WORKING_MEMORY:BG] Updated for story {story_id} scene {scene_sequence}")
            else:
                logger.warning(f"[WORKING_MEMORY:BG] No updates for story {story_id} scene {scene_sequence}")

        finally:
            wm_db.close()

    except Exception as e:
        logger.error(f"[WORKING_MEMORY:BG:ERROR] story_id={story_id} scene={scene_sequence} error={e}")
        import traceback
        logger.error(f"[WORKING_MEMORY:BG:TRACEBACK] {traceback.format_exc()}")


async def update_relationship_graph_in_background(
    story_id: int,
    branch_id: int,
    scene_id: int,
    scene_sequence: int,
    scene_content: str,
    user_id: int,
    user_settings: dict
):
    """Update relationship graph after scene generation.

    Extracts character relationship changes and updates:
    - CharacterRelationship events (every change logged)
    - RelationshipSummary (current state for fast context)

    Fetches characters from database internally.
    """
    logger.info(f"[RELATIONSHIP:BG:START] story_id={story_id} scene={scene_sequence} user_id={user_id}")

    # Check if relationship graph is enabled in user settings
    context_settings = user_settings.get('context_settings', {})
    if not context_settings.get('enable_relationship_graph', True):
        logger.info(f"[RELATIONSHIP:BG] Disabled for user {user_id}, skipping")
        return

    try:
        # Small delay for database consistency
        await asyncio.sleep(0.2)

        rel_db = SessionLocal()
        try:
            from ...services.entity_state_service import EntityStateService
            from sqlalchemy import or_

            # Get story characters for this story/branch
            story_characters = rel_db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id,
                StoryCharacter.branch_id == branch_id
            ).all()

            # Get character names
            characters = []
            for sc in story_characters:
                char = rel_db.query(Character).filter(Character.id == sc.character_id).first()
                if char and char.name:
                    characters.append(char.name)

            # Need at least 2 characters for relationship extraction
            if len(characters) < 2:
                logger.debug(f"[RELATIONSHIP:BG] Less than 2 characters ({len(characters)}), skipping")
                return

            entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)

            result = await entity_service.update_relationship_graph(
                db=rel_db,
                story_id=story_id,
                branch_id=branch_id,
                scene_id=scene_id,
                scene_sequence=scene_sequence,
                scene_content=scene_content,
                characters=characters
            )

            if result:
                logger.info(f"[RELATIONSHIP:BG] Updated {len(result)} relationships for story {story_id} scene {scene_sequence}")
            else:
                logger.debug(f"[RELATIONSHIP:BG] No relationship changes for story {story_id} scene {scene_sequence}")

        finally:
            rel_db.close()

    except Exception as e:
        logger.error(f"[RELATIONSHIP:BG:ERROR] story_id={story_id} scene={scene_sequence} error={e}")
        import traceback
        logger.error(f"[RELATIONSHIP:BG:TRACEBACK] {traceback.format_exc()}")


async def initialize_branch_entity_states_in_background(
    story_id: int,
    branch_id: int,
    fork_scene_sequence: int,
    user_id: int,
    user_settings: dict
):
    """Initialize entity states for a newly created branch.

    When a branch is created, entity state batches are cloned but the actual
    entity state rows may not be (due to filter functions checking scene sequence).
    This background task:
    1. Restores entity states from the most recent valid cloned batch
    2. Extracts any remaining scenes up to the fork point

    Args:
        story_id: Story ID
        branch_id: The newly created branch ID
        fork_scene_sequence: The scene sequence where the branch was forked
        user_id: User ID for settings
        user_settings: User settings dictionary
    """
    trace_id = f"branch-entity-init-{uuid.uuid4()}"
    logger.info(f"[BRANCH:ENTITY:START] trace_id={trace_id} story_id={story_id} branch_id={branch_id} fork_seq={fork_scene_sequence}")

    try:
        # Delay to ensure branch creation transaction is committed
        await asyncio.sleep(0.5)

        from ...services.entity_state_service import EntityStateService

        init_db = SessionLocal()
        try:
            entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)

            # Step 1: Find the most recent valid batch for this branch
            # (batches are cloned during branch creation)
            last_batch = entity_service.get_last_valid_batch(
                init_db, story_id, fork_scene_sequence + 1, branch_id=branch_id
            )

            if last_batch:
                # Step 2: Restore entity states from the batch
                restore_result = entity_service.restore_entity_states_from_batch(init_db, last_batch)
                # Commit restore immediately so it's not lost if extraction fails
                init_db.commit()
                logger.info(f"[BRANCH:ENTITY:RESTORE] trace_id={trace_id} batch_id={last_batch.id} "
                           f"chars={restore_result.get('characters_restored', 0)} "
                           f"locs={restore_result.get('locations_restored', 0)} "
                           f"objs={restore_result.get('objects_restored', 0)}")

                # Step 3: Check if there are scenes between batch end and fork point that need extraction
                batch_end_seq = last_batch.end_scene_sequence
                if batch_end_seq < fork_scene_sequence:
                    # Get scenes from batch_end + 1 to fork_scene_sequence
                    from ...models import Scene, StoryFlow
                    remaining_scenes = init_db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.branch_id == branch_id,
                        Scene.sequence_number > batch_end_seq,
                        Scene.sequence_number <= fork_scene_sequence
                    ).order_by(Scene.sequence_number).all()

                    if remaining_scenes:
                        logger.info(f"[BRANCH:ENTITY:EXTRACT] trace_id={trace_id} "
                                   f"extracting {len(remaining_scenes)} scenes ({batch_end_seq + 1}-{fork_scene_sequence})")

                        try:
                            for scene in remaining_scenes:
                                # Get active variant content
                                flow = init_db.query(StoryFlow).filter(
                                    StoryFlow.scene_id == scene.id,
                                    StoryFlow.is_active == True
                                ).first()

                                if flow and flow.scene_variant:
                                    await entity_service.extract_and_update_states(
                                        db=init_db,
                                        story_id=story_id,
                                        scene_id=scene.id,
                                        scene_content=flow.scene_variant.content,
                                        scene_sequence=scene.sequence_number,
                                        branch_id=branch_id
                                    )

                            init_db.commit()
                            logger.info(f"[BRANCH:ENTITY:DONE] trace_id={trace_id} extracted {len(remaining_scenes)} scenes")
                        except Exception as extract_err:
                            logger.warning(f"[BRANCH:ENTITY:EXTRACT_WARN] trace_id={trace_id} extraction failed (restore already committed): {extract_err}")
                    else:
                        logger.info(f"[BRANCH:ENTITY:DONE] trace_id={trace_id} no remaining scenes to extract")
                else:
                    logger.info(f"[BRANCH:ENTITY:DONE] trace_id={trace_id} no remaining scenes to extract")
            else:
                logger.info(f"[BRANCH:ENTITY:SKIP] trace_id={trace_id} no batch found for branch {branch_id}")

            # Step 4: Initialize working memory for the new branch
            # Working memory tracks character focus/spotlight and needs to be computed for the fork point
            try:
                from ...models import Scene, StoryFlow, Chapter
                fork_scene = init_db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.branch_id == branch_id,
                    Scene.sequence_number == fork_scene_sequence
                ).first()

                if fork_scene:
                    flow = init_db.query(StoryFlow).filter(
                        StoryFlow.scene_id == fork_scene.id,
                        StoryFlow.is_active == True
                    ).first()

                    if flow and flow.scene_variant:
                        chapter = init_db.query(Chapter).filter(Chapter.id == fork_scene.chapter_id).first()
                        chapter_id = chapter.id if chapter else None

                        wm_result = await entity_service.update_working_memory(
                            db=init_db,
                            story_id=story_id,
                            branch_id=branch_id,
                            chapter_id=chapter_id,
                            scene_sequence=fork_scene_sequence,
                            scene_content=flow.scene_variant.content
                        )
                        init_db.commit()
                        logger.info(f"[BRANCH:WORKING_MEMORY] trace_id={trace_id} initialized working memory for branch {branch_id}")
            except Exception as wm_err:
                logger.warning(f"[BRANCH:WORKING_MEMORY:WARN] trace_id={trace_id} failed to initialize working memory: {wm_err}")

        finally:
            init_db.close()

    except Exception as e:
        logger.error(f"[BRANCH:ENTITY:ERROR] trace_id={trace_id} error={e}")
        import traceback
        logger.error(f"[BRANCH:ENTITY:TRACEBACK] {traceback.format_exc()}")
