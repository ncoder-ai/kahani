"""
Story helper functions and adapters extracted from stories.py

This module contains:
- SceneVariantServiceAdapter: Adapter for legacy LLM function calls
- Multi-variant generation helpers
- Auto-play TTS setup
- Extraction invalidation/regeneration functions
- User settings helpers
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
import json
import logging

from ..models import (
    Story, Scene, SceneVariant, SceneChoice, StoryFlow, User, UserSettings,
    Chapter, CharacterState, LocationState, ObjectState
)
from ..services.llm.service import UnifiedLLMService
from ..config import settings

logger = logging.getLogger(__name__)

# Initialize the unified LLM service (shared instance)
llm_service = UnifiedLLMService()


def safe_get_custom_prompt(request, logger=None):
    """Safely extract custom_prompt from request, handling various input types"""
    if isinstance(request, dict):
        return request.get('custom_prompt', '')
    elif hasattr(request, 'custom_prompt'):
        # Handle Pydantic models
        return getattr(request, 'custom_prompt', '') or ''
    elif isinstance(request, str):
        # Try to parse JSON string
        try:
            request_dict = json.loads(request)
            return request_dict.get('custom_prompt', '')
        except json.JSONDecodeError:
            if logger:
                logger.warning(f"Request is a string but not valid JSON: {request}")
            return ''
    else:
        if logger:
            logger.warning(f"Request is unexpected type {type(request)}: {request}")
        return ''


class SceneVariantServiceAdapter:
    """Temporary adapter for SceneVariantService calls during migration"""

    def __init__(self, db: Session):
        self.db = db

    def get_active_variant(self, scene_id: int):
        """Get the active variant for a scene from story flow"""
        # Get the active story flow entry for this scene
        flow_entry = self.db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene_id,
            StoryFlow.is_active == True
        ).first()

        if not flow_entry:
            return None

        # Get the variant
        variant = self.db.query(SceneVariant).filter(
            SceneVariant.id == flow_entry.scene_variant_id
        ).first()

        return variant

    def get_active_story_flow(self, story_id: int, branch_id: int = None, chapter_id: int = None):
        return llm_service.get_active_story_flow(self.db, story_id, branch_id=branch_id, chapter_id=chapter_id)

    def get_scene_variants(self, scene_id: int):
        return llm_service.get_scene_variants(self.db, scene_id)

    def create_scene_with_variant(self, story_id: int, sequence_number: int, content: str, title: str = None, custom_prompt: str = None, choices: List[Dict[str, Any]] = None, generation_method: str = "auto", branch_id: int = None, chapter_id: int = None, entity_states_snapshot: str = None, context: Dict[str, Any] = None):
        """Create a new scene with its first variant.

        Args:
            context: Optional context dict - if provided, will automatically extract
                    _entity_states_snapshot and _context_snapshot from it for cache consistency
        """
        context_snapshot = None
        # Auto-extract snapshots from context if provided and not explicitly set
        if context is not None:
            if entity_states_snapshot is None:
                entity_states_snapshot = context.get('_entity_states_snapshot')
                if entity_states_snapshot:
                    logger.info(f"[SNAPSHOT] Auto-extracted entity_states_snapshot from context ({len(entity_states_snapshot)} chars)")
            # Extract prompt prefix snapshot (full messages list for variant cache consistency)
            context_snapshot = context.get('_prompt_prefix_snapshot')
            if context_snapshot:
                logger.info(f"[SNAPSHOT] Auto-extracted prompt_prefix_snapshot from context ({len(context_snapshot)} chars)")
        return llm_service.create_scene_with_variant(self.db, story_id, sequence_number, content, title, custom_prompt, choices, generation_method, branch_id, chapter_id, entity_states_snapshot=entity_states_snapshot, context_snapshot=context_snapshot)

    async def regenerate_scene_variant(self, scene_id: int, custom_prompt: str = None, user_settings: dict = None, user_id: int = None, branch_id: int = None):
        # Use provided user_id or fall back to default
        actual_user_id = user_id or 1
        return await llm_service.regenerate_scene_variant(self.db, scene_id, custom_prompt, user_id=actual_user_id, user_settings=user_settings, branch_id=branch_id)

    def switch_to_variant(self, story_id: int, scene_id: int, variant_id: int, branch_id: int = None):
        return llm_service.switch_to_variant(self.db, story_id, scene_id, variant_id, branch_id=branch_id)

    async def delete_scenes_from_sequence(self, story_id: int, sequence_number: int, skip_restoration: bool = False, branch_id: int = None) -> bool:
        return await llm_service.delete_scenes_from_sequence(self.db, story_id, sequence_number, skip_restoration=skip_restoration, branch_id=branch_id)


# Temporary adapter functions for old LLM function calls
async def generate_scene_streaming(context, user_id, user_settings):
    async for chunk in llm_service.generate_scene_streaming(context, user_id, user_settings):
        yield chunk


# REMOVED: generate_scene_continuation() - Use llm_service.generate_continuation_with_choices() instead
# REMOVED: generate_scene_continuation_streaming() - Use llm_service.generate_continuation_with_choices_streaming() instead


def SceneVariantService(db: Session):
    """Temporary adapter to maintain compatibility during migration"""
    return SceneVariantServiceAdapter(db)


# =====================================================================
# MULTI-GENERATION HELPER FUNCTIONS
# =====================================================================

def get_n_value_from_settings(user_settings: dict) -> int:
    """
    Extract n value from sampler settings.
    Returns 1 if n is not enabled or not configured.
    Clamps value between 1 and 5.
    """
    if not user_settings:
        return 1

    sampler_settings = user_settings.get('sampler_settings', {})
    n_config = sampler_settings.get('n', {})

    if not n_config.get('enabled', False):
        return 1

    value = n_config.get('value', 1)
    return min(max(int(value), 1), 5)  # Clamp between 1 and 5


def create_scene_with_multi_variants(
    db: Session,
    story_id: int,
    sequence_number: int,
    variants_data: List[Dict[str, Any]],
    branch_id: int,
    generation_method: str = "auto",
    title: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    chapter_id: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None
) -> Tuple[Scene, List[SceneVariant]]:
    """
    Create a Scene with multiple SceneVariants and their choices.

    Args:
        db: Database session
        story_id: Story ID
        sequence_number: Scene sequence number
        variants_data: List of dicts with {"content": str, "choices": list}
        branch_id: Branch ID
        generation_method: Method used for generation
        title: Optional scene title
        custom_prompt: Optional custom prompt used
        chapter_id: Optional chapter ID to link scene to
        context: Optional context dict - will extract _entity_states_snapshot for cache consistency

    Returns:
        Tuple of (Scene, List[SceneVariant])
    """
    # Extract entity_states_snapshot from context if available
    entity_states_snapshot = None
    if context is not None:
        entity_states_snapshot = context.get('_entity_states_snapshot')
        if entity_states_snapshot:
            logger.info(f"[MULTI-GEN] Extracted entity_states_snapshot from context ({len(entity_states_snapshot)} chars)")

    # Create the scene
    scene = Scene(
        story_id=story_id,
        sequence_number=sequence_number,
        branch_id=branch_id,
        chapter_id=chapter_id,
        title=title or f"Scene {sequence_number}",
        is_deleted=False
    )
    db.add(scene)
    db.flush()  # Get scene ID

    created_variants = []
    first_variant = None

    for idx, vdata in enumerate(variants_data):
        # Create variant - only first variant (which becomes active) gets the snapshot
        variant = SceneVariant(
            scene_id=scene.id,
            variant_number=idx + 1,
            is_original=(idx == 0),
            content=vdata["content"],
            title=title or f"Scene {sequence_number}",
            original_content=vdata["content"],
            generation_prompt=custom_prompt,
            generation_method=generation_method,
            entity_states_snapshot=entity_states_snapshot if idx == 0 else None
        )
        db.add(variant)
        db.flush()  # Get variant ID

        if idx == 0:
            first_variant = variant

        # Create choices for this variant
        choices = vdata.get("choices", [])
        for choice_idx, choice_text in enumerate(choices):
            if isinstance(choice_text, str) and choice_text.strip():
                choice = SceneChoice(
                    scene_id=scene.id,
                    scene_variant_id=variant.id,
                    branch_id=branch_id,
                    choice_text=choice_text.strip(),
                    choice_order=choice_idx + 1
                )
                db.add(choice)

        created_variants.append(variant)

    # Create or update StoryFlow to point to first variant
    flow_entry = StoryFlow(
        story_id=story_id,
        scene_id=scene.id,
        scene_variant_id=first_variant.id if first_variant else None,
        sequence_number=sequence_number,
        branch_id=branch_id,
        is_active=True
    )
    db.add(flow_entry)

    db.commit()
    db.refresh(scene)
    for v in created_variants:
        db.refresh(v)

    logger.info(f"[MULTI-GEN] Created scene {scene.id} with {len(created_variants)} variants")

    return scene, created_variants


def create_additional_variants(
    db: Session,
    scene_id: int,
    variants_data: List[Dict[str, Any]],
    starting_variant_number: int,
    branch_id: int,
    custom_prompt: Optional[str] = None
) -> List[SceneVariant]:
    """
    Add new variants to an existing scene (for variant regeneration).

    Args:
        db: Database session
        scene_id: Existing scene ID
        variants_data: List of dicts with {"content": str, "choices": list}
        starting_variant_number: Starting variant number (e.g., if scene has 2 variants, start at 3)
        branch_id: Branch ID
        custom_prompt: Optional custom prompt used

    Returns:
        List of created SceneVariant objects
    """
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise ValueError(f"Scene {scene_id} not found")

    # Get the active variant's context_snapshot to copy to new variants
    # This ensures cache consistency when regenerating from the new variant
    from ..models import StoryFlow
    active_flow = db.query(StoryFlow).filter(
        StoryFlow.scene_id == scene_id,
        StoryFlow.is_active == True
    ).first()

    original_context_snapshot = None
    original_entity_states_snapshot = None
    if active_flow:
        original_variant = db.query(SceneVariant).filter(
            SceneVariant.id == active_flow.scene_variant_id
        ).first()
        if original_variant:
            original_context_snapshot = original_variant.context_snapshot
            original_entity_states_snapshot = original_variant.entity_states_snapshot
            logger.info(f"[VARIANT] Copying snapshots from original variant {original_variant.id}: "
                       f"context_snapshot={'yes' if original_context_snapshot else 'no'}, "
                       f"entity_states_snapshot={'yes' if original_entity_states_snapshot else 'no'}")

    created_variants = []
    first_new_variant = None

    for idx, vdata in enumerate(variants_data):
        variant_number = starting_variant_number + idx

        variant = SceneVariant(
            scene_id=scene_id,
            variant_number=variant_number,
            is_original=False,  # Not original - regenerated
            content=vdata["content"],
            title=scene.title,
            original_content=vdata["content"],
            generation_prompt=custom_prompt,
            generation_method="regeneration",
            # Copy snapshots from original variant for cache consistency
            context_snapshot=original_context_snapshot,
            entity_states_snapshot=original_entity_states_snapshot
        )
        db.add(variant)
        db.flush()

        if idx == 0:
            first_new_variant = variant

        # Create choices for this variant
        choices = vdata.get("choices", [])
        for choice_idx, choice_text in enumerate(choices):
            if isinstance(choice_text, str) and choice_text.strip():
                choice = SceneChoice(
                    scene_id=scene_id,
                    scene_variant_id=variant.id,
                    branch_id=branch_id,
                    choice_text=choice_text.strip(),
                    choice_order=choice_idx + 1
                )
                db.add(choice)

        created_variants.append(variant)

    # Update StoryFlow to point to first new variant
    flow_entry = db.query(StoryFlow).filter(
        StoryFlow.scene_id == scene_id,
        StoryFlow.is_active == True
    ).first()

    if flow_entry and first_new_variant:
        flow_entry.scene_variant_id = first_new_variant.id

    db.commit()
    for v in created_variants:
        db.refresh(v)

    logger.info(f"[MULTI-GEN] Added {len(created_variants)} new variants to scene {scene_id}")

    return created_variants


# =====================================================================
# AUTO-PLAY TTS FUNCTIONS
# =====================================================================

async def setup_auto_play_if_enabled(
    scene_id: int,
    user_id: int,
    db: Session,
    start_generation: bool = True
) -> Optional[dict]:
    """
    UNIFIED auto-play setup for ANY scene operation (new scene or variant).

    This single function replaces all the duplicate auto-play logic scattered
    across different endpoints. It:
    1. Checks if auto-play is enabled for the user
    2. Creates a TTS session
    3. Optionally starts audio generation immediately in background
    4. Returns event data to be sent to frontend

    Args:
        scene_id: The scene to setup TTS for
        user_id: The user requesting auto-play
        db: Database session
        start_generation: If True, starts TTS generation immediately.
                         If False, generation will start when WebSocket connects.

    Returns:
        Dict with event data if auto-play was setup, None otherwise
        Format: {'session_id': str, 'event': dict}
    """
    from ..models.tts_settings import TTSSettings
    from ..services.tts_session_manager import tts_session_manager
    import asyncio

    try:
        # Check if user has auto-play enabled
        tts_settings = db.query(TTSSettings).filter(
            TTSSettings.user_id == user_id
        ).first()

        if not (tts_settings and tts_settings.tts_enabled and tts_settings.auto_play_last_scene):
            logger.info(f"[AUTO-PLAY] Skipping - not enabled for user {user_id}")
            return None

        logger.info(f"[AUTO-PLAY] Setting up for scene {scene_id}, user {user_id}")

        # Create TTS session
        session_id = tts_session_manager.create_session(
            scene_id=scene_id,
            user_id=user_id,
            auto_play=True
        )

        logger.info(f"[AUTO-PLAY] Created session {session_id}")

        # Conditionally start generation in background
        if start_generation:
            from ..routers.tts import generate_and_stream_chunks
            asyncio.create_task(generate_and_stream_chunks(
                session_id=session_id,
                scene_id=scene_id,
                user_id=user_id
            ))
            logger.info(f"[AUTO-PLAY] Started background generation for session {session_id}")
        else:
            logger.info(f"[AUTO-PLAY] Session created, generation will start when WebSocket connects")

        # Return event data for SSE streaming
        return {
            'session_id': session_id,
            'event': {
                'type': 'auto_play_ready',
                'auto_play_session_id': session_id,
                'scene_id': scene_id
            }
        }

    except Exception as e:
        logger.error(f"[AUTO-PLAY] Failed to setup for scene {scene_id}: {e}")
        return None


# DEPRECATED: Old function kept for backward compatibility
async def trigger_auto_play_tts(scene_id: int, user_id: int):
    """DEPRECATED: Use setup_auto_play_if_enabled() instead."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        result = await setup_auto_play_if_enabled(scene_id, user_id, db)
        return result['session_id'] if result else None
    finally:
        db.close()


