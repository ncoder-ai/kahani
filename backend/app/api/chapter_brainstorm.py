"""
Chapter Brainstorming API Endpoints

Handles all chapter brainstorming session management including:
- Creating brainstorm sessions
- Sending messages and getting AI responses
- Extracting chapter plots from conversations
- Managing structured elements
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from pydantic import BaseModel
from ..database import get_db
from ..models import Story, Chapter, User
from ..dependencies import get_current_user
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter()


# ====== PYDANTIC MODELS ======

class ChapterBrainstormCreateRequest(BaseModel):
    """Request for creating a chapter brainstorm session."""
    arc_phase_id: Optional[str] = None
    chapter_id: Optional[int] = None  # If editing an existing chapter
    prior_chapter_summary: Optional[str] = None  # User-provided summary of current/prior chapter


class ChapterBrainstormMessageRequest(BaseModel):
    """Request for sending a message in chapter brainstorm."""
    message: str


class ChapterBrainstormApplyRequest(BaseModel):
    """Request for applying brainstorm to chapter."""
    chapter_id: int


class ChapterBrainstormUpdatePlotRequest(BaseModel):
    """Request for updating extracted plot."""
    plot_data: Dict[str, Any]


class StructuredElementsUpdateRequest(BaseModel):
    """Request model for updating structured elements"""
    element_type: str  # 'overview', 'characters', 'tone', 'key_events', 'ending'
    value: Any  # str for most, list for characters/key_events


class StructuredElementsResponse(BaseModel):
    """Response model for structured elements"""
    session_id: int
    structured_elements: Dict[str, Any]


# ====== HELPER IMPORTS ======

def get_user_settings(current_user: User, db: Session, story: Story = None):
    """Get or create user settings with story context."""
    from .stories import get_or_create_user_settings
    return get_or_create_user_settings(current_user.id, db, current_user, story)


def get_chapter_response_builder():
    """Import build_chapter_response from chapters module."""
    from .chapters import build_chapter_response
    return build_chapter_response


# ====== BRAINSTORM CONTEXT ENDPOINT ======

@router.get("/{story_id}/chapters/{chapter_id}/brainstorm-context")
async def get_chapter_brainstorm_context(
    story_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current chapter's content for brainstorm context.

    Returns the chapter's auto_summary if available, otherwise returns
    a brief from the scene content that can be used as prior context
    for brainstorming the next chapter.

    Args:
        story_id: The story ID
        chapter_id: The chapter ID

    Returns:
        Chapter summary and scene content for context
    """
    from ..models import Scene, SceneVariant, StoryFlow

    # Verify story ownership
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.story_id == story_id
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Get chapter summary if available
    summary = chapter.auto_summary or chapter.story_so_far or chapter.description

    # Get scene content for more detailed context
    scenes = db.query(Scene).filter(
        Scene.chapter_id == chapter_id
    ).order_by(Scene.sequence_number).all()

    scene_contents = []
    for scene in scenes:
        # Get active variant content
        active_flow = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()
        if active_flow:
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == active_flow.active_variant_id
            ).first()
            if variant and variant.content:
                scene_contents.append({
                    "sequence": scene.sequence_number,
                    "content": variant.content,
                    "word_count": len(variant.content.split())
                })

    total_words = sum(s["word_count"] for s in scene_contents)

    return {
        "chapter_id": chapter_id,
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "has_summary": bool(summary),
        "summary": summary,
        "scene_count": len(scene_contents),
        "total_words": total_words,
        "scenes": scene_contents[:10]  # Limit to first 10 scenes for context
    }


# ====== SESSION MANAGEMENT ENDPOINTS ======

