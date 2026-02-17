"""
Draft Story Management API endpoints.

This module handles CRUD operations for draft stories including creation,
retrieval, finalization, and deletion.
Extracted from stories.py for better organization.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Story, StoryStatus, User, Character, StoryCharacter
from ..api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["drafts"])


# =============================================================================
# DRAFT STORY MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/draft")
async def create_draft_story(
    story_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update a draft story with incremental progress"""

    step = story_data.get('step', 0)
    story_id = story_data.get('story_id')  # Allow specifying which draft to update

    if story_id:
        # Update specific draft story
        story = db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == current_user.id,
            Story.status == StoryStatus.DRAFT
        ).first()

        if not story:
            raise HTTPException(status_code=404, detail="Draft story not found")
    else:
        # Check if there's already a draft for this user
        existing_draft = db.query(Story).filter(
            Story.owner_id == current_user.id,
            Story.status == StoryStatus.DRAFT
        ).first()

        if existing_draft:
            story = existing_draft
        else:
            story = None

    if story:
        # Update existing draft
        story.creation_step = step
        story.draft_data = story_data

        # Update story fields as they become available
        if 'title' in story_data and story_data['title']:
            story.title = story_data['title']
        if 'description' in story_data:
            story.description = story_data.get('description') or ''
        if 'genre' in story_data and story_data['genre']:
            story.genre = story_data['genre']
        if 'tone' in story_data and story_data['tone']:
            story.tone = story_data['tone']
        if 'world_setting' in story_data:
            story.world_setting = story_data.get('world_setting') or ''
        if 'initial_premise' in story_data:
            story.initial_premise = story_data.get('initial_premise') or ''
        if 'scenario' in story_data:
            story.scenario = story_data.get('scenario') or ''

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
            scenario=story_data.get('scenario', ''),
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


