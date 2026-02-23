from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from ..database import get_db
from ..models import Character, StoryCharacter, User, UserSettings, Story
from ..dependencies import get_current_user
from ..services.character_generation_service import CharacterGenerationService
from .stories import get_or_create_user_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class VoiceStyleSchema(BaseModel):
    """Schema for character voice/speech style"""
    preset: Optional[str] = None  # Preset ID like "indian_english", "formal_noble", or "custom"
    formality: Optional[str] = None  # formal, casual, streetwise, archaic
    vocabulary: Optional[str] = None  # simple, average, sophisticated, technical
    tone: Optional[str] = None  # cheerful, sarcastic, gruff, nervous, calm, dramatic, deadpan
    profanity: Optional[str] = None  # none, mild, moderate, heavy
    speech_quirks: Optional[str] = None  # Free text for catchphrases, verbal tics
    secondary_language: Optional[str] = None  # Language ID like "hindi", "spanish"
    language_mixing: Optional[str] = None  # none, light, moderate, heavy

class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    gender: Optional[str] = None
    personality_traits: Optional[List[str]] = []
    background: Optional[str] = ""
    goals: Optional[str] = ""
    fears: Optional[str] = ""
    appearance: Optional[str] = ""
    is_template: Optional[bool] = True
    is_public: Optional[bool] = False
    voice_style: Optional[Dict[str, Any]] = None  # Voice/speech style settings

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    gender: Optional[str] = None
    personality_traits: Optional[List[str]] = None
    background: Optional[str] = None
    goals: Optional[str] = None
    fears: Optional[str] = None
    appearance: Optional[str] = None
    is_template: Optional[bool] = None
    is_public: Optional[bool] = None
    voice_style: Optional[Dict[str, Any]] = None  # Voice/speech style settings

class CharacterResponse(BaseModel):
    id: int
    name: str
    description: str
    gender: Optional[str] = None
    personality_traits: List[str]
    background: str
    goals: str
    fears: str
    appearance: str
    is_template: bool
    is_public: bool
    voice_style: Optional[Dict[str, Any]] = None  # Voice/speech style settings
    portrait_image_id: Optional[int] = None
    creator_id: int
    created_at: str
    updated_at: Optional[str]
    # Structured data for AI-generated characters (optional)
    background_structured: Optional[Dict[str, Any]] = None
    goals_structured: Optional[Dict[str, Any]] = None
    fears_structured: Optional[Dict[str, Any]] = None
    appearance_structured: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class CharacterEnrichRequest(BaseModel):
    story_id: Optional[int] = None

class CharacterGenerationRequest(BaseModel):
    prompt: str
    story_context: Optional[Dict[str, Any]] = None
    previous_generation: Optional[Dict[str, Any]] = None


@router.get("/voice-style-presets")
async def get_voice_style_presets(
    current_user: User = Depends(get_current_user)
):
    """Get available voice style presets and attributes for character creation"""
    from ..services.llm.prompts import prompt_manager
    
    dialog_styles = prompt_manager._prompts_cache.get("dialog_styles", {})
    
    # Extract presets with their metadata
    presets_raw = dialog_styles.get("presets", {})
    presets = {}
    for preset_id, preset_data in presets_raw.items():
        presets[preset_id] = {
            "name": preset_data.get("name", preset_id),
            "description": preset_data.get("description", ""),
            "category": preset_data.get("category", "other"),
            "example": preset_data.get("example", "")
        }
    
    # Extract attribute options
    attributes = dialog_styles.get("attributes", {})
    
    return {
        "presets": presets,
        "attributes": attributes
    }


