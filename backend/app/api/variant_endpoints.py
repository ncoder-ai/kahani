"""
Variant management endpoints - extracted from stories.py

Contains:
- get_scene_variants(): Get all variants for a scene
- create_scene_variant(): Create new variant (non-streaming)
- create_scene_variant_streaming(): Create new variant (streaming)
- activate_scene_variant(): Activate a specific variant
- continue_scene(): Continue scene (non-streaming)
- continue_scene_streaming(): Continue scene (streaming)
- update_scene_variant(): Update variant content
- regenerate_scene_variant_choices(): Regenerate choices for variant
"""
from fastapi import APIRouter, Depends, HTTPException, status, Form, Body, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging
import json
import time
import uuid
import asyncio
from datetime import datetime, timezone

from ..database import get_db
from ..models import (
    Story, Scene, User, UserSettings, SceneChoice, SceneVariant, StoryFlow, Chapter, ChapterStatus
)


class ThinkingStreamHandler:
    """Helper class to handle thinking/reasoning content in SSE streams."""

    def __init__(self):
        self.is_thinking = False
        self.thinking_content = ""

    def process_chunk(self, chunk: str) -> list:
        """
        Process a chunk and return list of SSE event strings to yield.

        Returns list of formatted SSE data strings (without the 'data: ' prefix).
        """
        events = []

        if chunk.startswith("__THINKING__:"):
            thinking_chunk = chunk[13:]
            self.thinking_content += thinking_chunk
            if not self.is_thinking:
                self.is_thinking = True
                events.append(json.dumps({'type': 'thinking_start'}))
            events.append(json.dumps({'type': 'thinking_chunk', 'chunk': thinking_chunk}))
            return events, None  # No content to accumulate
        else:
            if self.is_thinking:
                self.is_thinking = False
                events.append(json.dumps({'type': 'thinking_end', 'total_chars': len(self.thinking_content)}))
            events.append(json.dumps({'type': 'content', 'chunk': chunk}))
            return events, chunk  # Return chunk for content accumulation
from ..services.llm.service import UnifiedLLMService
from ..dependencies import get_current_user
from ..config import settings

# Import from stories.py for shared models
from .stories import ContinuationRequest, SceneVariantUpdateRequest

# Import from story_helpers.py for shared functions
from .story_helpers import (
    get_or_create_user_settings,
    SceneVariantService,
    get_n_value_from_settings,
    create_scene_with_multi_variants,
    create_additional_variants,
    setup_auto_play_if_enabled,
    trigger_auto_play_tts,
    invalidate_extractions_for_scene,
    invalidate_and_regenerate_extractions_for_scene,
    llm_service,
)

