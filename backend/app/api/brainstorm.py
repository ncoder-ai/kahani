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
from ..api.stories import get_or_create_user_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brainstorm", tags=["brainstorm"])


# ====== REQUEST/RESPONSE MODELS ======

class ChatMessageRequest(BaseModel):
    """Request for sending a chat message."""
    session_id: int
    message: str


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
        
        # Create service and session
        service = BrainstormService(current_user.id, user_settings, db)
        session = service.create_session(pre_selected_character_ids=request.pre_selected_character_ids)
        
        return {
            "session_id": session.id,
            "status": session.status,
            "message_count": len(session.messages),
            "created_at": session.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"[BRAINSTORM:CREATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


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
        service = BrainstormService(current_user.id, user_settings, db)
        result = await service.send_message(
            session_id=request.session_id,
            user_message=request.message
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[BRAINSTORM:CHAT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to extract elements: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to update elements: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to complete session: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

