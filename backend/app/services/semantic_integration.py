"""
Semantic Integration Helper

Provides integration functions for semantic memory features
during scene generation and story management.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from datetime import datetime

from .context_manager import ContextManager
from .semantic_memory import get_semantic_memory_service
from .character_memory_service import get_character_memory_service
from .plot_thread_service import get_plot_thread_service
from .llm.prompts import prompt_manager
from .llm.extraction_service import extract_json_robust
from ..config import settings
from ..models import Scene, SceneVariant, Story, Chapter, StoryCharacter, Character
from ..models.scene_event import SceneEvent
from .llm.service import UnifiedLLMService

logger = logging.getLogger(__name__)


def get_context_manager_for_user(user_settings: Dict[str, Any], user_id: int) -> ContextManager:
    """
    Get context manager configured based on user settings.

    The unified ContextManager handles both linear and semantic strategies
    internally based on settings. Factory kept for backward compatibility.

    Args:
        user_settings: User settings dictionary
        user_id: User ID

    Returns:
        ContextManager instance
    """
    return ContextManager(user_settings=user_settings, user_id=user_id)


async def process_scene_embeddings(
    scene_id: int,
    variant_id: int,
    story_id: int,
    scene_content: str,
    sequence_number: int,
    chapter_id: Optional[int],
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session,
    skip_npc_extraction: bool = False,
    skip_plot_extraction: bool = False,
    skip_character_moments: bool = False,
    skip_entity_states: bool = False,
    skip_scene_embedding: bool = False,
    branch_id: Optional[int] = None
) -> Dict[str, bool]:
    """
    Process semantic embeddings and extractions for a new scene
    
    This function:
    1. Creates scene embedding in vector database
    2. Extracts character moments (if enabled)
    3. Extracts plot events (if enabled)
    4. Updates entity states (characters, locations, objects)
    
    Args:
        scene_id: Scene ID
        variant_id: Variant ID
        story_id: Story ID
        scene_content: Scene content text
        sequence_number: Scene sequence number
        chapter_id: Optional chapter ID
        user_id: User ID
        user_settings: User settings
        db: Database session
        branch_id: Optional branch ID (if not provided, uses active branch)
        
    Returns:
        Dictionary with success status for each operation
    """
    results = {
        'scene_embedding': False,
        'character_moments': False,
        'plot_events': False,
        'entity_states': False,
        'npc_tracking': False
    }
    
    # Get active branch if not specified
    if branch_id is None:
        from ..models import StoryBranch
        from sqlalchemy import and_
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        branch_id = active_branch.id if active_branch else None
    
    # Skip semantic embeddings if disabled, but still allow NPC tracking
    skip_semantic = not settings.enable_semantic_memory
    if skip_semantic:
        logger.info("Semantic memory disabled, skipping embeddings")
        # Still allow NPC tracking and entity states even if semantic memory is off
    
    try:
        # Verify scene exists before processing (may have been deleted)
        from ..models import Scene
        scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene_exists:
            logger.warning(f"Scene {scene_id} does not exist, skipping embedding creation")
            return results

        # Look up world_id for cross-story search scope
        story_obj = db.query(Story).filter(Story.id == story_id).first()
        world_id = story_obj.world_id if story_obj else None
        
        # 1. Create scene embedding (only if semantic memory enabled and not already done)
        if not skip_semantic and not skip_scene_embedding:
            logger.info(f"Starting semantic processing for scene {scene_id}")
            semantic_memory = get_semantic_memory_service()
            logger.info(f"Semantic memory service obtained successfully")

            # 1. Create scene embedding
            try:
                logger.info(f"Creating scene embedding for scene {scene_id}")
                embedding_id, embedding_vector = await semantic_memory.add_scene_embedding(
                    scene_id=scene_id,
                    variant_id=variant_id,
                    story_id=story_id,
                    content=scene_content,
                    metadata={
                        'sequence': sequence_number,
                        'chapter_id': chapter_id or 0,
                        'branch_id': branch_id or 0,
                        'characters': []
                    }
                )

                # Store embedding reference in database
                from ..models import SceneEmbedding
                import hashlib

                # Generate content hash for change detection
                content_hash = hashlib.sha256(scene_content.encode('utf-8')).hexdigest()

                # Check if embedding already exists (upsert pattern)
                existing_embedding = db.query(SceneEmbedding).filter(
                    SceneEmbedding.embedding_id == embedding_id
                ).first()

                if existing_embedding:
                    # Update existing record
                    existing_embedding.content_hash = content_hash
                    existing_embedding.sequence_order = sequence_number
                    existing_embedding.chapter_id = chapter_id
                    existing_embedding.content_length = len(scene_content)
                    existing_embedding.embedding = embedding_vector
                    existing_embedding.updated_at = None  # Will trigger onupdate
                    logger.info(f"Updated existing scene embedding: {embedding_id}")
                else:
                    # Create new record
                    scene_embedding = SceneEmbedding(
                        story_id=story_id,
                        branch_id=branch_id,
                        world_id=world_id,
                        scene_id=scene_id,
                        variant_id=variant_id,
                        embedding_id=embedding_id,
                        embedding=embedding_vector,
                        content_hash=content_hash,
                        sequence_order=sequence_number,
                        chapter_id=chapter_id,
                        content_length=len(scene_content)
                    )
                    db.add(scene_embedding)
                    logger.info(f"Created new scene embedding: {embedding_id}")

                db.commit()

                results['scene_embedding'] = True
                logger.info(f"Created scene embedding for scene {scene_id}")
                
            except Exception as e:
                logger.error(f"Failed to create scene embedding: {e}")
                import traceback
                logger.error(f"Scene embedding traceback: {traceback.format_exc()}")
                db.rollback()
        
        # 2. Extract character moments (if enabled in user settings and semantic memory enabled)
        auto_extract_chars = False
        if not skip_semantic and not skip_character_moments:
            auto_extract_chars = True
            if user_settings and user_settings.get("context_settings"):
                auto_extract_chars = user_settings["context_settings"].get(
                    "auto_extract_character_moments", 
                    settings.auto_extract_character_moments
                )
            else:
                auto_extract_chars = settings.auto_extract_character_moments
            
        if auto_extract_chars:
            try:
                char_service = get_character_memory_service()
                moments = await char_service.extract_character_moments(
                    scene_id=scene_id,
                    scene_content=scene_content,
                    story_id=story_id,
                    sequence_number=sequence_number,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                
                results['character_moments'] = len(moments) > 0
                logger.info(f"Extracted {len(moments)} character moments for scene {scene_id}")
                
            except Exception as e:
                logger.error(f"Failed to extract character moments: {e}")
        
        # 3. Extract plot events (if enabled in user settings and semantic memory enabled)
        auto_extract_plot = False
        if not skip_semantic and not skip_plot_extraction:
            auto_extract_plot = True
            if user_settings and user_settings.get("context_settings"):
                auto_extract_plot = user_settings["context_settings"].get(
                    "auto_extract_plot_events", 
                    settings.auto_extract_plot_events
                )
            else:
                auto_extract_plot = settings.auto_extract_plot_events
            
        if auto_extract_plot:
            try:
                plot_service = get_plot_thread_service()
                events = await plot_service.extract_plot_events(
                    scene_id=scene_id,
                    scene_content=scene_content,
                    story_id=story_id,
                    sequence_number=sequence_number,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                
                results['plot_events'] = len(events) > 0
                logger.info(f"Extracted {len(events)} plot events for scene {scene_id}")
                
            except Exception as e:
                logger.error(f"Failed to extract plot events: {e}")
        
        # 4. Extract and update entity states (characters, locations, objects)
        if not skip_entity_states:
            try:
                from .entity_state_service import EntityStateService
                from ..models import Chapter
                entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
                
                # Get chapter location for hierarchical context
                chapter_location = None
                if chapter_id:
                    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
                    if chapter and chapter.location_name:
                        chapter_location = chapter.location_name
                
                entity_results = await entity_service.extract_and_update_states(
                    db=db,
                    story_id=story_id,
                    scene_id=scene_id,
                    scene_sequence=sequence_number,
                    scene_content=scene_content,
                    branch_id=branch_id,
                    chapter_location=chapter_location
                )
                
                results['entity_states'] = entity_results.get('extraction_successful', False)
                logger.info(f"Entity states updated for scene {scene_id}: {entity_results}")
                
            except Exception as e:
                logger.error(f"Failed to update entity states: {e}")
        
        # 5. Extract and track NPCs (if enabled)
        if not skip_npc_extraction:
            npc_tracking_enabled = settings.npc_tracking_enabled
            if user_settings and user_settings.get("context_settings"):
                npc_tracking_enabled = user_settings["context_settings"].get(
                    "npc_tracking_enabled",
                    settings.npc_tracking_enabled
                )
            
            if npc_tracking_enabled:
                try:
                    from .npc_tracking_service import NPCTrackingService
                    npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
                    
                    npc_results = await npc_service.extract_npcs_from_scene(
                        db=db,
                        story_id=story_id,
                        scene_id=scene_id,
                        scene_sequence=sequence_number,
                        scene_content=scene_content,
                        branch_id=branch_id
                    )
                    
                    results['npc_tracking'] = npc_results.get('extraction_successful', False)
                    logger.info(f"NPC tracking completed for scene {scene_id}: {npc_results}")
                    
                except Exception as e:
                    logger.error(f"Failed to track NPCs: {e}")
        
        return results
        
    except RuntimeError as e:
        logger.warning(f"Semantic memory service not available: {e}")
        return results
    except Exception as e:
        logger.error(f"Unexpected error in semantic processing: {e}")
        import traceback
        logger.error(f"Semantic processing traceback: {traceback.format_exc()}")
        return results


def _store_scene_events(
    db: Session,
    events: list,
    story_id: int,
    scene_id: int,
    scene_sequence: int,
    chapter_id: Optional[int],
    branch_id: Optional[int],
    world_id: Optional[int] = None
) -> int:
    """Store extracted scene events in the database. Returns count stored."""
    # Delete existing events for this scene (idempotent re-extraction)
    db.query(SceneEvent).filter(SceneEvent.scene_id == scene_id).delete()

    stored = 0
    for event in events:
        text = event.get('text', '').strip()
        if not text or len(text) < 5:
            continue
        chars = event.get('characters', [])
        if not isinstance(chars, list):
            chars = []
        # Filter: keep only plain strings (person names), drop dicts/objects/non-strings
        chars = [c for c in chars if isinstance(c, str) and len(c) > 0]

        db.add(SceneEvent(
            story_id=story_id,
            branch_id=branch_id,
            world_id=world_id,
            scene_id=scene_id,
            scene_sequence=scene_sequence,
            chapter_id=chapter_id,
            event_text=text[:500],
            characters_involved=chars,
        ))
        stored += 1

    if stored:
        db.flush()
    return stored


async def _try_combined_extraction(
    scenes_data: List[Tuple[int, int, Optional[int], str]],
    story_id: int,
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session,
    results: Dict[str, Any],
    branch_id: Optional[int] = None,
    scene_generation_context: Optional[Dict[str, Any]] = None,
    skip_entity_states: bool = False
) -> bool:
    """
    Extract scene events and NPCs using cache-friendly multi-message structure.

    Replaces the old moments+NPCs combined extraction.

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        from .llm.service import UnifiedLLMService
        from .npc_tracking_service import NPCTrackingService
        from ..models import StoryCharacter, Character

        # Look up world_id for cross-story search scope
        _story_obj = db.query(Story).filter(Story.id == story_id).first()
        _world_id = _story_obj.world_id if _story_obj else None

        # Get character names
        story_characters = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id
        ).all()

        character_names = []
        explicit_character_names = []
        for sc in story_characters:
            char = db.query(Character).filter(Character.id == sc.character_id).first()
            if char:
                character_names.append(char.name)
                explicit_character_names.append(char.name)

        if scene_generation_context is None:
            logger.warning("[EXTRACTION] No scene_generation_context available, skipping combined extraction")
            return False

        logger.info("[EXTRACTION] Using cache-friendly events+NPCs extraction")

        if len(scenes_data) != 1:
            logger.info(f"[EXTRACTION] Skipping combined extraction for {len(scenes_data)} scenes - using separate batch")
            return False

        scene_id, sequence_number, chapter_id_local, scene_content = scenes_data[0]

        try:
            llm_service = UnifiedLLMService()
            response = await llm_service.extract_events_and_npcs_cache_friendly(
                scene_content=scene_content,
                character_names=character_names,
                explicit_character_names=explicit_character_names,
                context=scene_generation_context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
                max_tokens=2000
            )

            if response:
                extraction_results = extract_json_robust(response)

                # Store scene events
                events = extraction_results.get('events', [])
                if events:
                    stored = _store_scene_events(
                        db=db,
                        events=events,
                        story_id=story_id,
                        scene_id=scene_id,
                        scene_sequence=sequence_number,
                        chapter_id=chapter_id_local,
                        branch_id=branch_id,
                        world_id=_world_id,
                    )
                    results['scene_events'] = results.get('scene_events', 0) + stored
                    logger.info(f"[SCENE EVENTS] Extracted {stored} events for scene {scene_id}")

                # Store NPCs
                npcs = extraction_results.get('npcs', [])
                if npcs:
                    npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
                    for npc_data in npcs:
                        try:
                            await npc_service.track_npc(
                                db=db,
                                story_id=story_id,
                                scene_id=scene_id,
                                scene_sequence=sequence_number,
                                npc_data=npc_data,
                                branch_id=branch_id
                            )
                            results['npc_tracking'] += 1
                        except Exception as e:
                            logger.warning(f"Failed to track NPC: {e}")

                logger.info(f"[EXTRACTION] Events+NPCs extraction successful: events={results.get('scene_events', 0)}, npcs={results['npc_tracking']}")
                return True

        except Exception as e:
            logger.warning(f"[EXTRACTION] Cache-friendly events+NPCs extraction failed: {e}")
            return False

    except Exception as e:
        logger.error(f"Events+NPCs extraction failed: {e}", exc_info=True)
        return False


