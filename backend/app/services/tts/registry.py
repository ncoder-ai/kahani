"""
TTS Provider Registry

Registry for TTS providers allowing dynamic registration and retrieval.
"""

from typing import Dict, Type, List
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
