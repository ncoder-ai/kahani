from fastapi import APIRouter, Depends, HTTPException, status, Form, Body, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Scene, Character, StoryCharacter, User, UserSettings, SceneChoice, SceneVariant, StoryFlow, StoryStatus, Chapter, ChapterStatus
from ..services.llm.service import UnifiedLLMService
from sqlalchemy.sql import func
from ..services.context_manager import ContextManager
from ..dependencies import get_current_user
from ..config import settings
import logging
import json
import time
import uuid

logger = logging.getLogger(__name__)

# Lazy import for semantic integration to avoid blocking startup
try:
    from ..services.semantic_integration import (
        get_context_manager_for_user,
        process_scene_embeddings,
        batch_process_scene_extractions,
        get_semantic_stats
    )
    SEMANTIC_MEMORY_AVAILABLE = True
    logger.info("Semantic integration imported successfully")
except Exception as e:
    SEMANTIC_MEMORY_AVAILABLE = False
    logger.error(f"Failed to import semantic integration: {e}")
    # Fallback functions if semantic memory unavailable
    def get_context_manager_for_user(user_settings, user_id):
        from ..services.context_manager import ContextManager
        return ContextManager(user_settings=user_settings, user_id=user_id)
    
    async def process_scene_embeddings(*args, **kwargs):
        return {"scene_embedding_added": False, "character_moments_extracted": 0, "plot_events_extracted": 0}
    
    async def batch_process_scene_extractions(*args, **kwargs):
        return {"scenes_processed": 0, "character_moments": 0, "plot_events": 0, "entity_states": 0, "npc_tracking": 0, "scene_embeddings": 0}
    
    def get_semantic_stats(*args, **kwargs):
        return {}

# Initialize the unified LLM service
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

# Temporary adapter for SceneVariantService calls during migration
class SceneVariantServiceAdapter:
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
    
    def get_active_story_flow(self, story_id: int, branch_id: int = None):
        return llm_service.get_active_story_flow(self.db, story_id, branch_id=branch_id)
    
    def get_scene_variants(self, scene_id: int):
        return llm_service.get_scene_variants(self.db, scene_id)
    
    def create_scene_with_variant(self, story_id: int, sequence_number: int, content: str, title: str = None, custom_prompt: str = None, choices: List[Dict[str, Any]] = None, generation_method: str = "auto", branch_id: int = None):
        return llm_service.create_scene_with_variant(self.db, story_id, sequence_number, content, title, custom_prompt, choices, generation_method, branch_id)
    
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

async def generate_scene_continuation(context, user_id, user_settings, db=None):
    return await llm_service.generate_scene_continuation(context, user_id, user_settings, db)

async def generate_scene_continuation_streaming(context, user_id, user_settings, db=None):
    async for chunk in llm_service.generate_scene_continuation_streaming(context, user_id, user_settings, db):
        yield chunk

def SceneVariantService(db: Session):
    """Temporary adapter to maintain compatibility during migration"""
    return SceneVariantServiceAdapter(db)
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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

router = APIRouter()