async def run_inline_entity_extraction(
    story_id: int,
    chapter_id: int,
    scene_id: int,
    scene_sequence: int,
    scene_content: str,
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session,
    branch_id: int = None,
    scene_generation_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Fast inline entity extraction for contradiction checking.

    ONLY extracts entity states (characters, locations, objects) and checks for contradictions.
    Does NOT extract: character moments, NPCs, plot events, scene embeddings.

    Uses cache-friendly multi-message structure (same prefix as scene generation).

    Args:
        story_id: Story ID
        chapter_id: Chapter ID
        scene_id: Scene ID
        scene_sequence: Scene sequence number
        scene_content: The generated scene content
        user_id: User ID
        user_settings: User settings
        db: Database session
        branch_id: Branch ID
        scene_generation_context: Context from scene generation (for cache hits)

    Returns:
        Dictionary with entity states updated and contradictions found
    """
    import json
    import time

    start_time = time.perf_counter()
    logger.info(f"[INLINE_ENTITY] Starting inline entity extraction for scene {scene_sequence}")

    results = {
        'entity_states_updated': 0,
        'contradictions_found': 0,
        'extraction_time_ms': 0,
        'success': False
    }

    try:
        # Get story and chapter info
        story = db.query(Story).filter(Story.id == story_id).first()
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

        if not story or not chapter:
            logger.error(f"[INLINE_ENTITY] Story or chapter not found")
            return results

        # Get character names
        story_characters = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id
        ).all()
        character_names = [sc.character.name for sc in story_characters if sc.character]

        # Get chapter location
        chapter_location = chapter.location_name or story.setting or "unspecified location"

        # Get or create LLM service
        llm_service = UnifiedLLMService()

        # Check if we have scene generation context for cache-friendly extraction
        if scene_generation_context is None:
            logger.warning("[INLINE_ENTITY] No scene_generation_context provided, cache may not be optimal")
            # Still proceed, just won't have cache benefits
            scene_generation_context = {}

        # Call the fast entity-only extraction
        logger.info(f"[INLINE_ENTITY] Calling extract_entity_states_cache_friendly")
        raw_response = await llm_service.extract_entity_states_cache_friendly(
            scene_content=scene_content,
            character_names=character_names,
            chapter_location=chapter_location,
            context=scene_generation_context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        extraction_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"[INLINE_ENTITY] LLM response received in {extraction_time:.0f}ms")
        logger.info(f"[INLINE_ENTITY] Raw response: {raw_response[:1500] if raw_response else 'None'}")

        # Parse JSON response using robust extractor
        try:
            entity_states = extract_json_robust(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"[INLINE_ENTITY] Failed to parse JSON response: {e}")
            logger.debug(f"[INLINE_ENTITY] Raw response: {raw_response[:500]}...")
            results['extraction_time_ms'] = extraction_time
            return results

        # Process entity states and check for contradictions
        from .entity_state_service import EntityStateService

        entity_service = EntityStateService(
            user_id=user_id,
            user_settings=user_settings
        )

        # Process state updates (this includes contradiction checking)
        process_result = await entity_service.process_entity_states(
            db=db,
            story_id=story_id,
            branch_id=branch_id,
            scene_id=scene_id,
            scene_sequence=scene_sequence,
            entity_states=entity_states,
            scene_content=scene_content
        )

        # Note: db.commit() is already called inside process_entity_states, no need to call again

        # process_entity_states returns an int (total processed), not a dict
        results['entity_states_updated'] = process_result
        results['contradictions_found'] = 0  # Contradiction checking not yet implemented in process_entity_states
        results['extraction_time_ms'] = (time.perf_counter() - start_time) * 1000
        results['success'] = True

        logger.info(f"[INLINE_ENTITY] Complete: entities={results['entity_states_updated']}, "
                   f"contradictions={results['contradictions_found']}, time={results['extraction_time_ms']:.0f}ms")

        return results

    except Exception as e:
        logger.error(f"[INLINE_ENTITY] Extraction failed: {e}", exc_info=True)
        results['extraction_time_ms'] = (time.perf_counter() - start_time) * 1000
        return results


async def batch_process_scene_extractions(
    story_id: int,
    chapter_id: int,
    from_sequence: int,
    to_sequence: int,
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session,
    branch_id: int = None,
    scene_generation_context: Optional[Dict[str, Any]] = None,
    skip_entity_states: bool = False
) -> Dict[str, Any]:
    """
    Batch process character/NPC extraction for multiple scenes in a chapter.

    This function processes all scenes in a chapter that have been created since
    the last extraction, performing:
    - Character moments extraction
    - NPC tracking
    - Entity states extraction (unless skip_entity_states=True)
    - Plot events extraction
    - Scene embeddings (still created per-scene)

    Args:
        story_id: Story ID
        chapter_id: Chapter ID
        from_sequence: Starting scene sequence number (exclusive, scenes after this)
        to_sequence: Ending scene sequence number (inclusive)
        user_id: User ID
        skip_entity_states: If True, skip entity state processing (already done by inline check)
        user_settings: User settings
        db: Database session
        branch_id: Optional branch ID (if not provided, uses active branch)
        
    Returns:
        Dictionary with aggregated results from all processed scenes
    """
    # CRITICAL: Log immediately when this function actually starts executing
    logger.warning(f"[EXTRACTION] batch_process_scene_extractions() STARTED for chapter {chapter_id}, scenes {from_sequence+1} to {to_sequence}")
    
    results = {
        'scenes_processed': 0,
        'scene_events': 0,
        'character_moments': 0,
        'plot_events': 0,
        'entity_states': 0,
        'npc_tracking': 0,
        'scene_embeddings': 0
    }
    
    # Get active branch if not specified
    if branch_id is None:
        from ..models import StoryBranch
        from sqlalchemy import and_
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        branch_id = active_branch.id if active_branch else None
        logger.warning(f"[EXTRACTION] branch_id was None, looked up active branch: {branch_id} (branch name: {active_branch.name if active_branch else 'N/A'})")
    else:
        logger.warning(f"[EXTRACTION] branch_id provided: {branch_id}")

    # Look up world_id for cross-story search scope
    _batch_story = db.query(Story).filter(Story.id == story_id).first()
    world_id = _batch_story.world_id if _batch_story else None

    try:
        # DEBUG: Log query parameters
        logger.warning(f"[EXTRACTION] Query parameters: story_id={story_id}, chapter_id={chapter_id}, from_sequence={from_sequence}, to_sequence={to_sequence}, branch_id={branch_id}")
        
        # DEBUG: Check what scenes exist in the database matching each filter condition
        total_scenes_in_story = db.query(Scene).filter(Scene.story_id == story_id, Scene.is_deleted == False).count()
        scenes_in_chapter = db.query(Scene).filter(Scene.story_id == story_id, Scene.chapter_id == chapter_id, Scene.is_deleted == False).count()
        scenes_in_range = db.query(Scene).filter(
            Scene.story_id == story_id,
            Scene.sequence_number > from_sequence,
            Scene.sequence_number <= to_sequence,
            Scene.is_deleted == False
        ).count()
        scenes_in_chapter_and_range = db.query(Scene).filter(
            Scene.story_id == story_id,
            Scene.chapter_id == chapter_id,
            Scene.sequence_number > from_sequence,
            Scene.sequence_number <= to_sequence,
            Scene.is_deleted == False
        ).count()
        
        logger.warning(f"[EXTRACTION] Scene counts - Total in story: {total_scenes_in_story}, In chapter: {scenes_in_chapter}, In range: {scenes_in_range}, In chapter+range: {scenes_in_chapter_and_range}")
        
        # DEBUG: Log actual scenes in the range (without chapter filter) to see what we're missing
        scenes_in_range_all_chapters = db.query(Scene).filter(
            Scene.story_id == story_id,
            Scene.sequence_number > from_sequence,
            Scene.sequence_number <= to_sequence,
            Scene.is_deleted == False
        ).order_by(Scene.sequence_number).all()
        
        if scenes_in_range_all_chapters:
            logger.warning(f"[EXTRACTION] Found {len(scenes_in_range_all_chapters)} scenes in range (all chapters):")
            for s in scenes_in_range_all_chapters:
                logger.warning(f"  - Scene {s.id}: seq={s.sequence_number}, chapter_id={s.chapter_id}, is_deleted={s.is_deleted}")
        
        # DEBUG: Check StoryFlow to see if scenes are active (since scenes_count uses StoryFlow)
        from ..models import StoryFlow
        active_flow_query = db.query(StoryFlow).join(Scene).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.is_active == True,
            Scene.chapter_id == chapter_id,
            Scene.sequence_number > from_sequence,
            Scene.sequence_number <= to_sequence,
            Scene.is_deleted == False
        )
        if branch_id:
            active_flow_query = active_flow_query.filter(StoryFlow.branch_id == branch_id)
        active_scenes_in_chapter = active_flow_query.count()
        logger.warning(f"[EXTRACTION] Active scenes in chapter+range (via StoryFlow): {active_scenes_in_chapter}")

        # Get all scenes in the chapter within the sequence range
        # Try querying via StoryFlow first (to match how scenes_count is calculated)
        flow_query = db.query(Scene).join(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.is_active == True,
            Scene.chapter_id == chapter_id,
            Scene.sequence_number > from_sequence,
            Scene.sequence_number <= to_sequence,
            Scene.is_deleted == False
        )
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        scenes_via_flow = flow_query.order_by(Scene.sequence_number).all()

        # Fallback to direct Scene query if StoryFlow query returns nothing
        if not scenes_via_flow:
            logger.warning(f"[EXTRACTION] StoryFlow query returned no scenes, trying direct Scene query")
            scene_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.chapter_id == chapter_id,
                Scene.sequence_number > from_sequence,
                Scene.sequence_number <= to_sequence,
                Scene.is_deleted == False
            )
            if branch_id:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scenes = scene_query.order_by(Scene.sequence_number).all()
        else:
            scenes = scenes_via_flow
        
        if not scenes:
            logger.warning(f"[EXTRACTION] No scenes to process in batch (from_sequence={from_sequence}, to_sequence={to_sequence})")
            logger.warning(f"[EXTRACTION] DEBUG: This might be a timing issue - scenes may not be committed yet in this session")
            return results
        
        logger.warning(f"[EXTRACTION] Batch processing {len(scenes)} scenes for chapter {chapter_id} (sequences {from_sequence+1} to {to_sequence})")
        
        # Prepare scene data for batch extraction
        from ..models import SceneVariant
        scenes_data = []  # List of (scene_id, sequence_number, chapter_id, scene_content) for batch extraction
        scenes_for_embeddings = []  # List of (scene_id, variant_id, sequence_number, scene_content) for per-scene embeddings
        
        for scene in scenes:
            try:
                # Get active variant for the scene (filtered by branch)
                flow_query = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                )
                if branch_id:
                    flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
                flow_entry = flow_query.first()
                
                if not flow_entry or not flow_entry.scene_variant_id:
                    logger.warning(f"No active variant found for scene {scene.id}, skipping")
                    continue
                
                variant = db.query(SceneVariant).filter(
                    SceneVariant.id == flow_entry.scene_variant_id
                ).first()
                
                if not variant or not variant.content:
                    logger.warning(f"No content found for variant {flow_entry.scene_variant_id} of scene {scene.id}, skipping")
                    continue
                
                scene_content = variant.content
                
                # Extract attributes before batch processing to avoid ObjectDeletedError if scene is deleted
                scene_id = scene.id
                variant_id = variant.id
                sequence_number = scene.sequence_number
                
                # Add to batch extraction list
                scenes_data.append((scene_id, sequence_number, chapter_id, scene_content))
                scenes_for_embeddings.append((scene_id, variant_id, sequence_number, scene_content))
                
            except Exception as e:
                logger.error(f"Failed to prepare scene {scene.id} for batch processing: {e}")
                continue
        
        if not scenes_data:
            logger.warning(f"No valid scenes to process in batch")
            return results

        # === STEP 1: Generate scene summary + contextual embedding ===
        # This runs FIRST (before other extractions) to:
        #   a) Warm the LLM cache for subsequent extraction calls
        #   b) Create enriched embeddings immediately
        contextual_embedding_done = False
        if len(scenes_data) == 1 and scene_generation_context is not None:
            scene_id_embed, seq_embed, chapter_id_embed, scene_content_embed = scenes_data[0]
            _, variant_id_embed, _, _ = scenes_for_embeddings[0]

            # Step 1a: Generate 1-sentence summary + specific location via LLM
            summary_result = None
            try:
                llm_service = UnifiedLLMService()
                summary_result = await llm_service.generate_scene_summary_cache_friendly(
                    scene_content=scene_content_embed,
                    context=scene_generation_context,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                if summary_result:
                    logger.warning(f"[EXTRACTION] Scene location: {summary_result.get('location', '')}, summary: {summary_result.get('summary', '')[:80]}")
                else:
                    logger.warning("[EXTRACTION] Scene summary generation returned None")
            except Exception as e:
                logger.warning(f"[EXTRACTION] Scene summary generation failed: {e}")

            # Step 1b: Embed summary-only in pgvector
            # Pure summary without chapter/character prefix — prefix dilutes
            # bi-encoder signal by ~0.25 similarity points
            if settings.enable_semantic_memory:
                try:
                    # Use summary as embedding content; fall back to truncated scene content
                    if summary_result and summary_result.get("summary"):
                        enriched_content = summary_result["summary"]
                    else:
                        enriched_content = scene_content_embed[:1000]

                    semantic_memory = get_semantic_memory_service()
                    embedding_id, embedding_vector = await semantic_memory.add_scene_embedding(
                        scene_id=scene_id_embed,
                        variant_id=variant_id_embed,
                        story_id=story_id,
                        content=enriched_content,
                        metadata={
                            'sequence': seq_embed,
                            'chapter_id': chapter_id or 0,
                            'branch_id': branch_id or 0,
                            'characters': [],
                            'has_contextual_prefix': True
                        }
                    )

                    # Store SceneEmbedding record in DB
                    from ..models import SceneEmbedding
                    import hashlib
                    content_hash = hashlib.sha256(enriched_content.encode('utf-8')).hexdigest()

                    existing_embedding = db.query(SceneEmbedding).filter(
                        SceneEmbedding.embedding_id == embedding_id
                    ).first()

                    if existing_embedding:
                        existing_embedding.content_hash = content_hash
                        existing_embedding.sequence_order = seq_embed
                        existing_embedding.chapter_id = chapter_id
                        existing_embedding.content_length = len(enriched_content)
                        existing_embedding.embedding = embedding_vector
                        existing_embedding.updated_at = None
                    else:
                        scene_embedding = SceneEmbedding(
                            story_id=story_id,
                            branch_id=branch_id,
                            world_id=world_id,
                            scene_id=scene_id_embed,
                            variant_id=variant_id_embed,
                            embedding_id=embedding_id,
                            embedding=embedding_vector,
                            content_hash=content_hash,
                            sequence_order=seq_embed,
                            chapter_id=chapter_id,
                            content_length=len(enriched_content)
                        )
                        db.add(scene_embedding)

                    db.commit()
                    contextual_embedding_done = True
                    results['scene_embeddings'] += 1
                    logger.warning(f"[EXTRACTION] Contextual embedding created: {embedding_id} (prefix: {len(context_prefix)} chars)")

                except Exception as e:
                    logger.warning(f"[EXTRACTION] Contextual embedding failed, will fall back to plain embedding: {e}")
                    db.rollback()

        # Check if combined extraction is enabled (default: True)
        enable_combined = user_settings.get('extraction_model_settings', {}).get('enable_combined_extraction', True)
        
        # BATCH EXTRACTION: Try combined extraction first, fallback to separate calls
        combined_success = False
        if enable_combined:
            try:
                logger.warning(f"[EXTRACTION] Attempting combined extraction for {len(scenes_data)} scenes")
                combined_success = await _try_combined_extraction(
                    scenes_data=scenes_data,
                    story_id=story_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db,
                    results=results,
                    branch_id=branch_id,
                    scene_generation_context=scene_generation_context,
                    skip_entity_states=skip_entity_states
                )
                if combined_success:
                    logger.warning(f"[EXTRACTION] Combined extraction successful!")
            except Exception as e:
                logger.warning(f"[EXTRACTION] Combined extraction failed: {e}, falling back to separate calls")
                combined_success = False
        
        # Fallback to separate calls if combined extraction failed or disabled
        if not combined_success:
            logger.warning(f"[EXTRACTION] Using separate extraction calls")

            # Check if we can use cache-friendly extraction (single scene with context)
            use_cache_friendly = len(scenes_data) == 1 and scene_generation_context is not None
            if use_cache_friendly:
                logger.info("[EXTRACTION] Using cache-friendly fallback extraction for single scene")
                scene_id, sequence_number, chapter_id_local, scene_content = scenes_data[0]

                # Get character names for extraction
                story_characters = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id).all()
                character_names = []
                explicit_names = []
                character_map = {}
                for sc in story_characters:
                    char = db.query(Character).filter(Character.id == sc.character_id).first()
                    if char:
                        character_names.append(char.name)
                        explicit_names.append(char.name.lower())
                        character_map[char.name.lower()] = char

                llm_service = UnifiedLLMService()

                # 1. Cache-friendly NPC extraction
                try:
                    npcs = await llm_service.extract_npcs_cache_friendly(
                        scene_content=scene_content,
                        explicit_names=explicit_names,
                        context=scene_generation_context,
                        user_id=user_id,
                        user_settings=user_settings,
                        db=db
                    )
                    if npcs:
                        from .npc_tracking_service import NPCTrackingService
                        npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
                        for npc_data in npcs:
                            try:
                                await npc_service.track_npc(
                                    db=db,
                                    story_id=story_id,
                                    scene_id=scene_id,
                                    scene_sequence=sequence_number,
                                    npc_data=npc_data,
                                    branch_id=branch_id
                                )
                                results['npc_tracking'] += 1
                            except Exception as e:
                                logger.warning(f"Failed to track NPC: {e}")
                        logger.info(f"[EXTRACTION] Cache-friendly extracted {len(npcs)} NPCs")
                except Exception as e:
                    logger.error(f"Cache-friendly NPC extraction failed: {e}")

                # 2. Cache-friendly scene events extraction (replaces plot events + character moments)
                try:
                    events_response = await llm_service.extract_scene_events_cache_friendly(
                        scene_content=scene_content,
                        character_names=character_names,
                        context=scene_generation_context,
                        user_id=user_id,
                        user_settings=user_settings,
                        db=db
                    )
                    if events_response:
                        events_data = extract_json_robust(events_response)
                        events = events_data.get('events', [])
                        if events:
                            stored = _store_scene_events(
                                db=db,
                                events=events,
                                story_id=story_id,
                                scene_id=scene_id,
                                scene_sequence=sequence_number,
                                chapter_id=chapter_id_local,
                                branch_id=branch_id,
                                world_id=world_id,
                            )
                            results['scene_events'] = results.get('scene_events', 0) + stored
                            logger.info(f"[SCENE EVENTS] Fallback extracted {stored} events for scene {scene_id}")
                except Exception as e:
                    logger.error(f"Cache-friendly scene events extraction failed: {e}")

            else:
                # Original batch extraction path (multiple scenes or no context)
                try:
                    # 1. Batch extract NPCs
                    from .npc_tracking_service import NPCTrackingService
                    npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
                    npc_scenes_data = [(scene_id, seq_num, content) for scene_id, seq_num, _, content in scenes_data]
                    npc_results = await npc_service.extract_npcs_from_scenes_batch(
                        db=db,
                        story_id=story_id,
                        scenes=npc_scenes_data,
                        branch_id=branch_id
                    )
                    if npc_results.get('extraction_successful'):
                        results['npc_tracking'] += npc_results.get('npcs_tracked', 0)
                        logger.warning(f"[EXTRACTION] Batch extracted {npc_results.get('npcs_tracked', 0)} NPCs")
                except Exception as e:
                    logger.error(f"Failed to batch extract NPCs: {e}")

                # Note: Plot events and character moments extraction removed.
                # Scene events are extracted via cache-friendly single-scene path only.
                # Batch path only handles NPCs now.
        
        # PER-SCENE PROCESSING: Scene embeddings and entity states (still per-scene)
        for scene_id, variant_id, sequence_number, scene_content in scenes_for_embeddings:
            try:
                # Verify scene still exists (may have been deleted during batch extraction)
                scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
                if not scene_exists:
                    logger.warning(f"Scene {scene_id} was deleted during extraction, skipping embedding")
                    continue

                # Skip scene embedding if contextual embedding was already created above
                skip_embed = contextual_embedding_done and scene_id == scenes_for_embeddings[0][0]

                # Process scene embeddings (still per-scene)
                # Skip NPC/plot/character/entity extraction since they're done in batch above
                scene_results = await process_scene_embeddings(
                    scene_id=scene_id,
                    variant_id=variant_id,
                    story_id=story_id,
                    scene_content=scene_content,
                    sequence_number=sequence_number,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db,
                    skip_npc_extraction=True,
                    skip_plot_extraction=True,
                    skip_character_moments=True,
                    skip_entity_states=True,
                    skip_scene_embedding=skip_embed
                )

                # Aggregate results (NPCs, plot events, moments already counted above)
                results['scenes_processed'] += 1
                if scene_results.get('scene_embedding'):
                    results['scene_embeddings'] += 1
                if scene_results.get('entity_states'):
                    results['entity_states'] += 1

                logger.debug(f"Processed scene {scene_id} (sequence {sequence_number}): "
                           f"embedding={scene_results.get('scene_embedding')}, "
                           f"entities={scene_results.get('entity_states')}, "
                           f"skip_embed={skip_embed}")

            except Exception as e:
                logger.error(f"Failed to process scene {scene_id} embeddings: {e}")
                # Continue with next scene
                continue
        
        logger.warning(f"[EXTRACTION] Batch processing complete: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Unexpected error in batch processing: {e}")
        import traceback
        logger.error(f"Batch processing traceback: {traceback.format_exc()}")
        return results


async def cleanup_scene_embeddings(scene_id: int, db: Session):
    """
    Clean up all semantic data for a deleted scene

    Args:
        scene_id: Scene ID to clean up
        db: Database session
    """
    try:
        logger.info(f"[CLEANUP] Starting cleanup for scene {scene_id}")

        # Get semantic services
        char_service = get_character_memory_service()
        plot_service = get_plot_thread_service()

        # Delete character moments
        await char_service.delete_character_moments(scene_id, db)
        logger.debug(f"[CLEANUP] Deleted character moments for scene {scene_id}")

        # Delete plot events
        await plot_service.delete_plot_events(scene_id, db)
        logger.debug(f"[CLEANUP] Deleted plot events for scene {scene_id}")

        # Delete scene events
        scene_events_deleted = db.query(SceneEvent).filter(
            SceneEvent.scene_id == scene_id
        ).delete()
        logger.debug(f"[CLEANUP] Deleted {scene_events_deleted} scene events for scene {scene_id}")

        # Delete NPC mentions
        from ..models.npc_tracking import NPCMention
        npc_mentions_deleted = db.query(NPCMention).filter(
            NPCMention.scene_id == scene_id
        ).delete()
        logger.debug(f"[CLEANUP] Deleted {npc_mentions_deleted} NPC mentions for scene {scene_id}")

        # Delete chronicle and lorebook entries
        from ..models import CharacterChronicle, LocationLorebook
        chronicles_deleted = db.query(CharacterChronicle).filter(
            CharacterChronicle.scene_id == scene_id
        ).delete()
        lorebook_deleted = db.query(LocationLorebook).filter(
            LocationLorebook.scene_id == scene_id
        ).delete()
        logger.info(f"[CLEANUP] Deleted {chronicles_deleted} chronicle + {lorebook_deleted} lorebook entries for scene {scene_id}")

        # Delete scene embeddings from database (vectors are on the rows, deleted with them)
        from ..models import SceneEmbedding
        scene_embeddings_deleted = db.query(SceneEmbedding).filter(
            SceneEmbedding.scene_id == scene_id
        ).delete()

        db.commit()
        logger.info(f"[CLEANUP] Completed cleanup for scene {scene_id}: "
                   f"character moments, plot events, {scene_embeddings_deleted} scene embeddings removed")

    except Exception as e:
        logger.error(f"Failed to cleanup scene embeddings: {e}")
        db.rollback()


def get_semantic_stats(story_id: int, db: Session, branch_id: int = None) -> Dict[str, Any]:
    """
    Get statistics about semantic data for a story
    
    Args:
        story_id: Story ID
        db: Database session
        branch_id: Optional branch ID for filtering
        
    Returns:
        Dictionary with semantic memory statistics
    """
    try:
        from ..models import SceneEmbedding, CharacterMemory, PlotEvent
        
        stats = {
            'enabled': settings.enable_semantic_memory,
            'scene_embeddings': 0,
            'character_moments': 0,
            'plot_events': 0,
            'unresolved_threads': 0
        }
        
        if not settings.enable_semantic_memory:
            return stats
        
        # Count scene embeddings (filter by branch to avoid cross-branch contamination)
        scene_emb_query = db.query(SceneEmbedding).filter(
            SceneEmbedding.story_id == story_id
        )
        if branch_id:
            scene_emb_query = scene_emb_query.filter(SceneEmbedding.branch_id == branch_id)
        stats['scene_embeddings'] = scene_emb_query.count()
        
        # Count character moments (filter by branch)
        char_mem_query = db.query(CharacterMemory).filter(
            CharacterMemory.story_id == story_id
        )
        if branch_id:
            char_mem_query = char_mem_query.filter(CharacterMemory.branch_id == branch_id)
        stats['character_moments'] = char_mem_query.count()
        
        # Count plot events (filter by branch)
        plot_query = db.query(PlotEvent).filter(
            PlotEvent.story_id == story_id
        )
        if branch_id:
            plot_query = plot_query.filter(PlotEvent.branch_id == branch_id)
        stats['plot_events'] = plot_query.count()
        
        # Count unresolved threads (filter by branch)
        unresolved_query = db.query(PlotEvent).filter(
            PlotEvent.story_id == story_id,
            PlotEvent.is_resolved == False
        )
        if branch_id:
            unresolved_query = unresolved_query.filter(PlotEvent.branch_id == branch_id)
        stats['unresolved_threads'] = unresolved_query.count()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get semantic stats: {e}")
        return {'enabled': False, 'error': str(e)}

