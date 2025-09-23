from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Scene, Character, StoryCharacter, User, UserSettings, SceneChoice, SceneVariant, StoryFlow, StoryStatus
from ..services.scene_variant_service import SceneVariantService
from sqlalchemy.sql import func
from ..services.llm_service import llm_service
from ..services.context_manager import ContextManager
from ..dependencies import get_current_user
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

class StoryCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    world_setting: Optional[str] = ""
    initial_premise: Optional[str] = ""

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's stories"""
    stories = db.query(Story).filter(
        Story.owner_id == current_user.id
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": story.id,
            "title": story.title,
            "description": story.description,
            "genre": story.genre,
            "status": story.status,
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
    """Create a new story"""
    
    story = Story(
        title=story_data.title,
        description=story_data.description,
        owner_id=current_user.id,
        genre=story_data.genre,
        tone=story_data.tone,
        world_setting=story_data.world_setting,
        initial_premise=story_data.initial_premise
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
    
    # Get the active story flow instead of direct scenes
    service = SceneVariantService(db)
    flow = service.get_active_story_flow(story_id)
    
    # Transform flow data to match expected format for backward compatibility
    scenes = []
    for flow_item in flow:
        variant = flow_item['variant']
        scenes.append({
            "id": flow_item['scene_id'],
            "sequence_number": flow_item['sequence_number'],
            "title": variant['title'],
            "content": variant['content'],
            "location": "",  # TODO: Add location to variant
            "characters_present": [],  # TODO: Add characters to variant
            # Additional variant info
            "variant_id": variant['id'],
            "variant_number": variant['variant_number'],
            "is_original": variant['is_original'],
            "has_multiple_variants": flow_item['all_variants_count'] > 1,
            "choices": flow_item['choices']
        })
    
    return {
        "id": story.id,
        "title": story.title,
        "description": story.description,
        "genre": story.genre,
        "tone": story.tone,
        "world_setting": story.world_setting,
        "status": story.status,
        "scenes": scenes,
        "flow_info": {
            "total_scenes": len(scenes),
            "has_variants": any(scene['has_multiple_variants'] for scene in scenes)
        }
    }

@router.post("/{story_id}/scenes")
async def generate_scene(
    story_id: int,
    custom_prompt: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a new scene for the story with smart context management"""
    
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
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_settings = user_settings_db.to_dict() if user_settings_db else None
    
    # Create context manager with user settings
    context_manager = ContextManager(user_settings=user_settings)
    
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
    
    # Generate scene content using enhanced method
    try:
        scene_content = await llm_service.generate_scene_with_context_management(context, user_settings)
    except Exception as e:
        logger.error(f"Failed to generate scene for story {story_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate scene: {str(e)}"
        )
    
    # Create scene with variant system
    current_scene_count = db.query(Scene).filter(Scene.story_id == story_id).count()
    next_sequence = current_scene_count + 1
    
    # Generate choices first
    choices_data = []
    try:
        choice_context = await context_manager.build_choice_generation_context(story_id, db)
        choices_result = await llm_service.generate_choices(choice_context, user_settings)
        choices_data = choices_result.get('choices', [])
    except Exception as e:
        logger.warning(f"Failed to generate choices: {e}")
        choices_data = []  # Continue without choices
    
    # Use the new variant service to create scene with variant
    try:
        service = SceneVariantService(db)
        scene, variant = service.create_scene_with_variant(
            story_id=story_id,
            sequence_number=next_sequence,
            content=scene_content,
            title=f"Scene {next_sequence}",
            custom_prompt=custom_prompt if custom_prompt else None,
            choices=choices_data
        )
        
        # Format choices for response
        formatted_choices = [
            {
                "text": choice.get('text', ''),
                "order": i + 1,
                "description": choice.get('description')
            }
            for i, choice in enumerate(choices_data)
        ]
        
    except Exception as e:
        logger.error(f"Failed to create scene with variant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scene: {str(e)}"
        )
    
    return {
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

@router.post("/{story_id}/scenes/stream")
async def generate_scene_streaming(
    story_id: int,
    custom_prompt: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a new scene for the story with streaming response"""
    
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
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_settings = user_settings_db.to_dict() if user_settings_db else None
    
    # Create context manager with user settings
    context_manager = ContextManager(user_settings=user_settings)
    
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
    
    # Calculate next sequence number
    current_scene_count = db.query(Scene).filter(Scene.story_id == story_id).count()
    next_sequence = current_scene_count + 1
    
    async def generate_stream():
        try:
            full_content = ""
            
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'sequence': next_sequence})}\n\n"
            
            # Stream scene generation
            async for chunk in llm_service.generate_scene_with_context_management_streaming(context, user_settings):
                full_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
            
            # Save the scene to database
            scene = Scene(
                story_id=story_id,
                sequence_number=next_sequence,
                content=full_content.strip(),
                original_content=full_content.strip()
            )
            
            db.add(scene)
            db.commit()
            db.refresh(scene)
            
            # Generate choices for the new scene
            try:
                choice_context = {
                    "genre": context.get("genre"),
                    "tone": context.get("tone"),
                    "characters": context.get("characters", []),
                    "current_situation": f"Scene {next_sequence}: {full_content}"
                }
                
                choices = await llm_service.generate_choices(full_content, choice_context, user_settings)
                
                # Save choices to database
                choices_data = []
                for i, choice_text in enumerate(choices):
                    choice = SceneChoice(
                        scene_id=scene.id,
                        choice_text=choice_text,
                        choice_order=i + 1
                    )
                    db.add(choice)
                    choices_data.append({
                        "text": choice_text,
                        "order": i + 1
                    })
                
                db.commit()
                
            except Exception as e:
                logger.warning(f"Failed to generate choices for scene {scene.id}: {e}")
                choices_data = []
            
            # Send completion data
            yield f"data: {json.dumps({'type': 'complete', 'scene_id': scene.id, 'choices': choices_data})}\n\n"
            yield "data: [DONE]\n\n"
            
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
        user_settings_db = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        user_settings = user_settings_db.to_dict() if user_settings_db else None
        
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
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_settings = user_settings_db.to_dict() if user_settings_db else None
    
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
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_settings = user_settings_db.to_dict() if user_settings_db else None
    
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
async def generate_scenario(
    request: ScenarioGenerateRequest,
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
        
        # Generate scenario using LLM
        scenario = await llm_service.generate_scenario(context)
        
        return {
            "scenario": scenario,
            "message": "Scenario generated successfully"
        }
        
    except Exception as e:
        # Fallback to simple combination if LLM fails
        elements = [v for v in request.elements.values() if v]
        fallback_scenario = ". ".join(elements) + "." if elements else "A new adventure begins."
        
        return {
            "scenario": fallback_scenario,
            "message": "Scenario generated (fallback mode)"
        }

@router.post("/generate-title")
async def generate_title(
    request: TitleGenerateRequest,
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
        
        # Generate multiple title options using LLM
        titles = await llm_service.generate_titles(context)
        
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
async def generate_plot(
    request: PlotGenerateRequest,
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
        
        # Generate plot using LLM
        if request.plot_type == "complete":
            plot_points = await llm_service.generate_complete_plot(context)
            return {
                "plot_points": plot_points,
                "message": "Complete plot generated successfully"
            }
        else:
            plot_point = await llm_service.generate_single_plot_point(context)
            return {
                "plot_point": plot_point,
                "message": "Plot point generated successfully"
            }
        
    except Exception as e:
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
    
    service = SceneVariantService(db)
    flow = service.get_active_story_flow(story_id)
    
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
    
    service = SceneVariantService(db)
    variants = service.get_scene_variants(scene_id)
    
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

@router.post("/{story_id}/scenes/{scene_id}/variants")
async def create_scene_variant(
    story_id: int,
    scene_id: int,
    request: dict = {},
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
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_settings = user_settings_db.to_dict() if user_settings_db else None
    
    try:
        service = SceneVariantService(db)
        variant = await service.regenerate_scene_variant(
            scene_id=scene_id,
            custom_prompt=request.get('custom_prompt'),
            user_settings=user_settings
        )
        
        # Get choices for the new variant
        choices = db.query(SceneChoice)\
            .filter(SceneChoice.scene_variant_id == variant.id)\
            .order_by(SceneChoice.choice_order)\
            .all()
        
        return {
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
        
    except Exception as e:
        logger.error(f"Failed to create scene variant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scene variant: {str(e)}"
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
    success = service.delete_scenes_from_sequence(story_id, sequence_number)
    
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
    
    # Check if there's already a draft for this user
    existing_draft = db.query(Story).filter(
        Story.owner_id == current_user.id,
        Story.status == StoryStatus.DRAFT
    ).first()
    
    if existing_draft:
        # Update existing draft
        story = existing_draft
        story.creation_step = step
        story.draft_data = story_data
        
        # Update story fields as they become available
        if 'title' in story_data and story_data['title']:
            story.title = story_data['title']
        if 'description' in story_data and story_data['description']:
            story.description = story_data['description']
        if 'genre' in story_data and story_data['genre']:
            story.genre = story_data['genre']
        if 'tone' in story_data and story_data['tone']:
            story.tone = story_data['tone']
        if 'world_setting' in story_data and story_data['world_setting']:
            story.world_setting = story_data['world_setting']
        if 'initial_premise' in story_data and story_data['initial_premise']:
            story.initial_premise = story_data['initial_premise']
            
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

@router.post("/draft/{story_id}/finalize")
async def finalize_draft_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Convert a draft story to active status"""
    
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