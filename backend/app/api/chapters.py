from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Chapter, Scene, User, ChapterStatus, StoryMode, StoryCharacter, Character, ChapterSummaryBatch
from ..models.chapter import chapter_characters
from ..dependencies import get_current_user
from ..services.llm.service import UnifiedLLMService
from ..services.llm.prompts import prompt_manager
from ..config import settings
from datetime import datetime, timezone
import time
import logging
import json
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()
llm_service = UnifiedLLMService()

# Pydantic models for request/response
class ChapterCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    story_so_far: Optional[str] = None
    plot_point: Optional[str] = None
    story_character_ids: Optional[List[int]] = None  # IDs from story_characters table
    character_ids: Optional[List[int]] = None  # Character IDs from library to add to story
    character_roles: Optional[dict] = None  # Map of character_id to role for new characters
    location_name: Optional[str] = None
    time_period: Optional[str] = None
    scenario: Optional[str] = None
    continues_from_previous: Optional[bool] = True  # Default to True
    chapter_plot: Optional[Dict[str, Any]] = None  # Structured plot from brainstorming
    brainstorm_session_id: Optional[int] = None  # Link to brainstorm session

class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    story_so_far: Optional[str] = None
    auto_summary: Optional[str] = None
    plot_point: Optional[str] = None
    story_character_ids: Optional[List[int]] = None
    location_name: Optional[str] = None
    time_period: Optional[str] = None
    scenario: Optional[str] = None
    continues_from_previous: Optional[bool] = None
    chapter_plot: Optional[Dict[str, Any]] = None  # Structured plot from brainstorming
    brainstorm_session_id: Optional[int] = None  # Link to brainstorm session
    arc_phase_id: Optional[str] = None  # Story arc phase this chapter belongs to

class CharacterInfo(BaseModel):
    id: int
    name: str
    role: Optional[str]
    description: Optional[str]
    
    class Config:
        from_attributes = True

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
    characters: Optional[List[CharacterInfo]] = []
    location_name: Optional[str] = None
    time_period: Optional[str] = None
    scenario: Optional[str] = None
    continues_from_previous: Optional[bool] = True
    chapter_plot: Optional[Dict[str, Any]] = None
    arc_phase_id: Optional[str] = None
    
    class Config:
        from_attributes = True

def build_chapter_response(chapter: Chapter, db: Session) -> ChapterResponse:
    """Helper function to build ChapterResponse with characters"""
    # Load characters for chapter (filter by branch_id to avoid cross-branch contamination)
    chapter_char_query = db.query(StoryCharacter).join(
        chapter_characters, StoryCharacter.id == chapter_characters.c.story_character_id
    ).filter(
        chapter_characters.c.chapter_id == chapter.id
    )
    # Filter by branch_id if the chapter has one
    if chapter.branch_id:
        chapter_char_query = chapter_char_query.filter(StoryCharacter.branch_id == chapter.branch_id)
    chapter_chars = chapter_char_query.all()
    
    # Build character info list
    char_info_list = []
    for sc in chapter_chars:
        char = db.query(Character).filter(Character.id == sc.character_id).first()
        if char:
            char_info_list.append(CharacterInfo(
                id=sc.character_id,
                name=char.name,
                role=sc.role,
                description=char.description
            ))
    
    return ChapterResponse(
        id=chapter.id,
        story_id=chapter.story_id,
        chapter_number=chapter.chapter_number,
        title=chapter.title,
        description=chapter.description,
        story_so_far=chapter.story_so_far,
        plot_point=chapter.plot_point,
        status=chapter.status.value,
        context_tokens_used=chapter.context_tokens_used,
        scenes_count=chapter.scenes_count,
        auto_summary=chapter.auto_summary,
        last_summary_scene_count=chapter.last_summary_scene_count,
        created_at=chapter.created_at,
        completed_at=chapter.completed_at,
        characters=char_info_list,
        location_name=chapter.location_name,
        time_period=chapter.time_period,
        scenario=chapter.scenario,
        continues_from_previous=getattr(chapter, 'continues_from_previous', True),
        chapter_plot=chapter.chapter_plot,
        arc_phase_id=chapter.arc_phase_id
    )

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
    branch_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all chapters for a story on the active or specified branch"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Use provided branch_id or story's current branch
    active_branch_id = branch_id or story.current_branch_id
    
    # Filter chapters by branch
    query = db.query(Chapter).filter(Chapter.story_id == story_id)
    if active_branch_id:
        query = query.filter(Chapter.branch_id == active_branch_id)
    
    chapters = query.order_by(Chapter.chapter_number).all()
    
    # Build responses with characters
    return [build_chapter_response(ch, db) for ch in chapters]


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
    
    return build_chapter_response(chapter, db)


