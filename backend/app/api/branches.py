"""
Branch API Endpoints

Manages story branches including creation (forking), switching, listing, and deletion.
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Story, StoryBranch, Scene, Chapter, StoryCharacter
from ..services.branch_service import get_branch_service
from .story_helpers import get_or_create_user_settings
from .story_tasks import initialize_branch_entity_states_in_background
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories/{story_id}/branches", tags=["branches"])


# Pydantic Models for Request/Response
class BranchCreate(BaseModel):
    name: str
    description: Optional[str] = None
    fork_from_scene_sequence: int
    activate: bool = True


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class BranchResponse(BaseModel):
    id: int
    story_id: int
    name: str
    description: Optional[str]
    is_main: bool
    is_active: bool
    forked_from_branch_id: Optional[int]
    forked_at_scene_sequence: Optional[int]
    scene_count: int
    chapter_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class BranchListResponse(BaseModel):
    branches: List[BranchResponse]
    active_branch_id: Optional[int]


class BranchCreateResponse(BaseModel):
    branch: BranchResponse
    stats: dict


def _get_story_or_404(db: Session, story_id: int, user_id: int) -> Story:
    """Helper to get story or raise 404"""
    story = db.query(Story).filter(Story.id == story_id, Story.owner_id == user_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _branch_to_response(branch: StoryBranch, db: Session) -> BranchResponse:
    """Convert StoryBranch model to response"""
    scene_count = db.query(Scene).filter(Scene.branch_id == branch.id).count()
    chapter_count = db.query(Chapter).filter(Chapter.branch_id == branch.id).count()
    
    return BranchResponse(
        id=branch.id,
        story_id=branch.story_id,
        name=branch.name,
        description=branch.description,
        is_main=branch.is_main,
        is_active=branch.is_active,
        forked_from_branch_id=branch.forked_from_branch_id,
        forked_at_scene_sequence=branch.forked_at_scene_sequence,
        scene_count=scene_count,
        chapter_count=chapter_count,
        created_at=branch.created_at
    )


@router.get("", response_model=BranchListResponse)
async def list_branches(
    story_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    List all branches for a story.
    
    Returns all branches with their metadata, ordered by creation date.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    branches = branch_service.list_branches(db, story_id)
    active_branch = branch_service.get_active_branch(db, story_id)
    
    return BranchListResponse(
        branches=[_branch_to_response(b, db) for b in branches],
        active_branch_id=active_branch.id if active_branch else None
    )


@router.get("/active", response_model=BranchResponse)
async def get_active_branch(
    story_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get the currently active branch for a story.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    active_branch = branch_service.get_active_branch(db, story_id)
    if not active_branch:
        raise HTTPException(status_code=404, detail="No active branch found")
    
    return _branch_to_response(active_branch, db)


@router.post("", response_model=BranchCreateResponse)
async def create_branch(
    story_id: int,
    branch_data: BranchCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Create a new branch by forking from a specific scene.

    This performs a deep clone of all story data up to and including
    the specified scene sequence number. The new branch is independent
    and isolated from the source branch.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()

    try:
        branch, stats = branch_service.create_branch(
            db=db,
            story_id=story_id,
            name=branch_data.name,
            fork_from_scene_sequence=branch_data.fork_from_scene_sequence,
            description=branch_data.description,
            activate=branch_data.activate
        )

        # Get user settings for entity state extraction
        user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

        # Initialize entity states for the new branch in background
        # (restores from cloned batch and extracts remaining scenes up to fork point)
        asyncio.create_task(initialize_branch_entity_states_in_background(
            story_id=story_id,
            branch_id=branch.id,
            fork_scene_sequence=branch_data.fork_from_scene_sequence,
            user_id=current_user.id,
            user_settings=user_settings
        ))
        logger.info(f"[BRANCH] Created branch {branch.id} for story {story_id}, scheduled entity state initialization")

        return BranchCreateResponse(
            branch=_branch_to_response(branch, db),
            stats=stats
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create branch: {e}")
        raise HTTPException(status_code=500, detail="Failed to create branch")


@router.get("/{branch_id}", response_model=BranchResponse)
async def get_branch(
    story_id: int,
    branch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get details for a specific branch.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    branch = branch_service.get_branch(db, branch_id)
    if not branch or branch.story_id != story_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    return _branch_to_response(branch, db)


@router.put("/{branch_id}/activate")
async def activate_branch(
    story_id: int,
    branch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Switch to a different branch.
    
    This sets the specified branch as the active branch for the story.
    All subsequent operations will use this branch.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    success = branch_service.set_active_branch(db, story_id, branch_id)
    if not success:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    branch = branch_service.get_branch(db, branch_id)
    return {
        "success": True,
        "message": f"Switched to branch '{branch.name}'",
        "branch": _branch_to_response(branch, db)
    }


@router.patch("/{branch_id}", response_model=BranchResponse)
async def update_branch(
    story_id: int,
    branch_id: int,
    branch_data: BranchUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Update branch name or description.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    branch = branch_service.get_branch(db, branch_id)
    if not branch or branch.story_id != story_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    if branch_data.name is not None:
        success = branch_service.rename_branch(
            db, branch_id, branch_data.name, branch_data.description
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update branch")
    
    # Refresh branch data
    branch = branch_service.get_branch(db, branch_id)
    return _branch_to_response(branch, db)


@router.delete("/{branch_id}")
async def delete_branch(
    story_id: int,
    branch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Delete a branch.
    
    Cannot delete the main branch or the only remaining branch.
    If the active branch is deleted, switches to the main branch.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    branch = branch_service.get_branch(db, branch_id)
    if not branch or branch.story_id != story_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    if branch.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete the main branch")
    
    success = branch_service.delete_branch(db, branch_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete branch")
    
    return {"success": True, "message": f"Deleted branch '{branch.name}'"}


@router.get("/{branch_id}/stats")
async def get_branch_stats(
    story_id: int,
    branch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get detailed statistics for a branch.
    """
    story = _get_story_or_404(db, story_id, current_user.id)
    branch_service = get_branch_service()
    
    branch = branch_service.get_branch(db, branch_id)
    if not branch or branch.story_id != story_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    stats = branch_service.get_branch_stats(db, branch_id)
    
    return {
        "branch_id": branch_id,
        "branch_name": branch.name,
        **stats
    }

