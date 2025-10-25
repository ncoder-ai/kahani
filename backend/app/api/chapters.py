from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Chapter, Scene, User, ChapterStatus, StoryMode
from ..dependencies import get_current_user
from ..services.llm.service import UnifiedLLMService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
llm_service = UnifiedLLMService()

# Pydantic models for request/response
class ChapterCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    story_so_far: Optional[str] = None
    plot_point: Optional[str] = None

class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    story_so_far: Optional[str] = None
    auto_summary: Optional[str] = None
    plot_point: Optional[str] = None

class ChapterResponse(BaseModel):
    id: int
    story_id: int
    chapter_number: int
    title: Optional[str]
    description: Optional[str]
    story_so_far: Optional[str]
    plot_point: Optional[str]
    status: str
    context_tokens_used: int
    scenes_count: int
    auto_summary: Optional[str]
    last_summary_scene_count: int
    created_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ChapterContextStatus(BaseModel):
    chapter_id: int
    current_tokens: int
    max_tokens: int
    percentage_used: float
    should_create_new_chapter: bool
    reason: Optional[str] = None
    scenes_count: int
    avg_generation_time: Optional[float] = None


@router.get("/{story_id}/chapters", response_model=List[ChapterResponse])
async def get_story_chapters(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all chapters for a story"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapters = db.query(Chapter).filter(
        Chapter.story_id == story_id
    ).order_by(Chapter.chapter_number).all()
    
    return chapters


