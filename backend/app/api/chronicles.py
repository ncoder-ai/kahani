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
    World, Story, User, Character,
    CharacterChronicle, LocationLorebook, ChronicleEntryType, CharacterSnapshot,
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


class SnapshotGenerate(BaseModel):
    up_to_story_id: int
    branch_id: Optional[int] = None


class SnapshotUpdate(BaseModel):
    snapshot_text: str
    branch_id: Optional[int] = None


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


# === Character Snapshot endpoints ===

@router.get("/worlds/{world_id}/characters/{character_id}/snapshot")
async def get_character_snapshot(
    world_id: int,
    character_id: int,
    branch_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current snapshot for a character in a world (or null). Optionally filter by branch."""
    _verify_world_ownership(db, world_id, current_user.id)

    from sqlalchemy import or_

    snapshot_query = db.query(CharacterSnapshot).filter(
        CharacterSnapshot.world_id == world_id,
        CharacterSnapshot.character_id == character_id,
    )
    if branch_id is not None:
        # Prefer branch-specific, fall back to NULL
        snapshot_query = snapshot_query.filter(
            or_(CharacterSnapshot.branch_id == branch_id, CharacterSnapshot.branch_id.is_(None))
        ).order_by(CharacterSnapshot.branch_id.desc().nullslast())
    else:
        snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id.is_(None))
    snapshot = snapshot_query.first()

    if not snapshot:
        return {
            "snapshot_text": None,
            "chronicle_entry_count": 0,
            "current_entry_count": 0,
            "is_stale": False,
            "timeline_order": None,
            "up_to_story_id": None,
            "branch_id": None,
            "created_at": None,
            "updated_at": None,
        }

    # Count current entries up to the snapshot's timeline point
    stories_query = db.query(Story.id).filter(Story.world_id == world_id)
    if snapshot.timeline_order is not None:
        stories_query = stories_query.filter(
            or_(
                Story.timeline_order <= snapshot.timeline_order,
                Story.timeline_order.is_(None),
            )
        )
    eligible_story_ids = [r[0] for r in stories_query.all()]

    current_count = db.query(func.count(CharacterChronicle.id)).filter(
        CharacterChronicle.world_id == world_id,
        CharacterChronicle.character_id == character_id,
        CharacterChronicle.story_id.in_(eligible_story_ids) if eligible_story_ids else False,
    ).scalar() or 0

    return {
        "snapshot_text": snapshot.snapshot_text,
        "chronicle_entry_count": snapshot.chronicle_entry_count,
        "current_entry_count": current_count,
        "is_stale": current_count > snapshot.chronicle_entry_count,
        "timeline_order": snapshot.timeline_order,
        "up_to_story_id": snapshot.up_to_story_id,
        "branch_id": snapshot.branch_id,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
    }


@router.post("/worlds/{world_id}/characters/{character_id}/snapshot")
async def generate_snapshot(
    world_id: int,
    character_id: int,
    data: SnapshotGenerate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate/regenerate a character snapshot via LLM."""
    _verify_world_ownership(db, world_id, current_user.id)

    from .story_helpers import get_or_create_user_settings
    user_settings = get_or_create_user_settings(current_user.id, db, current_user)

    from ..services.chronicle_extraction_service import generate_character_snapshot
    try:
        result = await generate_character_snapshot(
            world_id=world_id,
            character_id=character_id,
            up_to_story_id=data.up_to_story_id,
            user_id=current_user.id,
            user_settings=user_settings,
            db=db,
            branch_id=data.branch_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SNAPSHOT] Generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Snapshot generation failed")


@router.put("/worlds/{world_id}/characters/{character_id}/snapshot")
async def update_snapshot(
    world_id: int,
    character_id: int,
    data: SnapshotUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually edit snapshot text."""
    _verify_world_ownership(db, world_id, current_user.id)

    snapshot_query = db.query(CharacterSnapshot).filter(
        CharacterSnapshot.world_id == world_id,
        CharacterSnapshot.character_id == character_id,
    )
    if data.branch_id is not None:
        snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id == data.branch_id)
    else:
        snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id.is_(None))
    snapshot = snapshot_query.first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot exists for this character")

    snapshot.snapshot_text = data.snapshot_text
    db.commit()
    db.refresh(snapshot)

    return {
        "snapshot_text": snapshot.snapshot_text,
        "chronicle_entry_count": snapshot.chronicle_entry_count,
        "timeline_order": snapshot.timeline_order,
        "up_to_story_id": snapshot.up_to_story_id,
        "branch_id": snapshot.branch_id,
        "updated_at": snapshot.updated_at,
    }
