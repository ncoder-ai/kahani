"""
Unified LLM Service

Provides a clean, unified interface for all LLM operations using LiteLLM
and centralized prompt management. Also handles scene variant database operations.
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List, Tuple
import litellm
from litellm import acompletion
import logging
import re
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from .client import LLMClient
from .prompts import prompt_manager
from .templates import TextCompletionTemplateManager
from .thinking_parser import ThinkingTagParser

# Import for type hints (will be imported within functions to avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models import Scene, SceneVariant

logger = logging.getLogger(__name__)

class UnifiedLLMService:
    """
    Unified LLM Service using LiteLLM
    
    Features:
    - Multi-provider support through LiteLLM
    - Centralized prompt management
    - User configuration caching
    - Both streaming and non-streaming operations
    - Comprehensive error handling
    """
    
    def __init__(self):
        self._client_cache: Dict[int, LLMClient] = {}
    
    def get_user_client(self, user_id: int, user_settings: Dict[str, Any]) -> LLMClient:
        """Get or create LLM client configuration for user"""
        # Always recreate client from user_settings to ensure we have latest settings
        # This is important for completion_mode and other settings that affect API calls
        try:
            client = LLMClient(user_settings)
            # Update cache with new client
            self._client_cache[user_id] = client
            logger.info(f"Created/updated LLM client for user {user_id} with provider {client.api_type}, completion_mode={client.completion_mode}")
        except Exception as e:
            logger.error(f"Failed to create LLM client for user {user_id}: {e}")
            raise
        
        # Ensure the global LiteLLM configuration is set correctly for this user
        client._configure_litellm()
        
        return client
    
    async def validate_user_connection(self, user_id: int, user_settings: Dict[str, Any]) -> tuple[bool, str]:
        """Validate user's LLM connection and return detailed error info"""
        try:
            client = self.get_user_client(user_id, user_settings)
            return await client.test_connection()
        except Exception as e:
            return False, f"Failed to create client: {str(e)}"
    
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
        temperature: Optional[float] = None,
        stream: bool = False
    ) -> str:
        """Generic text generation with streaming toggle"""
        if stream:
            # For streaming, collect all chunks and return complete text
            complete_text = ""
            async for chunk in self._generate_stream(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            ):
                complete_text += chunk
            return complete_text
        else:
            return await self._generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
    
    # Remove redundant generate_stream method - use _generate_stream directly
    
    async def _generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """Internal method for non-streaming generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check completion mode and branch accordingly
        completion_mode = client.completion_mode
        logger.info(f"User {user_id} generation mode: {completion_mode} (from client.completion_mode={client.completion_mode})")
        if completion_mode == "text":
            logger.info(f"Using text completion API for user {user_id}")
            return await self._generate_text_completion(
                prompt, user_id, user_settings, system_prompt, max_tokens, temperature
            )
        
        logger.info(f"Using chat completion API for user {user_id}")
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        messages = []
        if system_prompt and system_prompt.strip():
            # Inject NSFW filter if user doesn't have NSFW permissions
            if should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.info(f"NSFW filter injected for user {user_id}")
            
            messages.append({"role": "system", "content": system_prompt.strip()})
        elif should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            messages.append({"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.info(f"NSFW filter injected (no system prompt) for user {user_id}")
        
        # Ensure prompt is valid string
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        
        messages.append({"role": "user", "content": prompt.strip()})
        
        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        try:
            logger.info(f"Generating with {client.model_string} for user {user_id}")
            
            response = await acompletion(**gen_params)
            
            content = response.choices[0].message.content
            logger.info(f"Generated {len(content)} characters for user {user_id}")
            
            return content
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LiteLLM generation failed for user {user_id}: {error_msg}")
            
            # Provide helpful error messages for common connection issues
            if "404" in error_msg or "Not Found" in error_msg:
                if client.api_type == "openai_compatible":
                    raise ValueError(f"API endpoint not found. For TabbyAPI and similar services, try adding '/v1' to your URL: {client.api_url}/v1")
                else:
                    raise ValueError(f"API endpoint not found at {client.api_url}. Please check your URL.")
            elif "401" in error_msg or "Unauthorized" in error_msg:
                raise ValueError(f"Authentication failed. Please check your API key.")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise ValueError(f"Access forbidden. Please check your API key and permissions.")
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                raise ValueError(f"Cannot connect to {client.api_url}. Please check if the service is running and accessible.")
            else:
                # Fallback to direct HTTP for LM Studio and TabbyAPI
                if client.api_type in ["lm_studio", "openai_compatible"]:
                    logger.info(f"Attempting direct HTTP fallback for {client.api_type}")
                    return await self._direct_http_fallback(client, messages, max_tokens, temperature, False)
                else:
                    logger.error(f"LLM generation failed for user {user_id}: {error_msg}")
                    raise ValueError(f"LLM generation failed: {error_msg}")
    
    async def _generate_text_completion(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """Internal method for text completion generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        # Inject NSFW filter into system prompt if needed
        if system_prompt and system_prompt.strip():
            if should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.info(f"NSFW filter injected for user {user_id}")
        elif should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            system_prompt = get_nsfw_prevention_prompt()
            logger.info(f"NSFW filter injected (no system prompt) for user {user_id}")
        
        # Ensure prompt is valid string
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        
        # Get template and render prompt
        template = TextCompletionTemplateManager.get_template_for_user(
            client.text_completion_template,
            client.text_completion_preset
        )
        
        rendered_prompt = TextCompletionTemplateManager.render_template(
            template,
            system_prompt=system_prompt or "",
            user_prompt=prompt.strip()
        )
        
        logger.debug(f"Rendered text completion prompt (length: {len(rendered_prompt)})")
        
        # Get generation parameters
        gen_params = client.get_text_completion_params(max_tokens, temperature)
        gen_params["prompt"] = rendered_prompt
        
        try:
            logger.info(f"Text completion with {client.model_string} for user {user_id}")
            logger.info(f"Calling text_completion with model={gen_params['model']}, prompt_length={len(gen_params['prompt'])}")
            
            # Use litellm.text_completion for text completion (synchronous, run in thread)
            from litellm import text_completion
            import asyncio
            
            response = await asyncio.to_thread(text_completion, **gen_params)
            
            content = response.choices[0].text if hasattr(response.choices[0], 'text') else response.choices[0].message.content
            logger.info(f"Generated {len(content)} characters for user {user_id}")
            
            # Strip thinking tags from response
            cleaned_content = ThinkingTagParser.strip_thinking_tags(content)
            if len(cleaned_content) != len(content):
                logger.info(f"Stripped thinking tags, reduced from {len(content)} to {len(cleaned_content)} characters")
            
            return cleaned_content
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LiteLLM text completion failed for user {user_id}: {error_msg}")
            
            # Provide helpful error messages for common connection issues
            if "404" in error_msg or "Not Found" in error_msg:
                if client.api_type == "openai_compatible":
                    raise ValueError(f"API endpoint not found. For TabbyAPI and similar services, try adding '/v1' to your URL: {client.api_url}/v1")
                else:
                    raise ValueError(f"API endpoint not found at {client.api_url}. Please check your URL.")
            elif "401" in error_msg or "Unauthorized" in error_msg:
                raise ValueError(f"Authentication failed. Please check your API key.")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise ValueError(f"Access forbidden. Please check your API key and permissions.")
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                raise ValueError(f"Cannot connect to {client.api_url}. Please check if the service is running and accessible.")
            else:
                # Fallback to direct HTTP for LM Studio and TabbyAPI
                if client.api_type in ["lm_studio", "openai_compatible"]:
                    logger.info(f"Attempting direct HTTP text completion fallback for {client.api_type}")
                    return await self._direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, False)
                else:
                    logger.error(f"Text completion failed for user {user_id}: {error_msg}")
                    raise ValueError(f"Text completion failed: {error_msg}")
    
    async def _direct_http_fallback(self, client, messages, max_tokens, temperature, stream):
        """Direct HTTP fallback for LM Studio when LiteLLM fails"""
        import httpx
        
        payload = {
            "model": client.model_name,  # Use the actual model name, not the prefixed one
            "messages": messages,
            "max_tokens": max_tokens or client.max_tokens,
            "temperature": temperature if temperature is not None else client.temperature,
            "stream": stream
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if client.api_key:
            headers["Authorization"] = f"Bearer {client.api_key}"
        
        try:
            # Determine the correct endpoint URL
            if client.api_url.endswith("/v1"):
                endpoint_url = f"{client.api_url}/chat/completions"
            else:
                endpoint_url = f"{client.api_url}/v1/chat/completions"
            
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                
                if stream:
                    # Handle streaming response
                    async def stream_generator():
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data.strip() == "[DONE]":
                                    break
                                try:
                                    import json
                                    chunk = json.loads(data)
                                    if "choices" in chunk and len(chunk["choices"]) > 0:
                                        delta = chunk["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                    return stream_generator()
                else:
                    # Handle non-streaming response
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"]
                    else:
                        raise ValueError("Invalid response format from LM Studio")
                        
        except Exception as e:
            logger.error(f"Direct HTTP fallback failed: {e}", exc_info=True)
            raise ValueError(f"LLM generation failed: {str(e)}")
    
    async def _direct_http_text_completion_fallback(self, client, prompt, max_tokens, temperature, stream):
        """Direct HTTP fallback for text completion when LiteLLM fails"""
        import httpx
        
        payload = {
            "model": client.model_name,  # Use the actual model name, not the prefixed one
            "prompt": prompt,
            "max_tokens": max_tokens or client.max_tokens,
            "temperature": temperature if temperature is not None else client.temperature,
            "stream": stream
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if client.api_key:
            headers["Authorization"] = f"Bearer {client.api_key}"
        
        try:
            # Determine the correct endpoint URL for text completion
            if client.api_url.endswith("/v1"):
                endpoint_url = f"{client.api_url}/completions"
            else:
                endpoint_url = f"{client.api_url}/v1/completions"
            
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                
                if stream:
                    # Handle streaming response
                    async def stream_generator():
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data.strip() == "[DONE]":
                                    break
                                try:
                                    import json
                                    chunk = json.loads(data)
                                    if "choices" in chunk and len(chunk["choices"]) > 0:
                                        # Text completion uses 'text' field, not 'delta'
                                        text = chunk["choices"][0].get("text", "")
                                        if text:
                                            # Strip thinking tags from each chunk
                                            cleaned_text = ThinkingTagParser.strip_thinking_tags(text)
                                            if cleaned_text:
                                                yield cleaned_text
                                except json.JSONDecodeError:
                                    continue
                    return stream_generator()
                else:
                    # Handle non-streaming response
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["text"]
                        # Strip thinking tags from response
                        return ThinkingTagParser.strip_thinking_tags(content)
                    else:
                        raise ValueError("Invalid response format from text completion endpoint")
                        
        except Exception as e:
            logger.error(f"Direct HTTP text completion fallback failed: {e}", exc_info=True)
            raise ValueError(f"Text completion failed: {str(e)}")
    
    async def _generate_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check completion mode and branch accordingly
        completion_mode = client.completion_mode
        logger.info(f"User {user_id} streaming generation mode: {completion_mode} (from client.completion_mode={client.completion_mode})")
        if completion_mode == "text":
            logger.info(f"Using text completion streaming API for user {user_id}")
            async for chunk in self._generate_text_completion_stream(
                prompt, user_id, user_settings, system_prompt, max_tokens, temperature
            ):
                yield chunk
            return
        
        logger.info(f"Using chat completion streaming API for user {user_id}")
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        messages = []
        if system_prompt and system_prompt.strip():
            # Inject NSFW filter if user doesn't have NSFW permissions
            if should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.info(f"NSFW filter injected for streaming user {user_id}")
            
            messages.append({"role": "system", "content": system_prompt.strip()})
        elif should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            messages.append({"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.info(f"NSFW filter injected (no system prompt) for streaming user {user_id}")
        
        # Ensure prompt is valid string
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        
        messages.append({"role": "user", "content": prompt.strip()})
        
        # Get streaming parameters
        gen_params = client.get_streaming_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        try:
            logger.info(f"Streaming generation with {client.model_string} for user {user_id}")
            
            response = await acompletion(**gen_params)
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"LLM streaming failed for user {user_id}: {e}")
            raise ValueError(f"LLM streaming failed: {str(e)}")
    
    async def _generate_text_completion_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming text completion generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        # Inject NSFW filter into system prompt if needed
        if system_prompt and system_prompt.strip():
            if should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.info(f"NSFW filter injected for streaming user {user_id}")
        elif should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            system_prompt = get_nsfw_prevention_prompt()
            logger.info(f"NSFW filter injected (no system prompt) for streaming user {user_id}")
        
        # Ensure prompt is valid string
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        
        # Get template and render prompt
        template = TextCompletionTemplateManager.get_template_for_user(
            client.text_completion_template,
            client.text_completion_preset
        )
        
        rendered_prompt = TextCompletionTemplateManager.render_template(
            template,
            system_prompt=system_prompt or "",
            user_prompt=prompt.strip()
        )
        
        logger.debug(f"Rendered streaming text completion prompt (length: {len(rendered_prompt)})")
        
        # Get streaming parameters
        gen_params = client.get_text_completion_streaming_params(max_tokens, temperature)
        gen_params["prompt"] = rendered_prompt
        
        try:
            logger.info(f"Streaming text completion with {client.model_string} for user {user_id}")
            logger.info(f"Calling text_completion (streaming) with model={gen_params['model']}, prompt_length={len(gen_params['prompt'])}")
            
            # Use litellm.text_completion for text completion (synchronous, run in thread)
            from litellm import text_completion
            import asyncio
            
            response = await asyncio.to_thread(text_completion, **gen_params)
            
            # Buffer for accumulating chunks to detect thinking tags
            buffer = ""
            thinking_detected = False
            
            async for chunk in response:
                # Get text from chunk (text completion uses 'text' field)
                chunk_text = ""
                if hasattr(chunk.choices[0], 'text'):
                    chunk_text = chunk.choices[0].text
                elif hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    chunk_text = chunk.choices[0].delta.content or ""
                
                if chunk_text:
                    buffer += chunk_text
                    
                    # Check if we've accumulated enough to detect thinking tags
                    if len(buffer) > 50:  # Arbitrary threshold
                        # Try to detect and strip thinking tags from buffer
                        cleaned_buffer = ThinkingTagParser.strip_thinking_tags(buffer)
                        
                        if len(cleaned_buffer) < len(buffer):
                            # Thinking tags detected and removed
                            thinking_detected = True
                            logger.debug(f"Thinking tags detected in stream, stripped {len(buffer) - len(cleaned_buffer)} chars")
                            buffer = cleaned_buffer
                        
                        # Yield the cleaned buffer and reset
                        if buffer:
                            yield buffer
                            buffer = ""
                    else:
                        # Buffer not large enough yet, keep accumulating
                        pass
            
            # Yield any remaining buffer
            if buffer:
                cleaned_buffer = ThinkingTagParser.strip_thinking_tags(buffer)
                if cleaned_buffer:
                    yield cleaned_buffer
                    
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LiteLLM streaming text completion failed for user {user_id}: {error_msg}")
            
            # Fallback to direct HTTP for LM Studio and TabbyAPI
            if client.api_type in ["lm_studio", "openai_compatible"]:
                logger.info(f"Attempting direct HTTP streaming text completion fallback for {client.api_type}")
                async for chunk in await self._direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, True):
                    yield chunk
            else:
                logger.error(f"Streaming text completion failed for user {user_id}: {error_msg}")
                raise ValueError(f"Streaming text completion failed: {str(e)}")
    
    def _clean_scene_numbers(self, content: str) -> str:
        """Remove scene numbers and titles from the beginning of generated content"""
        # Remove patterns like "Scene 7:", "Scene 7: Title", etc. from the start
        content = re.sub(r'^Scene\s+\d+:.*?(\n|$)', '', content, flags=re.IGNORECASE).strip()
        # Also remove standalone scene titles that might start with numbers
        content = re.sub(r'^\d+[:.]\s*[A-Z][^.\n]*(\n|$)', '', content).strip()
        return content
    
    def _clean_scene_numbers_chunk(self, chunk: str) -> str:
        """Clean scene numbers from streaming chunks - more conservative than full cleaning"""
        if chunk.strip().startswith(('Scene ', 'SCENE ', 'scene ')):
            if re.match(r'^Scene\s+\d+[:\-\s]', chunk, re.IGNORECASE):
                cleaned = re.sub(r'^Scene\s+\d+[:\-\s]*[^\n]*\n?', '', chunk, flags=re.IGNORECASE)
                return cleaned
        return chunk
    
    # Story Generation Functions
    
    async def generate_story_title(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
        """Generate creative story titles based on story content"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "title_generation", "title_generation",
            context=self._format_context_for_titles(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("titles")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse titles from response
        titles = [title.strip() for title in response.split('\n') if title.strip()]
        
        # Clean up titles
        cleaned_titles = []
        for title in titles:
            cleaned_title = title.strip()
            # Remove common prefixes like "1.", "•", "-", etc.
            cleaned_title = re.sub(r'^[\d\.\-\*\•]\s*', '', cleaned_title)
            # Remove quotes if they wrap the entire title
            if cleaned_title.startswith('"') and cleaned_title.endswith('"'):
                cleaned_title = cleaned_title[1:-1]
            if cleaned_title.startswith("'") and cleaned_title.endswith("'"):
                cleaned_title = cleaned_title[1:-1]
            
            if cleaned_title and len(cleaned_title.split()) <= 8:  # Reasonable title length
                cleaned_titles.append(cleaned_title.strip())
        
        # Ensure we have exactly 5 titles
        if len(cleaned_titles) < 5:
            fallback_titles = [
                "The Journey Begins",
                "Shadows and Light", 
                "Destiny Calls",
                "The Final Choice",
                "Beyond the Horizon"
            ]
            cleaned_titles.extend(fallback_titles[:5-len(cleaned_titles)])
        
        return cleaned_titles[:5]
    
    async def generate_story_chapters(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], chapter_count: int = 5) -> List[str]:
        """Generate a chapter structure for a story"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "story_chapters",
            context=self._format_context_for_chapters(context),
            chapter_count=chapter_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_chapters")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse chapters from response
        chapters = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for numbered chapters
            if re.match(r'^[\d\.\-\*]\s*', line):
                # Clean the chapter text
                chapter_text = re.sub(r'^[\d\.\-\*]\s*', '', line).strip()
                if chapter_text and len(chapter_text) > 10:  # Ensure substantial content
                    chapters.append(chapter_text)
        
        # Ensure we have the requested number of chapters
        if len(chapters) < chapter_count:
            fallback_chapters = [
                f"Chapter {i+1}: The story begins to unfold with new challenges and opportunities."
                for i in range(len(chapters), chapter_count)
            ]
            chapters.extend(fallback_chapters)
        
        return chapters[:chapter_count]
    
    async def generate_scene(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a story scene"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "scene_generation", "scene_generation",
            context=self._format_context_for_scene(context)
        )
        
        # Log the complete prompt for debugging
        logger.info("=" * 80)
        logger.info("SCENE GENERATION PROMPT")
        logger.info("=" * 80)
        logger.info(f"SYSTEM PROMPT:\n{system_prompt}")
        logger.info("-" * 80)
        logger.info(f"USER PROMPT:\n{user_prompt}")
        logger.info("=" * 80)
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate a story scene with streaming"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "scene_generation", "scene_generation",
            context=self._format_context_for_scene(context)
        )
        
        # Log the complete prompt for debugging
        logger.info("=" * 80)
        logger.info("SCENE GENERATION PROMPT (STREAMING)")
        logger.info("=" * 80)
        logger.info(f"SYSTEM PROMPT:\n{system_prompt}")
        logger.info("-" * 80)
        logger.info(f"USER PROMPT:\n{user_prompt}")
        logger.info("=" * 80)
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
    async def generate_scene_variants(self, original_scene: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate alternative versions of a scene"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "scene_variants",
            original_scene=original_scene,
            context=self._format_context_for_scene(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_variants", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_variants_streaming(self, original_scene: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate alternative versions of a scene with streaming"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "scene_variants_streaming",
            original_scene=original_scene,
            context=self._format_context_for_scene(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_variants", user_settings)
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
    async def generate_scene_continuation(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate continuation content for an existing scene"""
        
        # Detect POV from current scene content
        current_content = context.get("current_content", "")
        previous_scenes = context.get("previous_scenes", "")
        
        # Detect POV from current scene and previous scenes
        pov = self._detect_pov(current_content)
        if previous_scenes:
            previous_pov = self._detect_pov(previous_scenes)
            # Prefer POV from previous scenes if available (more context)
            if previous_pov != 'third' or pov == 'third':
                pov = previous_pov
        
        # Enhance system prompt with POV consistency requirement
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            context=self._format_context_for_continuation(context)
        )
        
        if pov == 'first':
            system_prompt += "\n\nIMPORTANT: Continue the story in first person perspective (using 'I', 'me', 'my'). Maintain consistency with the established first-person narrative style."
        else:
            system_prompt += "\n\nIMPORTANT: Continue the story in third person perspective (using 'he', 'she', 'they', character names). Maintain consistency with the established third-person narrative style."
        
        max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_continuation_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate continuation content for an existing scene with streaming"""
        
        # Detect POV from current scene content
        current_content = context.get("current_content", "") or context.get("current_scene_content", "")
        previous_scenes = context.get("previous_scenes", "")
        
        # Detect POV from current scene and previous scenes
        pov = self._detect_pov(current_content)
        if previous_scenes:
            previous_pov = self._detect_pov(previous_scenes)
            # Prefer POV from previous scenes if available (more context)
            if previous_pov != 'third' or pov == 'third':
                pov = previous_pov
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            context=self._format_context_for_continuation(context)
        )
        
        # Enhance system prompt with POV consistency requirement
        if pov == 'first':
            system_prompt += "\n\nIMPORTANT: Continue the story in first person perspective (using 'I', 'me', 'my'). Maintain consistency with the established first-person narrative style."
        else:
            system_prompt += "\n\nIMPORTANT: Continue the story in third person perspective (using 'he', 'she', 'they', character names). Maintain consistency with the established third-person narrative style."
        
        max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
    def _detect_pov(self, text: str) -> str:
        """
        Detect point of view (1st person vs 3rd person) from text.
        Returns 'first' or 'third'
        """
        if not text:
            return 'third'  # Default to third person
        
        # Look for first person indicators
        first_person_patterns = [
            r'\bI\b', r'\bme\b', r'\bmy\b', r'\bmyself\b', r'\bmine\b',
            r'\bwe\b', r'\bus\b', r'\bour\b', r'\bourselves\b'
        ]
        
        # Look for third person indicators
        third_person_patterns = [
            r'\bhe\b', r'\bshe\b', r'\bthey\b', r'\bhim\b', r'\bher\b',
            r'\bhis\b', r'\bhers\b', r'\btheirs\b', r'\bthem\b'
        ]
        
        text_lower = text.lower()
        
        first_person_count = sum(len(re.findall(pattern, text_lower)) for pattern in first_person_patterns)
        third_person_count = sum(len(re.findall(pattern, text_lower)) for pattern in third_person_patterns)
        
        # If first person indicators are significantly more common, return first
        if first_person_count > third_person_count * 1.5:
            return 'first'
        
        # Default to third person
        return 'third'
    
    async def generate_choices(self, scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
        """Generate 4 narrative choices for the given scene"""
        
        # Detect POV from scene content
        pov = self._detect_pov(scene_content)
        
        # Also check previous scenes if available
        previous_scenes = context.get("previous_scenes", "")
        if previous_scenes:
            previous_pov = self._detect_pov(previous_scenes)
            # Use the POV from previous scenes if available (more context)
            if previous_pov != 'third' or pov == 'third':
                pov = previous_pov
        
        # Add POV instruction to context
        pov_instruction = "third person" if pov == 'third' else "first person"
        enhanced_context = context.copy()
        enhanced_context["pov_instruction"] = pov_instruction
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "choice_generation", "choice_generation",
            scene_content=scene_content[-800:],  # Last 800 chars to avoid token limits
            context=self._format_context_for_choices(enhanced_context)
        )
        
        # Enhance system prompt with POV consistency requirement
        if pov == 'first':
            system_prompt += "\n\nIMPORTANT: Write all choices in first person perspective (using 'I', 'me', 'my'). The choices should match the story's first-person narrative style."
        else:
            system_prompt += "\n\nIMPORTANT: Write all choices in third person perspective (using 'he', 'she', 'they', character names). The choices should match the story's third-person narrative style."
        
        max_tokens = prompt_manager.get_max_tokens("choices")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse choices from response
        choices = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for numbered choices
            if re.match(r'^[\d\.\-\*\s]+', line):
                # Clean the choice text - remove all leading numbers, dots, hyphens, asterisks and spaces
                choice_text = re.sub(r'^[\d\.\-\*\s]+', '', line).strip()
                if choice_text and len(choice_text) > 10:  # Ensure substantial content
                    choices.append(choice_text)
        
        # Ensure we have at least some choices
        if len(choices) < 2:
            choices = [
                "Continue forward cautiously",
                "Take a different approach", 
                "Investigate further",
                "Make a bold decision"
            ]
        
        return choices[:4]  # Return up to 4 choices
    
    async def generate_scenario(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a creative scenario based on user selections and characters"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "scenario_generation", "scenario_generation",
            context=self._format_context_for_scenario(context),
            elements=self._format_elements_for_scenario(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scenario")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return response
    
    async def generate_plot_points(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], plot_type: str = "complete") -> List[str]:
        """Generate plot points based on characters and scenario"""
        
        if plot_type == "complete":
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "plot_generation", "complete_plot",
                context=self._format_context_for_plot(context)
            )
            max_tokens = prompt_manager.get_max_tokens("complete_plot")
        else:
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "plot_generation", "single_plot_point",
                context=self._format_context_for_plot(context),
                point_name=self._get_plot_point_name(context.get("plot_point_index", 0))
            )
            max_tokens = prompt_manager.get_max_tokens("single_plot_point")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        if plot_type == "complete":
            return self._parse_plot_points(response)
        else:
            return [response]
    
    async def generate_summary(self, story_content: str, story_context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a comprehensive story summary"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "story_summary",
            story_context=self._format_context_for_summary(story_context),
            story_content=story_content
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_summary")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return response.strip()
    
    # Helper methods for context formatting
    
    def _format_context_for_titles(self, context: Dict[str, Any]) -> str:
        """Format context for title generation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
        
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
        
        # Story elements
        story_elements = context.get("story_elements", {})
        if story_elements:
            elements = []
            for key, value in story_elements.items():
                if value:
                    elements.append(f"{key.title()}: {value}")
            if elements:
                context_parts.append(f"Story Elements:\n{chr(10).join(elements)}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_scene(self, context: Dict[str, Any]) -> str:
        """Format context for scene generation"""
        context_parts = []
        
        # Check if this is the first scene with user prompt
        is_first_scene = context.get("is_first_scene", False)
        user_prompt_provided = context.get("user_prompt_provided", False)
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            context_parts.append(f"Setting: {context['world_setting']}")
        
        # For first scene with user prompt, prioritize user prompt over scenario
        if is_first_scene and user_prompt_provided and context.get("current_situation"):
            # User prompt takes precedence for first scene
            context_parts.append(f"User's Opening Prompt: {context['current_situation']}")
            if context.get("scenario"):
                context_parts.append(f"Story Scenario (for reference): {context['scenario']}")
        else:
            # Normal order: scenario first, then user prompt if provided
            if context.get("scenario"):
                context_parts.append(f"Story Scenario: {context['scenario']}")
            if context.get("current_situation"):
                context_parts.append(f"Current Situation: {context['current_situation']}")
        
        if context.get("initial_premise"):
            context_parts.append(f"Initial Premise: {context['initial_premise']}")
        
        if context.get("characters"):
            char_descriptions = []
            for char in context["characters"]:
                char_desc = f"- {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_desc += f" ({char['role']})"
                char_desc += f": {char.get('description', 'No description')}"
                if char.get('personality'):
                    char_desc += f". Personality: {char['personality']}"
                if char.get('background'):
                    char_desc += f". Background: {char['background']}"
                if char.get('goals'):
                    char_desc += f". Goals: {char['goals']}"
                char_descriptions.append(char_desc)
            context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
        
        if context.get("scene_summary"):
            context_parts.append(f"Story Summary: {context['scene_summary']}")
        
        if context.get("previous_scenes"):
            context_parts.append(f"Previous Events:\n{context['previous_scenes']}")
        
        return "\n\n".join(context_parts)
    
    def _format_context_for_continuation(self, context: Dict[str, Any]) -> str:
        """Format context for scene continuation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("characters"):
            char_descriptions = [f"- {char.get('name', 'Unknown')}: {char.get('description', 'No description')}" 
                               for char in context["characters"]]
            context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
        
        if context.get("previous_content"):
            context_parts.append(f"Previous content: {context['previous_content'][-600:]}")  # Last 600 chars
        
        if context.get("choice_made"):
            context_parts.append(f"Reader's choice: {context['choice_made']}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_choices(self, context: Dict[str, Any]) -> str:
        """Format context for choice generation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("characters"):
            char_list = [char.get('name', 'Unknown') for char in context.get('characters', [])]
            if char_list:
                context_parts.append(f"Characters involved: {', '.join(char_list)}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_scenario(self, context: Dict[str, Any]) -> str:
        """Format context for scenario generation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
        
        return "\n".join(context_parts)
    
    def _format_elements_for_scenario(self, context: Dict[str, Any]) -> str:
        """Format story elements for scenario generation"""
        elements = []
        if context.get("opening"):
            elements.append(f"Story opening: {context['opening']}")
        if context.get("setting"):
            elements.append(f"Setting: {context['setting']}")
        if context.get("conflict"):
            elements.append(f"Driving force: {context['conflict']}")
        
        return "\n".join(elements)
    
    def _format_context_for_plot(self, context: Dict[str, Any]) -> str:
        """Format context for plot generation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
        
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
        
        # World setting
        if context.get("world_setting"):
            context_parts.append(f"World Setting:\n{context['world_setting']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_chapters(self, context: Dict[str, Any]) -> str:
        """Format context for chapter generation"""
        return self._format_context_for_plot(context)  # Same format as plot
    
    def _format_context_for_summary(self, context: Dict[str, Any]) -> str:
        """Format context for summary generation"""
        context_parts = []
        
        if context.get("title"):
            context_parts.append(f"Title: {context['title']}")
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("scene_count"):
            context_parts.append(f"Number of scenes: {context['scene_count']}")
        
        return "\n".join(context_parts)
    
    def _get_plot_point_name(self, index: int) -> str:
        """Get plot point name by index"""
        plot_point_names = [
            "Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"
        ]
        return plot_point_names[min(index, len(plot_point_names)-1)]
    
    def _parse_plot_points(self, response: str) -> List[str]:
        """Parse plot points from response"""
        plot_points = []
        
        # Clean up the response and look for plot points
        lines = response.split('\n')
        current_point = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for plot point markers (numbers, bullets, or keywords)
            if (re.match(r'^[\d\.\-\*\•]\s*', line) or 
                re.search(r'\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*', line, re.IGNORECASE)):
                
                # Save previous point if exists
                if current_point:
                    # Clean the point
                    clean_point = current_point.strip()
                    # Remove leading markers and formatting
                    clean_point = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_point)
                    clean_point = re.sub(r'^\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*:\s*', '', clean_point, flags=re.IGNORECASE)
                    clean_point = re.sub(r'^(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution):\s*', '', clean_point, flags=re.IGNORECASE)
                    if clean_point and len(clean_point) > 20:  # Ensure it's substantial content
                        plot_points.append(clean_point)
                
                current_point = line
            else:
                # Continuation of current point
                if current_point:
                    current_point += " " + line
        
        # Don't forget the last point
        if current_point:
            clean_point = current_point.strip()
            clean_point = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_point)
            clean_point = re.sub(r'^\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*:\s*', '', clean_point, flags=re.IGNORECASE)
            clean_point = re.sub(r'^(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution):\s*', '', clean_point, flags=re.IGNORECASE)
            if clean_point and len(clean_point) > 20:
                plot_points.append(clean_point)
        
        # Ensure we have exactly 5 plot points
        if len(plot_points) < 5:
            fallback_points = [
                "The story begins with an intriguing hook that draws readers in.",
                "A pivotal event changes everything and sets the main conflict in motion.",
                "Challenges and obstacles test the characters' resolve and growth.",
                "The climax brings all conflicts to a head in an intense confrontation.",
                "The resolution ties up loose ends and shows character transformation."
            ]
            plot_points.extend(fallback_points[len(plot_points):])
        
        return plot_points[:5]

    # Scene Variant Database Operations
    def create_scene_with_variant(
        self, 
        db: Session,
        story_id: int, 
        sequence_number: int, 
        content: str,
        title: str = None,
        custom_prompt: str = None,
        choices: List[Dict[str, Any]] = None,
        generation_method: str = "auto"
    ) -> Tuple[Any, Any]:
        """Create a new scene with its first variant"""
        from ...models import Scene, SceneVariant, SceneChoice, StoryFlow
        
        # Check if a scene already exists for this sequence in this story
        existing_flow = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.sequence_number == sequence_number
        ).first()
        
        if existing_flow:
            # Return the existing scene and variant instead of creating duplicates
            existing_scene = db.query(Scene).filter(Scene.id == existing_flow.scene_id).first()
            existing_variant = db.query(SceneVariant).filter(SceneVariant.id == existing_flow.scene_variant_id).first()
            logger.warning(f"Scene already exists for story {story_id} sequence {sequence_number}, returning existing scene {existing_scene.id}")
            return existing_scene, existing_variant
        
        # Create the logical scene
        scene = Scene(
            story_id=story_id,
            sequence_number=sequence_number,
            title=title or f"Scene {sequence_number}",
        )
        db.add(scene)
        db.flush()  # Get the scene ID
        
        # Create the first variant
        variant = SceneVariant(
            scene_id=scene.id,
            variant_number=1,
            is_original=True,
            content=content,
            title=title,
            original_content=content,
            generation_prompt=custom_prompt,
            generation_method=generation_method
        )
        db.add(variant)
        db.flush()  # Get the variant ID
        
        # Create choices if provided
        if choices:
            for choice_data in choices:
                choice = SceneChoice(
                    scene_id=scene.id,
                    scene_variant_id=variant.id,
                    choice_text=choice_data.get('text', ''),
                    choice_order=choice_data.get('order', 0),
                    choice_description=choice_data.get('description')
                )
                db.add(choice)
        
        # Update story flow
        self._update_story_flow(db, story_id, sequence_number, scene.id, variant.id)
        
        db.commit()
        logger.info(f"Successfully created scene {scene.id} with variant {variant.id} at sequence {sequence_number}")
        return scene, variant

    async def regenerate_scene_variant(
        self, 
        db: Session,
        scene_id: int, 
        custom_prompt: str = None,
        user_id: int = None,
        user_settings: dict = None
    ) -> Any:
        """Create a new variant for an existing scene"""
        from ...models import Scene, SceneVariant, Story
        from ..context_manager import ContextManager
        
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            raise ValueError(f"Scene {scene_id} not found")
        
        # Get the next variant number
        max_variant = db.query(SceneVariant.variant_number)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(desc(SceneVariant.variant_number))\
            .first()
        
        next_variant_number = (max_variant[0] if max_variant else 0) + 1
        
        # Get story for context
        story = db.query(Story).filter(Story.id == scene.story_id).first()
        if not story:
            raise ValueError(f"Story {scene.story_id} not found")
        
        # Build context using ContextManager
        context_manager = ContextManager(user_settings=user_settings or {})
        context = await context_manager.build_scene_generation_context(
            story.id, db, custom_prompt=custom_prompt
        )
        
        # Generate new content using the original scene as base
        original_variant = db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id, SceneVariant.is_original == True)\
            .first()
        
        if original_variant:
            # Generate variant based on original
            new_content = await self.generate_scene_variants(
                original_scene=original_variant.content,
                context=context,
                user_id=user_id,
                user_settings=user_settings or {}
            )
        else:
            # Generate new scene if no original exists
            new_content = await self.generate_scene(
                context=context,
                user_id=user_id,
                user_settings=user_settings or {}
            )
        
        # Create the new variant
        variant = SceneVariant(
            scene_id=scene_id,
            variant_number=next_variant_number,
            is_original=False,
            content=new_content,
            title=scene.title,
            original_content=original_variant.content if original_variant else new_content,
            generation_prompt=custom_prompt,
            generation_method="regeneration"
        )
        
        db.add(variant)
        db.commit()
        
        logger.info(f"Successfully created variant {variant.id} (#{next_variant_number}) for scene {scene_id}")
        return variant

    def switch_to_variant(self, db: Session, story_id: int, scene_id: int, variant_id: int) -> bool:
        """Switch the active variant for a scene in the story flow"""
        from ...models import StoryFlow, SceneVariant
        
        # Verify the variant exists
        variant = db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
        if not variant or variant.scene_id != scene_id:
            return False
        
        # Update story flow to use this variant
        flow_entry = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.scene_id == scene_id
        ).first()
        
        if flow_entry:
            flow_entry.variant_id = variant_id
            db.commit()
            logger.info(f"Switched to variant {variant_id} for scene {scene_id} in story {story_id}")
            return True
        
        return False

    def get_scene_variants(self, db: Session, scene_id: int) -> List[Any]:
        """Get all variants for a scene"""
        from ...models import SceneVariant
        
        return db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(SceneVariant.variant_number)\
            .all()

    def get_active_story_flow(self, db: Session, story_id: int) -> List[Dict[str, Any]]:
        """Get the active story flow with scene variants"""
        from ...models import StoryFlow, Scene, SceneVariant, SceneChoice
        
        # Get the story flow ordered by sequence
        flow_entries = db.query(StoryFlow)\
            .filter(StoryFlow.story_id == story_id)\
            .order_by(StoryFlow.sequence_number)\
            .all()
        
        result = []
        for flow_entry in flow_entries:
            # Get the scene
            scene = db.query(Scene).filter(Scene.id == flow_entry.scene_id).first()
            if not scene:
                continue
                
            # Get the active variant
            variant = db.query(SceneVariant).filter(SceneVariant.id == flow_entry.scene_variant_id).first()
            if not variant:
                continue
                
            # Get choices for this variant
            choices = db.query(SceneChoice)\
                .filter(SceneChoice.scene_variant_id == variant.id)\
                .order_by(SceneChoice.choice_order)\
                .all()
            
            # Check if there are multiple variants for this scene
            variant_count = db.query(SceneVariant)\
                .filter(SceneVariant.scene_id == scene.id)\
                .count()
            
            result.append({
                'scene_id': scene.id,
                'chapter_id': scene.chapter_id,  # Add chapter_id for frontend filtering
                'sequence_number': flow_entry.sequence_number,
                'title': variant.title or scene.title,
                'content': variant.content,
                'location': variant.location or '',
                'characters_present': [],  # Could be enhanced to get actual characters
                'variant': {
                    'id': variant.id,
                    'variant_number': variant.variant_number,
                    'is_original': variant.is_original,
                    'content': variant.content,
                    'title': variant.title,
                    'generation_method': variant.generation_method
                },
                'variant_id': variant.id,
                'variant_number': variant.variant_number,
                'is_original': variant.is_original,
                'has_multiple_variants': variant_count > 1,
                'choices': [
                    {
                        'id': choice.id,
                        'text': choice.choice_text,
                        'description': choice.choice_description,
                        'order': choice.choice_order
                    } for choice in choices
                ]
            })
        
        return result

    def _update_story_flow(self, db: Session, story_id: int, sequence_number: int, scene_id: int, variant_id: int):
        """Update or create story flow entry"""
        from ...models import StoryFlow
        
        # Check if flow entry already exists for this sequence
        existing_flow = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.sequence_number == sequence_number
        ).first()
        
        if existing_flow:
            # Update existing entry
            existing_flow.scene_id = scene_id
            existing_flow.scene_variant_id = variant_id
        else:
            # Create new flow entry
            flow_entry = StoryFlow(
                story_id=story_id,
                sequence_number=sequence_number,
                scene_id=scene_id,
                scene_variant_id=variant_id
            )
            db.add(flow_entry)

    def delete_scenes_from_sequence(self, db: Session, story_id: int, sequence_number: int) -> bool:
        """Delete all scenes from a given sequence number onwards"""
        try:
            from ...models import StoryFlow, Scene
            
            # First, delete all StoryFlow entries for this story with sequence_number >= sequence_number
            story_flows_deleted = db.query(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.sequence_number >= sequence_number
            ).delete()
            
            # Get scenes to delete (don't use bulk delete to ensure cascades work)
            scenes_to_delete = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= sequence_number
            ).all()
            
            # Delete each scene individually to trigger cascade relationships
            scenes_deleted = 0
            for scene in scenes_to_delete:
                db.delete(scene)
                scenes_deleted += 1
            
            # Commit the transaction
            db.commit()
            
            logger.info(f"Deleted {story_flows_deleted} story flows and {scenes_deleted} scenes from sequence {sequence_number} onwards for story {story_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete scenes from sequence {sequence_number} for story {story_id}: {e}")
            db.rollback()
            return False
