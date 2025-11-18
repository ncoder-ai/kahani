# TTS Provider Architecture - Extensible Design

## 🎯 Goal
Create a flexible, extensible TTS system that supports multiple providers (OpenAI-compatible, ElevenLabs, Google TTS, Azure, etc.) without modifying core models or business logic.

## 🏗️ Architecture Pattern: Strategy + Factory

### Core Concept
- **Provider Interface**: Abstract base class defining TTS operations
- **Provider Implementations**: Concrete classes for each TTS service
- **Provider Factory**: Dynamic provider selection based on configuration
- **Provider Registry**: Plugin system for adding new providers

---

## 📁 File Structure

```
backend/app/services/tts/
├── __init__.py
├── base.py                    # Abstract base provider
├── factory.py                 # Provider factory
├── registry.py                # Provider registry
├── service.py                 # Main TTS service (provider-agnostic)
├── chunker.py                 # Text chunking utilities
├── providers/
│   ├── __init__.py
│   ├── openai_compatible.py  # OpenAI API format (default)
│   ├── elevenlabs.py          # ElevenLabs API
│   ├── google_tts.py          # Google Cloud TTS
│   ├── azure_tts.py           # Azure Cognitive Services
│   ├── kokoro.py              # Kokoro FastAPI
│   └── aws_polly.py           # AWS Polly
└── utils/
    ├── audio_utils.py         # Audio processing
    └── validation.py          # Input validation
```

---

## 🔧 Implementation

### 1. Base Provider Interface (`base.py`)

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class AudioFormat(Enum):
    MP3 = "mp3"
    AAC = "aac"
    OPUS = "opus"
    WAV = "wav"
    OGG = "ogg"

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
            raise ValueError(f"{self.provider_name}: API URL is required")
    
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
```

### 2. Provider Registry (`registry.py`)

```python
from typing import Dict, Type, Optional
from .base import TTSProviderBase, TTSProviderNotFoundError

class TTSProviderRegistry:
    """
    Registry for TTS providers.
    
    Allows dynamic registration and retrieval of provider classes.
    """
    
    _providers: Dict[str, Type[TTSProviderBase]] = {}
    
    @classmethod
    def register(cls, provider_name: str):
        """
        Decorator to register a TTS provider.
        
        Usage:
            @TTSProviderRegistry.register("openai")
            class OpenAIProvider(TTSProviderBase):
                ...
        """
        def decorator(provider_class: Type[TTSProviderBase]):
            if not issubclass(provider_class, TTSProviderBase):
                raise ValueError(
                    f"{provider_class.__name__} must inherit from TTSProviderBase"
                )
            cls._providers[provider_name.lower()] = provider_class
            return provider_class
        return decorator
    
    @classmethod
    def get_provider(cls, provider_name: str) -> Type[TTSProviderBase]:
        """
        Get a provider class by name.
        
        Args:
            provider_name: Name of the provider (case-insensitive)
            
        Returns:
            Provider class
            
        Raises:
            TTSProviderNotFoundError: If provider not found
        """
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise TTSProviderNotFoundError(
                f"Provider '{provider_name}' not found. "
                f"Available providers: {', '.join(cls.list_providers())}"
            )
        return provider_class
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """
        List all registered provider names.
        
        Returns:
            List of provider names
        """
        return list(cls._providers.keys())
    
    @classmethod
    def is_registered(cls, provider_name: str) -> bool:
        """
        Check if a provider is registered.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            True if registered, False otherwise
        """
        return provider_name.lower() in cls._providers
```

### 3. Provider Factory (`factory.py`)

```python
from typing import Optional
from sqlalchemy.orm import Session
from .base import TTSProviderBase, TTSProviderConfig, TTSProviderConfigError
from .registry import TTSProviderRegistry
from ..models.tts_settings import TTSSettings