@router.post("/{story_id}/chapters")
async def create_chapter(
    story_id: int,
    chapter_data: ChapterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new chapter (Dynamic mode) with streaming status updates"""
    
    async def generate_stream():
        trace_id = f"chap-create-{uuid.uuid4()}"
        prev_chapter_completed = False
        new_chapter_created = False
        
        try:
            logger.info(f"[CHAPTER:CREATE:START] trace_id={trace_id} story_id={story_id}")
            
            # Verify story ownership
            story = db.query(Story).filter(
                Story.id == story_id,
                Story.owner_id == current_user.id
            ).first()
            
            if not story:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Story not found'})}\n\n"
                return
            
            # Get active branch
            active_branch_id = story.current_branch_id
            if not active_branch_id:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Story has no active branch'})}\n\n"
                return
            
            logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} active_branch_id={active_branch_id}")
            
            # Get the current active chapter to complete it (filtered by branch)
            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id,
                Chapter.status == ChapterStatus.ACTIVE
            ).first()
            
            # STEP 1: Complete previous chapter (if exists) in its own transaction
            # This ensures that if summary generation fails, we can retry without side effects
            if active_chapter:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Completing previous chapter...', 'step': 'completing_previous'})}\n\n"
                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} completing_chapter_id={active_chapter.id} chapter_number={active_chapter.chapter_number}")
                
                try:
                    # ALWAYS regenerate summary for the completed chapter to include all scenes
                    # (even if summary exists, it might be stale and missing recent scenes)
                    # IMPORTANT: Generate summary BEFORE marking as completed so rollback works
                    if active_chapter.scenes_count > 0:
                        yield f"data: {json.dumps({'type': 'status', 'message': 'Generating chapter summary...', 'step': 'generating_chapter_summary'})}\n\n"
                        logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} generating_summary chapter_id={active_chapter.id} scenes={active_chapter.scenes_count}")
                        
                        # Generate the chapter's own summary (incremental - only new scenes)
                        await generate_chapter_summary_incremental(active_chapter.id, db, current_user.id)
                        
                        db.refresh(active_chapter)  # Refresh to get the auto_summary
                        logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} summary_generated chapter_id={active_chapter.id}")
                        
                        # Update story.summary now that this chapter is completed
                        try:
                            from ..api.summaries import update_story_summary_from_chapters
                            await update_story_summary_from_chapters(active_chapter.story_id, db, current_user.id)
                            logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} story_summary_updated")
                        except Exception as e:
                            # Don't fail chapter creation if story summary update fails
                            logger.warning(f"[CHAPTER:CREATE] trace_id={trace_id} story_summary_failed error={e}")
                    
                    # ONLY mark as completed AFTER summary generation succeeds
                    # This ensures rollback works properly if summary generation fails
                    active_chapter.status = ChapterStatus.COMPLETED
                    active_chapter.completed_at = datetime.now(timezone.utc)
                    
                    # Commit completed chapter changes ONLY (separate transaction)
                    db.commit()
                    prev_chapter_completed = True
                    logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} prev_chapter_committed chapter_id={active_chapter.id}")
                    
                except Exception as e:
                    logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} step=completing_previous error={e}")
                    db.rollback()
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to complete previous chapter: {str(e)}'})}\n\n"
                    return
            
            # STEP 2: Calculate next chapter number AFTER completing previous chapter
            # This ensures we get the correct number even if previous operation modified the database
            yield f"data: {json.dumps({'type': 'status', 'message': 'Creating new chapter...', 'step': 'creating_chapter'})}\n\n"
            
            # Recalculate chapter number to ensure accuracy
            max_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id
            ).order_by(Chapter.chapter_number.desc()).first()
            
            next_chapter_number = (max_chapter.chapter_number + 1) if max_chapter else 1
            logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} next_chapter_number={next_chapter_number} max_chapter={'None' if not max_chapter else max_chapter.chapter_number}")
            
            # STEP 3: Create new chapter in a separate transaction
            # This ensures clean rollback if anything fails during creation
            try:
                # Validate no duplicate chapter number exists (safety check)
                duplicate_check = db.query(Chapter).filter(
                    Chapter.story_id == story_id,
                    Chapter.branch_id == active_branch_id,
                    Chapter.chapter_number == next_chapter_number
                ).first()
                
                if duplicate_check:
                    logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} duplicate_chapter_number={next_chapter_number} existing_chapter_id={duplicate_check.id}")
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Chapter {next_chapter_number} already exists. Please refresh and try again.'})}\n\n"
                    return
                
                # Create new chapter (but don't commit yet - wait for summaries)
                # Don't use placeholder strings - use None if no real summary exists
                initial_story_so_far = None
                
                new_chapter = Chapter(
                    story_id=story_id,
                    branch_id=active_branch_id,
                    chapter_number=next_chapter_number,
                    title=chapter_data.title or f"Chapter {next_chapter_number}",
                    description=chapter_data.description,
                    story_so_far=initial_story_so_far,
                    plot_point=chapter_data.plot_point,
                    location_name=chapter_data.location_name,
                    time_period=chapter_data.time_period,
                    scenario=chapter_data.scenario,
                    continues_from_previous=chapter_data.continues_from_previous if chapter_data.continues_from_previous is not None else True,
                    status=ChapterStatus.ACTIVE,
                    context_tokens_used=0,
                    scenes_count=0,
                    chapter_plot=chapter_data.chapter_plot,
                    brainstorm_session_id=chapter_data.brainstorm_session_id
                )
                
                db.add(new_chapter)
                db.flush()  # Flush to get the chapter ID (but don't commit yet)
                new_chapter_created = True
                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} new_chapter_flushed chapter_id={new_chapter.id} chapter_number={next_chapter_number}")
                
                # Collect all story_character_ids to associate with the chapter
                all_story_character_ids = set()
                
                # Handle new characters from library (character_ids)
                if chapter_data.character_ids:
                    character_roles = chapter_data.character_roles or {}
                    for character_id in chapter_data.character_ids:
                        # Check if character exists
                        char = db.query(Character).filter(Character.id == character_id).first()
                        if not char:
                            db.rollback()  # Rollback before returning error
                            logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} character_not_found character_id={character_id}")
                            yield f"data: {json.dumps({'type': 'error', 'message': f'Character with ID {character_id} not found'})}\n\n"
                            return
                        
                        # Check if StoryCharacter entry already exists for this story and branch
                        story_char = db.query(StoryCharacter).filter(
                            StoryCharacter.story_id == story_id,
                            StoryCharacter.branch_id == active_branch_id,
                            StoryCharacter.character_id == character_id
                        ).first()
                        
                        if not story_char:
                            # Create new StoryCharacter entry for this branch
                            # Handle both int and str keys (JSON may convert int keys to strings)
                            role = None
                            if isinstance(character_roles, dict):
                                role = character_roles.get(character_id) or character_roles.get(str(character_id))
                            story_char = StoryCharacter(
                                story_id=story_id,
                                branch_id=active_branch_id,
                                character_id=character_id,
                                role=role,
                                is_active=True
                            )
                            db.add(story_char)
                            db.flush()  # Flush to get the ID (but don't commit yet)
                            logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} created_story_character character_id={character_id} role={role}")
                        else:
                            # Update role if provided and different
                            # Handle both int and str keys (JSON may convert int keys to strings)
                            new_role = None
                            if isinstance(character_roles, dict):
                                new_role = character_roles.get(character_id) or character_roles.get(str(character_id))
                            if new_role and story_char.role != new_role:
                                story_char.role = new_role
                                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} updated_story_character_role story_char_id={story_char.id} role={new_role}")
                        
                        all_story_character_ids.add(story_char.id)
                
                # Handle existing story characters (story_character_ids)
                if chapter_data.story_character_ids:
                    # Validate that all story_character_ids belong to this story and branch
                    # Allow characters with NULL branch_id (pre-branching or shared characters)
                    story_chars = db.query(StoryCharacter).filter(
                        StoryCharacter.id.in_(chapter_data.story_character_ids),
                        StoryCharacter.story_id == story_id,
                        or_(
                            StoryCharacter.branch_id == active_branch_id,
                            StoryCharacter.branch_id.is_(None)
                        )
                    ).all()
                    
                    if len(story_chars) != len(chapter_data.story_character_ids):
                        # Log which characters failed validation for debugging
                        found_ids = {sc.id for sc in story_chars}
                        missing_ids = [cid for cid in chapter_data.story_character_ids if cid not in found_ids]
                        
                        # Get details about missing characters for better error message
                        missing_chars = db.query(StoryCharacter).filter(
                            StoryCharacter.id.in_(missing_ids)
                        ).all()
                        
                        missing_details = []
                        for mc in missing_chars:
                            missing_details.append(f"id={mc.id} story_id={mc.story_id} branch_id={mc.branch_id}")
                        
                        db.rollback()  # Rollback before returning error
                        logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} invalid_story_characters requested={len(chapter_data.story_character_ids)} found={len(story_chars)} active_branch={active_branch_id}")
                        logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} missing_characters: {', '.join(missing_details)}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Some character IDs do not belong to this story branch'})}\n\n"
                        return
                    
                    # Add to the set of story_character_ids
                    for story_char in story_chars:
                        all_story_character_ids.add(story_char.id)
                
                # Create chapter-character associations for all characters
                if all_story_character_ids:
                    for story_char_id in all_story_character_ids:
                        db.execute(
                            chapter_characters.insert().values(
                                chapter_id=new_chapter.id,
                                story_character_id=story_char_id
                            )
                        )
                    logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} associated_characters count={len(all_story_character_ids)}")
                
                # Generate the story_so_far for the new chapter (combining all previous chapters)
                # BUT skip for the first chapter since there are no previous chapters
                if next_chapter_number > 1:
                    yield f"data: {json.dumps({'type': 'status', 'message': 'Generating story so far...', 'step': 'generating_story_so_far'})}\n\n"
                    try:
                        await generate_story_so_far(new_chapter.id, db, current_user.id)
                        db.refresh(new_chapter)
                        logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} story_so_far_generated")
                    except Exception as e:
                        logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} story_so_far_failed error={e}")
                        db.rollback()
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to generate story context: {str(e)}'})}\n\n"
                        return
                
                # Now commit everything atomically: new chapter + character associations + summaries
                db.commit()
                db.refresh(new_chapter)
                
                logger.info(f"[CHAPTER:CREATE:SUCCESS] trace_id={trace_id} chapter_id={new_chapter.id} chapter_number={next_chapter_number}")
                
                yield f"data: {json.dumps({'type': 'status', 'message': 'Finalizing...', 'step': 'finalizing'})}\n\n"
                
                # Build and return the final chapter response
                chapter_response = build_chapter_response(new_chapter, db)
                # Convert Pydantic model to dict with proper datetime serialization
                # Use model_dump with mode='json' to serialize datetime objects as ISO strings
                if hasattr(chapter_response, 'model_dump'):
                    # Pydantic v2
                    chapter_dict = chapter_response.model_dump(mode='json')
                else:
                    # Pydantic v1 - need to manually serialize datetime
                    chapter_dict = chapter_response.dict()
                    # Convert datetime objects to ISO format strings
                    if 'created_at' in chapter_dict and chapter_dict['created_at']:
                        chapter_dict['created_at'] = chapter_dict['created_at'].isoformat()
                    if 'completed_at' in chapter_dict and chapter_dict['completed_at']:
                        chapter_dict['completed_at'] = chapter_dict['completed_at'].isoformat()
                yield f"data: {json.dumps({'type': 'complete', 'chapter': chapter_dict})}\n\n"
                
            except Exception as e:
                logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} step=creating_new_chapter error={e}")
                db.rollback()
                yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to create new chapter: {str(e)}'})}\n\n"
                return
            
        except Exception as e:
            logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} step=outer_exception error={e}")
            # Rollback any uncommitted changes
            try:
                db.rollback()
            except Exception as rollback_error:
                logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} rollback_failed error={rollback_error}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'Unexpected error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


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
    
    # Verify chapter belongs to active branch (branch consistency check)
    if story.current_branch_id and chapter.branch_id != story.current_branch_id:
        logger.warning(f"[CHAPTER] Attempt to update chapter {chapter_id} from branch {chapter.branch_id} while active branch is {story.current_branch_id}")
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot update chapter from inactive branch. Please switch to the chapter's branch first."
        )
    
    # Update fields
    if chapter_data.title is not None:
        chapter.title = chapter_data.title
    if chapter_data.description is not None:
        chapter.description = chapter_data.description
    if chapter_data.story_so_far is not None:
        chapter.story_so_far = chapter_data.story_so_far
    if chapter_data.auto_summary is not None:
        chapter.auto_summary = chapter_data.auto_summary
    if chapter_data.plot_point is not None:
        chapter.plot_point = chapter_data.plot_point
    if chapter_data.location_name is not None:
        chapter.location_name = chapter_data.location_name
    if chapter_data.time_period is not None:
        chapter.time_period = chapter_data.time_period
    if chapter_data.scenario is not None:
        chapter.scenario = chapter_data.scenario
    
    if chapter_data.continues_from_previous is not None:
        chapter.continues_from_previous = chapter_data.continues_from_previous
    
    # Update brainstorm-related fields
    if chapter_data.chapter_plot is not None:
        chapter.chapter_plot = chapter_data.chapter_plot
    if chapter_data.brainstorm_session_id is not None:
        chapter.brainstorm_session_id = chapter_data.brainstorm_session_id
    if chapter_data.arc_phase_id is not None:
        chapter.arc_phase_id = chapter_data.arc_phase_id
    
    # Update character associations if provided
    if chapter_data.story_character_ids is not None:
        # Remove existing associations
        db.execute(
            chapter_characters.delete().where(
                chapter_characters.c.chapter_id == chapter.id
            )
        )
        
        # Validate that all story_character_ids belong to this story
        if chapter_data.story_character_ids:
            story_chars = db.query(StoryCharacter).filter(
                StoryCharacter.id.in_(chapter_data.story_character_ids),
                StoryCharacter.story_id == story_id
            ).all()
            
            if len(story_chars) != len(chapter_data.story_character_ids):
                raise HTTPException(
                    status_code=400,
                    detail="Some character IDs do not belong to this story"
                )
            
            # Create new associations
            for story_char in story_chars:
                db.execute(
                    chapter_characters.insert().values(
                        chapter_id=chapter.id,
                        story_character_id=story_char.id
                    )
                )
            logger.info(f"[CHAPTER] Updated character associations for chapter {chapter.id}")
    
    db.commit()
    db.refresh(chapter)
    
    logger.info(f"[CHAPTER] Updated chapter {chapter_id}")
    
    return build_chapter_response(chapter, db)


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
    
    # Verify chapter belongs to active branch (branch consistency check)
    if story.current_branch_id and chapter.branch_id != story.current_branch_id:
        logger.warning(f"[CHAPTER] Attempt to complete chapter {chapter_id} from branch {chapter.branch_id} while active branch is {story.current_branch_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot complete chapter from inactive branch. Please switch to the chapter's branch first."
        )
    
    # Generate chapter summary if not already done
    if not chapter.auto_summary or chapter.last_summary_scene_count < chapter.scenes_count:
        logger.info(f"[CHAPTER] Generating final summary for chapter {chapter_id}")
        await generate_chapter_summary_incremental(chapter_id, db, current_user.id)
        
        # Update story.summary now that this chapter is completed
        try:
            from ..api.summaries import update_story_summary_from_chapters
            await update_story_summary_from_chapters(story_id, db, current_user.id)
            logger.info(f"[CHAPTER] Updated story summary after completing chapter {chapter_id}")
        except Exception as e:
            # Don't fail chapter completion if story summary update fails
            logger.warning(f"[CHAPTER] Failed to update story summary after completing chapter {chapter_id}: {e}")
    
    # Mark as completed
    chapter.status = ChapterStatus.COMPLETED
    chapter.completed_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(chapter)
    
    logger.info(f"[CHAPTER] Chapter {chapter_id} completed")
    
    return build_chapter_response(chapter, db)


@router.post("/{story_id}/chapters/{chapter_id}/conclude", response_model=ChapterResponse)
async def conclude_chapter(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Conclude a chapter by generating a final scene that brings it to a natural end"""
    
    logger.info(f"[CHAPTER] Concluding chapter {chapter_id}")
    
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
    
    # Verify chapter belongs to active branch (branch consistency check)
    if story.current_branch_id and chapter.branch_id != story.current_branch_id:
        logger.warning(f"[CHAPTER] Attempt to conclude chapter {chapter_id} from branch {chapter.branch_id} while active branch is {story.current_branch_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot conclude chapter from inactive branch. Please switch to the chapter's branch first."
        )
    
    # Check that chapter has at least one scene
    if chapter.scenes_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot conclude a chapter with no scenes"
        )
    
    # Check if chapter is already completed
    if chapter.status == ChapterStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Chapter is already completed"
        )
    
    # Generate conclusion scene using special prompt
    try:
        # Get user settings
        from ..models import UserSettings
        from ..services.semantic_integration import get_context_manager_for_user
        from ..services.llm.prompts import prompt_manager
        
        user_settings_obj = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        if not user_settings_obj:
            # Create default settings if none exist
            user_settings_obj = UserSettings(user_id=current_user.id)
            # Populate with defaults from config.yaml
            user_settings_obj.populate_from_defaults()
            db.add(user_settings_obj)
            db.commit()
            db.refresh(user_settings_obj)
        
        user_settings = user_settings_obj.to_dict()
        # Add allow_nsfw from current_user
        user_settings['allow_nsfw'] = current_user.allow_nsfw
        
        context_manager = get_context_manager_for_user(user_settings, current_user.id)
        
        # Build context for scene generation (with chapter_id for character separation)
        context = await context_manager.build_scene_generation_context(
            story_id, db, "", is_variant_generation=False, chapter_id=chapter_id
        )
        
        # Format context for prompt
        from ..services.llm.service import UnifiedLLMService
        llm_service_instance = UnifiedLLMService()
        formatted_context = llm_service_instance._format_context_for_scene(context)
        logger.info(f"[CHAPTER] Formatted context length: {len(formatted_context)} characters")
        
        # Get chapter conclusion prompt from prompts.yml
        logger.info(f"[CHAPTER] Attempting to retrieve chapter_conclusion prompts from YAML")
        logger.debug(f"[CHAPTER] Template variables: chapter_number={chapter.chapter_number}, chapter_title={chapter.title}, chapter_location={chapter.location_name}, chapter_time_period={chapter.time_period}, chapter_scenario={chapter.scenario}")
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "chapter_conclusion", "chapter_conclusion",
            user_id=current_user.id,
            db=db,
            context=formatted_context,
            chapter_number=chapter.chapter_number,
            chapter_title=chapter.title or f"Chapter {chapter.chapter_number}",
            chapter_location=chapter.location_name or "Unknown",
            chapter_time_period=chapter.time_period or "Unknown",
            chapter_scenario=chapter.scenario or "None"
        )
        
        logger.info(f"[CHAPTER] Retrieved prompts - system_prompt length: {len(system_prompt) if system_prompt else 0}, user_prompt length: {len(user_prompt) if user_prompt else 0}")
        logger.debug(f"[CHAPTER] System prompt preview: {system_prompt[:200] if system_prompt else 'EMPTY'}...")
        logger.debug(f"[CHAPTER] User prompt preview: {user_prompt[:200] if user_prompt else 'EMPTY'}...")
        
        # Validate prompts are not empty
        if not system_prompt or not system_prompt.strip():
            logger.error(f"[CHAPTER] System prompt is empty for chapter_conclusion. Check if YAML file has chapter_conclusion.system defined.")
            raise HTTPException(
                status_code=500,
                detail="Failed to load system prompt for chapter conclusion"
            )
        if not user_prompt or not user_prompt.strip():
            logger.error(f"[CHAPTER] User prompt is empty for chapter_conclusion. Check if YAML file has chapter_conclusion.user defined.")
            raise HTTPException(
                status_code=500,
                detail="Failed to load user prompt for chapter conclusion"
            )
        
        max_tokens = prompt_manager.get_max_tokens("chapter_conclusion")
        
        # Generate conclusion scene using the chapter conclusion prompt
        conclusion_text = await llm_service_instance._generate(
            prompt=user_prompt,
            user_id=current_user.id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Clean scene numbers
        conclusion_text = llm_service_instance._clean_scene_numbers(conclusion_text)
        
        # Create the conclusion scene using the existing scene creation method
        from ..models import Scene, SceneVariant, StoryFlow
        
        # Get the next sequence number
        max_scene = db.query(Scene).filter(
            Scene.story_id == story_id
        ).order_by(Scene.sequence_number.desc()).first()
        
        next_sequence = (max_scene.sequence_number + 1) if max_scene else 1
        
        # Use the existing create_scene_with_variant method
        # Build a combined prompt string for the custom_prompt field
        conclusion_prompt_text = f"Chapter Conclusion Prompt:\n{user_prompt}"
        
        conclusion_scene, conclusion_variant = llm_service.create_scene_with_variant(
            db=db,
            story_id=story_id,
            sequence_number=next_sequence,
            content=conclusion_text,
            title=f"Chapter {chapter.chapter_number} Conclusion",
            custom_prompt=conclusion_prompt_text,
            generation_method="chapter_conclusion",
            branch_id=chapter.branch_id
        )
        
        # Link scene to chapter
        conclusion_scene.chapter_id = chapter_id
        db.commit()
        
        # Generate summary for the chapter before marking as completed
        if not chapter.auto_summary or chapter.last_summary_scene_count < chapter.scenes_count:
            await generate_chapter_summary_incremental(chapter_id, db, current_user.id)
            await generate_story_so_far(chapter_id, db, current_user.id)
            
            # Update story.summary now that this chapter is completed
            try:
                from ..api.summaries import update_story_summary_from_chapters
                await update_story_summary_from_chapters(story_id, db, current_user.id)
                logger.info(f"[CHAPTER] Updated story summary after concluding chapter {chapter_id}")
            except Exception as e:
                # Don't fail chapter conclusion if story summary update fails
                logger.warning(f"[CHAPTER] Failed to update story summary after concluding chapter {chapter_id}: {e}")
        
        # Mark chapter as COMPLETED after generating conclusion scene
        chapter.status = ChapterStatus.COMPLETED
        chapter.completed_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(chapter)
        
        logger.info(f"[CHAPTER] Chapter {chapter_id} concluded with scene {conclusion_scene.id}. Chapter marked as COMPLETED.")
        
    except Exception as e:
        logger.error(f"[CHAPTER] Failed to conclude chapter {chapter_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to conclude chapter: {str(e)}"
        )
    
    return build_chapter_response(chapter, db)


@router.put("/{story_id}/chapters/{chapter_id}/activate", response_model=List[ChapterResponse])
async def activate_chapter(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set a chapter as active. All other chapters in the SAME BRANCH will be marked as 
    COMPLETED (if they have scenes) or DRAFT (if empty).
    
    Note: Only affects chapters in the same branch to maintain branch isolation.
    """
    
    logger.info(f"[CHAPTER] Activating chapter {chapter_id} for story {story_id}")
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Verify chapter belongs to story
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Get all chapters for this story in the SAME BRANCH
    # This prevents cross-branch status changes
    # Note: SQLAlchemy handles None correctly in comparisons, so we can filter unconditionally
    branch_chapters_query = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.branch_id == chapter.branch_id
    )
    branch_chapters = branch_chapters_query.all()
    
    # Set all other chapters in this branch to COMPLETED (if they have scenes) or DRAFT (if empty)
    for ch in branch_chapters:
        if ch.id == chapter_id:
            # Set target chapter as ACTIVE
            ch.status = ChapterStatus.ACTIVE
            logger.info(f"[CHAPTER] Set chapter {ch.id} (Chapter {ch.chapter_number}, branch={ch.branch_id}) as ACTIVE")
        else:
            # Set other chapters based on whether they have scenes
            if ch.scenes_count > 0:
                ch.status = ChapterStatus.COMPLETED
                if not ch.completed_at:
                    ch.completed_at = datetime.now(timezone.utc)
                logger.info(f"[CHAPTER] Set chapter {ch.id} (Chapter {ch.chapter_number}, branch={ch.branch_id}) as COMPLETED (has {ch.scenes_count} scenes)")
            else:
                ch.status = ChapterStatus.DRAFT
                logger.info(f"[CHAPTER] Set chapter {ch.id} (Chapter {ch.chapter_number}, branch={ch.branch_id}) as DRAFT (no scenes)")
    
    db.commit()
    
    # Refresh all chapters and return updated list
    db.refresh(chapter)
    for ch in branch_chapters:
        db.refresh(ch)
    
    logger.info(f"[CHAPTER] Successfully activated chapter {chapter_id} in branch {chapter.branch_id}. {len(branch_chapters)} chapters updated.")
    
    return [build_chapter_response(ch, db) for ch in branch_chapters]


@router.post("/{story_id}/chapters/{chapter_id}/characters", response_model=ChapterResponse)
async def add_character_to_chapter(
    story_id: int,
    chapter_id: int,
    character_id: Optional[int] = None,
    story_character_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a character to a chapter. If character_id is provided, it will be added to story first if needed."""
    
    logger.info(f"[CHAPTER] Adding character to chapter {chapter_id}")
    
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
    
    # Verify chapter belongs to active branch (branch consistency check)
    if story.current_branch_id and chapter.branch_id != story.current_branch_id:
        logger.warning(f"[CHAPTER] Attempt to add characters to chapter {chapter_id} from branch {chapter.branch_id} while active branch is {story.current_branch_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot modify chapter from inactive branch. Please switch to the chapter's branch first."
        )
    
    # Determine which story_character_id to use
    target_story_character_id = None
    
    if story_character_id:
        # Use provided story_character_id
        story_char = db.query(StoryCharacter).filter(
            StoryCharacter.id == story_character_id,
            StoryCharacter.story_id == story_id
        ).first()
        
        if not story_char:
            raise HTTPException(
                status_code=404,
                detail="Story character not found"
            )
        target_story_character_id = story_character_id
    
    elif character_id:
        # Find or create StoryCharacter entry
        char = db.query(Character).filter(Character.id == character_id).first()
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")
        
        # Check if StoryCharacter exists
        story_char = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id,
            StoryCharacter.character_id == character_id
        ).first()
        
        if not story_char:
            # Create StoryCharacter entry
            story_char = StoryCharacter(
                story_id=story_id,
                character_id=character_id,
                is_active=True
            )
            db.add(story_char)
            db.flush()
            logger.info(f"[CHAPTER] Created StoryCharacter entry for character {character_id}")
        
        target_story_character_id = story_char.id
    else:
        raise HTTPException(
            status_code=400,
            detail="Either character_id or story_character_id must be provided"
        )
    
    # Check if association already exists
    existing = db.execute(
        chapter_characters.select().where(
            (chapter_characters.c.chapter_id == chapter_id) &
            (chapter_characters.c.story_character_id == target_story_character_id)
        )
    ).first()
    
    if existing:
        logger.info(f"[CHAPTER] Character already associated with chapter {chapter_id}")
    else:
        # Create association
        db.execute(
            chapter_characters.insert().values(
                chapter_id=chapter_id,
                story_character_id=target_story_character_id
            )
        )
        db.commit()
        logger.info(f"[CHAPTER] Added character {target_story_character_id} to chapter {chapter_id}")
    
    db.refresh(chapter)
    return build_chapter_response(chapter, db)


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
    
    # Get user settings for max tokens and context manager
    from ..models import UserSettings
    user_settings_model = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    # Convert user settings to dict format for context manager
    # UserSettings model doesn't have context_settings attribute directly,
    # need to use to_dict() method or get from stories.py helper
    from ..api.stories import get_or_create_user_settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)
    
    user_defaults = settings.user_defaults.get('context_settings', {})
    max_tokens = user_settings_model.context_max_tokens if user_settings_model else user_defaults.get('max_tokens', 4000)
    threshold_percentage = settings.chapter_context_threshold_percentage
    
    # Recalculate actual context size to ensure accuracy
    # This ensures we're counting only the current chapter's context, not previous chapters
    from ..services.semantic_integration import get_context_manager_for_user
    context_manager = get_context_manager_for_user(user_settings, current_user.id)
    
    try:
        # Calculate actual context size that would be sent to LLM for this chapter
        actual_context_size = await context_manager.calculate_actual_context_size(
            story_id, chapter_id, db
        )
        
        # Only update stored value if calculation succeeded and returned a valid value (> 0)
        # If calculation returns 0, it might be an error (should at least have base context)
        # Don't overwrite a valid stored value with 0
        if actual_context_size > 0:
            chapter.context_tokens_used = actual_context_size
            try:
                db.commit()
                logger.info(f"[CONTEXT STATUS] Recalculated context size for chapter {chapter_id}: {actual_context_size} tokens")
            except Exception as commit_error:
                # Non-blocking: if commit fails (e.g., database locked), just log and continue
                # The context size value is still accurate for this response
                logger.warning(f"[CONTEXT STATUS] Failed to persist context size update (non-critical): {commit_error}")
                db.rollback()
            current_tokens = actual_context_size
        else:
            # Calculation returned 0, which might be an error
            # Use stored value if it exists and is > 0, otherwise use 0
            if chapter.context_tokens_used and chapter.context_tokens_used > 0:
                current_tokens = chapter.context_tokens_used
                logger.warning(f"[CONTEXT STATUS] Calculation returned 0 for chapter {chapter_id}, using stored value: {current_tokens} tokens")
            else:
                # Both calculation and stored value are 0/None - might be a new chapter with no scenes yet
                current_tokens = 0
                logger.info(f"[CONTEXT STATUS] Chapter {chapter_id} has no context tokens yet (new chapter or no scenes)")
    except Exception as e:
        logger.error(f"[CONTEXT STATUS] Failed to recalculate context size for chapter {chapter_id}: {e}", exc_info=True)
        # Rollback failed transaction to reset session state (prevents PendingRollbackError cascade)
        db.rollback()
        # Refresh chapter from DB after rollback to get clean state
        db.refresh(chapter)
        # Fallback to stored value if calculation fails
        if chapter.context_tokens_used and chapter.context_tokens_used > 0:
            current_tokens = chapter.context_tokens_used
            logger.warning(f"[CONTEXT STATUS] Using stored context_tokens_used value: {current_tokens}")
        else:
            current_tokens = 0
            logger.warning(f"[CONTEXT STATUS] No valid stored value, using 0")
    
    # Calculate percentage
    percentage_used = (current_tokens / max_tokens) * 100 if max_tokens > 0 else 0
    
    # Determine if new chapter should be created
    should_create_new = False
    reason = None
    
    if percentage_used >= threshold_percentage:
        should_create_new = True
        reason = "context_limit"
    
    # TODO: Add time-based detection in future
    
    # Calculate scenes_count dynamically from active StoryFlow instead of using stored value
    from ..services.llm.service import UnifiedLLMService
    llm_service = UnifiedLLMService()
    active_scenes_count = llm_service.get_active_scene_count(db, story_id, chapter_id, branch_id=chapter.branch_id)
    
    return ChapterContextStatus(
        chapter_id=chapter_id,
        current_tokens=current_tokens,
        max_tokens=max_tokens,
        percentage_used=round(percentage_used, 2),
        should_create_new_chapter=should_create_new,
        reason=reason,
        scenes_count=active_scenes_count
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
    
    Note: Filters by branch_id to ensure only chapters from the same branch are included.
    """
    op_start = time.perf_counter()
    trace_id = f"chap-sum-{uuid.uuid4()}"
    status = "error"
    summary_text = ""
    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            logger.warning(f"[CHAPTER:SUMMARY:SKIP] trace_id={trace_id} chapter_id={chapter_id} reason=not_found")
            return ""
        
        logger.info(f"[CHAPTER:SUMMARY:START] trace_id={trace_id} chapter_id={chapter_id} story_id={chapter.story_id} branch_id={chapter.branch_id}")
        
        # Get ALL PREVIOUS chapters' summaries for context (filtered by branch_id)
        # This ensures we only get chapters from the same branch to avoid cross-branch pollution
        previous_chapters_query = db.query(Chapter).filter(
            Chapter.story_id == chapter.story_id,
            Chapter.chapter_number < chapter.chapter_number
        )
        # Filter by branch_id if the chapter has one
        if chapter.branch_id:
            previous_chapters_query = previous_chapters_query.filter(Chapter.branch_id == chapter.branch_id)
        previous_chapters = previous_chapters_query.order_by(Chapter.chapter_number).all()
        
        previous_summaries = []
        for ch in previous_chapters:
            if ch.auto_summary:
                previous_summaries.append(f"Chapter {ch.chapter_number} ({ch.title or 'Untitled'}): {ch.auto_summary}")
        
        # Get all scenes in THIS chapter with their active variants
        from .stories import SceneVariantServiceAdapter
        from ..models import StoryFlow
        
        variant_service = SceneVariantServiceAdapter(db)
        # Filter scenes by branch_id to avoid cross-branch contamination
        scene_query = db.query(Scene).filter(
            Scene.chapter_id == chapter_id
        )
        if chapter.branch_id:
            scene_query = scene_query.filter(Scene.branch_id == chapter.branch_id)
        scenes = scene_query.order_by(Scene.sequence_number).all()
        
        if not scenes:
            logger.warning(f"[CHAPTER:SUMMARY:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_scenes")
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
            logger.warning(f"[CHAPTER:SUMMARY:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_active_variants")
            return "No content available to summarize."
        
        # Prepare context for LLM with previous chapters for continuity
        combined_content = "\n\n".join(scene_contents)
        
        # Build context section from previous chapters
        context_section = ""
        if previous_summaries:
            context_section = f"Previous Chapters (for context):\n{chr(10).join(previous_summaries)}\n\n"
        
        # Get user prompt from prompts.yml with template variables
        prompt = prompt_manager.get_prompt(
            "chapter_summary", "user",
            user_id=user_id, db=db,
            context_section=context_section,
            chapter_number=chapter.chapter_number,
            chapter_title=chapter.title or 'Untitled',
            scenes_content=combined_content
        )
        if not prompt:
            # Fallback if template not found
            prompt = f"{context_section}Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}\n\nScenes:\n{combined_content}\n\nSummarize this chapter factually."
        
        # Get user settings
        from ..models import UserSettings
        user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        user_settings = user_settings_obj.to_dict() if user_settings_obj else None
        
        # Add allow_nsfw from user to ensure NSFW filter is applied correctly
        if user_settings is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user_settings['allow_nsfw'] = user.allow_nsfw
        
        # Get system prompt from prompts.yml
        system_prompt = prompt_manager.get_prompt("chapter_summary", "system", user_id=user_id, db=db)
        if not system_prompt:
            # Fallback if template not found
            system_prompt = "You are a helpful assistant that creates concise narrative summaries."
        
        # Generate summary - check if user wants to use extraction LLM
        llm_start = time.perf_counter()
        use_extraction_llm = user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False) if user_settings else False
        extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False) if user_settings else False
        
        if use_extraction_llm and extraction_enabled:
            try:
                from ..services.llm.extraction_service import ExtractionLLMService
                logger.info(f"[CHAPTER:SUMMARY] Using extraction LLM for chapter summary (chapter_id={chapter_id})")
                
                ext_settings = user_settings.get('extraction_model_settings', {})
                extraction_service = ExtractionLLMService(
                    url=ext_settings.get('url', 'http://localhost:1234/v1'),
                    model=ext_settings.get('model_name', 'qwen2.5-3b-instruct'),
                    api_key=ext_settings.get('api_key', ''),
                    temperature=ext_settings.get('temperature', 0.3),
                    max_tokens=ext_settings.get('max_tokens', 1000)
                )
                
                # Use extraction LLM for chapter summary
                from litellm import acompletion
                params = extraction_service._get_generation_params(max_tokens=400)
                response = await acompletion(
                    **params,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    timeout=extraction_service.timeout.total * 2
                )
                summary = response.choices[0].message.content.strip()
                logger.info(f"[CHAPTER:SUMMARY] Successfully generated with extraction LLM (chapter_id={chapter_id}, length={len(summary)})")
            except Exception as e:
                logger.warning(f"[CHAPTER:SUMMARY] Extraction LLM failed, falling back to main LLM: {e}")
                # Fall through to main LLM
                summary = await llm_service.generate(
                    prompt=prompt,
                    user_id=user_id,
                    user_settings=user_settings,
                    system_prompt=system_prompt,
                    max_tokens=400
                )
        else:
            # Use main LLM (default behavior)
            logger.info(f"[CHAPTER:SUMMARY] Using main LLM for chapter summary (chapter_id={chapter_id})")
            summary = await llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=400  # Enough for a good summary
            )
        logger.info(f"[CHAPTER:SUMMARY:LLM] trace_id={trace_id} duration_ms={(time.perf_counter() - llm_start) * 1000:.2f}")
        
        # Update chapter's auto_summary (just this chapter's content)
        chapter.auto_summary = summary
        # Store the max sequence number of scenes that were summarized (not the count)
        if scenes:
            chapter.last_summary_scene_count = max(s.sequence_number for s in scenes)
        else:
            chapter.last_summary_scene_count = 0
        db.commit()
        summary_text = summary
        
        status = "success"
        logger.info(f"[CHAPTER] Generated summary for chapter {chapter_id}: {len(summary)} chars trace_id={trace_id}")
        
        return summary
    except Exception as e:
        logger.error(f"[CHAPTER:SUMMARY:ERROR] trace_id={trace_id} chapter_id={chapter_id} error={e}")
        return ""
    finally:
        duration_ms = (time.perf_counter() - op_start) * 1000
        if duration_ms > 15000:
            logger.error(f"[CHAPTER:SUMMARY:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(summary_text)}")
        elif duration_ms > 5000:
            logger.warning(f"[CHAPTER:SUMMARY:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(summary_text)}")
        else:
            logger.info(f"[CHAPTER:SUMMARY:DONE] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(summary_text)}")


def combine_chapter_batches(chapter_id: int, db: Session) -> Optional[str]:
    """
    Get the latest chapter summary from batches.
    
    Each batch stores the complete cumulative summary up to that point
    (the LLM combines existing summary + new scenes). So we just need
    the latest batch's summary, not a concatenation of all batches.
    
    This preserves the batch rollback feature - if a scene is deleted,
    the affected batch is invalidated, and the previous batch (which has
    the complete summary up to that point) becomes the latest.
    
    Returns None if no batches exist.
    """
    # Get the latest batch (highest end_scene_sequence)
    latest_batch = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).order_by(ChapterSummaryBatch.end_scene_sequence.desc()).first()
    
    if not latest_batch:
        return None
    
    return latest_batch.summary


def update_chapter_summary_from_batches(chapter_id: int, db: Session) -> None:
    """
    Update chapter.auto_summary and last_summary_scene_count from current batches.
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return
    
    batches = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).order_by(ChapterSummaryBatch.start_scene_sequence).all()
    
    if batches:
        chapter.auto_summary = combine_chapter_batches(chapter_id, db)
        chapter.last_summary_scene_count = max(b.end_scene_sequence for b in batches)
    else:
        chapter.auto_summary = None
        chapter.last_summary_scene_count = 0
    
    db.commit()


