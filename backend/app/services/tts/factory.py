"""
TTS Provider Factory

Factory for creating TTS provider instances based on configuration.
"""

from typing import Optional
from sqlalchemy.orm import Session
from .base import TTSProviderBase, TTSProviderConfig, TTSProviderConfigError
from .registry import TTSProviderRegistry


class TTSProviderFactory:
    """
    Factory for creating TTS provider instances.
    
    Handles provider selection and instantiation based on user settings.
    """
    
    @staticmethod
    def create_provider(
        provider_type: str,
        api_url: str,
        api_key: str = "",
        timeout: int = 30,
        retry_attempts: int = 3,
        custom_headers: Optional[dict] = None,
        extra_params: Optional[dict] = None
    ) -> TTSProviderBase:
        """
        Create a TTS provider instance.
        
        Args:
            provider_type: Provider name (e.g., 'openai-compatible')
            api_url: API endpoint URL
            api_key: API key for authentication
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts
            custom_headers: Custom HTTP headers
            extra_params: Provider-specific parameters
            
        Returns:
            Instantiated provider
            
        Raises:
            TTSProviderConfigError: If provider configuration is invalid
        """
        if not provider_type:
            raise TTSProviderConfigError("No TTS provider specified")
        
        # Get provider class from registry
        provider_class = TTSProviderRegistry.get_provider(provider_type)
        
        # Create provider configuration
        config = TTSProviderConfig(
            api_url=api_url,
            api_key=api_key or "",
            timeout=timeout,
            retry_attempts=retry_attempts,
            custom_headers=custom_headers,
            extra_params=extra_params or {}
        )
        
        # Instantiate and return provider
        try:
            return provider_class(config)
        except Exception as e:
            raise TTSProviderConfigError(
                f"Failed to create {provider_type} provider: {str(e)}"
            )
    
    @staticmethod
    def get_available_providers() -> list:
        """
        Get list of all available TTS providers.
        
        Returns:
            List of provider names
        """
        return TTSProviderRegistry.list_providers()