# Import background tasks
from .story_tasks import (
    get_scene_variant_lock,
    get_variant_edit_lock,
    recalculate_entities_in_background,
    cleanup_semantic_data_in_background,
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


# Request model for variant generation
class VariantGenerateRequest(BaseModel):
    custom_prompt: Optional[str] = None
    variant_id: Optional[int] = None  # Specific variant to regenerate from
    is_concluding: Optional[bool] = False  # Whether to generate a concluding scene


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

    # Get variant generation lock for this scene to prevent concurrent regenerations
    variant_lock = await get_scene_variant_lock(scene_id)
    if variant_lock.locked():
        logger.warning(f"[SCENE:VARIANT:CONFLICT] trace_id={trace_id} scene_id={scene_id} variant generation already in progress")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A variant generation is already in progress for this scene. Please wait."
        )

    async with variant_lock:
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()

        if not story:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Story not found"
            )

        # Verify scene still exists (idempotency check)
        scene_check = db.query(Scene).filter(Scene.id == scene_id, Scene.story_id == story_id).first()
        if not scene_check:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scene not found or has been deleted"
            )

        # Get user settings (with story for content rating)
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

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
                        db=db,
                        branch_id=scene.branch_id
                    )

                    # Check if scene is at extraction threshold - if so, regenerate entity states in background
                    # IMPORTANT: Run in background to avoid blocking the streaming response (~90 sec for 5 scenes)
                    from .story_tasks.background_tasks import recalculate_entities_in_background
                    batch_threshold = user_settings.get("context_summary_threshold", 5) if user_settings else 5
                    if scene.sequence_number % batch_threshold == 0:
                        import asyncio
                        asyncio.create_task(recalculate_entities_in_background(
                            story_id=story_id,
                            user_id=current_user.id,
                            user_settings=user_settings,
                            up_to_sequence=scene.sequence_number,
                            branch_id=scene.branch_id
                        ))
                        logger.info(f"[VARIANT] Triggered background entity recalculation at threshold for scene {scene_id}")

            else:
                logger.warning(f"No active StoryFlow entry found for scene {scene_id} trace_id={trace_id}")
        
            # Check if this is the last scene and trigger auto-play TTS if enabled
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

            # Choices are now generated inline with the variant (cache-friendly single LLM call)
            # Only generate separately if separate_choice_generation is enabled and no choices exist
            generation_prefs = user_settings.get("generation_preferences", {})
            separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

            # Check if variant already has choices from inline generation
            existing_choices = db.query(SceneChoice)\
                .filter(SceneChoice.scene_variant_id == variant.id)\
                .count()

            if existing_choices == 0 and separate_choice_generation:
                # Separate choice generation mode - generate choices in dedicated call
                try:
                    context_manager = get_context_manager_for_user(user_settings, current_user.id)
                    active_branch_id = story.current_branch_id
                    active_chapter = db.query(Chapter).filter(
                        Chapter.story_id == story_id,
                        Chapter.branch_id == active_branch_id,
                        Chapter.status == ChapterStatus.ACTIVE
                    ).first()
                    chapter_id = active_chapter.id if active_chapter else None

                    choice_context = await context_manager.build_scene_generation_context(
                        story_id, db, chapter_id=chapter_id, exclude_scene_id=scene_id,
                        use_entity_states_snapshot=True  # Use saved entity states for cache consistency
                    )

                    generated_choices = await llm_service.generate_choices(
                        variant.content,
                        choice_context,
                        current_user.id,
                        user_settings,
                        db
                    )

                    scene = db.query(Scene).filter(Scene.id == scene_id).first()
                    branch_id = scene.branch_id if scene else None

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
                    logger.info(f"[VARIANT] Generated {len(generated_choices)} choices in separate call")
                except Exception as e:
                    logger.warning(f"[VARIANT] Failed to generate choices separately: {e}")
            elif existing_choices > 0:
                logger.info(f"[VARIANT] Using {existing_choices} choices from inline generation")

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
                detail="Failed to create scene variant"
            )

