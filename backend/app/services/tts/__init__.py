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
]
