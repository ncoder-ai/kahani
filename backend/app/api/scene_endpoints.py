"""
Scene generation endpoints - extracted from stories.py

Contains:
- generate_scene(): Non-streaming scene generation endpoint
- generate_scene_streaming_endpoint(): Streaming scene generation endpoint
"""
from fastapi import APIRouter, Depends, HTTPException, status, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Dict, Any, Optional
import asyncio
import logging
import json
import time
import uuid

from ..database import get_db
from ..models import (
    Story, Scene, User, SceneChoice, SceneVariant, StoryFlow, Chapter, ChapterStatus
)
from ..services.llm.service import UnifiedLLMService
from ..services.llm import LLMConnectionError
from ..dependencies import get_current_user

# Import from story_helpers.py for shared functions
from .story_helpers import (
    get_or_create_user_settings,
    SceneVariantService,
    get_n_value_from_settings,
    create_scene_with_multi_variants,
    setup_auto_play_if_enabled,
    trigger_auto_play_tts,
    llm_service,
)

# Import background tasks
from .story_tasks import (
    get_scene_generation_lock,
    run_extractions_in_background,
    run_plot_extraction_in_background,
    run_chronicle_extraction_in_background,
    update_working_memory_in_background,
    run_inline_entity_extraction_background,
    run_chapter_summary_background,
)

# Lazy import for semantic integration
try:
    from ..services.semantic_integration import get_context_manager_for_user
    SEMANTIC_MEMORY_AVAILABLE = True
except Exception:
    SEMANTIC_MEMORY_AVAILABLE = False
    def get_context_manager_for_user(user_settings, user_id):
        from ..services.context_manager import ContextManager
        return ContextManager(user_settings=user_settings, user_id=user_id)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{story_id}/scenes")
async def generate_scene(
    story_id: int,
    background_tasks: BackgroundTasks,
    custom_prompt: str = Form(""),
    user_content: str = Form(""),
    content_mode: str = Form("ai_generate"),
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

    # Get user settings and include permission flags (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

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
                detail="Failed to prepare story context"
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
                detail="Failed to prepare story context"
            )

        # Generate scene content using enhanced method
        try:
            scene_content = await llm_service.generate_scene(context, current_user.id, user_settings, db)
        except Exception as e:
            logger.error(f"Failed to generate scene for story {story_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate scene"
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
                detail="Failed to prepare story context"
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
                detail="Failed to generate scene"
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

    # Get or create active chapter BEFORE scene creation to ensure chapter_id is set atomically
    active_chapter = None
    chapter_id = None
    try:
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

        chapter_id = active_chapter.id
    except Exception as e:
        logger.error(f"[CHAPTER] Failed to get/create chapter: {e}")
        # Continue without chapter - scene will still be created

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
            branch_id=active_branch_id,
            chapter_id=chapter_id,
            context=context  # Auto-extracts entity_states_snapshot for cache consistency
        )

        # Format choices for response (already in correct format)
        formatted_choices = choices_data

        # Chapter integration - update chapter stats (chapter already linked during scene creation)
        if active_chapter:
            try:
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
                logger.info(f"[CHAPTER] Updated chapter {active_chapter.id} stats ({active_chapter.scenes_count} scenes, {active_chapter.context_tokens_used} tokens)")

                # AUTO-GENERATE SUMMARIES if enabled and threshold reached
                if user_settings:
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
            detail="Failed to create scene"
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
                    # First, check if this prompt matches an existing choice (AI or user-created)
                    # This prevents creating duplicate choices when user selects an existing AI choice
                    existing_choice_with_text = db.query(SceneChoice).filter(
                        SceneChoice.scene_variant_id == previous_flow.scene_variant_id,
                        SceneChoice.choice_text == custom_prompt.strip()
                    ).first()

                    if existing_choice_with_text:
                        # Update existing choice to point to new scene (don't create duplicate)
                        existing_choice_with_text.leads_to_scene_id = scene.id
                        logger.info(f"Updated existing choice {existing_choice_with_text.id} to point to scene {scene.id}")
                    else:
                        # Check for existing user-created choice to update
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

    # Update working memory in background (scene-to-scene continuity tracking)
    try:
        background_tasks.add_task(
            update_working_memory_in_background,
            story_id=story_id,
            branch_id=active_branch_id,
            chapter_id=active_chapter.id if active_chapter else None,
            scene_sequence=next_sequence,
            scene_content=scene_content,
            user_id=current_user.id,
            user_settings=user_settings or {},
            scene_generation_context=context  # Pass context for cache-friendly extraction
        )
    except Exception as e:
        logger.error(f"[WORKING_MEMORY] Failed to schedule update: {e}")

    return response_data


