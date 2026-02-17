from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from ..database import get_db
from ..models import Character, StoryCharacter, User, UserSettings, Story
from ..dependencies import get_current_user
from ..services.character_assistant_service import CharacterAssistantService
from .stories import get_or_create_user_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Test endpoint for debugging
@router.post("/test/character-detection")
async def test_character_detection(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test endpoint to verify character detection is working"""
    try:
        # Get user settings
        user_settings = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        settings_dict = user_settings.to_dict() if user_settings else {}
        
        service = CharacterAssistantService(current_user.id, settings_dict)
        
        test_scenes = [
            "John walked into the room and saw Mary sitting at the table.",
            "Sarah greeted John warmly and offered him some coffee."
        ]
        
        logger.info(f"Testing character detection with {len(test_scenes)} test scenes")
        result = await service._extract_characters_with_llm(test_scenes)
        
        return {
            "success": True,
            "test_input": test_scenes,
            "result": result,
            "result_count": len(result)
        }
    except Exception as e:
        logger.error(f"Test endpoint failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# Pydantic models for request/response
class CharacterSuggestion(BaseModel):
    name: str
    mention_count: int
    importance_score: int
    first_appearance_scene: int
    last_appearance_scene: int
    is_in_library: bool
    preview: str
    scenes: List[int]

class CharacterSuggestionsResponse(BaseModel):
    suggestions: List[CharacterSuggestion]
    chapter_analyzed: Optional[int]
    total_scenes_analyzed: int

class CharacterDetails(BaseModel):
    name: str
    description: str
    personality_traits: List[str]
    background: str
    goals: str
    fears: str
    appearance: str
    suggested_role: str
    suggested_voice_style: Optional[str] = None  # AI-suggested voice style preset
    confidence: float
    scenes_analyzed: List[int]

class CharacterCreateFromSuggestion(BaseModel):
    name: str
    description: str
    personality_traits: List[str]
    background: str
    goals: str
    fears: str
    appearance: str
    role: str

class CharacterCreatedResponse(BaseModel):
    id: int
    name: str
    description: str
    personality_traits: List[str]
    background: str
    goals: str
    fears: str
    appearance: str
    role: str
    story_character_id: int

@router.get("/{story_id}/character-suggestions", response_model=CharacterSuggestionsResponse)
async def get_character_suggestions(
    story_id: int,
    chapter_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get character suggestions for a story chapter.

    Args:
        branch_id: Optional branch ID to filter suggestions. If not provided,
                   uses the active branch for the story.
    """

    # Verify story ownership
    from ..models import Story, StoryBranch
    from ..models.npc_tracking import NPCTracking
    from sqlalchemy import and_
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
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        branch_id = active_branch.id if active_branch else None
    
    # DEBUG: Log branch info
    logger.info(f"[CHAR-SUGGEST] story_id={story_id}, story.current_branch_id={story.current_branch_id}, active_branch_id={branch_id}")
    
    # DEBUG: Log all branches for this story
    all_branches = db.query(StoryBranch).filter(StoryBranch.story_id == story_id).all()
    for b in all_branches:
        logger.info(f"[CHAR-SUGGEST]   Branch {b.id}: name='{b.name}', is_active={b.is_active}, is_main={b.is_main}")
    
    # DEBUG: Log all NPCTracking records for this story (grouped by branch)
    all_npcs = db.query(NPCTracking).filter(NPCTracking.story_id == story_id).all()
    logger.info(f"[CHAR-SUGGEST] Total NPCTracking records for story {story_id}: {len(all_npcs)}")
    npc_by_branch = {}
    for npc in all_npcs:
        bid = npc.branch_id
        if bid not in npc_by_branch:
            npc_by_branch[bid] = []
        npc_by_branch[bid].append(npc.character_name)
    for bid, names in npc_by_branch.items():
        logger.info(f"[CHAR-SUGGEST]   Branch {bid}: {len(names)} NPCs - {names[:10]}{'...' if len(names) > 10 else ''}")
    
    # Get user settings with story context for proper NSFW filtering
    # This considers both user profile AND story content_rating
    user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user, story)
    
    # Use NPC tracking data directly - no redundant LLM extraction
    # NPCTrackingService already extracts and tracks all characters during scene generation
    try:
        from ..services.npc_tracking_service import NPCTrackingService
        npc_service = NPCTrackingService(current_user.id, user_settings_dict)

        # Use importance threshold from user settings (default 10.0 to filter out minor mentions)
        min_importance = user_settings_dict.get('character_assistant_settings', {}).get('importance_threshold', 10.0)
        suggestions = npc_service.get_npcs_as_suggestions(db, story_id, min_importance=min_importance, branch_id=branch_id)
        
        # Sort by importance score
        suggestions.sort(key=lambda x: x.get('importance_score', 0), reverse=True)
        
        logger.info(f"[CHAR-SUGGEST] Retrieved {len(suggestions)} suggestions for branch_id={branch_id}")
        for s in suggestions[:5]:
            logger.info(f"[CHAR-SUGGEST]   - {s.get('name')}: importance={s.get('importance_score')}, first_scene={s.get('first_appearance_scene')}, last_scene={s.get('last_appearance_scene')}")
    except Exception as e:
        logger.error(f"Failed to get NPC suggestions: {e}")
        import traceback
        logger.error(f"[CHAR-SUGGEST] Traceback: {traceback.format_exc()}")
        # Return empty list if NPC tracking fails
        suggestions = []
    
    # Get chapter info
    chapter_info = None
    if chapter_id:
        from ..models import Chapter
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if chapter:
            chapter_info = chapter.chapter_number
    
    # Count total scenes analyzed
    total_scenes = len(suggestions) if suggestions else 0
    
    return CharacterSuggestionsResponse(
        suggestions=suggestions,
        chapter_analyzed=chapter_info,
        total_scenes_analyzed=total_scenes
    )