# =====================================================================
# EXTRACTION INVALIDATION/REGENERATION FUNCTIONS
# =====================================================================

async def invalidate_extractions_for_scene(
    scene_id: int,
    story_id: int,
    scene_sequence: int,
    user_id: int,
    user_settings: dict,
    db: Session,
    branch_id: int = None
) -> None:
    """
    Invalidate (clean up) extractions for a modified scene without regenerating.

    Regeneration will happen automatically when extraction threshold is reached.

    This function:
    1. Deletes all extractions for the scene (CharacterMemory, PlotEvent, NPCMention, SceneEmbedding)
    2. Invalidates entity state batches containing the scene
    """
    try:
        from ..services.semantic_integration import cleanup_scene_embeddings
        from ..services.entity_state_service import EntityStateService

        # Invalidate extractions for the scene
        await cleanup_scene_embeddings(scene_id, db)
        logger.info(f"[MODIFY] Cleaned up extractions for scene {scene_id} (regeneration will happen when threshold is reached)")

        # Invalidate entity state batches containing this scene (filtered by branch)
        entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
        entity_service.invalidate_entity_batches_for_scenes(
            db, story_id, scene_sequence, scene_sequence, branch_id=branch_id
        )
    except Exception as e:
        logger.error(f"Failed to invalidate extractions for scene {scene_id}: {e}")


