from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..database import get_db
from ..models import User, Story, UserSettings, Scene, StoryBranch
from ..dependencies import get_current_user
from ..services.context_manager import ContextManager
from ..services.llm.service import UnifiedLLMService
from .stories import get_or_create_user_settings

llm_service = UnifiedLLMService()
from ..services.llm.prompts import prompt_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_branch_scenes(db: Session, story_id: int) -> list:
    """Get scenes for the active branch of a story."""
    # Get active branch
    active_branch = db.query(StoryBranch).filter(
        and_(
            StoryBranch.story_id == story_id,
            StoryBranch.is_active == True
        )
    ).first()
    
    if active_branch:
        return db.query(Scene).filter(
            and_(
                Scene.story_id == story_id,
                Scene.branch_id == active_branch.id,
                Scene.is_deleted == False
            )
        ).order_by(Scene.sequence_number).all()
    else:
        # Fallback to all scenes if no active branch
        return db.query(Scene).filter(
            and_(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            )
        ).order_by(Scene.sequence_number).all()


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
        
        # Check if we have a stored summary
        if story.summary:
            logger.info(f"[SUMMARY] Returning stored summary for story {story_id}")
            scenes = _get_branch_scenes(db, story_id)
            total_tokens = sum(ContextManager().count_tokens(scene.content) for scene in scenes) if scenes else 0
            return {
                "summary": story.summary,
                "total_scenes": len(scenes),
                "total_tokens": total_tokens,
                "context_used": False,
                "has_summary": True,
                "is_stored": True
            }
        
        # Get story scenes (filtered by branch)
        scenes = _get_branch_scenes(db, story_id)
        if not scenes:
            return {
                "summary": "No scenes available to summarize.",
                "total_scenes": 0,
                "total_tokens": 0,
                "context_used": False,
                "is_stored": False
            }
        
        # Get user settings for context management
        user_settings = None
        if hasattr(current_user, 'settings') and current_user.settings:
            settings_obj = current_user.settings
            user_settings = {
                "api_type": settings_obj.llm_api_type,
                "api_url": settings_obj.llm_api_url,
                "api_key": settings_obj.llm_api_key,
                "model_name": settings_obj.llm_model_name,
                "max_tokens": settings_obj.llm_max_tokens,
                "temperature": settings_obj.llm_temperature,
                "top_p": settings_obj.llm_top_p
            }
        
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
        
        # Get story scenes (filtered by branch)
        scenes = _get_branch_scenes(db, story_id)
        if not scenes:
            raise HTTPException(status_code=400, detail="Story has no scenes to summarize")
        
        # Get user settings with story context for proper NSFW filtering
        # This considers both user profile AND story content_rating
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
        
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
        
        # Generate AI summary using the unified generate_summary method
        # This will automatically use extraction LLM if user has enabled it
        ai_summary = await llm_service.generate_summary(
            story_content=combined_text,
            story_context=story_context,
            user_id=current_user.id,
            user_settings=user_settings
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
        logger.info(f"[SUMMARY] Regenerating summary for story_id={story_id}, user_id={current_user.id}")
        
        # Get the story
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        
        if not story:
            logger.error(f"[SUMMARY] Story {story_id} not found for user {current_user.id}")
            raise HTTPException(status_code=404, detail="Story not found")
        
        # Get user settings object for context settings
        user_settings_obj = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        # Get user settings with story context for proper NSFW filtering
        # This considers both user profile AND story content_rating
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
        
        # Initialize services
        context_manager = ContextManager()
        # Use the global llm_service instance
        
        # Get scenes to summarize (exclude recent ones, filtered by branch)
        scenes = _get_branch_scenes(db, story_id)
        logger.info(f"[SUMMARY] Story has {len(scenes)} total scenes (active branch)")
        
        # Use user settings object for context settings
        keep_recent = user_settings_obj.context_keep_recent_scenes if user_settings_obj else 3
        summary_threshold = user_settings_obj.context_summary_threshold if user_settings_obj else 5
        
        # For testing: if we only have 1 scene, summarize it anyway
        if len(scenes) == 1:
            logger.info(f"[SUMMARY] Single scene story - will summarize the only scene")
            scenes_to_summarize = scenes
            keep_recent = 0
        elif len(scenes) <= summary_threshold:
            logger.warning(f"[SUMMARY] Not enough scenes ({len(scenes)}) to generate summary (threshold: {summary_threshold})")
            return {
                "message": "Not enough scenes to generate summary",
                "summary": None
            }
        else:
            # Get scenes to summarize
            scenes_to_summarize = scenes[:-keep_recent] if len(scenes) > keep_recent else scenes
        
        logger.info(f"[SUMMARY] Will summarize {len(scenes_to_summarize)} scenes (keeping {keep_recent} recent)")
        
        # Generate new summary using AI
        if scenes_to_summarize:
            # Get active variant content for each scene from StoryFlow
            from .stories import SceneVariantServiceAdapter
            variant_service = SceneVariantServiceAdapter(db)
            flow = variant_service.get_active_story_flow(story_id)
            
            # Create a map of scene_id -> active variant content
            scene_content_map = {}
            for flow_item in flow:
                scene_content_map[flow_item['scene_id']] = {
                    'content': flow_item['variant']['content'],
                    'title': flow_item['variant']['title']
                }
            
            logger.info(f"[SUMMARY] Loaded active variants for {len(scene_content_map)} scenes")
            
            # Build combined text using active variant content
            combined_text = "\n\n".join([
                f"Scene {scene.sequence_number}: {scene_content_map.get(scene.id, {}).get('title', scene.title)}\n{scene_content_map.get(scene.id, {}).get('content', scene.content)}"
                for scene in scenes_to_summarize
            ])
            
            logger.info(f"[SUMMARY] Combined text length: {len(combined_text)} characters")
            logger.info(f"[SUMMARY] First 200 chars: {combined_text[:200]}...")
            
            # Prepare story context for template
            story_context = {
                "title": story.title,
                "genre": story.genre or "Unknown",
                "scene_count": len(scenes_to_summarize)
            }
            
            logger.info(f"[SUMMARY] Story context: {story_context}")
            
            # Generate new summary using dynamic prompts
            db_session = next(get_db())
            try:
                # Get dynamic prompts (user custom or default)
                system_prompt = prompt_manager.get_prompt(
                    template_key="story_summary",
                    prompt_type="system",
                    user_id=current_user.id,
                    db=db_session
                )
                
                # Get user prompt with template variables
                user_prompt = prompt_manager.get_prompt(
                    template_key="story_summary",
                    prompt_type="user",
                    user_id=current_user.id,
                    db=db_session,
                    story_content=combined_text,
                    story_context=f"Title: {story_context['title']}, Genre: {story_context['genre']}, Total Scenes: {story_context['scene_count']}"
                )
                
                # Get max tokens for this template
                max_tokens = prompt_manager.get_max_tokens("story_summary")
                
                logger.info(f"[SUMMARY] Generating with max_tokens={max_tokens}")
                logger.info(f"[SUMMARY] System prompt length: {len(system_prompt)} chars")
                logger.info(f"[SUMMARY] User prompt length: {len(user_prompt)} chars")
                
                new_summary = await llm_service.generate(
                    prompt=user_prompt,
                    user_id=current_user.id,
                    user_settings=user_settings,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens
                )
                
                logger.info(f"[SUMMARY] Generated summary length: {len(new_summary)} characters")
                logger.info(f"[SUMMARY] Summary preview: {new_summary[:200]}...")
            finally:
                db_session.close()
            
            # Save the summary to the story
            story.summary = new_summary
            db.commit()
            logger.info(f"[SUMMARY] Saved summary to database for story {story_id}")
            
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


async def update_story_summary_from_chapters(story_id: int, db: Session, user_id: int) -> None:
    """
    Reusable function to update story.summary from chapter summaries.
    This is called automatically after chapter summaries are generated.
    Handles errors gracefully - doesn't fail if story summary update fails.
    """
    try:
        from ..models import Chapter, Scene, StoryFlow, UserSettings
        
        # Get the story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.warning(f"[STORY SUMMARY] Story {story_id} not found, skipping summary update")
            return
        
        # Get all chapters for this story
        chapters = db.query(Chapter).filter(
            Chapter.story_id == story_id
        ).order_by(Chapter.chapter_number).all()
        
        if not chapters:
            logger.info(f"[STORY SUMMARY] Story {story_id} has no chapters, skipping summary update")
            return
        
        # Get user settings with story context for proper NSFW filtering
        # This considers both user profile AND story content_rating
        user_settings = get_or_create_user_settings(user_id, db, story=story)
        
        # Collect chapter summaries
        chapter_summaries = []
        total_scenes = 0
        for chapter in chapters:
            total_scenes += chapter.scenes_count
            if chapter.auto_summary:
                chapter_summaries.append(
                    f"Chapter {chapter.chapter_number} ({chapter.title or 'Untitled'}):\n{chapter.auto_summary}"
                )
            elif chapter.scenes_count > 0:
                # Chapter has scenes but no summary - get scene content
                scenes = db.query(Scene).filter(
                    Scene.chapter_id == chapter.id
                ).order_by(Scene.sequence_number).all()
                
                scene_previews = []
                for scene in scenes[:3]:  # Just first 3 scenes for preview
                    flow = db.query(StoryFlow).filter(
                        StoryFlow.scene_id == scene.id,
                        StoryFlow.is_active == True
                    ).first()
                    if flow and flow.scene_variant:
                        content = flow.scene_variant.content[:300] + "..." if len(flow.scene_variant.content) > 300 else flow.scene_variant.content
                        scene_previews.append(f"Scene {scene.sequence_number}: {content}")
                
                if scene_previews:
                    chapter_summaries.append(
                        f"Chapter {chapter.chapter_number} ({chapter.title or 'Untitled'}) - {chapter.scenes_count} scenes:\n" + "\n".join(scene_previews)
                    )
        
        if not chapter_summaries:
            logger.info(f"[STORY SUMMARY] No chapter content available for story {story_id}, skipping summary update")
            return
        
        # Combine chapter summaries
        combined_summaries = "\n\n".join(chapter_summaries)
        
        # Build story context for template
        story_context = f"Title: {story.title}, Genre: {story.genre or 'Unknown'}, Chapters: {len(chapters)}, Scenes: {total_scenes}"
        
        # Get prompts from prompts.yml
        system_prompt = prompt_manager.get_prompt("story_summary", "system", user_id=user_id, db=db)
        if not system_prompt:
            system_prompt = "You are a story state tracker. Extract facts, not prose."
        
        prompt = prompt_manager.get_prompt(
            "story_summary", "user",
            user_id=user_id, db=db,
            story_context=story_context,
            story_content=combined_summaries
        )
        if not prompt:
            prompt = f"Story: {story_context}\n\nChapter Summaries:\n{combined_summaries}\n\nCreate a factual story summary."
        
        logger.info(f"[STORY SUMMARY] Auto-updating story summary from {len(chapter_summaries)} chapters for story {story_id}")
        
        story_summary = await llm_service.generate(
            prompt=prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=800  # More tokens for full story summary
        )
        
        # Save the summary to the story
        story.summary = story_summary
        db.commit()
        
        logger.info(f"[STORY SUMMARY] Auto-updated story summary for story {story_id}: {len(story_summary)} chars")
            
    except Exception as e:
        # Log error but don't fail - story summary update is non-critical
        logger.error(f"[STORY SUMMARY] Error auto-updating story summary for story {story_id}: {e}", exc_info=True)


@router.post("/stories/{story_id}/generate-story-summary")
async def generate_story_summary_from_chapters(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate story-level summary from chapter summaries (summary of summaries approach).
    This is more efficient than summarizing all scenes individually.
    """
    try:
        await update_story_summary_from_chapters(story_id, db, current_user.id)
        
        # Refresh story to get updated summary
        db.refresh(db.query(Story).filter(Story.id == story_id).first())
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        
        return {
            "message": "Story summary generated successfully",
            "summary": story.summary,
            "approach": "summary_of_summaries"
        }
            
    except Exception as e:
        logger.error(f"Error generating story summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
