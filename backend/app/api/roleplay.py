"""
Roleplay API Endpoints

Handles creation, management, and turn generation for roleplay sessions.
Roleplays are stored as Story records with story_mode=ROLEPLAY.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging
import time

from ..database import get_db
from ..models import Story, User, StoryMode
from ..dependencies import get_current_user
from .story_helpers import get_or_create_user_settings
from ..services.roleplay import RoleplayService, CharacterLoader

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---

class RoleplayCharacterConfig(BaseModel):
    character_id: int
    role: Optional[str] = "participant"
    source_story_id: Optional[int] = None
    source_branch_id: Optional[int] = None
    talkativeness: Optional[float] = 0.5
    is_player: Optional[bool] = False


class RoleplayCreate(BaseModel):
    title: str = "Untitled Roleplay"
    scenario: Optional[str] = ""
    setting: Optional[str] = ""
    tone: Optional[str] = ""
    content_rating: Optional[str] = "sfw"
    characters: list[RoleplayCharacterConfig]
    player_mode: Optional[str] = "character"  # character | narrator | director
    turn_mode: Optional[str] = "natural"  # natural | round_robin | manual
    response_length: Optional[str] = "concise"  # concise | detailed
    auto_continue: Optional[bool] = False
    max_auto_turns: Optional[int] = 2
    narration_style: Optional[str] = "moderate"  # minimal | moderate | rich
    voice_mapping: Optional[dict] = None
    generate_opening: Optional[bool] = True


class RoleplaySettingsUpdate(BaseModel):
    turn_mode: Optional[str] = None
    response_length: Optional[str] = None
    auto_continue: Optional[bool] = None
    max_auto_turns: Optional[int] = None
    narration_style: Optional[str] = None


# --- Endpoints ---

@router.post("/")
async def create_roleplay(
    config: RoleplayCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new roleplay session."""
    # Validate characters
    if not config.characters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one character is required",
        )

    # Ensure exactly one player character (unless narrator/director mode)
    player_count = sum(1 for c in config.characters if c.is_player)
    if config.player_mode == "character" and player_count != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one character must be marked as the player character",
        )

    # Validate NSFW
    if config.content_rating == "nsfw" and not getattr(current_user, "allow_nsfw", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="NSFW content is not enabled for your account",
        )

    # Build config dict for service
    service_config = {
        "title": config.title,
        "scenario": config.scenario,
        "setting": config.setting,
        "tone": config.tone,
        "content_rating": config.content_rating,
        "characters": [c.model_dump() for c in config.characters],
        "player_mode": config.player_mode,
        "voice_mapping": config.voice_mapping or {},
        "roleplay_settings": {
            "turn_mode": config.turn_mode,
            "response_length": config.response_length,
            "auto_continue": config.auto_continue,
            "max_auto_turns": config.max_auto_turns,
            "narration_style": config.narration_style,
        },
    }

    try:
        result = await RoleplayService.create_roleplay(
            db, current_user.id, service_config, {}
        )
    except Exception as e:
        logger.error(f"Failed to create roleplay: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create roleplay: {str(e)}",
        )

    return {
        "message": "Roleplay created successfully",
        **result,
    }


