from fastapi import APIRouter, Depends, HTTPException, status, Form, Body, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Tuple
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
import asyncio
from datetime import datetime, timezone

# Import background tasks and lock functions from the story_tasks submodule
from .story_tasks import (
    get_chapter_extraction_lock,
    get_story_entity_extraction_lock,
    get_story_deletion_lock,
    get_scene_variant_lock,
    get_variant_edit_lock,
    get_scene_generation_lock,
    run_extractions_in_background,
    recalculate_entities_in_background,
    run_plot_extraction_in_background,
    restore_npc_tracking_in_background,
    cleanup_semantic_data_in_background,
    restore_entity_states_in_background,
    rollback_plot_progress_in_background,
    rollback_working_memory_and_relationships_in_background,
)

# Import helper functions from story_helpers.py
from .story_helpers import (
    safe_get_custom_prompt,
    SceneVariantServiceAdapter,
    SceneVariantService,
    generate_scene_streaming,
    get_n_value_from_settings,
    create_scene_with_multi_variants,
    create_additional_variants,
    setup_auto_play_if_enabled,
    trigger_auto_play_tts,
    invalidate_extractions_for_scene,
    invalidate_and_regenerate_extractions_for_scene,
    get_or_create_user_settings,
    update_last_accessed_story,
    llm_service,
)

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


router = APIRouter()


class StoryCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    world_setting: Optional[str] = ""
    initial_premise: Optional[str] = ""
    story_mode: Optional[str] = "dynamic"  # dynamic or structured
    content_rating: Optional[str] = None  # "sfw" or "nsfw" - defaults to user's allow_nsfw setting
    plot_check_mode: Optional[str] = None  # "1" (strict), "3", or "all" - defaults to user's default_plot_check_mode
    world_id: Optional[int] = None  # Assign to existing world, or auto-create
    timeline_order: Optional[int] = None  # Position in world timeline

class StoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    tone: Optional[str] = None
    world_setting: Optional[str] = None
    initial_premise: Optional[str] = None
    scenario: Optional[str] = None
    content_rating: Optional[str] = None  # "sfw" or "nsfw"
    interaction_types: Optional[List[str]] = None  # User-defined interaction types to track
    plot_check_mode: Optional[str] = None  # "1" (strict), "3", or "all"
    world_id: Optional[int] = None  # Reassign story to a different world


class VariantGenerateRequest(BaseModel):
    custom_prompt: Optional[str] = ""
    variant_id: Optional[int] = None  # Specific variant to enhance, if None uses active variant
    is_concluding: Optional[bool] = False  # If True, generate a chapter-concluding scene (no choices)

class ContinuationRequest(BaseModel):
    custom_prompt: Optional[str] = ""

class SceneVariantUpdateRequest(BaseModel):
    content: str


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
            "content_rating": story.content_rating or "sfw",
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

    # Determine content rating: use provided value, or inherit from user's allow_nsfw setting
    if story_data.content_rating:
        content_rating = story_data.content_rating.lower()
    else:
        # Default: if user allows NSFW, default to NSFW; otherwise SFW
        content_rating = "nsfw" if current_user.allow_nsfw else "sfw"

    # Get user settings for default plot_check_mode
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()

    # Determine plot_check_mode: use provided value, or inherit from user settings
    if story_data.plot_check_mode:
        plot_check_mode = story_data.plot_check_mode
    elif user_settings and user_settings.default_plot_check_mode:
        plot_check_mode = user_settings.default_plot_check_mode
    else:
        plot_check_mode = "1"  # Default to strict

    # Resolve or auto-create world
    from ..models import World
    if story_data.world_id:
        world = db.query(World).filter(
            World.id == story_data.world_id,
            World.creator_id == current_user.id
        ).first()
        if not world:
            raise HTTPException(status_code=404, detail="World not found")
        world_id = world.id
    else:
        world = World(name=f"{story_data.title} Universe", creator_id=current_user.id)
        db.add(world)
        db.flush()
        world_id = world.id

    story = Story(
        title=story_data.title,
        description=story_data.description,
        owner_id=current_user.id,
        world_id=world_id,
        genre=story_data.genre,
        tone=story_data.tone,
        world_setting=story_data.world_setting,
        initial_premise=story_data.initial_premise,
        story_mode=story_data.story_mode or "dynamic",
        content_rating=content_rating,
        plot_check_mode=plot_check_mode,
        timeline_order=story_data.timeline_order,
    )

    db.add(story)
    db.commit()
    db.refresh(story)

    return {
        "id": story.id,
        "title": story.title,
        "description": story.description,
        "content_rating": story.content_rating,
        "message": "Story created successfully"
    }


