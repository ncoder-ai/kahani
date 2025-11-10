"""
Semantic Integration Helper

Provides integration functions for semantic memory features
during scene generation and story management.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session

from .semantic_context_manager import SemanticContextManager, create_semantic_context_manager
from .context_manager import ContextManager
from .semantic_memory import get_semantic_memory_service
from .character_memory_service import get_character_memory_service
from .plot_thread_service import get_plot_thread_service
from ..config import settings
from ..models import Scene, SceneVariant, Story, Chapter

logger = logging.getLogger(__name__)


def get_context_manager_for_user(user_settings: Dict[str, Any], user_id: int) -> ContextManager:
    """
    Get appropriate context manager based on configuration
    
    Args:
        user_settings: User settings dictionary
        user_id: User ID
        
    Returns:
        ContextManager (or SemanticContextManager if enabled)
    """
    # Check if semantic memory is enabled globally
    if not settings.enable_semantic_memory:
        logger.debug("Semantic memory disabled globally, using standard ContextManager")
        return ContextManager(user_settings=user_settings, user_id=user_id)
    
    # Check user-specific settings
    if user_settings and user_settings.get("context_strategy") == "linear":
        logger.debug("User prefers linear context, using standard ContextManager")
        return ContextManager(user_settings=user_settings, user_id=user_id)
    
    # Use semantic context manager
    try:
        logger.debug("Using SemanticContextManager for hybrid context")
        return create_semantic_context_manager(user_settings=user_settings, user_id=user_id)
    except Exception as e:
        logger.warning(f"Failed to create SemanticContextManager, falling back to standard: {e}")
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
    skip_entity_states: bool = False
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
    
    # Skip semantic embeddings if disabled, but still allow NPC tracking
    skip_semantic = not settings.enable_semantic_memory
    if skip_semantic:
        logger.info("Semantic memory disabled, skipping embeddings")
        # Still allow NPC tracking and entity states even if semantic memory is off
    
    try:
        # 1. Create scene embedding (only if semantic memory enabled)
        if not skip_semantic:
            logger.info(f"Starting semantic processing for scene {scene_id}")
            semantic_memory = get_semantic_memory_service()
            logger.info(f"Semantic memory service obtained successfully")
            
            # 1. Create scene embedding
            try:
                logger.info(f"Creating scene embedding for scene {scene_id}")
                embedding_id = await semantic_memory.add_scene_embedding(
                    scene_id=scene_id,
                    variant_id=variant_id,
                    story_id=story_id,
                    content=scene_content,
                    metadata={
                        'sequence': sequence_number,
                        'chapter_id': chapter_id or 0,
                        'characters': []  # Could be enhanced later
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
                    existing_embedding.updated_at = None  # Will trigger onupdate
                    logger.info(f"Updated existing scene embedding: {embedding_id}")
                else:
                    # Create new record
                    scene_embedding = SceneEmbedding(
                        story_id=story_id,
                        scene_id=scene_id,
                        variant_id=variant_id,
                        embedding_id=embedding_id,
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
                entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
                
                entity_results = await entity_service.extract_and_update_states(
                    db=db,
                    story_id=story_id,
                    scene_id=scene_id,
                    scene_sequence=sequence_number,
                    scene_content=scene_content
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
                        scene_content=scene_content
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


async def _try_combined_extraction(
    scenes_data: List[Tuple[int, int, Optional[int], str]],
    story_id: int,
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session,
    results: Dict[str, Any]
) -> bool:
    """
    Try to extract character moments, NPCs, and plot events in a single combined LLM call.
    
    Args:
        scenes_data: List of (scene_id, sequence_number, chapter_id, scene_content) tuples
        story_id: Story ID
        user_id: User ID
        user_settings: User settings
        db: Database session
        results: Results dictionary to update
        
    Returns:
        True if combined extraction succeeded, False otherwise
    """
    try:
        from .llm.extraction_service import ExtractionLLMService
        from .npc_tracking_service import NPCTrackingService
        from .character_memory_service import get_character_memory_service
        from .plot_thread_service import get_plot_thread_service
        from ..models import StoryCharacter, Character, PlotEvent
        
        # Check if extraction model is enabled
        extraction_settings = user_settings.get('extraction_model_settings', {})
        if not extraction_settings.get('enabled', False):
            logger.info("[EXTRACTION] Extraction model not enabled, skipping combined extraction")
            return False
        
        # Get extraction service
        url = extraction_settings.get('url', 'http://localhost:1234/v1')
        model = extraction_settings.get('model_name', 'qwen2.5-3b-instruct')
        api_key = extraction_settings.get('api_key', '')
        temperature = extraction_settings.get('temperature', 0.3)
        max_tokens = extraction_settings.get('max_tokens', 1000)
        
        extraction_service = ExtractionLLMService(
            url=url,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Get character names for character moments
        story_characters = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id
        ).all()
        
        character_names = []
        explicit_character_names = []
        character_map = {}
        for sc in story_characters:
            char = db.query(Character).filter(Character.id == sc.character_id).first()
            if char:
                character_names.append(char.name)
                explicit_character_names.append(char.name)
                character_map[char.name.lower()] = char
        
        # Build batch content with scene markers
        scenes_text = []
        for scene_id, sequence_number, chapter_id, scene_content in scenes_data:
            scenes_text.append(f"=== SCENE {sequence_number} (ID: {scene_id}) ===\n{scene_content}\n")
        batch_content = "\n".join(scenes_text)
        
        # Get thread context for plot events
        plot_service = get_plot_thread_service()
        existing_threads = await plot_service.get_unresolved_threads(story_id, db)
        thread_context = ""
        if existing_threads:
            thread_list = [f"- {t['description']}" for t in existing_threads[:5]]
            thread_context = f"\n{chr(10).join(thread_list)}"
        
        # Call combined extraction
        num_scenes = len(scenes_data)
        combined_results = await extraction_service.extract_all_batch(
            batch_content=batch_content,
            character_names=character_names,
            explicit_character_names=explicit_character_names,
            thread_context=thread_context,
            num_scenes=num_scenes
        )
        
        # Validate results - need at least one non-empty section
        entity_states = combined_results.get('entity_states', {})
        has_entity_states = (
            (entity_states.get('characters') and len(entity_states['characters']) > 0) or
            (entity_states.get('locations') and len(entity_states['locations']) > 0) or
            (entity_states.get('objects') and len(entity_states['objects']) > 0)
        )
        has_results = (
            (combined_results.get('character_moments') and len(combined_results['character_moments']) > 0) or
            (combined_results.get('npcs') and len(combined_results['npcs']) > 0) or
            (combined_results.get('plot_events') and len(combined_results['plot_events']) > 0) or
            has_entity_states
        )
        
        if not has_results:
            logger.warning("[EXTRACTION] Combined extraction returned empty results")
            return False
        
        # Process character moments using existing service logic
        if combined_results.get('character_moments'):
            try:
                from .character_memory_service import get_character_memory_service
                from ..utils.scene_verification import map_moments_to_scenes
                from ..models.semantic_memory import CharacterMemory, MomentType
                from datetime import datetime
                
                char_service = get_character_memory_service()
                moments_data = combined_results['character_moments']
                
                # Map moments to scenes
                scenes_for_verification = [(scene_id, content) for scene_id, _, _, content in scenes_data]
                
                # Group by character and map to scenes
                all_created_moments = {}
                for char_name in character_names:
                    char_moments = [m for m in moments_data if m.get('character_name', '').strip().lower() == char_name.lower()]
                    if not char_moments:
                        continue
                    
                    scene_moment_map = map_moments_to_scenes(char_moments, scenes_for_verification, char_name)
                    
                    # Create CharacterMemory entries
                    for scene_id, sequence_number, chapter_id, scene_content in scenes_data:
                        moments_for_scene = scene_moment_map.get(scene_id, [])
                        if scene_id not in all_created_moments:
                            all_created_moments[scene_id] = []
                        
                        for moment_data in moments_for_scene:
                            if moment_data.get('confidence', 0) < settings.extraction_confidence_threshold:
                                continue
                            
                            char_name_moment = moment_data.get('character_name', '').strip()
                            if char_name_moment.lower() not in character_map:
                                continue
                            
                            character = character_map[char_name_moment.lower()]
                            moment_type = moment_data.get('moment_type', 'action')
                            content = moment_data.get('content', '')
                            confidence = moment_data.get('confidence', 70)
                            
                            # Create embedding
                            embedding_id = await char_service.semantic_memory.add_character_moment(
                                character_id=character.id,
                                character_name=character.name,
                                scene_id=scene_id,
                                story_id=story_id,
                                moment_type=moment_type,
                                content=content,
                                metadata={
                                    'sequence': sequence_number,
                                    'timestamp': datetime.utcnow().isoformat()
                                }
                            )
                            
                            # Check if already exists
                            existing_memory = db.query(CharacterMemory).filter(
                                CharacterMemory.embedding_id == embedding_id
                            ).first()
                            
                            if existing_memory:
                                continue
                            
                            # Create database record
                            memory = CharacterMemory(
                                character_id=character.id,
                                scene_id=scene_id,
                                story_id=story_id,
                                moment_type=MomentType(moment_type),
                                content=content,
                                embedding_id=embedding_id,
                                sequence_order=sequence_number,
                                chapter_id=chapter_id,
                                extracted_automatically=True,
                                confidence_score=confidence
                            )
                            db.add(memory)
                            all_created_moments[scene_id].append(memory)
                
                db.commit()
                total_moments = sum(len(moments) for moments in all_created_moments.values())
                results['character_moments'] += total_moments
                logger.warning(f"[EXTRACTION] Combined: extracted {total_moments} character moments")
            except Exception as e:
                logger.error(f"Failed to process combined character moments: {e}")
                db.rollback()
        
        # Process NPCs using existing service logic
        if combined_results.get('npcs'):
            try:
                from .npc_tracking_service import NPCTrackingService
                from ..utils.scene_verification import map_npcs_to_scenes
                from ..models.npc_tracking import NPCMention
                
                npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
                npcs_data = combined_results['npcs']
                
                # Validate NPCs
                validated_npcs = npc_service._validate_npcs(npcs_data)
                
                # Map to scenes
                npc_scenes_data = [(scene_id, seq_num, content) for scene_id, seq_num, _, content in scenes_data]
                scenes_for_verification = [(scene_id, content) for scene_id, _, _, content in scenes_data]
                scene_npc_map = map_npcs_to_scenes(validated_npcs, scenes_for_verification)
                
                # Store NPCs using existing logic
                explicit_names_set = set(name.lower() for name in explicit_character_names)
                total_npcs = 0
                
                def to_bool(value):
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.lower() in ('true', '1', 'yes')
                    return bool(value)
                
                for scene_id, sequence_number, chapter_id, scene_content in scenes_data:
                    npcs_for_scene = scene_npc_map.get(scene_id, [])
                    for npc_data_scene in npcs_for_scene:
                        npc_name = npc_data_scene.get('name', '').strip()
                        if not npc_name or npc_name.lower() in explicit_names_set:
                            continue
                        
                        # Check importance filters
                        mention_count = npc_data_scene.get('mention_count', 0)
                        has_dialogue = to_bool(npc_data_scene.get('has_dialogue', False))
                        has_actions = to_bool(npc_data_scene.get('has_actions', False))
                        
                        if mention_count >= 2 or has_dialogue or has_actions:
                            # Store mention
                            mention = NPCMention(
                                story_id=story_id,
                                scene_id=scene_id,
                                character_name=npc_name,
                                sequence_number=sequence_number,
                                mention_count=mention_count,
                                has_dialogue=has_dialogue,
                                has_actions=has_actions,
                                has_relationships=to_bool(npc_data_scene.get('has_relationships', False)),
                                context_snippets=npc_data_scene.get('context_snippets', []),
                                extracted_properties=npc_data_scene.get('properties', {})
                            )
                            db.add(mention)
                            
                            # Update tracking
                            await npc_service._update_npc_tracking(
                                db, story_id, npc_name, sequence_number, npc_data_scene
                            )
                            total_npcs += 1
                
                db.commit()
                results['npc_tracking'] += total_npcs
                logger.warning(f"[EXTRACTION] Combined: extracted {total_npcs} NPCs")
            except Exception as e:
                logger.error(f"Failed to process combined NPCs: {e}")
                db.rollback()
        
        # Process plot events using existing service logic
        if combined_results.get('plot_events'):
            try:
                from ..utils.scene_verification import map_events_to_scenes
                from ..models.semantic_memory import PlotEvent, EventType
                
                events_data = combined_results['plot_events']
                
                # Filter by importance and confidence
                filtered_events = [
                    e for e in events_data
                    if e.get('importance', 0) >= 60 and e.get('confidence', 0) >= 70
                ]
                
                # Map to scenes
                scenes_for_verification = [(scene_id, content) for scene_id, _, _, content in scenes_data]
                scene_event_map = map_events_to_scenes(filtered_events, scenes_for_verification)
                
                # Create PlotEvent entries
                plot_service = get_plot_thread_service()
                total_events = 0
                
                for scene_id, sequence_number, chapter_id, scene_content in scenes_data:
                    events_for_scene = scene_event_map.get(scene_id, [])
                    
                    for event_data in events_for_scene:
                        event_type = event_data.get('event_type', 'complication')
                        description = event_data.get('description', '')
                        importance = event_data.get('importance', 50)
                        confidence = event_data.get('confidence', 70)
                        involved_chars = event_data.get('involved_characters', [])
                        
                        if confidence < settings.extraction_confidence_threshold or importance < 30:
                            continue
                        
                        # Generate thread ID
                        thread_id = plot_service._generate_thread_id(description, event_type)
                        
                        # Create PlotEvent
                        plot_event = PlotEvent(
                            story_id=story_id,
                            scene_id=scene_id,
                            sequence_number=sequence_number,
                            chapter_id=chapter_id,
                            event_type=EventType(event_type),
                            description=description,
                            importance_score=importance,
                            confidence_score=confidence,
                            thread_id=thread_id,
                            involved_characters=involved_chars,
                            extracted_automatically=True
                        )
                        db.add(plot_event)
                        total_events += 1
                
                db.commit()
                results['plot_events'] += total_events
                logger.warning(f"[EXTRACTION] Combined: extracted {total_events} plot events")
            except Exception as e:
                logger.error(f"Failed to process combined plot events: {e}")
                db.rollback()
        
        # Process entity states using existing service logic
        if combined_results.get('entity_states'):
            try:
                from .entity_state_service import EntityStateService
                from ..models import StoryCharacter, Character
                
                entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
                entity_states_data = combined_results['entity_states']
                
                # Get the last scene sequence number (most recent scene in batch)
                last_sequence = max([seq for _, seq, _, _ in scenes_data]) if scenes_data else 0
                
                total_entity_states = 0
                
                # Process character states (apply once per character, using last scene sequence)
                if entity_states_data.get('characters'):
                    for char_update in entity_states_data['characters']:
                        try:
                            await entity_service._update_character_state(
                                db, story_id, last_sequence, char_update
                            )
                            total_entity_states += 1
                        except Exception as e:
                            logger.warning(f"Failed to update character state for {char_update.get('name', 'unknown')}: {e}")
                            continue
                
                # Process location states
                if entity_states_data.get('locations'):
                    for loc_update in entity_states_data['locations']:
                        try:
                            await entity_service._update_location_state(
                                db, story_id, last_sequence, loc_update
                            )
                            total_entity_states += 1
                        except Exception as e:
                            logger.warning(f"Failed to update location state for {loc_update.get('name', 'unknown')}: {e}")
                            continue
                
                # Process object states
                if entity_states_data.get('objects'):
                    for obj_update in entity_states_data['objects']:
                        try:
                            await entity_service._update_object_state(
                                db, story_id, last_sequence, obj_update
                            )
                            total_entity_states += 1
                        except Exception as e:
                            logger.warning(f"Failed to update object state for {obj_update.get('name', 'unknown')}: {e}")
                            continue
                
                db.commit()
                results['entity_states'] += total_entity_states
                logger.warning(f"[EXTRACTION] Combined: extracted {total_entity_states} entity states")
            except Exception as e:
                logger.error(f"Failed to process combined entity states: {e}")
                db.rollback()
        
        return True
        
    except Exception as e:
        logger.error(f"Combined extraction failed: {e}", exc_info=True)
        return False


async def batch_process_scene_extractions(
    story_id: int,
    chapter_id: int,
    from_sequence: int,
    to_sequence: int,
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session
) -> Dict[str, Any]:
    """
    Batch process character/NPC extraction for multiple scenes in a chapter.
    
    This function processes all scenes in a chapter that have been created since
    the last extraction, performing:
    - Character moments extraction
    - NPC tracking
    - Entity states extraction
    - Plot events extraction
    - Scene embeddings (still created per-scene)
    
    Args:
        story_id: Story ID
        chapter_id: Chapter ID
        from_sequence: Starting scene sequence number (exclusive, scenes after this)
        to_sequence: Ending scene sequence number (inclusive)
        user_id: User ID
        user_settings: User settings
        db: Database session
        
    Returns:
        Dictionary with aggregated results from all processed scenes
    """
    # CRITICAL: Log immediately when this function actually starts executing
    logger.warning(f"[EXTRACTION] batch_process_scene_extractions() STARTED for chapter {chapter_id}, scenes {from_sequence+1} to {to_sequence}")
    
    results = {
        'scenes_processed': 0,
        'character_moments': 0,
        'plot_events': 0,
        'entity_states': 0,
        'npc_tracking': 0,
        'scene_embeddings': 0
    }
    
    try:
        # Get all scenes in the chapter within the sequence range
        scenes = db.query(Scene).filter(
            Scene.story_id == story_id,
            Scene.chapter_id == chapter_id,
            Scene.sequence_number > from_sequence,
            Scene.sequence_number <= to_sequence,
            Scene.is_deleted == False
        ).order_by(Scene.sequence_number).all()
        
        if not scenes:
            logger.warning(f"[EXTRACTION] No scenes to process in batch (from_sequence={from_sequence}, to_sequence={to_sequence})")
            return results
        
        logger.warning(f"[EXTRACTION] Batch processing {len(scenes)} scenes for chapter {chapter_id} (sequences {from_sequence+1} to {to_sequence})")
        
        # Prepare scene data for batch extraction
        from ..models import SceneVariant, StoryFlow
        scenes_data = []  # List of (scene_id, sequence_number, chapter_id, scene_content) for batch extraction
        scenes_for_embeddings = []  # List of (scene, variant, scene_content) for per-scene embeddings
        
        for scene in scenes:
            try:
                # Get active variant for the scene
                flow_entry = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()
                
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
                
                # Add to batch extraction list
                scenes_data.append((scene.id, scene.sequence_number, chapter_id, scene_content))
                scenes_for_embeddings.append((scene, variant, scene_content))
                
            except Exception as e:
                logger.error(f"Failed to prepare scene {scene.id} for batch processing: {e}")
                continue
        
        if not scenes_data:
            logger.warning(f"No valid scenes to process in batch")
            return results
        
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
                    results=results
                )
                if combined_success:
                    logger.warning(f"[EXTRACTION] Combined extraction successful!")
            except Exception as e:
                logger.warning(f"[EXTRACTION] Combined extraction failed: {e}, falling back to separate calls")
                combined_success = False
        
        # Fallback to separate calls if combined extraction failed or disabled
        if not combined_success:
            logger.warning(f"[EXTRACTION] Using separate extraction calls")
            try:
                # 1. Batch extract NPCs
                from .npc_tracking_service import NPCTrackingService
                npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
                npc_scenes_data = [(scene_id, seq_num, content) for scene_id, seq_num, _, content in scenes_data]
                npc_results = await npc_service.extract_npcs_from_scenes_batch(
                    db=db,
                    story_id=story_id,
                    scenes=npc_scenes_data
                )
                if npc_results.get('extraction_successful'):
                    results['npc_tracking'] += npc_results.get('npcs_tracked', 0)
                    logger.warning(f"[EXTRACTION] Batch extracted {npc_results.get('npcs_tracked', 0)} NPCs")
            except Exception as e:
                logger.error(f"Failed to batch extract NPCs: {e}")
            
            try:
                # 2. Batch extract plot events
                plot_service = get_plot_thread_service()
                plot_events_map = await plot_service.extract_plot_events_from_scenes_batch(
                    scenes=scenes_data,
                    story_id=story_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                total_plot_events = sum(len(events) for events in plot_events_map.values())
                results['plot_events'] += total_plot_events
                logger.warning(f"[EXTRACTION] Batch extracted {total_plot_events} plot events")
            except Exception as e:
                logger.error(f"Failed to batch extract plot events: {e}")
            
            try:
                # 3. Batch extract character moments
                char_service = get_character_memory_service()
                moments_map = await char_service.extract_character_moments_from_scenes_batch(
                    scenes=scenes_data,
                    story_id=story_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                total_moments = sum(len(moments) for moments in moments_map.values())
                results['character_moments'] += total_moments
                logger.warning(f"[EXTRACTION] Batch extracted {total_moments} character moments")
            except Exception as e:
                logger.error(f"Failed to batch extract character moments: {e}")
        
        # PER-SCENE PROCESSING: Scene embeddings and entity states (still per-scene)
        for scene, variant, scene_content in scenes_for_embeddings:
            try:
                # Process scene embeddings (still per-scene)
                # Skip NPC/plot/character/entity extraction since they're done in batch above
                scene_results = await process_scene_embeddings(
                    scene_id=scene.id,
                    variant_id=variant.id,
                    story_id=story_id,
                    scene_content=scene_content,
                    sequence_number=scene.sequence_number,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db,
                    skip_npc_extraction=True,
                    skip_plot_extraction=True,
                    skip_character_moments=True,
                    skip_entity_states=True
                )
                
                # Aggregate results (NPCs, plot events, moments already counted above)
                results['scenes_processed'] += 1
                if scene_results.get('scene_embedding'):
                    results['scene_embeddings'] += 1
                if scene_results.get('entity_states'):
                    results['entity_states'] += 1
                
                logger.debug(f"Processed scene {scene.id} (sequence {scene.sequence_number}): "
                           f"embedding={scene_results.get('scene_embedding')}, "
                           f"entities={scene_results.get('entity_states')}")
                
            except Exception as e:
                logger.error(f"Failed to process scene {scene.id} embeddings: {e}")
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
        semantic_memory = get_semantic_memory_service()
        
        # Delete character moments
        char_service.delete_character_moments(scene_id, db)
        logger.debug(f"[CLEANUP] Deleted character moments for scene {scene_id}")
        
        # Delete plot events
        plot_service.delete_plot_events(scene_id, db)
        logger.debug(f"[CLEANUP] Deleted plot events for scene {scene_id}")
        
        # Delete scene embeddings from database
        from ..models import SceneEmbedding
        scene_embeddings = db.query(SceneEmbedding).filter(
            SceneEmbedding.scene_id == scene_id
        ).all()
        
        # Delete from vector database (ChromaDB)
        embeddings_deleted = 0
        for embedding in scene_embeddings:
            try:
                # Get variant ID from embedding
                parts = embedding.embedding_id.split('_')
                if len(parts) >= 3:
                    variant_id = int(parts[-1].replace('v', ''))
                    semantic_memory.delete_scene_embedding(scene_id, variant_id)
                    embeddings_deleted += 1
                    logger.debug(f"[CLEANUP] Deleted scene embedding {embedding.embedding_id} from ChromaDB")
            except Exception as e:
                logger.warning(f"[CLEANUP] Failed to delete vector embedding {embedding.embedding_id}: {e}")
        
        logger.debug(f"[CLEANUP] Deleted {embeddings_deleted} scene embeddings from ChromaDB for scene {scene_id}")
        
        # Delete database records
        scene_embeddings_deleted = db.query(SceneEmbedding).filter(
            SceneEmbedding.scene_id == scene_id
        ).delete()
        
        db.commit()
        logger.info(f"[CLEANUP] Completed cleanup for scene {scene_id}: "
                   f"character moments, plot events, {scene_embeddings_deleted} scene embeddings (DB), "
                   f"and {embeddings_deleted} scene embeddings (ChromaDB) removed")
        
    except Exception as e:
        logger.error(f"Failed to cleanup scene embeddings: {e}")
        db.rollback()


def get_semantic_stats(story_id: int, db: Session) -> Dict[str, Any]:
    """
    Get statistics about semantic data for a story
    
    Args:
        story_id: Story ID
        db: Database session
        
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
        
        # Count scene embeddings
        stats['scene_embeddings'] = db.query(SceneEmbedding).filter(
            SceneEmbedding.story_id == story_id
        ).count()
        
        # Count character moments
        stats['character_moments'] = db.query(CharacterMemory).filter(
            CharacterMemory.story_id == story_id
        ).count()
        
        # Count plot events
        stats['plot_events'] = db.query(PlotEvent).filter(
            PlotEvent.story_id == story_id
        ).count()
        
        # Count unresolved threads
        stats['unresolved_threads'] = db.query(PlotEvent).filter(
            PlotEvent.story_id == story_id,
            PlotEvent.is_resolved == False
        ).count()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get semantic stats: {e}")
        return {'enabled': False, 'error': str(e)}

