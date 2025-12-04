from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Chapter, Scene, User, ChapterStatus, StoryMode, StoryCharacter, Character, ChapterSummaryBatch
from ..models.chapter import chapter_characters
from ..dependencies import get_current_user
from ..services.llm.service import UnifiedLLMService
from ..config import settings
from datetime import datetime, timezone
import logging
import json

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
    
    class Config:
        from_attributes = True

def build_chapter_response(chapter: Chapter, db: Session) -> ChapterResponse:
    """Helper function to build ChapterResponse with characters"""
    # Load characters for chapter
    chapter_chars = db.query(StoryCharacter).join(
        chapter_characters, StoryCharacter.id == chapter_characters.c.story_character_id
    ).filter(
        chapter_characters.c.chapter_id == chapter.id
    ).all()
    
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
        continues_from_previous=getattr(chapter, 'continues_from_previous', True)
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
        try:
            logger.info(f"[CHAPTER] Creating new chapter for story {story_id}")
            
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
            
            # Get the current active chapter to complete it (filtered by branch)
            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id,
                Chapter.status == ChapterStatus.ACTIVE
            ).first()
            
            # Get next chapter number (for this branch)
            max_chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.branch_id == active_branch_id
            ).order_by(Chapter.chapter_number.desc()).first()
            
            next_chapter_number = (max_chapter.chapter_number + 1) if max_chapter else 1
            
            # Mark current chapter as completed if exists
            # This needs to be committed before creating new chapter (to free up ACTIVE status)
            if active_chapter:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Completing previous chapter...', 'step': 'completing_previous'})}\n\n"
                
                active_chapter.status = ChapterStatus.COMPLETED
                active_chapter.completed_at = datetime.now(timezone.utc)
                logger.info(f"[CHAPTER] Marked chapter {active_chapter.id} as completed")
                
                # ALWAYS regenerate summary for the completed chapter to include all scenes
                # (even if summary exists, it might be stale and missing recent scenes)
                if active_chapter.scenes_count > 0:
                    yield f"data: {json.dumps({'type': 'status', 'message': 'Generating chapter summary...', 'step': 'generating_chapter_summary'})}\n\n"
                    logger.info(f"[CHAPTER] Generating final summary for completed chapter {active_chapter.id} ({active_chapter.scenes_count} scenes)")
                    try:
                        # Generate the chapter's own summary (incremental - only new scenes)
                        await generate_chapter_summary_incremental(active_chapter.id, db, current_user.id)
                        
                        db.refresh(active_chapter)  # Refresh to get the auto_summary
                        logger.info(f"[CHAPTER] Final summary generated for completed chapter {active_chapter.id}")
                        
                        # Update story.summary now that this chapter is completed
                        try:
                            from ..api.summaries import update_story_summary_from_chapters
                            await update_story_summary_from_chapters(active_chapter.story_id, db, current_user.id)
                            logger.info(f"[CHAPTER] Updated story summary after completing chapter {active_chapter.id}")
                        except Exception as e:
                            # Don't fail chapter creation if story summary update fails
                            logger.warning(f"[CHAPTER] Failed to update story summary after completing chapter {active_chapter.id}: {e}")
                    except Exception as e:
                        logger.error(f"[CHAPTER] Failed to generate summary for completed chapter {active_chapter.id}: {e}")
                        # Continue with chapter creation even if summary fails
                
                # Commit completed chapter changes before creating new chapter
                db.commit()
            
            yield f"data: {json.dumps({'type': 'status', 'message': 'Creating new chapter...', 'step': 'creating_chapter'})}\n\n"
            
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
                scenes_count=0
            )
            
            db.add(new_chapter)
            db.flush()  # Flush to get the chapter ID (but don't commit yet)
            
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
                        logger.info(f"[CHAPTER] Created StoryCharacter entry for character {character_id} with role {role} on branch {active_branch_id}")
                    else:
                        # Update role if provided and different
                        # Handle both int and str keys (JSON may convert int keys to strings)
                        new_role = None
                        if isinstance(character_roles, dict):
                            new_role = character_roles.get(character_id) or character_roles.get(str(character_id))
                        if new_role and story_char.role != new_role:
                            story_char.role = new_role
                            logger.info(f"[CHAPTER] Updated role for StoryCharacter {story_char.id} to {new_role}")
                    
                    all_story_character_ids.add(story_char.id)
            
            # Handle existing story characters (story_character_ids)
            if chapter_data.story_character_ids:
                # Validate that all story_character_ids belong to this story and branch
                story_chars = db.query(StoryCharacter).filter(
                    StoryCharacter.id.in_(chapter_data.story_character_ids),
                    StoryCharacter.story_id == story_id,
                    StoryCharacter.branch_id == active_branch_id
                ).all()
                
                if len(story_chars) != len(chapter_data.story_character_ids):
                    db.rollback()  # Rollback before returning error
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
                logger.info(f"[CHAPTER] Associated {len(all_story_character_ids)} characters with chapter {new_chapter.id}")
            
            # Generate the story_so_far for the new chapter (combining all previous chapters)
            # BUT skip for the first chapter since there are no previous chapters
            if next_chapter_number > 1:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Generating story so far...', 'step': 'generating_story_so_far'})}\n\n"
                try:
                    await generate_story_so_far(new_chapter.id, db, current_user.id)
                    db.refresh(new_chapter)
                    logger.info(f"[CHAPTER] Generated story_so_far for new chapter {new_chapter.id}")
                except Exception as e:
                    logger.error(f"[CHAPTER] Failed to generate story_so_far for new chapter {new_chapter.id}: {e}")
                    # If generation fails, story_so_far will remain None (already set above)
            
            # Now commit everything atomically: new chapter + character associations + summaries
            db.commit()
            db.refresh(new_chapter)
            
            logger.info(f"[CHAPTER] Created chapter {new_chapter.id} (Chapter {next_chapter_number})")
            
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
            logger.error(f"[CHAPTER] Error creating chapter: {e}")
            # Rollback any uncommitted changes (new chapter creation)
            try:
                db.rollback()
            except Exception as rollback_error:
                logger.error(f"[CHAPTER] Error during rollback: {rollback_error}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
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
    
    # Generate chapter summary if not already done
    if not chapter.auto_summary or chapter.last_summary_scene_count < chapter.scenes_count:
        logger.info(f"[CHAPTER] Generating final summary for chapter {chapter_id}")
        await generate_chapter_summary_incremental(chapter_id, db, current_user.id)
    
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
            generation_method="chapter_conclusion"
        )
        
        # Link scene to chapter
        conclusion_scene.chapter_id = chapter_id
        db.commit()
        
        # Generate summary for the chapter before marking as completed
        if not chapter.auto_summary or chapter.last_summary_scene_count < chapter.scenes_count:
            await generate_chapter_summary_incremental(chapter_id, db, current_user.id)
            await generate_story_so_far(chapter_id, db, current_user.id)
        
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
    branch_chapters_query = db.query(Chapter).filter(
        Chapter.story_id == story_id
    )
    # Filter by branch_id if the chapter has one
    if chapter.branch_id:
        branch_chapters_query = branch_chapters_query.filter(Chapter.branch_id == chapter.branch_id)
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
            db.commit()
            current_tokens = actual_context_size
            logger.info(f"[CONTEXT STATUS] Recalculated context size for chapter {chapter_id}: {actual_context_size} tokens")
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
    active_scenes_count = llm_service.get_active_scene_count(db, story_id, chapter_id)
    
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
    
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return ""
    
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
    
    # Add allow_nsfw from user to ensure NSFW filter is applied correctly
    if user_settings is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_settings['allow_nsfw'] = user.allow_nsfw
    
    # Generate summary using basic LLM generation (not scene continuation)
    # NSFW filter is automatically applied based on user settings
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
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return ""
    
    # Get scenes since last summary
    last_summary_count = chapter.last_summary_scene_count or 0
    new_scenes = db.query(Scene).filter(
        Scene.chapter_id == chapter_id,
        Scene.sequence_number > last_summary_count
    ).order_by(Scene.sequence_number).all()
    
    if not new_scenes:
        logger.info(f"[CHAPTER] No new scenes to summarize for chapter {chapter_id}")
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
        logger.info(f"[CHAPTER] No content available for new scenes in chapter {chapter_id}")
        return chapter.auto_summary or ""
    
    new_scenes_text = "\n\n".join(scene_contents)
    
    # Get rich context (similar to scene generation)
    # 1. story_so_far
    story_so_far_text = ""
    if chapter.story_so_far:
        story_so_far_text = f"\nStory So Far (Previous Chapters):\n{chapter.story_so_far}\n"
    
    # 2. previous chapter summary (filtered by branch_id to avoid cross-branch pollution)
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
    
    # 3. Characters in this chapter
    # Use the chapter's relationship to get characters
    chapter_chars = chapter.characters.all()
    
    characters_text = ""
    if chapter_chars:
        # Get character names from the Character relationship
        char_names = []
        for story_char in chapter_chars:
            if story_char.character and story_char.character.name:
                char_names.append(story_char.character.name)
        if char_names:
            characters_text = f"\nCharacters in Chapter: {', '.join(char_names)}\n"
    
    # 4. Entity states (characters, locations, objects)
    from ..models import CharacterState, LocationState, ObjectState, Character
    entity_parts = []
    
    character_states = db.query(CharacterState).filter(
        CharacterState.story_id == chapter.story_id
    ).all()
    
    location_states = db.query(LocationState).filter(
        LocationState.story_id == chapter.story_id
    ).all()
    
    object_states = db.query(ObjectState).filter(
        ObjectState.story_id == chapter.story_id
    ).all()
    
    if character_states:
        entity_parts.append("CURRENT CHARACTER STATES:")
        for char_state in character_states[:5]:  # Limit to 5 characters
            character = db.query(Character).filter(
                Character.id == char_state.character_id
            ).first()
            
            if not character:
                continue
            
            char_text = f"\n{character.name}:"
            
            if char_state.current_location:
                char_text += f"\n  Location: {char_state.current_location}"
            
            if char_state.emotional_state:
                char_text += f"\n  Emotional State: {char_state.emotional_state}"
            
            if char_state.physical_condition:
                char_text += f"\n  Physical Condition: {char_state.physical_condition}"
            
            if char_state.possessions:
                possessions_str = ", ".join(char_state.possessions[:5])
                char_text += f"\n  Possessions: {possessions_str}"
            
            if char_state.knowledge and len(char_state.knowledge) > 0:
                recent_knowledge = char_state.knowledge[-3:]
                char_text += f"\n  Recent Knowledge: {'; '.join(recent_knowledge)}"
            
            entity_parts.append(char_text)
    
    if location_states:
        entity_parts.append("\n\nCURRENT LOCATIONS:")
        for loc_state in location_states[:3]:  # Limit to 3 locations
            loc_text = f"\n{loc_state.location_name}:"
            
            if loc_state.condition:
                loc_text += f"\n  Condition: {loc_state.condition}"
            
            if loc_state.atmosphere:
                loc_text += f"\n  Atmosphere: {loc_state.atmosphere}"
            
            if loc_state.current_occupants:
                occupants_str = ", ".join(loc_state.current_occupants[:5])
                loc_text += f"\n  Present: {occupants_str}"
            
            entity_parts.append(loc_text)
    
    if object_states:
        entity_parts.append("\n\nIMPORTANT OBJECTS:")
        for obj_state in object_states[:3]:  # Limit to 3 objects
            obj_text = f"\n{obj_state.object_name}:"
            
            if obj_state.current_location:
                obj_text += f"\n  Location: {obj_state.current_location}"
            
            if obj_state.condition:
                obj_text += f"\n  Condition: {obj_state.condition}"
            
            if obj_state.significance:
                obj_text += f"\n  Significance: {obj_state.significance}"
            
            entity_parts.append(obj_text)
    
    entity_states_text = ""
    if entity_parts:
        entity_states_text = "\n" + "\n".join(entity_parts) + "\n"
    
    # 5. Chapter metadata
    chapter_context = ""
    if chapter.location_name or chapter.time_period or chapter.scenario:
        chapter_context = "\nChapter Context:\n"
        if chapter.location_name:
            chapter_context += f"Location: {chapter.location_name}\n"
        if chapter.time_period:
            chapter_context += f"Time Period: {chapter.time_period}\n"
        if chapter.scenario:
            chapter_context += f"Scenario: {chapter.scenario}\n"
    
    # Build prompt based on whether we have existing summary
    existing_summary = chapter.auto_summary
    
    if existing_summary:
        # Incremental update: extend existing summary
        prompt = f"""You are creating a cohesive chapter summary. You have an existing summary and new scenes to incorporate.

{story_so_far_text}{previous_chapter_text}{characters_text}{entity_states_text}{chapter_context}
Existing Chapter Summary (Scenes 1-{last_summary_count}):
{existing_summary}

New Scenes to Add (Scenes {last_summary_count + 1}-{chapter.scenes_count}):
{new_scenes_text}

Instructions:
- Create a cohesive summary that combines the existing summary with the new scenes
- Maintain narrative flow and chronological order
- Highlight key events, character developments, and plot progression
- Keep the summary engaging and comprehensive (3-4 paragraphs)
- Focus on what happens in THIS chapter only
- Maintain consistency with the story context provided

Updated Chapter {chapter.chapter_number} Summary:"""
    else:
        # First summary: create from scratch
        prompt = f"""Summarize the following scenes from Chapter {chapter.chapter_number} into a cohesive summary.

{story_so_far_text}{previous_chapter_text}{characters_text}{entity_states_text}{chapter_context}
Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}

Scenes to Summarize:
{new_scenes_text}

Instructions:
- Summarize ONLY Chapter {chapter.chapter_number}'s content
- Maintain consistency with the story context provided
- Capture key events, character developments, and plot progression
- Keep summary engaging and comprehensive (2-3 paragraphs)

Chapter {chapter.chapter_number} Summary:"""
    
    # Get user settings
    from ..models import UserSettings
    user_settings_obj = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    user_settings = user_settings_obj.to_dict() if user_settings_obj else None
    
    if user_settings is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_settings['allow_nsfw'] = user.allow_nsfw
    
    # Generate summary for this batch
    batch_summary = await llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt="You are a helpful assistant that creates cohesive narrative summaries.",
        max_tokens=500  # Slightly more for incremental updates
    )
    
    # Determine scene range for this batch
    batch_start = last_summary_count + 1
    batch_end = chapter.scenes_count
    
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
    
    logger.info(f"[CHAPTER] {'Extended' if existing_summary else 'Created'} summary for chapter {chapter_id}: {len(batch_summary)} chars (scenes {batch_start}-{batch_end}), total batches: {len(all_batches)}")
    
    return combined_summary


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
    
    # Use LLM to create a cohesive "Story So Far" summary
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
    
    # Add allow_nsfw from user to ensure NSFW filter is applied correctly
    if user_settings is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user_settings['allow_nsfw'] = user.allow_nsfw
    
    # Generate story so far
    story_so_far = await llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt="You are a helpful assistant that creates cohesive story summaries from chapter summaries.",
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
    
    # Collect scene IDs for background semantic cleanup BEFORE deleting
    scene_ids_to_cleanup = [scene.id for scene in scenes]
    
    # Delete scenes (CASCADE will handle related database records)
    for scene in scenes:
        db.delete(scene)
    
    # Recalculate scenes_count from active StoryFlow (should be 0 after deletion)
    chapter.scenes_count = llm_service.get_active_scene_count(db, story_id, chapter_id)
    
    # Delete all summary batches for this chapter (CASCADE should handle this, but explicit is clearer)
    batches_deleted = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).delete()
    if batches_deleted > 0:
        logger.info(f"[CHAPTER] Deleted {batches_deleted} summary batch(es) for chapter {chapter_id}")
    
    # Reset chapter metrics
    chapter.context_tokens_used = 0
    chapter.auto_summary = None
    chapter.last_summary_scene_count = 0
    chapter.last_extraction_scene_count = 0  # Also reset extraction count
    chapter.status = ChapterStatus.ACTIVE
    
    db.commit()
    
    # Schedule semantic cleanup in background (don't block response)
    if scene_ids_to_cleanup:
        background_tasks.add_task(
            cleanup_semantic_data_in_background,
            scene_ids=scene_ids_to_cleanup,
            story_id=story_id
        )
    
    logger.info(f"[CHAPTER] Deleted {scene_count} scenes from chapter {chapter_id}")
    
    return {
        "message": "Chapter content deleted successfully",
        "scenes_deleted": scene_count
    }


