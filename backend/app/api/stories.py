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
import logging
import json

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
    
    def get_active_story_flow(self, story_id: int):
        return llm_service.get_active_story_flow(self.db, story_id)
    
    def get_scene_variants(self, scene_id: int):
        return llm_service.get_scene_variants(self.db, scene_id)
    
    def create_scene_with_variant(self, story_id: int, sequence_number: int, content: str, title: str = None, custom_prompt: str = None, choices: List[Dict[str, Any]] = None, generation_method: str = "auto"):
        return llm_service.create_scene_with_variant(self.db, story_id, sequence_number, content, title, custom_prompt, choices, generation_method)
    
    async def regenerate_scene_variant(self, scene_id: int, custom_prompt: str = None, user_settings: dict = None, user_id: int = None):
        # Use provided user_id or fall back to default
        actual_user_id = user_id or 1
        return await llm_service.regenerate_scene_variant(self.db, scene_id, custom_prompt, user_id=actual_user_id, user_settings=user_settings)
    
    def switch_to_variant(self, story_id: int, scene_id: int, variant_id: int):
        return llm_service.switch_to_variant(self.db, story_id, scene_id, variant_id)
    
    async def delete_scenes_from_sequence(self, story_id: int, sequence_number: int) -> bool:
        return await llm_service.delete_scenes_from_sequence(self.db, story_id, sequence_number)

# Temporary adapter functions for old LLM function calls
async def generate_scene_streaming(context, user_id, user_settings):
    async for chunk in llm_service.generate_scene_streaming(context, user_id, user_settings):
        yield chunk

async def generate_scene_continuation(context, user_id, user_settings):
    return await llm_service.generate_scene_continuation(context, user_id, user_settings)

async def generate_scene_continuation_streaming(context, user_id, user_settings):
    async for chunk in llm_service.generate_scene_continuation_streaming(context, user_id, user_settings):
        yield chunk

def SceneVariantService(db: Session):
    """Temporary adapter to maintain compatibility during migration"""
    return SceneVariantServiceAdapter(db)
from datetime import datetime

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
        db.add(user_settings_db)
        db.commit()
        db.refresh(user_settings_db)
        logger.info(f"Created default UserSettings for user {user_id}")
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

class ContinuationRequest(BaseModel):
    custom_prompt: Optional[str] = ""

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
    
    stories = query.offset(skip).limit(limit).all()
    
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
        db.add(user_settings)
    
    user_settings.last_accessed_story_id = story_id
    db.commit()

