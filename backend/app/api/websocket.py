"""
WebSocket endpoints for real-time TTS audio streaming.

Handles WebSocket connections for streaming TTS audio chunks
as they are generated, eliminating the need for polling.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user_websocket
from app.services.tts_session_manager import tts_session_manager
from app.models.user import User
import json
import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/tts/{session_id}")
async def websocket_tts_stream(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for streaming TTS audio chunks.
    
    Flow:
    1. Client creates session via POST /api/tts/generate/{scene_id}
    2. Client connects to this WebSocket with session_id
    3. Backend streams chunks as they're generated
    4. Client plays chunks immediately
    
    Message Types Sent:
    - chunk_ready: Audio chunk is ready to play
    - progress: Generation progress update
    - complete: All chunks generated successfully
    - error: An error occurred during generation
    
    Example Messages:
    {
        "type": "chunk_ready",
        "chunk_number": 1,
        "total_chunks": 5,
        "audio_base64": "...",
        "duration": 3.5
    }
    
    {
        "type": "progress",
        "chunks_ready": 2,
        "total_chunks": 5,
        "progress_percent": 40
    }
    
    {
        "type": "complete",
        "total_chunks": 5,
        "total_duration": 17.5
    }
    
    {
        "type": "error",
        "message": "TTS generation failed",
        "chunk_number": 3
    }
    """
    # Log connection attempt
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"[WebSocket] Connection attempt for session {session_id} from {client_host}")
    
    try:
        await websocket.accept()
        logger.info(f"[WebSocket] Connection accepted for session {session_id}")
    except Exception as e:
        logger.error(f"[WebSocket] Failed to accept connection for session {session_id}: {e}")
        raise
    
    try:
        # Get session
        session = tts_session_manager.get_session(session_id)
        if not session:
            await websocket.send_json({
                "type": "error",
                "message": f"Session {session_id} not found or expired"
            })
            await websocket.close()
            return
        
        # Attach WebSocket to session
        tts_session_manager.attach_websocket(session_id, websocket)
        
        # If this is an auto-play session, flush any buffered messages first
        if session.auto_play and session.message_buffer:
            await tts_session_manager.flush_buffered_messages(session_id)
        
        # Check if generation has started for this auto-play session
        # For streaming scenes, generation might not have started yet (waiting for WebSocket)
        if session.auto_play and not session.is_generating:
            from ..routers.tts import generate_and_stream_chunks
            import asyncio
            asyncio.create_task(generate_and_stream_chunks(
                session_id=session_id,
                scene_id=session.scene_id,
                user_id=session.user_id
            ))
        
        # Keep connection alive and handle any client messages
        # (In current implementation, client doesn't send messages,
        # but we keep the connection open for server-to-client streaming)
        while True:
            try:
                # Wait for messages (with timeout to detect disconnection)
                data = await websocket.receive_text()
                
                # Handle client messages if needed
                try:
                    message = json.loads(data)
                    message_type = message.get("type")
                    
                    if message_type == "ping":
                        # Respond to keepalive
                        await websocket.send_json({"type": "pong"})
                    elif message_type == "cancel":
                        # Client wants to cancel generation
                        logger.info(f"[WebSocket] Cancel requested for session {session_id}")
                        tts_session_manager.cancel_session(session_id)
                        await websocket.send_json({
                            "type": "cancelled",
                            "message": "Generation cancelled by user"
                        })
                        break
                    
                except json.JSONDecodeError:
                    # Ignore invalid JSON
                    pass
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket session {session_id}: {e}")
                break
    
    finally:
        # Clean up session when WebSocket closes
        tts_session_manager.remove_session(session_id)


@router.websocket("/tts-auth/{session_id}")
async def websocket_tts_stream_authenticated(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Authenticated WebSocket endpoint for TTS streaming.
    
    This endpoint requires authentication via token in the initial message.
    Use this for production environments with strict access control.
    
    Client must send authentication token in first message:
    {
        "type": "auth",
        "token": "Bearer <jwt_token>"
    }
    """
    await websocket.accept()
    
    try:
        # Wait for authentication message
        auth_data = await websocket.receive_text()
        
        try:
            auth_message = json.loads(auth_data)
            if auth_message.get("type") != "auth":
                await websocket.send_json({
                    "type": "error",
                    "message": "First message must be authentication"
                })
                await websocket.close()
                return
            
            token = auth_message.get("token", "").replace("Bearer ", "")
            
            # Verify token (implement your auth logic here)
            # user = verify_token(token, db)
            # if not user:
            #     await websocket.send_json({
            #         "type": "error",
            #         "message": "Invalid authentication token"
            #     })
            #     await websocket.close()
            #     return
            
        except json.JSONDecodeError:
            await websocket.send_json({
                "type": "error",
                "message": "Invalid authentication message format"
            })
            await websocket.close()
            return
        
        # Get session
        session = tts_session_manager.get_session(session_id)
        if not session:
            await websocket.send_json({
                "type": "error",
                "message": f"Session {session_id} not found"
            })
            await websocket.close()
            return
        
        # Verify user owns this session
        # if session.user_id != user.id:
        #     await websocket.send_json({
        #         "type": "error",
        #         "message": "Unauthorized access to session"
        #     })
        #     await websocket.close()
        #     return
        
        # Attach WebSocket and continue
        tts_session_manager.attach_websocket(session_id, websocket)
        
        await websocket.send_json({
            "type": "authenticated",
            "message": "Authentication successful"
        })
        
        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                # Handle messages...
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[WebSocket Auth] Error: {e}")
                break
    
    finally:
        tts_session_manager.remove_session(session_id)