def invalidate_chapter_batches_for_scene(scene_id: int, db: Session) -> None:
    """
    Invalidate chapter summary batches if scene was part of summarized range.
    This should be called when a scene's content is modified.
    """
    from ..models import Scene
    
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene or not scene.chapter_id:
        return
    
    chapter = db.query(Chapter).filter(Chapter.id == scene.chapter_id).first()
    if not chapter:
        return
    
    # Find batches that contain this scene
    affected_batches = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter.id,
        ChapterSummaryBatch.start_scene_sequence <= scene.sequence_number,
        ChapterSummaryBatch.end_scene_sequence >= scene.sequence_number
    ).all()
    
    if affected_batches:
        # Delete affected batches
        for batch in affected_batches:
            db.delete(batch)
        
        logger.info(f"[INVALIDATE] Invalidated {len(affected_batches)} batch(es) for chapter {chapter.id} due to scene {scene_id} modification")
        
        # Recalculate summary from remaining batches
        update_chapter_summary_from_batches(chapter.id, db)


async def generate_chapter_summary_incremental(chapter_id: int, db: Session, user_id: int) -> str:
    """
    Generate or extend chapter summary incrementally.
    
    Instead of re-summarizing all scenes, this:
    1. Takes existing summary (if exists)
    2. Gets only NEW scenes since last summary
    3. Asks LLM to create cohesive summary combining existing + new
    4. Includes rich context (story_so_far, characters, entity states, etc.)
    
    This is much more efficient and scalable for long chapters.
    """
    op_start = time.perf_counter()
    trace_id = f"chap-sum-inc-{uuid.uuid4()}"
    status = "error"
    combined_summary = ""
    
    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            logger.warning(f"[CHAPTER:SUMMARY:INC:SKIP] trace_id={trace_id} chapter_id={chapter_id} reason=not_found")
            return ""
        
        logger.info(f"[CHAPTER:SUMMARY:INC:START] trace_id={trace_id} chapter_id={chapter_id} story_id={chapter.story_id} branch_id={chapter.branch_id}")
        
        # Get scenes since last summary
        last_summary_count = chapter.last_summary_scene_count or 0
        # Filter scenes by branch_id to avoid cross-branch contamination
        new_scene_query = db.query(Scene).filter(
            Scene.chapter_id == chapter_id,
            Scene.sequence_number > last_summary_count
        )
        if chapter.branch_id:
            new_scene_query = new_scene_query.filter(Scene.branch_id == chapter.branch_id)
        new_scenes = new_scene_query.order_by(Scene.sequence_number).all()
        
        if not new_scenes:
            logger.info(f"[CHAPTER:SUMMARY:INC:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_new_scenes")
            status = "no_new_scenes"
            return chapter.auto_summary or ""
        
        # Build scene content from active variants (only NEW scenes)
        from .stories import SceneVariantServiceAdapter
        from ..models import StoryFlow
        
        scene_contents = []
        for scene in new_scenes:
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            ).first()
            
            if flow and flow.scene_variant:
                scene_contents.append(f"Scene {scene.sequence_number}: {flow.scene_variant.content}")
        
        if not scene_contents:
            logger.info(f"[CHAPTER:SUMMARY:INC:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_active_variants")
            status = "no_active_variants"
            return chapter.auto_summary or ""
        
        new_scenes_text = "\n\n".join(scene_contents)
        
        # Get previous chapter summary for narrative continuity (filtered by branch_id to avoid cross-branch pollution)
        previous_chapter_text = ""
        if chapter.chapter_number > 1:
            previous_chapter_query = db.query(Chapter).filter(
                Chapter.story_id == chapter.story_id,
                Chapter.chapter_number == chapter.chapter_number - 1,
                Chapter.auto_summary.isnot(None)
            )
            # Filter by branch_id if the chapter has one
            if chapter.branch_id:
                previous_chapter_query = previous_chapter_query.filter(Chapter.branch_id == chapter.branch_id)
            previous_chapter = previous_chapter_query.first()
            if previous_chapter and previous_chapter.auto_summary:
                previous_chapter_text = f"\nPrevious Chapter Summary:\n{previous_chapter.auto_summary}\n"
        
        # Build prompt based on whether we have existing summary
        existing_summary = chapter.auto_summary
        
        if existing_summary:
            # Incremental update: extend existing summary using template
            prompt = prompt_manager.get_prompt(
                "chapter_summary_incremental", "user",
                user_id=user_id, db=db,
                previous_chapter_text=previous_chapter_text,
                last_summary_count=last_summary_count,
                existing_summary=existing_summary,
                new_scenes_start=last_summary_count + 1,
                new_scenes_end=chapter.scenes_count,
                new_scenes_text=new_scenes_text
            )
            template_key = "chapter_summary_incremental"
        else:
            # First summary: create from scratch using template
            prompt = prompt_manager.get_prompt(
                "chapter_summary_initial", "user",
                user_id=user_id, db=db,
                previous_chapter_text=previous_chapter_text,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title or 'Untitled',
                new_scenes_text=new_scenes_text
            )
            template_key = "chapter_summary_initial"
        
        # Fallback if template not found
        if not prompt:
            prompt = f"{previous_chapter_text}Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}\n\nScenes:\n{new_scenes_text}\n\nSummarize factually."
        
        # Get user settings
        from ..models import UserSettings
        user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        user_settings = user_settings_obj.to_dict() if user_settings_obj else None
        
        if user_settings is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user_settings['allow_nsfw'] = user.allow_nsfw
        
        # Get system prompt from prompts.yml using the appropriate template
        system_prompt = prompt_manager.get_prompt(template_key, "system", user_id=user_id, db=db)
        if not system_prompt:
            # Fallback if template not found
            system_prompt = "You are a story state tracker. Extract facts, not prose."
        
        # Generate summary for this batch - check if user wants to use extraction LLM
        llm_start = time.perf_counter()
        use_extraction_llm = user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False) if user_settings else False
        extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False) if user_settings else False
        
        if use_extraction_llm and extraction_enabled:
            try:
                from ..services.llm.extraction_service import ExtractionLLMService
                logger.info(f"[CHAPTER:SUMMARY:INC] Using extraction LLM for incremental chapter summary (chapter_id={chapter_id})")
                
                ext_settings = user_settings.get('extraction_model_settings', {})
                extraction_service = ExtractionLLMService(
                    url=ext_settings.get('url', 'http://localhost:1234/v1'),
                    model=ext_settings.get('model_name', 'qwen2.5-3b-instruct'),
                    api_key=ext_settings.get('api_key', ''),
                    temperature=ext_settings.get('temperature', 0.3),
                    max_tokens=ext_settings.get('max_tokens', 1000)
                )
                
                # Use extraction LLM for incremental chapter summary
                from litellm import acompletion
                params = extraction_service._get_generation_params(max_tokens=500)
                response = await acompletion(
                    **params,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    timeout=extraction_service.timeout.total * 2
                )
                batch_summary = response.choices[0].message.content.strip()
                logger.info(f"[CHAPTER:SUMMARY:INC] Successfully generated with extraction LLM (chapter_id={chapter_id}, length={len(batch_summary)})")
            except Exception as e:
                logger.warning(f"[CHAPTER:SUMMARY:INC] Extraction LLM failed, falling back to main LLM: {e}")
                # Fall through to main LLM
                batch_summary = await llm_service.generate(
                    prompt=prompt,
                    user_id=user_id,
                    user_settings=user_settings,
                    system_prompt=system_prompt,
                    max_tokens=500
                )
        else:
            # Use main LLM (default behavior)
            logger.info(f"[CHAPTER:SUMMARY:INC] Using main LLM for incremental chapter summary (chapter_id={chapter_id})")
            batch_summary = await llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=500  # Slightly more for incremental updates
            )
        logger.info(f"[CHAPTER:SUMMARY:INC:LLM] trace_id={trace_id} duration_ms={(time.perf_counter() - llm_start) * 1000:.2f}")
        
        # Determine scene range for this batch
        batch_start = last_summary_count + 1
        batch_end = max(s.sequence_number for s in new_scenes)  # Use actual max sequence number, not count
        
        # Store this batch
        batch = ChapterSummaryBatch(
            chapter_id=chapter_id,
            start_scene_sequence=batch_start,
            end_scene_sequence=batch_end,
            summary=batch_summary
        )
        db.add(batch)
        db.flush()  # Flush to get batch ID
        
        # Update chapter's auto_summary from all batches
        update_chapter_summary_from_batches(chapter_id, db)
        
        # Get batch count for logging
        all_batches = db.query(ChapterSummaryBatch).filter(
            ChapterSummaryBatch.chapter_id == chapter_id
        ).all()
        
        combined_summary = chapter.auto_summary or ""
        
        logger.info(f"[CHAPTER] {'Extended' if existing_summary else 'Created'} summary for chapter {chapter_id}: {len(batch_summary)} chars (scenes {batch_start}-{batch_end}), total batches: {len(all_batches)}, trace_id={trace_id}")
        status = "success"
        return combined_summary
    
    except Exception as e:
        logger.error(f"[CHAPTER:SUMMARY:INC:ERROR] trace_id={trace_id} chapter_id={chapter_id} error={e}")
        status = "error"
        raise
    
    finally:
        duration_ms = (time.perf_counter() - op_start) * 1000
        if duration_ms > 15000:
            logger.error(f"[CHAPTER:SUMMARY:INC:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(combined_summary)}")
        elif duration_ms > 5000:
            logger.warning(f"[CHAPTER:SUMMARY:INC:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(combined_summary)}")
        else:
            logger.info(f"[CHAPTER:SUMMARY:INC:DONE] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(combined_summary)}")
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover
    # noqa
    # pragma: no cover