async def invalidate_extractions_for_scene(
    scene_id: int,
    story_id: int,
    scene_sequence: int,
    user_id: int,
    user_settings: dict,
    db: Session
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
        
        # Invalidate entity state batches containing this scene
        entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
        entity_service.invalidate_entity_batches_for_scenes(
            db, story_id, scene_sequence, scene_sequence
        )
    except Exception as e:
        logger.error(f"Failed to invalidate extractions for scene {scene_id}: {e}")

async def invalidate_and_regenerate_extractions_for_scene(
    scene_id: int,
    story_id: int,
    scene_sequence: int,
    user_id: int,
    user_settings: dict,
    db: Session
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
        from ..models import Scene, StoryFlow
        
        # Get scene to get content
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            logger.warning(f"Scene {scene_id} not found for extraction invalidation")
            return
        
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
        
        # 2. Invalidate entity state batches containing this scene
        entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
        entity_service.invalidate_entity_batches_for_scenes(
            db, story_id, scene_sequence, scene_sequence
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
        
        # 4. Recalculate NPCTracking
        try:
            npc_service = NPCTrackingService(user_id=user_id, user_settings=user_settings)
            await npc_service.recalculate_all_scores(db, story_id)
            logger.info(f"[MODIFY] Recalculated NPC tracking for story {story_id}")
        except Exception as e:
            logger.warning(f"[MODIFY] Failed to recalculate NPC tracking: {e}")
        
        # 5. Recalculate entity states if the modified scene affects them
        # Find last valid batch before this scene
        last_valid_batch = entity_service.get_last_valid_batch(db, story_id, scene_sequence)
        
        if last_valid_batch:
            # Restore states from batch, then re-extract from modified scene onwards
            entity_service.restore_entity_states_from_batch(db, last_valid_batch)
            start_sequence = last_valid_batch.end_scene_sequence + 1
            logger.info(f"[MODIFY] Restored entity states from batch {last_valid_batch.id} (scenes 1-{last_valid_batch.end_scene_sequence})")
        else:
            # No valid batch, delete all states and start from scratch
            db.query(CharacterState).filter(CharacterState.story_id == story_id).delete()
            db.query(LocationState).filter(LocationState.story_id == story_id).delete()
            db.query(ObjectState).filter(ObjectState.story_id == story_id).delete()
            start_sequence = 1
            logger.info(f"[MODIFY] No valid batch found, starting entity state recalculation from scene 1")
        
        # Re-extract entity states from start_sequence onwards
        from ..models import Scene as SceneModel, Chapter
        scenes_to_reprocess = db.query(SceneModel).filter(
            SceneModel.story_id == story_id,
            SceneModel.sequence_number >= start_sequence
        ).order_by(SceneModel.sequence_number).all()
        
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


def get_or_create_user_settings(user_id: int, db: Session, current_user: User = None) -> dict:
    """Get user settings or create defaults if none exist
    
    Args:
        user_id: User ID
        db: Database session
        current_user: Optional User object - if provided, will add allow_nsfw to settings
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
    
    # Add user permissions to settings for NSFW filtering if current_user is provided
    if current_user:
        user_settings['allow_nsfw'] = current_user.allow_nsfw
        logger.debug(f"Added allow_nsfw={current_user.allow_nsfw} to user_settings for user {user_id}")
    else:
        # If current_user not provided, try to get it from database
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_settings['allow_nsfw'] = user.allow_nsfw
            logger.debug(f"Added allow_nsfw={user.allow_nsfw} to user_settings for user {user_id} (from DB)")
    
    return user_settings

class StoryCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    world_setting: Optional[str] = ""
    initial_premise: Optional[str] = ""
    story_mode: Optional[str] = "dynamic"  # dynamic or structured

class StoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    tone: Optional[str] = None
    world_setting: Optional[str] = None
    initial_premise: Optional[str] = None
    scenario: Optional[str] = None

class ScenarioGenerateRequest(BaseModel):
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    elements: dict
    characters: Optional[List[dict]] = []

class TitleGenerateRequest(BaseModel):
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    scenario: Optional[str] = ""
    characters: Optional[List[dict]] = []
    story_elements: Optional[dict] = {}

class VariantGenerateRequest(BaseModel):
    custom_prompt: Optional[str] = ""
    variant_id: Optional[int] = None  # Specific variant to enhance, if None uses active variant
    is_concluding: Optional[bool] = False  # If True, generate a chapter-concluding scene (no choices)

class ContinuationRequest(BaseModel):
    custom_prompt: Optional[str] = ""

class SceneVariantUpdateRequest(BaseModel):
    content: str

class PlotGenerateRequest(BaseModel):
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    scenario: Optional[str] = ""
    characters: Optional[List[dict]] = []
    world_setting: Optional[str] = ""
    plot_type: Optional[str] = "complete"  # "complete", "single_point"
    plot_point_index: Optional[int] = None

@router.get("/")
async def get_stories(
    skip: int = 0,
    limit: int = 10,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's stories (excluding archived by default)"""
    query = db.query(Story).filter(Story.owner_id == current_user.id)
    
    # Exclude archived stories unless explicitly requested
    if not include_archived:
        query = query.filter(Story.status != StoryStatus.ARCHIVED)
    
    # Order by most recently updated first
    stories = query.order_by(Story.updated_at.desc()).offset(skip).limit(limit).all()
    
    return [
        {
            "id": story.id,
            "title": story.title,
            "description": story.description,
            "genre": story.genre,
            "status": story.status,
            "creation_step": story.creation_step,
            "created_at": story.created_at,
            "updated_at": story.updated_at
        }
        for story in stories
    ]

@router.post("/")
async def create_story(
    story_data: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new story with NSFW content validation"""
    from ..utils.content_filter import validate_story_content, validate_genre
    
    # Validate genre permissions
    is_valid_genre, genre_error = validate_genre(story_data.genre, current_user.allow_nsfw)
    if not is_valid_genre:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=genre_error
        )
    
    # Validate story content for NSFW keywords
    is_valid_content, content_error = validate_story_content(
        story_data.title,
        story_data.description or "",
        current_user.allow_nsfw
    )
    if not is_valid_content:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=content_error
        )
    
    story = Story(
        title=story_data.title,
        description=story_data.description,
        owner_id=current_user.id,
        genre=story_data.genre,
        tone=story_data.tone,
        world_setting=story_data.world_setting,
        initial_premise=story_data.initial_premise,
        story_mode=story_data.story_mode or "dynamic"
    )
    
    db.add(story)
    db.commit()
    db.refresh(story)
    
    return {
        "id": story.id,
        "title": story.title,
        "description": story.description,
        "message": "Story created successfully"
    }

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

@router.get("/{story_id}")
async def get_story(
    story_id: int,
    branch_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific story with its active flow
    
    Args:
        branch_id: Optional. If provided, use this branch. Otherwise uses story's current_branch_id.
    """
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Update last accessed story for auto-open feature
    update_last_accessed_story(db, current_user.id, story_id)
    
    # Get active branch
    from ..models import StoryBranch
    active_branch_id = branch_id or story.current_branch_id
    active_branch = None
    if active_branch_id:
        active_branch = db.query(StoryBranch).filter(StoryBranch.id == active_branch_id).first()
    
    # Get the active story flow instead of direct scenes
    service = SceneVariantService(db)
    flow = service.get_active_story_flow(story_id, branch_id=active_branch_id)
    
    # Transform flow data to match expected format for backward compatibility
    scenes = []
    for flow_item in flow:
        variant = flow_item['variant']
        scenes.append({
            "id": flow_item['scene_id'],
            "chapter_id": flow_item['chapter_id'],  # Add chapter_id for frontend filtering
            "sequence_number": flow_item['sequence_number'],
            "title": variant['title'],
            "content": variant['content'],
            "location": "",  # TODO: Add location to variant
            "characters_present": [],  # TODO: Add characters to variant
            # Additional variant info
            "variant_id": variant['id'],
            "variant_number": variant['variant_number'],
            "is_original": variant['is_original'],
            "has_multiple_variants": flow_item.get('has_multiple_variants', False),
            "choices": flow_item['choices']
        })
    
    # Check draft_data as fallback for fields that might not be in columns
    draft_data = story.draft_data or {}
    
    # Get branch info
    branch_info = None
    if active_branch:
        branch_count = db.query(StoryBranch).filter(StoryBranch.story_id == story_id).count()
        branch_info = {
            "id": active_branch.id,
            "name": active_branch.name,
            "is_main": active_branch.is_main,
            "total_branches": branch_count
        }
    
    return {
        "id": story.id,
        "title": story.title,
        "description": story.description or draft_data.get('description', '') or "",
        "genre": story.genre or draft_data.get('genre', '') or "",
        "tone": story.tone or draft_data.get('tone', '') or "",
        "world_setting": story.world_setting or draft_data.get('world_setting', '') or "",
        "initial_premise": story.initial_premise or draft_data.get('initial_premise', '') or "",
        "scenario": story.scenario or draft_data.get('scenario', '') or "",
        "status": story.status,
        "scenes": scenes,
        "flow_info": {
            "total_scenes": len(scenes),
            "has_variants": any(scene['has_multiple_variants'] for scene in scenes)
        },
        "branch": branch_info,
        "current_branch_id": active_branch_id,
        "story_arc": story.story_arc
    }

@router.put("/{story_id}")
async def update_story(
    story_id: int,
    story_data: StoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update story settings with NSFW content validation"""
    from ..utils.content_filter import validate_story_content, validate_genre
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Validate genre if it's being updated
    if story_data.genre is not None:
        is_valid_genre, genre_error = validate_genre(story_data.genre, current_user.allow_nsfw)
        if not is_valid_genre:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=genre_error
            )
    
    # Validate story content for NSFW keywords if title or description is being updated
    title_to_validate = story_data.title if story_data.title is not None else story.title
    description_to_validate = story_data.description if story_data.description is not None else (story.description or "")
    
    is_valid_content, content_error = validate_story_content(
        title_to_validate,
        description_to_validate,
        current_user.allow_nsfw
    )
    if not is_valid_content:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=content_error
        )
    
    # Update fields that are provided
    if story_data.title is not None:
        story.title = story_data.title
    if story_data.description is not None:
        story.description = story_data.description
    if story_data.genre is not None:
        story.genre = story_data.genre
    if story_data.tone is not None:
        story.tone = story_data.tone
    if story_data.world_setting is not None:
        story.world_setting = story_data.world_setting
    if story_data.initial_premise is not None:
        story.initial_premise = story_data.initial_premise
    if story_data.scenario is not None:
        story.scenario = story_data.scenario
    
    db.commit()
    db.refresh(story)
    
    return {
        "id": story.id,
        "title": story.title,
        "description": story.description,
        "genre": story.genre,
        "tone": story.tone,
        "world_setting": story.world_setting,
        "initial_premise": story.initial_premise,
        "scenario": story.scenario,
        "message": "Story updated successfully"
    }

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
        import asyncio
        # Delay to ensure database commits from main session are visible
        # This helps with transaction isolation between sessions
        # Increased from 0.1s to 0.3s for better reliability under load
        await asyncio.sleep(0.3)
        
        from ..database import SessionLocal
        extraction_db = SessionLocal()
        try:
            # Reload chapter to get fresh data (in case it was updated)
            extraction_chapter = extraction_db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not extraction_chapter:
                logger.error(f"[EXTRACTION] Chapter {chapter_id} not found in background task")
                return
            
            # Get actual sequence numbers of scenes in this chapter (not scenes_count which is just a count)
            from ..models import Scene, StoryFlow
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
            
            # === PLOT PROGRESS EXTRACTION ===
            # Run plot progress extraction if chapter has a plot and tracking is enabled
            if extraction_chapter.chapter_plot:
                generation_prefs = user_settings.get("generation_preferences", {}) if user_settings else {}
                enable_plot_tracking = generation_prefs.get("enable_chapter_plot_tracking", True)
                
                if enable_plot_tracking and scenes_processed > 0:
                    try:
                        from ..services.chapter_progress_service import ChapterProgressService
                        progress_service = ChapterProgressService(extraction_db)
                        
                        # Get scene content from the processed scenes for extraction
                        # We use the scenes that were just extracted (from actual_from_sequence to actual_to_sequence)
                        from ..models import SceneVariant
                        for scene in scenes_in_chapter:
                            if scene.sequence_number > actual_from_sequence and scene.sequence_number <= actual_to_sequence:
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
                                        await progress_service.extract_and_update_progress(
                                            chapter=extraction_chapter,
                                            scene_content=variant.content,
                                            llm_service=llm_service,
                                            user_id=user_id,
                                            user_settings=user_settings
                                        )
                        
                        # Get updated progress for logging
                        extraction_db.refresh(extraction_chapter)
                        progress = extraction_chapter.plot_progress or {}
                        completed_count = len(progress.get("completed_events", []))
                        logger.info(f"[PLOT_PROGRESS] Updated chapter {chapter_id} progress: {completed_count} events completed")
                    except Exception as e:
                        logger.error(f"[PLOT_PROGRESS] Plot progress extraction failed: {e}")
                        # Don't fail the overall extraction if plot tracking fails
        finally:
            extraction_db.close()
    except Exception as e:
        logger.error(f"[EXTRACTION] Background extraction failed: {e}")
        import traceback
        logger.error(f"[EXTRACTION] Traceback: {traceback.format_exc()}")


@router.post("/{story_id}/scenes")
async def generate_scene(
    story_id: int,
    custom_prompt: str = Form(""),
    user_content: str = Form(""),
    content_mode: str = Form("ai_generate"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a new scene for the story with smart context management
    
    content_mode options:
    - "ai_generate": AI generates scene from scratch (default)
    - "user_prompt": Use user_content as prompt for AI generation
    - "user_scene": Use user_content directly as scene content, AI generates choices
    """
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get active branch
    active_branch_id = story.current_branch_id
    if not active_branch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Story has no active branch. Please create a branch first."
        )
    
    # Get user settings and include permission flags
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    # Handle different content modes
    scene_content = ""
    effective_custom_prompt = custom_prompt
    generation_method = "auto"
    
    if content_mode == "user_scene":
        # User provided their own scene content
        if not user_content or not user_content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_content is required when content_mode is 'user_scene'"
            )
        scene_content = user_content.strip()
        generation_method = "user_written"
        # Still need context for choice generation
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        try:
            context = await context_manager.build_scene_generation_context(
                story_id, db, ""
            )
        except Exception as e:
            logger.error(f"Failed to build context for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare story context: {str(e)}"
            )
    elif content_mode == "user_prompt":
        # User provided a prompt for AI generation
        if not user_content or not user_content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_content is required when content_mode is 'user_prompt'"
            )
        effective_custom_prompt = user_content.strip()
        # Continue with normal AI generation flow
        # Get active chapter for character separation (filter by branch to avoid cross-branch confusion)
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.branch_id == active_branch_id,
            Chapter.status == ChapterStatus.ACTIVE
        ).first()
        chapter_id = active_chapter.id if active_chapter else None
        
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        try:
            context = await context_manager.build_scene_generation_context(
                story_id, db, effective_custom_prompt, is_variant_generation=False, chapter_id=chapter_id
            )
        except Exception as e:
            logger.error(f"Failed to build context for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare story context: {str(e)}"
            )
        
        # Generate scene content using enhanced method
        try:
            scene_content = await llm_service.generate_scene(context, current_user.id, user_settings, db)
        except Exception as e:
            logger.error(f"Failed to generate scene for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate scene: {str(e)}"
            )
    else:
        # Default: ai_generate mode
        # Create context manager with user settings (semantic or linear)
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        
        # Get active chapter for character separation (filter by branch to avoid cross-branch confusion)
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.branch_id == active_branch_id,
            Chapter.status == ChapterStatus.ACTIVE
        ).first()
        chapter_id = active_chapter.id if active_chapter else None
        
        # Use context manager to build optimized context
        try:
            context = await context_manager.build_scene_generation_context(
                story_id, db, custom_prompt, is_variant_generation=False, chapter_id=chapter_id
            )
        except Exception as e:
            logger.error(f"Failed to build context for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare story context: {str(e)}"
            )
        
        # Generate scene content using enhanced method with combined choices
        try:
            scene_content, parsed_choices = await llm_service.generate_scene_with_choices(context, current_user.id, user_settings, db)
            
            # Check if separate choice generation is enabled
            generation_prefs = user_settings.get("generation_preferences", {})
            separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
            
            # If choices weren't parsed (or separate generation is enabled), generate separately
            if not parsed_choices or len(parsed_choices) < 2:
                if separate_choice_generation:
                    logger.info("Separate choice generation enabled - generating choices in dedicated LLM call")
                else:
                    logger.warning("Choice parsing failed, using fallback generation")
                # Reuse the existing scene generation context - don't rebuild it
                # The scene_content will be added to context as current_situation in generate_choices()
                parsed_choices = await llm_service.generate_choices(scene_content, context, current_user.id, user_settings, db)
        except Exception as e:
            logger.error(f"Failed to generate scene for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate scene: {str(e)}"
            )
    
    # Create scene with variant system - use active scene count from StoryFlow
    current_scene_count = llm_service.get_active_scene_count(db, story_id, branch_id=active_branch_id)
    next_sequence = current_scene_count + 1
    
    # Format choices from parsed result or fallback
    choices_data = []
    try:
        if parsed_choices and len(parsed_choices) >= 2:
            choices_data = [
                {
                    "text": choice_text,
                    "order": i + 1,
                    "description": None
                }
                for i, choice_text in enumerate(parsed_choices)
            ]
        else:
            logger.warning("No valid choices generated, continuing without choices")
            choices_data = []
    except Exception as e:
        logger.warning(f"Failed to format choices: {e}")
        choices_data = []

    # Use the new variant service to create scene with variant
    try:
        service = SceneVariantService(db)
        scene, variant = service.create_scene_with_variant(
            story_id=story_id,
            sequence_number=next_sequence,
            content=scene_content,
            title=f"Scene {next_sequence}",
            custom_prompt=effective_custom_prompt if effective_custom_prompt else None,
            choices=choices_data,
            generation_method=generation_method,
            branch_id=active_branch_id
        )
        
        # Format choices for response (already in correct format)
        formatted_choices = choices_data
        
        # Chapter integration - link scene to active chapter
        from ..models import Chapter, ChapterStatus
        active_chapter = None
        try:
            # Get or create active chapter for this story (filtered by branch)
            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id,
                Chapter.status == ChapterStatus.ACTIVE
            ).order_by(Chapter.chapter_number.desc()).first()
            
            if not active_chapter:
                # Create first chapter if none exists for this branch
                active_chapter = Chapter(
                    story_id=story_id,
                    branch_id=active_branch_id,
                    chapter_number=1,
                    title="Chapter 1",
                    status=ChapterStatus.ACTIVE,
                    context_tokens_used=0,
                    scenes_count=0,
                    last_summary_scene_count=0
                )
                db.add(active_chapter)
                db.flush()
                logger.info(f"[CHAPTER] Created first chapter {active_chapter.id} for story {story_id} on branch {active_branch_id}")
            
            # Link scene to active chapter
            scene.chapter_id = active_chapter.id
            db.flush()  # Flush to ensure chapter_id is set before counting scenes
            
            # Update chapter token tracking - calculate actual context size that would be sent to LLM
            # This includes base context, chapter summaries, entity states, and only recent scenes from current chapter
            try:
                actual_context_size = await context_manager.calculate_actual_context_size(
                    story_id, active_chapter.id, db
                )
                active_chapter.context_tokens_used = actual_context_size
                logger.info(f"[CHAPTER] Calculated actual context size for chapter {active_chapter.id}: {actual_context_size} tokens")
            except Exception as e:
                logger.error(f"[CHAPTER] Failed to calculate actual context size for chapter {active_chapter.id}: {e}")
                # Fallback: use scene tokens as before (but log the issue)
                scene_tokens = context_manager.count_tokens(scene_content.strip())
                active_chapter.context_tokens_used += scene_tokens
                logger.warning(f"[CHAPTER] Using fallback token accumulation: {scene_tokens} tokens added")
            
            # Recalculate scenes_count from active StoryFlow instead of incrementing
            active_chapter.scenes_count = llm_service.get_active_scene_count(db, story_id, branch_id=active_branch_id, chapter_id=active_chapter.id)
            
            db.commit()
            logger.info(f"[CHAPTER] Linked scene {scene.id} to chapter {active_chapter.id} ({active_chapter.scenes_count} scenes, {active_chapter.context_tokens_used} tokens)")
            
            # AUTO-GENERATE SUMMARIES if enabled and threshold reached
            if active_chapter and user_settings:
                # Check if we should auto-generate summaries
                auto_generate = user_settings.get("auto_generate_summaries", True)
                threshold = user_settings.get("context_summary_threshold", 5)
                
                if auto_generate:
                    # Calculate scenes since last summary
                    scenes_since_summary = active_chapter.scenes_count - (active_chapter.last_summary_scene_count or 0)
                    
                    if scenes_since_summary >= threshold:
                        logger.info(f"[AUTO-SUMMARY] Threshold reached ({scenes_since_summary}/{threshold}) for chapter {active_chapter.id}")
                        
                        # Generate chapter summary with context from previous chapters
                        from ..api.chapters import generate_chapter_summary_incremental
                        try:
                            await generate_chapter_summary_incremental(active_chapter.id, db, current_user.id)
                            # Note: story_so_far is NOT regenerated here because it only includes previous chapters,
                            # not the current chapter, so updating current chapter's summary doesn't affect it
                            logger.info(f"[AUTO-SUMMARY] Generated chapter summary for chapter {active_chapter.id}")
                        except Exception as e:
                            logger.error(f"[AUTO-SUMMARY] Failed to auto-generate summaries: {e}")
                            # Don't fail the scene creation if summary fails
        except Exception as e:
            logger.error(f"[CHAPTER] Failed to link scene to chapter: {e}")
            # Don't fail scene creation if chapter linking fails, but log the error
            db.rollback()
            # Try to commit just the scene without chapter linking
            db.commit()
        
    except Exception as e:
        logger.error(f"Failed to create scene with variant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scene: {str(e)}"
        )
    
    # Save manual choice if custom_prompt was provided
    if custom_prompt and custom_prompt.strip():
        try:
            # Get the previous scene (parent of the newly created scene, filtered by branch)
            previous_scenes = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.branch_id == active_branch_id,
                Scene.sequence_number == next_sequence - 1
            ).all()
            
            if previous_scenes:
                previous_scene = previous_scenes[0]
                
                # Get the active variant for the previous scene
                # Use StoryFlow to find the active variant (filtered by branch)
                previous_flow = db.query(StoryFlow).filter(
                    StoryFlow.story_id == story_id,
                    StoryFlow.branch_id == active_branch_id,
                    StoryFlow.scene_id == previous_scene.id
                ).order_by(StoryFlow.sequence_number.desc()).first()
                
                if previous_flow and previous_flow.scene_variant_id:
                    # Check if this manual choice already exists
                    existing_manual_choice = db.query(SceneChoice).filter(
                        SceneChoice.scene_variant_id == previous_flow.scene_variant_id,
                        SceneChoice.is_user_created == True
                    ).first()
                    
                    if existing_manual_choice:
                        # Update existing manual choice
                        existing_manual_choice.choice_text = custom_prompt.strip()
                        existing_manual_choice.leads_to_scene_id = scene.id
                    else:
                        # Create new manual choice
                        # Get max order for this variant to append at end
                        max_order = db.query(func.max(SceneChoice.choice_order)).filter(
                            SceneChoice.scene_variant_id == previous_flow.scene_variant_id
                        ).scalar() or 0
                        
                        manual_choice = SceneChoice(
                            scene_id=previous_scene.id,
                            scene_variant_id=previous_flow.scene_variant_id,
                            branch_id=active_branch_id,
                            choice_text=custom_prompt.strip(),
                            choice_order=max_order + 1,
                            is_user_created=True,
                            leads_to_scene_id=scene.id
                        )
                        db.add(manual_choice)
                    
                    db.commit()
                    logger.info(f"Saved manual choice for scene {previous_scene.id}, variant {previous_flow.scene_variant_id}")
        except Exception as e:
            logger.error(f"Failed to save manual choice: {e}")
            # Don't fail the scene creation if manual choice saving fails
            db.rollback()
    
    # AUTO-PLAY TTS if enabled
    from ..models.tts_settings import TTSSettings
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    auto_play_session_id = None
    if tts_settings and tts_settings.tts_enabled and tts_settings.auto_play_last_scene:
        logger.info(f"[AUTO-PLAY] Creating TTS session for scene {scene.id}")
        # Create session immediately (not in background) so we can return session_id
        auto_play_session_id = await trigger_auto_play_tts(
            scene_id=scene.id,
            user_id=current_user.id
        )
    
    response_data = {
        "id": scene.id,
        "content": scene_content,
        "sequence_number": next_sequence,
        "choices": formatted_choices,
        "variant": {
            "id": variant.id,
            "variant_number": variant.variant_number,
            "is_original": variant.is_original
        },
        "context_info": {
            "total_scenes": context.get("total_scenes", 0) + 1,
            "context_type": "summarized" if context.get("scene_summary") else "full",
            "user_settings_applied": user_settings is not None
        },
        "message": "Scene generated successfully with smart context management"
    }
    
    # Add auto-play info if enabled
    if auto_play_session_id:
        response_data["auto_play"] = {
            "enabled": True,
            "session_id": auto_play_session_id,
            "scene_id": scene.id
        }
    
    return response_data