@router.get("/{story_id}")
async def get_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific story with its active flow"""
    
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
    
    # Get the active story flow instead of direct scenes
    service = SceneVariantService(db)
    flow = service.get_active_story_flow(story_id)
    
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
        }
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
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        try:
            context = await context_manager.build_scene_generation_context(
                story_id, db, effective_custom_prompt
            )
        except Exception as e:
            logger.error(f"Failed to build context for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare story context: {str(e)}"
            )
        
        # Generate scene content using enhanced method
        try:
            scene_content = await llm_service.generate_scene(context, current_user.id, user_settings)
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
        
        # Use context manager to build optimized context
        try:
            context = await context_manager.build_scene_generation_context(
                story_id, db, custom_prompt
            )
        except Exception as e:
            logger.error(f"Failed to build context for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare story context: {str(e)}"
            )
        
        # Generate scene content using enhanced method with combined choices
        try:
            scene_content, parsed_choices = await llm_service.generate_scene_with_choices(context, current_user.id, user_settings)
            
            # If choices weren't parsed, fall back to separate generation
            if not parsed_choices or len(parsed_choices) < 2:
                logger.warning("Choice parsing failed, using fallback generation")
                choice_context = await context_manager.build_choice_generation_context(story_id, db)
                parsed_choices = await llm_service.generate_choices(scene_content, choice_context, current_user.id, user_settings)
        except Exception as e:
            logger.error(f"Failed to generate scene for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate scene: {str(e)}"
            )
    
    # Create scene with variant system - use active scene count from StoryFlow
    current_scene_count = llm_service.get_active_scene_count(db, story_id)
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
            generation_method=generation_method
        )
        
        # Format choices for response (already in correct format)
        formatted_choices = choices_data
        
        # AUTO-GENERATE SUMMARIES if enabled and threshold reached
        from ..models import Chapter
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.status.in_(["active", "in_progress"])
        ).order_by(Chapter.chapter_number.desc()).first()
        
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
                    from ..api.chapters import generate_chapter_summary, generate_story_so_far
                    try:
                        await generate_chapter_summary(active_chapter.id, db, current_user.id)
                        # Also update story_so_far for context in next scene
                        await generate_story_so_far(active_chapter.id, db, current_user.id)
                        logger.info(f"[AUTO-SUMMARY] Generated summaries for chapter {active_chapter.id}")
                    except Exception as e:
                        logger.error(f"[AUTO-SUMMARY] Failed to auto-generate summaries: {e}")
                        # Don't fail the scene creation if summary fails
        
    except Exception as e:
        logger.error(f"Failed to create scene with variant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scene: {str(e)}"
        )
    
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a new scene for the story with streaming response
    
    content_mode options:
    - "ai_generate": AI generates scene from scratch (default, streams tokens)
    - "user_prompt": Use user_content as prompt for AI generation (streams tokens)
    - "user_scene": Use user_content directly as scene content, AI generates choices (sends content immediately, then streams choices)
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
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    # Handle different content modes
    effective_custom_prompt = custom_prompt
    generation_method = "auto"
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
    # else: ai_generate mode (default)
    
    # Create context manager with user settings (semantic or linear)
    context_manager = get_context_manager_for_user(user_settings, current_user.id)
    
    # Use context manager to build optimized context
    try:
        context = await context_manager.build_scene_generation_context(
            story_id, db, effective_custom_prompt
        )
    except Exception as e:
        logger.error(f"Failed to build context for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to prepare story context: {str(e)}"
        )
    
    # Calculate next sequence number - use active scene count from StoryFlow
    current_scene_count = llm_service.get_active_scene_count(db, story_id)
    next_sequence = current_scene_count + 1
    
    async def generate_stream():
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
            else:
                # Use combined scene + choices generation
                scene_context = context.copy() if isinstance(context, dict) else {"story_context": context}
                if effective_custom_prompt and effective_custom_prompt.strip():
                    scene_context["custom_prompt"] = effective_custom_prompt.strip()
                
                parsed_choices = None
                async for chunk, scene_complete, choices in llm_service.generate_scene_with_choices_streaming(
                    scene_context,
                    current_user.id,
                    user_settings
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
                    generation_method=generation_method
                )
                logger.info(f"Created scene {scene.id} with variant {variant.id} for story {story_id}")
            except Exception as e:
                logger.error(f"Failed to create scene variant: {e}")
                raise
            
            # Process semantic embeddings (async, non-blocking)
            try:
                # Get chapter ID if available
                chapter_id = None
                active_chapter = db.query(Chapter).filter(
                    Chapter.story_id == story_id,
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
                if parsed_choices and len(parsed_choices) >= 2:
                    # Use parsed choices from combined generation
                    logger.info(f"Using parsed choices from combined generation: {len(parsed_choices)} choices")
                    choices = parsed_choices
                else:
                    # Fallback: separate choice generation
                    logger.warning("Choice parsing failed or no choices found, using fallback generation")
                    choice_context = {
                        "genre": context.get("genre"),
                        "tone": context.get("tone"),
                        "characters": context.get("characters", []),
                        "current_situation": f"Scene {next_sequence}: {full_content}"
                    }
                    choices = await llm_service.generate_choices(full_content, choice_context, current_user.id, user_settings)
                
                # Format and save choices
                for i, choice_text in enumerate(choices):
                    choice = SceneChoice(
                        scene_id=scene.id,
                        scene_variant_id=variant.id,
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
                # Get or create active chapter for this story
                active_chapter = db.query(Chapter).filter(
                    Chapter.story_id == story_id,
                    Chapter.status == ChapterStatus.ACTIVE
                ).order_by(Chapter.chapter_number.desc()).first()
                
                if not active_chapter:
                    # Create first chapter if none exists
                    active_chapter = Chapter(
                        story_id=story_id,
                        chapter_number=1,
                        title="Chapter 1",
                        status=ChapterStatus.ACTIVE,
                        context_tokens_used=0,
                        scenes_count=0,
                        last_summary_scene_count=0
                    )
                    db.add(active_chapter)
                    db.flush()
                    logger.info(f"[CHAPTER] Created first chapter {active_chapter.id} for story {story_id}")
                
                # Link scene to active chapter
                scene.chapter_id = active_chapter.id
                
                # Update chapter token tracking
                scene_tokens = context_manager.count_tokens(full_content.strip())
                active_chapter.context_tokens_used += scene_tokens
                # Recalculate scenes_count from active StoryFlow instead of incrementing
                active_chapter.scenes_count = llm_service.get_active_scene_count(db, story_id, active_chapter.id)
                
                db.commit()
                logger.info(f"[CHAPTER] Linked scene {scene.id} to chapter {active_chapter.id} ({active_chapter.scenes_count} scenes, {active_chapter.context_tokens_used} tokens)")
                
                # Log scene generation status after chapter update
                try:
                    # Get thresholds from user settings
                    summary_threshold = user_settings.get('context_settings', {}).get('summary_threshold', 5) if user_settings else 5
                    extraction_threshold = user_settings.get('context_settings', {}).get('character_extraction_threshold', 5) if user_settings else 5
                    
                    # Calculate scenes since last summary and extraction
                    last_summary_count = active_chapter.last_summary_scene_count or 0
                    scenes_since_summary = active_chapter.scenes_count - last_summary_count
                    
                    last_extraction_count = active_chapter.last_extraction_scene_count or 0
                    scenes_since_extraction = active_chapter.scenes_count - last_extraction_count
                    
                    logger.warning(f"[SCENE GENERATION] Chapter {active_chapter.id} status after scene {next_sequence}:")
                    logger.warning(f"  - Total scenes: {active_chapter.scenes_count}")
                    logger.warning(f"  - Scenes since last summary: {scenes_since_summary} (threshold: {summary_threshold})")
                    logger.warning(f"  - Scenes since last extraction: {scenes_since_extraction} (threshold: {extraction_threshold}, last_extraction_count: {last_extraction_count})")
                    
                    # Check NPC tracking status
                    try:
                        from ..models import NPCTracking
                        npc_count = db.query(NPCTracking).filter(
                            NPCTracking.story_id == story_id,
                            NPCTracking.converted_to_character == False
                        ).count()
                        npc_threshold_crossed = db.query(NPCTracking).filter(
                            NPCTracking.story_id == story_id,
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
            
            # PRIORITY: Send completion data with choices IMMEDIATELY (before any background tasks)
            complete_data = {
                'type': 'complete',
                'scene_id': scene.id,
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
            yield "data: [DONE]\n\n"
            
            # PRIORITY 3: Run extractions synchronously AFTER scene and choices are sent to frontend
            # Background task: Auto-summary generation (if needed) - keep this in background
            import asyncio
            
            if active_chapter:
                try:
                    summary_threshold = user_settings.get('context_settings', {}).get('summary_threshold', 5) if user_settings else 5
                    scenes_since_last_summary = active_chapter.scenes_count - active_chapter.last_summary_scene_count
                    logger.info(f"[CHAPTER] Auto-summary check: {scenes_since_last_summary} scenes since last summary (threshold: {summary_threshold})")
                    if scenes_since_last_summary >= summary_threshold:
                        logger.info(f"[CHAPTER] Chapter {active_chapter.id} reached {summary_threshold} scenes since last summary, triggering auto-summary in background")
                        from ..api.chapters import generate_chapter_summary, generate_story_so_far
                        
                        async def generate_summaries_background():
                            try:
                                # Create a new DB session for background task
                                from ..database import SessionLocal
                                bg_db = SessionLocal()
                                try:
                                    # Reload chapter to get latest state
                                    bg_chapter = bg_db.query(Chapter).filter(Chapter.id == active_chapter.id).first()
                                    if bg_chapter:
                                        await generate_chapter_summary(bg_chapter.id, bg_db, current_user.id)
                                        await generate_story_so_far(bg_chapter.id, bg_db, current_user.id)
                                        
                                        bg_chapter.last_summary_scene_count = bg_chapter.scenes_count
                                        bg_db.commit()
                                        logger.info(f"[CHAPTER] Auto-summary and story-so-far generated for chapter {bg_chapter.id}")
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
                    
                    # Calculate scenes since last extraction
                    last_extraction_count = active_chapter.last_extraction_scene_count or 0
                    scenes_since_extraction = active_chapter.scenes_count - last_extraction_count
                    
                    logger.warning(f"[EXTRACTION] Scenes since last extraction: {scenes_since_extraction}/{extraction_threshold} for chapter {active_chapter.id}")
                    
                    if scenes_since_extraction >= extraction_threshold:
                        logger.warning(f"[EXTRACTION] Threshold reached ({scenes_since_extraction}/{extraction_threshold}), starting batch extraction for chapter {active_chapter.id}")
                        
                        # Send extraction status to frontend
                        yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'extracting', 'message': 'Extracting character and plot events...'})}\n\n"
                        
                        # Create a new DB session for extraction
                        from ..database import SessionLocal
                        extraction_db = SessionLocal()
                        try:
                            # Reload chapter to get latest state
                            extraction_chapter = extraction_db.query(Chapter).filter(Chapter.id == active_chapter.id).first()
                            if extraction_chapter:
                                from_sequence = extraction_chapter.last_extraction_scene_count or 0
                                to_sequence = extraction_chapter.scenes_count
                                
                                # Run batch extraction synchronously
                                batch_results = await batch_process_scene_extractions(
                    story_id=story_id,
                                    chapter_id=extraction_chapter.id,
                                    from_sequence=from_sequence,
                                    to_sequence=to_sequence,
                    user_id=current_user.id,
                    user_settings=user_settings or {},
                                    db=extraction_db
                                )
                                
                                # Update last extraction scene count
                                extraction_chapter.last_extraction_scene_count = extraction_chapter.scenes_count
                                extraction_db.commit()
                                logger.warning(f"[EXTRACTION] Batch extraction complete for chapter {extraction_chapter.id}:")
                                logger.warning(f"  - Scenes processed: {batch_results.get('scenes_processed', 0)}")
                                logger.warning(f"  - Character moments extracted: {batch_results.get('character_moments', 0)}")
                                logger.warning(f"  - Plot events extracted: {batch_results.get('plot_events', 0)}")
                                logger.warning(f"  - Entity states updated: {batch_results.get('entity_states', 0)}")
                                logger.warning(f"  - NPC tracking completed: {batch_results.get('npc_tracking', 0)}")
                                logger.warning(f"  - Scene embeddings created: {batch_results.get('scene_embeddings', 0)}")
                                
                                # Send extraction complete status to frontend
                                yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'complete', 'message': 'Extraction complete'})}\n\n"
                        finally:
                            extraction_db.close()
                    else:
                        # Threshold not reached - skip extraction
                        logger.warning(f"[EXTRACTION] Threshold not reached ({scenes_since_extraction}/{extraction_threshold}), skipping extraction")
                except Exception as e:
                    logger.error(f"[EXTRACTION] Failed to process extraction: {e}")
                    import traceback
                    logger.error(f"[EXTRACTION] Traceback: {traceback.format_exc()}")
                    # Send error status to frontend
                    yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'error', 'message': 'Extraction failed'})}\n\n"
                    # Don't fail scene generation if extraction fails
            
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate fresh alternative choices for the current scene"""
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No scenes found for this story"
        )
    
    # Get user settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    # Create context manager with user settings
    context_manager = ContextManager(user_settings=user_settings)
    
    try:
        # Build context for choice generation
        choice_context = await context_manager.build_choice_generation_context(
            story_id, db
        )
        
        # Generate fresh choices using LLM
        choices = await llm_service.generate_choices(
            latest_scene.content, 
            choice_context, 
            current_user.id,
            user_settings
        )
        
        return {
            "choices": [
                {
                    "text": choice_text,
                    "order": i
                }
                for i, choice_text in enumerate(choices)
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to generate more choices for story {story_id}: {e}")
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
        if request.plot_type == "complete":
            plot_points = await llm_service.generate_plot_points(context, current_user.id, user_settings, plot_type="complete")
            return {
                "plot_points": plot_points,
                "message": "Complete plot generated successfully"
            }
        else:
            plot_point = await llm_service.generate_plot_points(context, current_user.id, user_settings, plot_type="single")
            return {
                "plot_point": plot_point,
                "message": "Plot point generated successfully"
            }
        
    except ValueError as e:
        # This handles validation errors (like missing API URL)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Plot generation error: {e}")
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
            return {
                "plot_points": fallback_points,
                "message": "Plot generated (fallback mode)"
            }
        else:
            index = request.plot_point_index or 0
            return {
                "plot_point": fallback_points[min(index, len(fallback_points)-1)],
                "message": "Plot point generated (fallback mode)"
            }

# ====== NEW SCENE VARIANT ENDPOINTS ======

@router.get("/{story_id}/flow")
async def get_story_flow(
    story_id: int,
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
    
    flow = llm_service.get_active_story_flow(db, story_id)
    
    return {
        "story_id": story_id,
        "flow": flow,
        "total_scenes": len(flow)
    }

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
            'created_at': variant.created_at,
            'choices': [
                {
                    'id': choice.id,
                    'text': choice.choice_text,
                    'description': choice.choice_description,
                    'order': choice.choice_order,
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
    
    context_budget = user_settings.context_max_tokens if user_settings else 4000
    keep_recent = user_settings.context_keep_recent_scenes if user_settings else 3
    summary_threshold = user_settings.context_summary_threshold if user_settings else 5
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
        else:
            logger.warning(f"No active StoryFlow entry found for scene {scene_id}")
        
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
            from ..services.context_manager import ContextManager
            context_manager = ContextManager(user_settings=user_settings, user_id=current_user.id)
            choice_context = await context_manager.build_choice_generation_context(story_id, db)
            generated_choices = await llm_service.generate_choices(
                variant.content, 
                choice_context, 
                current_user.id, 
                user_settings
            )
            
            # Create choice records for the variant
            for idx, choice_text in enumerate(generated_choices, 1):
                choice = SceneChoice(
                    scene_id=scene_id,
                    scene_variant_id=variant.id,
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
            
            # Get original variant content for variant generation
            variant_service = SceneVariantService(db)
            original_variant = variant_service.get_active_variant(scene_id)
            
            if not original_variant or not original_variant.content:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No active variant found or variant has no content'})}\n\n"
                logger.error(f"No active variant content found for scene {scene_id}")
                return
            
            original_scene_content = original_variant.content
            logger.info(f"Original variant content length: {len(original_scene_content)} chars")
            
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'scene_id': scene_id})}\n\n"
            
            # Build context for variant generation - use same context manager as new scene generation
            context_manager = get_context_manager_for_user(user_settings, current_user.id)
            
            # Get custom_prompt from proper request model
            custom_prompt = request.custom_prompt or ""
            logger.info(f"Custom prompt extracted: {custom_prompt}")
                
            context = await context_manager.build_scene_generation_context(
                story_id, db, custom_prompt
            )
            logger.info(f"Context built successfully: {type(context)}")

            # Stream variant generation with combined choices
            variant_content = ""
            parsed_choices = None
            logger.info(f"Starting variant generation with original scene length: {len(original_scene_content)}")
            async for chunk, scene_complete, choices in llm_service.generate_variant_with_choices_streaming(
                original_scene_content,
                context,
                current_user.id,
                user_settings
            ):
                if not scene_complete:
                    # Still streaming variant content
                    variant_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                else:
                    # Variant complete, choices parsed
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
            
            # Get original variant for reference
            original_variant = db.query(SceneVariant)\
                .filter(SceneVariant.scene_id == scene_id, SceneVariant.is_original == True)\
                .first()
            
            # Create the new variant
            variant = SceneVariant(
                scene_id=scene_id,
                variant_number=next_variant_number,
                is_original=False,
                content=variant_content,
                title=scene.title,
                original_content=original_variant.content if original_variant else variant_content,
                generation_prompt=custom_prompt,
                generation_method="regeneration"
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
                if parsed_choices and len(parsed_choices) >= 2:
                    # Use parsed choices from combined generation
                    logger.info(f"Using parsed choices from combined variant generation: {len(parsed_choices)} choices")
                    generated_choices = parsed_choices
                else:
                    # Fallback: separate choice generation
                    logger.warning("Choice parsing failed for variant, using fallback generation")
                    choice_context = await context_manager.build_choice_generation_context(story_id, db)
                    generated_choices = await llm_service.generate_choices(
                        variant_content, 
                        choice_context, 
                        current_user.id, 
                        user_settings
                    )
                
                # Create choice records for the variant
                for idx, choice_text in enumerate(generated_choices, 1):
                    choice = SceneChoice(
                        scene_id=scene_id,
                        scene_variant_id=variant.id,
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
        
        # Build context for continuation
        context_manager = ContextManager(user_settings=user_settings)
        
        # Get custom_prompt from the request model
        custom_prompt = request.custom_prompt
            
        context = await context_manager.build_scene_continuation_context(
            story_id, scene_id, current_variant.content, db, custom_prompt
        )
        
        # Generate continuation content
        continuation_content = await generate_scene_continuation(context, current_user.id, user_settings)
        
        # Append to existing content
        new_content = current_variant.content + "\n\n" + continuation_content
        
        # Update the scene variant with the new content
        current_variant.content = new_content
        current_variant.updated_at = datetime.utcnow()
        db.commit()
        
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
            
            # Build context for continuation
            context_manager = ContextManager(user_settings=user_settings)
            
            # Get custom_prompt from the request model
            custom_prompt = request.custom_prompt
                
            context = await context_manager.build_scene_continuation_context(
                story_id, scene_id, current_variant.content, db, custom_prompt
            )
            
            # Stream continuation generation with combined choices
            continuation_content = ""
            parsed_choices = None
            async for chunk, scene_complete, choices in llm_service.generate_continuation_with_choices_streaming(
                context, current_user.id, user_settings
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
            current_variant.updated_at = datetime.utcnow()
            db.commit()
            
            # Generate choices for continuation if parsed, otherwise use fallback
            choices_data = []
            if parsed_choices and len(parsed_choices) >= 2:
                try:
                    # Save choices for the continuation
                    for i, choice_text in enumerate(parsed_choices, 1):
                        choice = SceneChoice(
                            scene_id=scene_id,
                            scene_variant_id=current_variant.id,
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


@router.delete("/{story_id}/scenes/from/{sequence_number}")
async def delete_scenes_from_sequence(
    story_id: int,
    sequence_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete all scenes from a given sequence number onwards"""
    
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
    success = await service.delete_scenes_from_sequence(story_id, sequence_number)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete scenes"
        )
    
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
            # Check if character already exists for this story
            existing_char = db.query(Character).filter(
                Character.name == char_data.get('name'),
                Character.creator_id == current_user.id
            ).first()
            
            if existing_char:
                # Use existing character
                character = existing_char
                logger.info(f"[FINALIZE] Using existing character: {character.name} (ID: {character.id})")
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
    
    # Mark as active
    story.status = StoryStatus.ACTIVE
    story.creation_step = 6  # Completed
    
    db.commit()
    db.refresh(story)
    
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