class TTSProviderFactory:
    """
    Factory for creating TTS provider instances.
    
    Handles provider selection and instantiation based on user settings.
    """
    
    @staticmethod
    def create_provider(
        settings: TTSSettings,
        provider_override: Optional[str] = None
    ) -> TTSProviderBase:
        """
        Create a TTS provider instance from user settings.
        
        Args:
            settings: User's TTS settings
            provider_override: Optional provider name to use instead of settings
            
        Returns:
            Instantiated provider
            
        Raises:
            TTSProviderConfigError: If provider configuration is invalid
        """
        provider_name = provider_override or settings.tts_provider_type
        
        if not provider_name:
            raise TTSProviderConfigError("No TTS provider specified")
        
        # Get provider class from registry
        provider_class = TTSProviderRegistry.get_provider(provider_name)
        
        # Create provider configuration
        config = TTSProviderConfig(
            api_url=settings.tts_api_url,
            api_key=settings.tts_api_key or "",
            timeout=settings.tts_timeout or 30,
            retry_attempts=settings.tts_retry_attempts or 3,
            custom_headers=settings.tts_custom_headers,
            extra_params=settings.tts_extra_params
        )
        
        # Instantiate and return provider
        try:
            return provider_class(config)
        except Exception as e:
            raise TTSProviderConfigError(
                f"Failed to create {provider_name} provider: {str(e)}"
            )
    
    @staticmethod
    def get_available_providers() -> List[str]:
        """
        Get list of all available TTS providers.
        
        Returns:
            List of provider names
        """
        return TTSProviderRegistry.list_providers()
```

### 4. OpenAI-Compatible Provider (`providers/openai_compatible.py`)

```python
import httpx
from typing import List, AsyncIterator, Optional
from ..base import (
    TTSProviderBase, TTSRequest, TTSResponse, Voice,
    AudioFormat, TTSProviderAPIError
)
from ..registry import TTSProviderRegistry

