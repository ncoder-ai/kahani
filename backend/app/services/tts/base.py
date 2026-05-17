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
class PcmFormat:
    """Raw PCM frame format declared by providers that support true streaming.

    When a provider exposes `streaming_pcm_format`, its `synthesize_stream`
    yields raw PCM bytes that can be played frame-by-frame without any
    decoder — enabling sub-second time-to-first-audio. PCM is the lowest
    common denominator across browsers (especially iOS Safari, where
    streaming Opus/MP3 decode is unreliable).
    """
    sample_rate: int            # e.g. 24000 (Hz)
    channels: int = 1           # 1 = mono
    bits_per_sample: int = 16   # 8 / 16 / 24 / 32
    encoding: str = "pcm_s16le" # signed 16-bit little-endian


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
class MultiSpeakerSegment:
    """One ordered segment in a multi-speaker scene script.

    `speaker` is the canonical cast name (or "narrator"). `voice_id` is
    the provider-specific voice preset/clone name to use for this slot.
    `text` is the raw segment text — the provider's script formatter is
    responsible for any wrapping (quote-stripping, slot-prefixing, etc.).
    `kind` is one of "narrator" / "dialogue" / "thought" — providers may
    use it to apply per-kind transformations (e.g. prefixing thoughts
    with parenthetical cues for VibeVoice).
    """
    speaker: str
    voice_id: str
    text: str
    kind: str = "narrator"


@dataclass
class MultiSpeakerRequest:
    """Multi-speaker scene synthesis request.

    Used by providers whose `supports_multi_speaker_script` is True —
    the scene's per-speaker segments are sent in a single API call as
    one cohesive script (with seamless turn-taking between speakers).
    `voice_slots` is the ordered slot→voice_id mapping the provider
    should expose to the underlying model (positional for VibeVoice's
    `--speaker_names` arg, named-key for F5-TTS's TOML voice library).
    """
    segments: List["MultiSpeakerSegment"]
    voice_slots: List[str]      # ordered list of voice_ids, slot 0..N-1
    speed: float = 1.0
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
    def streaming_pcm_format(self) -> Optional["PcmFormat"]:
        """Provider's PCM format for true frame-level streaming.

        Return a PcmFormat to opt in to the new `stream_start`/`frame`/
        `stream_end` WebSocket protocol — `synthesize_stream` will then
        be expected to yield raw PCM bytes (no container, no encoding).

        Default `None` means the provider only supports complete-chunk
        streaming, so `tts_service` falls back to the existing path that
        calls `synthesize` and emits `chunk_ready` messages.
        """
        return None
    
    @property
    @abstractmethod
    def supports_pitch_control(self) -> bool:
        """Return whether provider supports pitch control"""
        pass

    # -------- multi-speaker capability flags --------
    # These default to False so existing providers (Qwen3, IndexTTS,
    # Chatterbox, Kokoro, Orpheus, OpenAI-compatible) keep their current
    # per-utterance chunked behavior without any changes. Providers that
    # natively understand multi-speaker scripts (VibeVoice, F5-TTS) override.

    @property
    def supports_multi_speaker_script(self) -> bool:
        """Provider can render a multi-speaker script in a single call.

        When True, the scene's per-speaker segments are passed as one
        ordered script (e.g. `Speaker 0: ...\\nSpeaker 1: ...`) with
        a positional voice slot map — and the provider returns one
        cohesive audio stream with seamless turn-taking between speakers.
        Implementing providers must also implement
        `synthesize_multi_speaker_block` and (optionally)
        `synthesize_multi_speaker_stream`.
        """
        return False

    @property
    def supports_multi_speaker_streaming(self) -> bool:
        """Multi-speaker call can stream PCM frames as the model generates.

        Implies `supports_multi_speaker_script` is also True. When True,
        `synthesize_multi_speaker_stream` yields raw PCM bytes matching
        `streaming_pcm_format` — the same WS protocol as single-utterance
        streaming, just one big stream instead of N chunked streams.
        """
        return False

    @property
    def max_speakers_per_call(self) -> int:
        """Hard cap on distinct speaker slots in one multi-speaker call.

        VibeVoice = 4 (model architecture limit). F5-TTS effectively
        unbounded (TOML voice library). Default 1 means no multi-speaker
        support — the dispatcher won't even try.
        """
        return 1
    
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
    
    async def synthesize_multi_speaker_block(
        self, request: "MultiSpeakerRequest"
    ) -> TTSResponse:
        """Render a multi-speaker scene as one complete audio file.

        Default implementation raises — providers without
        `supports_multi_speaker_script` will never have this called by
        the dispatcher, so they don't need to override.
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support multi-speaker scripts"
        )

    async def synthesize_multi_speaker_stream(
        self, request: "MultiSpeakerRequest"
    ) -> AsyncIterator[bytes]:
        """Stream a multi-speaker scene as PCM frames (sub-second TTFB).

        Default implementation raises — providers without
        `supports_multi_speaker_streaming` will never have this called.
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support multi-speaker streaming"
        )
        yield b""  # unreachable, satisfies AsyncIterator typing

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
