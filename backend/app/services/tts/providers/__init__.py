"""
TTS Providers Module

Import all TTS provider implementations to register them.
"""

from .openai_compatible import OpenAICompatibleProvider
from .chatterbox import ChatterboxProvider
from .kokoro import KokoroProvider
from .orpheus import OrpheusProvider
from .vibevoice import VibeVoiceProvider

__all__ = [
    "OpenAICompatibleProvider",
    "ChatterboxProvider",
    "KokoroProvider",
    "OrpheusProvider",
    "VibeVoiceProvider",
]
