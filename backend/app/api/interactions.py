"""
Character Interaction API endpoints.

This module handles character interaction management including retrieval,
deletion, extraction progress, and retroactive extraction.
Extracted from stories.py for better organization.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Story, User
from ..api.auth import get_current_user
from .story_tasks import (
    extraction_progress_store,
    scene_event_extraction_progress_store,
    run_interaction_extraction_background,
    run_scene_event_extraction_background,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["interactions"])


# =============================================================================
# INTERACTION PRESETS ENDPOINT
# =============================================================================

@router.get("/interaction-presets")
async def get_interaction_presets(
    current_user: User = Depends(get_current_user)
):
    """Get available interaction type presets for story configuration."""
    import yaml

    # Try multiple paths for the presets file
    preset_paths = [
        'interaction_presets.yml',
        '/app/interaction_presets.yml',
        os.path.join(os.path.dirname(__file__), '..', '..', 'interaction_presets.yml'),
    ]

    for preset_path in preset_paths:
        try:
            with open(preset_path, 'r') as f:
                presets = yaml.safe_load(f)
                if presets:
                    return presets
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.warning(f"Error loading interaction presets from {preset_path}: {e}")
            continue

    # Return default presets if file not found
    return {
        "default": {
            "name": "Default",
            "description": "Basic interactions suitable for any story type",
            "types": [
                "first meeting",
                "first argument",
                "first collaboration",
                "betrayal",
                "reconciliation",
                "secret shared",
                "trust established",
                "alliance formed"
            ]
        }
    }


# =============================================================================
# STORY INTERACTION ENDPOINTS
# =============================================================================

@router.get("/{story_id}/interactions")
async def get_story_interactions(
    story_id: int,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all recorded character interactions for a story.

    Returns the interaction history showing what has occurred between characters.

    Args:
        branch_id: Optional branch ID to filter interactions. If not provided,
                   uses the active branch for the story.
    """
    from ..models import CharacterInteraction, Character, StoryBranch, Scene

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

    # Get all interactions
    query = db.query(CharacterInteraction).filter(
        CharacterInteraction.story_id == story_id
    )
    if branch_id:
        query = query.filter(CharacterInteraction.branch_id == branch_id)

    interactions = query.order_by(CharacterInteraction.first_occurrence_scene).all()

    # Build character ID to name mapping
    char_ids = set()
    for interaction in interactions:
        char_ids.add(interaction.character_a_id)
        char_ids.add(interaction.character_b_id)

    characters = db.query(Character).filter(Character.id.in_(char_ids)).all() if char_ids else []
    char_id_to_name = {c.id: c.name for c in characters}

    # Format response
    result = []
    for interaction in interactions:
        result.append({
            "id": interaction.id,
            "interaction_type": interaction.interaction_type,
            "character_a": char_id_to_name.get(interaction.character_a_id, "Unknown"),
            "character_b": char_id_to_name.get(interaction.character_b_id, "Unknown"),
            "first_occurrence_scene": interaction.first_occurrence_scene,
            "description": interaction.description,
            "created_at": interaction.created_at.isoformat() if interaction.created_at else None
        })

    # Also show what hasn't occurred yet
    configured_types = set(story.interaction_types or [])
    occurred_types = {i.interaction_type for i in interactions}
    not_occurred = list(configured_types - occurred_types)

    # Get total scene count for progress tracking
    scene_query = db.query(Scene).filter(Scene.story_id == story_id)
    if branch_id:
        scene_query = scene_query.filter(Scene.branch_id == branch_id)
    total_scenes = scene_query.count()

    return {
        "story_id": story_id,
        "interaction_types_configured": story.interaction_types or [],
        "interactions": result,
        "interactions_not_occurred": sorted(not_occurred),
        "total_interactions": len(result),
        "total_scenes": total_scenes
    }


