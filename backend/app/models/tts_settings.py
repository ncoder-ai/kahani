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
    progressive_narration = Column(Boolean, default=False)  # Split scene into chunks for progressive playback
    chunk_size = Column(Integer, default=280)  # Chunk size for progressive narration (100-500)
    stream_audio = Column(Boolean, default=True)  # Future: Use provider streaming capabilities (SSE)
    auto_play_last_scene = Column(Boolean, default=False)  # Auto-play TTS after scene generation completes

    # When True, scene playback runs an LLM extraction first to split the
    # scene into per-speaker segments {speaker, text, emotion}. The TTS
    # pipeline then dispatches each segment with the matching character's
    # voice (from Story.tts_character_voices) and that segment's emotion
    # as a per-utterance instructions hint. Adds 5-15s on first play per
    # scene (cached on SceneVariant.tts_segments). Off by default — opt-in
    # for users who want immersive multi-voice playback.
    use_segment_extraction = Column(Boolean, default=False, nullable=False)

    # Which LLM the TTS scene-segment extractor calls. 'extraction' uses
    # the user's configured extraction LLM (typically local, slower, no
    # per-call cost). 'main' forces the user's main LLM (typically a
    # cloud model — much faster, costs credits). Defaults to extraction
    # so opt-in users don't suddenly burn cloud credits on background
    # scene processing.
    tts_extraction_llm_choice = Column(String(20), default="extraction", nullable=False)

    # When True, scene playback uses native multi-speaker TTS (one inference
    # call per scene, seamless turn-taking) for providers that support
    # it (VibeVoice, F5-TTS). The dispatcher builds an ordered Speaker N:
    # script + per-slot voice mapping from extracted segments and the
    # Story.tts_character_voices map, and streams PCM frames as the model
    # generates. Falls back transparently to per-utterance chunking when
    # provider doesn't support multi-speaker, scene has too many speakers,
    # or any voice slot is unmapped.
    use_multi_speaker = Column(Boolean, default=False, nullable=False)

    # When True AND the provider supports PCM frame streaming, the scene
    # is sent as a SINGLE single-voice TTS call and PCM frames stream as
    # the model generates them (sub-second TTFB, no chunk seams). Distinct
    # from `use_multi_speaker` (which renders multiple voices in one
    # call) — `use_streaming` is the single-voice equivalent. Falls back
    # transparently to chunked playback when streaming isn't supported
    # or fails. Default False to preserve current chunked behavior.
    use_streaming = Column(Boolean, default=False, nullable=False)

    # When True AND streaming isn't being used (either disabled OR the
    # provider doesn't support it), send the entire scene to the TTS in
    # ONE block call (single voice, single response) instead of chunking.
    # No streaming benefit — caller waits for the full audio file before
    # playback starts — but avoids the cut/resume artifacts at chunk
    # boundaries. Useful for providers without streaming when scene
    # cohesion matters more than time-to-first-audio.
    use_whole_scene = Column(Boolean, default=False, nullable=False)

    # Advanced Settings
    pause_between_paragraphs = Column(Integer, default=500)  # milliseconds
    volume = Column(Float, default=1.0)  # 0.0 - 1.0

    # Pre-buffer (seconds) — frontend audio player accumulates this many
    # seconds of generated audio before starting playback, so subsequent
    # frames pile up ahead of the playhead. Absorbs upstream generation
    # jitter when streaming RTF is close to 1.0. Range 0.0 - 10.0; the
    # UI surfaces 0.5 - 10. Default 1.0 (mild buffer, ~negligible delay
    # before audio starts, survives small spikes).
    playback_buffer_seconds = Column(Float, default=1.0, nullable=False)
    
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
                "progressive_narration": self.progressive_narration,
                "chunk_size": self.chunk_size,
                "stream_audio": self.stream_audio,
                "auto_play_last_scene": self.auto_play_last_scene,
                "pause_between_paragraphs": self.pause_between_paragraphs,
                "volume": self.volume,
                "playback_buffer_seconds": self.playback_buffer_seconds,
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
    scene = relationship("Scene", back_populates="scene_audio")
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
