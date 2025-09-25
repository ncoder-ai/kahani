"""
Modern LLM Service Architecture using LiteLLM
- Load user settings once into a configured client
- Support multiple LLM providers through LiteLLM
- Connection pooling and proper error handling
- Clean separation of concerns
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
import litellm
from litellm import acompletion
import logging
from ..models.user_settings import UserSettings
from ..config import settings

logger = logging.getLogger(__name__)

class LLMClientConfig:
    """Configuration for an LLM client instance"""
    
    def __init__(self, user_settings: Dict[str, Any]):
        self.user_settings = user_settings
        llm_config = user_settings.get('llm_settings', {})
        
        # Validate required settings
        self.api_url = llm_config.get('api_url')
        if not self.api_url:
            raise ValueError("LLM API URL not configured. Please provide your LLM endpoint URL in user settings first.")
        
        # Extract configuration
        self.api_key = llm_config.get('api_key', '')
        self.api_type = llm_config.get('api_type', 'openai_compatible')
        self.model_name = llm_config.get('model_name', 'gpt-3.5-turbo')
        
        # Generation parameters
        self.temperature = llm_config.get('temperature', 0.7)
        self.top_p = llm_config.get('top_p', 1.0)
        self.top_k = llm_config.get('top_k', 50)
        self.repetition_penalty = llm_config.get('repetition_penalty', 1.1)
        self.max_tokens = llm_config.get('max_tokens', 2048)
        
        # Configure LiteLLM model string based on provider
        self.model_string = self._build_model_string()
        
        # Set LiteLLM configuration
        self._configure_litellm()
    
    def _build_model_string(self) -> str:
        """Build LiteLLM model string based on provider type"""
        if self.api_type == "openai":
            return self.model_name
        elif self.api_type == "openai_compatible":
            # For OpenAI-compatible APIs like TabbyAPI
            return f"openai/{self.model_name}"
        elif self.api_type == "ollama":
            return f"ollama/{self.model_name}"
        elif self.api_type == "koboldcpp":
            return f"koboldcpp/{self.model_name}"
        else:
            return f"openai/{self.model_name}"  # Default fallback
    
    def _configure_litellm(self):
        """Configure LiteLLM with provider-specific settings"""
        # Set the base URL for the provider
        if self.api_type == "openai_compatible":
            litellm.api_base = self.api_url
            if self.api_key:
                litellm.api_key = self.api_key
        elif self.api_type == "ollama":
            litellm.api_base = self.api_url
        elif self.api_type == "koboldcpp":
            litellm.api_base = self.api_url
        
        # Configure logging
        litellm.set_verbose = logger.level <= logging.DEBUG

class ModernLLMService:
    """
    Modern LLM Service using LiteLLM
    - Loads user settings once per session
    - Uses LiteLLM for multi-provider support  
    - Proper connection pooling and error handling
    """
    
    def __init__(self):
        self._client_cache: Dict[int, LLMClientConfig] = {}
        self._fallback_config = None
    
    def get_user_client(self, user_id: int, user_settings: Dict[str, Any]) -> LLMClientConfig:
        """Get or create LLM client configuration for user"""
        if user_id not in self._client_cache:
            try:
                self._client_cache[user_id] = LLMClientConfig(user_settings)
                logger.info(f"Created LLM client for user {user_id} with provider {self._client_cache[user_id].api_type}")
            except Exception as e:
                logger.error(f"Failed to create LLM client for user {user_id}: {e}")
                raise
        
        return self._client_cache[user_id]
    
    def invalidate_user_client(self, user_id: int):
        """Invalidate cached client when user updates settings"""
        if user_id in self._client_cache:
            del self._client_cache[user_id]
            logger.info(f"Invalidated LLM client cache for user {user_id}")
    
    async def generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """Generate text using user's configured LLM"""
        
        client_config = self.get_user_client(user_id, user_settings)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Override parameters if specified
        gen_params = {
            "model": client_config.model_string,
            "messages": messages,
            "max_tokens": max_tokens or client_config.max_tokens,
            "temperature": temperature if temperature is not None else client_config.temperature,
            "top_p": client_config.top_p,
        }
        
        # Add provider-specific parameters
        if client_config.api_type in ["openai_compatible", "koboldcpp"]:
            if hasattr(client_config, 'top_k'):
                gen_params["top_k"] = client_config.top_k
            if hasattr(client_config, 'repetition_penalty'):
                gen_params["repetition_penalty"] = client_config.repetition_penalty
        
        try:
            logger.info(f"Generating with {client_config.model_string} for user {user_id}")
            
            response = await acompletion(**gen_params)
            
            content = response.choices[0].message.content
            logger.info(f"Generated {len(content)} characters for user {user_id}")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM generation failed for user {user_id}: {e}")
            raise ValueError(f"LLM generation failed: {str(e)}")
    
    async def generate_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """Generate streaming text using user's configured LLM"""
        
        client_config = self.get_user_client(user_id, user_settings)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        gen_params = {
            "model": client_config.model_string,
            "messages": messages,
            "max_tokens": max_tokens or client_config.max_tokens,
            "temperature": temperature if temperature is not None else client_config.temperature,
            "top_p": client_config.top_p,
            "stream": True
        }
        
        # Add provider-specific parameters
        if client_config.api_type in ["openai_compatible", "koboldcpp"]:
            if hasattr(client_config, 'top_k'):
                gen_params["top_k"] = client_config.top_k
            if hasattr(client_config, 'repetition_penalty'):
                gen_params["repetition_penalty"] = client_config.repetition_penalty
        
        try:
            logger.info(f"Streaming generation with {client_config.model_string} for user {user_id}")
            
            response = await acompletion(**gen_params)
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"LLM streaming failed for user {user_id}: {e}")
            raise ValueError(f"LLM streaming failed: {str(e)}")

# Global service instance
modern_llm_service = ModernLLMService()