@router.post("/{story_id}/scenes/stream")
async def generate_scene_streaming_endpoint(
    story_id: int,
    custom_prompt: str = Form(""),
    user_content: str = Form(""),
    content_mode: str = Form("ai_generate"),
    is_concluding: str = Form("false"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a new scene for the story with streaming response
    
    content_mode options:
    - "ai_generate": AI generates scene from scratch (default, streams tokens)
    - "user_prompt": Use user_content as prompt for AI generation (streams tokens)
    - "user_scene": Use user_content directly as scene content, AI generates choices (sends content immediately, then streams choices)
    
    is_concluding: If "true", generates a chapter-concluding scene (no choices)
    """
    trace_id = f"scene-stream-{uuid.uuid4()}"
    start_time = time.perf_counter()
    logger.info(f"[SCENE:STREAM:START] trace_id={trace_id} story_id={story_id} content_mode={content_mode} is_concluding={is_concluding}")
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get active branch
    active_branch_id = story.current_branch_id
    if not active_branch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Story has no active branch. Please create a branch first."
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    # Parse is_concluding (form data comes as string)
    is_concluding_bool = is_concluding.lower() == "true"
    
    # Handle different content modes
    effective_custom_prompt = custom_prompt
    generation_method = "concluding_scene" if is_concluding_bool else "auto"
    user_provided_content = None
    
    if content_mode == "user_scene":
        # User provided their own scene content
        if not user_content or not user_content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_content is required when content_mode is 'user_scene'"
            )
        user_provided_content = user_content.strip()
        generation_method = "user_written"
        # Still need context for choice generation
        # Get active chapter for character separation (filtered by branch)
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.branch_id == active_branch_id,
            Chapter.status == ChapterStatus.ACTIVE
        ).first()
        chapter_id = active_chapter.id if active_chapter else None
        
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        try:
            context = await context_manager.build_scene_generation_context(
                story_id, db, "", is_variant_generation=False, chapter_id=chapter_id
            )
        except Exception as e:
            logger.error(f"Failed to build context for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare story context: {str(e)}"
            )
    elif content_mode == "user_prompt":
        # User provided a prompt for AI generation
        if not user_content or not user_content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_content is required when content_mode is 'user_prompt'"
            )
        effective_custom_prompt = user_content.strip()
    # else: ai_generate mode (default)
    
    # Create context manager with user settings (semantic or linear)
    context_manager = get_context_manager_for_user(user_settings, current_user.id)
    
    # Get active chapter for character separation (filtered by branch)
    active_chapter = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.branch_id == active_branch_id,
        Chapter.status == ChapterStatus.ACTIVE
    ).first()
    chapter_id = active_chapter.id if active_chapter else None
    
    # Use context manager to build optimized context
    try:
        context = await context_manager.build_scene_generation_context(
            story_id, db, effective_custom_prompt, is_variant_generation=False, chapter_id=chapter_id, branch_id=active_branch_id
        )
    except Exception as e:
        logger.error(f"Failed to build context for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to prepare story context: {str(e)}"
        )
    
    # Calculate next sequence number - use active scene count from StoryFlow
    current_scene_count = llm_service.get_active_scene_count(db, story_id, branch_id=active_branch_id)
    next_sequence = current_scene_count + 1
    
    async def generate_stream():
        nonlocal active_chapter  # Use outer scope's active_chapter variable
        try:
            full_content = ""
            
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'sequence': next_sequence})}\n\n"
            
            # Handle user-provided content vs AI generation
            if user_provided_content:
                # User wrote their own scene - send it immediately as a single chunk
                full_content = user_provided_content
                yield f"data: {json.dumps({'type': 'content', 'chunk': user_provided_content})}\n\n"
                parsed_choices = None  # User-provided scenes need separate choice generation
            elif is_concluding_bool:
                # Generate concluding scene (no choices)
                logger.info(f"[SCENE STREAM] Generating concluding scene for story {story_id}")
                
                # Get chapter info for the concluding prompt
                chapter_info = {
                    "chapter_number": active_chapter.chapter_number if active_chapter else 1,
                    "chapter_title": active_chapter.title if active_chapter else "Untitled",
                    "chapter_location": active_chapter.location_name if active_chapter else "Unknown",
                    "chapter_time_period": active_chapter.time_period if active_chapter else "Unknown",
                    "chapter_scenario": active_chapter.scenario if active_chapter else "None"
                }
                
                async for chunk in llm_service.generate_concluding_scene_streaming(
                    context,
                    chapter_info,
                    current_user.id,
                    user_settings,
                    db
                ):
                    full_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                
                # Concluding scenes don't have choices
                parsed_choices = None
            else:
                # Use combined scene + choices generation
                scene_context = context.copy() if isinstance(context, dict) else {"story_context": context}
                if effective_custom_prompt and effective_custom_prompt.strip():
                    scene_context["custom_prompt"] = effective_custom_prompt.strip()
                
                parsed_choices = None
                async for chunk, scene_complete, choices in llm_service.generate_scene_with_choices_streaming(
                    scene_context,
                    current_user.id,
                    user_settings,
                    db
                ):
                    if not scene_complete:
                        # Still streaming scene content
                        full_content += chunk
                        yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                    else:
                        # Scene complete, choices parsed
                        parsed_choices = choices
                        break
            
            # Save the scene to database FIRST (before choices)
            variant_service = SceneVariantService(db)
            try:
                scene, variant = variant_service.create_scene_with_variant(
                    story_id=story_id,
                    sequence_number=next_sequence,
                    content=full_content.rstrip(),
                    title=f"Scene {next_sequence}",
                    custom_prompt=effective_custom_prompt if effective_custom_prompt else None,
                    choices=[],  # We'll add choices later
                    generation_method=generation_method,
                    branch_id=active_branch_id
                )
                logger.info(f"Created scene {scene.id} with variant {variant.id} for story {story_id} on branch {active_branch_id} trace_id={trace_id}")
            except Exception as e:
                logger.error(f"Failed to create scene variant: {e} trace_id={trace_id}")
                raise
            
            # Process semantic embeddings (async, non-blocking)
            try:
                # Get chapter ID if available (filtered by branch)
                chapter_id = None
                active_chapter = db.query(Chapter).filter(
                    Chapter.story_id == story_id,
                    Chapter.branch_id == active_branch_id,
                    Chapter.status == ChapterStatus.ACTIVE
                ).first()
                if active_chapter:
                    chapter_id = active_chapter.id
                
            except Exception as e:
                logger.error(f"Failed to extract chapter: {e}")
            
            # PRIORITY 1: Setup TTS IMMEDIATELY (different server, runs in parallel)
            auto_play_session_id = None
            try:
                auto_play_data = await setup_auto_play_if_enabled(
                    scene.id, 
                    current_user.id, 
                    db,
                    start_generation=False  # Generation starts when WebSocket connects
                )
                
                if auto_play_data:
                    auto_play_session_id = auto_play_data['session_id']
                    # Send event immediately so frontend can connect NOW!
                    yield f"data: {json.dumps(auto_play_data['event'])}\n\n"
                    logger.info(f"[AUTO-PLAY] Sent auto_play_ready event (TTS can start now)")
                    
            except Exception as e:
                logger.error(f"[AUTO-PLAY] Failed to setup: {e}")
                # Don't fail scene generation if auto-play fails
            
            # PRIORITY 2: Generate choices (may already be parsed from combined generation)
            choices_data = []
            try:
                # Check if separate choice generation is enabled
                generation_prefs = user_settings.get("generation_preferences", {})
                separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
                
                if parsed_choices and len(parsed_choices) >= 2 and not separate_choice_generation:
                    # Use parsed choices from combined generation
                    logger.info(f"Using parsed choices from combined generation: {len(parsed_choices)} choices")
                    choices = parsed_choices
                else:
                    # Separate choice generation (intentional or fallback)
                    if separate_choice_generation:
                        logger.info("Separate choice generation enabled - generating choices in dedicated LLM call")
                    else:
                        logger.warning("Choice parsing failed or no choices found, using fallback generation")
                    # Reuse the existing scene generation context - don't create minimal dict
                    # The scene_content will be added to context as current_situation in generate_choices()
                    choices = await llm_service.generate_choices(full_content, context, current_user.id, user_settings, db)
                
                # Format and save choices
                for i, choice_text in enumerate(choices):
                    choice = SceneChoice(
                        scene_id=scene.id,
                        scene_variant_id=variant.id,
                        branch_id=active_branch_id,
                        choice_text=choice_text,
                        choice_order=i + 1
                    )
                    db.add(choice)
                    choices_data.append({
                        "text": choice_text,
                        "order": i + 1
                    })
                
                db.commit()
                logger.info(f"Saved {len(choices_data)} choices for scene {scene.id}")
                
            except Exception as e:
                logger.warning(f"Failed to generate choices for scene: {e}")
                choices_data = []
                db.rollback()

            # Chapter integration (optional - won't break if it fails)
            active_chapter = None  # Initialize outside try block for use in background tasks
            try:
                # Get or create active chapter for this story (filtered by branch)
                active_chapter = db.query(Chapter).filter(
                    Chapter.story_id == story_id,
                    Chapter.branch_id == active_branch_id,
                    Chapter.status == ChapterStatus.ACTIVE
                ).order_by(Chapter.chapter_number.desc()).first()
                
                if not active_chapter:
                    # Create first chapter if none exists for this branch
                    active_chapter = Chapter(
                        story_id=story_id,
                        branch_id=active_branch_id,
                        chapter_number=1,
                        title="Chapter 1",
                        status=ChapterStatus.ACTIVE,
                        context_tokens_used=0,
                        scenes_count=0,
                        last_summary_scene_count=0
                    )
                    db.add(active_chapter)
                    db.flush()
                    logger.info(f"[CHAPTER] Created first chapter {active_chapter.id} for story {story_id} on branch {active_branch_id}")
                
                # Link scene to active chapter
                scene.chapter_id = active_chapter.id
                db.flush()  # Flush to ensure chapter_id is set before counting scenes
                
                # Update chapter token tracking - calculate actual context size that would be sent to LLM
                # This includes base context, chapter summaries, entity states, and only recent scenes from current chapter
                try:
                    actual_context_size = await context_manager.calculate_actual_context_size(
                        story_id, active_chapter.id, db
                    )
                    active_chapter.context_tokens_used = actual_context_size
                    logger.info(f"[CHAPTER] Calculated actual context size for chapter {active_chapter.id}: {actual_context_size} tokens")
                except Exception as e:
                    logger.error(f"[CHAPTER] Failed to calculate actual context size for chapter {active_chapter.id}: {e}")
                    # Fallback: use scene tokens as before (but log the issue)
                    scene_tokens = context_manager.count_tokens(full_content.strip())
                    active_chapter.context_tokens_used += scene_tokens
                    logger.warning(f"[CHAPTER] Using fallback token accumulation: {scene_tokens} tokens added")
                
                # Recalculate scenes_count from active StoryFlow instead of incrementing
                active_chapter.scenes_count = llm_service.get_active_scene_count(db, story_id, branch_id=active_branch_id, chapter_id=active_chapter.id)
                
                db.commit()
                logger.info(f"[CHAPTER] Linked scene {scene.id} to chapter {active_chapter.id} ({active_chapter.scenes_count} scenes, {active_chapter.context_tokens_used} tokens)")
                
                # Log scene generation status after chapter update
                try:
                    # Get thresholds from user settings
                    summary_threshold = user_settings.get('context_settings', {}).get('summary_threshold', 5) if user_settings else 5
                    extraction_threshold = user_settings.get('context_settings', {}).get('character_extraction_threshold', 5) if user_settings else 5
                    
                    # Calculate scenes since last summary and extraction using actual sequence numbers
                    # Get scenes in this chapter to find actual sequence numbers
                    scenes_in_chapter = db.query(Scene).join(StoryFlow).filter(
                        StoryFlow.story_id == story_id,
                        StoryFlow.is_active == True,
                        Scene.chapter_id == active_chapter.id,
                        Scene.is_deleted == False
                    ).order_by(Scene.sequence_number).all()
                    
                    if scenes_in_chapter:
                        scene_sequence_numbers = [s.sequence_number for s in scenes_in_chapter]
                        last_summary_sequence = active_chapter.last_summary_scene_count or 0
                        last_extraction_sequence = active_chapter.last_extraction_scene_count or 0
                        
                        # Count scenes with sequence > last_summary/extraction_sequence
                        scenes_since_summary = len([s for s in scene_sequence_numbers if s > last_summary_sequence])
                        scenes_since_extraction = len([s for s in scene_sequence_numbers if s > last_extraction_sequence])
                    else:
                        scenes_since_summary = 0
                        scenes_since_extraction = 0
                    
                    logger.warning(f"[SCENE GENERATION] Chapter {active_chapter.id} status after scene {next_sequence}:")
                    logger.warning(f"  - Total scenes: {active_chapter.scenes_count}")
                    logger.warning(f"  - Scenes since last summary: {scenes_since_summary} (threshold: {summary_threshold}, last_summary_sequence: {active_chapter.last_summary_scene_count or 0})")
                    logger.warning(f"  - Scenes since last extraction: {scenes_since_extraction} (threshold: {extraction_threshold}, last_extraction_sequence: {active_chapter.last_extraction_scene_count or 0})")
                    
                    # Check NPC tracking status (filtered by branch)
                    try:
                        from ..models import NPCTracking
                        npc_count = db.query(NPCTracking).filter(
                            NPCTracking.story_id == story_id,
                            NPCTracking.branch_id == active_branch_id,
                            NPCTracking.converted_to_character == False
                        ).count()
                        npc_threshold_crossed = db.query(NPCTracking).filter(
                            NPCTracking.story_id == story_id,
                            NPCTracking.branch_id == active_branch_id,
                            NPCTracking.crossed_threshold == True,
                            NPCTracking.converted_to_character == False
                        ).count()
                        logger.warning(f"  - NPC tracking: {npc_count} total NPCs, {npc_threshold_crossed} crossed threshold")
                    except Exception as npc_error:
                        logger.debug(f"Could not get NPC stats: {npc_error}")
                except Exception as log_error:
                    logger.warning(f"Failed to log scene generation status: {log_error}")
                
                # Note: Auto-summary check will happen AFTER choices are sent (see below)
            except Exception as e:
                logger.warning(f"[CHAPTER] Chapter integration failed for scene {scene.id}, but scene was created successfully: {e}")
                # Don't fail the scene generation if chapter integration fails
                db.rollback()  # Rollback any chapter changes
                db.commit()    # But keep the scene
                active_chapter = None  # Set to None so we don't try summary generation
                logger.info(f"[SCENE GENERATION] Scene {next_sequence} created (no active chapter)")
            
            # Save manual choice if custom_prompt was provided
            if custom_prompt and custom_prompt.strip():
                try:
                    # Get the previous scene (parent of the newly created scene, filtered by branch)
                    previous_scenes = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.branch_id == active_branch_id,
                        Scene.sequence_number == next_sequence - 1
                    ).all()
                    
                    if previous_scenes:
                        previous_scene = previous_scenes[0]
                        
                        # Get the active variant for the previous scene
                        # Use StoryFlow to find the active variant (filtered by branch)
                        previous_flow = db.query(StoryFlow).filter(
                            StoryFlow.story_id == story_id,
                            StoryFlow.branch_id == active_branch_id,
                            StoryFlow.scene_id == previous_scene.id
                        ).order_by(StoryFlow.sequence_number.desc()).first()
                        
                        if previous_flow and previous_flow.scene_variant_id:
                            # Check if this manual choice already exists
                            existing_manual_choice = db.query(SceneChoice).filter(
                                SceneChoice.scene_variant_id == previous_flow.scene_variant_id,
                                SceneChoice.is_user_created == True
                            ).first()
                            
                            if existing_manual_choice:
                                # Update existing manual choice
                                existing_manual_choice.choice_text = custom_prompt.strip()
                                existing_manual_choice.leads_to_scene_id = scene.id
                            else:
                                # Create new manual choice
                                # Get max order for this variant to append at end
                                max_order = db.query(func.max(SceneChoice.choice_order)).filter(
                                    SceneChoice.scene_variant_id == previous_flow.scene_variant_id
                                ).scalar() or 0
                                
                                manual_choice = SceneChoice(
                                    scene_id=previous_scene.id,
                                    scene_variant_id=previous_flow.scene_variant_id,
                                    branch_id=active_branch_id,
                                    choice_text=custom_prompt.strip(),
                                    choice_order=max_order + 1,
                                    is_user_created=True,
                                    leads_to_scene_id=scene.id
                                )
                                db.add(manual_choice)
                            
                            db.commit()
                            logger.info(f"Saved manual choice for scene {previous_scene.id}, variant {previous_flow.scene_variant_id}")
                except Exception as e:
                    logger.error(f"Failed to save manual choice: {e}")
                    # Don't fail the scene creation if manual choice saving fails
                    db.rollback()
            
            # PRIORITY: Send completion data with choices IMMEDIATELY (before any background tasks)
            complete_data = {
                'type': 'complete',
                'scene_id': scene.id,
                'variant_id': variant.id,
                'choices': choices_data
            }
            
            # Add auto-play info to complete event if it was set up
            if auto_play_session_id:
                complete_data['auto_play'] = {
                    'enabled': True,
                    'session_id': auto_play_session_id,
                    'scene_id': scene.id
                }
            
            yield f"data: {json.dumps(complete_data)}\n\n"
            
            # PRIORITY 3: Run extractions synchronously AFTER scene and choices are sent to frontend
            # Background task: Auto-summary generation (if needed) - keep this in background
            import asyncio
            
            if active_chapter:
                try:
                    summary_threshold = user_settings.get('context_settings', {}).get('summary_threshold', 5) if user_settings else 5
                    # Use the already calculated scenes_since_summary from above (uses actual sequence numbers)
                    logger.info(f"[CHAPTER] Auto-summary check: {scenes_since_summary} scenes since last summary (threshold: {summary_threshold})")
                    if scenes_since_summary >= summary_threshold:
                        logger.info(f"[CHAPTER] Chapter {active_chapter.id} reached {summary_threshold} scenes since last summary, triggering auto-summary in background")
                        from ..api.chapters import generate_chapter_summary_incremental
                        
                        async def generate_summaries_background():
                            try:
                                # Create a new DB session for background task
                                from ..database import SessionLocal
                                bg_db = SessionLocal()
                                try:
                                    # Reload chapter to get latest state
                                    bg_chapter = bg_db.query(Chapter).filter(Chapter.id == active_chapter.id).first()
                                    if bg_chapter:
                                        await generate_chapter_summary_incremental(bg_chapter.id, bg_db, current_user.id)
                                        # Note: story_so_far is NOT regenerated here because it only includes previous chapters,
                                        # not the current chapter, so updating current chapter's summary doesn't affect it
                                        
                                        bg_chapter.last_summary_scene_count = bg_chapter.scenes_count
                                        bg_db.commit()
                                        logger.info(f"[CHAPTER] Auto-summary generated for chapter {bg_chapter.id}")
                                finally:
                                    bg_db.close()
                            except Exception as e:
                                logger.error(f"[AUTO-SUMMARY] Background task failed: {e}")
                        
                        # Run summary generation in background (fire and forget)
                        asyncio.create_task(generate_summaries_background())
                        logger.info(f"[CHAPTER] Started background summary generation for chapter {active_chapter.id}")
                except Exception as e:
                    logger.error(f"[AUTO-SUMMARY] Failed to start background summary generation: {e}")
                    # Don't fail scene generation if summary fails
            
            # Run extractions synchronously - no background tasks
            if active_chapter:
                try:
                    # Get extraction threshold from user settings
                    extraction_threshold = user_settings.get('context_settings', {}).get(
                        'character_extraction_threshold', 
                        5  # Default threshold
                    ) if user_settings else 5
                    
                    # Calculate scenes since last extraction using actual sequence numbers
                    # Get scenes in this chapter to find actual sequence numbers
                    scenes_in_chapter = db.query(Scene).join(StoryFlow).filter(
                        StoryFlow.story_id == story_id,
                        StoryFlow.is_active == True,
                        Scene.chapter_id == active_chapter.id,
                        Scene.is_deleted == False
                    ).order_by(Scene.sequence_number).all()
                    
                    if scenes_in_chapter:
                        scene_sequence_numbers = [s.sequence_number for s in scenes_in_chapter]
                        max_sequence_in_chapter = max(scene_sequence_numbers)
                        last_extraction_sequence = active_chapter.last_extraction_scene_count or 0
                        
                        # Count scenes with sequence > last_extraction_sequence
                        scenes_since_extraction = len([s for s in scene_sequence_numbers if s > last_extraction_sequence])
                        
                        logger.warning(f"[EXTRACTION] Scenes since last extraction: {scenes_since_extraction}/{extraction_threshold} for chapter {active_chapter.id}")
                        logger.warning(f"[EXTRACTION] Chapter {active_chapter.id} has {len(scenes_in_chapter)} scenes (sequences {min(scene_sequence_numbers)} to {max_sequence_in_chapter}), last extracted: {last_extraction_sequence}")
                        
                        if scenes_since_extraction >= extraction_threshold:
                            logger.warning(f"[EXTRACTION] ✓ SCHEDULED: Threshold reached ({scenes_since_extraction}/{extraction_threshold})")
                            
                            # Schedule extraction to run after response completes
                            # Use actual sequence numbers, not scenes_count
                            background_tasks.add_task(
                                run_extractions_in_background,
                                story_id=story_id,
                                chapter_id=active_chapter.id,
                                from_sequence=last_extraction_sequence,
                                to_sequence=max_sequence_in_chapter,
                                user_id=current_user.id,
                                user_settings=user_settings or {}
                            )
                            
                            # Send status event with clear message
                            extraction_msg = f"Extracting ({scenes_since_extraction}/{extraction_threshold})"
                            yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'scheduled', 'message': extraction_msg})}\n\n"
                        else:
                            # Threshold not reached - skip extraction with clear reason
                            skip_msg = f"Skipped ({scenes_since_extraction}/{extraction_threshold})"
                            logger.warning(f"[EXTRACTION] ✗ SKIPPED: {skip_msg}")
                            yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'skipped', 'message': skip_msg})}\n\n"
                    else:
                        logger.warning(f"[EXTRACTION] No scenes found in chapter {active_chapter.id}, skipping extraction")
                except Exception as e:
                    logger.error(f"[EXTRACTION] Failed to process extraction: {e}")
                    import traceback
                    logger.error(f"[EXTRACTION] Traceback: {traceback.format_exc()}")
                    # Send error status to frontend
                    yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'error', 'message': 'Extraction failed'})}\n\n"
                    # Don't fail scene generation if extraction fails
            
            # Note: Plot progress extraction now runs inside run_extractions_in_background
            # when the extraction threshold is reached, aligned with character extraction
            
            # Send [DONE] as the LAST event after all extraction status events
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    response = StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )
    logger.info(f"[SCENE:STREAM:READY] trace_id={trace_id} story_id={story_id} setup_ms={(time.perf_counter() - start_time) * 1000:.2f}")
    return response

@router.get("/{story_id}/context-info")
async def get_story_context_info(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get information about the story's context management status"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Create context manager with user settings
        context_manager = ContextManager(user_settings=user_settings)
        
        # Build context to analyze
        context = await context_manager.build_story_context(story_id, db)
        
        # Count scenes
        total_scenes = db.query(Scene).filter(Scene.story_id == story_id).count()
        
        # Analyze context usage
        base_tokens = context_manager._calculate_base_context_tokens(context)
        
        # Estimate total content tokens
        all_scenes = db.query(Scene).filter(Scene.story_id == story_id).all()
        total_content = " ".join([scene.content for scene in all_scenes])
        total_content_tokens = context_manager.count_tokens(total_content)
        
        return {
            "story_id": story_id,
            "total_scenes": total_scenes,
            "context_management": {
                "max_tokens": context_manager.max_tokens,
                "base_context_tokens": base_tokens,
                "total_story_tokens": total_content_tokens,
                "needs_summarization": total_content_tokens > context_manager.max_tokens,
                "context_type": "summarized" if context.get("scene_summary") else "full",
                "user_settings_applied": user_settings is not None
            },
            "characters": len(context.get("characters", [])),
            "recent_scenes_included": context.get("total_scenes", 0),
            "summary_used": bool(context.get("scene_summary")),
            "user_settings": user_settings
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze context for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze story context: {str(e)}"
        )

@router.get("/{story_id}/choices")
async def get_current_choices(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get choices for the latest scene in the story"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get the latest scene
    latest_scene = db.query(Scene).filter(
        Scene.story_id == story_id
    ).order_by(Scene.sequence_number.desc()).first()
    
    if not latest_scene:
        return {"choices": []}
    
    # Get choices for the latest scene
    choices = db.query(SceneChoice).filter(
        SceneChoice.scene_id == latest_scene.id
    ).order_by(SceneChoice.choice_order).all()
    
    return {
        "choices": [
            {
                "text": choice.choice_text,
                "order": choice.choice_order
            }
            for choice in choices
        ]
    }

@router.post("/{story_id}/generate-more-choices")
async def generate_more_choices(
    story_id: int,
    request: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate fresh alternative choices for a specific scene variant"""
    
    variant_id = request.get("variant_id")
    if not variant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variant_id is required"
        )
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get the specified variant
    variant = db.query(SceneVariant).filter(
        SceneVariant.id == variant_id
    ).first()
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )
    
    # Verify the variant belongs to a scene in this story
    scene = db.query(Scene).filter(
        Scene.id == variant.scene_id,
        Scene.story_id == story_id
    ).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found for this variant"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    # Create context manager with user settings
    context_manager = get_context_manager_for_user(user_settings, current_user.id)
    
    try:
        # For "More Choices": We need to rebuild context since the original scene generation context isn't available
        # Build full scene generation context with appropriate parameters
        # Filter by branch to avoid cross-branch confusion
        active_branch_id = story.current_branch_id
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.branch_id == active_branch_id,
            Chapter.status == ChapterStatus.ACTIVE
        ).first()
        chapter_id = active_chapter.id if active_chapter else None
        
        # Build full scene generation context (exclude the current scene to avoid duplication)
        choice_context = await context_manager.build_scene_generation_context(
            story_id, db, chapter_id=chapter_id, exclude_scene_id=scene.id
        )
        
        # Generate fresh choices using LLM with variant's content
        # The variant.content will be added to context as current_situation in generate_choices()
        generated_choices = await llm_service.generate_choices(
            variant.content, 
            choice_context, 
            current_user.id,
            user_settings,
            db
        )
        
        # Check if choice generation failed
        if not generated_choices or len(generated_choices) < 2:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI failed to generate choices. Please try regenerating or use the custom prompt field to specify your continuation."
            )
        
        # Get existing choices for this variant to determine next order number
        existing_choices = db.query(SceneChoice).filter(
            SceneChoice.scene_variant_id == variant_id
        ).order_by(SceneChoice.choice_order.desc()).first()
        
        next_order = (existing_choices.choice_order + 1) if existing_choices else 1
        
        # Store choices in database linked to the variant
        stored_choices = []
        for idx, choice_text in enumerate(generated_choices):
            choice = SceneChoice(
                scene_id=scene.id,
                scene_variant_id=variant.id,
                branch_id=scene.branch_id,
                choice_text=choice_text,
                choice_order=next_order + idx
            )
            db.add(choice)
            stored_choices.append({
                "id": None,  # Will be set after commit
                "text": choice_text,
                "order": next_order + idx
            })
        
        db.commit()
        
        # Refresh to get IDs - query all choices for this variant ordered by creation time
        # Get the most recently created choices (the ones we just added)
        all_variant_choices = db.query(SceneChoice).filter(
            SceneChoice.scene_variant_id == variant_id
        ).order_by(SceneChoice.created_at.desc()).limit(len(stored_choices)).all()
        
        # Match stored choices with created choices (reverse order since we queried desc)
        for i, created_choice in enumerate(reversed(all_variant_choices[:len(stored_choices)])):
            if i < len(stored_choices):
                stored_choices[i]["id"] = created_choice.id
        
        logger.info(f"Generated and stored {len(stored_choices)} additional choices for variant {variant_id}")
        
        return {
            "choices": stored_choices
        }
        
    except HTTPException:
        # Re-raise HTTPExceptions (like our choice generation failure message)
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate more choices for variant {variant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate choices: {str(e)}"
        )