async def invalidate_and_regenerate_extractions_for_scene(
    scene_id: int,
    story_id: int,
    scene_sequence: int,
    user_id: int,
    user_settings: dict,
    db: Session,
    branch_id: int = None
) -> None:
    """
    Invalidate and regenerate extractions for a modified scene.

    This function:
    1. Deletes all extractions for the scene (CharacterMemory, PlotEvent, NPCMention, SceneEmbedding)
    2. Invalidates entity state batches containing the scene
    3. Regenerates extractions for the scene
    4. Recalculates NPCTracking
    5. Recalculates entity states if needed
    """
    try:
        from ..services.semantic_integration import cleanup_scene_embeddings, process_scene_embeddings
        from ..services.entity_state_service import EntityStateService
        from ..services.npc_tracking_service import NPCTrackingService

        # Get scene to get content
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            logger.warning(f"Scene {scene_id} not found for extraction invalidation")
            return

        # Use scene's branch_id if not provided
        if branch_id is None:
            branch_id = scene.branch_id

        # Get active variant content
        flow = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene_id,
            StoryFlow.is_active == True
        ).first()

        if not flow or not flow.scene_variant:
            logger.warning(f"No active variant found for scene {scene_id}")
            return

        scene_content = flow.scene_variant.content

        # 1. Invalidate extractions for the scene
        await cleanup_scene_embeddings(scene_id, db)
        logger.info(f"[MODIFY] Cleaned up extractions for scene {scene_id}")

        # 2. Invalidate entity state batches containing this scene (filtered by branch)
        entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
        entity_service.invalidate_entity_batches_for_scenes(
            db, story_id, scene_sequence, scene_sequence, branch_id=branch_id
        )

        # 3. Regenerate extractions for the modified scene
        await process_scene_embeddings(
            scene_id=scene_id,
            variant_id=flow.scene_variant_id,
            story_id=story_id,
            scene_content=scene_content,
            sequence_number=scene_sequence,
            chapter_id=scene.chapter_id,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )
        logger.info(f"[MODIFY] Regenerated extractions for scene {scene_id}")

        # 4. Recalculate NPCTracking (filtered by branch)
        try:
            npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
            await npc_service.recalculate_all_scores(db, story_id, branch_id=branch_id)
            logger.info(f"[MODIFY] Recalculated NPC tracking for story {story_id} branch {branch_id}")
        except Exception as e:
            logger.warning(f"[MODIFY] Failed to recalculate NPC tracking: {e}")

        # 5. Recalculate entity states if the modified scene affects them
        # Find last valid batch before this scene (filtered by branch)
        last_valid_batch = entity_service.get_last_valid_batch(db, story_id, scene_sequence, branch_id=branch_id)

        # Delete all existing entity states for this branch before restoring
        char_del_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
        loc_del_query = db.query(LocationState).filter(LocationState.story_id == story_id)
        obj_del_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
        if branch_id is not None:
            char_del_query = char_del_query.filter(CharacterState.branch_id == branch_id)
            loc_del_query = loc_del_query.filter(LocationState.branch_id == branch_id)
            obj_del_query = obj_del_query.filter(ObjectState.branch_id == branch_id)
        char_del_query.delete()
        loc_del_query.delete()
        obj_del_query.delete()

        if last_valid_batch:
            # Restore states from batch, then re-extract from modified scene onwards
            entity_service.restore_entity_states_from_batch(db, last_valid_batch)
            start_sequence = last_valid_batch.end_scene_sequence + 1
            logger.info(f"[MODIFY] Restored entity states from batch {last_valid_batch.id} (scenes 1-{last_valid_batch.end_scene_sequence})")
        else:
            start_sequence = 1
            logger.info(f"[MODIFY] No valid batch found, starting entity state recalculation from scene 1 (branch {branch_id})")

        # Re-extract entity states from start_sequence onwards (filtered by branch)
        scenes_query = db.query(Scene).filter(
            Scene.story_id == story_id,
            Scene.sequence_number >= start_sequence
        )
        if branch_id is not None:
            scenes_query = scenes_query.filter(Scene.branch_id == branch_id)
        scenes_to_reprocess = scenes_query.order_by(Scene.sequence_number).all()

        scenes_processed = 0
        for scene_to_process in scenes_to_reprocess:
            flow_to_process = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene_to_process.id,
                StoryFlow.is_active == True
            ).first()

            if flow_to_process and flow_to_process.scene_variant:
                # Get chapter location for hierarchical context
                chapter_location = None
                if scene_to_process.chapter_id:
                    chapter = db.query(Chapter).filter(Chapter.id == scene_to_process.chapter_id).first()
                    if chapter and chapter.location_name:
                        chapter_location = chapter.location_name

                await entity_service.extract_and_update_states(
                    db=db,
                    story_id=story_id,
                    scene_id=scene_to_process.id,
                    scene_sequence=scene_to_process.sequence_number,
                    scene_content=flow_to_process.scene_variant.content,
                    chapter_location=chapter_location
                )
                scenes_processed += 1

        db.commit()
        logger.info(f"[MODIFY] Recalculated entity states for story {story_id} (processed {scenes_processed} scenes from scene {start_sequence} onwards)")

    except Exception as e:
        logger.error(f"[MODIFY] Failed to invalidate and regenerate extractions for scene {scene_id}: {e}")
        db.rollback()