async def generate_story_so_far(chapter_id: int, db: Session, user_id: int) -> Optional[str]:
    """
    Generate "Story So Far" for a chapter by combining summaries of ALL PREVIOUS chapters.
    Does NOT include the current chapter's summary.
    
    Returns None if there are no previous chapters with summaries.
    This is used when creating a new chapter to provide context from all previous chapters.
    
    Note: Filters by branch_id to ensure only chapters from the same branch are included.
    """
    
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return None
    
    story_id = chapter.story_id
    
    # Get all previous chapters (completed or active, in order)
    # Filter by branch_id to avoid cross-branch context pollution
    previous_chapters_query = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.chapter_number < chapter.chapter_number
    )
    # Filter by branch_id if the chapter has one
    if chapter.branch_id:
        previous_chapters_query = previous_chapters_query.filter(Chapter.branch_id == chapter.branch_id)
    previous_chapters = previous_chapters_query.order_by(Chapter.chapter_number).all()
    
    # Build the story so far from previous chapter summaries ONLY
    previous_summaries = []
    for prev_ch in previous_chapters:
        if prev_ch.auto_summary:
            previous_summaries.append(f"Chapter {prev_ch.chapter_number} ({prev_ch.title or 'Untitled'}): {prev_ch.auto_summary}")
    
    if not previous_summaries:
        # No previous chapters with summaries - return None instead of placeholder
        logger.info(f"[CHAPTER] No previous chapter summaries available for chapter {chapter_id}")
        chapter.story_so_far = None
        db.commit()
        return None
    
    # Combine previous chapter summaries
    combined_story = "=== Previous Chapters ===\n" + "\n\n".join(previous_summaries)
    
    # Get story details for genre-aware summary
    story = db.query(Story).filter(Story.id == story_id).first()
    genre = story.genre if story else "fiction"
    content_rating = story.content_rating if story and hasattr(story, 'content_rating') else "general"
    tone = story.tone if story else "neutral"
    
    # Get user prompt from prompts.yml with template variables
    prompt = prompt_manager.get_prompt(
        "story_so_far", "user",
        user_id=user_id, db=db,
        combined_chapters=combined_story,
        genre=genre or "fiction",
        content_rating=content_rating or "general",
        tone=tone or "neutral"
    )
    if not prompt:
        # Fallback if template not found
        prompt = f"{combined_story}\n\nConsolidate into a factual story summary for this {genre} story."
    
    # Get user settings
    from ..models import UserSettings
    user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    user_settings = user_settings_obj.to_dict() if user_settings_obj else None
    
    # Add allow_nsfw from user to ensure NSFW filter is applied correctly
    if user_settings is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_settings['allow_nsfw'] = user.allow_nsfw
    
    # Get system prompt from prompts.yml
    system_prompt = prompt_manager.get_prompt("story_so_far", "system", user_id=user_id, db=db)
    if not system_prompt:
        # Fallback if template not found
        system_prompt = "You are a story state tracker. Consolidate chapter facts into a single state document."
    
    # Generate story so far - check if user wants to use extraction LLM
    use_extraction_llm = user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False) if user_settings else False
    extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False) if user_settings else False
    
    if use_extraction_llm and extraction_enabled:
        try:
            from ..services.llm.extraction_service import ExtractionLLMService
            logger.info(f"[CHAPTER:STORY_SO_FAR] Using extraction LLM for story so far (chapter_id={chapter_id})")
            
            ext_settings = user_settings.get('extraction_model_settings', {})
            extraction_service = ExtractionLLMService(
                url=ext_settings.get('url', 'http://localhost:1234/v1'),
                model=ext_settings.get('model_name', 'qwen2.5-3b-instruct'),
                api_key=ext_settings.get('api_key', ''),
                temperature=ext_settings.get('temperature', 0.3),
                max_tokens=ext_settings.get('max_tokens', 1000)
            )
            
            # Use extraction LLM for story so far
            from litellm import acompletion
            params = extraction_service._get_generation_params(max_tokens=600)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=extraction_service.timeout.total * 2
            )
            story_so_far = response.choices[0].message.content.strip()
            logger.info(f"[CHAPTER:STORY_SO_FAR] Successfully generated with extraction LLM (chapter_id={chapter_id}, length={len(story_so_far)})")
        except Exception as e:
            logger.warning(f"[CHAPTER:STORY_SO_FAR] Extraction LLM failed, falling back to main LLM: {e}")
            # Fall through to main LLM
            story_so_far = await llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=600
            )
    else:
        # Use main LLM (default behavior)
        logger.info(f"[CHAPTER:STORY_SO_FAR] Using main LLM for story so far (chapter_id={chapter_id})")
        story_so_far = await llm_service.generate(
            prompt=prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=600
        )
    
    # Update chapter's story_so_far
    chapter.story_so_far = story_so_far
    db.commit()
    
    logger.info(f"[CHAPTER] Generated story_so_far for chapter {chapter_id} using {len(previous_chapters)} previous chapters: {len(story_so_far)} chars")
    
    return story_so_far


