"""
Semantic Search API

Provides endpoints for semantic search, character arcs, and plot thread analysis.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from ..database import get_db
from ..models import User, Story
from ..dependencies import get_current_user
from ..services.semantic_memory import get_semantic_memory_service
from ..services.character_memory_service import get_character_memory_service
from ..services.plot_thread_service import get_plot_thread_service
from ..services.semantic_integration import get_semantic_stats
from ..config import settings

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class SemanticSearchRequest(BaseModel):
    query: str
    context_type: str = "scenes"  # scenes, characters, plot_events, all
    top_k: int = 5


class SemanticSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total_found: int
    query: str


class CharacterArcResponse(BaseModel):
    character_id: int
    character_name: str
    moments: List[Dict[str, Any]]
    total_moments: int


class PlotThreadsResponse(BaseModel):
    threads: List[Dict[str, Any]]
    total_threads: int
    unresolved_count: int


# Endpoints

@router.post("/stories/{story_id}/semantic-search", response_model=SemanticSearchResponse)
async def semantic_search(
    story_id: int,
    request: SemanticSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Perform semantic search across story content
    
    Search types:
    - scenes: Search for similar scenes
    - characters: Search for character moments
    - plot_events: Search for related plot events
    - all: Search across all types
    """
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    if not settings.enable_semantic_memory:
        raise HTTPException(
            status_code=503,
            detail="Semantic search is not enabled"
        )
    
    try:
        semantic_memory = get_semantic_memory_service()
        results = []
        
        # Perform search based on context type
        if request.context_type in ["scenes", "all"]:
            scene_results = await semantic_memory.search_similar_scenes(
                query_text=request.query,
                story_id=story_id,
                top_k=request.top_k
            )
            for result in scene_results:
                result['type'] = 'scene'
                results.append(result)
        
        if request.context_type in ["plot_events", "all"]:
            plot_service = get_plot_thread_service()
            plot_results = await plot_service.get_related_plot_events(
                query_text=request.query,
                story_id=story_id,
                top_k=request.top_k
            )
            for result in plot_results:
                result['type'] = 'plot_event'
                results.append(result)
        
        # Sort by similarity if multiple types
        if request.context_type == "all":
            results.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
            results = results[:request.top_k]
        
        return SemanticSearchResponse(
            results=results,
            total_found=len(results),
            query=request.query
        )
        
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Semantic memory service not available: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Semantic search failed: {str(e)}"
        )


@router.get("/stories/{story_id}/characters/{character_id}/arc", response_model=CharacterArcResponse)
async def get_character_arc(
    story_id: int,
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get chronological character arc with all significant moments
    """
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    if not settings.enable_semantic_memory:
        raise HTTPException(
            status_code=503,
            detail="Character arc tracking is not enabled"
        )
    
    try:
        char_service = get_character_memory_service()
        arc = await char_service.get_character_arc(
            character_id=character_id,
            story_id=story_id,
            db=db
        )
        
        # Get character name
        from ..models import Character
        character = db.query(Character).filter(Character.id == character_id).first()
        character_name = character.name if character else "Unknown"
        
        return CharacterArcResponse(
            character_id=character_id,
            character_name=character_name,
            moments=arc,
            total_moments=len(arc)
        )
        
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Character memory service not available: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to get character arc: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get character arc: {str(e)}"
        )


@router.get("/stories/{story_id}/plot-threads", response_model=PlotThreadsResponse)
async def get_plot_threads(
    story_id: int,
    only_unresolved: bool = Query(False, description="Only return unresolved threads"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all plot threads for a story
    """
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    if not settings.enable_semantic_memory:
        raise HTTPException(
            status_code=503,
            detail="Plot thread tracking is not enabled"
        )
    
    try:
        plot_service = get_plot_thread_service()
        
        if only_unresolved:
            threads = await plot_service.get_unresolved_threads(
                story_id=story_id,
                db=db
            )
            unresolved_count = len(threads)
        else:
            threads = await plot_service.get_plot_timeline(
                story_id=story_id,
                db=db
            )
            unresolved_count = sum(1 for t in threads if not t.get('is_resolved', False))
        
        return PlotThreadsResponse(
            threads=threads,
            total_threads=len(threads),
            unresolved_count=unresolved_count
        )
        
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Plot thread service not available: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to get plot threads: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get plot threads: {str(e)}"
        )


@router.get("/stories/{story_id}/semantic-stats")
async def get_story_semantic_stats(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get semantic memory statistics for a story
    """
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    try:
        stats = get_semantic_stats(story_id, db)
        return {
            "story_id": story_id,
            "semantic_memory": stats
        }
    except Exception as e:
        logger.error(f"Failed to get semantic stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get semantic stats: {str(e)}"
        )


@router.post("/stories/{story_id}/plot-threads/{thread_id}/resolve")
async def mark_thread_resolved(
    story_id: int,
    thread_id: str,
    resolution_scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark a plot thread as resolved
    """
    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    if not settings.enable_semantic_memory:
        raise HTTPException(
            status_code=503,
            detail="Plot thread tracking is not enabled"
        )
    
    try:
        plot_service = get_plot_thread_service()
        success = await plot_service.mark_thread_resolved(
            thread_id=thread_id,
            story_id=story_id,
            resolution_scene_id=resolution_scene_id,
            db=db
        )
        
        if success:
            return {
                "message": "Thread marked as resolved",
                "thread_id": thread_id,
                "resolution_scene_id": resolution_scene_id
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Thread not found or already resolved"
            )
        
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Plot thread service not available: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to mark thread resolved: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark thread resolved: {str(e)}"
        )