@router.post("/{story_id}/scenes/{scene_id}/variants/stream")
async def create_scene_variant_streaming(
    story_id: int,
    scene_id: int,
    request: VariantGenerateRequest,
    background_tasks: BackgroundTasks,
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
    
    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
    
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

            # Load saved prompt snapshot from original variant for cache consistency.
            # Load saved prompt snapshot: {"v": 2, "messages": [...]} (full prompt)
            snapshot_messages = None
            if original_variant.context_snapshot:
                try:
                    raw = json.loads(original_variant.context_snapshot)
                    if isinstance(raw, dict) and raw.get("v") == 2:
                        snapshot_messages = raw["messages"]
                        logger.info(f"[VARIANT] Loaded prompt snapshot ({len(snapshot_messages)} messages)")
                except (json.JSONDecodeError, TypeError):
                    pass

            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'scene_id': scene_id})}\n\n"

            # Thinking/reasoning handler
            thinking_handler = ThinkingStreamHandler()

            # Build context for variant generation - use same context manager as new scene generation
            context_manager = get_context_manager_for_user(user_settings, current_user.id)
            
            # Get custom_prompt from proper request model
            custom_prompt = request.custom_prompt or ""
            logger.warning(f"[VARIANT] Custom prompt from request: '{custom_prompt}'")
            
            # Check if this should be a concluding scene
            # Either explicitly requested OR regenerating an existing concluding scene
            is_concluding = request.is_concluding or (original_variant.generation_method == "concluding_scene")
            logger.warning(f"[VARIANT] is_concluding: {is_concluding} (request: {request.is_concluding}, variant method: {original_variant.generation_method})")
            
            # Check for multi-generation (n > 1)
            n_value = get_n_value_from_settings(user_settings)
            
            if n_value > 1:
                # =====================================================================
                # MULTI-GENERATION PATH FOR VARIANT REGENERATION (n > 1)
                # =====================================================================
                logger.info(f"[MULTI-GEN VARIANT] Starting multi-regeneration with n={n_value} for scene {scene_id}")
                
                generation_prefs = user_settings.get("generation_preferences", {})
                separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
                
                # Build context
                context = await context_manager.build_scene_generation_context(
                    story_id, db, custom_prompt or "", is_variant_generation=True,
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id,
                    use_entity_states_snapshot=True  # Use saved entity states for cache consistency
                )
                if snapshot_messages:
                    context["_saved_prompt_prefix"] = snapshot_messages[:-1]

                # Get current max variant number
                from sqlalchemy import desc
                max_variant = db.query(SceneVariant.variant_number)\
                    .filter(SceneVariant.scene_id == scene_id)\
                    .order_by(desc(SceneVariant.variant_number))\
                    .first()
                starting_variant_number = (max_variant[0] if max_variant else 0) + 1
                
                variants_data = None
                
                if is_concluding:
                    # Multi-generation concluding variant (no choices)
                    chapter_info = {
                        "chapter_number": active_chapter.chapter_number if active_chapter else 1,
                        "chapter_title": active_chapter.title if active_chapter else "Untitled",
                        "chapter_location": active_chapter.location_name if active_chapter else "Unknown",
                        "chapter_time_period": active_chapter.time_period if active_chapter else "Unknown",
                        "chapter_scenario": active_chapter.scenario if active_chapter else "None"
                    }
                    
                    async for chunk, is_complete, contents in llm_service.generate_concluding_scene_streaming_multi(
                        context,
                        chapter_info,
                        current_user.id,
                        user_settings,
                        db,
                        n_value
                    ):
                        if not is_complete:
                            events, _ = thinking_handler.process_chunk(chunk)
                            for event in events:
                                yield f"data: {event}\n\n"
                        else:
                            variants_data = [{"content": c, "choices": []} for c in contents]

                elif separate_choice_generation:
                    # Separate mode: generate variants, then choices in parallel
                    async for chunk, is_complete, contents in llm_service.generate_scene_streaming_multi(
                        context,
                        current_user.id,
                        user_settings,
                        db,
                        n_value
                    ):
                        if not is_complete:
                            events, _ = thinking_handler.process_chunk(chunk)
                            for event in events:
                                yield f"data: {event}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating choices for all variants...'})}\n\n"
                            all_choices = await llm_service.generate_choices_for_variants(
                                contents,
                                context,
                                current_user.id,
                                user_settings,
                                db
                            )
                            variants_data = [
                                {"content": c, "choices": ch}
                                for c, ch in zip(contents, all_choices)
                            ]
                
                else:
                    # Combined mode: variant + choices together
                    async for chunk, is_complete, vdata in llm_service.regenerate_scene_variant_streaming_multi(
                        db,
                        scene_id,
                        context,
                        current_user.id,
                        user_settings,
                        n_value,
                        custom_prompt=custom_prompt
                    ):
                        if not is_complete:
                            events, _ = thinking_handler.process_chunk(chunk)
                            for event in events:
                                yield f"data: {event}\n\n"
                        else:
                            variants_data = vdata

                # Create additional variants
                if variants_data:
                    new_variants = create_additional_variants(
                        db=db,
                        scene_id=scene_id,
                        variants_data=variants_data,
                        starting_variant_number=starting_variant_number,
                        branch_id=branch_id,
                        custom_prompt=custom_prompt
                    )
                    
                    # Format response
                    variants_response = []
                    for v in new_variants:
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
                    
                    # Invalidate extractions and chapter batches
                    from ..api.chapters import invalidate_chapter_batches_for_scene
                    invalidate_chapter_batches_for_scene(scene_id, db)
                    await invalidate_extractions_for_scene(
                        scene_id=scene_id,
                        story_id=story_id,
                        scene_sequence=scene.sequence_number,
                        user_id=current_user.id,
                        user_settings=user_settings,
                        db=db,
                        branch_id=scene.branch_id
                    )

                    # Send multi_variant_complete event
                    yield f"data: {json.dumps({'type': 'multi_variant_complete', 'scene_id': scene_id, 'new_variants_count': len(new_variants), 'variants': variants_response, 'active_variant_id': new_variants[0].id if new_variants else None})}\n\n"
                    
                    logger.info(f"[MULTI-GEN VARIANT] Added {len(new_variants)} new variants to scene {scene_id}")
                    
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return  # Exit early - don't continue to single-generation path
                else:
                    logger.error("[MULTI-GEN VARIANT] No variants data generated")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to generate variants'})}\n\n"
                    return
            
            # =====================================================================
            # SINGLE-GENERATION PATH FOR VARIANT REGENERATION (n == 1)
            # =====================================================================

            # Stream variant generation with combined choices
            variant_content = ""
            parsed_choices = None
            
            if is_concluding:
                # CONCLUDING SCENE: Generate chapter-ending scene without choices
                logger.warning(f"[VARIANT] Mode: CONCLUDING SCENE")
                context = await context_manager.build_scene_generation_context(
                    story_id, db, "", is_variant_generation=False,
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id,
                    use_entity_states_snapshot=True  # Use saved entity states for cache consistency
                )
                if snapshot_messages:
                    context["_saved_prompt_prefix"] = snapshot_messages[:-1]

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
                    events, content = thinking_handler.process_chunk(chunk)
                    for event in events:
                        yield f"data: {event}\n\n"
                    if content:
                        variant_content += content

                # Concluding scenes don't have choices
                parsed_choices = None
            elif custom_prompt:
                # GUIDED ENHANCEMENT: Has custom prompt from user
                logger.warning(f"[VARIANT] Mode: GUIDED ENHANCEMENT")
                context = await context_manager.build_scene_generation_context(
                    story_id, db, custom_prompt, is_variant_generation=True,
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id,
                    use_entity_states_snapshot=True  # Use saved entity states for cache consistency
                )
                if snapshot_messages:
                    context["_saved_prompt_prefix"] = snapshot_messages[:-1]

                # Use guided enhancement function
                async for chunk, scene_complete, choices in llm_service.generate_variant_with_choices_streaming(
                    original_scene_content,
                    context,
                    current_user.id,
                    user_settings,
                    db
                ):
                    if not scene_complete:
                        events, content = thinking_handler.process_chunk(chunk)
                        for event in events:
                            yield f"data: {event}\n\n"
                        if content:
                            variant_content += content
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
                # use_entity_states_snapshot ensures we use the exact entity states from original generation
                context = await context_manager.build_scene_generation_context(
                    story_id, db, original_continue_option, is_variant_generation=False,
                    exclude_scene_id=scene_id, chapter_id=chapter_id, branch_id=branch_id,
                    use_entity_states_snapshot=True  # Use saved entity states for cache consistency
                )
                if snapshot_messages:
                    context["_saved_full_prompt"] = snapshot_messages  # 100% identical prompt

                # Use the SAME function as new scene generation
                async for chunk, scene_complete, choices in llm_service.generate_scene_with_choices_streaming(
                    context,
                    current_user.id,
                    user_settings,
                    db
                ):
                    if not scene_complete:
                        events, content = thinking_handler.process_chunk(chunk)
                        for event in events:
                            yield f"data: {event}\n\n"
                        if content:
                            variant_content += content
                    else:
                        parsed_choices = choices
                        break

            # Create the new variant manually since we already have the content
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
            
            # Clean the final assembled variant content comprehensively (chunk cleaning may miss patterns)
            cleaned_variant_content = llm_service._clean_scene_content(variant_content.rstrip())

            # Get snapshots from context (populated during prompt building)
            # _prompt_prefix_snapshot: v2 JSON string {"v": 2, "messages": [...]} for cache consistency
            entity_states_snapshot = context.get('_entity_states_snapshot') if isinstance(context, dict) else None
            context_snapshot = context.get('_prompt_prefix_snapshot') if isinstance(context, dict) else None

            # If no snapshot in current context, copy from original variant
            # This ensures cache consistency when regenerating from the new variant
            if not context_snapshot and variant_to_regenerate_from:
                context_snapshot = variant_to_regenerate_from.context_snapshot
                entity_states_snapshot = entity_states_snapshot or variant_to_regenerate_from.entity_states_snapshot
                logger.info(f"[VARIANT] Copying snapshots from variant {variant_to_regenerate_from.id}: "
                           f"context_snapshot={'yes' if context_snapshot else 'no'}, "
                           f"entity_states_snapshot={'yes' if entity_states_snapshot else 'no'}")

            # Create the new variant
            variant = SceneVariant(
                scene_id=scene_id,
                variant_number=next_variant_number,
                is_original=False,
                content=cleaned_variant_content,
                title=scene.title,
                original_content=original_variant.content if original_variant else cleaned_variant_content,
                generation_prompt=prompt_to_save,
                generation_method=generation_method,
                entity_states_snapshot=entity_states_snapshot,
                context_snapshot=context_snapshot
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
            
            # Track scene info for background tasks (scheduled after completion is sent)
            scene_for_extraction = None

            if flow_entry:
                old_variant_id = flow_entry.scene_variant_id
                flow_entry.scene_variant_id = variant.id
                db.commit()
                logger.info(f"Updated StoryFlow: scene {scene_id} now points to variant {variant.id} (was {old_variant_id})")

                # Invalidate chapter summary batches if this scene was summarized
                from ..api.chapters import invalidate_chapter_batches_for_scene
                invalidate_chapter_batches_for_scene(scene_id, db)

                # Invalidate extractions for the modified scene (fast cleanup, regeneration happens later)
                scene_for_extraction = db.query(Scene).filter(Scene.id == scene_id).first()
                if scene_for_extraction:
                    await invalidate_extractions_for_scene(
                        scene_id=scene_id,
                        story_id=story_id,
                        scene_sequence=scene_for_extraction.sequence_number,
                        user_id=current_user.id,
                        user_settings=user_settings,
                        db=db,
                        branch_id=scene_for_extraction.branch_id
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

            # Schedule background extraction tasks AFTER completion is sent to frontend
            # This ensures choices are displayed before potentially slow extractions run
            if scene_for_extraction:
                from .story_tasks.background_tasks import recalculate_entities_in_background
                batch_threshold = user_settings.get("context_summary_threshold", 5) if user_settings else 5
                if scene_for_extraction.sequence_number % batch_threshold == 0:
                    import asyncio
                    asyncio.create_task(recalculate_entities_in_background(
                        story_id=story_id,
                        user_id=current_user.id,
                        user_settings=user_settings,
                        up_to_sequence=scene_for_extraction.sequence_number,
                        branch_id=scene_for_extraction.branch_id
                    ))
                    logger.info(f"[VARIANT] Triggered background entity recalculation at threshold for scene {scene_id}")

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in variant stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    # Check if streaming is disabled in user settings
    generation_prefs = user_settings.get("generation_preferences", {})
    enable_streaming = generation_prefs.get("enable_streaming", True)

    if not enable_streaming:
        logger.info(f"[VARIANT:NON-STREAMING:START] scene_id={scene_id}")
        complete_data = None
        full_content = ""
        chunk_count = 0

        try:
            async for chunk in generate_variant_stream():
                chunk_count += 1
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "content":
                            full_content += event.get("chunk", "")
                        elif event.get("type") == "complete":
                            complete_data = event
                            logger.info(f"[VARIANT:NON-STREAMING:COMPLETE] scene_id={scene_id}")
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"[VARIANT:NON-STREAMING:ERROR] scene_id={scene_id} error={e}")
            raise

        if complete_data:
            from fastapi.responses import JSONResponse
            # Extract variant data - streaming format has it nested under 'variant' key
            variant_data = complete_data.get("variant", {})
            # Use cleaned content from saved variant, not raw full_content which includes ###CHOICES### marker
            cleaned_content = variant_data.get("content", full_content)
            logger.info(f"[VARIANT:NON-STREAMING:RETURN] scene_id={scene_id} content_len={len(cleaned_content)}")
            return JSONResponse(content={
                "variant_id": variant_data.get("id"),
                "variant_number": variant_data.get("variant_number"),
                "content": cleaned_content,
                "choices": variant_data.get("choices", [])
            })
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Variant generation failed - no completion data received"
            )

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
    
    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
    
    try:
        # Get the current active variant content
        service = SceneVariantService(db)
        current_variant = service.get_active_variant(scene_id)

        if not current_variant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active scene variant found"
            )

        # Load saved prompt snapshot: {"v": 2, "messages": [...]}
        snapshot_messages = None
        if current_variant.context_snapshot:
            try:
                raw = json.loads(current_variant.context_snapshot)
                if isinstance(raw, dict) and raw.get("v") == 2:
                    snapshot_messages = raw["messages"]
                    logger.info(f"[CONTINUE] Loaded prompt snapshot ({len(snapshot_messages)} messages)")
            except (json.JSONDecodeError, TypeError):
                pass

        # Build context for continuation - ContextManager produces structured format
        # needed for multi-message LLM caching (uses hybrid strategy if enabled)
        context_manager = get_context_manager_for_user(user_settings, current_user.id)

        # Get custom_prompt from the request model
        custom_prompt = request.custom_prompt

        context = await context_manager.build_scene_continuation_context(
            story_id, scene_id, current_variant.content, db, custom_prompt,
            branch_id=story.current_branch_id  # Pass branch_id for branch-aware context
        )
        if snapshot_messages:
            context["_saved_prompt_prefix"] = snapshot_messages[:-1]

        # Generate continuation content with inline choices using unified cache-friendly method
        continuation_content, parsed_choices = await llm_service.generate_continuation_with_choices(
            context, current_user.id, user_settings, db
        )

        # Clean the continuation content before appending
        cleaned_continuation = llm_service._clean_scene_content(continuation_content.rstrip())
        
        # Append to existing content
        new_content = current_variant.content + "\n\n" + cleaned_continuation
        
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
            db=db,
            branch_id=scene.branch_id
        )

        # Handle choices from inline generation
        choices_data = []
        if parsed_choices and len(parsed_choices) >= 2:
            try:
                # Delete existing choices for this variant (continuation replaces choices)
                db.query(SceneChoice).filter(
                    SceneChoice.scene_variant_id == current_variant.id
                ).delete()

                # Create new choices
                for idx, choice_text in enumerate(parsed_choices, 1):
                    choice = SceneChoice(
                        scene_id=scene_id,
                        scene_variant_id=current_variant.id,
                        branch_id=scene.branch_id,
                        choice_text=choice_text,
                        choice_order=idx
                    )
                    db.add(choice)
                    choices_data.append({
                        "text": choice_text,
                        "order": idx
                    })
                db.commit()
                logger.info(f"[CONTINUE] Generated {len(choices_data)} choices from inline generation")
            except Exception as e:
                logger.warning(f"[CONTINUE] Failed to save inline choices: {e}")
                db.rollback()
                choices_data = []

        return {
            "message": "Scene continued successfully",
            "scene": {
                "id": scene.id,
                "content": new_content,
                "title": scene.title,
                "sequence_number": scene.sequence_number
            },
            "choices": choices_data
        }
        
    except Exception as e:
        logger.error(f"Failed to continue scene {scene_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to continue scene"
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
    
    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
    
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

            # Thinking/reasoning handler
            thinking_handler = ThinkingStreamHandler()

            # Load saved prompt snapshot: {"v": 2, "messages": [...]}
            snapshot_messages = None
            if current_variant.context_snapshot:
                try:
                    raw = json.loads(current_variant.context_snapshot)
                    if isinstance(raw, dict) and raw.get("v") == 2:
                        snapshot_messages = raw["messages"]
                        logger.info(f"[CONTINUE] Loaded prompt snapshot ({len(snapshot_messages)} messages)")
                except (json.JSONDecodeError, TypeError):
                    pass

            # Build context for continuation - ContextManager produces structured format
            # needed for multi-message LLM caching (uses hybrid strategy if enabled)
            context_manager = get_context_manager_for_user(user_settings, current_user.id)

            # Get custom_prompt from the request model
            custom_prompt = request.custom_prompt

            context = await context_manager.build_scene_continuation_context(
                story_id, scene_id, current_variant.content, db, custom_prompt,
                branch_id=story.current_branch_id  # Pass branch_id for branch-aware context
            )
            if snapshot_messages:
                context["_saved_prompt_prefix"] = snapshot_messages[:-1]

            # Stream continuation generation with combined choices
            continuation_content = ""
            parsed_choices = None
            async for chunk, scene_complete, choices in llm_service.generate_continuation_with_choices_streaming(
                context, current_user.id, user_settings, db
            ):
                if not scene_complete:
                    events, content = thinking_handler.process_chunk(chunk)
                    for event in events:
                        yield f"data: {event}\n\n"
                    if content:
                        continuation_content += content
                else:
                    # Continuation complete, choices parsed
                    parsed_choices = choices
                    break
            
            # Update the variant with the new content
            # Clean the continuation content before appending (chunk cleaning may miss patterns)
            cleaned_continuation = llm_service._clean_scene_content(continuation_content.rstrip())
            new_content = current_variant.content + "\n\n" + cleaned_continuation
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
                db=db,
                branch_id=scene.branch_id
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

    # Check if streaming is disabled in user settings
    generation_prefs = user_settings.get("generation_preferences", {})
    enable_streaming = generation_prefs.get("enable_streaming", True)

    if not enable_streaming:
        logger.info(f"[CONTINUE:NON-STREAMING:START] scene_id={scene_id}")
        complete_data = None
        chunk_count = 0

        try:
            async for chunk in generate_continuation_stream():
                chunk_count += 1
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "complete":
                            complete_data = event
                            logger.info(f"[CONTINUE:NON-STREAMING:COMPLETE] scene_id={scene_id}")
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"[CONTINUE:NON-STREAMING:ERROR] scene_id={scene_id} error={e}")
            raise

        if complete_data:
            from fastapi.responses import JSONResponse
            logger.info(f"[CONTINUE:NON-STREAMING:RETURN] scene_id={scene_id}")
            return JSONResponse(content={
                "scene_id": complete_data.get("scene_id"),
                "new_content": complete_data.get("new_content"),
                "choices": complete_data.get("choices", [])
            })
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Continuation generation failed - no completion data received"
            )

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

    # Get edit lock for this variant to prevent concurrent edits
    edit_lock = await get_variant_edit_lock(variant_id)
    if edit_lock.locked():
        logger.warning(f"[SCENE:EDIT:CONFLICT] variant_id={variant_id} edit already in progress")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An edit operation is already in progress for this variant. Please wait."
        )

    async with edit_lock:
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

        # Get user settings (with story for content rating)
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

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
            # NOTE: Cleanup is now done in background to avoid blocking the UI response
            from ..services.entity_state_service import EntityStateService

            # Schedule semantic cleanup in background (was blocking before)
            # Reuse existing background function with single-element list
            import asyncio
            asyncio.create_task(cleanup_semantic_data_in_background([scene_id], story_id))
            logger.info(f"[MODIFY] Scheduled cleanup of extractions for scene {scene_id} (non-blocking)")

            # Rollback entity states to prior valid batch and trigger re-extraction
            # This ensures any changes to character attributes/possessions/locations get re-extracted
            entity_service = EntityStateService(user_id=current_user.id, user_settings=user_settings)
            rollback_result = entity_service.rollback_entity_states_for_edit(
                db, story_id, scene.sequence_number, branch_id=scene.branch_id
            )
            logger.info(f"[MODIFY] Entity state rollback for scene {scene_id}: {rollback_result}")

            # Always trigger entity state re-extraction after an edit
            # (edits can change character attributes, possessions, locations, etc.)
            import asyncio
            asyncio.create_task(recalculate_entities_in_background(
                story_id=story_id,
                user_id=current_user.id,
                user_settings=user_settings,
                up_to_sequence=scene.sequence_number,
                branch_id=scene.branch_id,
                force_extraction=True  # Force extraction regardless of batch threshold
            ))
            logger.info(f"[MODIFY] Scheduled entity state regeneration for scene {scene_id}")

            # Invalidate plot progress batches affected by this scene modification
            # Re-extraction will happen naturally at the next scene generation threshold
            chapter = db.query(Chapter).filter(Chapter.id == scene.chapter_id).first()
            if chapter and chapter.chapter_plot:
                from ..services.chapter_progress_service import ChapterProgressService
                progress_service = ChapterProgressService(db)
                progress_service.invalidate_plot_progress_batches_for_scene(scene.id)
                logger.info(f"[MODIFY] Invalidated plot progress batches for scene {scene_id}")

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
                detail="Failed to update scene variant"
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
    
    # Get user settings (with story for content rating)
    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
    
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
        
        # Load saved prompt snapshot: {"v": 2, "messages": [...]}
        snapshot_messages = None
        if variant.context_snapshot:
            try:
                raw = json.loads(variant.context_snapshot)
                if isinstance(raw, dict) and raw.get("v") == 2:
                    snapshot_messages = raw["messages"]
                    logger.info(f"[REGENERATE_CHOICES] Loaded prompt snapshot ({len(snapshot_messages)} messages)")
            except (json.JSONDecodeError, TypeError):
                pass

        # Build context excluding the current scene (same as generate_more_choices)
        choice_context = await context_manager.build_scene_generation_context(
            story_id, db, chapter_id=chapter_id, exclude_scene_id=scene_id,
            use_entity_states_snapshot=True  # Use saved entity states for cache consistency
        )
        if snapshot_messages:
            choice_context["_saved_prompt_prefix"] = snapshot_messages[:-1]

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
            detail="Failed to regenerate choices"
        )