@router.post("/{story_id}/character-suggestions/{character_name}/analyze", response_model=CharacterDetails)
async def analyze_character_details(
    story_id: int,
    character_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze detailed character information using LLM."""
    
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
    
    # Get user settings with story context for proper NSFW filtering
    # This considers both user profile AND story content_rating
    user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user, story)
    
    # First, check if NPC tracking has already extracted a profile
    # This avoids redundant LLM calls and uses pre-computed data
    try:
        from ..models import NPCTracking
        npc_tracking = db.query(NPCTracking).filter(
            NPCTracking.story_id == story_id,
            NPCTracking.character_name == character_name,
            NPCTracking.profile_extracted == True
        ).first()
        
        if npc_tracking and npc_tracking.extracted_profile:
            profile = npc_tracking.extracted_profile
            
            # Check if profile has meaningful content
            has_content = (
                profile.get("description") or 
                profile.get("personality") or 
                profile.get("background") or 
                profile.get("goals") or
                profile.get("appearance")
            )
            
            if has_content:
                logger.info(f"Using pre-extracted NPC profile for {character_name} (no LLM call needed)")
                # Use the already-extracted profile
                character_details = {
                    "name": profile.get("name", character_name),
                    "description": profile.get("description", ""),
                    "personality_traits": profile.get("personality", []),
                    "background": profile.get("background", ""),
                    "goals": profile.get("goals", ""),
                    "fears": profile.get("fears", ""),  # Include fears if available
                    "appearance": profile.get("appearance", ""),
                    "suggested_role": profile.get("role", "other"),
                    "suggested_voice_style": profile.get("voice_style", "neutral"),  # Include voice style if available
                    "confidence": 85,  # High confidence for extracted profiles
                    "scenes_analyzed": []
                }
                return CharacterDetails(**character_details)
            else:
                logger.info(f"NPC profile for {character_name} exists but is empty, extracting fresh")
                # Fall through to fresh extraction
    except Exception as e:
        logger.debug(f"NPC profile not found for {character_name}, will extract fresh: {e}")
    
    # Create service instance
    service = CharacterAssistantService(current_user.id, user_settings_dict)
    
    try:
        # Extract character details
        logger.info(f"Extracting character details for '{character_name}' in story {story_id}")
        character_details = await service.extract_character_details(db, story_id, character_name)
        
        if not character_details:
            logger.error(f"No character details returned for {character_name} in story {story_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found or could not be analyzed"
            )
        
        logger.info(f"Successfully extracted character details for {character_name}: {list(character_details.keys())}")
        return CharacterDetails(**character_details)
    except ValueError as e:
        logger.error(f"Character extraction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze character"
        )
    except Exception as e:
        logger.error(f"Unexpected error during character extraction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while analyzing the character"
        )

@router.post("/{story_id}/character-suggestions/{character_name}/create", response_model=CharacterCreatedResponse)
async def create_character_from_suggestion(
    story_id: int,
    character_name: str,
    character_data: CharacterCreateFromSuggestion,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a character in the library and link it to the story."""
    
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
    
    # Get user settings with story context for proper NSFW filtering
    # This considers both user profile AND story content_rating
    user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user, story)
    
    # Check if character already exists
    existing_character = db.query(Character).filter(
        Character.name == character_data.name,
        Character.creator_id == current_user.id
    ).first()
    
    if existing_character:
        # Use existing character
        character = existing_character
    else:
        # Create new character
        character = Character(
            name=character_data.name,
            description=character_data.description,
            personality_traits=character_data.personality_traits,
            background=character_data.background,
            goals=character_data.goals,
            fears=character_data.fears,
            appearance=character_data.appearance,
            creator_id=current_user.id,
            is_template=True,  # Characters discovered from story should be templates
            is_public=False
        )
        db.add(character)
        db.flush()  # Get the character ID
    
    # Get the active branch for this character association
    active_branch_id = story.current_branch_id

    # Check if story character relationship already exists for this branch
    existing_story_char = db.query(StoryCharacter).filter(
        StoryCharacter.story_id == story_id,
        StoryCharacter.branch_id == active_branch_id,
        StoryCharacter.character_id == character.id
    ).first()

    if not existing_story_char:
        # Create story character relationship with branch
        story_character = StoryCharacter(
            story_id=story_id,
            branch_id=active_branch_id,
            character_id=character.id,
            role=character_data.role
        )
        db.add(story_character)
        db.flush()  # Get the story character ID
        logger.info(f"Created StoryCharacter for '{character.name}' in story {story_id}, branch {active_branch_id}")
    else:
        story_character = existing_story_char
    
    # Mark NPC as converted if it was tracked as an NPC
    # Try both the original character_name (from URL, the NPC name) and character_data.name (user may have changed it)
    try:
        from ..services.npc_tracking_service import NPCTrackingService
        npc_service = NPCTrackingService(current_user.id, user_settings_dict)
        # Try original NPC name first (from URL parameter)
        marked = npc_service.mark_npc_as_converted(db, story_id, character_name)
        # If not found, try the new character name (user may have changed it)
        if not marked:
            npc_service.mark_npc_as_converted(db, story_id, character_data.name)
    except Exception as e:
        logger.warning(f"Failed to mark NPC as converted: {e}")
        # Don't fail character creation if NPC marking fails
    
    db.commit()
    db.refresh(character)
    
    return CharacterCreatedResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        role=story_character.role or "",
        story_character_id=story_character.id
    )

