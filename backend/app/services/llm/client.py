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
        """Initialize LLM client with user settings - NO DEFAULTS, user must configure everything"""
        # Validate that user_settings is provided
        if not user_settings:
            raise ValueError("No LLM settings provided. Please configure your LLM settings first.")
        
        self.user_settings = user_settings
        
        # Support both nested and flat structure for backwards compatibility
        # If 'llm_settings' key exists, use it (old format)
        # Otherwise, use the flat structure (new format)
        if 'llm_settings' in user_settings:
            self.llm_config = user_settings['llm_settings']
        else:
            self.llm_config = user_settings
        
        # Validate required settings - NO DEFAULTS
        self.api_url = self.llm_config.get('api_url')
        if not self.api_url:
            raise ValueError("LLM API URL not configured. Please provide your LLM endpoint URL in user settings.")
        
        self.api_type = self.llm_config.get('api_type')
        if not self.api_type:
            raise ValueError("LLM API type not configured. Please provide your LLM API type in user settings.")
        
        self.model_name = self.llm_config.get('model_name')
        if not self.model_name:
            raise ValueError("LLM model name not configured. Please provide your LLM model name in user settings.")
        
        # API key is optional for some providers (like localhost LM Studio)
        self.api_key = self.llm_config.get('api_key', '')
        
        # Generation parameters - use user values or None (will be set per-request if not provided)
        self.temperature = self.llm_config.get('temperature')
        self.top_p = self.llm_config.get('top_p')
        self.top_k = self.llm_config.get('top_k')
        self.repetition_penalty = self.llm_config.get('repetition_penalty')
        self.max_tokens = self.llm_config.get('max_tokens')
        
        # Configure LiteLLM model string based on provider
        self.model_string = self._build_model_string()
        
        # Set LiteLLM configuration
        self._configure_litellm()
    
    def _build_model_string(self) -> str:
        """Build LiteLLM model string based on provider type"""
        if self.api_type == "openai":
            return self.model_name
        elif self.api_type == "openai-compatible" or self.api_type == "openai_compatible":
            # For OpenAI-compatible APIs, MUST use openai/ prefix
            # As per LiteLLM docs: model="openai/mistral"
            return f"openai/{self.model_name}"
        elif self.api_type == "lm_studio":
            # LM Studio is also OpenAI-compatible
            return f"openai/{self.model_name}"
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
        # For openai-compatible, we DON'T set api_base globally because LiteLLM
        # automatically adds /v1. Instead, we pass it per-request in get_generation_params()
        if self.api_type == "openai-compatible":
            # Just set the API key if needed
            if self.api_key and self.api_key.strip():
                litellm.api_key = self.api_key
            else:
                # Set a dummy API key for LM Studio compatibility
                litellm.api_key = "lm-studio-dummy-key"
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
        
        # Disable verbose logging to reduce console noise
        litellm.set_verbose = False
        
        logger.info(f"Configured LiteLLM for {self.api_type} with model {self.model_string}")
    
    def get_generation_params(self, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """Get generation parameters for API calls"""
        params = {
            "model": self.model_string,
        }
        
        # Log what settings we're using
        logger.info(f"Building generation params - user settings: temp={self.temperature}, top_p={self.top_p}, top_k={self.top_k}, rep_penalty={self.repetition_penalty}")
        
        # Only add parameters if they're provided (either as args or in user settings)
        # Use provided values first, then user settings, then skip if neither
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        elif self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        else:
            # Use a reasonable default if absolutely nothing is provided
            params["max_tokens"] = 2048
        
        if temperature is not None:
            params["temperature"] = temperature
        elif self.temperature is not None:
            params["temperature"] = self.temperature
        else:
            params["temperature"] = 0.7
        
        # Only add top_p if explicitly set (don't default to 1.0)
        if self.top_p is not None:
            params["top_p"] = self.top_p
        
        # Add API base and key for openai-compatible providers
        # Pass api_base per-request so LiteLLM uses it directly without modification
        if self.api_type == "openai-compatible":
            params["api_base"] = self.api_url
            # For localhost (LM Studio, etc), use a dummy key that LiteLLM accepts
            # LiteLLM will pass it through but local servers typically ignore it
            if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                params["api_key"] = "dummy-key-for-local-server"
            elif self.api_key and self.api_key.strip():
                params["api_key"] = self.api_key
            else:
                # For non-localhost openai-compatible, still need some key
                params["api_key"] = self.api_key or "not-needed"
        elif self.api_type in ["openai", "anthropic", "cohere"]:
            # For these providers, API key is required
            if self.api_key:
                params["api_key"] = self.api_key
        
        # Add provider-specific parameters
        # Note: OpenAI-compatible APIs (like LM Studio) may support these via extra_body
        if self.api_type == "koboldcpp":
            if self.top_k is not None:
                params["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                params["repetition_penalty"] = self.repetition_penalty
        elif self.api_type in ["openai-compatible", "lm_studio"]:
            # For OpenAI-compatible APIs, use extra_body for non-standard params
            extra_body = {}
            if self.top_k is not None:
                extra_body["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                extra_body["repetition_penalty"] = self.repetition_penalty
            if extra_body:
                params["extra_body"] = extra_body
        
        logger.info(f"Final generation params: {params}")
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
