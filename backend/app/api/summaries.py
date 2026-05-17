from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..database import get_db
from ..models import User, Story, Scene, StoryBranch
from ..dependencies import get_current_user
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
    """Get the story summary for display (narrative recap + current chapter info)."""
    try:
        from ..models import Chapter

        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        # Get latest chapter for story_so_far fallback and current chapter info
        latest_chapter = (
            db.query(Chapter)
            .filter(Chapter.story_id == story_id)
            .order_by(Chapter.chapter_number.desc())
            .first()
        )

        # Build summary text: prefer stored narrative recap, fall back to structured story_so_far
        summary_text = story.summary or ""
        if not summary_text and latest_chapter:
            summary_text = latest_chapter.story_so_far or latest_chapter.auto_summary or ""

        # Append current chapter overview
        if latest_chapter:
            current_ch = f"\n\nCURRENT CHAPTER: Chapter {latest_chapter.chapter_number}"
            if latest_chapter.title:
                current_ch += f" — {latest_chapter.title}"
            if latest_chapter.description:
                current_ch += f"\n{latest_chapter.description}"
            summary_text = (summary_text + current_ch).strip()

        if not summary_text:
            return {"summary": "No summary available yet. Generate scenes first.", "has_summary": False}

        return {
            "summary": summary_text,
            "has_summary": True,
            "is_stored": bool(story.summary),
        }

    except HTTPException:
        raise
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
    """Regenerate story summary by converting the latest chapter's story_so_far into narrative prose."""
    try:
        from ..models import Chapter
        from sqlalchemy import func

        logger.info(f"[SUMMARY] Regenerating summary for story_id={story_id}, user_id={current_user.id}")

        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id
        ).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        # Get latest chapter's story_so_far (already maintained by chapter creation flow)
        latest_chapter = (
            db.query(Chapter)
            .filter(Chapter.story_id == story_id)
            .order_by(Chapter.chapter_number.desc())
            .first()
        )

        story_so_far = None
        if latest_chapter:
            story_so_far = latest_chapter.story_so_far or latest_chapter.auto_summary

        if not story_so_far:
            return {"message": "No story data available to summarize", "summary": None}

        logger.info(f"[SUMMARY] Using story_so_far from chapter {latest_chapter.chapter_number} ({len(story_so_far)} chars)")

        # Get user settings for LLM call
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

        # Compute word limit proportional to input size (half of input words, clamped 300-1200)
        word_limit = min(1200, max(300, len(story_so_far.split()) // 2))

        # Use story_recap prompt to convert structured story_so_far → narrative prose
        system_prompt = prompt_manager.get_prompt(
            "story_recap", "system", user_id=current_user.id, db=db,
            word_limit=word_limit
        )
        if not system_prompt:
            system_prompt = "Rewrite a structured story tracker into a readable narrative recap."

        user_prompt = prompt_manager.get_prompt(
            "story_recap", "user", user_id=current_user.id, db=db,
            story_so_far=story_so_far, word_limit=word_limit
        )
        if not user_prompt:
            user_prompt = f"Rewrite this as a narrative recap:\n\n{story_so_far}"

        max_tokens = prompt_manager.get_max_tokens("story_recap")

        new_summary = await llm_service.generate(
            prompt=user_prompt,
            user_id=current_user.id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )

        # Save to story.summary for caching
        story.summary = new_summary
        db.commit()

        logger.info(f"[SUMMARY] Generated narrative recap: {len(new_summary)} chars")

        return {
            "message": "Summary regenerated successfully",
            "summary": new_summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating story summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate summary")


async def update_story_summary_from_chapters(story_id: int, db: Session, user_id: int) -> None:
    """
    Update story.summary by converting the latest chapter's story_so_far into narrative prose.
    Called automatically after chapter completion. Non-critical — errors are logged but don't propagate.
    """
    try:
        from ..models import Chapter

        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.warning(f"[STORY SUMMARY] Story {story_id} not found, skipping")
            return

        # Get latest chapter's story_so_far
        latest_chapter = (
            db.query(Chapter)
            .filter(Chapter.story_id == story_id)
            .order_by(Chapter.chapter_number.desc())
            .first()
        )

        story_so_far = None
        if latest_chapter:
            story_so_far = latest_chapter.story_so_far or latest_chapter.auto_summary

        if not story_so_far:
            logger.info(f"[STORY SUMMARY] No story_so_far available for story {story_id}, skipping")
            return

        user_settings = get_or_create_user_settings(user_id, db, story=story)

        # Compute word limit proportional to input size (half of input words, clamped 300-1200)
        word_limit = min(1200, max(300, len(story_so_far.split()) // 2))

        system_prompt = prompt_manager.get_prompt("story_recap", "system", user_id=user_id, db=db, word_limit=word_limit)
        if not system_prompt:
            system_prompt = "Rewrite a structured story tracker into a readable narrative recap."

        user_prompt = prompt_manager.get_prompt(
            "story_recap", "user", user_id=user_id, db=db,
            story_so_far=story_so_far, word_limit=word_limit
        )
        if not user_prompt:
            user_prompt = f"Rewrite this as a narrative recap:\n\n{story_so_far}"

        max_tokens = prompt_manager.get_max_tokens("story_recap")

        logger.info(f"[STORY SUMMARY] Generating narrative recap from story_so_far ({len(story_so_far)} chars) for story {story_id}")

        narrative = await llm_service.generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )

        story.summary = narrative
        db.commit()

        logger.info(f"[STORY SUMMARY] Updated narrative recap for story {story_id}: {len(narrative)} chars")

    except Exception as e:
        logger.error(f"[STORY SUMMARY] Error updating story summary for story {story_id}: {e}", exc_info=True)


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