@router.get("/{story_id}/character-importance-check")
async def check_character_importance(
    story_id: int,
    chapter_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if any new important characters are detected using NPC tracking.

    Args:
        branch_id: Optional branch ID to filter NPCs. If not provided,
                   checks NPCs across all branches.
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

    # Get user settings with story context for proper NSFW filtering
    # This considers both user profile AND story content_rating
    user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user, story)

    # Check NPC tracking for characters that haven't been converted
    try:
        from ..services.npc_tracking_service import NPCTrackingService
        from ..models import NPCTracking

        npc_service = NPCTrackingService(current_user.id, user_settings_dict)

        # Get all NPCs that haven't been converted to characters, filtered by branch if provided
        query = db.query(NPCTracking).filter(
            NPCTracking.story_id == story_id,
            NPCTracking.converted_to_character == False
        )
        if branch_id is not None:
            query = query.filter(NPCTracking.branch_id == branch_id)
        npcs = query.all()
        
        # Check if any NPCs exist (regardless of threshold for discovery purposes)
        has_characters = len(npcs) > 0
        
        logger.info(f"Character importance check for story {story_id}: {len(npcs)} NPCs found, has_characters={has_characters}")
        
        return {
            "new_character_detected": has_characters,
            "importance_threshold": npc_service.importance_threshold,
            "mention_threshold": 0  # Not applicable for NPC tracking
        }
    except Exception as e:
        logger.error(f"Failed to check character importance: {e}")
        return {
            "new_character_detected": False,
            "importance_threshold": 0,
            "mention_threshold": 0
        }

@router.post("/{story_id}/npcs/recalculate-scores")
async def recalculate_npc_scores(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Recalculate importance scores for all NPCs in a story."""
    try:
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
        
        # Get user settings with story context for proper NSFW filtering
        # This considers both user profile AND story content_rating
        user_settings_dict = get_or_create_user_settings(current_user.id, db, current_user, story)
        
        from ..services.npc_tracking_service import NPCTrackingService
        
        npc_service = NPCTrackingService(
            user_id=current_user.id,
            user_settings=user_settings_dict
        )
        
        result = await npc_service.recalculate_all_scores(db, story_id)
        
        if result["success"]:
            return {
                "success": True,
                "message": f"Recalculated {result['npcs_recalculated']} NPC scores"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Unknown error")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to recalculate NPC scores: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
