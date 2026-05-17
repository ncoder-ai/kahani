"""
Brainstorm API Router

Endpoints for AI-powered story brainstorming sessions.
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..dependencies import get_current_user
from ..models.user import User
from ..models.brainstorm_session import BrainstormSession
from ..services.brainstorm_service import BrainstormService
from ..services.character_generation_service import CharacterGenerationService
from ..api.stories import get_or_create_user_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brainstorm", tags=["brainstorm"])


# ====== REQUEST/RESPONSE MODELS ======

class ChatMessageRequest(BaseModel):
    """Request for sending a chat message."""
    session_id: int
    message: str
    generate_ideas: bool = False


class ExtractElementsRequest(BaseModel):
    """Request for extracting story elements."""
    session_id: int


class UpdateElementsRequest(BaseModel):
    """Request for updating extracted elements."""
    session_id: int
    elements: Dict[str, Any]


class CompleteSessionRequest(BaseModel):
    """Request for marking session as completed."""
    session_id: int
    story_id: int


class CreateSessionRequest(BaseModel):
    """Request for creating a new session."""
    pre_selected_character_ids: list[int] = []
    content_rating: str = "sfw"  # "sfw" or "nsfw"


# ====== SESSION MANAGEMENT ======

@router.post("/session")
async def create_brainstorm_session(
    request: CreateSessionRequest = Body(default=CreateSessionRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new brainstorming session.
    
    Args:
        request: Optional pre-selected character IDs
    
    Returns:
        New session data with ID
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Create service and session with content rating
        service = BrainstormService(current_user.id, user_settings, db)
        session = service.create_session(
            pre_selected_character_ids=request.pre_selected_character_ids,
            content_rating=request.content_rating
        )
        
        return {
            "session_id": session.id,
            "status": session.status,
            "message_count": len(session.messages),
            "created_at": session.created_at.isoformat(),
            "content_rating": request.content_rating
        }
        
    except Exception as e:
        logger.error(f"[BRAINSTORM:CREATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.get("/session/{session_id}")
async def get_brainstorm_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get brainstorm session details.
    
    Args:
        session_id: The session ID
        
    Returns:
        Session data including messages and extracted elements
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Get session
        service = BrainstormService(current_user.id, user_settings, db)
        session = service.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "session_id": session.id,
            "status": session.status,
            "messages": session.messages,
            "extracted_elements": session.extracted_elements,
            "story_id": session.story_id,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BRAINSTORM:GET] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get session")


@router.delete("/session/{session_id}")
async def delete_brainstorm_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a brainstorming session.
    
    Args:
        session_id: The session ID
        
    Returns:
        Success confirmation
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Delete session
        service = BrainstormService(current_user.id, user_settings, db)
        success = service.delete_session(session_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"success": True, "message": "Session deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BRAINSTORM:DELETE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete session")


# ====== CHAT INTERACTION ======

@router.post("/chat")
async def send_chat_message(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a message in brainstorming chat and get AI response.
    
    Args:
        request: Chat message request with session_id and message
        
    Returns:
        AI response and updated message count
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Send message and get response
        logger.info(f"[BRAINSTORM API] Received chat request - session_id={request.session_id}, generate_ideas={request.generate_ideas}, message_len={len(request.message)}")
        service = BrainstormService(current_user.id, user_settings, db)
        result = await service.send_message(
            session_id=request.session_id,
            user_message=request.message,
            generate_ideas=request.generate_ideas
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[BRAINSTORM:CHAT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send message")


# ====== ELEMENT EXTRACTION ======

@router.post("/extract")
async def extract_story_elements(
    request: ExtractElementsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Extract structured story elements from brainstorming conversation.
    
    Analyzes the conversation history and extracts:
    - Genre and tone
    - Characters
    - World setting
    - Scenario/premise
    - Plot points
    - Themes and conflicts
    - Title suggestions
    
    Args:
        request: Extraction request with session_id
        
    Returns:
        Extracted story elements
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Extract elements
        service = BrainstormService(current_user.id, user_settings, db)
        result = await service.extract_elements(session_id=request.session_id)
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[BRAINSTORM:EXTRACT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to extract elements")


@router.post("/elements/update")
async def update_story_elements(
    request: UpdateElementsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update extracted story elements (user refinement).
    
    Args:
        request: Update request with session_id and elements
        
    Returns:
        Updated elements
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Update elements
        service = BrainstormService(current_user.id, user_settings, db)
        result = service.update_elements(
            session_id=request.session_id,
            updated_elements=request.elements
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[BRAINSTORM:UPDATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update elements")


@router.post("/complete")
async def complete_brainstorm_session(
    request: CompleteSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark brainstorm session as completed and link to created story.
    
    Args:
        request: Completion request with session_id and story_id
        
    Returns:
        Updated session data
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Mark completed
        service = BrainstormService(current_user.id, user_settings, db)
        session = service.mark_completed(
            session_id=request.session_id,
            story_id=request.story_id
        )
        
        return {
            "session_id": session.id,
            "status": session.status,
            "story_id": session.story_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[BRAINSTORM:COMPLETE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to complete session")


@router.get("/sessions/list")
async def list_user_sessions(
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List user's brainstorming sessions.
    
    Args:
        skip: Number of sessions to skip (pagination)
        limit: Maximum number of sessions to return
        
    Returns:
        List of session summaries
    """
    try:
        sessions = db.query(BrainstormSession).filter(
            BrainstormSession.user_id == current_user.id
        ).order_by(
            BrainstormSession.updated_at.desc()
        ).offset(skip).limit(limit).all()
        
        return [
            {
                "session_id": session.id,
                "status": session.status,
                "message_count": len(session.messages) if session.messages else 0,
                "has_elements": bool(session.extracted_elements),
                "story_id": session.story_id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat()
            }
            for session in sessions
        ]
        
    except Exception as e:
        logger.error(f"[BRAINSTORM:LIST] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@router.get("/sessions")
async def get_user_brainstorm_sessions(
    include_completed: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's brainstorming sessions with summaries.
    
    This endpoint returns sessions with generated summaries for display
    on the dashboard, allowing users to resume incomplete sessions.
    
    Args:
        include_completed: If True, include completed sessions
        
    Returns:
        List of session summaries with context
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Get sessions using service method
        service = BrainstormService(current_user.id, user_settings, db)
        sessions = service.get_user_sessions(include_completed=include_completed)
        
        return {
            "sessions": sessions,
            "count": len(sessions)
        }
        
    except Exception as e:
        logger.error(f"[BRAINSTORM:SESSIONS] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get sessions")


# ====== STORY ARC GENERATION ======

class GenerateArcFromSessionRequest(BaseModel):
    """Request for generating story arc from session."""
    structure_type: str = "three_act"  # three_act, five_act, hero_journey


@router.post("/sessions/{session_id}/generate-arc")
async def generate_arc_from_session(
    session_id: int,
    request: GenerateArcFromSessionRequest = Body(default=GenerateArcFromSessionRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a story arc from the brainstorm session's extracted elements.
    
    This allows generating an arc before the story is created.
    
    Args:
        session_id: The brainstorming session ID
        request: Arc generation options (structure type)
        
    Returns:
        Generated story arc
    """
    try:
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        service = BrainstormService(current_user.id, user_settings, db)
        
        result = await service.generate_arc_from_session(
            session_id=session_id,
            structure_type=request.structure_type
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[BRAINSTORM:GEN_ARC] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate story arc")


# ====== CHARACTER GENERATION ======

@router.post("/sessions/{session_id}/generate-characters")
async def generate_characters_for_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate additional characters based on the story elements in the brainstorm session.
    
    Uses the existing character generation service to create characters that fit
    the story's genre, tone, and world setting.
    
    Args:
        session_id: The brainstorming session ID
        
    Returns:
        List of generated characters
    """
    try:
        # Get user settings
        user_settings = get_or_create_user_settings(current_user.id, db, current_user)
        
        # Get session
        brainstorm_service = BrainstormService(current_user.id, user_settings, db)
        session = brainstorm_service.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get extracted elements
        elements = session.extracted_elements or {}
        
        # Build story context for character generation
        story_context = {
            'genre': elements.get('genre', ''),
            'tone': elements.get('tone', ''),
            'world_setting': elements.get('world_setting', ''),
            'description': elements.get('description', ''),
            'scenario': elements.get('scenario', '')
        }
        
        # Build a prompt for character generation based on story elements
        character_prompt = f"Generate 2-3 diverse characters for this story"
        if story_context.get('description'):
            character_prompt += f": {story_context['description'][:200]}"
        
        # Use character generation service
        char_gen_service = CharacterGenerationService(current_user.id, user_settings)
        
        # Generate multiple characters (we'll call it 2-3 times)
        generated_characters = []
        num_characters = 3
        
        for i in range(num_characters):
            try:
                char_data = await char_gen_service.generate_character_from_prompt(
                    user_prompt=character_prompt,
                    story_context=story_context,
                    previous_generation=generated_characters[-1] if generated_characters else None
                )
                
                # Format for brainstorm session (simpler format)
                brainstorm_char = {
                    'name': char_data.get('name', f'Character {i+1}'),
                    'role': 'other',  # Default role
                    'description': char_data.get('description', ''),
                    'personality_traits': char_data.get('personality_traits', [])
                }
                
                generated_characters.append(brainstorm_char)
                
            except Exception as e:
                logger.warning(f"[BRAINSTORM:GEN_CHAR] Failed to generate character {i+1}: {str(e)}")
                continue
        
        if not generated_characters:
            raise HTTPException(status_code=500, detail="Failed to generate any characters")
        
        logger.info(f"[BRAINSTORM:GEN_CHAR] Generated {len(generated_characters)} characters for session {session_id}")
        
        return {
            "session_id": session_id,
            "characters": generated_characters,
            "count": len(generated_characters)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BRAINSTORM:GEN_CHAR] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate characters")