@router.get("/draft/{story_id}")
async def get_specific_draft_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific draft story by ID"""

    draft = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id,
        Story.status == StoryStatus.DRAFT
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft story not found")

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
    """Convert a draft story to active status and process draft data"""

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

    # Extract data from draft_data JSON
    draft_data = story.draft_data or {}

    # Transfer all story fields from draft_data to story columns
    # (Only update if not already set or if draft_data has a value)
    if 'description' in draft_data and draft_data.get('description'):
        story.description = draft_data['description']
    if 'world_setting' in draft_data and draft_data.get('world_setting'):
        story.world_setting = draft_data['world_setting']
    if 'initial_premise' in draft_data and draft_data.get('initial_premise'):
        story.initial_premise = draft_data['initial_premise']
    if 'scenario' in draft_data and draft_data.get('scenario'):
        story.scenario = draft_data['scenario']
        logger.info(f"[FINALIZE] Transferred scenario to story {story_id}")

    # Transfer world_id from draft_data if provided
    if 'world_id' in draft_data and draft_data.get('world_id'):
        from ..models import World
        world = db.query(World).filter(
            World.id == draft_data['world_id'],
            World.creator_id == current_user.id
        ).first()
        if world:
            story.world_id = world.id
            logger.info(f"[FINALIZE] Set world_id={world.id} for story {story_id}")
    if 'timeline_order' in draft_data and draft_data.get('timeline_order') is not None:
        story.timeline_order = draft_data['timeline_order']
        logger.info(f"[FINALIZE] Set timeline_order={story.timeline_order} for story {story_id}")

    # Set content_rating - use draft_data value if provided, otherwise default based on user's NSFW permission
    if 'content_rating' in draft_data and draft_data.get('content_rating'):
        story.content_rating = draft_data['content_rating']
    elif not story.content_rating:
        # Default: if user allows NSFW, default to NSFW; otherwise SFW
        story.content_rating = "nsfw" if current_user.allow_nsfw else "sfw"
        logger.info(f"[FINALIZE] Set default content_rating={story.content_rating} for story {story_id} (user allow_nsfw={current_user.allow_nsfw})")

    # Ensure the story has a main branch (required for chapters and character association)
    # This needs to be done BEFORE processing characters so they can be associated with the branch
    from ..services.branch_service import get_branch_service
    branch_service = get_branch_service()
    main_branch = branch_service.ensure_main_branch(db, story_id)

    # Set the story's current branch to the main branch
    if not story.current_branch_id:
        story.current_branch_id = main_branch.id
        logger.info(f"[FINALIZE] Set current_branch_id={main_branch.id} for story {story_id}")

    # Process characters from draft_data and create StoryCharacter relationships
    characters_data = draft_data.get('characters', [])
    if characters_data:
        logger.info(f"[FINALIZE] Processing {len(characters_data)} characters for story {story_id}")

        for char_data in characters_data:
            # If character has an ID, use it directly (from brainstorm flow)
            if 'id' in char_data and char_data['id']:
                character = db.query(Character).filter(
                    Character.id == char_data['id']
                ).first()

                if character:
                    logger.info(f"[FINALIZE] Using character by ID: {character.name} (ID: {character.id})")
                else:
                    logger.warning(f"[FINALIZE] Character ID {char_data['id']} not found, skipping")
                    continue
            else:
                # Check if character already exists by name
                existing_char = db.query(Character).filter(
                    Character.name == char_data.get('name'),
                    Character.creator_id == current_user.id
                ).first()

                if existing_char:
                    # Use existing character
                    character = existing_char
                    logger.info(f"[FINALIZE] Using existing character by name: {character.name} (ID: {character.id})")
                else:
                    # Create new character (without role - role is story-specific)
                    character = Character(
                        name=char_data.get('name', 'Unnamed'),
                        description=char_data.get('description', ''),
                        creator_id=current_user.id,
                        is_template=False,
                        is_public=False
                    )
                    db.add(character)
                    db.flush()  # Get the character ID
                    logger.info(f"[FINALIZE] Created new character: {character.name} (ID: {character.id})")

            # Check if StoryCharacter relationship already exists for this branch
            existing_story_char = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id,
                StoryCharacter.branch_id == main_branch.id,
                StoryCharacter.character_id == character.id
            ).first()

            if not existing_story_char:
                # Create StoryCharacter relationship with story-specific role and branch
                story_character = StoryCharacter(
                    story_id=story_id,
                    branch_id=main_branch.id,
                    character_id=character.id,
                    role=char_data.get('role', '')  # Store role in the relationship
                )
                db.add(story_character)
                logger.info(f"[FINALIZE] Linked character {character.name} to story {story_id}, branch {main_branch.id} with role: {char_data.get('role', 'N/A')}")

                # Mark NPC as converted if it was tracked as an NPC
                try:
                    from ..services.npc_tracking_service import NPCTrackingService
                    from ..models import UserSettings
                    user_settings = db.query(UserSettings).filter(
                        UserSettings.user_id == current_user.id
                    ).first()
                    if user_settings:
                        user_settings_dict = user_settings.to_dict()
                        user_settings_dict['allow_nsfw'] = current_user.allow_nsfw
                        npc_service = NPCTrackingService(current_user.id, user_settings_dict)
                        npc_service.mark_npc_as_converted(db, story_id, character.name)
                except Exception as e:
                    logger.warning(f"Failed to mark NPC as converted during finalization: {e}")
                    # Don't fail story finalization if NPC marking fails

    # Mark as active
    logger.info(f"[FINALIZE] Setting story {story_id} to ACTIVE status")
    story.status = StoryStatus.ACTIVE
    story.creation_step = 6  # Completed
    logger.info(f"[FINALIZE] Story {story_id} status updated: {story.status}, step: {story.creation_step}")

    db.commit()
    db.refresh(story)

    logger.info(f"[FINALIZE] Story {story_id} committed. Final status: {story.status}, step: {story.creation_step}")

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