@router.post("/{story_id}/regenerate-last-scene")
async def regenerate_last_scene(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new variant for the last scene"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get the latest scene from the active flow
    service = SceneVariantService(db)
    flow = service.get_active_story_flow(story_id)
    
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No scenes found for this story"
        )
    
    # Get the last scene
    last_flow_item = flow[-1]
    last_scene_id = last_flow_item['scene_id']
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    try:
        # Create a new variant for the last scene
        new_variant = await service.regenerate_scene_variant(
            scene_id=last_scene_id,
            user_settings=user_settings
        )
        
        # Get choices for the new variant
        choices = db.query(SceneChoice)\
            .filter(SceneChoice.scene_variant_id == new_variant.id)\
            .order_by(SceneChoice.choice_order)\
            .all()
        
        return {
            "message": "Scene regenerated successfully",
            "scene": {
                "id": last_scene_id,
                "sequence_number": last_flow_item['sequence_number'],
                "title": new_variant.title,
                "content": new_variant.content,
                "location": "",  # TODO: Add to variant
                "characters_present": []  # TODO: Add to variant
            },
            "variant": {
                "id": new_variant.id,
                "variant_number": new_variant.variant_number,
                "is_original": new_variant.is_original,
                "generation_method": new_variant.generation_method,
                "choices": [
                    {
                        "id": choice.id,
                        "text": choice.choice_text,
                        "description": choice.choice_description,
                        "order": choice.choice_order,
                    }
                    for choice in choices
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to regenerate scene for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate scene: {str(e)}"
        )

@router.post("/generate-scenario")
async def generate_scenario_endpoint(
    request: ScenarioGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a creative scenario using LLM based on user selections"""
    
    try:
        # Build context for LLM
        context = {
            "genre": request.genre,
            "tone": request.tone,
            "opening": request.elements.get("opening", ""),
            "setting": request.elements.get("setting", ""), 
            "conflict": request.elements.get("conflict", ""),
            "characters": request.characters
        }
        
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        # Add user permissions to settings for NSFW filtering
        user_settings['allow_nsfw'] = current_user.allow_nsfw
        
        # Generate scenario using LLM
        scenario = await llm_service.generate_scenario(context, current_user.id, user_settings)
        
        return {
            "scenario": scenario,
            "message": "Scenario generated successfully"
        }
        
    except ValueError as e:
        # This handles validation errors (like missing API URL)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"LLM service error: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback:", exc_info=True)
        # Fallback to simple combination if LLM fails for other reasons
        elements = [v for v in request.elements.values() if v]
        fallback_scenario = ". ".join(elements) + "." if elements else "A new adventure begins."
        
        return {
            "scenario": fallback_scenario,
            "message": "Scenario generated (fallback mode due to LLM service error)"
        }

@router.post("/generate-title")
async def generate_title(
    request: TitleGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate creative story titles using LLM based on story content"""
    
    try:
        # Build context for LLM
        context = {
            "genre": request.genre,
            "tone": request.tone,
            "scenario": request.scenario,
            "characters": request.characters,
            "story_elements": request.story_elements
        }
        
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        # Add user permissions to settings for NSFW filtering
        user_settings['allow_nsfw'] = current_user.allow_nsfw
        
        # Generate multiple title options using LLM
        titles = await llm_service.generate_story_title(context, current_user.id, user_settings)
        
        return {
            "titles": titles,
            "message": "Titles generated successfully"
        }
        
    except Exception as e:
        # Fallback titles based on genre
        genre = request.genre or "adventure"
        fallback_titles = [
            f"The {genre.title()} Begins",
            f"Chronicles of {genre.title()}",
            f"Beyond the {genre.title()}"
        ]
        
        return {
            "titles": fallback_titles,
            "message": "Titles generated (fallback mode)"
        }

@router.post("/generate-plot")
async def generate_plot_endpoint(
    request: PlotGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate plot points using LLM based on characters and scenario"""
    
    try:
        # Build context for LLM
        context = {
            "genre": request.genre,
            "tone": request.tone,
            "scenario": request.scenario,
            "characters": request.characters,
            "world_setting": request.world_setting,
            "plot_type": request.plot_type,
            "plot_point_index": request.plot_point_index
        }
        
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        # Add user permissions to settings for NSFW filtering
        user_settings['allow_nsfw'] = current_user.allow_nsfw
        
        # Generate plot using LLM
        try:
            if request.plot_type == "complete":
                plot_points = await llm_service.generate_plot_points(context, current_user.id, user_settings, plot_type="complete")
                
                # Validate that we got plot points
                if not plot_points or len(plot_points) == 0:
                    logger.error("Plot generation returned empty plot_points list")
                    raise ValueError("Failed to parse plot points from LLM response")
                
                logger.info(f"Successfully generated {len(plot_points)} plot points for user {current_user.id}")
                return {
                    "plot_points": plot_points,
                    "message": "Complete plot generated successfully"
                }
            else:
                plot_point_result = await llm_service.generate_plot_points(context, current_user.id, user_settings, plot_type="single")
                
                # Handle single plot point (returns a list with one element)
                plot_point = plot_point_result[0] if isinstance(plot_point_result, list) and len(plot_point_result) > 0 else str(plot_point_result) if plot_point_result else ""
                
                if not plot_point or len(plot_point.strip()) == 0:
                    logger.error("Plot generation returned empty plot_point")
                    raise ValueError("Failed to generate plot point from LLM response")
                
                logger.info(f"Successfully generated single plot point for user {current_user.id}")
                return {
                    "plot_point": plot_point,
                    "message": "Plot point generated successfully"
                }
        except (ValueError, AttributeError, IndexError, TypeError) as parse_error:
            # These are likely parsing errors
            logger.error(f"Plot parsing error for user {current_user.id}: {parse_error}")
            logger.error(f"Parse error type: {type(parse_error).__name__}")
            logger.error(f"Context: plot_type={request.plot_type}, plot_point_index={request.plot_point_index}")
            logger.error(f"Full traceback:", exc_info=True)
            
            # Return meaningful error to frontend
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse plot points from LLM response: {str(parse_error)}. Check backend logs for details."
            )
        
    except ValueError as e:
        # This handles validation errors (like missing API URL)
        logger.error(f"Plot generation validation error for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Plot generation error for user {current_user.id}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback:", exc_info=True)
        
        # Fallback plot points
        fallback_points = [
            "The story begins with an intriguing hook that draws readers in.",
            "A pivotal event changes everything and sets the main conflict in motion.", 
            "Challenges and obstacles test the characters' resolve and growth.",
            "The climax brings all conflicts to a head in an intense confrontation.",
            "The resolution ties up loose ends and shows character transformation."
        ]
        
        if request.plot_type == "complete":
            logger.warning(f"Using fallback plot points for user {current_user.id}")
            return {
                "plot_points": fallback_points,
                "message": "Plot generated (fallback mode due to error)"
            }
        else:
            index = request.plot_point_index or 0
            logger.warning(f"Using fallback plot point for user {current_user.id}, index {index}")
            return {
                "plot_point": fallback_points[min(index, len(fallback_points)-1)],
                "message": "Plot point generated (fallback mode due to error)"
            }

# ====== NEW SCENE VARIANT ENDPOINTS ======

@router.get("/{story_id}/flow")
async def get_story_flow(
    story_id: int,
    branch_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the current active story flow with scene variants"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Use provided branch_id or story's current branch
    active_branch_id = branch_id or story.current_branch_id
    
    flow = llm_service.get_active_story_flow(db, story_id, branch_id=active_branch_id)
    
    return {
        "story_id": story_id,
        "flow": flow,
        "total_scenes": len(flow),
        "branch_id": active_branch_id
    }

@router.put("/{story_id}/variants/{variant_id}/manual-choice")
async def update_manual_choice(
    story_id: int,
    variant_id: int,
    choice_text: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update the user-created manual choice for a variant"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Find the manual choice for this variant
    manual_choice = db.query(SceneChoice).filter(
        SceneChoice.scene_variant_id == variant_id,
        SceneChoice.is_user_created == True
    ).first()
    
    if manual_choice:
        # Update existing
        manual_choice.choice_text = choice_text.strip()
    else:
        # Create new if doesn't exist
        variant = db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        
        max_order = db.query(func.max(SceneChoice.choice_order)).filter(
            SceneChoice.scene_variant_id == variant_id
        ).scalar() or 0
        
        # Get branch_id from variant's scene
        scene = db.query(Scene).filter(Scene.id == variant.scene_id).first()
        branch_id = scene.branch_id if scene else None
        
        manual_choice = SceneChoice(
            scene_id=variant.scene_id,
            scene_variant_id=variant_id,
            branch_id=branch_id,
            choice_text=choice_text.strip(),
            choice_order=max_order + 1,
            is_user_created=True
        )
        db.add(manual_choice)
    
    db.commit()
    
    return {"message": "Manual choice updated", "choice_id": manual_choice.id}

@router.get("/{story_id}/scenes/{scene_id}/variants")
async def get_scene_variants(
    story_id: int,
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all variants for a specific scene"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.story_id == story_id
    ).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    variants = llm_service.get_scene_variants(db, scene_id)
    
    # Get choices for each variant
    result = []
    for variant in variants:
        choices = db.query(SceneChoice)\
            .filter(SceneChoice.scene_variant_id == variant.id)\
            .order_by(SceneChoice.choice_order)\
            .all()
        
        result.append({
            'id': variant.id,
            'variant_number': variant.variant_number,
            'content': variant.content,
            'title': variant.title,
            'is_original': variant.is_original,
            'generation_method': variant.generation_method,
            'user_rating': variant.user_rating,
            'is_favorite': variant.is_favorite,
            'user_edited': variant.user_edited,
            'created_at': variant.created_at,
            'choices': [
                {
                    'id': choice.id,
                    'text': choice.choice_text,
                    'description': choice.choice_description,
                    'order': choice.choice_order,
                    'is_user_created': choice.is_user_created
                }
                for choice in choices
            ]
        })
    
    return {
        "scene_id": scene_id,
        "variants": result
    }

@router.get("/{story_id}/summary")
async def get_story_summary(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a summary of the story including context information"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get story flow for scene count
    service = SceneVariantService(db)
    flow = service.get_active_story_flow(story_id)
    
    # Get user settings for context information
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_defaults = settings.user_defaults.get('context_settings', {})
    context_budget = user_settings.context_max_tokens if user_settings else user_defaults.get('max_tokens', 4000)
    keep_recent = user_settings.context_keep_recent_scenes if user_settings else user_defaults.get('keep_recent_scenes', 3)
    summary_threshold = user_settings.context_summary_threshold if user_settings else user_defaults.get('summary_threshold', 5)
    summarization_enabled = user_settings.enable_context_summarization if user_settings else True
    
    # Calculate context usage
    total_scenes = len(flow)
    recent_scenes = min(keep_recent, total_scenes)
    summarized_scenes = max(0, total_scenes - recent_scenes) if total_scenes > summary_threshold else 0
    
    # Estimate token usage (rough calculation)
    estimated_tokens = 0
    for scene_data in flow:
        content = scene_data['variant']['content']
        estimated_tokens += len(content.split()) * 1.3  # Rough token estimate
    
    # Generate a basic summary from the story content
    story_summary = f"'{story.title}' is a {story.genre or 'story'} with {total_scenes} scenes."
    if story.description:
        story_summary += f" {story.description}"
    
    if total_scenes > 0:
        first_scene = flow[0]['variant']['content'][:200] + "..." if len(flow[0]['variant']['content']) > 200 else flow[0]['variant']['content']
        story_summary += f" The story begins: {first_scene}"
    
    summary_data = {
        "story": {
            "id": story.id,
            "title": story.title,
            "description": story.description,
            "genre": story.genre,
            "total_scenes": total_scenes
        },
        "context_info": {
            "total_scenes": total_scenes,
            "recent_scenes": recent_scenes,
            "summarized_scenes": summarized_scenes,
            "context_budget": context_budget,
            "estimated_tokens": int(estimated_tokens),
            "usage_percentage": min(100, (estimated_tokens / context_budget) * 100) if context_budget > 0 else 0,
            "summarization_enabled": summarization_enabled,
            "summary_threshold": summary_threshold
        },
        "summary": story_summary
    }
    
    return summary_data

@router.post("/{story_id}/scenes/{scene_id}/variants")
async def create_scene_variant(
    story_id: int,
    scene_id: int,
    request: VariantGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new variant (regeneration) for a scene"""
    trace_id = f"scene-variant-{uuid.uuid4()}"
    op_start = time.perf_counter()
    logger.info(f"[SCENE:VARIANT:START] trace_id={trace_id} story_id={story_id} scene_id={scene_id}")
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    try:
        # Get custom_prompt from the request model
        custom_prompt = request.custom_prompt
            
        service = SceneVariantService(db)
        variant = await service.regenerate_scene_variant(
            scene_id=scene_id,
            custom_prompt=custom_prompt,
            user_settings=user_settings,
            user_id=current_user.id
        )
        
        logger.info(f"Created new variant {variant.id} (#{variant.variant_number}) for scene {scene_id} trace_id={trace_id}")
        
        # Update StoryFlow to point to the new variant as active
        flow_entry = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene_id,
            StoryFlow.is_active == True
        ).first()
        
        if flow_entry:
            old_variant_id = flow_entry.scene_variant_id
            flow_entry.scene_variant_id = variant.id
            db.commit()
            logger.info(f"Updated StoryFlow: scene {scene_id} now points to variant {variant.id} (was {old_variant_id})")
            
            # Invalidate chapter summary batches if this scene was summarized
            from ..api.chapters import invalidate_chapter_batches_for_scene
            invalidate_chapter_batches_for_scene(scene_id, db)
            
            # Invalidate extractions for the modified scene (regeneration happens when threshold is reached)
            scene = db.query(Scene).filter(Scene.id == scene_id).first()
            if scene:
                await invalidate_extractions_for_scene(
                    scene_id=scene_id,
                    story_id=story_id,
                    scene_sequence=scene.sequence_number,
                    user_id=current_user.id,
                    user_settings=user_settings,
                    db=db
                )
        else:
            logger.warning(f"No active StoryFlow entry found for scene {scene_id} trace_id={trace_id}")
        
        # Check if this is the last scene and trigger auto-play TTS if enabled
        # Do this BEFORE generating choices so user can start listening sooner
        auto_play_session_id = None
        try:
            # Check if this scene is the last scene in the story
            from sqlalchemy import desc
            last_scene = db.query(Scene)\
                .filter(Scene.story_id == story_id)\
                .order_by(desc(Scene.sequence_number))\
                .first()
            
            if last_scene and last_scene.id == scene_id:
                # This is the last scene, check auto-play settings
                from ..models.tts_settings import TTSSettings
                tts_settings = db.query(TTSSettings).filter(
                    TTSSettings.user_id == current_user.id
                ).first()
                
                if tts_settings and tts_settings.tts_enabled and tts_settings.auto_play_last_scene:
                    logger.info(f"[AUTO-PLAY] Triggering TTS for variant {variant.id} of scene {scene_id}")
                    auto_play_session_id = await trigger_auto_play_tts(scene_id, current_user.id)
                    if auto_play_session_id:
                        logger.info(f"[AUTO-PLAY] Created TTS session: {auto_play_session_id}")
        except Exception as e:
            logger.error(f"[AUTO-PLAY] Failed to trigger auto-play: {e}")
            # Don't fail variant generation if auto-play fails
        
        # Generate choices for the new variant
        try:
            # Build full scene generation context for choice generation
            # Note: We don't have the original scene generation context here, so we rebuild it
            # Use get_context_manager_for_user to get SemanticContextManager for structured format
            context_manager = get_context_manager_for_user(user_settings, current_user.id)
            
            # Get active chapter for character separation (filter by branch to avoid cross-branch confusion)
            active_branch_id = story.current_branch_id
            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id,
                Chapter.status == ChapterStatus.ACTIVE
            ).first()
            chapter_id = active_chapter.id if active_chapter else None
            
            # Build full scene generation context
            choice_context = await context_manager.build_scene_generation_context(
                story_id, db, chapter_id=chapter_id, exclude_scene_id=scene_id
            )
            
            generated_choices = await llm_service.generate_choices(
                variant.content, 
                choice_context, 
                current_user.id, 
                user_settings,
                db
            )
            
            # Get branch_id from scene
            scene = db.query(Scene).filter(Scene.id == scene_id).first()
            branch_id = scene.branch_id if scene else None
            
            # Create choice records for the variant
            for idx, choice_text in enumerate(generated_choices, 1):
                choice = SceneChoice(
                    scene_id=scene_id,
                    scene_variant_id=variant.id,
                    branch_id=branch_id,
                    choice_text=choice_text,
                    choice_order=idx
                )
                db.add(choice)
            
            db.commit()
            logger.info(f"Generated {len(generated_choices)} choices for variant {variant.id}")
        except Exception as e:
            logger.warning(f"Failed to generate choices for variant {variant.id}: {e}")
            # Continue without choices - fallback will be used
        
        # Get choices for the new variant
        choices = db.query(SceneChoice)\
            .filter(SceneChoice.scene_variant_id == variant.id)\
            .order_by(SceneChoice.choice_order)\
            .all()
        
        response = {
            "message": "Scene variant created successfully",
            "variant": {
                "id": variant.id,
                "variant_number": variant.variant_number,
                "content": variant.content,
                "title": variant.title,
                "is_original": variant.is_original,
                "generation_method": variant.generation_method,
                "choices": [
                    {
                        "id": choice.id,
                        "text": choice.choice_text,
                        "description": choice.choice_description,
                        "order": choice.choice_order,
                    }
                    for choice in choices
                ]
            }
        }
        
        # Add auto_play_session_id to response if present
        if auto_play_session_id:
            response['auto_play_session_id'] = auto_play_session_id
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to create scene variant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scene variant: {str(e)}"
        )

@router.post("/{story_id}/scenes/{scene_id}/variants/stream")
async def create_scene_variant_streaming(
    story_id: int,
    scene_id: int,
    request: VariantGenerateRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new variant (regeneration) for a scene with streaming"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    async def generate_variant_stream():
        try:
            logger.info(f"Starting variant generation for scene {scene_id}")
            logger.info(f"Request type: {type(request)}, Request value: {request}")
            
            # Get the current scene and original variant
            scene = db.query(Scene).filter(Scene.id == scene_id).first()
            if not scene:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Scene not found'})}\n\n"
                return
            
            # Get branch_id from story (same as new scene generation)
            branch_id = story.current_branch_id if story else None
            
            # Get active chapter for character separation (filter by branch to avoid cross-branch confusion)
            # This ensures context is identical between new scene and variant generation
            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == branch_id,
                Chapter.status == ChapterStatus.ACTIVE
            ).first()
            chapter_id = active_chapter.id if active_chapter else None
            
            # Get original variant content for variant generation
            variant_service = SceneVariantService(db)
            
            # Use specified variant_id if provided, otherwise use active variant
            if request.variant_id:
                from ..models import SceneVariant
                original_variant = db.query(SceneVariant).filter(
                    SceneVariant.id == request.variant_id,
                    SceneVariant.scene_id == scene_id
                ).first()
                if not original_variant:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Variant {request.variant_id} not found for scene {scene_id}'})}\n\n"
                    logger.error(f"Variant {request.variant_id} not found for scene {scene_id}")
                    return
                logger.info(f"Using specified variant {request.variant_id} for guided enhancement")
            else:
                original_variant = variant_service.get_active_variant(scene_id)
                logger.info(f"Using active variant for guided enhancement")
            
            if not original_variant or not original_variant.content:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No variant found or variant has no content'})}\n\n"
                logger.error(f"No variant content found for scene {scene_id}")
                return
            
            original_scene_content = original_variant.content
            logger.info(f"Original variant content length: {len(original_scene_content)} chars")
            
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'scene_id': scene_id})}\n\n"
            
            # Build context for variant generation - use same context manager as new scene generation
            context_manager = get_context_manager_for_user(user_settings, current_user.id)
            
            # Get custom_prompt from proper request model
            custom_prompt = request.custom_prompt or ""
            logger.warning(f"[VARIANT] Custom prompt from request: '{custom_prompt}'")
            
            # Check if this should be a concluding scene
            # Either explicitly requested OR regenerating an existing concluding scene
            is_concluding = request.is_concluding or (original_variant.generation_method == "concluding_scene")
            logger.warning(f"[VARIANT] is_concluding: {is_concluding} (request: {request.is_concluding}, variant method: {original_variant.generation_method})")

            # Stream variant generation with combined choices
            variant_content = ""
            parsed_choices = None
            
            if is_concluding:
                # CONCLUDING SCENE: Generate chapter-ending scene without choices
                logger.warning(f"[VARIANT] Mode: CONCLUDING SCENE")
                context = await context_manager.build_scene_generation_context(
                    story_id, db, "", is_variant_generation=False, 
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id
                )
                
                # Get chapter info for the concluding prompt
                chapter_info = {
                    "chapter_number": active_chapter.chapter_number if active_chapter else 1,
                    "chapter_title": active_chapter.title if active_chapter else "Untitled",
                    "chapter_location": active_chapter.location_name if active_chapter else "Unknown",
                    "chapter_time_period": active_chapter.time_period if active_chapter else "Unknown",
                    "chapter_scenario": active_chapter.scenario if active_chapter else "None"
                }
                
                # Use concluding scene function (no choices generated)
                async for chunk in llm_service.generate_concluding_scene_streaming(
                    context,
                    chapter_info,
                    current_user.id,
                    user_settings,
                    db
                ):
                    variant_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                
                # Concluding scenes don't have choices
                parsed_choices = None
            elif custom_prompt:
                # GUIDED ENHANCEMENT: Has custom prompt from user
                logger.warning(f"[VARIANT] Mode: GUIDED ENHANCEMENT")
                context = await context_manager.build_scene_generation_context(
                    story_id, db, custom_prompt, is_variant_generation=True, 
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id
                )
                
                # Use guided enhancement function
                async for chunk, scene_complete, choices in llm_service.generate_variant_with_choices_streaming(
                    original_scene_content,
                    context,
                    current_user.id,
                    user_settings,
                    db
                ):
                    if not scene_complete:
                        variant_content += chunk
                        yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                    else:
                        parsed_choices = choices
                        break
            else:
                # SIMPLE VARIANT: No custom prompt - use original continue option
                # Get the ORIGINAL variant (is_original=True) to get the continue option that created the scene
                # NOT the current variant which may have guidance from a previous enhancement
                true_original_variant = db.query(SceneVariant)\
                    .filter(SceneVariant.scene_id == scene_id, SceneVariant.is_original == True)\
                    .first()
                original_continue_option = true_original_variant.generation_prompt if true_original_variant else ""
                logger.warning(f"[VARIANT] Mode: SIMPLE REGENERATION")
                logger.warning(f"[VARIANT] Using original continue option: '{original_continue_option}' (from is_original=True variant)")
                
                # Build context with original continue option (triggers IMMEDIATE SITUATION)
                # chapter_id ensures context is identical to new scene generation for cache hits
                context = await context_manager.build_scene_generation_context(
                    story_id, db, original_continue_option, is_variant_generation=False, 
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id
                )
                
                # Use the SAME function as new scene generation
                async for chunk, scene_complete, choices in llm_service.generate_scene_with_choices_streaming(
                    context,
                    current_user.id,
                    user_settings,
                    db
                ):
                    if not scene_complete:
                        variant_content += chunk
                        yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                    else:
                        parsed_choices = choices
                        break
            
            # Create the new variant manually since we already have the content
            from ..models import SceneVariant
            from sqlalchemy import desc
            
            # Get the next variant number
            max_variant = db.query(SceneVariant.variant_number)\
                .filter(SceneVariant.scene_id == scene_id)\
                .order_by(desc(SceneVariant.variant_number))\
                .first()
            
            next_variant_number = (max_variant[0] if max_variant else 0) + 1
            
            # Preserve the generation_prompt from the variant we're regenerating from
            # (before it gets overwritten by the query below)
            variant_to_regenerate_from = original_variant
            
            # Get original variant for reference
            original_variant = db.query(SceneVariant)\
                .filter(SceneVariant.scene_id == scene_id, SceneVariant.is_original == True)\
                .first()
            
            # Determine what to save as generation_prompt
            # For guided enhancement: save the custom_prompt (enhancement instructions)
            # For simple variant: save the ORIGINAL variant's generation_prompt (the continue option that created the scene)
            #   NOT the current variant's prompt (which may contain guidance from a previous enhancement)
            # For concluding scene: save empty prompt (uses chapter_conclusion prompt)
            if is_concluding:
                prompt_to_save = ""
                generation_method = "concluding_scene"
            elif custom_prompt:
                # Guided enhancement - save the custom prompt
                prompt_to_save = custom_prompt
                generation_method = "regeneration"
            else:
                # Simple regeneration - use the ORIGINAL variant's generation_prompt
                # This is the continue option that was used to create the scene originally
                prompt_to_save = original_variant.generation_prompt if original_variant else ""
                generation_method = "regeneration"
            logger.warning(f"[VARIANT] Saving generation_prompt: '{prompt_to_save}' (is_concluding: {is_concluding}, custom_prompt: '{custom_prompt}', original_variant prompt: '{original_variant.generation_prompt if original_variant else 'N/A'}')")
            
            # Create the new variant
            variant = SceneVariant(
                scene_id=scene_id,
                variant_number=next_variant_number,
                is_original=False,
                content=variant_content,
                title=scene.title,
                original_content=original_variant.content if original_variant else variant_content,
                generation_prompt=prompt_to_save,
                generation_method=generation_method
            )
            
            db.add(variant)
            db.commit()
            db.refresh(variant)
            
            logger.info(f"Created new variant {variant.id} (#{variant.variant_number}) for scene {scene_id}")
            
            # Update StoryFlow to point to the new variant as active
            flow_entry = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene_id,
                StoryFlow.is_active == True
            ).first()
            
            if flow_entry:
                old_variant_id = flow_entry.scene_variant_id
                flow_entry.scene_variant_id = variant.id
                db.commit()
                logger.info(f"Updated StoryFlow: scene {scene_id} now points to variant {variant.id} (was {old_variant_id})")
                
                # Invalidate chapter summary batches if this scene was summarized
                from ..api.chapters import invalidate_chapter_batches_for_scene
                invalidate_chapter_batches_for_scene(scene_id, db)
                
                # Invalidate extractions for the modified scene (regeneration happens when threshold is reached)
                scene = db.query(Scene).filter(Scene.id == scene_id).first()
                if scene:
                    await invalidate_extractions_for_scene(
                        scene_id=scene_id,
                        story_id=story_id,
                        scene_sequence=scene.sequence_number,
                        user_id=current_user.id,
                        user_settings=user_settings,
                        db=db
                    )
            else:
                logger.warning(f"No active StoryFlow entry found for scene {scene_id}")
            
            # Check if this is the last scene and trigger auto-play TTS if enabled
            # UNIFIED AUTO-PLAY SETUP
            auto_play_session_id = None
            try:
                # Check if this scene is the last scene in the story
                from sqlalchemy import desc
                last_scene = db.query(Scene)\
                    .filter(Scene.story_id == story_id)\
                    .order_by(desc(Scene.sequence_number))\
                    .first()
                
                if last_scene and last_scene.id == scene_id:
                    # Use unified auto-play setup
                    auto_play_data = await setup_auto_play_if_enabled(scene_id, current_user.id, db)
                    
                    if auto_play_data:
                        auto_play_session_id = auto_play_data['session_id']
                        # Send event immediately
                        yield f"data: {json.dumps(auto_play_data['event'])}\n\n"
                        logger.info(f"[AUTO-PLAY] Sent auto_play_ready event for variant")
                        
            except Exception as e:
                logger.error(f"[AUTO-PLAY] Failed to setup: {e}")
                # Don't fail variant generation if auto-play fails
            
            # Generate choices for the new variant (may already be parsed from combined generation)
            try:
                # Check if separate choice generation is enabled
                generation_prefs = user_settings.get("generation_preferences", {})
                separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
                
                if parsed_choices and len(parsed_choices) >= 2 and not separate_choice_generation:
                    # Use parsed choices from combined generation
                    logger.info(f"Using parsed choices from combined variant generation: {len(parsed_choices)} choices")
                    generated_choices = parsed_choices
                else:
                    # Separate choice generation (intentional or fallback)
                    if separate_choice_generation:
                        logger.info("Separate choice generation enabled - generating choices in dedicated LLM call")
                    else:
                        logger.warning("Choice parsing failed for variant, using fallback generation")
                    # Reuse the existing scene generation context - don't rebuild it
                    # The variant_content will be added to context as current_situation in generate_choices()
                    generated_choices = await llm_service.generate_choices(
                        variant_content, 
                        context, 
                        current_user.id, 
                        user_settings,
                        db
                    )
                
                # Get branch_id from scene
                scene = db.query(Scene).filter(Scene.id == scene_id).first()
                branch_id = scene.branch_id if scene else None
                
                # Create choice records for the variant
                for idx, choice_text in enumerate(generated_choices, 1):
                    choice = SceneChoice(
                        scene_id=scene_id,
                        scene_variant_id=variant.id,
                        branch_id=branch_id,
                        choice_text=choice_text,
                        choice_order=idx
                    )
                    db.add(choice)
                
                db.commit()
                logger.info(f"Generated {len(generated_choices)} choices for variant {variant.id}")
            except Exception as e:
                logger.warning(f"Failed to generate choices for variant {variant.id}: {e}")
                db.rollback()
                # Continue without choices - fallback will be used
            
            # Get choices for the new variant
            choices = db.query(SceneChoice)\
                .filter(SceneChoice.scene_variant_id == variant.id)\
                .order_by(SceneChoice.choice_order)\
                .all()
            
            # Send completion data
            variant_data = {
                'type': 'complete',
                'variant': {
                    'id': variant.id,
                    'variant_number': variant.variant_number,
                    'content': variant.content,
                    'title': variant.title,
                    'is_original': variant.is_original,
                    'generation_method': variant.generation_method,
                    'choices': [
                        {
                            'id': choice.id,
                            'text': choice.choice_text,
                            'description': choice.choice_description,
                            'order': choice.choice_order,
                        }
                        for choice in choices
                    ]
                }
            }
            
            # Add auto_play_session_id to response if present
            if auto_play_session_id:
                variant_data['auto_play_session_id'] = auto_play_session_id
                logger.info(f"[AUTO-PLAY DEBUG] Adding session ID to completion event: {auto_play_session_id}")
            
            completion_json = json.dumps(variant_data)
            logger.info(f"[STREAMING DEBUG] Sending completion event (length: {len(completion_json)} chars)")
            logger.info(f"[STREAMING DEBUG] Completion event includes auto_play_session_id: {'auto_play_session_id' in variant_data}")
            
            yield f"data: {completion_json}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Error in variant stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_variant_stream(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@router.post("/{story_id}/scenes/{scene_id}/variants/{variant_id}/activate")