@router.post("/{story_id}/chapters/brainstorm")
async def create_chapter_brainstorm_session(
    story_id: int,
    request: ChapterBrainstormCreateRequest = Body(default=ChapterBrainstormCreateRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new chapter brainstorming session.

    Args:
        story_id: The story ID
        request: Optional arc phase ID to target, and optional chapter_id if editing existing chapter

    Returns:
        New session data
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        # Fetch story to get content_rating for NSFW filtering
        story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        user_settings = get_user_settings(current_user, db, story)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        session = service.create_session(
            story_id=story_id,
            arc_phase_id=request.arc_phase_id,
            chapter_id=request.chapter_id,  # Pass chapter_id if editing existing chapter
            prior_chapter_summary=request.prior_chapter_summary  # Pass user-provided summary of prior chapter
        )

        return {
            "session_id": session.id,
            "story_id": session.story_id,
            "chapter_id": session.chapter_id,
            "arc_phase_id": session.arc_phase_id,
            "status": session.status,
            "prior_chapter_summary": session.prior_chapter_summary,
            "created_at": session.created_at.isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:CREATE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.get("/{story_id}/chapters/brainstorm/sessions")
async def list_chapter_brainstorm_sessions(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List chapter brainstorming sessions for a story.

    Args:
        story_id: The story ID

    Returns:
        List of session summaries
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        sessions = service.get_sessions_for_story(story_id)

        return {
            "story_id": story_id,
            "sessions": sessions,
            "count": len(sessions)
        }

    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:LIST] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@router.get("/{story_id}/chapters/brainstorm/{session_id}")
async def get_chapter_brainstorm_session(
    story_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a chapter brainstorming session.

    Args:
        story_id: The story ID
        session_id: The session ID

    Returns:
        Session data including messages and extracted plot
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        session = service.get_session(session_id)

        if not session or session.story_id != story_id:
            raise HTTPException(status_code=404, detail="Session not found")

        return {
            "session_id": session.id,
            "story_id": session.story_id,
            "chapter_id": session.chapter_id,
            "arc_phase_id": session.arc_phase_id,
            "status": session.status,
            "messages": session.messages,
            "extracted_plot": session.extracted_plot,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat() if session.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:GET] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get session")


@router.delete("/{story_id}/chapters/brainstorm/{session_id}")
async def delete_chapter_brainstorm_session(
    story_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a chapter brainstorming session.

    Args:
        story_id: The story ID
        session_id: The session ID

    Returns:
        Success confirmation
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        success = service.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"success": True, "message": "Session deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:DELETE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete session")


# ====== MESSAGE ENDPOINTS ======

@router.post("/{story_id}/chapters/brainstorm/{session_id}/message")
async def send_chapter_brainstorm_message(
    story_id: int,
    session_id: int,
    request: ChapterBrainstormMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a message in chapter brainstorming and get AI response.

    Args:
        story_id: The story ID
        session_id: The session ID
        request: Message content

    Returns:
        AI response and updated message count
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        # Fetch story to get content_rating for NSFW filtering
        story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        user_settings = get_user_settings(current_user, db, story)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        result = await service.send_message(
            session_id=session_id,
            user_message=request.message
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:MESSAGE] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.post("/{story_id}/chapters/brainstorm/{session_id}/message/stream")
async def send_chapter_brainstorm_message_streaming(
    story_id: int,
    session_id: int,
    request: ChapterBrainstormMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a message in chapter brainstorming and stream AI response.

    Uses Server-Sent Events (SSE) to stream the response.

    Event types:
    - thinking_start: LLM is starting to reason
    - thinking_chunk: Chunk of thinking content
    - thinking_end: Thinking complete
    - content: Regular content chunk
    - complete: Full response complete with metadata
    - error: An error occurred

    Args:
        story_id: The story ID
        session_id: The session ID
        request: Message content

    Returns:
        StreamingResponse with SSE events
    """
    from ..services.chapter_brainstorm_service import ChapterBrainstormService

    # Fetch story to get content_rating for NSFW filtering
    story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    user_settings = get_user_settings(current_user, db, story)

    # Create service BEFORE the generator to ensure db session is valid
    service = ChapterBrainstormService(current_user.id, user_settings, db)
    user_message = request.message

    async def generate_stream():
        try:
            async for event in service.send_message_streaming(
                session_id=session_id,
                user_message=user_message
            ):
                yield f"data: {json.dumps(event)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"[CHAPTER_BRAINSTORM:MESSAGE:STREAM] Error: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# ====== PLOT EXTRACTION AND APPLICATION ======

@router.post("/{story_id}/chapters/brainstorm/{session_id}/extract")
async def extract_chapter_plot(
    story_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Extract structured chapter plot from brainstorming conversation.

    Args:
        story_id: The story ID
        session_id: The session ID

    Returns:
        Extracted chapter plot
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        # Fetch story to get content_rating for NSFW filtering
        story = db.query(Story).filter(Story.id == story_id, Story.owner_id == current_user.id).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        user_settings = get_user_settings(current_user, db, story)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        result = await service.extract_chapter_plot(session_id=session_id)

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:EXTRACT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to extract plot")


@router.post("/{story_id}/chapters/brainstorm/{session_id}/apply")
async def apply_brainstorm_to_chapter(
    story_id: int,
    session_id: int,
    request: ChapterBrainstormApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Apply extracted plot to a chapter.

    Args:
        story_id: The story ID
        session_id: The session ID
        request: Chapter ID to apply to

    Returns:
        Updated chapter data
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        chapter = service.apply_to_chapter(
            session_id=session_id,
            chapter_id=request.chapter_id
        )

        build_chapter_response = get_chapter_response_builder()
        return build_chapter_response(chapter, db)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:APPLY] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to apply plot")


@router.put("/{story_id}/chapters/brainstorm/{session_id}/plot")
async def update_chapter_brainstorm_plot(
    story_id: int,
    session_id: int,
    request: ChapterBrainstormUpdatePlotRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the extracted plot (user edits).

    Args:
        story_id: The story ID
        session_id: The session ID
        request: Updated plot data

    Returns:
        Updated plot data
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        result = service.update_extracted_plot(
            session_id=session_id,
            plot_data=request.plot_data
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:UPDATE_PLOT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update plot")


# ====== STRUCTURED ELEMENTS ENDPOINTS ======

@router.get("/{story_id}/chapters/brainstorm/{session_id}/elements")
async def get_chapter_brainstorm_elements(
    story_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current structured elements for a brainstorming session.

    If structured_elements is empty, tries to parse suggestions from the last
    assistant message in the conversation.

    Args:
        story_id: The story ID
        session_id: The session ID

    Returns:
        Current structured elements with defaults for missing ones,
        plus any suggested_elements parsed from the last message
    """
    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService, parse_element_suggestions

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        session = service.get_session(session_id)
        if not session or session.story_id != story_id:
            raise HTTPException(status_code=404, detail="Session not found")

        structured_elements = session.get_structured_elements()
        suggested_elements = None

        # If structured_elements is mostly empty, try to parse from last assistant message
        has_confirmed = any([
            structured_elements.get('overview'),
            structured_elements.get('tone'),
            structured_elements.get('ending'),
            len(structured_elements.get('key_events', [])) > 0,
            len(structured_elements.get('characters', [])) > 0
        ])

        if not has_confirmed and session.messages:
            # Find the last assistant message
            for msg in reversed(session.messages):
                if msg.get('role') == 'assistant':
                    _, parsed_suggestions = parse_element_suggestions(msg.get('content', ''))
                    if parsed_suggestions:
                        suggested_elements = parsed_suggestions
                        logger.info(f"[CHAPTER_BRAINSTORM:GET_ELEMENTS] Parsed suggestions from last message: {list(parsed_suggestions.keys())}")
                    break

        result = {
            "session_id": session.id,
            "structured_elements": structured_elements
        }

        if suggested_elements:
            result["suggested_elements"] = suggested_elements

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:GET_ELEMENTS] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get elements")


@router.put("/{story_id}/chapters/brainstorm/{session_id}/elements")
async def update_chapter_brainstorm_element(
    story_id: int,
    session_id: int,
    request: StructuredElementsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a single structured element in a brainstorming session.

    Args:
        story_id: The story ID
        session_id: The session ID
        request: Element type and value to update

    Returns:
        Updated structured elements
    """
    valid_element_types = ['overview', 'characters', 'tone', 'key_events', 'ending']
    if request.element_type not in valid_element_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid element_type. Must be one of: {', '.join(valid_element_types)}"
        )

    try:
        from ..services.chapter_brainstorm_service import ChapterBrainstormService

        user_settings = get_user_settings(current_user, db)
        service = ChapterBrainstormService(current_user.id, user_settings, db)

        result = service.update_structured_element(
            session_id=session_id,
            element_type=request.element_type,
            value=request.value
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAPTER_BRAINSTORM:UPDATE_ELEMENT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update element")