@router.post("/{story_id}/chapters/{chapter_id}/regenerate-story-so-far")
async def regenerate_story_so_far_endpoint(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Regenerate only the story_so_far for a chapter without touching the chapter summary.
    This is useful when previous chapters are modified and user wants to update story_so_far.
    """
    
    logger.info(f"[CHAPTER] Regenerating story_so_far for chapter {chapter_id}")
    
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
    
    # Generate story_so_far (only previous chapters, not current)
    story_so_far = await generate_story_so_far(chapter_id, db, current_user.id)
    
    return {
        "message": "Story so far regenerated successfully",
        "story_so_far": story_so_far
    }


@router.delete("/{story_id}/chapters/{chapter_id}/scenes")
async def delete_chapter_content(
    story_id: int,
    chapter_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete all scenes in a chapter (for structured mode - rewrite chapter)"""
    import time
    import uuid
    
    op_start = time.perf_counter()
    trace_id = f"chapter-content-del-{uuid.uuid4()}"
    logger.info(f"[CHAPTER:CONTENT:DELETE:START] trace_id={trace_id} story_id={story_id} chapter_id={chapter_id} user_id={current_user.id}")
    
    # Phase 1: Verify story ownership
    phase_start = time.perf_counter()
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=query_story duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    phase_start = time.perf_counter()
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=query_chapter duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Verify chapter belongs to active branch (branch consistency check)
    if story.current_branch_id and chapter.branch_id != story.current_branch_id:
        logger.warning(f"[CHAPTER:CONTENT:DELETE:ERROR] trace_id={trace_id} branch_mismatch chapter_branch={chapter.branch_id} active_branch={story.current_branch_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete scenes from chapter in inactive branch. Please switch to the chapter's branch first."
        )
    
    # Phase 2: Query scenes to delete
    phase_start = time.perf_counter()
    scene_query = db.query(Scene).filter(Scene.chapter_id == chapter_id)
    if chapter.branch_id:
        scene_query = scene_query.filter(Scene.branch_id == chapter.branch_id)
    scenes = scene_query.all()
    scene_count = len(scenes)
    logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=query_scenes duration_ms={(time.perf_counter()-phase_start)*1000:.2f} scenes_found={scene_count}")
    
    # Collect scene IDs and sequence numbers for background cleanup BEFORE deleting
    scene_ids_to_cleanup = [scene.id for scene in scenes]
    min_deleted_seq = min(scene.sequence_number for scene in scenes) if scenes else 1
    max_deleted_seq = max(scene.sequence_number for scene in scenes) if scenes else 1
    logger.info(f"[CHAPTER:CONTENT:DELETE:PREP] trace_id={trace_id} scene_ids={scene_ids_to_cleanup[:10]}{'...' if len(scene_ids_to_cleanup) > 10 else ''} seq_range={min_deleted_seq}-{max_deleted_seq}")
    
    # Phase 2.5: Clear leads_to_scene_id references in SceneChoice before deleting scenes
    # This prevents foreign key constraint violations
    if scene_ids_to_cleanup:
        from ..models import SceneChoice
        phase_start = time.perf_counter()
        leads_to_cleared = db.query(SceneChoice).filter(
            SceneChoice.leads_to_scene_id.in_(scene_ids_to_cleanup)
        ).update({SceneChoice.leads_to_scene_id: None}, synchronize_session='fetch')
        logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=clear_leads_to_refs duration_ms={(time.perf_counter()-phase_start)*1000:.2f} refs_cleared={leads_to_cleared}")
    
    # Phase 3: Delete scenes (CASCADE will handle related database records)
    phase_start = time.perf_counter()
    total_scenes = len(scenes)
    batch_log_interval = max(1, total_scenes // 10) if total_scenes > 10 else 1
    
    logger.info(f"[CHAPTER:CONTENT:DELETE:SCENE_LOOP:START] trace_id={trace_id} total_scenes={total_scenes}")
    for i, scene in enumerate(scenes):
        scene_start = time.perf_counter()
        db.delete(scene)
        scene_duration = (time.perf_counter() - scene_start) * 1000
        
        if (i + 1) % batch_log_interval == 0 or scene_duration > 100:
            elapsed_ms = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[CHAPTER:CONTENT:DELETE:PROGRESS] trace_id={trace_id} progress={i+1}/{total_scenes} elapsed_ms={elapsed_ms:.2f} last_scene_ms={scene_duration:.2f}")
    
    loop_duration = (time.perf_counter() - phase_start) * 1000
    logger.info(f"[CHAPTER:CONTENT:DELETE:SCENE_LOOP:END] trace_id={trace_id} scenes_deleted={total_scenes} duration_ms={loop_duration:.2f}")
    
    # Phase 4: Recalculate scenes_count from active StoryFlow (should be 0 after deletion)
    phase_start = time.perf_counter()
    chapter.scenes_count = llm_service.get_active_scene_count(db, story_id, chapter_id, branch_id=chapter.branch_id)
    logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=recalc_scene_count duration_ms={(time.perf_counter()-phase_start)*1000:.2f} new_count={chapter.scenes_count}")
    
    # Phase 5: Delete all summary batches for this chapter
    phase_start = time.perf_counter()
    batches_deleted = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).delete()
    logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=delete_batches duration_ms={(time.perf_counter()-phase_start)*1000:.2f} batches_deleted={batches_deleted}")
    
    # Delete all plot progress batches for this chapter
    from ..models import ChapterPlotProgressBatch
    plot_batches_deleted = db.query(ChapterPlotProgressBatch).filter(
        ChapterPlotProgressBatch.chapter_id == chapter_id
    ).delete()
    logger.info(f"[CHAPTER:CONTENT:DELETE:PHASE] trace_id={trace_id} phase=delete_plot_batches plot_batches_deleted={plot_batches_deleted}")
    
    # Reset chapter metrics
    chapter.context_tokens_used = 0
    chapter.auto_summary = None
    chapter.last_summary_scene_count = 0
    chapter.last_extraction_scene_count = 0
    chapter.last_plot_extraction_scene_count = 0
    chapter.plot_progress = None
    chapter.status = ChapterStatus.ACTIVE
    
    # Phase 6: Commit
    phase_start = time.perf_counter()
    logger.info(f"[CHAPTER:CONTENT:DELETE:COMMIT:START] trace_id={trace_id}")
    db.commit()
    commit_duration = (time.perf_counter() - phase_start) * 1000
    logger.info(f"[CHAPTER:CONTENT:DELETE:COMMIT:END] trace_id={trace_id} commit_duration_ms={commit_duration:.2f}")
    
    # Schedule background cleanup tasks (don't block response)
    if scene_ids_to_cleanup:
        # 1. Semantic cleanup (embeddings, character moments, plot events)
        logger.info(f"[CHAPTER:CONTENT:DELETE:BG_SCHEDULE] trace_id={trace_id} task=semantic_cleanup scene_count={len(scene_ids_to_cleanup)}")
        background_tasks.add_task(
            cleanup_semantic_data_in_background,
            scene_ids=scene_ids_to_cleanup,
            story_id=story_id
        )
        
        # 2. NPC tracking restoration
        from .stories import restore_npc_tracking_in_background
        logger.info(f"[CHAPTER:CONTENT:DELETE:BG_SCHEDULE] trace_id={trace_id} task=npc_tracking")
        background_tasks.add_task(
            restore_npc_tracking_in_background,
            story_id=story_id,
            sequence_number=min_deleted_seq,
            branch_id=chapter.branch_id
        )
        
        # 3. Entity states restoration
        from .stories import restore_entity_states_in_background, get_or_create_user_settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        logger.info(f"[CHAPTER:CONTENT:DELETE:BG_SCHEDULE] trace_id={trace_id} task=entity_states")
        background_tasks.add_task(
            restore_entity_states_in_background,
            story_id=story_id,
            sequence_number=min_deleted_seq,
            min_deleted_seq=min_deleted_seq,
            max_deleted_seq=max_deleted_seq,
            user_id=current_user.id,
            user_settings=user_settings,
            branch_id=chapter.branch_id
        )
    
    total_duration = (time.perf_counter() - op_start) * 1000
    if total_duration > 10000:
        logger.warning(f"[CHAPTER:CONTENT:DELETE:SLOW] trace_id={trace_id} duration_ms={total_duration:.2f} scenes_deleted={scene_count}")
    else:
        logger.info(f"[CHAPTER:CONTENT:DELETE:END] trace_id={trace_id} duration_ms={total_duration:.2f} scenes_deleted={scene_count}")
    
    return {
        "message": "Chapter content deleted successfully",
        "scenes_deleted": scene_count
    }


@router.delete("/{story_id}/chapters/{chapter_id}")
async def delete_chapter(
    story_id: int,
    chapter_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an entire chapter and all its content.
    
    WARNING: This permanently deletes:
    - The chapter itself
    - All scenes in the chapter
    - All scene variants
    - Chapter summaries
    - Chapter-character associations
    - Semantic embeddings
    
    Use with caution!
    """
    import time
    import uuid
    
    op_start = time.perf_counter()
    trace_id = f"chapter-del-{uuid.uuid4()}"
    logger.info(f"[CHAPTER:DELETE:START] trace_id={trace_id} story_id={story_id} chapter_id={chapter_id} user_id={current_user.id}")
    
    # Phase 1: Verify story ownership
    phase_start = time.perf_counter()
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=query_story duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    if not story:
        logger.error(f"[CHAPTER:DELETE:ERROR] trace_id={trace_id} story_id={story_id} chapter_id={chapter_id} error=story_not_found")
        raise HTTPException(status_code=404, detail="Story not found")
    
    phase_start = time.perf_counter()
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=query_chapter duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # Verify chapter belongs to active branch (branch consistency check)
    if story.current_branch_id and chapter.branch_id != story.current_branch_id:
        logger.warning(f"[CHAPTER:DELETE:ERROR] trace_id={trace_id} branch_mismatch chapter_branch={chapter.branch_id} active_branch={story.current_branch_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete chapter from inactive branch. Please switch to the chapter's branch first."
        )
    
    # Prevent deletion of the only chapter
    chapter_count = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.branch_id == chapter.branch_id
    ).count()
    
    if chapter_count <= 1:
        logger.warning(f"[CHAPTER:DELETE:ERROR] trace_id={trace_id} cannot_delete_only_chapter")
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the only chapter in the story. Stories must have at least one chapter."
        )
    
    # Store chapter info for logging
    chapter_number = chapter.chapter_number
    chapter_title = chapter.title
    logger.info(f"[CHAPTER:DELETE:CONTEXT] trace_id={trace_id} chapter_number={chapter_number} chapter_title={chapter_title} branch_id={chapter.branch_id}")
    
    # Phase 2: Get all scenes for background cleanup (filter by branch_id)
    phase_start = time.perf_counter()
    scene_query = db.query(Scene).filter(Scene.chapter_id == chapter_id)
    if chapter.branch_id:
        scene_query = scene_query.filter(Scene.branch_id == chapter.branch_id)
    scenes = scene_query.all()
    scene_ids_to_cleanup = [scene.id for scene in scenes]
    min_deleted_seq = min(scene.sequence_number for scene in scenes) if scenes else 1
    max_deleted_seq = max(scene.sequence_number for scene in scenes) if scenes else 1
    scene_count = len(scenes)
    logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=query_scenes duration_ms={(time.perf_counter()-phase_start)*1000:.2f} scenes_found={scene_count}")
    logger.info(f"[CHAPTER:DELETE:PREP] trace_id={trace_id} scene_ids={scene_ids_to_cleanup[:10]}{'...' if len(scene_ids_to_cleanup) > 10 else ''} seq_range={min_deleted_seq}-{max_deleted_seq}")
    
    # Phase 3: Delete chapter-character associations
    phase_start = time.perf_counter()
    db.execute(
        chapter_characters.delete().where(
            chapter_characters.c.chapter_id == chapter_id
        )
    )
    logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=delete_chapter_characters duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    # Phase 4: Delete all summary batches for this chapter
    phase_start = time.perf_counter()
    batches_deleted = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).delete()
    logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=delete_batches duration_ms={(time.perf_counter()-phase_start)*1000:.2f} batches_deleted={batches_deleted}")
    
    # Phase 4.5: Clear leads_to_scene_id references in SceneChoice before deleting scenes
    # This prevents foreign key constraint violations
    if scene_ids_to_cleanup:
        from ..models import SceneChoice
        phase_start = time.perf_counter()
        leads_to_cleared = db.query(SceneChoice).filter(
            SceneChoice.leads_to_scene_id.in_(scene_ids_to_cleanup)
        ).update({SceneChoice.leads_to_scene_id: None}, synchronize_session='fetch')
        logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=clear_leads_to_refs duration_ms={(time.perf_counter()-phase_start)*1000:.2f} refs_cleared={leads_to_cleared}")
    
    # Phase 5: Delete all scenes in this chapter (CASCADE will handle variants, story flow, etc.)
    phase_start = time.perf_counter()
    total_scenes = len(scenes)
    batch_log_interval = max(1, total_scenes // 10) if total_scenes > 10 else 1
    
    logger.info(f"[CHAPTER:DELETE:SCENE_LOOP:START] trace_id={trace_id} total_scenes={total_scenes}")
    for i, scene in enumerate(scenes):
        scene_start = time.perf_counter()
        db.delete(scene)
        scene_duration = (time.perf_counter() - scene_start) * 1000
        
        if (i + 1) % batch_log_interval == 0 or scene_duration > 100:
            elapsed_ms = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[CHAPTER:DELETE:PROGRESS] trace_id={trace_id} progress={i+1}/{total_scenes} elapsed_ms={elapsed_ms:.2f} last_scene_ms={scene_duration:.2f}")
    
    loop_duration = (time.perf_counter() - phase_start) * 1000
    logger.info(f"[CHAPTER:DELETE:SCENE_LOOP:END] trace_id={trace_id} scenes_deleted={total_scenes} duration_ms={loop_duration:.2f}")
    
    # Phase 6: Delete the chapter itself
    phase_start = time.perf_counter()
    db.delete(chapter)
    logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=delete_chapter duration_ms={(time.perf_counter()-phase_start)*1000:.2f}")
    
    # If this was the active chapter, we need to activate another one
    if chapter.status == ChapterStatus.ACTIVE:
        phase_start = time.perf_counter()
        new_active = db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.branch_id == chapter.branch_id,
            Chapter.id != chapter_id
        ).order_by(Chapter.chapter_number.desc()).first()
        
        if new_active:
            new_active.status = ChapterStatus.ACTIVE
            logger.info(f"[CHAPTER:DELETE:PHASE] trace_id={trace_id} phase=activate_new_chapter duration_ms={(time.perf_counter()-phase_start)*1000:.2f} new_active_chapter={new_active.id}")
    
    # Phase 7: Commit
    phase_start = time.perf_counter()
    logger.info(f"[CHAPTER:DELETE:COMMIT:START] trace_id={trace_id}")
    db.commit()
    commit_duration = (time.perf_counter() - phase_start) * 1000
    logger.info(f"[CHAPTER:DELETE:COMMIT:END] trace_id={trace_id} commit_duration_ms={commit_duration:.2f}")
    
    # Schedule background cleanup tasks (don't block response)
    if scene_ids_to_cleanup:
        # 1. Semantic cleanup (embeddings, character moments, plot events)
        logger.info(f"[CHAPTER:DELETE:BG_SCHEDULE] trace_id={trace_id} task=semantic_cleanup scene_count={len(scene_ids_to_cleanup)}")
        background_tasks.add_task(
            cleanup_semantic_data_in_background,
            scene_ids=scene_ids_to_cleanup,
            story_id=story_id
        )
        
        # 2. NPC tracking restoration
        from .stories import restore_npc_tracking_in_background
        logger.info(f"[CHAPTER:DELETE:BG_SCHEDULE] trace_id={trace_id} task=npc_tracking")
        background_tasks.add_task(
            restore_npc_tracking_in_background,
            story_id=story_id,
            sequence_number=min_deleted_seq,
            branch_id=chapter.branch_id
        )
        
        # 3. Entity states restoration
        from .stories import restore_entity_states_in_background, get_or_create_user_settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        logger.info(f"[CHAPTER:DELETE:BG_SCHEDULE] trace_id={trace_id} task=entity_states")
        background_tasks.add_task(
            restore_entity_states_in_background,
            story_id=story_id,
            sequence_number=min_deleted_seq,
            min_deleted_seq=min_deleted_seq,
            max_deleted_seq=max_deleted_seq,
            user_id=current_user.id,
            user_settings=user_settings,
            branch_id=chapter.branch_id
        )
    
    total_duration = (time.perf_counter() - op_start) * 1000
    if total_duration > 10000:
        logger.warning(f"[CHAPTER:DELETE:SLOW] trace_id={trace_id} duration_ms={total_duration:.2f} scenes_deleted={scene_count} batches_deleted={batches_deleted}")
    else:
        logger.info(f"[CHAPTER:DELETE:END] trace_id={trace_id} duration_ms={total_duration:.2f} chapter_number={chapter_number} scenes_deleted={scene_count} batches_deleted={batches_deleted}")
    
    return {
        "message": "Chapter deleted successfully",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "scenes_deleted": scene_count,
        "batches_deleted": batches_deleted
    }


async def cleanup_semantic_data_in_background(scene_ids: list, story_id: int):
    """Background task to clean up semantic data for deleted scenes"""
    import time
    import uuid
    
    trace_id = f"chapter-semantic-bg-{uuid.uuid4()}"
    task_start = time.perf_counter()
    total_scenes = len(scene_ids)
    
    logger.info(f"[CHAPTER-BG:SEMANTIC:START] trace_id={trace_id} story_id={story_id} scene_count={total_scenes} scene_ids={scene_ids[:5]}{'...' if total_scenes > 5 else ''}")
    
    try:
        import asyncio
        # Delay to ensure database commits from main session are visible
        await asyncio.sleep(0.3)
        logger.info(f"[CHAPTER-BG:SEMANTIC:PHASE] trace_id={trace_id} phase=delay_complete")
        
        from ..database import SessionLocal
        bg_db = SessionLocal()
        try:
            from ..services.semantic_integration import cleanup_scene_embeddings
            
            # Determine logging interval (every 10% or every scene if < 10)
            batch_log_interval = max(1, total_scenes // 10) if total_scenes > 10 else 1
            
            cleanup_start = time.perf_counter()
            cleaned_count = 0
            failed_count = 0
            
            for i, scene_id in enumerate(scene_ids):
                scene_start = time.perf_counter()
                try:
                    await cleanup_scene_embeddings(scene_id, bg_db)
                    cleaned_count += 1
                    scene_duration = (time.perf_counter() - scene_start) * 1000
                    
                    # Log progress at intervals or if cleanup takes > 500ms
                    if (i + 1) % batch_log_interval == 0 or scene_duration > 500:
                        elapsed_ms = (time.perf_counter() - cleanup_start) * 1000
                        logger.info(f"[CHAPTER-BG:SEMANTIC:PROGRESS] trace_id={trace_id} progress={i+1}/{total_scenes} ({((i+1)/total_scenes*100):.1f}%) elapsed_ms={elapsed_ms:.2f} last_scene_ms={scene_duration:.2f}")
                except Exception as e:
                    failed_count += 1
                    logger.warning(f"[CHAPTER-BG:SEMANTIC:SCENE_ERROR] trace_id={trace_id} scene_id={scene_id} error={e}")
                    # Continue with other scenes even if one fails
            
            cleanup_duration = (time.perf_counter() - cleanup_start) * 1000
            total_duration = (time.perf_counter() - task_start) * 1000
            
            if failed_count > 0:
                logger.warning(f"[CHAPTER-BG:SEMANTIC:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} cleaned={cleaned_count} failed={failed_count}")
            else:
                logger.info(f"[CHAPTER-BG:SEMANTIC:END] trace_id={trace_id} total_duration_ms={total_duration:.2f} cleaned={cleaned_count} avg_per_scene_ms={cleanup_duration/max(1,cleaned_count):.2f}")
        finally:
            bg_db.close()
    except Exception as e:
        total_duration = (time.perf_counter() - task_start) * 1000
        logger.error(f"[CHAPTER-BG:SEMANTIC:ERROR] trace_id={trace_id} duration_ms={total_duration:.2f} error={e}")
        import traceback
        logger.error(f"[CHAPTER-BG:SEMANTIC:TRACEBACK] trace_id={trace_id} {traceback.format_exc()}")


@router.get("/{story_id}/available-characters")
async def get_available_characters(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all available story characters for a story (for chapter wizard selection)"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Get all story characters for the active branch (or NULL branch for shared characters)
    active_branch_id = story.current_branch_id
    story_chars = db.query(StoryCharacter).filter(
        StoryCharacter.story_id == story_id,
        or_(
            StoryCharacter.branch_id == active_branch_id,
            StoryCharacter.branch_id.is_(None)
        )
    ).all()
    
    # Build response with character details, deduplicating by character_id
    seen_character_ids = set()
    characters = []
    for sc in story_chars:
        # Skip if we've already added this character
        if sc.character_id in seen_character_ids:
            continue
            
        char = db.query(Character).filter(Character.id == sc.character_id).first()
        if char:
            characters.append({
                "story_character_id": sc.id,
                "character_id": char.id,
                "name": char.name,
                "role": sc.role,
                "description": char.description
            })
            seen_character_ids.add(sc.character_id)
    
    return {"characters": characters}


@router.get("/{story_id}/available-locations")
async def get_available_locations(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all available locations for a story (from LocationState table)"""
    
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Get all location states for this story
    from ..models import LocationState
    locations = db.query(LocationState).filter(
        LocationState.story_id == story_id
    ).all()
    
    # Extract unique location names
    location_names = list(set([loc.location_name for loc in locations if loc.location_name]))
    
    return {"locations": location_names}


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
    
    # Filter by the story's current active branch
    active_branch_id = story.current_branch_id
    
    chapter = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.branch_id == active_branch_id,
        Chapter.status == ChapterStatus.ACTIVE
    ).first()
    
    if not chapter:
        # No active chapter found - return 404
        # Initial chapter should be created through chapter wizard during story setup
        # or when first scene is generated
        raise HTTPException(
            status_code=404,
            detail="No active chapter found. Please create a new chapter."
        )
    
    return build_chapter_response(chapter, db)


# NOTE: Chapter brainstorm endpoints have been moved to chapter_brainstorm.py
# =============================================================================
# Chapter Plot Progress Endpoints
# =============================================================================

class ChapterProgressResponse(BaseModel):
    """Response model for chapter progress"""
    has_plot: bool
    completed_events: List[str]
    total_events: int
    progress_percentage: float
    remaining_events: List[str]
    climax_reached: bool
    scene_count: int
    climax: Optional[str] = None
    resolution: Optional[str] = None
    key_events: List[str] = []


class EventToggleRequest(BaseModel):
    """Request model for toggling event completion"""
    event: str
    completed: bool


@router.get("/{story_id}/chapters/{chapter_id}/progress", response_model=ChapterProgressResponse)
async def get_chapter_progress(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the plot progress for a chapter.
    
    Returns progress information including completed events, remaining events,
    and progress percentage.
    """
    # Verify story ownership
    story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Get the chapter
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    try:
        from ..services.chapter_progress_service import ChapterProgressService
        progress_service = ChapterProgressService(db)
        progress = progress_service.get_chapter_progress(chapter)
        return progress
    except Exception as e:
        logger.error(f"[CHAPTER_PROGRESS:GET] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get progress: {str(e)}")


@router.put("/{story_id}/chapters/{chapter_id}/progress/events")
async def toggle_event_completion(
    story_id: int,
    chapter_id: int,
    request: EventToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually toggle the completion status of a plot event.
    
    This allows users to manually mark events as complete or incomplete,
    overriding the automatic detection.
    """
    # Verify story ownership
    story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Get the chapter
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    if not chapter.chapter_plot:
        raise HTTPException(status_code=400, detail="Chapter has no plot to track")
    
    try:
        from ..services.chapter_progress_service import ChapterProgressService
        progress_service = ChapterProgressService(db)
        # Use batch-aware toggle to keep batches in sync with manual changes
        updated_progress = progress_service.toggle_event_completion_with_batch(
            chapter=chapter,
            event=request.event,
            completed=request.completed
        )
        
        # Return full progress info
        progress = progress_service.get_chapter_progress(chapter)
        return progress
    except Exception as e:
        logger.error(f"[CHAPTER_PROGRESS:TOGGLE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update event: {str(e)}")


@router.post("/{story_id}/chapters/{chapter_id}/progress/extract")
async def extract_chapter_progress(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger plot event extraction for a chapter.
    
    This runs the extraction LLM on all scenes in the chapter to detect
    which planned events have occurred.
    """
    # Verify story ownership
    story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    # Get the chapter
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.story_id == story_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    if not chapter.chapter_plot:
        raise HTTPException(status_code=400, detail="Chapter has no plot to track")
    
    try:
        from ..services.chapter_progress_service import ChapterProgressService
        from ..services.llm.service import UnifiedLLMService
        from ..models import Scene, SceneVariant, StoryFlow, UserSettings
        
        # Get user settings
        user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
        user_settings = user_settings_obj.to_dict() if user_settings_obj else {}
        
        progress_service = ChapterProgressService(db)
        llm_service = UnifiedLLMService(user_settings=user_settings, user_id=current_user.id)
        
        # Get all scenes in the chapter
        scenes = db.query(Scene).filter(
            Scene.chapter_id == chapter_id,
            Scene.is_deleted == False
        ).order_by(Scene.sequence_number).all()
        
        logger.info(f"[CHAPTER_PROGRESS:EXTRACT] Manually extracting from {len(scenes)} scenes")
        
        key_events = chapter.chapter_plot.get("key_events", [])
        all_extracted = []
        
        for scene in scenes:
            # Get active variant content
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            ).first()
            
            if not flow or not flow.scene_variant_id:
                continue
                
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == flow.scene_variant_id
            ).first()
            
            if not variant or not variant.content:
                continue
            
            # Run extraction
            extracted = await progress_service.extract_completed_events(
                scene_content=variant.content,
                key_events=key_events,
                llm_service=llm_service,
                user_id=current_user.id,
                user_settings=user_settings
            )
            
            if extracted:
                all_extracted.extend(extracted)
                logger.info(f"[CHAPTER_PROGRESS:EXTRACT] Scene {scene.sequence_number}: Found {len(extracted)} events")
        
        # Update progress with all extracted events
        if all_extracted:
            progress_service.update_progress(
                chapter=chapter,
                new_completed_events=list(set(all_extracted))  # Dedupe
            )
        
        # Return updated progress
        progress = progress_service.get_chapter_progress(chapter)
        return {
            "message": f"Extracted events from {len(scenes)} scenes",
            "newly_detected": list(set(all_extracted)),
            "progress": progress
        }
        
    except Exception as e:
        logger.error(f"[CHAPTER_PROGRESS:EXTRACT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract progress: {str(e)}")