@TTSProviderRegistry.register("openai-compatible")
class OpenAICompatibleProvider(TTSProviderBase):
    """
    OpenAI-compatible TTS provider.
    
    Works with OpenAI API, Kokoro FastAPI, ChatterboxTTS, and other
    OpenAI-compatible endpoints.
    """
    
    @property
    def provider_name(self) -> str:
        return "openai-compatible"
    
    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.MP3, AudioFormat.OPUS, AudioFormat.AAC]
    
    @property
    def max_text_length(self) -> int:
        return self.config.extra_params.get("max_text_length", 280)
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    @property
    def supports_pitch_control(self) -> bool:
        return False
    
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Synthesize speech using OpenAI-compatible API"""
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.config.api_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    **(self.config.custom_headers or {})
                },
                json={
                    "input": request.text,
                    "voice": request.voice_id,
                    "speed": request.speed,
                    "response_format": request.format.value
                }
            )
            
            if response.status_code != 200:
                raise TTSProviderAPIError(
                    f"API returned status {response.status_code}: {response.text}"
                )
            
            audio_data = response.content
            
            return TTSResponse(
                audio_data=audio_data,
                format=request.format,
                duration=self._estimate_duration(len(audio_data), request.format),
                sample_rate=request.sample_rate,
                file_size=len(audio_data),
                metadata={"provider": self.provider_name}
            )
    
    async def synthesize_stream(
        self,
        request: TTSRequest
    ) -> AsyncIterator[bytes]:
        """Stream synthesized speech"""
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.config.api_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    **(self.config.custom_headers or {})
                },
                json={
                    "input": request.text,
                    "voice": request.voice_id,
                    "speed": request.speed,
                    "response_format": request.format.value,
                    "stream": True
                }
            ) as response:
                if response.status_code != 200:
                    raise TTSProviderAPIError(
                        f"API returned status {response.status_code}"
                    )
                
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk
    
    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        """Get available voices"""
        # For OpenAI-compatible APIs, voices might be hardcoded or
        # fetched from a /voices endpoint if available
        
        # Try to fetch from API first
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(
                    f"{self.config.api_url}/voices",
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
                if response.status_code == 200:
                    voices_data = response.json()
                    return [
                        Voice(
                            id=v.get("id", v.get("voice_id")),
                            name=v.get("name", v.get("id")),
                            language=v.get("language", "en"),
                            gender=v.get("gender"),
                            description=v.get("description")
                        )
                        for v in voices_data.get("voices", [])
                    ]
        except Exception:
            pass
        
        # Fallback to default voices
        default_voices = self.config.extra_params.get("voices", ["Sara"])
        return [
            Voice(
                id=voice_id,
                name=voice_id,
                language="en",
                description=f"Default voice: {voice_id}"
            )
            for voice_id in default_voices
        ]
    
    async def validate_voice(self, voice_id: str) -> bool:
        """Validate voice ID"""
        voices = await self.get_voices()
        return any(v.id == voice_id for v in voices)
    
    def _estimate_duration(self, file_size: int, format: AudioFormat) -> float:
        """Estimate audio duration from file size"""
        # Rough estimation based on bitrate
        bitrates = {
            AudioFormat.MP3: 128000,  # 128 kbps
            AudioFormat.AAC: 96000,   # 96 kbps
            AudioFormat.OPUS: 64000   # 64 kbps
        }
        bitrate = bitrates.get(format, 128000)
        return (file_size * 8) / bitrate
```

### 5. ElevenLabs Provider Example (`providers/elevenlabs.py`)

```python
import httpx
from typing import List, AsyncIterator, Optional
from ..base import (
    TTSProviderBase, TTSRequest, TTSResponse, Voice,
    AudioFormat, TTSProviderAPIError
)
from ..registry import TTSProviderRegistry

@TTSProviderRegistry.register("elevenlabs")
class ElevenLabsProvider(TTSProviderBase):
    """ElevenLabs TTS provider"""
    
    @property
    def provider_name(self) -> str:
        return "elevenlabs"
    
    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.MP3, AudioFormat.MP3]  # ElevenLabs supports MP3
    
    @property
    def max_text_length(self) -> int:
        return 5000  # ElevenLabs supports longer text
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    @property
    def supports_pitch_control(self) -> bool:
        return False  # ElevenLabs uses voice models, not pitch control
    
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Synthesize using ElevenLabs API"""
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                f"{self.config.api_url}/v1/text-to-speech/{request.voice_id}",
                headers={
                    "xi-api-key": self.config.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "text": request.text,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                }
            )
            
            if response.status_code != 200:
                raise TTSProviderAPIError(
                    f"ElevenLabs API error: {response.text}"
                )
            
            audio_data = response.content
            
            return TTSResponse(
                audio_data=audio_data,
                format=AudioFormat.MP3,
                duration=self._estimate_duration(len(audio_data)),
                sample_rate=44100,
                file_size=len(audio_data),
                metadata={"provider": "elevenlabs"}
            )
    
    async def synthesize_stream(
        self,
        request: TTSRequest
    ) -> AsyncIterator[bytes]:
        """Stream from ElevenLabs"""
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.config.api_url}/v1/text-to-speech/{request.voice_id}/stream",
                headers={"xi-api-key": self.config.api_key},
                json={"text": request.text}
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk
    
    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        """Get ElevenLabs voices"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.config.api_url}/v1/voices",
                headers={"xi-api-key": self.config.api_key}
            )
            voices_data = response.json()
            
            return [
                Voice(
                    id=v["voice_id"],
                    name=v["name"],
                    language="en",  # ElevenLabs doesn't provide language in API
                    description=v.get("description"),
                    preview_url=v.get("preview_url")
                )
                for v in voices_data.get("voices", [])
            ]
    
    async def validate_voice(self, voice_id: str) -> bool:
        voices = await self.get_voices()
        return any(v.id == voice_id for v in voices)
    
    def _estimate_duration(self, file_size: int) -> float:
        return (file_size * 8) / 128000  # Assume 128kbps
```

### 6. Updated TTS Settings Model

```python
# backend/app/models/tts_settings.py

from sqlalchemy import Column, Integer, String, Float, Boolean, JSON
from ..database import Base

class TTSSettings(Base):
    __tablename__ = "tts_settings"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # Provider selection
    tts_enabled = Column(Boolean, default=False)
    tts_provider_type = Column(String(50), default="openai-compatible")
    
    # Provider configuration
    tts_api_url = Column(String(500), default="")
    tts_api_key = Column(String(500), default="")
    tts_timeout = Column(Integer, default=30)
    tts_retry_attempts = Column(Integer, default=3)
    tts_custom_headers = Column(JSON, default=None)  # For custom headers
    tts_extra_params = Column(JSON, default=None)    # Provider-specific params
    
    # Voice settings
    default_voice = Column(String(100), default="Sara")
    speech_speed = Column(Float, default=1.0)
    audio_format = Column(String(10), default="mp3")
    
    # Behavior
    auto_narrate_new_scenes = Column(Boolean, default=False)
    chunk_size = Column(Integer, default=280)
    stream_audio = Column(Boolean, default=True)
    
    # ... rest of fields
```

### 7. Updated TTS Service (Provider-Agnostic)

```python
# backend/app/services/tts/service.py

from sqlalchemy.orm import Session
from .factory import TTSProviderFactory
from .base import TTSRequest, AudioFormat
from ...models.tts_settings import TTSSettings

class TTSService:
    """
    Main TTS service - provider agnostic.
    
    Handles business logic and delegates to appropriate provider.
    """
    
    async def generate_scene_audio(
        self,
        scene_id: int,
        user_id: int,
        db: Session
    ):
        """Generate audio for a scene using user's configured provider"""
        
        # Get user's TTS settings
        settings = db.query(TTSSettings).filter_by(user_id=user_id).first()
        if not settings or not settings.tts_enabled:
            raise ValueError("TTS not enabled for user")
        
        # Create provider instance
        provider = TTSProviderFactory.create_provider(settings)
        
        # Get scene content
        scene = db.query(Scene).filter_by(id=scene_id).first()
        
        # Chunk text if needed
        chunks = self._chunk_text(scene.content, provider.max_text_length)
        
        # Generate audio for each chunk
        audio_parts = []
        for chunk in chunks:
            request = TTSRequest(
                text=chunk,
                voice_id=settings.default_voice,
                speed=settings.speech_speed,
                format=AudioFormat(settings.audio_format)
            )
            
            response = await provider.synthesize(request)
            audio_parts.append(response.audio_data)
        
        # Concatenate and return
        return self._concatenate_audio(audio_parts, settings.audio_format)
    
    def _chunk_text(self, text: str, max_size: int) -> List[str]:
        """Smart text chunking"""
        # Implementation from chunker.py
        pass
