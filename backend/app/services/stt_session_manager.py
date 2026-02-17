"""
STT Session Manager for WebSocket-based real-time transcription.

Manages STT transcription sessions, tracks WebSocket connections,
and coordinates real-time audio streaming and transcription.
"""

import uuid
import asyncio
import logging
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class STTSession(BaseModel):
    """Represents an STT transcription session."""
    
    session_id: str
    user_id: int
    created_at: datetime
    websocket: Optional[WebSocket] = None
    is_transcribing: bool = False
    is_recording: bool = False
    transcript: str = ""
    partial_transcript: str = ""
    error: Optional[str] = None
    message_buffer: list = []  # Buffer messages when WebSocket not connected yet
    user_model: Optional[str] = None  # User's preferred STT model
    
    class Config:
        arbitrary_types_allowed = True


class STTSessionManager:
    """
    Manages STT transcription sessions and WebSocket connections.
    
    Responsibilities:
    - Create and track sessions
    - Associate WebSocket connections with sessions
    - Clean up expired sessions
    - Coordinate real-time transcription streaming
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        self.sessions: Dict[str, STTSession] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_started = False
    
    def _start_cleanup_task(self):
        """Start background task to clean up expired sessions."""
        if not self._cleanup_started:
            try:
                loop = asyncio.get_running_loop()
                if self._cleanup_task is None or self._cleanup_task.done():
                    self._cleanup_task = loop.create_task(self._cleanup_expired_sessions())
                    self._cleanup_started = True
            except RuntimeError:
                # No event loop running, will start later
                pass
    
    async def _cleanup_expired_sessions(self):
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                now = datetime.now()
                expired_sessions = []
                
                for session_id, session in self.sessions.items():
                    if now - session.created_at > self.session_timeout:
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    await self.remove_session(session_id)
                    logger.info(f"Cleaned up expired STT session: {session_id}")
                    
            except Exception as e:
                logger.error(f"Error in STT session cleanup: {e}")
    
    def create_session(self, user_id: int) -> str:
        """
        Create a new STT session.
        
        Args:
            user_id: ID of the user creating the session
            
        Returns:
            Session ID
        """
        # Start cleanup task if not already started
        self._start_cleanup_task()
        
        session_id = str(uuid.uuid4())
        
        session = STTSession(
            session_id=session_id,
            user_id=user_id,
            created_at=datetime.now()
        )
        
        self.sessions[session_id] = session
        logger.info(f"Created STT session: {session_id} for user {user_id}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[STTSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def attach_websocket(self, session_id: str, websocket: WebSocket):
        """
        Attach WebSocket to session.
        
        Args:
            session_id: Session ID
            websocket: WebSocket connection
        """
        session = self.sessions.get(session_id)
        if session:
            session.websocket = websocket
            logger.info(f"Attached WebSocket to STT session: {session_id}")
            
            # Flush any buffered messages
            if session.message_buffer:
                asyncio.create_task(self.flush_buffered_messages(session_id))
    
    async def send_message(self, session_id: str, message: dict):
        """
        Send message to session's WebSocket.
        
        Args:
            session_id: Session ID
            message: Message to send
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"STT session not found: {session_id}")
            return
        
        if session.websocket:
            try:
                await session.websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to STT session {session_id}: {e}")
        else:
            # Buffer message if WebSocket not connected
            session.message_buffer.append(message)
            logger.debug(f"Buffered message for STT session {session_id}")
    
    async def flush_buffered_messages(self, session_id: str):
        """Flush buffered messages to WebSocket."""
        session = self.sessions.get(session_id)
        if not session or not session.websocket:
            return
        
        try:
            for message in session.message_buffer:
                await session.websocket.send_json(message)
            
            session.message_buffer.clear()
            logger.info(f"Flushed {len(session.message_buffer)} buffered messages for STT session {session_id}")
        except Exception as e:
            logger.error(f"Error flushing buffered messages for STT session {session_id}: {e}")
    
    def update_transcript(self, session_id: str, transcript: str, is_partial: bool = False):
        """
        Update session transcript.
        
        Args:
            session_id: Session ID
            transcript: New transcript text
            is_partial: Whether this is a partial (live) transcript
        """
        session = self.sessions.get(session_id)
        if session:
            if is_partial:
                session.partial_transcript = transcript
            else:
                session.transcript = transcript
                session.partial_transcript = ""  # Clear partial when final is received
    
    def set_transcribing(self, session_id: str, is_transcribing: bool):
        """Set transcription status."""
        session = self.sessions.get(session_id)
        if session:
            session.is_transcribing = is_transcribing
    
    def set_recording(self, session_id: str, is_recording: bool):
        """Set recording status."""
        session = self.sessions.get(session_id)
        if session:
            session.is_recording = is_recording
    
    def set_error(self, session_id: str, error: str):
        """Set session error."""
        session = self.sessions.get(session_id)
        if session:
            session.error = error
    
    async def remove_session(self, session_id: str):
        """
        Remove session and close WebSocket.
        
        Args:
            session_id: Session ID to remove
        """
        session = self.sessions.get(session_id)
        if session:
            if session.websocket:
                try:
                    await session.websocket.close()
                except:
                    pass
            
            del self.sessions[session_id]
            logger.info(f"Removed STT session: {session_id}")
    
    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self.sessions)
    
    def get_sessions_for_user(self, user_id: int) -> list[STTSession]:
        """Get all sessions for a user."""
        return [session for session in self.sessions.values() if session.user_id == user_id]


# Global STT session manager instance
stt_session_manager = STTSessionManager()