async def activate_scene_variant(
    story_id: int,
    scene_id: int,
    variant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Switch the story flow to use a different scene variant"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    service = SceneVariantService(db)
    success = service.switch_to_variant(story_id, scene_id, variant_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to switch variant"
        )
    
    return {"message": "Variant activated successfully"}

@router.post("/{story_id}/scenes/{scene_id}/continue")
async def continue_scene(
    story_id: int,
    scene_id: int,
    request: ContinuationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Continue/extend a scene by adding more content to the existing scene"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.story_id == story_id
    ).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    try:
        # Get the current active variant content
        service = SceneVariantService(db)
        current_variant = service.get_active_variant(scene_id)
        
        if not current_variant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active scene variant found"
            )
        
        # Build context for continuation - use get_context_manager_for_user to get SemanticContextManager
        # which produces structured format needed for multi-message LLM caching
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        
        # Get custom_prompt from the request model
        custom_prompt = request.custom_prompt
            
        context = await context_manager.build_scene_continuation_context(
            story_id, scene_id, current_variant.content, db, custom_prompt,
            branch_id=story.current_branch_id  # Pass branch_id for branch-aware context
        )
        
        # Generate continuation content
        continuation_content = await generate_scene_continuation(context, current_user.id, user_settings, db)
        
        # Append to existing content
        new_content = current_variant.content + "\n\n" + continuation_content
        
        # Update the scene variant with the new content
        current_variant.content = new_content
        current_variant.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        # Invalidate chapter summary batches if this scene was summarized
        from ..api.chapters import invalidate_chapter_batches_for_scene
        invalidate_chapter_batches_for_scene(scene_id, db)
        
        # Invalidate extractions for the modified scene (regeneration happens when threshold is reached)
        await invalidate_extractions_for_scene(
            scene_id=scene_id,
            story_id=story_id,
            scene_sequence=scene.sequence_number,
            user_id=current_user.id,
            user_settings=user_settings,
            db=db
        )
        
        return {
            "message": "Scene continued successfully",
            "scene": {
                "id": scene.id,
                "content": new_content,
                "title": scene.title,
                "sequence_number": scene.sequence_number
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to continue scene {scene_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to continue scene: {str(e)}"
        )

@router.post("/{story_id}/scenes/{scene_id}/continue/stream")
async def continue_scene_streaming(
    story_id: int,
    scene_id: int,
    request: ContinuationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Continue/extend a scene with streaming response"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.story_id == story_id
    ).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    async def generate_continuation_stream():
        try:
            # Get the current active variant
            service = SceneVariantService(db)
            current_variant = service.get_active_variant(scene_id)
            
            if not current_variant:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No active scene variant found'})}\n\n"
                return
            
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'scene_id': scene_id, 'original_length': len(current_variant.content)})}\n\n"
            
            # Build context for continuation - use get_context_manager_for_user to get SemanticContextManager
            # which produces structured format needed for multi-message LLM caching
            context_manager = get_context_manager_for_user(user_settings, current_user.id)
            
            # Get custom_prompt from the request model
            custom_prompt = request.custom_prompt
                
            context = await context_manager.build_scene_continuation_context(
                story_id, scene_id, current_variant.content, db, custom_prompt,
                branch_id=story.current_branch_id  # Pass branch_id for branch-aware context
            )
            
            # Stream continuation generation with combined choices
            continuation_content = ""
            parsed_choices = None
            async for chunk, scene_complete, choices in llm_service.generate_continuation_with_choices_streaming(
                context, current_user.id, user_settings, db
            ):
                if not scene_complete:
                    # Still streaming continuation content
                    continuation_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                else:
                    # Continuation complete, choices parsed
                    parsed_choices = choices
                    break
            
            # Update the variant with the new content
            new_content = current_variant.content + "\n\n" + continuation_content
            current_variant.content = new_content
            current_variant.updated_at = datetime.now(timezone.utc)
            db.commit()
            
            # Invalidate chapter summary batches if this scene was summarized
            from .chapters import invalidate_chapter_batches_for_scene
            invalidate_chapter_batches_for_scene(scene_id, db)
            
            # Invalidate extractions for the modified scene (regeneration happens when threshold is reached)
            await invalidate_extractions_for_scene(
                scene_id=scene_id,
                story_id=story_id,
                scene_sequence=scene.sequence_number,
                user_id=current_user.id,
                user_settings=user_settings,
                db=db
            )
            
            # Generate choices for continuation if parsed, otherwise use fallback
            choices_data = []
            if parsed_choices and len(parsed_choices) >= 2:
                try:
                    # Save choices for the continuation
                    for i, choice_text in enumerate(parsed_choices, 1):
                        choice = SceneChoice(
                            scene_id=scene_id,
                            scene_variant_id=current_variant.id,
                            branch_id=scene.branch_id,
                            choice_text=choice_text,
                            choice_order=i
                        )
                        db.add(choice)
                    db.commit()
                    choices_data = [{"text": c, "order": i+1} for i, c in enumerate(parsed_choices)]
                    logger.info(f"Saved {len(choices_data)} choices from continuation")
                except Exception as e:
                    logger.warning(f"Failed to save continuation choices: {e}")
                    db.rollback()
            else:
                # Fallback: generate choices separately if needed
                logger.info("No choices parsed from continuation, skipping choice generation")
            
            # Send completion
            yield f"data: {json.dumps({'type': 'complete', 'scene_id': scene_id, 'new_content': new_content, 'choices': choices_data})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in continuation stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_continuation_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )


