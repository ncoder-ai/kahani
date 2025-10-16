"""
TTS Session Manager for WebSocket-based audio streaming.

Manages TTS generation sessions, tracks WebSocket connections,
and coordinates audio chunk streaming.
"""

import uuid
import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta
from fastapi import WebSocket
from pydantic import BaseModel


class TTSSession(BaseModel):
    """Represents a TTS generation session."""
    
    session_id: str
    scene_id: int
    user_id: int
    created_at: datetime
    websocket: Optional[WebSocket] = None
    is_generating: bool = False
    chunks_sent: int = 0
    total_chunks: Optional[int] = None
    error: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True


class TTSSessionManager:
    """
    Manages TTS generation sessions and WebSocket connections.
    
    Responsibilities:
    - Create and track sessions
    - Associate WebSocket connections with sessions
    - Clean up expired sessions
    - Coordinate chunk streaming
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        self.sessions: Dict[str, TTSSession] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def create_session(self, scene_id: int, user_id: int) -> str:
        """
        Create a new TTS generation session.
        
        Args:
            scene_id: The scene to generate audio for
            user_id: The user requesting generation
            
        Returns:
            session_id: Unique identifier for this session
        """
        session_id = uuid.uuid4().hex
        
        session = TTSSession(
            session_id=session_id,
            scene_id=scene_id,
            user_id=user_id,
            created_at=datetime.now()
        )
        
        self.sessions[session_id] = session
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[TTSSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)
    
    def attach_websocket(self, session_id: str, websocket: WebSocket) -> bool:
        """
        Attach a WebSocket connection to a session.
        
        Args:
            session_id: The session to attach to
            websocket: The WebSocket connection
            
        Returns:
            True if successful, False if session not found
        """
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.websocket = websocket
        return True
    
    def set_generating(self, session_id: str, is_generating: bool):
        """Mark a session as actively generating."""
        session = self.sessions.get(session_id)
        if session:
            session.is_generating = is_generating
    
    def set_total_chunks(self, session_id: str, total_chunks: int):
        """Set the total number of chunks for a session."""
        session = self.sessions.get(session_id)
        if session:
            session.total_chunks = total_chunks
    
    def increment_chunks_sent(self, session_id: str):
        """Increment the chunks sent counter."""
        session = self.sessions.get(session_id)
        if session:
            session.chunks_sent += 1
    
    def set_error(self, session_id: str, error: str):
        """Set an error message for a session."""
        session = self.sessions.get(session_id)
        if session:
            session.error = error
            session.is_generating = False
    
    async def send_message(self, session_id: str, message: dict) -> bool:
        """
        Send a JSON message via the session's WebSocket.
        
        Args:
            session_id: The session to send to
            message: Dictionary to send as JSON
            
        Returns:
            True if sent successfully, False otherwise
        """
        session = self.sessions.get(session_id)
        if not session or not session.websocket:
            return False
        
        try:
            await session.websocket.send_json(message)
            return True
        except Exception as e:
            print(f"Error sending message to session {session_id}: {e}")
            return False
    
    def remove_session(self, session_id: str):
        """Remove a session (called on completion or error)."""
        self.sessions.pop(session_id, None)
    
    async def cleanup_expired_sessions(self):
        """Remove sessions that have expired."""
        now = datetime.now()
        expired = [
            sid for sid, session in self.sessions.items()
            if now - session.created_at > self.session_timeout
        ]
        
        for session_id in expired:
            print(f"Cleaning up expired session: {session_id}")
            self.remove_session(session_id)
    
    async def start_cleanup_task(self):
        """Start background task to clean up expired sessions."""
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            await self.cleanup_expired_sessions()
    
    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self.sessions)
    
    def get_active_sessions(self) -> list[TTSSession]:
        """Get all sessions that are currently generating."""
        return [
            session for session in self.sessions.values()
            if session.is_generating
        ]


# Global session manager instance
tts_session_manager = TTSSessionManager()
