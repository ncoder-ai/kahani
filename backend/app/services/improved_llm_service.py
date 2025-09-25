"""
Improved LLM Service Architecture
- Loads user settings once into a configured client
- Caches client configurations per user
- Clean separation of concerns
- Efficient parameter handling
"""

import httpx
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
import logging
from dataclasses import dataclass
from ..config import settings

logger = logging.getLogger(__name__)

@dataclass
class LLMClientConfig:
    """Configuration for an LLM client instance"""
    user_id: int
    api_url: str
    api_key: str
    api_type: str
    model_name: str
    temperature: float
    top_p: float
    top_k: int
    repetition_penalty: float
    max_tokens: int
    
    @classmethod
    def from_user_settings(cls, user_id: int, user_settings: Dict[str, Any]) -> 'LLMClientConfig':
        """Create client config from user settings"""
        llm_config = user_settings.get('llm_settings', {})
        
        api_url = llm_config.get('api_url')
        if not api_url or api_url.strip() == "":
            raise ValueError("LLM API URL not configured. Please provide your LLM endpoint URL in user settings first.")
        
        return cls(
            user_id=user_id,
            api_url=api_url,
            api_key=llm_config.get('api_key', ''),
            api_type=llm_config.get('api_type', 'openai_compatible'),
            model_name=llm_config.get('model_name', 'local-model'),
            temperature=llm_config.get('temperature', 0.7),
            top_p=llm_config.get('top_p', 1.0),
            top_k=llm_config.get('top_k', 50),
            repetition_penalty=llm_config.get('repetition_penalty', 1.1),
            max_tokens=llm_config.get('max_tokens', 2048)
        )
    
    def get_endpoint(self) -> str:
        """Get the correct API endpoint based on provider type"""
        if self.api_type == "ollama":
            return f"{self.api_url}/api/chat"
        elif self.api_type == "koboldcpp":
            return f"{self.api_url}/api/v1/chat/completions"
        else:  # openai, openai_compatible
            if self.api_url.endswith("/v1"):
                return f"{self.api_url}/chat/completions"
            else:
                return f"{self.api_url}/v1/chat/completions"
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "not-needed-for-local":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

class ImprovedLLMService:
    """
    Improved LLM Service with proper client management
    - Caches user configurations to avoid repeated parsing
    - Uses persistent HTTP client with connection pooling
    - Clean parameter management
    """
    
    def __init__(self):
        self._client_configs: Dict[int, LLMClientConfig] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create persistent HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
        return self._http_client
    
    async def close(self):
        """Clean up resources"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    def get_user_config(self, user_id: int, user_settings: Dict[str, Any]) -> LLMClientConfig:
        """Get or create user LLM configuration"""
        if user_id not in self._client_configs:
            self._client_configs[user_id] = LLMClientConfig.from_user_settings(user_id, user_settings)
            logger.info(f"Created LLM config for user {user_id}: {self._client_configs[user_id].api_url}")
        
        return self._client_configs[user_id]
    
    def invalidate_user_config(self, user_id: int):
        """Invalidate cached config when user updates settings"""
        if user_id in self._client_configs:
            del self._client_configs[user_id]
            logger.info(f"Invalidated LLM config cache for user {user_id}")
    
    def _build_payload(
        self,
        config: LLMClientConfig,
        messages: list,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Build request payload"""
        return {
            "model": config.model_name,
            "messages": messages,
            "max_tokens": max_tokens or config.max_tokens or 1024,
            "temperature": temperature if temperature is not None else config.temperature,
            "stream": stream
        }
    
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
        
        # Get user configuration (cached)
        config = self.get_user_config(user_id, user_settings)
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Build payload
        payload = self._build_payload(config, messages, max_tokens, temperature)
        
        # Get HTTP client and make request
        client = await self._get_http_client()
        
        logger.info(f"Generating with {config.model_name} for user {user_id} at {config.api_url}")
        logger.info(f"Request payload: {payload}")
        
        try:
            response = await client.post(
                config.get_endpoint(),
                headers=config.get_headers(),
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            logger.info(f"Generated {len(content)} characters for user {user_id}")
            return content
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for user {user_id}: {e}")
            logger.error(f"Error response body: {e.response.text}")
            logger.error(f"Request URL: {config.get_endpoint()}")
            logger.error(f"Request payload: {payload}")
            raise ValueError(f"LLM API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Generation error for user {user_id}: {e}")
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
        
        # Get user configuration (cached)
        config = self.get_user_config(user_id, user_settings)
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Build payload for streaming
        payload = self._build_payload(config, messages, max_tokens, temperature, stream=True)
        
        # Get HTTP client
        client = await self._get_http_client()
        
        logger.info(f"Streaming with {config.model_name} for user {user_id} at {config.api_url}")
        
        try:
            async with client.stream(
                "POST",
                config.get_endpoint(),
                headers=config.get_headers(),
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_lines():
                    if not chunk:  # Skip empty chunks
                        continue
                        
                    try:
                        # Convert everything to string first to avoid type issues
                        if isinstance(chunk, bytes):
                            chunk_str = chunk.decode('utf-8')
                        else:
                            chunk_str = str(chunk)
                        
                        # Now work with strings consistently
                        if chunk_str.startswith("data: "):
                            chunk_data = chunk_str[6:]  # Remove "data: "
                            
                            if chunk_data.strip() == "[DONE]":
                                break
                            
                            try:
                                import json
                                data = json.loads(chunk_data)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        yield delta["content"]
                            except json.JSONDecodeError:
                                continue
                                
                    except Exception as e:
                        logger.error(f"Error processing chunk: {e}, chunk type: {type(chunk)}, chunk value: {repr(chunk[:100] if chunk else None)}")
                        continue  # Don't raise, just continue
                            
        except httpx.HTTPStatusError as e:
            logger.error(f"Streaming HTTP error for user {user_id}: {e}")
            raise ValueError(f"LLM streaming API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Streaming error for user {user_id}: {e}")
            raise ValueError(f"LLM streaming failed: {str(e)}")

# Global service instance - initialized once
improved_llm_service = ImprovedLLMService()

# Cleanup function for app shutdown
async def cleanup_llm_service():
    """Call this on app shutdown"""
    await improved_llm_service.close()