@router.delete("/{story_id}/interactions/{interaction_id}")
async def delete_interaction(
    story_id: int,
    interaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a specific character interaction.

    Allows users to manually remove incorrect or unwanted interactions.
    """
    from ..models import CharacterInteraction

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

    # Find and delete the interaction
    interaction = db.query(CharacterInteraction).filter(
        CharacterInteraction.id == interaction_id,
        CharacterInteraction.story_id == story_id
    ).first()

    if not interaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interaction not found"
        )

    db.delete(interaction)
    db.commit()

    logger.info(f"[INTERACTION_DELETE] Deleted interaction {interaction_id} ({interaction.interaction_type}) from story {story_id}")

    return {
        "message": "Interaction deleted successfully",
        "deleted_id": interaction_id
    }


@router.get("/{story_id}/extraction-progress")
async def get_extraction_progress(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current progress of interaction extraction.

    Returns batch progress for ongoing extractions.
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

    progress = extraction_progress_store.get(story_id)

    if not progress:
        return {
            "in_progress": False,
            "batches_processed": 0,
            "total_batches": 0,
            "interactions_found": 0
        }

    return {
        "in_progress": True,
        "batches_processed": progress['batches_processed'],
        "total_batches": progress['total_batches'],
        "interactions_found": progress['interactions_found']
    }


@router.post("/{story_id}/extract-interactions")
async def extract_interactions_retroactively(
    story_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retroactively extract character interactions from existing scenes.

    Uses a BATCHED approach for efficiency:
    - Groups scenes into batches (10 scenes per batch by default)
    - Sends batch to LLM in a single request
    - Much faster than processing 170 scenes individually

    This is useful when:
    - Interaction types are configured after scenes already exist
    - You want to rebuild the interaction history
    """
    from ..models import Scene, StoryBranch, UserSettings

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

    # Check if story has interaction types configured
    if not story.interaction_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No interaction types configured for this story. Configure them in Story Settings first."
        )

    # Get active branch
    active_branch = db.query(StoryBranch).filter(
        StoryBranch.story_id == story_id,
        StoryBranch.is_active == True
    ).first()
    branch_id = active_branch.id if active_branch else None

    # Count scenes to process
    scene_query = db.query(Scene).filter(Scene.story_id == story_id)
    if branch_id:
        scene_query = scene_query.filter(Scene.branch_id == branch_id)
    scene_count = scene_query.count()

    if scene_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No scenes found in this story"
        )

    # Get user settings for extraction
    user_settings_record = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    user_settings = user_settings_record.to_dict() if user_settings_record else {}

    # Calculate batches
    batch_size = 10  # Scenes per batch
    num_batches = (scene_count + batch_size - 1) // batch_size

    # Schedule background extraction
    background_tasks.add_task(
        run_interaction_extraction_background,
        story_id=story_id,
        branch_id=branch_id,
        user_id=current_user.id,
        user_settings=user_settings,
        interaction_types=story.interaction_types,
        batch_size=batch_size
    )

    return {
        "message": f"Interaction extraction started: {scene_count} scenes in {num_batches} batches",
        "story_id": story_id,
        "scene_count": scene_count,
        "batch_size": batch_size,
        "num_batches": num_batches,
        "interaction_types": story.interaction_types,
        "status": "processing"
    }


# =============================================================================
# SCENE EVENT EXTRACTION ENDPOINTS
# =============================================================================

@router.post("/{story_id}/extract-events")
async def extract_events_retroactively(
    story_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retroactively extract scene events from existing scenes.
    Processes each scene independently for reliable extraction.
    """
    from ..models import Scene, StoryBranch, UserSettings

    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )

    # Get active branch
    active_branch = db.query(StoryBranch).filter(
        StoryBranch.story_id == story_id,
        StoryBranch.is_active == True
    ).first()
    branch_id = active_branch.id if active_branch else None

    # Count scenes
    scene_query = db.query(Scene).filter(Scene.story_id == story_id)
    if branch_id:
        scene_query = scene_query.filter(Scene.branch_id == branch_id)
    scene_count = scene_query.count()

    if scene_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No scenes found in this story"
        )

    # Get user settings
    user_settings_record = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    user_settings = user_settings_record.to_dict() if user_settings_record else {}

    background_tasks.add_task(
        run_scene_event_extraction_background,
        story_id=story_id,
        branch_id=branch_id,
        user_id=current_user.id,
        user_settings=user_settings,
    )

    return {
        "message": f"Scene event extraction started: {scene_count} scenes",
        "story_id": story_id,
        "scene_count": scene_count,
        "status": "processing"
    }


@router.get("/{story_id}/extract-events/progress")
async def get_event_extraction_progress(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get progress of retroactive scene event extraction."""
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )

    progress = scene_event_extraction_progress_store.get(story_id)
    if not progress:
        return {
            "in_progress": False,
            "scenes_processed": 0,
            "total_scenes": 0,
            "events_found": 0
        }

    return {
        "in_progress": True,
        "scenes_processed": progress.get('scenes_processed', 0),
        "total_scenes": progress.get('total_scenes', 0),
        "events_found": progress.get('events_found', 0)
    }
