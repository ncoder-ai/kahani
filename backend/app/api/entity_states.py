"""
Entity State Management API endpoints.

This module handles CRUD operations for entity states (characters, locations, objects).
Extracted from stories.py for better organization.
"""

import logging
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Story, User
from ..api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["entity-states"])


# =============================================================================
# PYDANTIC MODELS FOR UPDATES
# =============================================================================

class CharacterStateUpdate(BaseModel):
    """Update model for character state"""
    current_location: Optional[str] = None
    physical_condition: Optional[str] = None
    appearance: Optional[str] = None
    possessions: Optional[List[str]] = None
    emotional_state: Optional[str] = None
    current_goal: Optional[str] = None
    active_conflicts: Optional[List[str]] = None
    knowledge: Optional[List[str]] = None
    secrets: Optional[List[str]] = None
    relationships: Optional[Dict[str, str]] = None
    arc_stage: Optional[str] = None
    arc_progress: Optional[float] = None
    recent_decisions: Optional[List[str]] = None
    recent_actions: Optional[List[str]] = None


class LocationStateUpdate(BaseModel):
    """Update model for location state"""
    location_name: Optional[str] = None
    condition: Optional[str] = None
    atmosphere: Optional[str] = None
    notable_features: Optional[List[str]] = None
    current_occupants: Optional[List[str]] = None
    significant_events: Optional[List[str]] = None
    time_of_day: Optional[str] = None
    weather: Optional[str] = None


class ObjectStateUpdate(BaseModel):
    """Update model for object state"""
    object_name: Optional[str] = None
    condition: Optional[str] = None
    current_location: Optional[str] = None
    current_owner_id: Optional[int] = None
    significance: Optional[str] = None
    object_type: Optional[str] = None
    powers: Optional[List[str]] = None
    limitations: Optional[List[str]] = None
    origin: Optional[str] = None
    previous_owners: Optional[List[str]] = None
    recent_events: Optional[List[str]] = None


# =============================================================================
# ENTITY STATE ENDPOINTS
# =============================================================================

