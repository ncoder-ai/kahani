"""
TTS Providers Module

Import all TTS provider implementations to register them.
"""

from .openai_compatible import OpenAICompatibleProvider
from .chatterbox import ChatterboxProvider
from .kokoro import KokoroProvider

__all__ = [
    "OpenAICompatibleProvider",
    "ChatterboxProvider",
    "KokoroProvider",
]
