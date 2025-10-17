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
    auto_play: bool = False  # Flag to indicate if this is an auto-play session
    message_buffer: list = []  # Buffer messages when WebSocket not connected yet
    
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
    
    def create_session(self, scene_id: int, user_id: int, auto_play: bool = False) -> str:
        """
        Create a new TTS generation session.
        
        Args:
            scene_id: The scene to generate audio for
            user_id: The user requesting generation
            auto_play: Whether this is an auto-play session
            
        Returns:
            session_id: Unique identifier for this session
        """
        session_id = uuid.uuid4().hex
        
        session = TTSSession(
            session_id=session_id,
            scene_id=scene_id,
            user_id=user_id,
            created_at=datetime.now(),
            auto_play=auto_play
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
        If WebSocket not connected yet (auto-play), buffer the message.
        
        Args:
            session_id: The session to send to
            message: Dictionary to send as JSON
            
        Returns:
            True if sent successfully or buffered, False otherwise
        """
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        # If WebSocket connected, send immediately
        if session.websocket:
            try:
                await session.websocket.send_json(message)
                return True
            except Exception as e:
                print(f"Error sending message to session {session_id}: {e}")
                return False
        
        # If no WebSocket yet (auto-play), buffer the message
        if session.auto_play:
            session.message_buffer.append(message)
            print(f"[AUTO-PLAY] Buffered message for session {session_id} (buffer size: {len(session.message_buffer)})")
            return True
        
        return False
    
    async def flush_buffered_messages(self, session_id: str) -> bool:
        """
        Send all buffered messages when WebSocket connects.
        Called when WebSocket attaches to an auto-play session.
        
        Sends messages with tiny delays to avoid overwhelming the connection.
        
        Args:
            session_id: The session to flush
            
        Returns:
            True if all messages sent successfully
        """
        session = self.sessions.get(session_id)
        if not session or not session.websocket:
            return False
        
        if not session.message_buffer:
            print(f"[AUTO-PLAY] No buffered messages for session {session_id}")
            return True
        
        print(f"[AUTO-PLAY] Flushing {len(session.message_buffer)} buffered messages for session {session_id}")
        
        try:
            for i, message in enumerate(session.message_buffer):
                await session.websocket.send_json(message)
                print(f"[AUTO-PLAY] Flushed message {i+1}/{len(session.message_buffer)}: {message.get('type', 'unknown')}")
                
                # Add tiny delay after first chunk to ensure it's processed before next one
                # This helps frontend start playback faster
                if i == 0 and message.get('type') == 'chunk_ready':
                    await asyncio.sleep(0.05)  # 50ms delay after first chunk
            
            # Clear buffer after sending
            session.message_buffer = []
            print(f"[AUTO-PLAY] Successfully flushed all messages for session {session_id}")
            return True
        
        except Exception as e:
            print(f"Error flushing buffered messages for session {session_id}: {e}")
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
