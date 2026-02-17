from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import World, Story, StoryBranch, User, Scene, Chapter, StoryCharacter, Character
from ..dependencies import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class WorldCreate(BaseModel):
    name: str
    description: Optional[str] = None


class WorldUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class StoryOrderItem(BaseModel):
    story_id: int
    timeline_order: int


class StoryReorder(BaseModel):
    story_orders: list[StoryOrderItem]


@router.get("/")
async def list_worlds(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all worlds owned by the current user"""
    worlds = db.query(World).filter(
        World.creator_id == current_user.id
    ).order_by(World.updated_at.desc().nullsfirst(), World.created_at.desc()).all()

    results = []
    for world in worlds:
        story_count = db.query(func.count(Story.id)).filter(
            Story.world_id == world.id
        ).scalar()
        results.append({
            "id": world.id,
            "name": world.name,
            "description": world.description,
            "story_count": story_count,
            "created_at": world.created_at,
            "updated_at": world.updated_at,
        })

    return results


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_world(
    world_data: WorldCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new world"""
    world = World(
        name=world_data.name,
        description=world_data.description,
        creator_id=current_user.id,
    )
    db.add(world)
    db.commit()
    db.refresh(world)

    return {
        "id": world.id,
        "name": world.name,
        "description": world.description,
        "created_at": world.created_at,
    }


@router.get("/{world_id}")
async def get_world(
    world_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a world with its story count"""
    world = db.query(World).filter(
        World.id == world_id,
        World.creator_id == current_user.id
    ).first()

    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    story_count = db.query(func.count(Story.id)).filter(
        Story.world_id == world.id
    ).scalar()

    return {
        "id": world.id,
        "name": world.name,
        "description": world.description,
        "story_count": story_count,
        "created_at": world.created_at,
        "updated_at": world.updated_at,
    }


@router.put("/{world_id}")
async def update_world(
    world_id: int,
    world_data: WorldUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a world"""
    world = db.query(World).filter(
        World.id == world_id,
        World.creator_id == current_user.id
    ).first()

    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    if world_data.name is not None:
        world.name = world_data.name
    if world_data.description is not None:
        world.description = world_data.description

    db.commit()
    db.refresh(world)

    return {
        "id": world.id,
        "name": world.name,
        "description": world.description,
        "updated_at": world.updated_at,
    }


@router.delete("/{world_id}")
async def delete_world(
    world_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a world (only if it has no stories)"""
    world = db.query(World).filter(
        World.id == world_id,
        World.creator_id == current_user.id
    ).first()

    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    story_count = db.query(func.count(Story.id)).filter(
        Story.world_id == world.id
    ).scalar()

    if story_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete world with {story_count} stories. Move or delete stories first."
        )

    db.delete(world)
    db.commit()

    return {"message": "World deleted successfully"}


@router.get("/{world_id}/stories")
async def list_world_stories(
    world_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all stories in a world"""
    world = db.query(World).filter(
        World.id == world_id,
        World.creator_id == current_user.id
    ).first()

    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    stories = db.query(Story).filter(
        Story.world_id == world_id
    ).order_by(Story.timeline_order.asc().nullslast(), Story.updated_at.desc()).all()

    result = []
    for story in stories:
        branches = db.query(StoryBranch).filter(StoryBranch.story_id == story.id).all()

        # Get scene count on main/current branch
        scene_query = db.query(func.count(Scene.id)).filter(Scene.story_id == story.id)
        if story.current_branch_id:
            scene_query = scene_query.filter(Scene.branch_id == story.current_branch_id)
        scene_count = scene_query.scalar() or 0

        chapter_count = db.query(func.count(Chapter.id)).filter(
            Chapter.story_id == story.id
        ).scalar() or 0

        # Get distinct character names from StoryCharacter records
        char_rows = (
            db.query(Character.name)
            .join(StoryCharacter, StoryCharacter.character_id == Character.id)
            .filter(StoryCharacter.story_id == story.id)
            .distinct()
            .all()
        )
        character_names = [row[0] for row in char_rows]

        result.append({
            "id": story.id,
            "title": story.title,
            "description": story.description,
            "genre": story.genre,
            "status": story.status,
            "content_rating": story.content_rating or "sfw",
            "timeline_order": story.timeline_order,
            "branches": [
                {"id": b.id, "name": b.name, "is_main": b.is_main}
                for b in branches
            ],
            "current_branch_id": story.current_branch_id,
            "scene_count": scene_count,
            "chapter_count": chapter_count,
            "character_names": character_names,
            "created_at": story.created_at,
            "updated_at": story.updated_at,
        })
    return result


@router.put("/{world_id}/stories/reorder")
async def reorder_world_stories(
    world_id: int,
    data: StoryReorder,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set timeline order for stories in a world."""
    world = db.query(World).filter(
        World.id == world_id,
        World.creator_id == current_user.id
    ).first()

    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    for item in data.story_orders:
        story = db.query(Story).filter(
            Story.id == item.story_id,
            Story.world_id == world_id,
        ).first()
        if not story:
            raise HTTPException(
                status_code=404,
                detail=f"Story {item.story_id} not found in this world"
            )
        story.timeline_order = item.timeline_order

    db.commit()
    return {"message": "Timeline order updated"}
