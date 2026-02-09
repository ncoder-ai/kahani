"""
Contradictions API

Endpoints for viewing and resolving detected continuity errors.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models import User, Story, Contradiction
from ..dependencies import get_current_user
from ..services.contradiction_service import ContradictionService

logger = logging.getLogger(__name__)
router = APIRouter()


class ContradictionResponse(BaseModel):
    id: int
    story_id: int
    branch_id: Optional[int]
    scene_sequence: int
    contradiction_type: str
    character_name: Optional[str]
    previous_value: Optional[str]
    current_value: Optional[str]
    severity: str
    resolved: bool
    resolution_note: Optional[str]
    detected_at: Optional[str]
    resolved_at: Optional[str]

    class Config:
        from_attributes = True


class ResolveRequest(BaseModel):
    note: str


@router.get("/stories/{story_id}/contradictions", response_model=List[ContradictionResponse])
async def get_contradictions(
    story_id: int,
    resolved: bool = False,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get contradictions for a story.

    Args:
        story_id: Story ID
        resolved: If True, include resolved contradictions. Default: False (unresolved only)
        branch_id: Optional branch filter
    """
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

    # Query contradictions
    query = db.query(Contradiction).filter(Contradiction.story_id == story_id)

    if not resolved:
        query = query.filter(Contradiction.resolved == False)

    if branch_id:
        query = query.filter(Contradiction.branch_id == branch_id)

    contradictions = query.order_by(Contradiction.detected_at.desc()).all()

    return [
        ContradictionResponse(
            id=c.id,
            story_id=c.story_id,
            branch_id=c.branch_id,
            scene_sequence=c.scene_sequence,
            contradiction_type=c.contradiction_type,
            character_name=c.character_name,
            previous_value=c.previous_value,
            current_value=c.current_value,
            severity=c.severity,
            resolved=c.resolved,
            resolution_note=c.resolution_note,
            detected_at=c.detected_at.isoformat() if c.detected_at else None,
            resolved_at=c.resolved_at.isoformat() if c.resolved_at else None
        )
        for c in contradictions
    ]


@router.patch("/contradictions/{contradiction_id}/resolve", response_model=ContradictionResponse)
async def resolve_contradiction(
    contradiction_id: int,
    request: ResolveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a contradiction as resolved with an explanation.

    Args:
        contradiction_id: Contradiction ID
        request: Resolution note
    """
    # Get contradiction and verify ownership
    contradiction = db.query(Contradiction).filter(
        Contradiction.id == contradiction_id
    ).first()

    if not contradiction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contradiction not found"
        )

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == contradiction.story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this contradiction"
        )

    # Resolve the contradiction
    service = ContradictionService(db)
    resolved = service.resolve(contradiction_id, request.note)

    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve contradiction"
        )

    return ContradictionResponse(
        id=resolved.id,
        story_id=resolved.story_id,
        branch_id=resolved.branch_id,
        scene_sequence=resolved.scene_sequence,
        contradiction_type=resolved.contradiction_type,
        character_name=resolved.character_name,
        previous_value=resolved.previous_value,
        current_value=resolved.current_value,
        severity=resolved.severity,
        resolved=resolved.resolved,
        resolution_note=resolved.resolution_note,
        detected_at=resolved.detected_at.isoformat() if resolved.detected_at else None,
        resolved_at=resolved.resolved_at.isoformat() if resolved.resolved_at else None
    )


@router.get("/stories/{story_id}/contradictions/summary")
async def get_contradictions_summary(
    story_id: int,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a summary of contradictions for a story.

    Returns counts by type and severity.

    Args:
        branch_id: Optional branch ID to filter contradictions. If not provided,
                   returns contradictions for all branches.
    """
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

    # Get contradictions, optionally filtered by branch
    query = db.query(Contradiction).filter(
        Contradiction.story_id == story_id
    )
    if branch_id is not None:
        query = query.filter(Contradiction.branch_id == branch_id)
    contradictions = query.all()

    # Build summary
    summary = {
        "total": len(contradictions),
        "unresolved": sum(1 for c in contradictions if not c.resolved),
        "resolved": sum(1 for c in contradictions if c.resolved),
        "by_type": {},
        "by_severity": {}
    }

    for c in contradictions:
        if not c.resolved:  # Only count unresolved for breakdown
            summary["by_type"][c.contradiction_type] = summary["by_type"].get(c.contradiction_type, 0) + 1
            summary["by_severity"][c.severity] = summary["by_severity"].get(c.severity, 0) + 1

    return summary