# =====================================================================
# USER SETTINGS HELPERS
# =====================================================================

def get_or_create_user_settings(user_id: int, db: Session, current_user: User = None, story: Story = None) -> dict:
    """Get user settings or create defaults if none exist

    Args:
        user_id: User ID
        db: Database session
        current_user: Optional User object - if provided, will add allow_nsfw to settings
        story: Optional Story object - if provided, will compute effective allow_nsfw based on story's content_rating
    """
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == user_id
    ).first()

    if user_settings_db:
        user_settings = user_settings_db.to_dict()
    else:
        # Create default UserSettings for this user if none exist
        user_settings_db = UserSettings(user_id=user_id)
        # Populate with defaults from config.yaml
        user_settings_db.populate_from_defaults()
        db.add(user_settings_db)
        db.commit()
        db.refresh(user_settings_db)
        logger.info(f"Created default UserSettings for user {user_id} with values from config.yaml")
        user_settings = user_settings_db.to_dict()

    # Compute effective allow_nsfw based on user profile AND story content rating
    # NSFW is only allowed if: user allows NSFW AND story is rated NSFW
    user_allow_nsfw = False
    if current_user:
        user_allow_nsfw = current_user.allow_nsfw
    else:
        # If current_user not provided, try to get it from database
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_allow_nsfw = user.allow_nsfw

    # Compute effective NSFW permission
    # If story is provided and has a content_rating, use it to determine effective NSFW
    # Story must be explicitly marked as "nsfw" AND user must allow NSFW
    if story and hasattr(story, 'content_rating') and story.content_rating:
        effective_nsfw = user_allow_nsfw and story.content_rating.lower() == "nsfw"
        logger.debug(f"Effective allow_nsfw for user {user_id}, story {story.id}: user={user_allow_nsfw}, story_rating={story.content_rating}, effective={effective_nsfw}")
    else:
        # No story provided - use user's setting directly
        effective_nsfw = user_allow_nsfw
        logger.debug(f"No story context - using user allow_nsfw={user_allow_nsfw} for user {user_id}")

    user_settings['allow_nsfw'] = effective_nsfw

    return user_settings


def update_last_accessed_story(db: Session, user_id: int, story_id: int):
    """Update the user's last accessed story ID"""
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == user_id
    ).first()

    if not user_settings:
        user_settings = UserSettings(user_id=user_id)
        # Populate with defaults from config.yaml
        user_settings.populate_from_defaults()
        db.add(user_settings)

    user_settings.last_accessed_story_id = story_id
    db.commit()
