"""
TTS Service Module

Provides text-to-speech functionality with support for multiple providers.
"""

from .base import (
    TTSProviderBase,
    TTSProviderConfig,
    TTSRequest,
    TTSResponse,
    Voice,
    AudioFormat,
    TTSProviderError,
    TTSProviderNotFoundError,
    TTSProviderConfigError,
    TTSProviderAPIError
)
from .registry import TTSProviderRegistry
from .factory import TTSProviderFactory
from .text_chunker import TextChunker, TextChunk
from .tts_service import TTSService

# Import providers to trigger registration
from .providers import openai_compatible, chatterbox, kokoro, orpheus, vibevoice

__all__ = [
    "TTSProviderBase",
    "TTSProviderConfig",
    "TTSRequest",
    "TTSResponse",
    "Voice",
    "AudioFormat",
    "TTSProviderError",
    "TTSProviderNotFoundError",
    "TTSProviderConfigError",
    "TTSProviderAPIError",
    "TTSProviderRegistry",
    "TTSProviderFactory",
    "TextChunker",
    "TextChunk",
    "TTSService",
]
