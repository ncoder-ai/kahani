"""
LiteLLM Client Management

Handles LiteLLM client configuration and connection management for different providers.
"""

import litellm
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    """Manages LiteLLM client configuration and connections"""
    
    def __init__(self, user_settings: Dict[str, Any]):
        """Initialize LLM client with user settings"""
        self.user_settings = user_settings
        self.llm_config = user_settings.get('llm_settings', {})
        
        # Validate required settings
        self.api_url = self.llm_config.get('api_url')
        if not self.api_url:
            raise ValueError("LLM API URL not configured. Please provide your LLM endpoint URL in user settings first.")
        
        # Extract configuration
        self.api_key = self.llm_config.get('api_key', '')
        self.api_type = self.llm_config.get('api_type', 'openai_compatible')
        self.model_name = self.llm_config.get('model_name', 'gpt-3.5-turbo')
        
        # Generation parameters
        self.temperature = self.llm_config.get('temperature', 0.7)
        self.top_p = self.llm_config.get('top_p', 1.0)
        self.top_k = self.llm_config.get('top_k', 50)
        self.repetition_penalty = self.llm_config.get('repetition_penalty', 1.1)
        self.max_tokens = self.llm_config.get('max_tokens', 2048)
        
        # Configure LiteLLM model string based on provider
        self.model_string = self._build_model_string()
        
        # Set LiteLLM configuration
        self._configure_litellm()
    
    def _build_model_string(self) -> str:
        """Build LiteLLM model string based on provider type"""
        if self.api_type == "openai":
            return self.model_name
        elif self.api_type == "openai_compatible":
            # For OpenAI-compatible APIs like TabbyAPI, etc.
            return f"openai/{self.model_name}"
        elif self.api_type == "lm_studio":
            # For LM Studio
            return f"lm_studio/{self.model_name}"
        elif self.api_type == "ollama":
            return f"ollama/{self.model_name}"
        elif self.api_type == "koboldcpp":
            return f"koboldcpp/{self.model_name}"
        elif self.api_type == "anthropic":
            return f"anthropic/{self.model_name}"
        elif self.api_type == "cohere":
            return f"cohere/{self.model_name}"
        else:
            # Default fallback to openai format
            return f"openai/{self.model_name}"
    
    def _configure_litellm(self):
        """Configure LiteLLM with provider-specific settings"""
        # Set the base URL for the provider - use exactly what the user provided
        if self.api_type == "openai_compatible":
            litellm.api_base = self.api_url
            if self.api_key:
                litellm.api_key = self.api_key
        elif self.api_type == "lm_studio":
            # LM Studio uses environment variables for configuration
            import os
            os.environ['LM_STUDIO_API_BASE'] = self.api_url
            if self.api_key:
                os.environ['LM_STUDIO_API_KEY'] = self.api_key
        elif self.api_type == "ollama":
            litellm.api_base = self.api_url
        elif self.api_type == "koboldcpp":
            litellm.api_base = self.api_url
        elif self.api_type == "anthropic":
            if self.api_key:
                litellm.api_key = self.api_key
        elif self.api_type == "cohere":
            if self.api_key:
                litellm.api_key = self.api_key
        
        # Configure logging
        litellm.set_verbose = logger.level <= logging.DEBUG
        
        logger.info(f"Configured LiteLLM for {self.api_type} with model {self.model_string}")
    
    def get_generation_params(self, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """Get generation parameters for API calls"""
        params = {
            "model": self.model_string,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
        }
        
        # Add provider-specific parameters (only for providers that support them)
        if self.api_type == "koboldcpp":
            if hasattr(self, 'top_k'):
                params["top_k"] = self.top_k
            if hasattr(self, 'repetition_penalty'):
                params["repetition_penalty"] = self.repetition_penalty
        # For openai_compatible (like LM Studio), only use standard OpenAI parameters
        # For ollama, only use standard parameters
        
        return params
    
    def get_streaming_params(self, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """Get generation parameters for streaming API calls"""
        params = self.get_generation_params(max_tokens, temperature)
        params["stream"] = True
        return params
    
    async def test_connection(self) -> tuple[bool, str]:
        """Test if the LLM service is available and return detailed error info"""
        try:
            from litellm import acompletion
            
            # Simple test request
            response = await acompletion(
                model=self.model_string,
                messages=[{"role": "user", "content": "Hello, please respond with 'Connection successful'"}],
                max_tokens=10
            )
            
            content = response.choices[0].message.content
            if "successful" in content.lower():
                return True, "Connection successful"
            else:
                return False, f"Unexpected response: {content}"
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"LLM connection test failed: {error_msg}")
            
            # Provide helpful error messages based on common issues
            if "404" in error_msg or "Not Found" in error_msg:
                if self.api_type == "openai_compatible":
                    return False, f"API endpoint not found. For TabbyAPI and similar services, try adding '/v1' to your URL: {self.api_url}/v1"
                else:
                    return False, f"API endpoint not found at {self.api_url}. Please check your URL."
            elif "401" in error_msg or "Unauthorized" in error_msg:
                return False, f"Authentication failed. Please check your API key."
            elif "403" in error_msg or "Forbidden" in error_msg:
                return False, f"Access forbidden. Please check your API key and permissions."
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                return False, f"Cannot connect to {self.api_url}. Please check if the service is running and accessible."
            else:
                return False, f"Connection failed: {error_msg}"