@router.get("/", response_model=List[CharacterResponse])
async def get_characters(
    skip: int = 0,
    limit: int = 50,
    include_public: bool = True,
    templates_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's characters and optionally public characters"""
    
    query = db.query(Character)
    
    if include_public:
        # Get user's characters + public characters from others
        query = query.filter(
            (Character.creator_id == current_user.id) | 
            (Character.is_public == True)
        )
    else:
        # Only user's characters
        query = query.filter(Character.creator_id == current_user.id)
    
    if templates_only:
        query = query.filter(Character.is_template == True)
    
    characters = query.offset(skip).limit(limit).all()
    
    return [
        CharacterResponse(
            id=char.id,
            name=char.name,
            description=char.description or "",
            gender=char.gender,
            personality_traits=char.personality_traits or [],
            background=char.background or "",
            goals=char.goals or "",
            fears=char.fears or "",
            appearance=char.appearance or "",
            is_template=char.is_template if char.is_template is not None else True,
            is_public=char.is_public if char.is_public is not None else False,
            voice_style=char.voice_style,
            portrait_image_id=char.portrait_image_id,
            creator_id=char.creator_id,
            created_at=char.created_at.isoformat(),
            updated_at=char.updated_at.isoformat() if char.updated_at else None
        )
        for char in characters
    ]

@router.post("/", response_model=CharacterResponse)
async def create_character(
    character_data: CharacterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new character"""
    
    character = Character(
        name=character_data.name,
        description=character_data.description,
        gender=character_data.gender,
        personality_traits=character_data.personality_traits,
        background=character_data.background,
        goals=character_data.goals,
        fears=character_data.fears,
        appearance=character_data.appearance,
        creator_id=current_user.id,
        is_template=character_data.is_template,
        is_public=character_data.is_public,
        voice_style=character_data.voice_style
    )
    
    db.add(character)
    db.commit()
    db.refresh(character)
    
    return CharacterResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        gender=character.gender,
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        is_template=character.is_template if character.is_template is not None else True,
        is_public=character.is_public if character.is_public is not None else False,
        voice_style=character.voice_style,
        portrait_image_id=character.portrait_image_id,
        creator_id=character.creator_id,
        created_at=character.created_at.isoformat(),
        updated_at=character.updated_at.isoformat() if character.updated_at else None
    )

@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific character"""
    
    character = db.query(Character).filter(
        Character.id == character_id,
        (Character.creator_id == current_user.id) | (Character.is_public == True)
    ).first()
    
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    
    return CharacterResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        gender=character.gender,
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        is_template=character.is_template if character.is_template is not None else True,
        is_public=character.is_public if character.is_public is not None else False,
        voice_style=character.voice_style,
        portrait_image_id=character.portrait_image_id,
        creator_id=character.creator_id,
        created_at=character.created_at.isoformat(),
        updated_at=character.updated_at.isoformat() if character.updated_at else None
    )

@router.put("/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: int,
    character_data: CharacterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a character (only the creator can update)"""
    
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()
    
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found or you don't have permission to edit it"
        )
    
    # Update fields that were provided
    update_data = character_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)
    
    db.commit()
    db.refresh(character)
    
    return CharacterResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        gender=character.gender,
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        is_template=character.is_template if character.is_template is not None else True,
        is_public=character.is_public if character.is_public is not None else False,
        voice_style=character.voice_style,
        portrait_image_id=character.portrait_image_id,
        creator_id=character.creator_id,
        created_at=character.created_at.isoformat(),
        updated_at=character.updated_at.isoformat() if character.updated_at else None
    )

@router.delete("/{character_id}")
async def delete_character(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a character (only the creator can delete)"""
    
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()
    
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found or you don't have permission to delete it"
        )
    
    db.delete(character)
    db.commit()
    
    return {"message": "Character deleted successfully"}


class BulkDeleteRequest(BaseModel):
    character_ids: List[int]


@router.delete("/bulk-delete")
async def bulk_delete_characters(
    request: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk delete multiple characters (only characters owned by the user)"""
    
    if not request.character_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No character IDs provided"
        )
    
    # Find all characters that belong to the current user
    characters = db.query(Character).filter(
        Character.id.in_(request.character_ids),
        Character.creator_id == current_user.id
    ).all()
    
    if not characters:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No characters found or you don't have permission to delete them"
        )
    
    deleted_count = len(characters)
    deleted_ids = [c.id for c in characters]
    
    for character in characters:
        db.delete(character)
    
    db.commit()
    
    return {
        "message": f"Successfully deleted {deleted_count} character(s)",
        "deleted_ids": deleted_ids
    }


@router.post("/generate-with-ai", response_model=CharacterResponse)
async def generate_character_with_ai(
    request: CharacterGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a character using AI from freeform text description"""
    
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt cannot be empty"
        )
    
    try:
        # Get user settings with story context for proper NSFW filtering
        # If story_context includes a story_id, fetch the story for content_rating
        story = None
        if request.story_context and request.story_context.get('story_id'):
            story = db.query(Story).filter(
                Story.id == request.story_context['story_id'],
                Story.owner_id == current_user.id
            ).first()
        
        # This considers both user profile AND story content_rating (if story provided)
        user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user, story)
        
        # Create service instance
        service = CharacterGenerationService(current_user.id, user_settings_dict)
        
        # Generate character
        character_data = await service.generate_character_from_prompt(
            user_prompt=request.prompt,
            story_context=request.story_context,
            previous_generation=request.previous_generation
        )
        
        # Return the generated character data (not saved to DB yet)
        # The frontend will handle saving after user accepts/edits
        return CharacterResponse(
            id=0,  # Temporary ID, will be set when saved
            name=character_data['name'],
            description=character_data.get('description', ''),
            gender=character_data.get('gender'),
            personality_traits=character_data.get('personality_traits', []),
            background=character_data.get('background', ''),
            goals=character_data.get('goals', ''),
            fears=character_data.get('fears', ''),
            appearance=character_data.get('appearance', ''),
            is_template=True,  # Default to template
            is_public=False,  # Default to private
            creator_id=current_user.id,
            created_at="",  # Will be set when saved
            updated_at=None,
            background_structured=character_data.get('background_structured'),
            goals_structured=character_data.get('goals_structured'),
            fears_structured=character_data.get('fears_structured'),
            appearance_structured=character_data.get('appearance_structured')
        )
        
    except ValueError as e:
        logger.error(f"Character generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate character"
        )
    except Exception as e:
        logger.error(f"Unexpected error during character generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while generating the character"
        )