@router.put("/{story_id}/scenes/{scene_id}/variants/{variant_id}")
async def update_scene_variant(
    story_id: int,
    scene_id: int,
    variant_id: int,
    request: SceneVariantUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scene variant content after manual editing"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Verify scene belongs to story
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.story_id == story_id
    ).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Verify variant belongs to scene
    variant = db.query(SceneVariant).filter(
        SceneVariant.id == variant_id,
        SceneVariant.scene_id == scene_id
    ).first()
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene variant not found"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    try:
        # Store original content if this is the first edit
        if not variant.user_edited and not variant.original_content:
            variant.original_content = variant.content
        
        # Update variant content
        variant.content = request.content
        variant.user_edited = True
        variant.updated_at = datetime.now(timezone.utc)
        
        # Update edit history
        if not variant.edit_history:
            variant.edit_history = []
        variant.edit_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_length": len(request.content)
        })
        
        db.commit()
        db.refresh(variant)
        
        # Invalidate chapter summary batches if this scene was summarized
        from .chapters import invalidate_chapter_batches_for_scene
        invalidate_chapter_batches_for_scene(scene_id, db)
        
        # Only invalidate extractions (clean up old ones), don't regenerate
        # Regeneration will happen automatically when extraction threshold is reached
        from ..services.semantic_integration import cleanup_scene_embeddings
        from ..services.entity_state_service import EntityStateService
        await cleanup_scene_embeddings(scene_id, db)
        logger.info(f"[MODIFY] Cleaned up extractions for scene {scene_id} (regeneration will happen when threshold is reached)")
        
        # Invalidate entity state batches containing this scene
        entity_service = EntityStateService(user_id=current_user.id, user_settings=user_settings)
        entity_service.invalidate_entity_batches_for_scenes(
            db, story_id, scene.sequence_number, scene.sequence_number
        )
        
        return {
            "message": "Scene variant updated successfully",
            "variant": {
                "id": variant.id,
                "content": variant.content,
                "user_edited": variant.user_edited,
                "updated_at": variant.updated_at.isoformat() if variant.updated_at else None
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to update scene variant {variant_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update scene variant: {str(e)}"
        )


@router.post("/{story_id}/scenes/{scene_id}/variants/{variant_id}/regenerate-choices")
async def regenerate_scene_variant_choices(
    story_id: int,
    scene_id: int,
    variant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Regenerate choices for a scene variant after manual editing"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Verify scene belongs to story
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.story_id == story_id
    ).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Verify variant belongs to scene
    variant = db.query(SceneVariant).filter(
        SceneVariant.id == variant_id,
        SceneVariant.scene_id == scene_id
    ).first()
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene variant not found"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    try:
        # Verify we're using the correct variant
        logger.info(f"[REGENERATE_CHOICES] Regenerating choices for variant {variant_id} (scene {scene_id}, story {story_id})")
        logger.info(f"[REGENERATE_CHOICES] Variant details: id={variant.id}, variant_number={variant.variant_number}, content_length={len(variant.content)}")
        
        # Build context for choice generation - use same structure as scene generation for cache hits
        # Exclude the current scene since its content will be in the final message
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        
        # Get active chapter for character separation (filter by branch to avoid cross-branch confusion)
        active_branch_id = story.current_branch_id
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.branch_id == active_branch_id,
            Chapter.status == ChapterStatus.ACTIVE
        ).first()
        chapter_id = active_chapter.id if active_chapter else None
        
        # Build context excluding the current scene (same as generate_more_choices)
        choice_context = await context_manager.build_scene_generation_context(
            story_id, db, chapter_id=chapter_id, exclude_scene_id=scene_id
        )
        
        # Generate new choices using the same fallback logic
        generated_choices = await llm_service.generate_choices(
            variant.content, 
            choice_context, 
            current_user.id, 
            user_settings,
            db
        )
        
        # Check if choice generation failed
        if not generated_choices or len(generated_choices) < 2:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI failed to generate choices. Please try regenerating or use the custom prompt field to specify your continuation."
            )
        
        # Delete existing choices for this specific variant (using variant_id to ensure we target the correct one)
        deleted_count = db.query(SceneChoice).filter(
            SceneChoice.scene_variant_id == variant_id
        ).delete()
        logger.info(f"[REGENERATE_CHOICES] Deleted {deleted_count} existing choices for variant {variant_id}")
        
        # Create new choice records - explicitly use variant.id to ensure correct linkage
        choices_data = []
        for idx, choice_text in enumerate(generated_choices, 1):
            choice = SceneChoice(
                scene_id=scene_id,
                scene_variant_id=variant.id,  # Explicitly use variant.id to ensure correct linkage
                branch_id=scene.branch_id,
                choice_text=choice_text,
                choice_order=idx
            )
            db.add(choice)
            choices_data.append({
                "id": None,  # Will be set after commit
                "text": choice_text,
                "order": idx
            })
        
        db.commit()
        logger.info(f"[REGENERATE_CHOICES] Committed {len(choices_data)} new choices to database for variant {variant.id}")
        
        # Refresh to get IDs and verify choices were saved correctly
        db.refresh(variant)
        saved_choices = db.query(SceneChoice).filter(
            SceneChoice.scene_variant_id == variant.id
        ).order_by(SceneChoice.choice_order).all()
        
        logger.info(f"[REGENERATE_CHOICES] Verified: {len(saved_choices)} choices now linked to variant {variant.id}")
        
        # Update choice_data with actual IDs
        for choice in saved_choices:
            for choice_data in choices_data:
                if choice.choice_text == choice_data["text"] and choice.choice_order == choice_data["order"]:
                    choice_data["id"] = choice.id
                    break
        
        logger.info(f"[REGENERATE_CHOICES] Successfully regenerated {len(choices_data)} choices for variant {variant.id}")
        
        return {
            "message": "Choices regenerated successfully",
            "choices": choices_data
        }
        
    except HTTPException:
        # Re-raise HTTPExceptions (like our choice generation failure message)
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate choices for variant {variant_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate choices: {str(e)}"
        )


