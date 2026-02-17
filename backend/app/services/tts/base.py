"""
TTS Provider Base Classes and Interfaces

This module defines the abstract base classes and data structures for TTS providers.
All TTS providers must inherit from TTSProviderBase and implement its abstract methods.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class AudioFormat(Enum):
    """Supported audio formats"""
    MP3 = "mp3"
    AAC = "aac"
    OPUS = "opus"
    WAV = "wav"
    OGG = "ogg"
    FLAC = "flac"
    PCM = "pcm"


@dataclass
class TTSProviderConfig:
    """Configuration for TTS provider"""
    api_url: str
    api_key: str
    timeout: int = 30
    retry_attempts: int = 3
    custom_headers: Optional[Dict[str, str]] = None
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class Voice:
    """Voice information"""
    id: str
    name: str
    language: str
    gender: Optional[str] = None
    preview_url: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


@dataclass
class TTSRequest:
    """Standard TTS request"""
    text: str
    voice_id: str
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    format: AudioFormat = AudioFormat.MP3
    sample_rate: int = 24000
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class TTSResponse:
    """Standard TTS response"""
    audio_data: bytes
    format: AudioFormat
    duration: float  # seconds
    sample_rate: int
    file_size: int  # bytes
    metadata: Optional[Dict[str, Any]] = None


class TTSProviderBase(ABC):
    """
    Abstract base class for all TTS providers.
    
    Each provider must implement these methods to be compatible
    with the TTS system.
    """
    
    def __init__(self, config: TTSProviderConfig):
        self.config = config
        self._validate_config()
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'openai', 'elevenlabs')"""
        pass
    
    @property
    @abstractmethod
    def supported_formats(self) -> List[AudioFormat]:
        """Return list of supported audio formats"""
        pass
    
    @property
    @abstractmethod
    def max_text_length(self) -> int:
        """Return maximum text length per request"""
        pass
    
    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Return whether provider supports streaming"""
        pass
    
    @property
    @abstractmethod
    def supports_pitch_control(self) -> bool:
        """Return whether provider supports pitch control"""
        pass
    
    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize speech from text.
        
        Args:
            request: TTSRequest with text and voice settings
            
        Returns:
            TTSResponse with audio data and metadata
            
        Raises:
            TTSProviderError: If synthesis fails
        """
        pass
    
    @abstractmethod
    async def synthesize_stream(
        self,
        request: TTSRequest
    ) -> AsyncIterator[bytes]:
        """
        Stream synthesized speech.
        
        Args:
            request: TTSRequest with text and voice settings
            
        Yields:
            Audio data chunks
            
        Raises:
            TTSProviderError: If streaming not supported or fails
        """
        pass
    
    @abstractmethod
    async def get_voices(
        self,
        language: Optional[str] = None
    ) -> List[Voice]:
        """
        Get available voices.
        
        Args:
            language: Optional language filter (e.g., 'en', 'es')
            
        Returns:
            List of available Voice objects
        """
        pass
    
    @abstractmethod
    async def validate_voice(self, voice_id: str) -> bool:
        """
        Validate if a voice ID exists.
        
        Args:
            voice_id: Voice identifier to validate
            
        Returns:
            True if voice exists, False otherwise
        """
        pass
    
    def _validate_config(self):
        """Validate provider configuration"""
        if not self.config.api_url:
            raise TTSProviderConfigError(
                f"{self.provider_name}: API URL is required"
            )
    
    async def health_check(self) -> bool:
        """
        Check if provider is accessible and healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            voices = await self.get_voices()
            return len(voices) > 0
        except Exception:
            return False


class TTSProviderError(Exception):
    """Base exception for TTS provider errors"""
    pass


class TTSProviderNotFoundError(TTSProviderError):
    """Provider not found in registry"""
    pass


class TTSProviderConfigError(TTSProviderError):
    """Provider configuration error"""
    pass


class TTSProviderAPIError(TTSProviderError):
    """Provider API error"""
    pass