@router.get("/")
async def list_roleplays(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all roleplays for the current user."""
    return await RoleplayService.list_roleplays(db, current_user.id)


@router.get("/{roleplay_id}")
async def get_roleplay(
    roleplay_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a roleplay with full turn history."""
    result = await RoleplayService.get_roleplay(db, roleplay_id, current_user.id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roleplay not found",
        )
    # Update last accessed story for auto-open feature
    from .story_helpers import update_last_accessed_story
    update_last_accessed_story(db, current_user.id, roleplay_id)
    return result


@router.delete("/{roleplay_id}")
async def delete_roleplay(
    roleplay_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a roleplay."""
    deleted = await RoleplayService.delete_roleplay(db, roleplay_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roleplay not found",
        )
    return {"message": "Roleplay deleted"}


@router.post("/{roleplay_id}/opening/stream")
async def generate_opening_stream(
    roleplay_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate the opening scene for a roleplay (streaming SSE)."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

    async def stream_generator():
        full_content = ""
        try:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"

            async for chunk in RoleplayService.generate_opening(
                db, roleplay_id, current_user.id, user_settings
            ):
                # Filter out thinking tokens
                if chunk.startswith("__THINKING__:"):
                    continue
                full_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"

            # Save the opening as an AI turn
            scene, variant = RoleplayService.save_ai_turn(
                db, story.id, story.current_branch_id,
                story.chapters[0].id if story.chapters else None,
                content=full_content,
            )
            db.commit()

            yield f"data: {json.dumps({'type': 'complete', 'scene_id': scene.id, 'variant_id': variant.id, 'content': full_content})}\n\n"

        except Exception as e:
            logger.error(f"Opening generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class TurnInput(BaseModel):
    content: str
    input_mode: str = "character"  # character | narration | direction
    active_character_ids: Optional[list[int]] = None  # Manual mode: specify who responds


class TurnEditInput(BaseModel):
    content: str


class AutoContinueInput(BaseModel):
    num_turns: int = 1


class AddCharacterInput(BaseModel):
    character_id: int
    role: Optional[str] = "participant"
    source_story_id: Optional[int] = None
    source_branch_id: Optional[int] = None
    talkativeness: Optional[float] = 0.5


@router.post("/{roleplay_id}/turns/stream")
async def generate_turn_stream(
    roleplay_id: int,
    turn_input: TurnInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate an AI response to the user's turn (streaming SSE)."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    content = turn_input.content
    input_mode = turn_input.input_mode

    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Content is required")

    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
    chapter_id = story.chapters[0].id if story.chapters else None

    # Save user's turn first
    user_scene, user_variant = RoleplayService.save_user_turn(
        db, story.id, story.current_branch_id, chapter_id,
        content=content.strip(),
        generation_method="direction" if input_mode == "direction" else "user_written",
    )
    db.commit()

    async def stream_generator():
        full_content = ""
        try:
            yield f"data: {json.dumps({'type': 'start', 'user_turn_scene_id': user_scene.id})}\n\n"

            async for chunk in RoleplayService.generate_response(
                db, roleplay_id, current_user.id,
                user_input=content.strip(),
                input_mode=input_mode,
                user_settings=user_settings,
                active_character_ids=turn_input.active_character_ids,
            ):
                if chunk.startswith("__THINKING__:"):
                    continue
                full_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"

            # Save AI response
            ai_scene, ai_variant = RoleplayService.save_ai_turn(
                db, story.id, story.current_branch_id, chapter_id,
                content=full_content,
            )
            db.commit()

            yield f"data: {json.dumps({'type': 'complete', 'scene_id': ai_scene.id, 'variant_id': ai_variant.id, 'content': full_content})}\n\n"

        except Exception as e:
            logger.error(f"Turn generation failed for RP {roleplay_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/{roleplay_id}/turns/{scene_id}")
async def edit_turn(
    roleplay_id: int,
    scene_id: int,
    edit_input: TurnEditInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit a turn's content."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    if not edit_input.content or not edit_input.content.strip():
        raise HTTPException(status_code=400, detail="Content is required")

    result = RoleplayService.edit_turn(db, story, scene_id, edit_input.content)
    if not result:
        raise HTTPException(status_code=404, detail="Turn not found")

    return result


@router.delete("/{roleplay_id}/turns/from/{sequence}")
async def delete_turns_from(
    roleplay_id: int,
    sequence: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all turns from a given sequence number onwards."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    count = RoleplayService.delete_turns_from(db, story, sequence)
    return {"message": f"Deleted {count} turns", "deleted_count": count}


@router.post("/{roleplay_id}/turns/{scene_id}/regenerate")
async def regenerate_turn(
    roleplay_id: int,
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate the last AI turn (streaming SSE)."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    from ..models import StoryFlow, Scene
    from ..models.scene_variant import SceneVariant as SV

    branch_id = story.current_branch_id

    # Find the scene to regenerate — must be the last AI turn
    flow = (
        db.query(StoryFlow)
        .filter(
            StoryFlow.story_id == story.id,
            StoryFlow.scene_id == scene_id,
            StoryFlow.branch_id == branch_id,
            StoryFlow.is_active == True,
        )
        .first()
    )
    if not flow:
        raise HTTPException(status_code=404, detail="Turn not found")

    variant = db.query(SV).filter(SV.id == flow.scene_variant_id).first()
    if not variant or variant.generation_method not in ("auto",):
        raise HTTPException(status_code=400, detail="Can only regenerate AI turns")

    # Delete this turn
    seq = flow.sequence_number
    RoleplayService.delete_turns_from(db, story, seq)

    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
    chapter_id = story.chapters[0].id if story.chapters else None

    async def stream_generator():
        full_content = ""
        try:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"

            # Get the last user input from previous turn for context
            prev_flow = (
                db.query(StoryFlow)
                .filter(
                    StoryFlow.story_id == story.id,
                    StoryFlow.branch_id == branch_id,
                    StoryFlow.is_active == True,
                )
                .order_by(StoryFlow.sequence_number.desc())
                .first()
            )
            last_user_input = ""
            if prev_flow:
                prev_variant = db.query(SV).filter(SV.id == prev_flow.scene_variant_id).first()
                if prev_variant and prev_variant.generation_method in ("user_written", "direction"):
                    last_user_input = prev_variant.content or ""

            async for chunk in RoleplayService.generate_response(
                db, roleplay_id, current_user.id,
                user_input=last_user_input or "(continue)",
                input_mode="direction",
                user_settings=user_settings,
            ):
                if chunk.startswith("__THINKING__:"):
                    continue
                full_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"

            # Save the regenerated turn
            ai_scene, ai_variant = RoleplayService.save_ai_turn(
                db, story.id, branch_id, chapter_id,
                content=full_content,
            )
            db.commit()

            yield f"data: {json.dumps({'type': 'complete', 'scene_id': ai_scene.id, 'variant_id': ai_variant.id, 'content': full_content})}\n\n"

        except Exception as e:
            logger.error(f"Regeneration failed for RP {roleplay_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/{roleplay_id}/settings")
async def update_roleplay_settings(
    roleplay_id: int,
    settings: RoleplaySettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update roleplay settings mid-session."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    ctx = story.story_context or {}
    rp_settings = ctx.get("roleplay_settings", {})

    # Update only provided fields
    update_data = settings.model_dump(exclude_none=True)
    rp_settings.update(update_data)
    ctx["roleplay_settings"] = rp_settings
    story.story_context = ctx

    from sqlalchemy.orm import attributes
    attributes.flag_modified(story, "story_context")
    db.commit()

    return {"message": "Settings updated", "roleplay_settings": rp_settings}


@router.get("/{roleplay_id}/voices")
async def get_voice_mapping(
    roleplay_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current voice mapping for a roleplay."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    ctx = story.story_context or {}
    return {"voice_mapping": ctx.get("voice_mapping", {})}


class VoiceMappingInput(BaseModel):
    voice_mapping: dict  # {char_name: {voice_id, speed}, "__narrator__": {voice_id, speed}}


@router.put("/{roleplay_id}/voices")
async def update_voice_mapping(
    roleplay_id: int,
    input_data: VoiceMappingInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update voice mapping for a roleplay."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    ctx = story.story_context or {}
    ctx["voice_mapping"] = input_data.voice_mapping
    story.story_context = ctx

    from sqlalchemy.orm import attributes
    attributes.flag_modified(story, "story_context")
    db.commit()

    return {"message": "Voice mapping updated", "voice_mapping": ctx["voice_mapping"]}


@router.post("/{roleplay_id}/auto-player/stream")
async def auto_player_stream(
    roleplay_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Auto-generate the player character's turn (streaming SSE)."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

    async def stream_generator():
        full_content = ""
        try:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"

            async for chunk in RoleplayService.generate_player_turn(
                db, roleplay_id, current_user.id, user_settings
            ):
                if chunk.startswith("__THINKING__:"):
                    continue
                full_content += chunk
                yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"

            # Don't save — return as draft for the user to review/edit before sending
            yield f"data: {json.dumps({'type': 'complete', 'content': full_content})}\n\n"

        except Exception as e:
            logger.error(f"Auto-player generation failed for RP {roleplay_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{roleplay_id}/auto-continue/stream")
async def auto_continue_stream(
    roleplay_id: int,
    input_data: AutoContinueInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate multiple AI turns without user input (streaming SSE)."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    if input_data.num_turns < 1:
        raise HTTPException(status_code=400, detail="num_turns must be at least 1")

    user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)

    async def stream_generator():
        try:
            yield f"data: {json.dumps({'type': 'start', 'requested_turns': input_data.num_turns})}\n\n"

            async for chunk in RoleplayService.auto_continue(
                db, roleplay_id, current_user.id,
                num_turns=input_data.num_turns,
                user_settings=user_settings,
            ):
                if chunk.startswith("__AUTO_TURN_START__:"):
                    turn_num = chunk.split(":")[1]
                    yield f"data: {json.dumps({'type': 'auto_turn_start', 'turn': int(turn_num)})}\n\n"
                elif chunk.startswith("__AUTO_TURN_COMPLETE__:"):
                    parts = chunk.split(":")
                    yield f"data: {json.dumps({'type': 'auto_turn_complete', 'turn': int(parts[1]), 'scene_id': int(parts[2]), 'variant_id': int(parts[3])})}\n\n"
                elif chunk.startswith("__THINKING__:"):
                    continue
                else:
                    yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            logger.error(f"Auto-continue failed for RP {roleplay_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{roleplay_id}/characters")
async def add_character(
    roleplay_id: int,
    char_input: AddCharacterInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a character to an active roleplay mid-session."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    result = await RoleplayService.add_character(
        db, story, char_input.model_dump()
    )
    return result


@router.delete("/{roleplay_id}/characters/{story_character_id}")
async def remove_character(
    roleplay_id: int,
    story_character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a character from an active roleplay mid-session."""
    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    result = await RoleplayService.remove_character(
        db, story, story_character_id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Character not found in this roleplay")
    return result


@router.get("/characters/{character_id}/stories")
async def get_character_stories(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all stories where a character appears (for development stage picker)."""
    return await CharacterLoader.get_character_stories(db, character_id, current_user.id)


class RelationshipUpdate(BaseModel):
    """Update a relationship between two characters."""
    target_character_name: str
    relationship_type: str  # e.g. "friend", "rival", "lover", "mentor"
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    description: Optional[str] = None


@router.get("/{roleplay_id}/relationships")
async def get_relationships(
    roleplay_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all character relationships for a roleplay."""
    from ..models.character import StoryCharacter as SC

    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    scs = db.query(SC).filter(SC.story_id == story.id, SC.is_active == True).all()
    result = {}
    for sc in scs:
        name = sc.character.name if sc.character else "Unknown"
        result[name] = sc.relationships or {}
    return result


@router.put("/{roleplay_id}/characters/{story_character_id}/relationships")
async def update_relationship(
    roleplay_id: int,
    story_character_id: int,
    rel: RelationshipUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a character's relationship with another character."""
    from ..models.character import StoryCharacter as SC

    story = db.query(Story).filter(
        Story.id == roleplay_id,
        Story.owner_id == current_user.id,
        Story.story_mode == StoryMode.ROLEPLAY,
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Roleplay not found")

    sc = db.query(SC).filter(
        SC.id == story_character_id,
        SC.story_id == story.id,
        SC.is_active == True,
    ).first()
    if not sc:
        raise HTTPException(status_code=404, detail="Character not found")

    relationships = dict(sc.relationships or {})
    relationships[rel.target_character_name] = {
        "type": rel.relationship_type,
        "strength": rel.strength,
        "arc_summary": rel.description or "",
    }
    sc.relationships = relationships

    from sqlalchemy.orm import attributes
    attributes.flag_modified(sc, "relationships")
    db.commit()

    char_name = sc.character.name if sc.character else "Unknown"
    return {
        "message": f"Updated {char_name}'s relationship with {rel.target_character_name}",
        "relationships": relationships,
    }
