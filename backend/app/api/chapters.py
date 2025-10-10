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
    
    # Create new chapter
    new_chapter = Chapter(
        story_id=story_id,
        chapter_number=next_chapter_number,
        title=chapter_data.title or f"Chapter {next_chapter_number}",
        description=chapter_data.description,
        story_so_far=chapter_data.story_so_far or "Continuing the story...",
        plot_point=chapter_data.plot_point,
        status=ChapterStatus.ACTIVE,
        context_tokens_used=0,
        scenes_count=0
    )
    
    db.add(new_chapter)
    db.commit()
    db.refresh(new_chapter)
    
    logger.info(f"[CHAPTER] Created chapter {new_chapter.id} (Chapter {next_chapter_number})")
    
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate or regenerate chapter summary"""
    
    logger.info(f"[CHAPTER] Generating summary for chapter {chapter_id}")
    
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
    
    summary = await generate_chapter_summary(chapter_id, db, current_user.id)
    
    return {
        "message": "Chapter summary generated successfully",
        "summary": summary,
        "scenes_summarized": chapter.scenes_count
    }


async def generate_chapter_summary(chapter_id: int, db: Session, user_id: int) -> str:
    """Internal helper to generate chapter summary"""
    
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return ""
    
    # Get all scenes in this chapter with their active variants
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
    
    # Prepare context for LLM
    combined_content = "\n\n".join(scene_contents)
    
    prompt = f"""Summarize the following chapter content into a concise summary that captures the key events, character developments, and plot progression. This summary will be used as context for future chapters.

Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}

Content:
{combined_content}

Provide a clear, comprehensive summary in 2-3 paragraphs:"""
    
    # Get user settings
    from ..models import UserSettings
    user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    user_settings = user_settings_obj.to_dict() if user_settings_obj else None
    
    # Generate summary using basic LLM generation (not scene continuation)
    summary = await llm_service._generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt="You are a helpful assistant that creates concise narrative summaries.",
        max_tokens=400  # Enough for a good summary
    )
    
    # Update chapter
    chapter.auto_summary = summary
    chapter.last_summary_scene_count = chapter.scenes_count
    db.commit()
    
    logger.info(f"[CHAPTER] Generated summary for chapter {chapter_id}: {len(summary)} chars")
    
    return summary


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