async def cleanup_semantic_data_in_background(scene_ids: list, story_id: int):
    """Background task to clean up semantic data for deleted scenes"""
    try:
        import asyncio
        # Small delay to ensure database commits from main session are visible
        await asyncio.sleep(0.1)
        
        from ..database import SessionLocal
        bg_db = SessionLocal()
        try:
            from ..services.semantic_integration import cleanup_scene_embeddings
            
            logger.info(f"[CHAPTER-BG] Starting semantic cleanup for {len(scene_ids)} scenes (story {story_id})")
            
            for scene_id in scene_ids:
                try:
                    await cleanup_scene_embeddings(scene_id, bg_db)
                    logger.debug(f"[CHAPTER-BG] Cleaned up semantic data for scene {scene_id}")
                except Exception as e:
                    logger.warning(f"[CHAPTER-BG] Failed to cleanup semantic data for scene {scene_id}: {e}")
                    # Continue with other scenes even if one fails
            
            logger.info(f"[CHAPTER-BG] Completed semantic cleanup for {len(scene_ids)} scenes (story {story_id})")
        finally:
            bg_db.close()
    except Exception as e:
        logger.error(f"[CHAPTER-BG] Failed to cleanup semantic data in background: {e}")
        import traceback
        logger.error(f"[CHAPTER-BG] Traceback: {traceback.format_exc()}")


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
    
    # Get all story characters
    story_chars = db.query(StoryCharacter).filter(
        StoryCharacter.story_id == story_id
    ).all()
    
    # Build response with character details
    characters = []
    for sc in story_chars:
        char = db.query(Character).filter(Character.id == sc.character_id).first()
        if char:
            characters.append({
                "story_character_id": sc.id,
                "character_id": char.id,
                "name": char.name,
                "role": sc.role,
                "description": char.description
            })
    
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
