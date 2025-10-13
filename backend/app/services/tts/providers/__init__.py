"""
TTS Providers Module

Import all TTS provider implementations to register them.
"""

from .openai_compatible import OpenAICompatibleProvider

__all__ = [
    "OpenAICompatibleProvider",
]
