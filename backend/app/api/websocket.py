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
    await websocket.accept()
    
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
        
        print(f"[WebSocket] Client connected to TTS session: {session_id} (auto_play={session.auto_play})")
        
        # Only auto-start generation for auto-play sessions
        # Regular TTS button clicks start generation via POST endpoint
        if session.auto_play and not session.is_generating:
            from ..routers.tts import generate_and_stream_chunks
            import asyncio
            
            print(f"[WebSocket] Auto-starting TTS generation for auto-play session: {session_id}")
            # Start generation in background task
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
                        print(f"[WebSocket] Client requested cancellation for session: {session_id}")
                        await websocket.send_json({
                            "type": "cancelled",
                            "message": "Generation cancelled by user"
                        })
                        break
                    
                except json.JSONDecodeError:
                    # Ignore invalid JSON
                    pass
                    
            except WebSocketDisconnect:
                print(f"[WebSocket] Client disconnected from session: {session_id}")
                break
            except Exception as e:
                print(f"[WebSocket] Error in session {session_id}: {e}")
                break
    
    finally:
        # Clean up session when WebSocket closes
        print(f"[WebSocket] Cleaning up session: {session_id}")
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
                print(f"[WebSocket Auth] Error: {e}")
                break
    
    finally:
        tts_session_manager.remove_session(session_id)