@router.post("/{story_id}/scenes/stream")
async def generate_scene_streaming_endpoint(
    story_id: int,
    background_tasks: BackgroundTasks,
    custom_prompt: str = Form(""),
    user_content: str = Form(""),
    content_mode: str = Form("ai_generate"),
    is_concluding: str = Form("false"),
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
    logger.warning(f"[SCENE:STREAM:PARAMS] trace_id={trace_id} custom_prompt='{custom_prompt[:100] if custom_prompt else 'EMPTY'}' user_content='{user_content[:100] if user_content else 'EMPTY'}'")

    # Check if scene generation is already in progress for this story
    # Use non-blocking check since this is a streaming endpoint
    generation_lock = await get_scene_generation_lock(story_id)
    if generation_lock.locked():
        logger.warning(f"[SCENE:STREAM:CONFLICT] trace_id={trace_id} story_id={story_id} scene generation already in progress")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scene generation is already in progress for this story. Please wait for it to complete."
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

    # Get active branch
    active_branch_id = story.current_branch_id
    if not active_branch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Story has no active branch. Please create a branch first."
        )

    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

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
                detail="Failed to prepare story context"
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

    # Get or create active chapter for character separation (filtered by branch)
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

    chapter_id = active_chapter.id

    # Use context manager to build optimized context
    logger.warning(f"[SCENE:STREAM:CONTEXT] Building context with effective_custom_prompt='{effective_custom_prompt[:100] if effective_custom_prompt else 'EMPTY'}'")
    try:
        context = await context_manager.build_scene_generation_context(
            story_id, db, effective_custom_prompt, is_variant_generation=False, chapter_id=chapter_id, branch_id=active_branch_id
        )
    except Exception as e:
        logger.error(f"Failed to build context for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare story context"
        )

    # Calculate next sequence number - use active scene count from StoryFlow
    current_scene_count = llm_service.get_active_scene_count(db, story_id, branch_id=active_branch_id)
    next_sequence = current_scene_count + 1

    async def generate_stream():
        nonlocal active_chapter  # Use outer scope's active_chapter variable
        # Acquire lock for the duration of scene generation
        async with generation_lock:
            full_content = ""
            thinking_content = ""
            is_thinking = False

            # Quick health check before starting generation
            try:
                client = llm_service.get_user_client(current_user.id, user_settings)
                is_healthy, health_msg = await client.check_health(timeout=3.0)
                if not is_healthy:
                    logger.error(f"[SCENE STREAM] LLM health check failed: {health_msg}")
                    yield f"data: {json.dumps({'type': 'error', 'message': f'LLM server unavailable: {health_msg}'})}\n\n"
                    return
            except Exception as e:
                logger.warning(f"[SCENE STREAM] Health check error (proceeding anyway): {e}")
                # Don't block on health check failures - let the actual generation try

            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'sequence': next_sequence})}\n\n"

            # Wrap entire generation in try-except to catch LLM connection errors
            try:
                # Check for multi-generation (n > 1)
                n_value = get_n_value_from_settings(user_settings)

                if n_value > 1 and not user_provided_content:
                    # =====================================================================
                    # MULTI-GENERATION PATH (n > 1)
                    # =====================================================================
                    logger.info(f"[MULTI-GEN] Starting multi-generation with n={n_value} for story {story_id}")

                    generation_prefs = user_settings.get("generation_preferences", {})
                    separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

                    scene_context = context.copy() if isinstance(context, dict) else {"story_context": context}
                    if effective_custom_prompt and effective_custom_prompt.strip():
                        scene_context["custom_prompt"] = effective_custom_prompt.strip()

                    variants_data = None

                    if is_concluding_bool:
                        # Multi-generation concluding scene (no choices)
                        chapter_info = {
                            "chapter_number": active_chapter.chapter_number if active_chapter else 1,
                            "chapter_title": active_chapter.title if active_chapter else "Untitled",
                            "chapter_location": active_chapter.location_name if active_chapter else "Unknown",
                            "chapter_time_period": active_chapter.time_period if active_chapter else "Unknown",
                            "chapter_scenario": active_chapter.scenario if active_chapter else "None"
                        }

                        async for chunk, is_complete, contents in llm_service.generate_concluding_scene_streaming_multi(
                            scene_context,
                            chapter_info,
                            current_user.id,
                            user_settings,
                            db,
                            n_value
                        ):
                            if not is_complete:
                                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                            else:
                                # Convert contents to variants_data format (no choices for concluding scenes)
                                variants_data = [{"content": c, "choices": []} for c in contents]

                    elif separate_choice_generation:
                        # Separate mode: generate scenes, then choices in parallel
                        async for chunk, is_complete, contents in llm_service.generate_scene_streaming_multi(
                            scene_context,
                            current_user.id,
                            user_settings,
                            db,
                            n_value
                        ):
                            if not is_complete:
                                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                            else:
                                # Generate choices for all variants in parallel
                                yield f"data: {json.dumps({'type': 'status', 'message': 'Generating choices for all variants...'})}\n\n"
                                all_choices = await llm_service.generate_choices_for_variants(
                                    contents,
                                    scene_context,
                                    current_user.id,
                                    user_settings,
                                    db
                                )
                                variants_data = [
                                    {"content": c, "choices": ch}
                                    for c, ch in zip(contents, all_choices)
                                ]

                    else:
                        # Combined mode: scene + choices together
                        async for chunk, is_complete, vdata in llm_service.generate_scene_with_choices_streaming_multi(
                            scene_context,
                            current_user.id,
                            user_settings,
                            db,
                            n_value
                        ):
                            if not is_complete:
                                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                            else:
                                variants_data = vdata

                    # Create Scene with multiple variants (chapter_id already set atomically)
                    if variants_data:
                        scene, created_variants = create_scene_with_multi_variants(
                            db=db,
                            story_id=story_id,
                            sequence_number=next_sequence,
                            variants_data=variants_data,
                            branch_id=active_branch_id,
                            generation_method=generation_method,
                            title=f"Scene {next_sequence}",
                            custom_prompt=effective_custom_prompt if effective_custom_prompt else None,
                            chapter_id=chapter_id,
                            context=scene_context  # Auto-extracts entity_states_snapshot
                        )

                        # Format response
                        variants_response = []
                        for v in created_variants:
                            # Get choices for this variant
                            variant_choices = db.query(SceneChoice).filter(
                                SceneChoice.scene_variant_id == v.id
                            ).order_by(SceneChoice.choice_order).all()

                            variants_response.append({
                                "id": v.id,
                                "variant_number": v.variant_number,
                                "content": v.content,
                                "is_original": v.is_original,
                                "choices": [{"text": c.choice_text, "order": c.choice_order} for c in variant_choices]
                            })

                        # Send multi_complete event
                        yield f"data: {json.dumps({'type': 'multi_complete', 'scene_id': scene.id, 'sequence': next_sequence, 'total_variants': len(created_variants), 'variants': variants_response, 'chapter_id': chapter_id})}\n\n"

                        # Update chapter stats (chapter_id already set during scene creation)
                        if active_chapter:
                            active_chapter.scenes_count = llm_service.get_active_scene_count(db, story_id, branch_id=active_branch_id, chapter_id=active_chapter.id)
                            db.commit()

                        logger.info(f"[MULTI-GEN] Created scene {scene.id} with {len(created_variants)} variants in chapter {chapter_id}")

                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return  # Exit early - don't continue to single-generation path
                    else:
                        logger.error("[MULTI-GEN] No variants data generated")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to generate variants'})}\n\n"
                        return

                # =====================================================================
                # SINGLE-GENERATION PATH (n == 1 or user_provided_content)
                # =====================================================================

                # Handle user-provided content vs AI generation
                if user_provided_content:
                    # User wrote their own scene - send it immediately as a single chunk
                    full_content = user_provided_content
                    yield f"data: {json.dumps({'type': 'content', 'chunk': user_provided_content})}\n\n"
                    parsed_choices = None  # User-provided scenes need separate choice generation
                    scene_context = context  # No LLM generation, so no snapshot, but we need scene_context defined
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

                    # Use context directly (no copy needed for concluding scenes)
                    # Store reference in scene_context for consistent snapshot retrieval
                    scene_context = context

                    async for chunk in llm_service.generate_concluding_scene_streaming(
                        scene_context,
                        chapter_info,
                        current_user.id,
                        user_settings,
                        db
                    ):
                        # Check if this is thinking content
                        if chunk.startswith("__THINKING__:"):
                            thinking_chunk = chunk[13:]  # Remove prefix
                            thinking_content += thinking_chunk
                            if not is_thinking:
                                is_thinking = True
                                yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"
                            yield f"data: {json.dumps({'type': 'thinking_chunk', 'chunk': thinking_chunk})}\n\n"
                        else:
                            if is_thinking:
                                is_thinking = False
                                yield f"data: {json.dumps({'type': 'thinking_end', 'total_chars': len(thinking_content)})}\n\n"
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
                            # Check if this is thinking content (prefixed by LLM service)
                            if chunk.startswith("__THINKING__:"):
                                thinking_chunk = chunk[13:]  # Remove prefix
                                thinking_content += thinking_chunk
                                if not is_thinking:
                                    # First thinking chunk - send thinking_start
                                    is_thinking = True
                                    yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"
                                # Stream thinking chunk to frontend
                                yield f"data: {json.dumps({'type': 'thinking_chunk', 'chunk': thinking_chunk})}\n\n"
                            else:
                                # Regular content - send thinking_end if we were thinking
                                if is_thinking:
                                    is_thinking = False
                                    yield f"data: {json.dumps({'type': 'thinking_end', 'total_chars': len(thinking_content)})}\n\n"
                                # Stream regular content
                                full_content += chunk
                                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
                        else:
                            # Scene complete, choices parsed
                            # Make sure to close thinking if still open
                            if is_thinking:
                                yield f"data: {json.dumps({'type': 'thinking_end', 'total_chars': len(thinking_content)})}\n\n"
                            parsed_choices = choices
                            break

            except LLMConnectionError as conn_error:
                # Centralized handler for LLM connection failures
                logger.error(f"[SCENE STREAM] LLM connection error: {conn_error}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(conn_error)})}\n\n"
                return
            except Exception as gen_error:
                # Catch any other generation errors
                error_msg = str(gen_error)
                logger.error(f"[SCENE STREAM] Generation failed: {error_msg}")
                yield f"data: {json.dumps({'type': 'error', 'message': f'Scene generation failed: {error_msg}'})}\n\n"
                return

            # Propagate semantic improvement state from scene_context back to original context
            # so background tasks (summary, extraction, working memory) don't re-run the agent
            # AND get the same RELATED PAST SCENES text for cache-friendly prefix matching.
            # scene_context is a .copy() of context — these fields were set on the copy during scene gen.
            if scene_context.get("_semantic_improved"):
                context["_semantic_improved"] = True
                context["semantic_scenes_text"] = scene_context.get("semantic_scenes_text")

            # Save the scene to database FIRST (before choices)
            # Clean the final assembled content comprehensively (chunk cleaning may miss patterns)
            cleaned_full_content = llm_service._clean_scene_content(full_content.rstrip())

            # Get or create active chapter BEFORE scene creation to ensure chapter_id is set atomically
            chapter_id = None
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

            chapter_id = active_chapter.id

            variant_service = SceneVariantService(db)
            try:
                # Pass scene_context to automatically extract _entity_states_snapshot
                scene, variant = variant_service.create_scene_with_variant(
                    story_id=story_id,
                    sequence_number=next_sequence,
                    content=cleaned_full_content,
                    title=f"Scene {next_sequence}",
                    custom_prompt=effective_custom_prompt if effective_custom_prompt else None,
                    choices=[],  # We'll add choices later
                    generation_method=generation_method,
                    branch_id=active_branch_id,
                    chapter_id=chapter_id,
                    context=scene_context  # Auto-extracts entity_states_snapshot
                )
                logger.info(f"Created scene {scene.id} with variant {variant.id} for story {story_id} on branch {active_branch_id} chapter {chapter_id} trace_id={trace_id}")
            except Exception as e:
                logger.error(f"Failed to create scene variant: {e} trace_id={trace_id}")
                raise

            # Process semantic embeddings (async, non-blocking)
            try:
                # chapter_id already set above
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
                    # Reuse the scene generation context (scene_context, not context) so the
                    # improved semantic_scenes_text and _semantic_improved flag carry over → cache hit
                    choices = await llm_service.generate_choices(full_content, scene_context, current_user.id, user_settings, db)

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

            # Chapter integration - update chapter stats (chapter already created/linked during scene creation)
            # active_chapter was set earlier before scene creation
            try:
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
                            # First, check if this prompt matches an existing choice (AI or user-created)
                            # This prevents creating duplicate choices when user selects an existing AI choice
                            existing_choice_with_text = db.query(SceneChoice).filter(
                                SceneChoice.scene_variant_id == previous_flow.scene_variant_id,
                                SceneChoice.choice_text == custom_prompt.strip()
                            ).first()

                            if existing_choice_with_text:
                                # Update existing choice to point to new scene (don't create duplicate)
                                existing_choice_with_text.leads_to_scene_id = scene.id
                                logger.info(f"Updated existing choice {existing_choice_with_text.id} to point to scene {scene.id}")
                            else:
                                # Check for existing user-created choice to update
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
                'content': cleaned_full_content,  # Include cleaned content for non-streaming mode
                'choices': choices_data,
                'chapter_id': chapter_id
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

                        # Schedule summary generation via background_tasks for sequential execution
                        # This runs LAST after all extractions complete
                        # Pass scene_generation_context for cache-friendly summary generation
                        background_tasks.add_task(
                            run_chapter_summary_background,
                            chapter_id=active_chapter.id,
                            user_id=current_user.id,
                            scene_generation_context=context.copy() if context else None,
                            user_settings=user_settings
                        )
                        logger.info(f"[CHAPTER] Scheduled background summary generation (cache-friendly) for chapter {active_chapter.id}")
                except Exception as e:
                    logger.error(f"[AUTO-SUMMARY] Failed to start background summary generation: {e}")
                    # Don't fail scene generation if summary fails

            # Run extractions synchronously - no background tasks
            if active_chapter:
                try:
                    # Get extraction threshold from user settings
                    ctx_settings = user_settings.get('context_settings', {}) if user_settings else {}
                    extraction_threshold = ctx_settings.get(
                        'character_extraction_threshold',
                        5  # Default threshold
                    )
                    # Inline check requires parent contradiction detection to be enabled
                    enable_contradiction_detection = ctx_settings.get('enable_contradiction_detection', True)
                    enable_inline_check = ctx_settings.get('enable_inline_contradiction_check', False) and enable_contradiction_detection

                    # Override threshold to 1 when inline check is enabled
                    effective_threshold = 1 if enable_inline_check else extraction_threshold

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

                        logger.warning(f"[EXTRACTION] Scenes since last extraction: {scenes_since_extraction}/{effective_threshold} for chapter {active_chapter.id} (inline_check={enable_inline_check})")
                        logger.warning(f"[EXTRACTION] Chapter {active_chapter.id} has {len(scenes_in_chapter)} scenes (sequences {min(scene_sequence_numbers)} to {max_sequence_in_chapter}), last extracted: {last_extraction_sequence}")

                        # === INLINE CONTRADICTION CHECK (if enabled) ===
                        # Uses FastAPI background_tasks for sequential execution with other LLM tasks
                        if enable_inline_check:
                            logger.warning(f"[INLINE_CHECK] Scheduling background entity extraction for contradiction check")
                            yield f"data: {json.dumps({'type': 'contradiction_check', 'status': 'scheduled'})}\n\n"

                            # Schedule inline check FIRST so it runs before other extractions
                            background_tasks.add_task(
                                run_inline_entity_extraction_background,
                                story_id=story_id,
                                chapter_id=active_chapter.id,
                                scene_id=scene.id,
                                scene_sequence=scene.sequence_number,
                                scene_content=cleaned_full_content,
                                user_id=current_user.id,
                                user_settings=user_settings or {},
                                branch_id=active_branch_id,
                                scene_generation_context=context.copy() if context else {}
                            )
                            logger.info(f"[INLINE_CHECK] Background task scheduled for scene {scene.sequence_number}")

                        # === FULL EXTRACTION AT NORMAL THRESHOLD ===
                        # Character moments, plot events, NPCs, scene embeddings
                        # (Entity states already done by inline check if enabled)
                        if scenes_since_extraction >= extraction_threshold:
                            logger.warning(f"[EXTRACTION] ✓ SCHEDULED: Threshold reached ({scenes_since_extraction}/{extraction_threshold})")

                            # Schedule extraction to run after response completes
                            # Use actual sequence numbers, not scenes_count
                            # If inline_check ran, entity states are already done for this scene
                            background_tasks.add_task(
                                run_extractions_in_background,
                                story_id=story_id,
                                chapter_id=active_chapter.id,
                                from_sequence=last_extraction_sequence,
                                to_sequence=max_sequence_in_chapter,
                                user_id=current_user.id,
                                user_settings=user_settings or {},
                                scene_generation_context=context,  # Pass context for cache-friendly extraction
                                skip_entity_states=enable_inline_check  # Skip if already done by inline check
                            )

                            # Send status event with clear message
                            extraction_msg = f"Extracting ({scenes_since_extraction}/{extraction_threshold})"
                            yield f"data: {json.dumps({'type': 'extraction_status', 'status': 'scheduled', 'message': extraction_msg})}\n\n"
                        else:
                            # Threshold not reached - skip extraction with clear reason
                            # Show extraction_threshold (not effective_threshold) since that's what full extraction uses
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

            # === PLOT EVENT EXTRACTION (SEPARATE FROM ENTITY EXTRACTION) ===
            # Check if plot event extraction should run independently
            if active_chapter and active_chapter.chapter_plot:
                try:
                    # Get plot event extraction threshold from user settings
                    plot_extraction_threshold = user_settings.get('context_settings', {}).get(
                        'plot_event_extraction_threshold',
                        5  # Default threshold
                    ) if user_settings else 5

                    # Check if plot tracking is enabled
                    generation_prefs = user_settings.get("generation_preferences", {}) if user_settings else {}
                    enable_plot_tracking = generation_prefs.get("enable_chapter_plot_tracking", True)

                    if enable_plot_tracking:
                        # Get scenes in this chapter
                        scenes_in_chapter = db.query(Scene).join(StoryFlow).filter(
                            StoryFlow.story_id == story_id,
                            StoryFlow.is_active == True,
                            Scene.chapter_id == active_chapter.id,
                            Scene.is_deleted == False
                        ).order_by(Scene.sequence_number).all()

                        if scenes_in_chapter:
                            scene_sequence_numbers = [s.sequence_number for s in scenes_in_chapter]
                            max_sequence_in_chapter = max(scene_sequence_numbers)
                            last_plot_extraction_sequence = active_chapter.last_plot_extraction_scene_count or 0

                            # Count scenes since last plot extraction
                            scenes_since_plot_extraction = len([s for s in scene_sequence_numbers if s > last_plot_extraction_sequence])

                            logger.warning(f"[PLOT_EXTRACTION] Scenes since last plot extraction: {scenes_since_plot_extraction}/{plot_extraction_threshold} for chapter {active_chapter.id}")

                            if scenes_since_plot_extraction >= plot_extraction_threshold:
                                logger.warning(f"[PLOT_EXTRACTION] ✓ SCHEDULED: Threshold reached ({scenes_since_plot_extraction}/{plot_extraction_threshold})")

                                # Schedule plot extraction to run after response completes
                                background_tasks.add_task(
                                    run_plot_extraction_in_background,
                                    story_id=story_id,
                                    chapter_id=active_chapter.id,
                                    from_sequence=last_plot_extraction_sequence,
                                    to_sequence=max_sequence_in_chapter,
                                    user_id=current_user.id,
                                    user_settings=user_settings or {},
                                    scene_generation_context=context
                                )

                                # Send status event
                                plot_msg = f"Plot tracking ({scenes_since_plot_extraction}/{plot_extraction_threshold})"
                                yield f"data: {json.dumps({'type': 'plot_extraction_status', 'status': 'scheduled', 'message': plot_msg})}\n\n"
                            else:
                                # Threshold not reached
                                skip_msg = f"Plot tracking skipped ({scenes_since_plot_extraction}/{plot_extraction_threshold})"
                                logger.warning(f"[PLOT_EXTRACTION] ✗ SKIPPED: {skip_msg}")
                                yield f"data: {json.dumps({'type': 'plot_extraction_status', 'status': 'skipped', 'message': skip_msg})}\n\n"
                except Exception as e:
                    logger.error(f"[PLOT_EXTRACTION] Failed to check plot extraction: {e}")
                    import traceback
                    logger.error(f"[PLOT_EXTRACTION] Traceback: {traceback.format_exc()}")

            # === CHRONICLE EXTRACTION (world lorebook + character chronicle) ===
            if active_chapter and story.world_id:
                try:
                    chronicle_threshold = user_settings.get('context_settings', {}).get(
                        'chronicle_extraction_threshold', 5
                    ) if user_settings else 5

                    # Query scenes in this chapter for threshold check
                    ch_scenes_for_chronicle = db.query(Scene).join(StoryFlow).filter(
                        StoryFlow.story_id == story_id,
                        StoryFlow.is_active == True,
                        Scene.chapter_id == active_chapter.id,
                        Scene.is_deleted == False,
                    ).order_by(Scene.sequence_number).all()
                    chronicle_scene_seqs = [s.sequence_number for s in ch_scenes_for_chronicle]

                    last_chronicle_seq = active_chapter.last_chronicle_scene_count or 0
                    scenes_since_chronicle = len([s for s in chronicle_scene_seqs if s > last_chronicle_seq])

                    if scenes_since_chronicle >= chronicle_threshold:
                        max_seq_chapter = max(chronicle_scene_seqs) if chronicle_scene_seqs else 0
                        logger.warning(f"[CHRONICLE] ✓ SCHEDULED: Threshold reached ({scenes_since_chronicle}/{chronicle_threshold})")
                        background_tasks.add_task(
                            run_chronicle_extraction_in_background,
                            story_id=story_id,
                            chapter_id=active_chapter.id,
                            from_sequence=last_chronicle_seq,
                            to_sequence=max_seq_chapter,
                            user_id=current_user.id,
                            user_settings=user_settings or {},
                            scene_generation_context=context,
                        )
                        yield f"data: {json.dumps({'type': 'chronicle_status', 'status': 'scheduled'})}\n\n"
                    else:
                        logger.info(f"[CHRONICLE] Skipped ({scenes_since_chronicle}/{chronicle_threshold})")
                        yield f"data: {json.dumps({'type': 'chronicle_status', 'status': 'skipped'})}\n\n"

                except Exception as e:
                    logger.error(f"[CHRONICLE] Failed to check chronicle extraction: {e}")
                    import traceback
                    logger.error(f"[CHRONICLE] Traceback: {traceback.format_exc()}")

            # === WORKING MEMORY UPDATE (runs every scene for continuity) ===
            # Check if enabled before scheduling
            ctx_settings_for_tasks = user_settings.get('context_settings', {}) if user_settings else {}
            if ctx_settings_for_tasks.get('enable_working_memory', True):
                try:
                    background_tasks.add_task(
                        update_working_memory_in_background,
                        story_id=story_id,
                        branch_id=active_branch_id,
                        chapter_id=active_chapter.id if active_chapter else None,
                        scene_sequence=scene.sequence_number,
                        scene_content=cleaned_full_content,
                        user_id=current_user.id,
                        user_settings=user_settings or {},
                        scene_generation_context=context  # Pass context for cache-friendly extraction
                    )
                    logger.info(f"[WORKING_MEMORY] Scheduled update for scene {scene.sequence_number}")
                except Exception as e:
                    logger.error(f"[WORKING_MEMORY] Failed to schedule update: {e}")

            # Relationship extraction removed — low ROI, separate LLM call not justified

            # Send [DONE] as the LAST event after all extraction status events
            yield "data: [DONE]\n\n"

    # Check if streaming is disabled in user settings
    generation_prefs = user_settings.get("generation_preferences", {})
    enable_streaming = generation_prefs.get("enable_streaming", True)

    if not enable_streaming:
        # Non-streaming mode: collect all generator output and return JSON
        logger.info(f"[SCENE:NON-STREAMING:START] trace_id={trace_id} story_id={story_id}")

        complete_data = None
        full_content = ""
        chunk_count = 0

        try:
            async for chunk in generate_stream():
                chunk_count += 1
                if chunk_count % 10 == 0:
                    logger.info(f"[SCENE:NON-STREAMING:PROGRESS] trace_id={trace_id} chunks={chunk_count}")

                # Parse SSE format: "data: {...}\n\n"
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        logger.info(f"[SCENE:NON-STREAMING:DONE] trace_id={trace_id} total_chunks={chunk_count}")
                        continue
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "content":
                            full_content += event.get("chunk", "")
                        elif event.get("type") == "complete":
                            complete_data = event
                            logger.info(f"[SCENE:NON-STREAMING:COMPLETE] trace_id={trace_id} scene_id={event.get('scene_id')}")
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"[SCENE:NON-STREAMING:ERROR] trace_id={trace_id} error={e}")
            raise

        if complete_data:
            from fastapi.responses import JSONResponse
            # Use cleaned content from completion event, not raw full_content which includes ###CHOICES### marker
            cleaned_content = complete_data.get("content", full_content)
            logger.info(f"[SCENE:NON-STREAMING:RETURN] trace_id={trace_id} content_len={len(cleaned_content)}")
            return JSONResponse(content={
                "scene_id": complete_data.get("scene_id"),
                "variant_id": complete_data.get("variant_id"),
                "content": cleaned_content,
                "choices": complete_data.get("choices", []),
                "chapter_id": complete_data.get("chapter_id")
            })
        else:
            logger.error(f"[SCENE:NON-STREAMING:NO_COMPLETE] trace_id={trace_id} chunks={chunk_count}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Scene generation failed - no completion data received"
            )

    # Streaming mode: return StreamingResponse
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
