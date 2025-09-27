from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Story
from ..dependencies import get_current_user
from ..services.context_manager import ContextManager
from ..services.llm_functions import generate_content
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/stories/{story_id}/summary")
async def get_story_summary(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the current summary of a story"""
    try:
        # Get the story
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        
        # Get story scenes
        scenes = story.scenes
        if not scenes:
            return {
                "summary": "No scenes available to summarize.",
                "total_scenes": 0,
                "total_tokens": 0,
                "context_used": False
            }
        
        # Get user settings for context management
        user_settings = None
        if hasattr(current_user, 'settings') and current_user.settings:
            user_settings = current_user.settings
        
        # Initialize context manager
        context_manager = ContextManager()
        
        # Prepare context (this will trigger summarization if needed)
        context_data = await context_manager.prepare_context_for_generation(
            story=story,
            user_settings=user_settings
        )
        
        # Calculate token counts
        total_tokens = sum(context_manager.count_tokens(scene.content) for scene in scenes)
        
        return {
            "summary": context_data.get("summary", "No summary generated yet."),
            "total_scenes": len(scenes),
            "total_tokens": total_tokens,
            "context_used": context_data.get("context_length", 0),
            "has_summary": bool(context_data.get("summary")),
            "recent_scenes_count": len(context_data.get("recent_scenes", [])),
            "summarized_scenes_count": len(scenes) - len(context_data.get("recent_scenes", [])) if context_data.get("summary") else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting story summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get story summary")

@router.post("/stories/{story_id}/ai-summary")
async def generate_ai_summary(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a comprehensive AI summary of the entire story"""
    try:
        # Get the story
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        
        # Get story scenes
        scenes = story.scenes
        if not scenes:
            raise HTTPException(status_code=400, detail="Story has no scenes to summarize")
        
        # Get user settings
        user_settings = None
        if hasattr(current_user, 'settings') and current_user.settings:
            user_settings = current_user.settings
        
        # Combine all scene content
        combined_text = "\n\n".join([
            f"Scene {scene.sequence_number}: {scene.title}\n{scene.content}"
            for scene in scenes
        ])
        
        # Prepare story context for template
        story_context = {
            "title": story.title,
            "genre": story.genre or "Unknown",
            "scene_count": len(scenes)
        }
        
        # Generate AI summary using configurable prompts
        ai_summary = await llm_service.generate_summary(
            story_content=combined_text,
            story_context=story_context,
            user_settings=user_settings,
            db=db,
            user=current_user
        )
        
        return {
            "message": "AI summary generated successfully",
            "summary": ai_summary,
            "total_scenes": len(scenes),
            "summary_type": "ai_generated"
        }
            
    except Exception as e:
        logger.error(f"Error generating AI summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate AI summary")

@router.post("/stories/{story_id}/regenerate-summary")
async def regenerate_story_summary(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Force regeneration of story summary"""
    try:
        # Get the story
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        
        # Get user settings
        user_settings = None
        if hasattr(current_user, 'settings') and current_user.settings:
            user_settings = current_user.settings
        
        # Initialize services
        context_manager = ContextManager()
        # Use the global llm_service instance
        
        # Get scenes to summarize (exclude recent ones)
        scenes = story.scenes
        if len(scenes) <= (user_settings.context_keep_recent_scenes if user_settings else 3):
            return {
                "message": "Not enough scenes to generate summary",
                "summary": None
            }
        
        # Get scenes to summarize
        keep_recent = user_settings.context_keep_recent_scenes if user_settings else 3
        scenes_to_summarize = scenes[:-keep_recent]
        
        # Generate new summary using AI
        if scenes_to_summarize:
            combined_text = "\n\n".join([
                f"Scene {scene.sequence_number}: {scene.title}\n{scene.content}"
                for scene in scenes_to_summarize
            ])
            
            # Prepare story context for template
            story_context = {
                "title": story.title,
                "genre": story.genre or "Unknown",
                "scene_count": len(scenes_to_summarize)
            }
            
            new_summary = await llm_service.generate_summary(
                story_content=combined_text,
                story_context=story_context,
                user_settings=user_settings,
                db=db,
                user=current_user
            )
            
            return {
                "message": "Summary regenerated successfully",
                "summary": new_summary,
                "summarized_scenes": len(scenes_to_summarize),
                "recent_scenes": keep_recent
            }
        else:
            return {
                "message": "No scenes to summarize",
                "summary": None
            }
            
    except Exception as e:
        logger.error(f"Error regenerating story summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate summary")