@router.get("/{story_id}/entity-states")
async def get_entity_states(
    story_id: int,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all entity states (characters, locations, objects) for a story.

    Returns comprehensive state data for review and editing.

    Args:
        branch_id: Optional branch ID to filter states. If not provided,
                   uses the active branch for the story.
    """
    from ..models import CharacterState, LocationState, ObjectState, Character, StoryBranch

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )

    # Use provided branch_id or fall back to active branch
    if branch_id is None:
        active_branch = db.query(StoryBranch).filter(
            StoryBranch.story_id == story_id,
            StoryBranch.is_active == True
        ).first()
        branch_id = active_branch.id if active_branch else None

    # Get character states with character names
    char_states_query = db.query(CharacterState).filter(
        CharacterState.story_id == story_id
    )
    if branch_id:
        char_states_query = char_states_query.filter(CharacterState.branch_id == branch_id)
    char_states = char_states_query.order_by(CharacterState.last_updated_scene.desc()).all()

    # Build character ID to name mapping
    char_ids = {cs.character_id for cs in char_states}
    characters = db.query(Character).filter(Character.id.in_(char_ids)).all() if char_ids else []
    char_id_to_name = {c.id: c.name for c in characters}

    # Format character states
    character_states_result = []
    for cs in char_states:
        state_dict = cs.to_dict()
        state_dict["character_name"] = char_id_to_name.get(cs.character_id, "Unknown")
        character_states_result.append(state_dict)

    # Get location states
    loc_states_query = db.query(LocationState).filter(
        LocationState.story_id == story_id
    )
    if branch_id:
        loc_states_query = loc_states_query.filter(LocationState.branch_id == branch_id)
    loc_states = loc_states_query.order_by(LocationState.last_updated_scene.desc()).all()

    location_states_result = [ls.to_dict() for ls in loc_states]

    # Get object states with owner names
    obj_states_query = db.query(ObjectState).filter(
        ObjectState.story_id == story_id
    )
    if branch_id:
        obj_states_query = obj_states_query.filter(ObjectState.branch_id == branch_id)
    obj_states = obj_states_query.order_by(ObjectState.last_updated_scene.desc()).all()

    # Get owner names for objects
    owner_ids = {os.current_owner_id for os in obj_states if os.current_owner_id}
    if owner_ids:
        owners = db.query(Character).filter(Character.id.in_(owner_ids)).all()
        owner_id_to_name = {c.id: c.name for c in owners}
    else:
        owner_id_to_name = {}

    object_states_result = []
    for os in obj_states:
        state_dict = os.to_dict()
        state_dict["current_owner_name"] = owner_id_to_name.get(os.current_owner_id) if os.current_owner_id else None
        object_states_result.append(state_dict)

    return {
        "story_id": story_id,
        "branch_id": branch_id,
        "character_states": character_states_result,
        "location_states": location_states_result,
        "object_states": object_states_result,
        "counts": {
            "characters": len(character_states_result),
            "locations": len(location_states_result),
            "objects": len(object_states_result)
        }
    }


@router.delete("/{story_id}/entity-states/characters/{state_id}")
async def delete_character_state(
    story_id: int,
    state_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a character state entry."""
    from ..models import CharacterState

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    state = db.query(CharacterState).filter(
        CharacterState.id == state_id,
        CharacterState.story_id == story_id
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Character state not found")

    db.delete(state)
    db.commit()

    logger.info(f"[ENTITY_STATE_DELETE] Deleted character state {state_id} from story {story_id}")

    return {"message": "Character state deleted successfully", "deleted_id": state_id}


@router.delete("/{story_id}/entity-states/locations/{state_id}")
async def delete_location_state(
    story_id: int,
    state_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a location state entry."""
    from ..models import LocationState

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    state = db.query(LocationState).filter(
        LocationState.id == state_id,
        LocationState.story_id == story_id
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Location state not found")

    db.delete(state)
    db.commit()

    logger.info(f"[ENTITY_STATE_DELETE] Deleted location state {state_id} from story {story_id}")

    return {"message": "Location state deleted successfully", "deleted_id": state_id}


@router.delete("/{story_id}/entity-states/objects/{state_id}")
async def delete_object_state(
    story_id: int,
    state_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an object state entry."""
    from ..models import ObjectState

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    state = db.query(ObjectState).filter(
        ObjectState.id == state_id,
        ObjectState.story_id == story_id
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Object state not found")

    db.delete(state)
    db.commit()

    logger.info(f"[ENTITY_STATE_DELETE] Deleted object state {state_id} from story {story_id}")

    return {"message": "Object state deleted successfully", "deleted_id": state_id}


@router.put("/{story_id}/entity-states/characters/{state_id}")
async def update_character_state(
    story_id: int,
    state_id: int,
    update_data: CharacterStateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a character state entry."""
    from ..models import CharacterState

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    state = db.query(CharacterState).filter(
        CharacterState.id == state_id,
        CharacterState.story_id == story_id
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Character state not found")

    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(state, field, value)

    db.commit()
    db.refresh(state)

    logger.info(f"[ENTITY_STATE_UPDATE] Updated character state {state_id} in story {story_id}")

    return {"message": "Character state updated successfully", "state": state.to_dict()}


@router.put("/{story_id}/entity-states/locations/{state_id}")
async def update_location_state(
    story_id: int,
    state_id: int,
    update_data: LocationStateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a location state entry."""
    from ..models import LocationState

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    state = db.query(LocationState).filter(
        LocationState.id == state_id,
        LocationState.story_id == story_id
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Location state not found")

    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(state, field, value)

    db.commit()
    db.refresh(state)

    logger.info(f"[ENTITY_STATE_UPDATE] Updated location state {state_id} in story {story_id}")

    return {"message": "Location state updated successfully", "state": state.to_dict()}


@router.put("/{story_id}/entity-states/objects/{state_id}")
async def update_object_state(
    story_id: int,
    state_id: int,
    update_data: ObjectStateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an object state entry."""
    from ..models import ObjectState

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    state = db.query(ObjectState).filter(
        ObjectState.id == state_id,
        ObjectState.story_id == story_id
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Object state not found")

    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(state, field, value)

    db.commit()
    db.refresh(state)

    logger.info(f"[ENTITY_STATE_UPDATE] Updated object state {state_id} in story {story_id}")

    return {"message": "Object state updated successfully", "state": state.to_dict()}
