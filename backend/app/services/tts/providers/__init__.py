"""
TTS Providers Module

Import all TTS provider implementations to register them.
"""

from .openai_compatible import OpenAICompatibleProvider
from .chatterbox import ChatterboxProvider
from .kokoro import KokoroProvider
from .orpheus import OrpheusProvider
from .vibevoice import VibeVoiceProvider
from .qwen3 import Qwen3TTSProvider
from .indextts import IndexTTSProvider
from .chatterbox_turbo import ChatterboxTurboProvider

__all__ = [
    "OpenAICompatibleProvider",
    "ChatterboxProvider",
    "KokoroProvider",
    "OrpheusProvider",
    "VibeVoiceProvider",
    "Qwen3TTSProvider",
    "IndexTTSProvider",
    "ChatterboxTurboProvider",
]