@router.post("/{character_id}/enrich", response_model=CharacterResponse)
async def enrich_character(
    character_id: int,
    request: CharacterEnrichRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enrich a character's empty fields using AI, optionally with story context"""

    # Load character (verify ownership)
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found or you don't have permission to edit it"
        )

    # Build story context if story_id provided
    story_context = None
    if request.story_id:
        story = db.query(Story).filter(
            Story.id == request.story_id,
            Story.owner_id == current_user.id
        ).first()
        if story:
            story_context = {
                'genre': story.genre,
                'tone': story.tone,
                'world_setting': story.world_setting,
                'description': story.description
            }

    # Build character data dict
    character_data = {
        'name': character.name,
        'description': character.description or '',
        'gender': character.gender or '',
        'personality_traits': character.personality_traits or [],
        'background': character.background or '',
        'goals': character.goals or '',
        'fears': character.fears or '',
        'appearance': character.appearance or '',
        'voice_style': character.voice_style,
    }

    try:
        user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user)
        service = CharacterGenerationService(current_user.id, user_settings_dict)
        enriched_fields = await service.enrich_character(character_data, story_context)

        if not enriched_fields:
            # No empty fields to enrich
            pass
        else:
            # Update only the fields that were empty and got filled
            for field, value in enriched_fields.items():
                if field == 'suggested_voice_style':
                    # Apply voice style if character doesn't have one
                    if not character.voice_style and value:
                        character.voice_style = {'preset': value}
                    continue
                current_value = getattr(character, field, None)
                if not current_value or (isinstance(current_value, str) and not current_value.strip()):
                    setattr(character, field, value)

            db.commit()
            db.refresh(character)

        return CharacterResponse(
            id=character.id,
            name=character.name,
            description=character.description or "",
            gender=character.gender,
            personality_traits=character.personality_traits or [],
            background=character.background or "",
            goals=character.goals or "",
            fears=character.fears or "",
            appearance=character.appearance or "",
            is_template=character.is_template if character.is_template is not None else True,
            is_public=character.is_public if character.is_public is not None else False,
            voice_style=character.voice_style,
            portrait_image_id=character.portrait_image_id,
            creator_id=character.creator_id,
            created_at=character.created_at.isoformat(),
            updated_at=character.updated_at.isoformat() if character.updated_at else None
        )

    except ValueError as e:
        logger.error(f"Character enrichment failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enrich character"
        )


