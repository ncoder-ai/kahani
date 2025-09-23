from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Scene, SceneChoice, User, UserSettings
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
    """Get a specific story"""
    
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get scenes
    scenes = db.query(Scene).filter(
        Scene.story_id == story_id
    ).order_by(Scene.sequence_number).all()
    
    return {
        "id": story.id,
        "title": story.title,
        "description": story.description,
        "genre": story.genre,
        "tone": story.tone,
        "world_setting": story.world_setting,
        "status": story.status,
        "scenes": [
            {
                "id": scene.id,
                "sequence_number": scene.sequence_number,
                "title": scene.title,
                "content": scene.content,
                "location": scene.location,
                "characters_present": scene.characters_present
            }
            for scene in scenes
        ]
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
    
    # Create scene
    current_scene_count = db.query(Scene).filter(Scene.story_id == story_id).count()
    next_sequence = current_scene_count + 1
    
    scene = Scene(
        story_id=story_id,
        sequence_number=next_sequence,
        content=scene_content,
        original_content=scene_content
    )
    
    db.add(scene)
    db.commit()
    db.refresh(scene)
    
    # Generate choices with context
    choices_data = []
    try:
        # Build lighter context for choice generation
        choice_context = {
            "genre": context.get("genre"),
            "tone": context.get("tone"),
            "characters": context.get("characters", []),
            "current_situation": f"Scene {next_sequence}: {scene_content}"
        }
        
        choices = await llm_service.generate_choices(scene_content, choice_context, user_settings)
        
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
        # Scene was created successfully, but choices failed
        logger.warning(f"Failed to generate choices for scene {scene.id}: {e}")
    
    return {
        "id": scene.id,
        "content": scene_content,
        "sequence_number": next_sequence,
        "choices": choices_data,
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
    """Remove the last scene and generate a new one"""
    
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
    
    # Delete the latest scene
    db.delete(latest_scene)
    db.commit()
    
    # Get user settings
    user_settings_db = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    user_settings = user_settings_db.to_dict() if user_settings_db else None
    
    # Create context manager with user settings
    context_manager = ContextManager(user_settings=user_settings)
    
    try:
        # Build context for scene generation
        scene_context = await context_manager.build_scene_generation_context(story_id, db)
        
        # Generate new scene using LLM with context management
        new_content = await llm_service.generate_scene_with_context_management(scene_context, user_settings)
        
        # Create new scene
        new_scene = Scene(
            story_id=story_id,
            sequence_number=latest_scene.sequence_number,  # Use same sequence number
            title=f"Scene {latest_scene.sequence_number}",
            content=new_content
        )
        
        db.add(new_scene)
        db.commit()
        db.refresh(new_scene)
        
        return {
            "message": "Scene regenerated successfully",
            "scene": {
                "id": new_scene.id,
                "sequence_number": new_scene.sequence_number,
                "title": new_scene.title,
                "content": new_scene.content,
                "location": new_scene.location,
                "characters_present": new_scene.characters_present or []
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