@router.get("/{story_id}")
async def get_story(
    story_id: int,
    branch_id: int = None,
    chapter_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific story with its active flow

    Args:
        branch_id: Optional. If provided, use this branch. Otherwise uses story's current_branch_id.
        chapter_id: Optional. If provided, only return scenes for this chapter (performance optimization).
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
    flow = service.get_active_story_flow(story_id, branch_id=active_branch_id, chapter_id=chapter_id)

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
        "content_rating": story.content_rating or "sfw",
        "interaction_types": story.interaction_types or [],
        "plot_check_mode": story.plot_check_mode or "1",
        "scenes": scenes,
        "flow_info": {
            "total_scenes": len(scenes),
            "has_variants": any(scene['has_multiple_variants'] for scene in scenes)
        },
        "branch": branch_info,
        "current_branch_id": active_branch_id,
        "story_arc": story.story_arc,
        "world_id": story.world_id,
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
    if story_data.content_rating is not None:
        # Validate content rating value
        rating = story_data.content_rating.lower()
        if rating not in ("sfw", "nsfw"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="content_rating must be 'sfw' or 'nsfw'"
            )
        # Only allow NSFW if user has permission
        if rating == "nsfw" and not current_user.allow_nsfw:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create NSFW content"
            )
        story.content_rating = rating
    if story_data.interaction_types is not None:
        story.interaction_types = story_data.interaction_types
    if story_data.plot_check_mode is not None:
        # Validate plot_check_mode value
        if story_data.plot_check_mode not in ("1", "3", "all"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plot_check_mode must be '1', '3', or 'all'"
            )
        story.plot_check_mode = story_data.plot_check_mode
    if story_data.world_id is not None:
        from ..models import World
        world = db.query(World).filter(
            World.id == story_data.world_id,
            World.creator_id == current_user.id
        ).first()
        if not world:
            raise HTTPException(status_code=404, detail="World not found")
        story.world_id = story_data.world_id

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
        "content_rating": story.content_rating,
        "interaction_types": story.interaction_types,
        "plot_check_mode": story.plot_check_mode or "1",
        "world_id": story.world_id,
        "message": "Story updated successfully"
    }


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
        # Get user settings (with story for content rating)
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

        # Create context manager with user settings (uses hybrid strategy if enabled)
        context_manager = get_context_manager_for_user(user_settings, current_user.id)

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
            "recent_scenes_included": context.get("included_scenes", context.get("total_scenes", 0)),
            "summary_used": bool(context.get("scene_summary")),
            "user_settings": user_settings
        }

    except Exception as e:
        logger.error(f"Failed to analyze context for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze story context"
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

    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

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
            detail="Failed to generate choices"
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

    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

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
            detail="Failed to regenerate scene"
        )


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

