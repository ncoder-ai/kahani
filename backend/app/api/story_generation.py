"""
Story Generation Helper API endpoints.

This module handles AI-powered generation of story elements including
scenarios, titles, and plot points during story creation.
Extracted from stories.py for better organization.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..api.auth import get_current_user
from ..services.llm.service import UnifiedLLMService
from .stories import get_or_create_user_settings

# Create LLM service instance
llm_service = UnifiedLLMService()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["story-generation"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ScenarioGenerateRequest(BaseModel):
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    elements: dict
    characters: Optional[List[dict]] = []


class TitleGenerateRequest(BaseModel):
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    scenario: Optional[str] = ""
    characters: Optional[List[dict]] = []
    story_elements: Optional[dict] = {}


class PlotGenerateRequest(BaseModel):
    genre: Optional[str] = ""
    tone: Optional[str] = ""
    scenario: Optional[str] = ""
    characters: Optional[List[dict]] = []
    world_setting: Optional[str] = ""
    plot_type: Optional[str] = "complete"  # "complete", "single_point"
    plot_point_index: Optional[int] = None


# =============================================================================
# STORY GENERATION ENDPOINTS
# =============================================================================

@router.post("/generate-scenario")
async def generate_scenario_endpoint(
    request: ScenarioGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a creative scenario using LLM based on user selections"""

    try:
        # Build context for LLM
        context = {
            "genre": request.genre,
            "tone": request.tone,
            "opening": request.elements.get("opening", ""),
            "setting": request.elements.get("setting", ""),
            "conflict": request.elements.get("conflict", ""),
            "characters": request.characters
        }

        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        # Add user permissions to settings for NSFW filtering
        user_settings['allow_nsfw'] = current_user.allow_nsfw

        # Generate scenario using LLM
        scenario = await llm_service.generate_scenario(context, current_user.id, user_settings)

        return {
            "scenario": scenario,
            "message": "Scenario generated successfully"
        }

    except ValueError as e:
        # This handles validation errors (like missing API URL)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"LLM service error: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback:", exc_info=True)
        # Fallback to simple combination if LLM fails for other reasons
        elements = [v for v in request.elements.values() if v]
        fallback_scenario = ". ".join(elements) + "." if elements else "A new adventure begins."

        return {
            "scenario": fallback_scenario,
            "message": "Scenario generated (fallback mode due to LLM service error)"
        }


@router.post("/generate-title")
async def generate_title(
    request: TitleGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate creative story titles using LLM based on story content"""

    try:
        # Build context for LLM
        context = {
            "genre": request.genre,
            "tone": request.tone,
            "scenario": request.scenario,
            "characters": request.characters,
            "story_elements": request.story_elements
        }

        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        # Add user permissions to settings for NSFW filtering
        user_settings['allow_nsfw'] = current_user.allow_nsfw

        # Generate multiple title options using LLM
        titles = await llm_service.generate_story_title(context, current_user.id, user_settings)

        return {
            "titles": titles,
            "message": "Titles generated successfully"
        }

    except Exception as e:
        # Fallback titles based on genre
        genre = request.genre or "adventure"
        fallback_titles = [
            f"The {genre.title()} Begins",
            f"Chronicles of {genre.title()}",
            f"Beyond the {genre.title()}"
        ]

        return {
            "titles": fallback_titles,
            "message": "Titles generated (fallback mode)"
        }


@router.post("/generate-plot")
async def generate_plot_endpoint(
    request: PlotGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate plot points using LLM based on characters and scenario"""

    try:
        # Build context for LLM
        context = {
            "genre": request.genre,
            "tone": request.tone,
            "scenario": request.scenario,
            "characters": request.characters,
            "world_setting": request.world_setting,
            "plot_type": request.plot_type,
            "plot_point_index": request.plot_point_index
        }

        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        # Add user permissions to settings for NSFW filtering
        user_settings['allow_nsfw'] = current_user.allow_nsfw

        # Generate plot using LLM
        try:
            if request.plot_type == "complete":
                plot_points = await llm_service.generate_plot_points(context, current_user.id, user_settings, plot_type="complete")

                # Validate that we got plot points
                if not plot_points or len(plot_points) == 0:
                    logger.error("Plot generation returned empty plot_points list")
                    raise ValueError("Failed to parse plot points from LLM response")

                logger.info(f"Successfully generated {len(plot_points)} plot points for user {current_user.id}")
                return {
                    "plot_points": plot_points,
                    "message": "Complete plot generated successfully"
                }
            else:
                plot_point_result = await llm_service.generate_plot_points(context, current_user.id, user_settings, plot_type="single")

                # Handle single plot point (returns a list with one element)
                plot_point = plot_point_result[0] if isinstance(plot_point_result, list) and len(plot_point_result) > 0 else str(plot_point_result) if plot_point_result else ""

                if not plot_point or len(plot_point.strip()) == 0:
                    logger.error("Plot generation returned empty plot_point")
                    raise ValueError("Failed to generate plot point from LLM response")

                logger.info(f"Successfully generated single plot point for user {current_user.id}")
                return {
                    "plot_point": plot_point,
                    "message": "Plot point generated successfully"
                }
        except (ValueError, AttributeError, IndexError, TypeError) as parse_error:
            # These are likely parsing errors
            logger.error(f"Plot parsing error for user {current_user.id}: {parse_error}")
            logger.error(f"Parse error type: {type(parse_error).__name__}")
            logger.error(f"Context: plot_type={request.plot_type}, plot_point_index={request.plot_point_index}")
            logger.error(f"Full traceback:", exc_info=True)

            # Return meaningful error to frontend
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse plot points from LLM response: {str(parse_error)}. Check backend logs for details."
            )

    except ValueError as e:
        # This handles validation errors (like missing API URL)
        logger.error(f"Plot generation validation error for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Plot generation error for user {current_user.id}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback:", exc_info=True)

        # Fallback plot points
        fallback_points = [
            "The story begins with an intriguing hook that draws readers in.",
            "A pivotal event changes everything and sets the main conflict in motion.",
            "Challenges and obstacles test the characters' resolve and growth.",
            "The climax brings all conflicts to a head in an intense confrontation.",
            "The resolution ties up loose ends and shows character transformation."
        ]

        if request.plot_type == "complete":
            logger.warning(f"Using fallback plot points for user {current_user.id}")
            return {
                "plot_points": fallback_points,
                "message": "Plot generated (fallback mode due to error)"
            }
        else:
            index = request.plot_point_index or 0
            logger.warning(f"Using fallback plot point for user {current_user.id}, index {index}")
            return {
                "plot_point": fallback_points[min(index, len(fallback_points)-1)],
                "message": "Plot point generated (fallback mode due to error)"
            }
