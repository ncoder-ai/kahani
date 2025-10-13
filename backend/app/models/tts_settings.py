"""
TTS Settings Model

User-specific TTS configuration with support for multiple providers.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class TTSSettings(Base):
    """
    User TTS configuration - Provider Agnostic Design
    
    Supports multiple TTS providers through flexible configuration.
    """
    __tablename__ = "tts_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Provider Selection (Extensible!)
    tts_enabled = Column(Boolean, default=False)
    tts_provider_type = Column(String(50), default="openai-compatible")
    # Supported: openai-compatible, elevenlabs, google, azure, aws-polly, etc.
    
    # Provider Configuration
    tts_api_url = Column(String(500), default="")
    tts_api_key = Column(String(500), default="")  # Should be encrypted in production
    tts_timeout = Column(Integer, default=30)
    tts_retry_attempts = Column(Integer, default=3)
    
    # Provider-Specific Settings (JSON for flexibility)
    tts_custom_headers = Column(JSON, default=None)  # Custom HTTP headers
    tts_extra_params = Column(JSON, default=None)    # Provider-specific params
    # Example: {"model_id": "eleven_monolingual_v1", "stability": 0.75}
    
    # Voice Settings
    default_voice = Column(String(100), default="Sara")
    speech_speed = Column(Float, default=1.0)  # 0.5 - 2.0
    audio_format = Column(String(10), default="mp3")  # mp3, aac, opus
    
    # Behavior Settings
    auto_narrate_new_scenes = Column(Boolean, default=False)
    chunk_size = Column(Integer, default=280)  # Max characters per chunk
    stream_audio = Column(Boolean, default=True)
    
    # Advanced Settings
    pause_between_paragraphs = Column(Integer, default=500)  # milliseconds
    volume = Column(Float, default=1.0)  # 0.0 - 1.0
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="tts_settings")
    
    def to_dict(self):
        """Convert settings to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tts_enabled": self.tts_enabled,
            "provider": {
                "type": self.tts_provider_type,
                "api_url": self.tts_api_url,
                "has_api_key": bool(self.tts_api_key),  # Don't expose the actual key
                "timeout": self.tts_timeout,
                "retry_attempts": self.tts_retry_attempts,
                "custom_headers": self.tts_custom_headers,
                "extra_params": self.tts_extra_params
            },
            "voice": {
                "default_voice": self.default_voice,
                "speed": self.speech_speed,
                "format": self.audio_format
            },
            "behavior": {
                "auto_narrate_new_scenes": self.auto_narrate_new_scenes,
                "chunk_size": self.chunk_size,
                "stream_audio": self.stream_audio,
                "pause_between_paragraphs": self.pause_between_paragraphs,
                "volume": self.volume
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class SceneAudio(Base):
    """
    Cache generated TTS audio for scenes
    
    Stores audio files to avoid regenerating the same content.
    """
    __tablename__ = "scene_audio"
    
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Audio file info
    audio_url = Column(String(500), nullable=False)  # Relative path to audio file
    audio_format = Column(String(10), nullable=False)  # mp3, aac, etc.
    file_size = Column(Integer, nullable=False)  # bytes
    duration = Column(Float, nullable=False)  # seconds
    
    # Generation metadata
    voice_used = Column(String(100))
    speed_used = Column(Float)
    provider_used = Column(String(50))
    chunk_count = Column(Integer, default=1)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    scene = relationship("Scene")
    user = relationship("User")
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "scene_id": self.scene_id,
            "audio_url": self.audio_url,
            "format": self.audio_format,
            "file_size": self.file_size,
            "duration": self.duration,
            "voice": self.voice_used,
            "speed": self.speed_used,
            "provider": self.provider_used,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
