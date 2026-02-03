"""
Story Arc API endpoints.

This module handles generation, retrieval, and updating of story arcs.
Extracted from stories.py for better organization.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..api.auth import get_current_user
from .stories import get_or_create_user_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["story-arc"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class GenerateArcRequest(BaseModel):
    """Request for generating a story arc."""
    structure_type: str = "three_act"  # three_act, five_act, hero_journey


class UpdateArcRequest(BaseModel):
    """Request for updating a story arc."""
    arc_data: Dict[str, Any]


# =============================================================================
# STORY ARC ENDPOINTS
# =============================================================================

@router.post("/{story_id}/arc/generate")
async def generate_story_arc(
    story_id: int,
    request: GenerateArcRequest = Body(default=GenerateArcRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a story arc for the given story.

    Uses AI to analyze the story's elements and create a structured narrative arc.

    Args:
        story_id: The story ID
        request: Arc generation options (structure type)

    Returns:
        Generated story arc
    """
    try:
        from ..services.brainstorm_service import BrainstormService

        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)

        result = await service.generate_story_arc(
            story_id=story_id,
            structure_type=request.structure_type
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[STORY_ARC:GENERATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate story arc")


@router.put("/{story_id}/arc")
async def update_story_arc(
    story_id: int,
    request: UpdateArcRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the story arc (user edits).

    Args:
        story_id: The story ID
        request: Updated arc data

    Returns:
        Updated story arc
    """
    try:
        from ..services.brainstorm_service import BrainstormService

        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)

        result = service.update_story_arc(
            story_id=story_id,
            arc_data=request.arc_data
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[STORY_ARC:UPDATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update story arc")


@router.get("/{story_id}/arc")
async def get_story_arc(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the story arc for a story.

    Args:
        story_id: The story ID

    Returns:
        Story arc data or null if not generated
    """
    try:
        from ..services.brainstorm_service import BrainstormService

        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)

        arc = service.get_story_arc(story_id)

        return {
            "story_id": story_id,
            "arc": arc
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[STORY_ARC:GET] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get story arc")