@router.get("/{character_id}/stories")
async def get_character_stories(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stories that a character is linked to"""

    # Verify character access
    character = db.query(Character).filter(
        Character.id == character_id,
        (Character.creator_id == current_user.id) | (Character.is_public == True)
    ).first()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )

    # Query StoryCharacter joined with Story
    story_characters = db.query(StoryCharacter).filter(
        StoryCharacter.character_id == character_id
    ).all()

    stories = []
    seen_story_ids = set()
    for sc in story_characters:
        if sc.story_id in seen_story_ids:
            continue
        story = db.query(Story).filter(
            Story.id == sc.story_id,
            Story.owner_id == current_user.id
        ).first()
        if story:
            stories.append({"id": story.id, "title": story.title})
            seen_story_ids.add(story.id)

    return stories


# ============================================================================
# STORY CHARACTER ENDPOINTS (for managing characters within a specific story)
# ============================================================================

class StoryCharacterVoiceUpdate(BaseModel):
    """Schema for updating a story character's voice style override"""
    voice_style_override: Optional[Dict[str, Any]] = None  # Story-specific voice style


class StoryCharacterRoleUpdate(BaseModel):
    """Schema for updating a story character's role"""
    role: str  # Role in the story (protagonist, antagonist, ally, etc.)


class StoryCharacterResponse(BaseModel):
    """Response schema for story characters"""
    id: int  # story_character id
    character_id: int
    story_id: int
    branch_id: Optional[int] = None  # Branch this character belongs to
    role: Optional[str] = None
    voice_style_override: Optional[Dict[str, Any]] = None
    # Include character details
    name: str
    description: Optional[str] = None
    gender: Optional[str] = None
    appearance: Optional[str] = None  # Character appearance
    portrait_image_id: Optional[int] = None  # Portrait image ID
    default_voice_style: Optional[Dict[str, Any]] = None  # Character's default voice style

    class Config:
        from_attributes = True


@router.get("/story/{story_id}/characters", response_model=List[StoryCharacterResponse])
async def get_story_characters(
    story_id: int,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all characters linked to a specific story with their voice style settings.

    Args:
        story_id: The story ID
        branch_id: Optional branch ID to filter characters by branch.
                   If not provided, returns characters from all branches.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[get_story_characters] story_id={story_id}, branch_id={branch_id}")

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

    # Build query with optional branch filter
    query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)

    if branch_id is not None:
        query = query.filter(StoryCharacter.branch_id == branch_id)

    story_characters = query.all()

    result = []
    for sc in story_characters:
        character = db.query(Character).filter(Character.id == sc.character_id).first()
        if character:
            result.append(StoryCharacterResponse(
                id=sc.id,
                character_id=sc.character_id,
                story_id=sc.story_id,
                branch_id=sc.branch_id,
                role=sc.role,
                voice_style_override=sc.voice_style_override,
                name=character.name,
                description=character.description,
                gender=character.gender,
                appearance=character.appearance,
                portrait_image_id=character.portrait_image_id,
                default_voice_style=character.voice_style
            ))

    return result


@router.put("/story/{story_id}/characters/{story_character_id}/voice-style")
async def update_story_character_voice_style(
    story_id: int,
    story_character_id: int,
    update_data: StoryCharacterVoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update the voice style override for a character in a specific story"""
    
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
    
    # Get the story character
    story_character = db.query(StoryCharacter).filter(
        StoryCharacter.id == story_character_id,
        StoryCharacter.story_id == story_id
    ).first()
    
    if not story_character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story character not found"
        )
    
    # Update voice style override
    story_character.voice_style_override = update_data.voice_style_override
    db.commit()
    db.refresh(story_character)
    
    # Get character details for response
    character = db.query(Character).filter(Character.id == story_character.character_id).first()
    
    logger.info(f"Updated voice style override for story_character {story_character_id} in story {story_id}")

    return StoryCharacterResponse(
        id=story_character.id,
        character_id=story_character.character_id,
        story_id=story_character.story_id,
        branch_id=story_character.branch_id,
        role=story_character.role,
        voice_style_override=story_character.voice_style_override,
        name=character.name if character else "Unknown",
        description=character.description if character else None,
        gender=character.gender if character else None,
        default_voice_style=character.voice_style if character else None
    )


@router.delete("/story/{story_id}/characters/{story_character_id}/voice-style")
async def clear_story_character_voice_style(
    story_id: int,
    story_character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clear the voice style override for a character, reverting to their default"""
    
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
    
    # Get the story character
    story_character = db.query(StoryCharacter).filter(
        StoryCharacter.id == story_character_id,
        StoryCharacter.story_id == story_id
    ).first()
    
    if not story_character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story character not found"
        )
    
    # Clear voice style override
    story_character.voice_style_override = None
    db.commit()
    
    logger.info(f"Cleared voice style override for story_character {story_character_id} in story {story_id}")
    
    return {"message": "Voice style override cleared successfully"}


@router.put("/story/{story_id}/characters/{story_character_id}/role")
async def update_story_character_role(
    story_id: int,
    story_character_id: int,
    update_data: StoryCharacterRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update the role for a character in a specific story"""

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

    # Get the story character
    story_character = db.query(StoryCharacter).filter(
        StoryCharacter.id == story_character_id,
        StoryCharacter.story_id == story_id
    ).first()

    if not story_character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story character not found"
        )

    # Update role
    story_character.role = update_data.role
    db.commit()
    db.refresh(story_character)

    # Get character details for response
    character = db.query(Character).filter(Character.id == story_character.character_id).first()

    logger.info(f"Updated role for story_character {story_character_id} in story {story_id} to '{update_data.role}'")

    return StoryCharacterResponse(
        id=story_character.id,
        character_id=story_character.character_id,
        story_id=story_character.story_id,
        branch_id=story_character.branch_id,
        role=story_character.role,
        voice_style_override=story_character.voice_style_override,
        name=character.name if character else "Unknown",
        description=character.description if character else None,
        gender=character.gender if character else None,
        default_voice_style=character.voice_style if character else None
    )


@router.delete("/story/{story_id}/characters/{story_character_id}")
async def remove_character_from_story(
    story_id: int,
    story_character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a character from a story (deletes the StoryCharacter association).

    This does NOT delete the underlying Character from the character library,
    it only removes the character's association with this specific story/branch.
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

    # Get the story character
    story_character = db.query(StoryCharacter).filter(
        StoryCharacter.id == story_character_id,
        StoryCharacter.story_id == story_id
    ).first()

    if not story_character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story character not found"
        )

    # Get character name for logging before deletion
    character = db.query(Character).filter(Character.id == story_character.character_id).first()
    character_name = character.name if character else "Unknown"
    branch_id = story_character.branch_id

    # Delete the story character association
    db.delete(story_character)
    db.commit()

    logger.info(f"Removed character '{character_name}' (story_character_id={story_character_id}) from story {story_id}, branch {branch_id}")

    return {
        "message": f"Character '{character_name}' removed from story",
        "deleted_story_character_id": story_character_id,
        "character_id": character.id if character else None,
        "branch_id": branch_id
    }