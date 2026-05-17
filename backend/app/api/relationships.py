"""
Relationship Graph API endpoints.

Provides endpoints for querying character relationships:
- List relationship summaries
- Get relationship history between two characters
- Get graph data for visualization
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from ..database import get_db
from ..models import CharacterRelationship, RelationshipSummary, Story
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stories/{story_id}/relationships", tags=["relationships"])


def _verify_story_ownership(story_id: int, current_user, db: Session):
    """Verify the current user owns the story. Raises 404 if not found or not owned."""
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _format_summary(s: RelationshipSummary) -> dict:
    """Format a relationship summary for API response."""
    return {
        "id": s.id,
        "characters": [s.character_a, s.character_b],
        "type": s.current_type,
        "strength": s.current_strength,
        "trajectory": s.trajectory,
        "arc": s.arc_summary,
        "last_change": s.last_change,
        "interactions": s.total_interactions,
        "last_scene": s.last_scene_sequence,
        "initial_type": s.initial_type,
        "initial_strength": s.initial_strength,
    }


def _format_event(e: CharacterRelationship) -> dict:
    """Format a relationship event for API response."""
    return {
        "id": e.id,
        "characters": [e.character_a, e.character_b],
        "type": e.relationship_type,
        "strength": e.strength,
        "scene_sequence": e.scene_sequence,
        "change": e.change_description,
        "sentiment": e.change_sentiment,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("")
async def get_relationships(
    story_id: int,
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    character: Optional[str] = Query(None, description="Filter by character name"),
    min_strength: Optional[float] = Query(None, description="Minimum strength threshold"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all relationship summaries for a story."""
    _verify_story_ownership(story_id, current_user, db)
    query = db.query(RelationshipSummary).filter(
        RelationshipSummary.story_id == story_id
    )

    if branch_id is not None:
        query = query.filter(RelationshipSummary.branch_id == branch_id)

    if character:
        query = query.filter(
            (RelationshipSummary.character_a == character) |
            (RelationshipSummary.character_b == character)
        )

    summaries = query.all()

    # Apply strength filter after fetching (if specified)
    if min_strength is not None:
        summaries = [s for s in summaries if abs(s.current_strength or 0) >= min_strength]

    # Sort by absolute strength (strongest first)
    summaries.sort(key=lambda s: abs(s.current_strength or 0), reverse=True)

    return {
        "relationships": [_format_summary(s) for s in summaries],
        "count": len(summaries)
    }


@router.get("/history/{character_a}/{character_b}")
async def get_relationship_history(
    story_id: int,
    character_a: str,
    character_b: str,
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get full history of a specific relationship."""
    _verify_story_ownership(story_id, current_user, db)
    # Normalize order (alphabetical)
    char_a, char_b = sorted([character_a, character_b])

    # Get events
    query = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id,
        CharacterRelationship.character_a == char_a,
        CharacterRelationship.character_b == char_b
    )

    if branch_id is not None:
        query = query.filter(CharacterRelationship.branch_id == branch_id)

    events = query.order_by(CharacterRelationship.scene_sequence).all()

    # Get summary
    summary_query = db.query(RelationshipSummary).filter(
        RelationshipSummary.story_id == story_id,
        RelationshipSummary.character_a == char_a,
        RelationshipSummary.character_b == char_b
    )
    if branch_id is not None:
        summary_query = summary_query.filter(RelationshipSummary.branch_id == branch_id)

    summary = summary_query.first()

    return {
        "characters": [char_a, char_b],
        "history": [_format_event(e) for e in events],
        "summary": _format_summary(summary) if summary else None,
        "event_count": len(events)
    }


@router.get("/graph")
async def get_relationship_graph(
    story_id: int,
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    min_strength: float = Query(0.2, description="Minimum strength to include in graph"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get relationship data formatted for graph visualization."""
    _verify_story_ownership(story_id, current_user, db)
    query = db.query(RelationshipSummary).filter(
        RelationshipSummary.story_id == story_id
    )

    if branch_id is not None:
        query = query.filter(RelationshipSummary.branch_id == branch_id)

    summaries = query.all()

    # Build nodes (unique characters)
    characters = set()
    for s in summaries:
        characters.add(s.character_a)
        characters.add(s.character_b)

    nodes = [{"id": c, "label": c} for c in sorted(characters)]

    # Build edges (relationships above threshold)
    edges = []
    for s in summaries:
        if abs(s.current_strength or 0) >= min_strength:
            edges.append({
                "source": s.character_a,
                "target": s.character_b,
                "type": s.current_type,
                "strength": s.current_strength,
                "trajectory": s.trajectory,
                "label": s.arc_summary,
                "interactions": s.total_interactions
            })

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges)
    }


@router.get("/neglected")
async def get_neglected_relationships(
    story_id: int,
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    threshold_scenes: int = Query(3, description="Scenes without interaction to be considered neglected"),
    min_strength: float = Query(0.3, description="Minimum strength for meaningful relationships"),
    current_scene: Optional[int] = Query(None, description="Current scene sequence (defaults to max in story)"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get relationships that haven't had recent interaction."""
    _verify_story_ownership(story_id, current_user, db)
    query = db.query(RelationshipSummary).filter(
        RelationshipSummary.story_id == story_id
    )

    if branch_id is not None:
        query = query.filter(RelationshipSummary.branch_id == branch_id)

    summaries = query.all()

    # Determine current scene if not provided
    if current_scene is None:
        from ..models import Scene, StoryFlow
        max_scene = db.query(Scene).join(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.is_active == True
        ).order_by(Scene.sequence_number.desc()).first()
        current_scene = max_scene.sequence_number if max_scene else 0

    # Find neglected relationships
    neglected = []
    for s in summaries:
        if (s.current_strength or 0) < min_strength:
            continue

        if s.last_scene_sequence is None:
            continue

        scenes_since = current_scene - s.last_scene_sequence
        if scenes_since >= threshold_scenes:
            neglected.append({
                "characters": [s.character_a, s.character_b],
                "type": s.current_type,
                "strength": s.current_strength,
                "last_scene": s.last_scene_sequence,
                "scenes_since": scenes_since,
                "arc": s.arc_summary
            })

    # Sort by scenes_since (most neglected first)
    neglected.sort(key=lambda n: n["scenes_since"], reverse=True)

    return {
        "neglected": neglected,
        "count": len(neglected),
        "current_scene": current_scene,
        "threshold": threshold_scenes
    }