@router.get("/{story_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific chapter"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    return chapter


@router.post("/{story_id}/chapters", response_model=ChapterResponse)
async def create_chapter(
    story_id: int,
    chapter_data: ChapterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new chapter (Dynamic mode)"""
    
    logger.info(f"[CHAPTER] Creating new chapter for story {story_id}")
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Get the current active chapter to complete it
    active_chapter = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.status == ChapterStatus.ACTIVE
    ).first()
    
    # Get next chapter number
    max_chapter = db.query(Chapter).filter(
        Chapter.story_id == story_id
    ).order_by(Chapter.chapter_number.desc()).first()
    
    next_chapter_number = (max_chapter.chapter_number + 1) if max_chapter else 1
    
    # Mark current chapter as completed if exists
    if active_chapter:
        active_chapter.status = ChapterStatus.COMPLETED
        active_chapter.completed_at = datetime.utcnow()
        logger.info(f"[CHAPTER] Marked chapter {active_chapter.id} as completed")
        
        # Generate summary for the completed chapter if it doesn't have one yet
        if not active_chapter.auto_summary and active_chapter.scenes_count > 0:
            logger.info(f"[CHAPTER] Generating summary for completed chapter {active_chapter.id}")
            try:
                # Generate the chapter's own summary
                await generate_chapter_summary(active_chapter.id, db, current_user.id)
                
                # Also update its story_so_far (for reference)
                await generate_story_so_far(active_chapter.id, db, current_user.id)
                
                db.refresh(active_chapter)  # Refresh to get the auto_summary
                logger.info(f"[CHAPTER] Summary generated for completed chapter {active_chapter.id}")
            except Exception as e:
                logger.error(f"[CHAPTER] Failed to generate summary for completed chapter {active_chapter.id}: {e}")
                # Continue with chapter creation even if summary fails
    
    # Create new chapter
    # Generate initial story_so_far for the new chapter based on all previous chapters
    new_chapter = Chapter(
        story_id=story_id,
        chapter_number=next_chapter_number,
        title=chapter_data.title or f"Chapter {next_chapter_number}",
        description=chapter_data.description,
        story_so_far="Generating story summary...",  # Placeholder
        plot_point=chapter_data.plot_point,
        status=ChapterStatus.ACTIVE,
        context_tokens_used=0,
        scenes_count=0
    )
    
    db.add(new_chapter)
    db.commit()
    db.refresh(new_chapter)
    
    logger.info(f"[CHAPTER] Created chapter {new_chapter.id} (Chapter {next_chapter_number})")
    
    # Generate the story_so_far for the new chapter (combining all previous chapters)
    try:
        await generate_story_so_far(new_chapter.id, db, current_user.id)
        db.refresh(new_chapter)
        logger.info(f"[CHAPTER] Generated story_so_far for new chapter {new_chapter.id}")
    except Exception as e:
        logger.error(f"[CHAPTER] Failed to generate story_so_far for new chapter {new_chapter.id}: {e}")
        # Set a fallback if generation fails
        new_chapter.story_so_far = "Continuing the story..."
        db.commit()
    
    return new_chapter


@router.put("/{story_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    story_id: int,
    chapter_id: int,
    chapter_data: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update chapter details"""
    
    logger.info(f"[CHAPTER] Updating chapter {chapter_id}")
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Update fields
    if chapter_data.title is not None:
        chapter.title = chapter_data.title
    if chapter_data.description is not None:
        chapter.description = chapter_data.description
    if chapter_data.story_so_far is not None:
        chapter.story_so_far = chapter_data.story_so_far
    if chapter_data.plot_point is not None:
        chapter.plot_point = chapter_data.plot_point
    
    db.commit()
    db.refresh(chapter)
    
    logger.info(f"[CHAPTER] Updated chapter {chapter_id}")
    
    return chapter


@router.post("/{story_id}/chapters/{chapter_id}/complete", response_model=ChapterResponse)
async def complete_chapter(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark chapter as completed and generate summary"""
    
    logger.info(f"[CHAPTER] Completing chapter {chapter_id}")
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Generate chapter summary if not already done
    if not chapter.auto_summary or chapter.last_summary_scene_count < chapter.scenes_count:
        logger.info(f"[CHAPTER] Generating final summary for chapter {chapter_id}")
        await generate_chapter_summary(chapter_id, db, current_user.id)
    
    # Mark as completed
    chapter.status = ChapterStatus.COMPLETED
    chapter.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(chapter)
    
    logger.info(f"[CHAPTER] Chapter {chapter_id} completed")
    
    return chapter


@router.get("/{story_id}/chapters/{chapter_id}/context-status", response_model=ChapterContextStatus)
async def get_chapter_context_status(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get context usage status for a chapter"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Get user settings for max tokens
    from ..models import UserSettings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    max_tokens = user_settings.context_max_tokens if user_settings else 4000
    threshold_percentage = 80  # Default 80%
    
    # Calculate percentage
    percentage_used = (chapter.context_tokens_used / max_tokens) * 100 if max_tokens > 0 else 0
    
    # Determine if new chapter should be created
    should_create_new = False
    reason = None
    
    if percentage_used >= threshold_percentage:
        should_create_new = True
        reason = "context_limit"
    
    # TODO: Add time-based detection in future
    
    return ChapterContextStatus(
        chapter_id=chapter_id,
        current_tokens=chapter.context_tokens_used,
        max_tokens=max_tokens,
        percentage_used=round(percentage_used, 2),
        should_create_new_chapter=should_create_new,
        reason=reason,
        scenes_count=chapter.scenes_count
    )


@router.post("/{story_id}/chapters/{chapter_id}/generate-summary")
async def generate_chapter_summary_endpoint(
    story_id: int,
    chapter_id: int,
    regenerate_story_so_far: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate or regenerate chapter summary and optionally story_so_far.
    - Generates chapter.auto_summary (summary of this chapter's scenes)
    - If regenerate_story_so_far=True, also regenerates chapter.story_so_far
      (combined summary of all previous chapters + current chapter)
    """
    
    logger.info(f"[CHAPTER] Generating summary for chapter {chapter_id} (regenerate_story_so_far={regenerate_story_so_far})")
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Generate chapter summary (this chapter's content only)
    chapter_summary = await generate_chapter_summary(chapter_id, db, current_user.id)
    
    # Optionally regenerate story_so_far (all previous + current)
    story_so_far = None
    if regenerate_story_so_far:
        story_so_far = await generate_story_so_far(chapter_id, db, current_user.id)
    
    return {
        "message": "Chapter summary generated successfully",
        "chapter_summary": chapter_summary,
        "story_so_far": story_so_far,
        "scenes_summarized": chapter.scenes_count
    }


async def generate_chapter_summary(chapter_id: int, db: Session, user_id: int) -> str:
    """
    Generate a summary of the chapter's scenes WITH CONTEXT from previous chapters.
    This is stored in chapter.auto_summary and represents ONLY this chapter's content,
    but the LLM receives previous chapter summaries to maintain consistency.
    """
    
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return ""
    
    # Get ALL PREVIOUS chapters' summaries for context
    previous_chapters = db.query(Chapter).filter(
        Chapter.story_id == chapter.story_id,
        Chapter.chapter_number < chapter.chapter_number
    ).order_by(Chapter.chapter_number).all()
    
    previous_summaries = []
    for ch in previous_chapters:
        if ch.auto_summary:
            previous_summaries.append(f"Chapter {ch.chapter_number} ({ch.title or 'Untitled'}): {ch.auto_summary}")
    
    # Get all scenes in THIS chapter with their active variants
    from .stories import SceneVariantServiceAdapter
    from ..models import StoryFlow
    
    variant_service = SceneVariantServiceAdapter(db)
    scenes = db.query(Scene).filter(
        Scene.chapter_id == chapter_id
    ).order_by(Scene.sequence_number).all()
    
    if not scenes:
        return "No scenes in this chapter yet."
    
    # Build scene content from active variants
    scene_contents = []
    for scene in scenes:
        # Get active variant from StoryFlow
        flow = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()
        
        if flow and flow.scene_variant:
            scene_contents.append(f"Scene {scene.sequence_number}: {flow.scene_variant.content}")
    
    if not scene_contents:
        return "No content available to summarize."
    
    # Prepare context for LLM with previous chapters for continuity
    combined_content = "\n\n".join(scene_contents)
    
    # Build prompt with context from previous chapters
    context_section = ""
    if previous_summaries:
        context_section = f"""
Previous Chapters (for context - maintain consistency with these):
{chr(10).join(previous_summaries)}

"""
    
    prompt = f"""Summarize Chapter {chapter.chapter_number} below into a concise summary that captures the key events, character developments, and plot progression.

{context_section}Current Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}

Scenes to Summarize:
{combined_content}

Instructions:
- Summarize ONLY Chapter {chapter.chapter_number}'s content
- Maintain consistency with characters and events from previous chapters
- Capture key events, character developments, and plot progression
- Keep summary to 2-3 paragraphs

Summary:"""
    
    # Get user settings
    from ..models import UserSettings
    user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    user_settings = user_settings_obj.to_dict() if user_settings_obj else None
    
    # Generate summary using basic LLM generation (not scene continuation)
    summary = await llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt="You are a helpful assistant that creates concise narrative summaries.",
        max_tokens=400  # Enough for a good summary
    )
    
    # Update chapter's auto_summary (just this chapter's content)
    chapter.auto_summary = summary
    chapter.last_summary_scene_count = chapter.scenes_count
    db.commit()
    
    logger.info(f"[CHAPTER] Generated summary for chapter {chapter_id}: {len(summary)} chars")
    
    return summary


async def generate_story_so_far(chapter_id: int, db: Session, user_id: int) -> str:
    """
    Generate "Story So Far" for a chapter by combining:
    1. Summaries of ALL previous chapters (from their auto_summary) 
    2. Summary of the CURRENT chapter (from its auto_summary)
    
    This creates a cumulative narrative context stored in chapter.story_so_far.
    If current chapter doesn't have auto_summary yet, it will generate it first.
    """
    
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return ""
    
    story_id = chapter.story_id
    
    # Get all previous chapters (completed or active, in order)
    previous_chapters = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.chapter_number < chapter.chapter_number
    ).order_by(Chapter.chapter_number).all()
    
    # Build the story so far from previous chapter summaries
    previous_summaries = []
    for prev_ch in previous_chapters:
        if prev_ch.auto_summary:
            previous_summaries.append(f"Chapter {prev_ch.chapter_number} ({prev_ch.title or 'Untitled'}): {prev_ch.auto_summary}")
    
    # Get CURRENT chapter's summary (generate if doesn't exist)
    if not chapter.auto_summary:
        logger.info(f"[CHAPTER] Current chapter {chapter_id} has no summary, generating it first...")
        await generate_chapter_summary(chapter_id, db, user_id)
        # Refresh to get the updated auto_summary
        db.refresh(chapter)
    
    current_summary = chapter.auto_summary or "No content yet."
    
    # Combine everything  
    story_parts = []
    
    if previous_summaries:
        story_parts.append("=== Previous Chapters ===\n" + "\n\n".join(previous_summaries))
    
    story_parts.append(f"=== Chapter {chapter.chapter_number} (Current): {chapter.title or 'Untitled'} ===\n{current_summary}")
    
    if not story_parts:
        return "The story begins..."
    
    combined_story = "\n\n".join(story_parts)
    
    # Now use LLM to create a cohesive "Story So Far" summary
    prompt = f"""Create a cohesive "Story So Far" summary from the following chapter summaries. This should read as a continuous narrative that helps the reader understand where the story currently stands.

{combined_story}

Instructions:
- Combine all chapter summaries into a flowing narrative
- Maintain chronological order
- Highlight key plot points and character developments
- Keep the summary engaging and comprehensive (3-4 paragraphs)

Story So Far:"""
    
    # Get user settings
    from ..models import UserSettings
    user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    user_settings = user_settings_obj.to_dict() if user_settings_obj else None
    
    # Generate story so far
    story_so_far = await llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt="You are a helpful assistant that creates cohesive story summaries from chapter summaries and recent events.",
        max_tokens=600  # More tokens since it combines multiple chapters
    )
    
    # Update chapter's story_so_far
    chapter.story_so_far = story_so_far
    db.commit()
    
    logger.info(f"[CHAPTER] Generated story_so_far for chapter {chapter_id}: {len(story_so_far)} chars")
    
    return story_so_far


@router.delete("/{story_id}/chapters/{chapter_id}/scenes")
async def delete_chapter_content(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete all scenes in a chapter (for structured mode - rewrite chapter)"""
    
    logger.info(f"[CHAPTER] Deleting content for chapter {chapter_id}")
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Delete all scenes in this chapter
    scenes = db.query(Scene).filter(Scene.chapter_id == chapter_id).all()
    scene_count = len(scenes)
    
    for scene in scenes:
        db.delete(scene)
    
    # Reset chapter metrics
    chapter.scenes_count = 0
    chapter.context_tokens_used = 0
    chapter.auto_summary = None
    chapter.last_summary_scene_count = 0
    chapter.status = ChapterStatus.ACTIVE
    
    db.commit()
    
    logger.info(f"[CHAPTER] Deleted {scene_count} scenes from chapter {chapter_id}")
    
    return {
        "message": "Chapter content deleted successfully",
        "scenes_deleted": scene_count
    }


@router.get("/{story_id}/active-chapter", response_model=ChapterResponse)
async def get_active_chapter(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the currently active chapter for a story"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    chapter = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.status == ChapterStatus.ACTIVE
    ).first()
    
    if not chapter:
        # No active chapter - create Chapter 1
        chapter = Chapter(
            story_id=story_id,
            chapter_number=1,
            title="Chapter 1",
            story_so_far="The story begins...",
            status=ChapterStatus.ACTIVE
        )
        db.add(chapter)
        db.commit()
        db.refresh(chapter)
        logger.info(f"[CHAPTER] Created initial chapter for story {story_id}")
    
    return chapter
