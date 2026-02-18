from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Chapter, Scene, User, ChapterStatus, StoryMode, StoryCharacter, Character, ChapterSummaryBatch, StoryBranch
from ..models.chapter import chapter_characters
from ..dependencies import get_current_user
from ..services.llm.service import UnifiedLLMService
from ..services.llm.prompts import prompt_manager
from ..config import settings
from datetime import datetime, timezone
import asyncio
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
    character_ids: Optional[List[int]] = None  # New characters from library to add to story
    character_roles: Optional[Dict[str, str]] = None  # Roles for new characters {character_id: role}
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
    creation_step: Optional[int] = None
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
        status=chapter.status.value if chapter.status else 'draft',
        creation_step=chapter.creation_step,
        context_tokens_used=chapter.context_tokens_used or 0,
        scenes_count=chapter.scenes_count or 0,
        auto_summary=chapter.auto_summary,
        last_summary_scene_count=chapter.last_summary_scene_count or 0,
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
    """Create a new chapter (Dynamic mode) with streaming status updates.

    Resilient, resumable flow:
    - Phase A: Complete previous chapter (generate summary, mark completed, fire background story summary)
    - Phase B: Create new chapter record + characters (DB-only, fast) → commit with creation_step=4
    - Phase C: Enrich new chapter (generate story_so_far via LLM, non-fatal) → commit with creation_step=None
    """

    async def generate_stream():
        trace_id = f"chap-create-{uuid.uuid4()}"

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

            # Guard against double creation: check for any incomplete chapter in this story/branch
            incomplete_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id,
                Chapter.creation_step.isnot(None)
            ).first()

            if incomplete_chapter:
                logger.warning(f"[CHAPTER:CREATE] trace_id={trace_id} incomplete_chapter_exists chapter_id={incomplete_chapter.id} creation_step={incomplete_chapter.creation_step}")
                yield f"data: {json.dumps({'type': 'error', 'message': f'Chapter {incomplete_chapter.chapter_number} has incomplete setup. Please resume or discard it before creating a new chapter.'})}\n\n"
                return

            # Get the current active chapter to complete it (filtered by branch)
            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id,
                Chapter.status == ChapterStatus.ACTIVE
            ).first()

            # ============================================================
            # PHASE A: Complete previous chapter
            # ============================================================
            if active_chapter:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Completing previous chapter...', 'step': 'completing_previous'})}\n\n"
                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} completing_chapter_id={active_chapter.id} chapter_number={active_chapter.chapter_number}")

                try:
                    # A1: Generate chapter summary (LLM) → commit summary
                    if active_chapter.scenes_count > 0:
                        yield f"data: {json.dumps({'type': 'status', 'message': 'Generating chapter summary...', 'step': 'generating_chapter_summary'})}\n\n"
                        logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} generating_summary chapter_id={active_chapter.id} scenes={active_chapter.scenes_count}")

                        await generate_chapter_summary_incremental(active_chapter.id, db, current_user.id)
                        db.refresh(active_chapter)
                        logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} summary_generated chapter_id={active_chapter.id}")

                    # A2: Mark previous chapter COMPLETED → commit
                    active_chapter.status = ChapterStatus.COMPLETED
                    active_chapter.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} prev_chapter_committed chapter_id={active_chapter.id}")

                    # A3: Fire story summary update as background task (non-blocking)
                    if active_chapter.scenes_count > 0:
                        async def _update_story_summary_bg(story_id_bg, user_id_bg):
                            from ..database import SessionLocal
                            bg_db = SessionLocal()
                            try:
                                from ..api.summaries import update_story_summary_from_chapters
                                await update_story_summary_from_chapters(story_id_bg, bg_db, user_id_bg)
                                logger.info(f"[CHAPTER:CREATE:BG] trace_id={trace_id} story_summary_updated")
                            except Exception as e:
                                logger.warning(f"[CHAPTER:CREATE:BG] trace_id={trace_id} story_summary_failed error={e}")
                            finally:
                                bg_db.close()

                        asyncio.create_task(_update_story_summary_bg(active_chapter.story_id, current_user.id))

                except Exception as e:
                    logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} step=completing_previous error={e}")
                    db.rollback()
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to complete previous chapter: {str(e)}'})}\n\n"
                    return

            # ============================================================
            # PHASE B: Create new chapter (DB-only, fast)
            # ============================================================
            yield f"data: {json.dumps({'type': 'status', 'message': 'Creating new chapter...', 'step': 'creating_chapter'})}\n\n"

            # Recalculate chapter number to ensure accuracy
            max_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id
            ).order_by(Chapter.chapter_number.desc()).first()

            next_chapter_number = (max_chapter.chapter_number + 1) if max_chapter else 1
            logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} next_chapter_number={next_chapter_number}")

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

                # Determine initial creation_step: 4 if story_so_far is needed, None otherwise
                needs_story_so_far = next_chapter_number > 1
                initial_creation_step = 4 if needs_story_so_far else None

                new_chapter = Chapter(
                    story_id=story_id,
                    branch_id=active_branch_id,
                    chapter_number=next_chapter_number,
                    title=chapter_data.title or f"Chapter {next_chapter_number}",
                    description=chapter_data.description,
                    story_so_far=None,
                    plot_point=chapter_data.plot_point,
                    location_name=chapter_data.location_name,
                    time_period=chapter_data.time_period,
                    scenario=chapter_data.scenario,
                    continues_from_previous=chapter_data.continues_from_previous if chapter_data.continues_from_previous is not None else True,
                    status=ChapterStatus.ACTIVE,
                    creation_step=initial_creation_step,
                    context_tokens_used=0,
                    scenes_count=0,
                    chapter_plot=chapter_data.chapter_plot,
                    brainstorm_session_id=chapter_data.brainstorm_session_id
                )

                db.add(new_chapter)
                db.flush()  # Get the chapter ID
                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} new_chapter_flushed chapter_id={new_chapter.id} chapter_number={next_chapter_number}")

                # Collect all story_character_ids to associate with the chapter
                all_story_character_ids = set()

                # Handle new characters from library (character_ids)
                if chapter_data.character_ids:
                    character_roles = chapter_data.character_roles or {}
                    for character_id in chapter_data.character_ids:
                        char = db.query(Character).filter(Character.id == character_id).first()
                        if not char:
                            db.rollback()
                            logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} character_not_found character_id={character_id}")
                            yield f"data: {json.dumps({'type': 'error', 'message': f'Character with ID {character_id} not found'})}\n\n"
                            return

                        story_char = db.query(StoryCharacter).filter(
                            StoryCharacter.story_id == story_id,
                            StoryCharacter.branch_id == active_branch_id,
                            StoryCharacter.character_id == character_id
                        ).first()

                        if not story_char:
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
                            db.flush()
                            logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} created_story_character character_id={character_id} role={role}")
                        else:
                            new_role = None
                            if isinstance(character_roles, dict):
                                new_role = character_roles.get(character_id) or character_roles.get(str(character_id))
                            if new_role and story_char.role != new_role:
                                story_char.role = new_role
                                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} updated_story_character_role story_char_id={story_char.id} role={new_role}")

                        all_story_character_ids.add(story_char.id)

                # Handle existing story characters (story_character_ids)
                if chapter_data.story_character_ids:
                    branch_ids = []
                    if active_branch_id:
                        current_branch = db.query(StoryBranch).filter(StoryBranch.id == active_branch_id).first()
                        while current_branch:
                            branch_ids.append(current_branch.id)
                            if current_branch.forked_from_branch_id:
                                current_branch = db.query(StoryBranch).filter(
                                    StoryBranch.id == current_branch.forked_from_branch_id
                                ).first()
                            else:
                                break

                    if branch_ids:
                        story_chars = db.query(StoryCharacter).filter(
                            StoryCharacter.id.in_(chapter_data.story_character_ids),
                            StoryCharacter.story_id == story_id,
                            StoryCharacter.branch_id.in_(branch_ids)
                        ).all()
                    else:
                        story_chars = db.query(StoryCharacter).filter(
                            StoryCharacter.id.in_(chapter_data.story_character_ids),
                            StoryCharacter.story_id == story_id
                        ).all()

                    if len(story_chars) != len(chapter_data.story_character_ids):
                        found_ids = {sc.id for sc in story_chars}
                        missing_ids = [cid for cid in chapter_data.story_character_ids if cid not in found_ids]
                        missing_chars = db.query(StoryCharacter).filter(
                            StoryCharacter.id.in_(missing_ids)
                        ).all()
                        missing_details = [f"id={mc.id} story_id={mc.story_id} branch_id={mc.branch_id}" for mc in missing_chars]

                        db.rollback()
                        logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} invalid_story_characters requested={len(chapter_data.story_character_ids)} found={len(story_chars)} active_branch={active_branch_id}")
                        logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} missing_characters: {', '.join(missing_details)}")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Some character IDs do not belong to this story branch'})}\n\n"
                        return

                    for story_char in story_chars:
                        all_story_character_ids.add(story_char.id)

                # Create chapter-character associations
                if all_story_character_ids:
                    for story_char_id in all_story_character_ids:
                        db.execute(
                            chapter_characters.insert().values(
                                chapter_id=new_chapter.id,
                                story_character_id=story_char_id
                            )
                        )
                    logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} associated_characters count={len(all_story_character_ids)}")

                # Commit chapter + characters with creation_step marker
                db.commit()
                db.refresh(new_chapter)
                logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} chapter_committed chapter_id={new_chapter.id} creation_step={new_chapter.creation_step}")

                # Send minimal chapter info — frontend reloads full data via loadChapters()
                yield f"data: {json.dumps({'type': 'complete', 'chapter': {'id': new_chapter.id, 'chapter_number': new_chapter.chapter_number}})}\n\n"

            except Exception as e:
                logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} step=creating_new_chapter error={e}")
                db.rollback()
                yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to create new chapter: {str(e)}'})}\n\n"
                return

            # ============================================================
            # PHASE C: Enrich new chapter (LLM, non-fatal)
            # ============================================================
            if needs_story_so_far:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Generating story context...', 'step': 'generating_story_so_far'})}\n\n"
                try:
                    await generate_story_so_far(new_chapter.id, db, current_user.id, auto_commit=False)
                    new_chapter.creation_step = None
                    db.commit()
                    db.refresh(new_chapter)
                    logger.info(f"[CHAPTER:CREATE] trace_id={trace_id} story_so_far_generated, creation_step cleared")
                    yield f"data: {json.dumps({'type': 'enrichment_complete', 'step': 'story_so_far'})}\n\n"
                except Exception as e:
                    # Non-fatal: chapter is still usable without story_so_far
                    logger.warning(f"[CHAPTER:CREATE:WARN] trace_id={trace_id} story_so_far_failed (non-fatal) error={e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'type': 'enrichment_failed', 'step': 'story_so_far', 'message': str(e)})}\n\n"

            logger.info(f"[CHAPTER:CREATE:SUCCESS] trace_id={trace_id} chapter_id={new_chapter.id} chapter_number={next_chapter_number}")

        except Exception as e:
            logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} step=outer_exception error={e}")
            try:
                db.rollback()
            except Exception as rollback_error:
                logger.error(f"[CHAPTER:CREATE:ERROR] trace_id={trace_id} rollback_failed error={rollback_error}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'Unexpected error: {str(e)}'})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


@router.post("/{story_id}/chapters/{chapter_id}/resume-creation")
async def resume_chapter_creation(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resume an interrupted chapter creation process.

    Picks up from the last successful step (identified by creation_step).
    Currently handles: creation_step=4 → generate story_so_far.
    """

    async def generate_stream():
        trace_id = f"chap-resume-{uuid.uuid4()}"

        try:
            logger.info(f"[CHAPTER:RESUME:START] trace_id={trace_id} story_id={story_id} chapter_id={chapter_id}")

            # Verify story ownership
            story = db.query(Story).filter(
                Story.id == story_id,
                Story.owner_id == current_user.id
            ).first()

            if not story:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Story not found'})}\n\n"
                return

            chapter = db.query(Chapter).filter(
                Chapter.id == chapter_id,
                Chapter.story_id == story_id
            ).first()

            if not chapter:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Chapter not found'})}\n\n"
                return

            if chapter.creation_step is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Chapter creation is already complete'})}\n\n"
                return

            logger.info(f"[CHAPTER:RESUME] trace_id={trace_id} creation_step={chapter.creation_step}")

            # Resume based on creation_step
            if chapter.creation_step == 4:
                # Step 5: Generate story_so_far
                yield f"data: {json.dumps({'type': 'status', 'message': 'Generating story context...', 'step': 'generating_story_so_far'})}\n\n"
                try:
                    await generate_story_so_far(chapter.id, db, current_user.id, auto_commit=False)
                    chapter.creation_step = None
                    db.commit()
                    db.refresh(chapter)
                    logger.info(f"[CHAPTER:RESUME] trace_id={trace_id} story_so_far_generated, creation_step cleared")

                    # Send minimal chapter info — frontend reloads full data via loadChapters()
                    yield f"data: {json.dumps({'type': 'complete', 'chapter': {'id': chapter.id, 'chapter_number': chapter.chapter_number}})}\n\n"

                except Exception as e:
                    logger.error(f"[CHAPTER:RESUME:ERROR] trace_id={trace_id} story_so_far_failed error={e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to generate story context: {str(e)}'})}\n\n"
                    return
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Unknown creation step: {chapter.creation_step}'})}\n\n"
                return

            logger.info(f"[CHAPTER:RESUME:SUCCESS] trace_id={trace_id} chapter_id={chapter_id}")

        except Exception as e:
            logger.error(f"[CHAPTER:RESUME:ERROR] trace_id={trace_id} step=outer_exception error={e}")
            try:
                db.rollback()
            except Exception:
                pass
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

    logger.info(f"[CHAPTER] Updating chapter {chapter_id}, character_ids={chapter_data.character_ids}, story_character_ids={chapter_data.story_character_ids}, character_roles={chapter_data.character_roles}")
    
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
    
    # Handle new characters from library (character_ids) — create StoryCharacter records
    new_story_char_ids = set()
    if chapter_data.character_ids:
        active_branch_id = story.current_branch_id
        character_roles = chapter_data.character_roles or {}
        for character_id in chapter_data.character_ids:
            char = db.query(Character).filter(Character.id == character_id).first()
            if not char:
                raise HTTPException(status_code=404, detail=f"Character with ID {character_id} not found")

            story_char = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id,
                StoryCharacter.branch_id == active_branch_id,
                StoryCharacter.character_id == character_id
            ).first()

            if not story_char:
                role = character_roles.get(str(character_id))
                story_char = StoryCharacter(
                    story_id=story_id,
                    branch_id=active_branch_id,
                    character_id=character_id,
                    role=role,
                    is_active=True
                )
                db.add(story_char)
                db.flush()
                logger.info(f"[CHAPTER] Created story_character from library: char_id={character_id} role={role}")
            else:
                new_role = character_roles.get(str(character_id))
                if new_role and story_char.role != new_role:
                    story_char.role = new_role

            new_story_char_ids.add(story_char.id)

    # Update character associations if provided
    if chapter_data.story_character_ids is not None or new_story_char_ids:
        # Remove existing associations
        db.execute(
            chapter_characters.delete().where(
                chapter_characters.c.chapter_id == chapter.id
            )
        )

        # Validate that all story_character_ids belong to this story and branch ancestry
        if chapter_data.story_character_ids:
            # Build the branch ancestry chain (current branch + all ancestors)
            active_branch_id = story.current_branch_id
            branch_ids = []
            if active_branch_id:
                current_branch = db.query(StoryBranch).filter(StoryBranch.id == active_branch_id).first()
                while current_branch:
                    branch_ids.append(current_branch.id)
                    if current_branch.forked_from_branch_id:
                        current_branch = db.query(StoryBranch).filter(
                            StoryBranch.id == current_branch.forked_from_branch_id
                        ).first()
                    else:
                        break

            if branch_ids:
                story_chars = db.query(StoryCharacter).filter(
                    StoryCharacter.id.in_(chapter_data.story_character_ids),
                    StoryCharacter.story_id == story_id,
                    StoryCharacter.branch_id.in_(branch_ids)
                ).all()
            else:
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
                new_story_char_ids.add(story_char.id)

        # Associate all characters (from library + existing story characters)
        if new_story_char_ids:
            for sc_id in new_story_char_ids:
                db.execute(
                    chapter_characters.insert().values(
                        chapter_id=chapter.id,
                        story_character_id=sc_id
                    )
                )
            logger.info(f"[CHAPTER] Updated character associations for chapter {chapter.id}: {len(new_story_char_ids)} characters")
    
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
        
        # Extract entity_states_snapshot from context for cache consistency
        entity_states_snapshot = context.get('entity_states_text') if context else None

        conclusion_scene, conclusion_variant = llm_service.create_scene_with_variant(
            db=db,
            story_id=story_id,
            sequence_number=next_sequence,
            content=conclusion_text,
            title=f"Chapter {chapter.chapter_number} Conclusion",
            custom_prompt=conclusion_prompt_text,
            generation_method="chapter_conclusion",
            branch_id=chapter.branch_id,
            entity_states_snapshot=entity_states_snapshot
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
            detail="Failed to conclude chapter"
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
    role: Optional[str] = None,
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
        
        # Check if StoryCharacter exists for this branch
        story_char = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id,
            StoryCharacter.branch_id == story.current_branch_id,
            StoryCharacter.character_id == character_id
        ).first()

        if not story_char:
            # Create StoryCharacter entry with branch and role
            story_char = StoryCharacter(
                story_id=story_id,
                branch_id=story.current_branch_id,
                character_id=character_id,
                role=role,
                is_active=True
            )
            db.add(story_char)
            db.flush()
            logger.info(f"[CHAPTER] Created StoryCharacter entry for character {character_id} in branch {story.current_branch_id} with role '{role}'")
        
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
    from ..services.chapter_summary_service import ChapterSummaryService

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

    # Use summary service
    summary_service = ChapterSummaryService(db, current_user.id)

    # Generate chapter summary (this chapter's content only)
    chapter_summary = await summary_service.generate_chapter_summary(chapter_id)

    # Optionally regenerate story_so_far (all previous + current)
    story_so_far = None
    if regenerate_story_so_far:
        story_so_far = await summary_service.generate_story_so_far(chapter_id)

    return {
        "message": "Chapter summary generated successfully",
        "chapter_summary": chapter_summary,
        "story_so_far": story_so_far,
        "scenes_summarized": chapter.scenes_count
    }


# ====== WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY ======
# These functions delegate to ChapterSummaryService for external imports

async def generate_chapter_summary(chapter_id: int, db: Session, user_id: int) -> str:
    """Wrapper for backward compatibility. Use ChapterSummaryService directly for new code."""
    from ..services.chapter_summary_service import ChapterSummaryService
    service = ChapterSummaryService(db, user_id)
    return await service.generate_chapter_summary(chapter_id)


async def generate_chapter_summary_incremental(chapter_id: int, db: Session, user_id: int) -> str:
    """Wrapper for backward compatibility. Use ChapterSummaryService directly for new code."""
    from ..services.chapter_summary_service import ChapterSummaryService
    service = ChapterSummaryService(db, user_id)
    return await service.generate_chapter_summary_incremental(chapter_id)


async def generate_story_so_far(chapter_id: int, db: Session, user_id: int, auto_commit: bool = True) -> Optional[str]:
    """Wrapper for backward compatibility. Use ChapterSummaryService directly for new code."""
    from ..services.chapter_summary_service import ChapterSummaryService
    service = ChapterSummaryService(db, user_id)
    return await service.generate_story_so_far(chapter_id, auto_commit=auto_commit)


def combine_chapter_batches(chapter_id: int, db: Session) -> Optional[str]:
    """Wrapper for backward compatibility."""
    from ..services.chapter_summary_service import combine_chapter_batches as _combine
    return _combine(chapter_id, db)


def update_chapter_summary_from_batches(chapter_id: int, db: Session) -> None:
    """Wrapper for backward compatibility."""
    from ..services.chapter_summary_service import update_chapter_summary_from_batches as _update
    return _update(chapter_id, db)


def invalidate_chapter_batches_for_scene(scene_id: int, db: Session) -> None:
    """Wrapper for backward compatibility."""
    from ..services.chapter_summary_service import invalidate_chapter_batches_for_scene as _invalidate
    return _invalidate(scene_id, db)


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
    from ..services.chapter_summary_service import ChapterSummaryService

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

    # Use summary service
    summary_service = ChapterSummaryService(db, current_user.id)
    story_so_far = await summary_service.generate_story_so_far(chapter_id)

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
        from .story_tasks import restore_npc_tracking_in_background
        logger.info(f"[CHAPTER:CONTENT:DELETE:BG_SCHEDULE] trace_id={trace_id} task=npc_tracking")
        background_tasks.add_task(
            restore_npc_tracking_in_background,
            story_id=story_id,
            sequence_number=min_deleted_seq,
            branch_id=chapter.branch_id
        )

        # 3. Entity states restoration
        from .story_tasks import restore_entity_states_in_background
        from .story_helpers import get_or_create_user_settings
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
        from .story_tasks import restore_npc_tracking_in_background
        logger.info(f"[CHAPTER:DELETE:BG_SCHEDULE] trace_id={trace_id} task=npc_tracking")
        background_tasks.add_task(
            restore_npc_tracking_in_background,
            story_id=story_id,
            sequence_number=min_deleted_seq,
            branch_id=chapter.branch_id
        )

        # 3. Entity states restoration
        from .story_tasks import restore_entity_states_in_background
        from .story_helpers import get_or_create_user_settings
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


# Import cleanup_semantic_data_in_background from story_tasks (has retry logic)
from .story_tasks import cleanup_semantic_data_in_background


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

    # Get the full branch ancestry chain (current branch + all ancestors)
    # This ensures characters from parent branches are visible when on a child branch
    active_branch_id = story.current_branch_id
    branch_ids = []

    if active_branch_id:
        # Build the ancestry chain by following forked_from_branch_id
        current_branch = db.query(StoryBranch).filter(StoryBranch.id == active_branch_id).first()
        while current_branch:
            branch_ids.append(current_branch.id)
            if current_branch.forked_from_branch_id:
                current_branch = db.query(StoryBranch).filter(
                    StoryBranch.id == current_branch.forked_from_branch_id
                ).first()
            else:
                break

    # Get all story characters for branches in the ancestry chain
    if branch_ids:
        story_chars = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id,
            StoryCharacter.branch_id.in_(branch_ids)
        ).all()
    else:
        # No active branch, get all characters for this story
        story_chars = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id
        ).all()

    # Build response with character details, deduplicating by character_id
    # Prefer characters from the current branch over ancestors (more specific version)
    seen_character_ids = set()
    characters = []

    # Sort by branch_id so current branch characters come first (they have higher branch_id typically)
    # or more specifically, sort by position in branch_ids list (index 0 = current branch = highest priority)
    def sort_key(sc):
        if sc.branch_id is None:
            return len(branch_ids) + 1  # NULL branch has lowest priority
        try:
            return branch_ids.index(sc.branch_id)
        except ValueError:
            return len(branch_ids)  # Unknown branch has low priority

    story_chars_sorted = sorted(story_chars, key=sort_key)

    for sc in story_chars_sorted:
        # Skip if we've already added this character (from a more specific branch)
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

    logger.info(f"[AVAILABLE_CHARACTERS] Story {story_id}: branch_ids={branch_ids}, returning {len(characters)} characters: {[c['name'] for c in characters]}")
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
    resolution_reached: bool
    scene_count: int
    climax: Optional[str] = None
    resolution: Optional[str] = None
    key_events: List[str] = []


class EventToggleRequest(BaseModel):
    """Request model for toggling event completion"""
    event: str
    completed: bool


class MilestoneToggleRequest(BaseModel):
    """Request model for toggling milestone (climax/resolution) completion"""
    milestone: str  # "climax" or "resolution"
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
        raise HTTPException(status_code=500, detail="Failed to get progress")


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
        raise HTTPException(status_code=500, detail="Failed to update event")


@router.put("/{story_id}/chapters/{chapter_id}/progress/milestone")
async def toggle_milestone_completion(
    story_id: int,
    chapter_id: int,
    request: MilestoneToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually toggle the completion status of a milestone (climax or resolution).

    This allows users to manually mark the climax or resolution as complete
    or incomplete, useful when the story has reached these points.
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

    # Validate milestone value
    if request.milestone not in ("climax", "resolution"):
        raise HTTPException(status_code=400, detail="Milestone must be 'climax' or 'resolution'")

    try:
        from ..services.chapter_progress_service import ChapterProgressService
        progress_service = ChapterProgressService(db)
        updated_progress = progress_service.toggle_milestone_completion(
            chapter=chapter,
            milestone=request.milestone,
            completed=request.completed
        )

        # Return full progress info
        progress = progress_service.get_chapter_progress(chapter)
        return progress
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_PROGRESS:MILESTONE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update milestone")


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
        raise HTTPException(status_code=500, detail="Failed to extract progress")
