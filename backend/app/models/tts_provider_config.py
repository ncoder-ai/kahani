"""
TTS Provider Configuration Model

Stores user-specific configuration for each TTS provider.
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class TTSProviderConfig(Base):
    """
    Per-provider TTS configuration for users
    
    Allows users to save different settings for each TTS provider
    (e.g., Chatterbox, Kokoro, OpenAI-compatible) and switch between them
    without losing their configurations.
    """
    __tablename__ = "tts_provider_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider_type = Column(String(50), nullable=False)  # chatterbox, kokoro, openai-compatible
    
    # Provider Configuration
    api_url = Column(String(500), nullable=False)
    api_key = Column(String(500), default="")  # Should be encrypted in production
    timeout = Column(Integer, default=30)
    
    # Voice Settings
    voice_id = Column(String(100), default="")
    speed = Column(Float, default=1.0)  # 0.5 - 2.0
    
    # Provider-Specific Settings (JSON for flexibility)
    extra_params = Column(JSON, default=None)
    # Examples:
    # Chatterbox: {"exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.7}
    # Kokoro: {"volume_multiplier": 1.0, "lang_code": "en-us"}
    # OpenAI: {"model": "tts-1", "response_format": "mp3"}
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User")
    
    # Ensure one config per user per provider
    __table_args__ = (
        UniqueConstraint('user_id', 'provider_type', name='uq_user_provider'),
    )
    
    def to_dict(self):
        """Convert config to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider_type": self.provider_type,
            "api_url": self.api_url,
            "has_api_key": bool(self.api_key),  # Don't expose the actual key
            "api_key": self.api_key if self.api_key else "",  # For internal use
            "timeout": self.timeout,
            "voice_id": self.voice_id,
            "speed": self.speed,
            "extra_params": self.extra_params or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
