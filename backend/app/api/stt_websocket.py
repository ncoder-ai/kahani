"""
WebSocket endpoints for real-time STT audio streaming.

Handles WebSocket connections for streaming audio chunks
and receiving real-time transcription results.
"""

import asyncio
import logging
import json
import base64
import io
import wave
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.stt_session_manager import stt_session_manager
from app.services.stt_service import stt_service
from app.models.user import User
from app.models.user_settings import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["stt-websocket"])


@router.websocket("/stt/{session_id}")
async def websocket_stt_stream(
    websocket: WebSocket,
    session_id: str
):
    """
    WebSocket endpoint for real-time STT audio streaming.
    
    Flow:
    1. Client creates session via POST /api/stt/create-session
    2. Client connects to this WebSocket with session_id
    3. Client sends audio chunks as binary data
    4. Backend processes audio and streams transcription results
    
    Message Types Received:
    - Binary audio data (WebM/Opus chunks)
    
    Message Types Sent:
    - partial: Live transcription (words as detected)
    - final: Sentence complete (after VAD silence)
    - complete: Full transcription done
    - error: An error occurred during processing
    - status: Recording/transcribing status updates
    
    Example Messages:
    {
        "type": "partial",
        "text": "Hello world",
        "confidence": 0.95
    }
    
    {
        "type": "final",
        "text": "Hello world, how are you?",
        "confidence": 0.92
    }
    
    {
        "type": "status",
        "recording": true,
        "transcribing": false
    }
    
    {
        "type": "error",
        "message": "Audio processing failed"
    }
    """
    await websocket.accept()
    
    try:
        # Get session
        session = stt_session_manager.get_session(session_id)
        if not session:
            await websocket.send_json({
                "type": "error",
                "message": f"Session {session_id} not found or expired"
            })
            await websocket.close()
            return
        
        # Attach WebSocket to session
        stt_session_manager.attach_websocket(session_id, websocket)
        
        logger.info(f"[STT WebSocket] Client connected to session: {session_id}")
        
        # Set up STT callbacks
        async def on_final(text: str):
            """Called when transcription is finalized."""
            stt_session_manager.update_transcript(session_id, text, is_partial=False)
            await stt_session_manager.send_message(session_id, {
                "type": "final",
                "text": text,
                "timestamp": asyncio.get_event_loop().time()
            })
        
        async def on_partial(text: str):
            """Called during live transcription updates."""
            stt_session_manager.update_transcript(session_id, text, is_partial=True)
            await stt_session_manager.send_message(session_id, {
                "type": "partial",
                "text": text,
                "timestamp": asyncio.get_event_loop().time()
            })
        
        async def on_error(error: Exception):
            """Called on processing errors."""
            error_msg = str(error)
            stt_session_manager.set_error(session_id, error_msg)
            await stt_session_manager.send_message(session_id, {
                "type": "error",
                "message": error_msg
            })
        
        # Start professional STT transcription with user's model preference
        await stt_service.start_transcription(
            on_partial=on_partial,
            on_final=on_final,
            on_error=on_error,
            model=session.user_model
        )
        
        # Keep connection alive and handle audio data
        while True:
            try:
                # Receive audio data (binary)
                data = await websocket.receive_bytes()
                
                # Process audio data
                await process_audio_data(session_id, data)
                
            except WebSocketDisconnect:
                logger.info(f"[STT WebSocket] Client disconnected from session: {session_id}")
                break
            except Exception as e:
                logger.error(f"[STT WebSocket] Error in session {session_id}: {e}")
                await stt_session_manager.send_message(session_id, {
                    "type": "error",
                    "message": f"WebSocket error: {str(e)}"
                })
                break
    
    finally:
        # Clean up session when WebSocket closes
        logger.info(f"[STT WebSocket] Cleaning up session: {session_id}")
        await stt_service.stop_transcription()
        await stt_session_manager.remove_session(session_id)


async def process_audio_data(session_id: str, audio_data: bytes):
    """
    Process incoming audio data and feed it to STT service.
    
    Args:
        session_id: Session ID
        audio_data: Raw audio data (PCM format from frontend)
    """
    try:
        # Frontend is now sending raw PCM audio directly
        # No conversion needed - feed directly to STT service
        await stt_service.feed_audio_data(audio_data, sample_rate=16000)
        
    except Exception as e:
        logger.error(f"Error processing audio data for session {session_id}: {e}")
        await stt_session_manager.send_message(session_id, {
            "type": "error",
            "message": f"Audio processing error: {str(e)}"
        })


async def convert_audio_to_pcm(audio_data: bytes) -> bytes:
    """
    Convert WebM/Opus audio data to PCM format.
    
    This is a simplified implementation. In production, you'd use
    a proper audio conversion library like ffmpeg-python or pydub.
    
    Args:
        audio_data: Raw audio data
        
    Returns:
        PCM audio data
    """
    try:
        # For testing purposes, we'll assume the data is already PCM
        # In a real implementation, you'd use ffmpeg or similar to convert
        # WebM/Opus to 16kHz mono PCM
        
        # This is a placeholder - implement proper audio conversion
        # For now, return the data as-is (assuming it's already PCM)
        return audio_data
        
    except Exception as e:
        logger.error(f"Error converting audio to PCM: {e}")
        return None


@router.post("/stt/create-session")
async def create_stt_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new STT session.
    
    Returns:
        Session ID and WebSocket URL for connection
    """
    try:
        # Get user's STT settings
        user_settings = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        if not user_settings:
            # Create default settings for new user
            user_settings = UserSettings(user_id=current_user.id)
            # Populate with defaults from config.yaml
            user_settings.populate_from_defaults()
            db.add(user_settings)
            db.commit()
            db.refresh(user_settings)
        
        # Check if STT is enabled for this user
        if not user_settings.stt_enabled:
            raise HTTPException(
                status_code=403,
                detail="STT is disabled for this user. Please enable it in Settings."
            )
        
        # Create STT session with user's model preference
        session_id = stt_session_manager.create_session(current_user.id)
        
        # Store user's model preference in session for later use
        session = stt_session_manager.get_session(session_id)
        if session:
            session.user_model = user_settings.stt_model
        
        logger.info(f"Created STT session: {session_id} for user {current_user.id} with model: {user_settings.stt_model}")
        
        return {
            "session_id": session_id,
            "websocket_url": f"/ws/stt/{session_id}",
            "model": user_settings.stt_model,
            "message": "Connect to WebSocket to start real-time transcription"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create STT session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create session"
        )


@router.get("/stt/device-info")
async def get_device_info():
    """
    Get STT device and model information.
    
    Returns:
        Device configuration details
    """
    try:
        from app.config import settings
        
        # Determine actual device being used
        device, compute_type = stt_service._get_device_config()
        
        return {
            "device": device,
            "compute_type": compute_type,
            "model": settings.stt_model,
            "language": settings.stt_language,
            "use_silero_vad": settings.stt_use_silero_vad,
            "vad_threshold": settings.stt_vad_threshold,
            "min_silence_duration_ms": settings.stt_min_silence_duration_ms,
            "max_speech_duration_s": settings.stt_max_speech_duration_s
        }
        
    except Exception as e:
        logger.error(f"Failed to get device info: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get device info"
        )