@router.put("/{story_id}/choices/{choice_id}")
async def update_choice(
    story_id: int,
    choice_id: int,
    choice_text: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing choice's text (AI-generated or user-created)"""

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Find the choice
    choice = db.query(SceneChoice).filter(
        SceneChoice.id == choice_id
    ).first()

    if not choice:
        raise HTTPException(status_code=404, detail="Choice not found")

    # Verify the choice belongs to a scene in this story
    scene = db.query(Scene).filter(Scene.id == choice.scene_id).first()
    if not scene or scene.story_id != story_id:
        raise HTTPException(status_code=404, detail="Choice not found in this story")

    # Update the choice text and mark as user-edited
    choice.choice_text = choice_text.strip()
    choice.is_user_created = True  # Mark as user-modified

    db.commit()

    return {
        "message": "Choice updated",
        "choice": {
            "id": choice.id,
            "text": choice.choice_text,
            "order": choice.choice_order,
            "is_user_created": choice.is_user_created
        }
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

@router.delete("/{story_id}/scenes/from/{sequence_number}")
async def delete_scenes_from_sequence(
    story_id: int,
    sequence_number: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete all scenes from a given sequence number onwards"""
    op_start = time.perf_counter()
    trace_id = f"scene-del-api-{uuid.uuid4()}"
    logger.info(f"[SCENE:DELETE:START] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} user_id={current_user.id}")

    # Get deletion lock for this story to prevent concurrent deletions
    deletion_lock = await get_story_deletion_lock(story_id)
    if deletion_lock.locked():
        logger.warning(f"[SCENE:DELETE:CONFLICT] trace_id={trace_id} story_id={story_id} deletion already in progress")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A deletion operation is already in progress for this story. Please wait."
        )

    async with deletion_lock:
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

        # Idempotency check: if no scenes to delete, return success without doing anything
        if not scenes_to_delete:
            logger.info(f"[SCENE:DELETE:IDEMPOTENT] trace_id={trace_id} story_id={story_id} no_scenes_to_delete")
            return {"message": f"No scenes found from sequence {sequence_number} onwards (already deleted or never existed)"}

        # Collect scene IDs for semantic cleanup (before scenes are deleted)
        scene_ids_to_cleanup = [scene.id for scene in scenes_to_delete]
        min_deleted_seq = min(scene.sequence_number for scene in scenes_to_delete)
        max_deleted_seq = max(scene.sequence_number for scene in scenes_to_delete)

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

        # Phase 5: Schedule ALL cleanup/restoration tasks concurrently using asyncio.create_task
        # Using create_task instead of BackgroundTasks.add_task to run tasks concurrently
        # This prevents connection pool exhaustion from sequential task execution
        phase_start = time.perf_counter()

        # 1. Semantic cleanup (embeddings, character moments, plot events)
        if scene_ids_to_cleanup:
            logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=semantic_cleanup scene_count={len(scene_ids_to_cleanup)}")
            asyncio.create_task(
                cleanup_semantic_data_in_background(
                    scene_ids=scene_ids_to_cleanup,
                    story_id=story_id
                )
            )

        # 2. NPC tracking restoration
        logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=npc_tracking")
        asyncio.create_task(
            restore_npc_tracking_in_background(
                story_id=story_id,
                sequence_number=sequence_number,
                branch_id=branch_id
            )
        )

        # 3. Entity states restoration
        logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=entity_states")
        asyncio.create_task(
            restore_entity_states_in_background(
                story_id=story_id,
                sequence_number=sequence_number,
                min_deleted_seq=min_deleted_seq,
                max_deleted_seq=max_deleted_seq,
                user_id=current_user.id,
                user_settings=user_settings,
                branch_id=branch_id
            )
        )

        # 4. Plot progress rollback
        logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=plot_progress_rollback")
        asyncio.create_task(
            rollback_plot_progress_in_background(
                story_id=story_id,
                min_deleted_seq=min_deleted_seq,
                branch_id=branch_id
            )
        )

        # 5. Working memory and relationships rollback
        logger.info(f"[SCENE:DELETE:BG_SCHEDULE] trace_id={trace_id} task=working_memory_relationships")
        asyncio.create_task(
            rollback_working_memory_and_relationships_in_background(
                story_id=story_id,
                min_deleted_seq=min_deleted_seq,
                branch_id=branch_id
            )
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