```

---

## 🎯 Usage Examples

### Adding a New Provider

```python
# Create new file: providers/azure_tts.py

from ..base import TTSProviderBase
from ..registry import TTSProviderRegistry

@TTSProviderRegistry.register("azure")
class AzureTTSProvider(TTSProviderBase):
    
    @property
    def provider_name(self) -> str:
        return "azure"
    
    # Implement abstract methods...
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        # Azure-specific implementation
        pass
```

### User Configuration

```json
{
  "tts_provider_type": "elevenlabs",
  "tts_api_url": "https://api.elevenlabs.io",
  "tts_api_key": "your-key",
  "tts_extra_params": {
    "model_id": "eleven_monolingual_v1",
    "voice_settings": {
      "stability": 0.75,
      "similarity_boost": 0.85
    }
  }
}
```

---

## 📋 Benefits

1. **Zero Core Changes**: Add new providers without touching existing code
2. **Type Safety**: Abstract base class ensures consistency
3. **Easy Testing**: Mock providers for unit tests
4. **Plugin System**: Third-party providers can be added
5. **Configuration Flexibility**: Provider-specific settings via JSON
6. **Automatic Discovery**: Registry pattern makes providers discoverable
7. **Fail-Safe**: If one provider fails, can switch to another

---

## 🚀 Migration Path

Existing code doesn't break - just set `tts_provider_type = "openai-compatible"`!

