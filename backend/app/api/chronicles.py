"""
Chronicle & Lorebook CRUD endpoints for author review and curation.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel

from ..database import get_db
from ..models import (
    World, User, Character, CharacterChronicle, LocationLorebook, ChronicleEntryType,
)
from ..dependencies import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Pydantic schemas ---

class ChronicleUpdate(BaseModel):
    description: Optional[str] = None
    entry_type: Optional[str] = None
    is_defining: Optional[bool] = None


class LorebookUpdate(BaseModel):
    location_name: Optional[str] = None
    event_description: Optional[str] = None


# --- Helper ---

def _verify_world_ownership(db: Session, world_id: int, user_id: int) -> World:
    world = db.query(World).filter(
        World.id == world_id,
        World.creator_id == user_id,
    ).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found")
    return world


# === World character discovery ===

@router.get("/worlds/{world_id}/characters")
async def list_world_characters(
    world_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all characters that have chronicle entries in a world."""
    _verify_world_ownership(db, world_id, current_user.id)

    results = db.query(
        CharacterChronicle.character_id,
        Character.name.label("character_name"),
        func.count(CharacterChronicle.id).label("entry_count"),
    ).join(
        Character, CharacterChronicle.character_id == Character.id
    ).filter(
        CharacterChronicle.world_id == world_id,
    ).group_by(
        CharacterChronicle.character_id, Character.name
    ).order_by(Character.name).all()

    return [
        {
            "character_id": r.character_id,
            "character_name": r.character_name,
            "entry_count": r.entry_count,
        }
        for r in results
    ]


# === Chronicle endpoints ===

@router.get("/worlds/{world_id}/characters/{character_id}/chronicle")
async def list_character_chronicle(
    world_id: int,
    character_id: int,
    story_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List chronicle entries for a character in a world."""
    _verify_world_ownership(db, world_id, current_user.id)

    query = db.query(CharacterChronicle).filter(
        CharacterChronicle.world_id == world_id,
        CharacterChronicle.character_id == character_id,
    )
    if story_id is not None:
        query = query.filter(CharacterChronicle.story_id == story_id)
    if branch_id is not None:
        query = query.filter(CharacterChronicle.branch_id == branch_id)

    entries = query.order_by(CharacterChronicle.sequence_order.asc()).all()

    return [
        {
            "id": e.id,
            "entry_type": e.entry_type.value,
            "description": e.description,
            "is_defining": e.is_defining,
            "sequence_order": e.sequence_order,
            "scene_id": e.scene_id,
            "story_id": e.story_id,
            "branch_id": e.branch_id,
            "created_at": e.created_at,
        }
        for e in entries
    ]


@router.put("/chronicles/{entry_id}")
async def update_chronicle_entry(
    entry_id: int,
    data: ChronicleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a chronicle entry (description, entry_type, is_defining)."""
    entry = db.query(CharacterChronicle).filter(
        CharacterChronicle.id == entry_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Chronicle entry not found")

    _verify_world_ownership(db, entry.world_id, current_user.id)

    if data.description is not None:
        entry.description = data.description
    if data.entry_type is not None:
        valid_types = {e.value for e in ChronicleEntryType}
        if data.entry_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid entry_type. Must be one of: {valid_types}")
        entry.entry_type = ChronicleEntryType(data.entry_type)
    if data.is_defining is not None:
        entry.is_defining = data.is_defining

    db.commit()
    db.refresh(entry)

    return {
        "id": entry.id,
        "entry_type": entry.entry_type.value,
        "description": entry.description,
        "is_defining": entry.is_defining,
    }


@router.delete("/chronicles/{entry_id}")
async def delete_chronicle_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a chronicle entry."""
    entry = db.query(CharacterChronicle).filter(
        CharacterChronicle.id == entry_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Chronicle entry not found")

    _verify_world_ownership(db, entry.world_id, current_user.id)

    db.delete(entry)
    db.commit()
    return {"message": "Chronicle entry deleted"}


# === Lorebook endpoints ===

@router.get("/worlds/{world_id}/locations")
async def list_world_locations(
    world_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all locations in a world with entry counts."""
    _verify_world_ownership(db, world_id, current_user.id)

    results = db.query(
        LocationLorebook.location_name,
        func.count(LocationLorebook.id).label("entry_count"),
    ).filter(
        LocationLorebook.world_id == world_id,
    ).group_by(LocationLorebook.location_name).order_by(
        LocationLorebook.location_name
    ).all()

    return [
        {"location_name": r.location_name, "entry_count": r.entry_count}
        for r in results
    ]


@router.get("/worlds/{world_id}/locations/{location_name}/lorebook")
async def list_location_lorebook(
    world_id: int,
    location_name: str,
    story_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List lorebook entries for a location."""
    _verify_world_ownership(db, world_id, current_user.id)

    query = db.query(LocationLorebook).filter(
        LocationLorebook.world_id == world_id,
        LocationLorebook.location_name == location_name,
    )
    if story_id is not None:
        query = query.filter(LocationLorebook.story_id == story_id)
    if branch_id is not None:
        query = query.filter(LocationLorebook.branch_id == branch_id)

    entries = query.order_by(LocationLorebook.sequence_order.asc()).all()

    return [
        {
            "id": e.id,
            "location_name": e.location_name,
            "event_description": e.event_description,
            "sequence_order": e.sequence_order,
            "scene_id": e.scene_id,
            "story_id": e.story_id,
            "branch_id": e.branch_id,
            "created_at": e.created_at,
        }
        for e in entries
    ]


@router.put("/lorebook/{entry_id}")
async def update_lorebook_entry(
    entry_id: int,
    data: LorebookUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a lorebook entry."""
    entry = db.query(LocationLorebook).filter(
        LocationLorebook.id == entry_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Lorebook entry not found")

    _verify_world_ownership(db, entry.world_id, current_user.id)

    if data.location_name is not None:
        entry.location_name = data.location_name
    if data.event_description is not None:
        entry.event_description = data.event_description

    db.commit()
    db.refresh(entry)

    return {
        "id": entry.id,
        "location_name": entry.location_name,
        "event_description": entry.event_description,
    }


@router.delete("/lorebook/{entry_id}")
async def delete_lorebook_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a lorebook entry."""
    entry = db.query(LocationLorebook).filter(
        LocationLorebook.id == entry_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Lorebook entry not found")

    _verify_world_ownership(db, entry.world_id, current_user.id)

    db.delete(entry)
    db.commit()
    return {"message": "Lorebook entry deleted"}