async def restore_npc_tracking_in_background(
    story_id: int,
    sequence_number: int,
    branch_id: int = None
):
    """Background task to restore NPC tracking from snapshot after scene deletion"""
    import uuid
    trace_id = f"npc-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()
    
    logger.info(f"[DELETE-BG:NPC:START] trace_id={trace_id} story_id={story_id} sequence_number={sequence_number} branch_id={branch_id}")
    
    try:
        import asyncio
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[DELETE-BG:NPC:PHASE] trace_id={trace_id} phase=delay_complete")
        
        from ..database import get_background_db
        with get_background_db() as bg_db:
            from ..models import Story, NPCTracking, NPCTrackingSnapshot, Scene
            
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
    except Exception as e:
        total_duration = (time.perf_counter() - task_start) * 1000
        logger.error(f"[DELETE-BG:NPC:ERROR] trace_id={trace_id} duration_ms={total_duration:.2f} error={e}")
        import traceback
        logger.error(f"[DELETE-BG:NPC:TRACEBACK] trace_id={trace_id} {traceback.format_exc()}")


async def cleanup_semantic_data_in_background(
    scene_ids: list,
    story_id: int
):
    """Background task to clean up semantic data for deleted scenes"""
    import uuid
    trace_id = f"semantic-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()
    total_scenes = len(scene_ids)
    
    logger.info(f"[DELETE-BG:SEMANTIC:START] trace_id={trace_id} story_id={story_id} scene_count={total_scenes} scene_ids={scene_ids[:5]}{'...' if total_scenes > 5 else ''}")
    
    try:
        import asyncio
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[DELETE-BG:SEMANTIC:PHASE] trace_id={trace_id} phase=delay_complete")
        
        from ..database import get_background_db
        with get_background_db() as bg_db:
            from ..services.semantic_integration import cleanup_scene_embeddings
            
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
    """Background task to restore entity states after scene deletion"""
    import uuid
    trace_id = f"entity-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()
    
    logger.info(f"[DELETE-BG:ENTITY:START] trace_id={trace_id} story_id={story_id} sequence_number={sequence_number} seq_range={min_deleted_seq}-{max_deleted_seq} branch_id={branch_id}")
    
    try:
        import asyncio
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=delay_complete")
        
        from ..database import get_background_db
        with get_background_db() as bg_db:
            from ..models import Story, UserSettings, Scene
            from ..services.entity_state_service import EntityStateService
            
            # Phase 1: Get user settings if not provided
            phase_start = time.perf_counter()
            if not user_settings:
                user_settings_obj = bg_db.query(UserSettings).filter(
                    UserSettings.user_id == user_id
                ).first()
                if user_settings_obj:
                    user_settings = user_settings_obj.to_dict()
                else:
                    logger.warning(f"[DELETE-BG:ENTITY:WARNING] trace_id={trace_id} no_user_settings user_id={user_id}")
                    return
            logger.info(f"[DELETE-BG:ENTITY:PHASE] trace_id={trace_id} phase=get_settings duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
            
            entity_service = EntityStateService(
                user_id=user_id,
                user_settings=user_settings
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
                from ..models import CharacterState, LocationState, ObjectState
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
    except Exception as e:
        total_duration = (time.perf_counter() - task_start) * 1000
        logger.error(f"[DELETE-BG:ENTITY:ERROR] trace_id={trace_id} duration_ms={total_duration:.2f} error={e}")
        import traceback
        logger.error(f"[DELETE-BG:ENTITY:TRACEBACK] trace_id={trace_id} {traceback.format_exc()}")


@router.delete("/{story_id}/scenes/from/{sequence_number}")
async def delete_scenes_from_sequence(
    story_id: int,
    sequence_number: int,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete all scenes from a given sequence number onwards"""
    op_start = time.perf_counter()
    trace_id = f"scene-del-api-{uuid.uuid4()}"
    logger.info(f"[SCENE:DELETE:START] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} user_id={current_user.id}")
    
    # Phase 1: Query story
    phase_start = time.perf_counter()
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    logger.info(f"[SCENE:DELETE:PHASE] trace_id={trace_id} phase=query_story duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Phase 2: Get user settings for background tasks
    phase_start = time.perf_counter()
    user_settings_obj = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    user_settings = user_settings_obj.to_dict() if user_settings_obj else {}
    logger.info(f"[SCENE:DELETE:PHASE] trace_id={trace_id} phase=query_settings duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    # Get branch_id from story's current branch
    branch_id = story.current_branch_id
    logger.info(f"[SCENE:DELETE:CONTEXT] trace_id={trace_id} branch_id={branch_id}")
    
    # Phase 3: Get scene info for background tasks BEFORE deletion (filtered by branch)
    phase_start = time.perf_counter()
    from ..models import Scene as SceneModel
    scenes_to_delete_query = db.query(SceneModel).filter(
        SceneModel.story_id == story_id,
        SceneModel.sequence_number >= sequence_number
    )
    if branch_id is not None:
        scenes_to_delete_query = scenes_to_delete_query.filter(SceneModel.branch_id == branch_id)
    scenes_to_delete = scenes_to_delete_query.all()
    logger.info(f"[SCENE:DELETE:PHASE] trace_id={trace_id} phase=query_scenes duration_ms={(time.perf_counter()-phase_start)*1000:.2f} scenes_found={len(scenes_to_delete)}")
    
    # Collect scene IDs for semantic cleanup (before scenes are deleted)
    scene_ids_to_cleanup = [scene.id for scene in scenes_to_delete]
    min_deleted_seq = min(scene.sequence_number for scene in scenes_to_delete) if scenes_to_delete else sequence_number
    max_deleted_seq = max(scene.sequence_number for scene in scenes_to_delete) if scenes_to_delete else sequence_number
    
    logger.info(f"[SCENE:DELETE:PREP] trace_id={trace_id} scenes_count={len(scene_ids_to_cleanup)} seq_range={min_deleted_seq}-{max_deleted_seq} scene_ids={scene_ids_to_cleanup[:10]}{'...' if len(scene_ids_to_cleanup) > 10 else ''}")
    
    # Phase 4: Perform deletion (fast database operations only - semantic cleanup in background)
    phase_start = time.perf_counter()
    logger.info(f"[SCENE:DELETE:PHASE] trace_id={trace_id} phase=service_delete_start")
    service = SceneVariantService(db)
    success = await service.delete_scenes_from_sequence(story_id, sequence_number, skip_restoration=True, branch_id=branch_id)
    service_duration = (time.perf_counter() - phase_start) * 1000
    logger.info(f"[SCENE:DELETE:PHASE] trace_id={trace_id} phase=service_delete_end duration_ms={service_duration:.2f} success={success}")
    
    if not success:
        logger.error(f"[SCENE:DELETE:ERROR] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} service_returned_false")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete scenes"
        )
    
    # Phase 5: Schedule ALL cleanup/restoration tasks in background for fast response
    phase_start = time.perf_counter()
    
    # 1. Semantic cleanup (embeddings, character moments, plot events)
    if scene_ids_to_cleanup:
        logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=semantic_cleanup scene_count={len(scene_ids_to_cleanup)}")
        background_tasks.add_task(
            cleanup_semantic_data_in_background,
            scene_ids=scene_ids_to_cleanup,
            story_id=story_id
        )
    
    # 2. NPC tracking restoration
    logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=npc_tracking")
    background_tasks.add_task(
        restore_npc_tracking_in_background,
        story_id=story_id,
        sequence_number=sequence_number,
        branch_id=branch_id
    )
    
    # 3. Entity states restoration
    logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=entity_states")
    background_tasks.add_task(
        restore_entity_states_in_background,
        story_id=story_id,
        sequence_number=sequence_number,
        min_deleted_seq=min_deleted_seq,
        max_deleted_seq=max_deleted_seq,
        user_id=current_user.id,
        user_settings=user_settings,
        branch_id=branch_id
    )
    logger.info(f"[SCENE:DELETE:PHASE] trace_id={trace_id} phase=schedule_background duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    duration_ms = (time.perf_counter() - op_start) * 1000
    if duration_ms > 15000:
        logger.error(f"[SCENE:DELETE:SLOW] trace_id={trace_id} story_id={story_id} duration_ms={duration_ms:.2f} scenes_deleted={len(scene_ids_to_cleanup)} service_duration_ms={service_duration:.2f}")
    elif duration_ms > 5000:
        logger.warning(f"[SCENE:DELETE:SLOW] trace_id={trace_id} story_id={story_id} duration_ms={duration_ms:.2f} scenes_deleted={len(scene_ids_to_cleanup)} service_duration_ms={service_duration:.2f}")
    else:
        logger.info(f"[SCENE:DELETE:END] trace_id={trace_id} story_id={story_id} duration_ms={duration_ms:.2f} scenes_deleted={len(scene_ids_to_cleanup)}")
    
    return {"message": f"Scenes from sequence {sequence_number} onwards deleted successfully"}

# ====== DRAFT STORY MANAGEMENT ======

@router.post("/draft")
async def create_draft_story(
    story_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update a draft story with incremental progress"""
    
    step = story_data.get('step', 0)
    story_id = story_data.get('story_id')  # Allow specifying which draft to update
    
    if story_id:
        # Update specific draft story
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id,
            Story.status == StoryStatus.DRAFT
        ).first()
        
        if not story:
            raise HTTPException(status_code=404, detail="Draft story not found")
    else:
        # Check if there's already a draft for this user
        existing_draft = db.query(Story).filter(
            Story.owner_id == current_user.id,
            Story.status == StoryStatus.DRAFT
        ).first()
        
        if existing_draft:
            story = existing_draft
        else:
            story = None
    
    if story:
        # Update existing draft
        story.creation_step = step
        story.draft_data = story_data
        
        # Update story fields as they become available
        if 'title' in story_data and story_data['title']:
            story.title = story_data['title']
        if 'description' in story_data:
            story.description = story_data.get('description') or ''
        if 'genre' in story_data and story_data['genre']:
            story.genre = story_data['genre']
        if 'tone' in story_data and story_data['tone']:
            story.tone = story_data['tone']
        if 'world_setting' in story_data:
            story.world_setting = story_data.get('world_setting') or ''
        if 'initial_premise' in story_data:
            story.initial_premise = story_data.get('initial_premise') or ''
        if 'scenario' in story_data:
            story.scenario = story_data.get('scenario') or ''
            
        story.updated_at = func.now()
        
    else:
        # Create new draft
        story = Story(
            title=story_data.get('title', 'Untitled Story'),
            description=story_data.get('description', ''),
            owner_id=current_user.id,
            genre=story_data.get('genre', ''),
            tone=story_data.get('tone', ''),
            world_setting=story_data.get('world_setting', ''),
            initial_premise=story_data.get('initial_premise', ''),
            scenario=story_data.get('scenario', ''),
            status=StoryStatus.DRAFT,
            creation_step=step,
            draft_data=story_data
        )
        db.add(story)
    
    db.commit()
    db.refresh(story)
    
    return {
        "id": story.id,
        "title": story.title,
        "status": story.status,
        "creation_step": story.creation_step,
        "draft_data": story.draft_data,
        "message": "Draft saved successfully"
    }

@router.get("/draft")
async def get_draft_story(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the current draft story for the user"""
    
    draft = db.query(Story).filter(
        Story.owner_id == current_user.id,
        Story.status == StoryStatus.DRAFT
    ).first()
    
    if not draft:
        return {"draft": None}
    
    return {
        "draft": {
            "id": draft.id,
            "title": draft.title,
            "description": draft.description,
            "genre": draft.genre,
            "tone": draft.tone,
            "world_setting": draft.world_setting,
            "initial_premise": draft.initial_premise,
            "status": draft.status,
            "creation_step": draft.creation_step,
            "draft_data": draft.draft_data,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at
        }
    }

@router.get("/draft/{story_id}")
async def get_specific_draft_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific draft story by ID"""
    
    draft = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id,
        Story.status == StoryStatus.DRAFT
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft story not found")
    
    return {
        "draft": {
            "id": draft.id,
            "title": draft.title,
            "description": draft.description,
            "genre": draft.genre,
            "tone": draft.tone,
            "world_setting": draft.world_setting,
            "initial_premise": draft.initial_premise,
            "status": draft.status,
            "creation_step": draft.creation_step,
            "draft_data": draft.draft_data,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at
        }
    }

@router.post("/draft/{story_id}/finalize")
async def finalize_draft_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Convert a draft story to active status and process draft data"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id,
        Story.status == StoryStatus.DRAFT
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft story not found"
        )
    
    # Extract data from draft_data JSON
    draft_data = story.draft_data or {}
    
    # Transfer all story fields from draft_data to story columns
    # (Only update if not already set or if draft_data has a value)
    if 'description' in draft_data and draft_data.get('description'):
        story.description = draft_data['description']
    if 'world_setting' in draft_data and draft_data.get('world_setting'):
        story.world_setting = draft_data['world_setting']
    if 'initial_premise' in draft_data and draft_data.get('initial_premise'):
        story.initial_premise = draft_data['initial_premise']
    if 'scenario' in draft_data and draft_data.get('scenario'):
        story.scenario = draft_data['scenario']
        logger.info(f"[FINALIZE] Transferred scenario to story {story_id}")
    
    # Process characters from draft_data and create StoryCharacter relationships
    characters_data = draft_data.get('characters', [])
    if characters_data:
        logger.info(f"[FINALIZE] Processing {len(characters_data)} characters for story {story_id}")
        
        for char_data in characters_data:
            # If character has an ID, use it directly (from brainstorm flow)
            if 'id' in char_data and char_data['id']:
                character = db.query(Character).filter(
                    Character.id == char_data['id']
                ).first()
                
                if character:
                    logger.info(f"[FINALIZE] Using character by ID: {character.name} (ID: {character.id})")
                else:
                    logger.warning(f"[FINALIZE] Character ID {char_data['id']} not found, skipping")
                    continue
            else:
                # Check if character already exists by name
                existing_char = db.query(Character).filter(
                    Character.name == char_data.get('name'),
                    Character.creator_id == current_user.id
                ).first()
                
                if existing_char:
                    # Use existing character
                    character = existing_char
                    logger.info(f"[FINALIZE] Using existing character by name: {character.name} (ID: {character.id})")
                else:
                    # Create new character (without role - role is story-specific)
                    character = Character(
                        name=char_data.get('name', 'Unnamed'),
                        description=char_data.get('description', ''),
                        creator_id=current_user.id,
                        is_template=False,
                        is_public=False
                    )
                    db.add(character)
                    db.flush()  # Get the character ID
                    logger.info(f"[FINALIZE] Created new character: {character.name} (ID: {character.id})")
            
            # Check if StoryCharacter relationship already exists
            existing_story_char = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id,
                StoryCharacter.character_id == character.id
            ).first()
            
            if not existing_story_char:
                # Create StoryCharacter relationship with story-specific role
                story_character = StoryCharacter(
                    story_id=story_id,
                    character_id=character.id,
                    role=char_data.get('role', '')  # Store role in the relationship
                )
                db.add(story_character)
                logger.info(f"[FINALIZE] Linked character {character.name} to story {story_id} with role: {char_data.get('role', 'N/A')}")
                
                # Mark NPC as converted if it was tracked as an NPC
                try:
                    from ..services.npc_tracking_service import NPCTrackingService
                    from ..models import UserSettings
                    user_settings = db.query(UserSettings).filter(
                        UserSettings.user_id == current_user.id
                    ).first()
                    if user_settings:
                        user_settings_dict = user_settings.to_dict()
                        user_settings_dict['allow_nsfw'] = current_user.allow_nsfw
                        npc_service = NPCTrackingService(current_user.id, user_settings_dict)
                        npc_service.mark_npc_as_converted(db, story_id, character.name)
                except Exception as e:
                    logger.warning(f"Failed to mark NPC as converted during finalization: {e}")
                    # Don't fail story finalization if NPC marking fails
    
    # Ensure the story has a main branch (required for chapters)
    from ..services.branch_service import get_branch_service
    branch_service = get_branch_service()
    main_branch = branch_service.ensure_main_branch(db, story_id)
    
    # Set the story's current branch to the main branch
    if not story.current_branch_id:
        story.current_branch_id = main_branch.id
        logger.info(f"[FINALIZE] Set current_branch_id={main_branch.id} for story {story_id}")
    
    # Mark as active
    logger.info(f"[FINALIZE] Setting story {story_id} to ACTIVE status")
    story.status = StoryStatus.ACTIVE
    story.creation_step = 6  # Completed
    logger.info(f"[FINALIZE] Story {story_id} status updated: {story.status}, step: {story.creation_step}")
    
    db.commit()
    db.refresh(story)
    
    logger.info(f"[FINALIZE] Story {story_id} committed. Final status: {story.status}, step: {story.creation_step}")
    
    return {
        "id": story.id,
        "title": story.title,
        "status": story.status,
        "message": "Story finalized successfully"
    }

@router.delete("/draft/{story_id}")
async def delete_draft_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a draft story"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id,
        Story.status == StoryStatus.DRAFT
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft story not found"
        )
    
    db.delete(story)
    db.commit()
    
    return {"message": "Draft story deleted successfully"}

@router.delete("/{story_id}")
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a story and all its related data (scenes, variants, choices, flow)"""
    
    logger.info(f"[DELETE] Deleting story {story_id} for user {current_user.id}")
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get scene count for logging
    scene_count = len(story.scenes)
    logger.info(f"[DELETE] Story has {scene_count} scenes")
    
    # Delete the story - cascades will handle:
    # - StoryFlow entries (ON DELETE CASCADE)
    # - Scene entries (ON DELETE CASCADE) which cascade to:
    #   - SceneVariant entries (ON DELETE CASCADE) which cascade to:
    #     - SceneChoice entries (ON DELETE CASCADE)
    # Characters are NOT deleted (as per requirement)
    
    db.delete(story)
    db.commit()
    
    logger.info(f"[DELETE] Successfully deleted story {story_id}")
    
    return {
        "message": "Story deleted successfully",
        "story_id": story_id,
        "scenes_deleted": scene_count
    }

@router.post("/{story_id}/close")
async def close_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Close/archive a story - removes it from active story list"""
    
    logger.info(f"[CLOSE] Closing story {story_id} for user {current_user.id}")
    
    # Get the story
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        logger.error(f"[CLOSE] Story {story_id} not found for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Update story status to archived
    story.status = StoryStatus.ARCHIVED
    db.commit()
    
    logger.info(f"[CLOSE] Story {story_id} archived successfully")
    
    # If this was the last accessed story, clear it from user settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if user_settings and user_settings.last_accessed_story_id == story_id:
        user_settings.last_accessed_story_id = None
        db.commit()
        logger.info(f"[CLOSE] Cleared last_accessed_story_id for user {current_user.id}")
    
    return {
        "message": "Story closed successfully",
        "story_id": story_id,
        "status": "archived"
    }


# ====== STORY ARC ENDPOINTS ======

class GenerateArcRequest(BaseModel):
    """Request for generating a story arc."""
    structure_type: str = "three_act"  # three_act, five_act, hero_journey

class UpdateArcRequest(BaseModel):
    """Request for updating a story arc."""
    arc_data: Dict[str, Any]


@router.post("/{story_id}/arc/generate")
async def generate_story_arc(
    story_id: int,
    request: GenerateArcRequest = Body(default=GenerateArcRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a story arc for the given story.
    
    Uses AI to analyze the story's elements and create a structured narrative arc.
    
    Args:
        story_id: The story ID
        request: Arc generation options (structure type)
        
    Returns:
        Generated story arc
    """
    try:
        from ..services.brainstorm_service import BrainstormService
        
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)
        
        result = await service.generate_story_arc(
            story_id=story_id,
            structure_type=request.structure_type
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[STORY_ARC:GENERATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate story arc: {str(e)}")


@router.put("/{story_id}/arc")
async def update_story_arc(
    story_id: int,
    request: UpdateArcRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the story arc (user edits).
    
    Args:
        story_id: The story ID
        request: Updated arc data
        
    Returns:
        Updated story arc
    """
    try:
        from ..services.brainstorm_service import BrainstormService
        
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)
        
        result = service.update_story_arc(
            story_id=story_id,
            arc_data=request.arc_data
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[STORY_ARC:UPDATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update story arc: {str(e)}")


@router.get("/{story_id}/arc")
async def get_story_arc(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the story arc for a story.
    
    Args:
        story_id: The story ID
        
    Returns:
        Story arc data or null if not generated
    """
    try:
        from ..services.brainstorm_service import BrainstormService
        
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)
        
        arc = service.get_story_arc(story_id)
        
        return {
            "story_id": story_id,
            "arc": arc
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[STORY_ARC:GET] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get story arc: {str(e)}")

