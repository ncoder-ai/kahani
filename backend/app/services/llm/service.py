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
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import httpx
import time
import uuid

from .client import LLMClient
from .prompts import prompt_manager
from .templates import TextCompletionTemplateManager
from .thinking_parser import ThinkingTagParser
from ...config import settings

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
    
    def _get_prompt_debug_path(self, filename: str) -> str:
        """Get the path for prompt debug files, handling both Docker and bare-metal environments.
        
        Args:
            filename: Name of the debug file (e.g., 'prompt_sent.json', 'prompt_choice_sent.json')
        
        Returns:
            Full path to the debug file
        """
        # Check if we're in Docker (working directory is /app)
        if os.path.exists("/app") and os.getcwd().startswith("/app"):
            # Docker: use mounted logs directory
            return f"/app/root_logs/{filename}"
        else:
            # Bare-metal: use logs directory relative to project root
            # Go up from service.py: backend/app/services/llm/service.py 
            # -> backend/app/services/llm -> backend/app/services -> backend/app -> backend -> project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
            logs_dir = os.path.join(project_root, "logs")
            os.makedirs(logs_dir, exist_ok=True)  # Ensure directory exists
            return os.path.join(logs_dir, filename)
    
    async def generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False,
        skip_nsfw_filter: bool = False
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
                temperature=temperature,
                skip_nsfw_filter=skip_nsfw_filter
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
                temperature=temperature,
                skip_nsfw_filter=skip_nsfw_filter
            )
    
    # Remove redundant generate_stream method - use _generate_stream directly
    
    def _log_raw_response(self, response: Any, operation_name: str = "LLM Generation") -> None:
        """
        Log full raw LLM response object to file (only for scene generation debugging)
        
        Args:
            response: The LLM response object
            operation_name: Name of the operation (for logging context)
        """
        if not settings.prompt_debug:
            return
        
        try:
            import json
            backend_dir = Path(__file__).parent.parent.parent
            raw_response_file = backend_dir / "Raw-Response.txt"
            with open(raw_response_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"RAW LLM RESPONSE OBJECT (FULL - BEFORE PARSING)\n")
                f.write(f"Operation: {operation_name}\n")
                f.write("=" * 80 + "\n\n")
                # Convert response object to dict for JSON serialization
                response_dict = {
                    "id": getattr(response, 'id', None),
                    "model": getattr(response, 'model', None),
                    "created": getattr(response, 'created', None),
                    "object": getattr(response, 'object', None),
                    "choices": [
                        {
                            "index": getattr(choice, 'index', None),
                            "message": {
                                "role": getattr(choice.message, 'role', None) if hasattr(choice, 'message') else None,
                                "content": getattr(choice.message, 'content', None) if hasattr(choice, 'message') else None,
                            } if hasattr(choice, 'message') else None,
                            "finish_reason": getattr(choice, 'finish_reason', None),
                        }
                        for choice in getattr(response, 'choices', [])
                    ],
                    "usage": {
                        "prompt_tokens": getattr(response.usage, 'prompt_tokens', None) if hasattr(response, 'usage') else None,
                        "completion_tokens": getattr(response.usage, 'completion_tokens', None) if hasattr(response, 'usage') else None,
                        "total_tokens": getattr(response.usage, 'total_tokens', None) if hasattr(response, 'usage') else None,
                    } if hasattr(response, 'usage') else None,
                }
                f.write(json.dumps(response_dict, indent=2, ensure_ascii=False))
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("PARSED CONTENT (what we extract):\n")
                f.write("=" * 80 + "\n\n")
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    f.write(content)
                f.write("\n\n" + "=" * 80 + "\n")
        except Exception as e:
            logger.error(f"Failed to write full raw response to file: {e}")
    
    async def _generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> str:
        """Internal method for non-streaming generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check completion mode and branch accordingly
        completion_mode = client.completion_mode
        logger.debug(f"User {user_id} generation mode: {completion_mode} (from client.completion_mode={client.completion_mode})")
        if completion_mode == "text":
            logger.debug(f"Using text completion API for user {user_id}")
            return await self._generate_text_completion(
                prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            )
        
        logger.debug(f"Using chat completion API for user {user_id}")
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        messages = []
        if system_prompt and system_prompt.strip():
            # Inject NSFW filter if user doesn't have NSFW permissions (unless explicitly skipped)
            if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.debug(f"NSFW filter injected for user {user_id}")
            
            messages.append({"role": "system", "content": system_prompt.strip()})
        elif not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            messages.append({"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"NSFW filter injected (no system prompt) for user {user_id}")
        
        # Ensure prompt is valid string
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        
        messages.append({"role": "user", "content": prompt.strip()})
        
        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value
        
        # Get prompts for file logging (only if prompt_debug is enabled)
        system_prompt_log = next((msg["content"] for msg in messages if msg.get("role") == "system"), "")
        user_prompt_log = next((msg["content"] for msg in messages if msg.get("role") == "user"), "")
        
        try:
            response = await acompletion(**gen_params)
            
            # Check finish_reason for truncation
            if hasattr(response, 'choices') and len(response.choices) > 0:
                finish_reason = getattr(response.choices[0], 'finish_reason', None)
                if finish_reason == 'length':
                    logger.warning(f"[TRUNCATION] Response truncated due to token limit! max_tokens={max_tokens}")
                    logger.warning(f"[TRUNCATION] Consider increasing max_tokens or reducing prompt size")
                elif finish_reason:
                    logger.debug(f"[GENERATION] Finish reason: {finish_reason}")
            
            content = response.choices[0].message.content
            
            # Check for reasoning_content from LiteLLM (supported by DeepSeek, Anthropic, OpenRouter, etc.)
            reasoning_content = getattr(response.choices[0].message, 'reasoning_content', None)
            if reasoning_content:
                logger.info(f"[REASONING] Captured reasoning content ({len(reasoning_content)} chars)")
                # For non-streaming, we return content only but log the reasoning
                # The streaming endpoint handles reasoning display
            
            # If content is empty but reasoning exists, warn about token limits
            if not content and reasoning_content:
                logger.warning("[REASONING] Content empty but reasoning present - model may need more max_tokens")
            
            return content
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LiteLLM generation failed for user {user_id}: {error_msg}")
            
            # Log timeout information
            timeout_used = gen_params.get('timeout', 'not set (using LiteLLM default ~60s)')
            logger.warning(f"Timeout used: {timeout_used}, max_tokens: {gen_params.get('max_tokens')}")
            
            # Try to capture partial response
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                partial_response = e.response.text
                logger.warning(f"Partial response received (length: {len(partial_response)} chars):\n{partial_response[:1000]}")
            
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
                    return await self._direct_http_fallback(client, messages, max_tokens, temperature, False, user_settings)
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
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> str:
        """Internal method for text completion generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        # Inject NSFW filter into system prompt if needed (unless explicitly skipped)
        if system_prompt and system_prompt.strip():
            if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.debug(f"NSFW filter injected for user {user_id}")
        elif not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            system_prompt = get_nsfw_prevention_prompt()
            logger.debug(f"NSFW filter injected (no system prompt) for user {user_id}")
        
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
        
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value
        
        # Log complete prompt being sent to LLM
        logger.debug("=" * 80)
        logger.debug("COMPLETE PROMPT BEING SENT TO LLM (TEXT COMPLETION)")
        logger.debug("=" * 80)
        logger.debug(f"SYSTEM PROMPT:\n{system_prompt or '(none)'}")
        logger.debug("-" * 80)
        logger.debug(f"USER PROMPT:\n{prompt.strip()}")
        logger.debug("-" * 80)
        logger.debug(f"RENDERED PROMPT (FULL):\n{rendered_prompt}")
        logger.debug("-" * 80)
        logger.info(f"GENERATION PARAMETERS: max_tokens={gen_params.get('max_tokens')}, temperature={gen_params.get('temperature')}, model={client.model_string}")
        logger.info("=" * 80)
        
        # For OpenAI-compatible providers (LM Studio, TabbyAPI, KoboldCpp), skip LiteLLM
        # and use direct HTTP to ensure correct /v1/completions endpoint is called
        if client.api_type in ["lm_studio", "openai_compatible", "openai-compatible", "tabbyapi", "koboldcpp"]:
            logger.info(f"Using direct HTTP for text completion with {client.api_type}")
            return await self._direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, False, user_settings)
        
        # For other providers, try LiteLLM
        try:
            logger.info(f"Text completion with {client.model_string} for user {user_id}")
            logger.debug(f"Calling text_completion with model={gen_params['model']}, prompt_length={len(gen_params['prompt'])}")
            
            # Use litellm.text_completion for text completion (synchronous, run in thread)
            from litellm import text_completion
            import asyncio
            
            response = await asyncio.to_thread(text_completion, **gen_params)
            
            # Check finish_reason for truncation
            if hasattr(response, 'choices') and len(response.choices) > 0:
                finish_reason = getattr(response.choices[0], 'finish_reason', None)
                if finish_reason == 'length':
                    logger.warning(f"[TRUNCATION] Text completion truncated due to token limit! max_tokens={max_tokens}")
                    logger.warning(f"[TRUNCATION] Consider increasing max_tokens or reducing prompt size")
                elif finish_reason:
                    logger.debug(f"[TEXT COMPLETION] Finish reason: {finish_reason}")
            
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
            logger.error(f"Text completion failed for user {user_id}: {error_msg}")
            raise ValueError(f"Text completion failed: {error_msg}")
    
    async def _direct_http_fallback(self, client, messages, max_tokens, temperature, stream, user_settings: Optional[Dict[str, Any]] = None):
        """Direct HTTP fallback for LM Studio when LiteLLM fails"""
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_total = user_timeout if user_timeout is not None else settings.llm_timeout_total
        
        # Configure timeout from settings
        timeout = httpx.Timeout(
            timeout_total,
            connect=settings.llm_timeout_connect,
            read=settings.llm_timeout_read,
            write=settings.llm_timeout_write
        )
        max_retries = settings.llm_max_retries
        base_delay = settings.llm_retry_base_delay
        
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
        
        # Determine the correct endpoint URL
        if client.api_url.endswith("/v1"):
            endpoint_url = f"{client.api_url}/chat/completions"
        else:
            endpoint_url = f"{client.api_url}/v1/chat/completions"
        
        if stream:
            # For streaming, retry logic must be inside the generator
            async def stream_generator():
                last_error = None
                for attempt in range(max_retries):
                    try:
                        async with httpx.AsyncClient(timeout=timeout) as http_client:
                            async with http_client.stream(
                                "POST",
                                endpoint_url,
                                json=payload,
                                headers=headers
                            ) as response:
                                response.raise_for_status()
                                async for line in response.aiter_lines():
                                    if line.startswith("data: "):
                                        data = line[6:]  # Remove "data: " prefix
                                        if data.strip() == "[DONE]":
                                            break
                                        try:
                                            chunk = json.loads(data)
                                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                                delta = chunk["choices"][0].get("delta", {})
                                                content = delta.get("content", "")
                                                if content:
                                                    yield content
                                        except json.JSONDecodeError:
                                            continue
                                return  # Success, exit retry loop
                    except httpx.HTTPStatusError as e:
                        # Check if it's a 504 Gateway Timeout
                        if e.response.status_code == 504:
                            last_error = e
                            if attempt < max_retries - 1:
                                delay = base_delay * (2 ** attempt)  # Exponential backoff
                                logger.warning(
                                    f"504 Gateway Timeout on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                                    f"Retrying in {delay:.1f}s..."
                                )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                logger.error(f"504 Gateway Timeout after {max_retries} attempts: {e}")
                                raise ValueError(f"LLM generation failed: Gateway timeout after {max_retries} attempts. The API may be overloaded or slow.")
                        else:
                            # For other HTTP errors, don't retry
                            logger.error(f"HTTP error {e.response.status_code} from {endpoint_url}: {e}")
                            raise ValueError(f"LLM generation failed: HTTP {e.response.status_code}")
                    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(
                                f"Network/timeout error on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                                f"Retrying in {delay:.1f}s... Error: {str(e)}"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"Network/timeout error after {max_retries} attempts: {e}")
                            raise ValueError(f"LLM generation failed: {str(e)}")
                    except Exception as e:
                        # For other exceptions, don't retry
                        logger.error(f"Direct HTTP fallback failed: {e}", exc_info=True)
                        raise ValueError(f"LLM generation failed: {str(e)}")
                
                # If we exhausted all retries
                if last_error:
                    raise ValueError(f"LLM generation failed after {max_retries} attempts: {str(last_error)}")
                else:
                    raise ValueError("LLM generation failed: Unknown error")
            return stream_generator()
        else:
            # Handle non-streaming response with retry logic
            last_error = None
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as http_client:
                        response = await http_client.post(
                            endpoint_url,
                            json=payload,
                            headers=headers
                        )
                        response.raise_for_status()
                        data = response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            return data["choices"][0]["message"]["content"]
                        else:
                            raise ValueError("Invalid response format from LM Studio")
                            
                except httpx.HTTPStatusError as e:
                    # Check if it's a 504 Gateway Timeout
                    if e.response.status_code == 504:
                        last_error = e
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(
                                f"504 Gateway Timeout on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                                f"Retrying in {delay:.1f}s..."
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"504 Gateway Timeout after {max_retries} attempts: {e}")
                            raise ValueError(f"LLM generation failed: Gateway timeout after {max_retries} attempts. The API may be overloaded or slow.")
                    else:
                        # For other HTTP errors, don't retry
                        logger.error(f"HTTP error {e.response.status_code} from {endpoint_url}: {e}")
                        raise ValueError(f"LLM generation failed: HTTP {e.response.status_code}")
                        
                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"Network/timeout error on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                            f"Retrying in {delay:.1f}s... Error: {str(e)}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"Network/timeout error after {max_retries} attempts: {e}")
                        raise ValueError(f"LLM generation failed: {str(e)}")
                        
                except Exception as e:
                    # For other exceptions, don't retry
                    logger.error(f"Direct HTTP fallback failed: {e}", exc_info=True)
                    raise ValueError(f"LLM generation failed: {str(e)}")
            
            # If we exhausted all retries
            if last_error:
                raise ValueError(f"LLM generation failed after {max_retries} attempts: {str(last_error)}")
            else:
                raise ValueError("LLM generation failed: Unknown error")
    
    async def _direct_http_text_completion_fallback(self, client, prompt, max_tokens, temperature, stream, user_settings: Optional[Dict[str, Any]] = None):
        """Direct HTTP call to /v1/completions endpoint for text completion"""
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_total = user_timeout if user_timeout is not None else settings.llm_timeout_total
        
        # Configure timeout from settings
        timeout = httpx.Timeout(
            timeout_total,
            connect=settings.llm_timeout_connect,
            read=settings.llm_timeout_read,
            write=settings.llm_timeout_write
        )
        max_retries = settings.llm_max_retries
        base_delay = settings.llm_retry_base_delay
        
        logger.info(f"Direct HTTP text completion: stream={stream}, model={client.model_name}")
        
        payload = {
            "model": client.model_name,  # Use the actual model name, not the prefixed one
            "prompt": prompt,
            "max_tokens": max_tokens or client.max_tokens,
            "temperature": temperature if temperature is not None else client.temperature,
            "stream": stream
        }
        
        # Add stop sequences based on template
        if client.text_completion_template:
            # Parse template to get EOS token
            try:
                template = json.loads(client.text_completion_template)
                eos_token = template.get("eos_token")
                if eos_token:
                    payload["stop"] = [eos_token]
            except:
                pass
        elif client.text_completion_preset:
            # Get preset template EOS token
            from .templates import TextCompletionTemplateManager
            preset_template = TextCompletionTemplateManager.get_preset_template(client.text_completion_preset)
            if preset_template and preset_template.get("eos_token"):
                payload["stop"] = [preset_template["eos_token"]]
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if client.api_key:
            headers["Authorization"] = f"Bearer {client.api_key}"
        
        # Determine the correct endpoint URL for text completion
        if client.api_url.endswith("/v1"):
            endpoint_url = f"{client.api_url}/completions"
        else:
            endpoint_url = f"{client.api_url}/v1/completions"
        
        logger.info(f"Calling text completion endpoint: {endpoint_url}")
        logger.debug(f"Payload: model={client.model_name}, prompt_length={len(prompt)}, stream={stream}, stop={payload.get('stop')}")
        
        if stream:
            # For streaming, retry logic must be inside the generator
            async def stream_generator():
                last_error = None
                for attempt in range(max_retries):
                    try:
                        async with httpx.AsyncClient(timeout=timeout) as http_client:
                            async with http_client.stream(
                                "POST",
                                endpoint_url,
                                json=payload,
                                headers=headers
                            ) as response:
                                response.raise_for_status()
                                async for line in response.aiter_lines():
                                    if line.startswith("data: "):
                                        data = line[6:]  # Remove "data: " prefix
                                        if data.strip() == "[DONE]":
                                            break
                                        try:
                                            chunk = json.loads(data)
                                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                                # Text completion uses 'text' field, not 'delta'
                                                text = chunk["choices"][0].get("text", "")
                                                if text:
                                                    # Strip thinking tags from each chunk
                                                    # Preserve whitespace for streaming chunks to maintain word boundaries
                                                    cleaned_text = ThinkingTagParser.strip_thinking_tags(text, preserve_whitespace=True)
                                                    if cleaned_text:
                                                        yield cleaned_text
                                        except json.JSONDecodeError:
                                            continue
                                return  # Success, exit retry loop
                    except httpx.HTTPStatusError as e:
                        # Check if it's a 504 Gateway Timeout
                        if e.response.status_code == 504:
                            last_error = e
                            if attempt < max_retries - 1:
                                delay = base_delay * (2 ** attempt)  # Exponential backoff
                                logger.warning(
                                    f"504 Gateway Timeout on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                                    f"Retrying in {delay:.1f}s..."
                                )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                logger.error(f"504 Gateway Timeout after {max_retries} attempts: {e}")
                                raise ValueError(f"Text completion failed: Gateway timeout after {max_retries} attempts. The API may be overloaded or slow.")
                        else:
                            # For other HTTP errors, don't retry
                            logger.error(f"HTTP error {e.response.status_code} from {endpoint_url}: {e}")
                            raise ValueError(f"Text completion failed: HTTP {e.response.status_code}")
                    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(
                                f"Network/timeout error on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                                f"Retrying in {delay:.1f}s... Error: {str(e)}"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"Network/timeout error after {max_retries} attempts: {e}")
                            raise ValueError(f"Text completion failed: {str(e)}")
                    except Exception as e:
                        # For other exceptions, don't retry
                        logger.error(f"Direct HTTP text completion fallback failed: {e}", exc_info=True)
                        raise ValueError(f"Text completion failed: {str(e)}")
                
                # If we exhausted all retries
                if last_error:
                    raise ValueError(f"Text completion failed after {max_retries} attempts: {str(last_error)}")
                else:
                    raise ValueError("Text completion failed: Unknown error")
            return stream_generator()
        else:
            # Handle non-streaming response with retry logic
            last_error = None
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as http_client:
                        response = await http_client.post(
                            endpoint_url,
                            json=payload,
                            headers=headers
                        )
                        response.raise_for_status()
                        data = response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0]["text"]
                            # Strip thinking tags from response
                            return ThinkingTagParser.strip_thinking_tags(content)
                        else:
                            raise ValueError("Invalid response format from text completion endpoint")
                            
                except httpx.HTTPStatusError as e:
                    # Check if it's a 504 Gateway Timeout
                    if e.response.status_code == 504:
                        last_error = e
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(
                                f"504 Gateway Timeout on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                                f"Retrying in {delay:.1f}s..."
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"504 Gateway Timeout after {max_retries} attempts: {e}")
                            raise ValueError(f"Text completion failed: Gateway timeout after {max_retries} attempts. The API may be overloaded or slow.")
                    else:
                        # For other HTTP errors, don't retry
                        logger.error(f"HTTP error {e.response.status_code} from {endpoint_url}: {e}")
                        raise ValueError(f"Text completion failed: HTTP {e.response.status_code}")
                        
                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"Network/timeout error on attempt {attempt + 1}/{max_retries} for {endpoint_url}. "
                            f"Retrying in {delay:.1f}s... Error: {str(e)}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"Network/timeout error after {max_retries} attempts: {e}")
                        raise ValueError(f"Text completion failed: {str(e)}")
                        
                except Exception as e:
                    # For other exceptions, don't retry
                    logger.error(f"Direct HTTP text completion fallback failed: {e}", exc_info=True)
                    raise ValueError(f"Text completion failed: {str(e)}")
            
            # If we exhausted all retries
            if last_error:
                raise ValueError(f"Text completion failed after {max_retries} attempts: {str(last_error)}")
            else:
                raise ValueError("Text completion failed: Unknown error")
    
    async def _generate_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check completion mode and branch accordingly
        completion_mode = client.completion_mode
        logger.debug(f"User {user_id} streaming generation mode: {completion_mode} (from client.completion_mode={client.completion_mode})")
        if completion_mode == "text":
            logger.debug(f"Using text completion streaming API for user {user_id}")
            async for chunk in self._generate_text_completion_stream(
                prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            ):
                yield chunk
            return
        
        logger.debug(f"Using chat completion streaming API for user {user_id}")
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        messages = []
        if system_prompt and system_prompt.strip():
            # Inject NSFW filter if user doesn't have NSFW permissions (unless explicitly skipped)
            if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.debug(f"NSFW filter injected for streaming user {user_id}")
            
            messages.append({"role": "system", "content": system_prompt.strip()})
        elif not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            messages.append({"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"NSFW filter injected (no system prompt) for streaming user {user_id}")
        
        # Ensure prompt is valid string
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        
        messages.append({"role": "user", "content": prompt.strip()})
        
        # Get streaming parameters
        gen_params = client.get_streaming_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value
        
        # Get prompts for file logging (only if prompt_debug is enabled)
        system_prompt_log = next((msg["content"] for msg in messages if msg.get("role") == "system"), "")
        user_prompt_log = next((msg["content"] for msg in messages if msg.get("role") == "user"), "")
        
        # Write prompt to file for streaming generation (only if prompt_debug is enabled)
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
                debug_data = {
                    "messages": gen_params["messages"],
                    "generation_parameters": {
                        "max_tokens": gen_params.get('max_tokens'),
                        "temperature": gen_params.get('temperature'),
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                pass  # Silently fail if file writing fails
        
        try:
            response = await acompletion(**gen_params)
            
            # Track if we've seen reasoning content (for logging)
            has_reasoning = False
            reasoning_chars = 0
            content_chars = 0
            chunk_count = 0
            
            async for chunk in response:
                chunk_count += 1
                
                # Check for reasoning_content (LiteLLM's standardized field for all providers)
                # This works for OpenRouter, Anthropic, DeepSeek, etc. when using proper LiteLLM params
                delta = chunk.choices[0].delta
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    has_reasoning = True
                    reasoning_chars += len(delta.reasoning_content)
                    # Yield reasoning with special prefix for frontend to detect
                    yield f"__THINKING__:{delta.reasoning_content}"
                
                # Regular content
                if delta.content:
                    content_chars += len(delta.content)
                    yield delta.content
            
            # Log summary of what was received
            logger.info(f"[STREAMING COMPLETE] chunks={chunk_count}, content_chars={content_chars}, reasoning_chars={reasoning_chars}")
            if chunk_count > 0 and content_chars == 0:
                logger.warning(f"[STREAMING] Received {chunk_count} chunks but no content! Model may need higher max_tokens or reasoning disabled.")
            if has_reasoning:
                logger.info(f"[REASONING] Streamed {reasoning_chars} chars of reasoning content")
                    
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
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming text completion generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        # Check if NSFW filter should be injected
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        logger.debug(f"NSFW check for user {user_id} (text completion streaming): user_settings.get('allow_nsfw')={user_settings.get('allow_nsfw') if user_settings else None}, user_allow_nsfw={user_allow_nsfw}, type={type(user_allow_nsfw)}")
        
        # Inject NSFW filter into system prompt if needed (unless explicitly skipped)
        if system_prompt and system_prompt.strip():
            if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
                system_prompt = system_prompt.strip() + "\n\n" + get_nsfw_prevention_prompt()
                logger.debug(f"NSFW filter injected for streaming user {user_id}")
        elif not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # No system prompt provided, but we need to inject NSFW filter
            system_prompt = get_nsfw_prevention_prompt()
            logger.debug(f"NSFW filter injected (no system prompt) for streaming user {user_id}")
        
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
        
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value
        
        # Log complete prompt being sent to LLM
        logger.debug("=" * 80)
        logger.debug("COMPLETE PROMPT BEING SENT TO LLM (TEXT COMPLETION STREAMING)")
        logger.debug("=" * 80)
        logger.debug(f"SYSTEM PROMPT:\n{system_prompt or '(none)'}")
        logger.debug("-" * 80)
        logger.debug(f"USER PROMPT:\n{prompt.strip()}")
        logger.debug("-" * 80)
        logger.debug(f"RENDERED PROMPT (FULL):\n{rendered_prompt}")
        logger.info("-" * 80)
        logger.info(f"GENERATION PARAMETERS: max_tokens={gen_params.get('max_tokens')}, temperature={gen_params.get('temperature')}, model={client.model_string}")
        logger.info("=" * 80)
        
        # Write prompt to file for text completion streaming generation (only if prompt_debug is enabled)
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
                debug_data = {
                    "system_prompt": system_prompt or None,
                    "user_prompt": prompt.strip(),
                    "rendered_prompt": rendered_prompt,
                    "generation_parameters": {
                        "max_tokens": gen_params.get('max_tokens'),
                        "temperature": gen_params.get('temperature'),
                        "model": client.model_string,
                        "prompt": gen_params.get('prompt', '')
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.debug(f"Failed to write prompt to file: {e}")
        
        # For OpenAI-compatible providers (LM Studio, TabbyAPI, KoboldCpp), skip LiteLLM
        # and use direct HTTP to ensure correct /v1/completions endpoint is called
        if client.api_type in ["lm_studio", "openai_compatible", "openai-compatible", "tabbyapi", "koboldcpp"]:
            logger.info(f"Using direct HTTP streaming for text completion with {client.api_type}")
            async for chunk in await self._direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, True, user_settings):
                yield chunk
            return
        
        # For other providers, try LiteLLM
        try:
            logger.info(f"Streaming text completion with {client.model_string} for user {user_id}")
            logger.debug(f"Calling text_completion (streaming) with model={gen_params['model']}, prompt_length={len(gen_params['prompt'])}")
            
            # Use litellm.text_completion for text completion
            # text_completion returns a synchronous generator when stream=True
            from litellm import text_completion
            import asyncio
            
            # Call text_completion (it returns a synchronous generator for streaming)
            response_stream = text_completion(**gen_params)
            
            # Buffer for accumulating chunks to detect thinking tags
            buffer = ""
            thinking_detected = False
            
            # Convert synchronous generator to async by yielding in executor
            for chunk in response_stream:
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
                        # Preserve whitespace for streaming chunks to maintain word boundaries
                        cleaned_buffer = ThinkingTagParser.strip_thinking_tags(buffer, preserve_whitespace=True)
                        
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
                
                # Allow other tasks to run
                await asyncio.sleep(0)
            
            # Yield any remaining buffer
            if buffer:
                # Preserve whitespace for streaming chunks to maintain word boundaries
                cleaned_buffer = ThinkingTagParser.strip_thinking_tags(buffer, preserve_whitespace=True)
                if cleaned_buffer:
                    yield cleaned_buffer
                    
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LiteLLM streaming text completion failed for user {user_id}: {error_msg}")
            logger.error(f"Streaming text completion failed for user {user_id}: {error_msg}")
            raise ValueError(f"Streaming text completion failed: {error_msg}")
            
            # Fallback to direct HTTP for LM Studio and TabbyAPI
            if client.api_type in ["lm_studio", "openai_compatible"]:
                logger.info(f"Attempting direct HTTP streaming text completion fallback for {client.api_type}")
                async for chunk in await self._direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, True, user_settings):
                    yield chunk
            else:
                logger.error(f"Streaming text completion failed for user {user_id}: {error_msg}")
                raise ValueError(f"Streaming text completion failed: {str(e)}")
    
    def _clean_scene_content(self, content: str) -> str:
        """
        Comprehensive cleaning of LLM-generated scene content.
        Removes various junk patterns that LLMs commonly add to scenes.
        Uses multi-pass cleaning to catch nested patterns.
        """
        if not content:
            return content
        
        original_content = content
        
        # Multi-pass cleaning to catch nested patterns (max 3 passes)
        for pass_num in range(3):
            old_content = content
            
            # === AGGRESSIVE MARKDOWN HEADER REMOVAL ===
            # Remove ANY line that starts with markdown-style headers
            # These are NEVER legitimate prose - always LLM junk
            # Must come FIRST before other patterns
            # Exception: Preserve ###CHOICES### marker (used for choice generation)
            
            # Remove lines starting with 2+ hash marks (##, ###, ####, etc.)
            # But NOT ###CHOICES### (negative lookahead)
            content = re.sub(r'^#{2,}(?!#*CHOICES###)[^\n]*\n?', '', content, flags=re.MULTILINE | re.IGNORECASE).strip()
            
            # Remove lines starting with 2+ equals signs (==, ===, ====, etc.)
            content = re.sub(r'^={2,}[^\n]*\n?', '', content, flags=re.MULTILINE).strip()
            
            # Remove lines starting with 2+ dashes (--, ---, ----, etc.)
            content = re.sub(r'^-{2,}[^\n]*\n?', '', content, flags=re.MULTILINE).strip()
            
            # Remove lines starting with 2+ asterisks (**, ***, ****, etc.)
            # Preserves single * for thoughts
            content = re.sub(r'^\*{2,}[^\n]*\n?', '', content, flags=re.MULTILINE).strip()
            
            # === HEADER/PREFIX PATTERNS (at start of content) ===
            # Order matters: most specific patterns first, most general last
            
            # Markdown scene headers with numbers: "### SCENE 113 ###", "## SCENE 7 ##"
            # Must come BEFORE generic scene markers to catch specific pattern
            content = re.sub(r'^#{1,6}\s*SCENE\s+\d+\s*#{1,6}\s*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # Scene numbers and titles: "Scene 7:", "Scene 7: The Escape", "### Scene 7 ###", "SCENE 1"
            content = re.sub(r'^#{1,6}\s*Scene\s+\d+[^#\n]*#{0,6}\s*\n?', '', content, flags=re.IGNORECASE).strip()
            content = re.sub(r'^Scene\s+\d+(?:\s*[:\-]\s*[^\n]*)?\s*\n', '', content, flags=re.IGNORECASE).strip()
            
            # Standalone numbers as titles: "7:", "7. The Beginning"
            content = re.sub(r'^\d+[:.]\s*[A-Z][^.\n]*(\n|$)', '', content).strip()
            
            # Scene response markers: "=== SCENE RESPONSE ==="
            content = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s+RESPONSE\s*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # Scene expansion markers: "### SCENE EXPANSION ###", "=== SCENE EXPANSION ==="
            content = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s*(?:EXPANSION|CONTINUATION|CONTENT|START|BEGIN)[^#=\-\*\n]*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # Regenerated/Revised scene markers: "=== REGENERATED SCENE ===", "### REVISED SCENE ###"
            # Also handles typos like "REGNERATED" and makes "SCENE" word optional
            content = re.sub(r'^[#=\-\*]{2,}\s*(?:REGE?NERATED|REVISED|UPDATED|NEW|REWRITTEN)(?:\s+SCENE)?[^#=\-\*\n]*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # Generic section markers at start: "### SCENE ###", "=== SCENE ==="
            content = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s*\d*\s*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # "Continue scene" prefixes: "Continue scene:", "Continuing the scene:"
            content = re.sub(r'^(?:Continue|Continuing|Continued)\s+(?:the\s+)?scene[:\s]*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # "Here is" prefixes: "Here is the scene:", "Here's the continuation:"
            content = re.sub(r'^Here(?:\'s|\s+is)\s+(?:the\s+)?(?:scene|continuation|next\s+part|story)[:\s]*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # Instruction acknowledgments: "Understood, here's the scene:", "Got it. Here's the scene:"
            content = re.sub(r'^(?:Understood|Got\s+it|Okay|Sure|Certainly)[.,!]?\s*(?:Here(?:\'s|\s+is)[^:]*:)?\s*\n?', '', content, flags=re.IGNORECASE).strip()
            
            # Chapter/Part markers at start: "Chapter 7:", "Part 3:"
            content = re.sub(r'^(?:Chapter|Part)\s+\d+[:\s].*?(\n|$)', '', content, flags=re.IGNORECASE).strip()
            
            # === INSTRUCTION TAGS (can appear anywhere) ===
            
            # Llama-style instruction tags: [/inst], [inst], <<SYS>>, <</SYS>>
            content = re.sub(r'\[/?inst\]', '', content, flags=re.IGNORECASE)
            content = re.sub(r'<<?/?SYS>>?', '', content, flags=re.IGNORECASE)
            
            # Assistant/User role markers that leak through
            content = re.sub(r'^(?:Assistant|AI|Model):\s*', '', content, flags=re.IGNORECASE | re.MULTILINE).strip()
            
            # === TRAILING JUNK PATTERNS ===
            
            # "End of scene" markers: "--- End of Scene ---", "=== END ==="
            content = re.sub(r'\n?[#=\-\*]{2,}\s*(?:END|FIN|THE\s+END)\s*(?:OF\s+SCENE)?[^#=\-\*\n]*[#=\-\*]*\s*$', '', content, flags=re.IGNORECASE).strip()
            
            # "To be continued" markers
            content = re.sub(r'\n?\s*(?:\[|\()?(?:To\s+be\s+continued|TBC|Continued\s+in\s+next\s+scene)(?:\]|\))?\s*\.?\s*$', '', content, flags=re.IGNORECASE).strip()
            
            # Word count annotations: "(Word count: 150)", "[~200 words]"
            content = re.sub(r'\n?\s*(?:\[|\()?\s*(?:~?\s*\d+\s*words?|word\s*count[:\s]*\d+)\s*(?:\]|\))?\s*$', '', content, flags=re.IGNORECASE).strip()
            
            # === EMBEDDED METADATA (anywhere in content) ===
            
            # Scene numbers embedded: "### Scene 113 ###" in middle of text
            content = re.sub(r'\n[#=\-\*]{2,}\s*SCENE\s+\d+\s*[#=\-\*]*\s*\n', '\n', content, flags=re.IGNORECASE)
            
            # Remove multiple consecutive blank lines (normalize to max 2)
            content = re.sub(r'\n{3,}', '\n\n', content)
            
            # Check if any changes were made this pass
            if content == old_content:
                logger.debug(f"[SCENE_CLEAN] Cleaning converged after {pass_num + 1} pass(es)")
                break
        
        # Log if significant cleaning occurred
        if len(original_content) - len(content) > 10:
            removed_preview = original_content[:150].replace('\n', '\\n')
            logger.info(f"[SCENE_CLEAN] Removed {len(original_content) - len(content)} chars. Preview: {removed_preview}")
        
        return content.strip()
    
    def _clean_scene_numbers(self, content: str) -> str:
        """
        Remove scene numbers and LLM junk from generated content.
        This is an alias for _clean_scene_content for backward compatibility.
        """
        return self._clean_scene_content(content)
    
    def _clean_instruction_tags(self, content: str) -> str:
        """Remove instruction tags like [/inst][inst] that may appear in LLM responses"""
        # Remove [/inst] and [inst] tags (with or without closing brackets)
        content = re.sub(r'\[/inst\]\s*\[inst\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[/inst\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[inst\]', '', content, flags=re.IGNORECASE)
        return content.strip()
    
    def _clean_scene_numbers_chunk(self, chunk: str, chars_processed: int = 0) -> str:
        """
        Clean scene numbers and junk from streaming chunks.
        Position-aware: aggressive cleaning only at start of response.
        
        Args:
            chunk: The chunk to clean
            chars_processed: Total characters processed so far (for position awareness)
        """
        if not chunk:
            return chunk
        
        stripped = chunk.strip()
        
        # === POSITION-AWARE MARKDOWN HEADER REMOVAL ===
        # Only apply aggressive ## removal in first ~200 chars (where SCENE junk appears)
        # After that, allow ## patterns through (for ###CHOICES### marker)
        HEADER_REMOVAL_THRESHOLD = 200  # Only strip ## headers in first 200 chars
        
        if stripped.startswith(('##', '==', '--', '**')):
            if chars_processed < HEADER_REMOVAL_THRESHOLD:
                # Early in response - this is likely SCENE junk, strip it
                return ''
            else:
                # Later in response - could be CHOICES marker, preserve it
                pass  # Fall through to return chunk
        
        # Check for "START OF SCENE" and similar patterns early in response
        # These patterns might appear in chunks that don't start with ##
        # (e.g., when "############\nSTART OF SCENE\n############" is split across chunks)
        if chars_processed < HEADER_REMOVAL_THRESHOLD:
            if re.search(r'^(?:#+\s*)?START\s+OF\s+SCENE\s*(?:#+)?$', stripped, re.IGNORECASE):
                return ''
            if re.search(r'^(?:#+\s*)?(?:BEGIN|BEGINNING)\s+(?:OF\s+)?SCENE\s*(?:#+)?$', stripped, re.IGNORECASE):
                return ''
        
        # Markdown scene headers with numbers: "### SCENE 113 ###" (most specific first)
        if stripped.startswith('#'):
            if re.match(r'^#{1,6}\s*SCENE\s+\d+', stripped, re.IGNORECASE):
                cleaned = re.sub(r'^#{1,6}\s*SCENE\s+\d+\s*#{1,6}\s*\n?', '', chunk, flags=re.IGNORECASE)
                return cleaned
            if re.match(r'^#{1,6}\s*Scene\s+\d+', stripped, re.IGNORECASE):
                cleaned = re.sub(r'^#{1,6}\s*Scene\s+\d+[^#\n]*#{0,6}\s*\n?', '', chunk, flags=re.IGNORECASE)
                return cleaned
        
        # Scene number patterns at start of chunk: "Scene 123:", "SCENE 42"
        if stripped.startswith(('Scene ', 'SCENE ', 'scene ')):
            if re.match(r'^Scene\s+\d+[:\-\s]', chunk, re.IGNORECASE):
                cleaned = re.sub(r'^Scene\s+\d+[:\-\s]*[^\n]*\n?', '', chunk, flags=re.IGNORECASE)
                return cleaned
        
        # Scene response markers: "=== SCENE RESPONSE ==="
        if 'SCENE RESPONSE' in stripped.upper():
            cleaned = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s+RESPONSE\s*[#=\-\*]*\s*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned
        
        # Scene expansion markers and regenerated variants
        if any(marker in stripped.upper() for marker in ['SCENE EXPANSION', 'SCENE CONTINUATION', 'REGENERATED SCENE', 'REGNERATED SCENE', 'REVISED SCENE']):
            cleaned = re.sub(r'^[#=\-\*]{2,}\s*(?:REGE?NERATED|REVISED|SCENE)\s*(?:EXPANSION|CONTINUATION)?[^#=\-\*\n]*[#=\-\*]*\s*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned
        
        # "Continue scene" prefix
        if stripped.lower().startswith(('continue scene', 'continuing the scene', 'continued scene')):
            cleaned = re.sub(r'^(?:Continue|Continuing|Continued)\s+(?:the\s+)?scene[:\s]*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned
        
        # "Here is" prefix
        if stripped.lower().startswith(("here's the scene", "here is the scene", "here's the continuation")):
            cleaned = re.sub(r'^Here(?:\'s|\s+is)\s+(?:the\s+)?(?:scene|continuation)[:\s]*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned
        
        return chunk
    
    # Story Generation Functions
    
    async def generate_story_title(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
        """Generate creative story titles based on story content"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "title_generation", "title_generation",
            context=self._format_context_for_titles(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("titles", user_settings)
        
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
        
        max_tokens = prompt_manager.get_max_tokens("story_chapters", user_settings)
        
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
    
    async def generate_scene(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> str:
        """
        Generate a story scene using multi-message structure for better cache utilization.
        
        The context is split into multiple user messages to maximize LLM cache hits:
        - Story Foundation (stable per story)
        - Chapter Context (stable per chapter)
        - Entity States (changes every N scenes)
        - Story Progress + Task (changes every scene)
        """
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get prose_style from writing preset (default to balanced)
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Extract immediate_situation from context for template variable
        # This should contain the continuation option text when a choice is made
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE GENERATION] Using scene_with_immediate template (has immediate_situation)")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE GENERATION] Using scene_without_immediate template (no immediate_situation)")
        
        # Get system prompt from template (user prompt will be built from multi-message structure)
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        # Check completion mode - multi-message only works with chat completion
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                db=db,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation
            )
            response_text = await self._generate_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            )
            return self._clean_scene_numbers(response_text)
        
        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        # Build messages array with context split into stable/dynamic parts
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (most stable → most dynamic)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Add the final task message from prompts.yml (most dynamic - changes every scene)
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE GENERATION] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
        # Call LLM with multi-message structure
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if should_inject_nsfw_filter(user_allow_nsfw):
            messages[0]["content"] = messages[0]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
        
        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, None)
        gen_params["messages"] = messages
        
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value
        
        # Call LLM and get full response object
        response = await acompletion(**gen_params)
        
        # Log raw response for scene generation debugging
        self._log_raw_response(response, "New Scene Generation (Multi-Message)")
        
        # Extract content
        response_text = response.choices[0].message.content
        
        return self._clean_scene_numbers(response_text)
    
    async def generate_scene_with_choices(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> Tuple[str, Optional[List[str]]]:
        """
        Generate scene content and choices in a single non-streaming call.
        Uses multi-message structure for better cache utilization.
        Returns (scene_content, parsed_choices)
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get scene length, choices count, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get prose_style from writing preset (default to balanced)
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE WITH CHOICES] Using scene_with_immediate template (has immediate_situation)")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE WITH CHOICES] Using scene_without_immediate template (no immediate_situation)")
        
        # Get system prompt from template
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Add buffer for choices section when generating scene with choices
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        max_tokens = base_max_tokens + 300  # Extra tokens for choices section
        logger.info(f"[SCENE WITH CHOICES] Using max_tokens: {max_tokens} (base: {base_max_tokens} + 300 buffer for choices)")
        
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                db=db,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation
            )
            response_text = await self._generate_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            )
            cleaned_response = self._clean_scene_numbers(response_text)
            
        else:
            # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
            messages = [{"role": "system", "content": system_prompt.strip()}]
            
            # Get scene batch size from user settings for cache optimization
            scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
            
            # Add context as multiple user messages (most stable → most dynamic)
            context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
            messages.extend(context_messages)
            
            # Get task instruction and choices reminder from prompts.yml
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            tone = context.get('tone', '')
            task_content = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            
            # Only append choices reminder if separate_choice_generation is NOT enabled
            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
            else:
                logger.info(f"[SCENE WITH CHOICES] Separate choice generation enabled - skipping choices reminder in task")
            
            messages.append({"role": "user", "content": task_content})
            
            logger.info(f"[SCENE WITH CHOICES] Using multi-message structure: {len(messages)} messages")
            
            # Apply NSFW filter
            from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
            user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
            
            if should_inject_nsfw_filter(user_allow_nsfw):
                messages[0]["content"] = messages[0]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            
            # Get generation parameters
            gen_params = client.get_generation_params(max_tokens, None)
            gen_params["messages"] = messages
            
            # Get timeout from user settings or fallback to system default
            user_timeout = None
            if user_settings:
                llm_settings = user_settings.get('llm_settings', {})
                user_timeout = llm_settings.get('timeout_total')
            timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
            gen_params["timeout"] = timeout_value
            
            # Call LLM and get full response object
            response = await acompletion(**gen_params)
            
            # Log raw response for scene generation debugging
            self._log_raw_response(response, "New Scene Generation with Choices (Multi-Message)")
            
            # Extract content
            response_text = response.choices[0].message.content
            
            # Print raw LLM response to console for scene generation with choices
            logger.info("=" * 80)
            logger.info("RAW LLM RESPONSE - SCENE GENERATION WITH CHOICES (MULTI-MESSAGE)")
            logger.info("=" * 80)
            logger.info(f"Full response text ({len(response_text)} chars):")
            logger.info(response_text)
            logger.info("=" * 80)
            
            cleaned_response = self._clean_scene_numbers(response_text)
        
        # Split scene and choices
        if CHOICES_MARKER in cleaned_response:
            parts = cleaned_response.split(CHOICES_MARKER, 1)
            scene_content = parts[0].strip()
            choices_text = parts[1].strip() if len(parts) > 1 else ""
            
            parsed_choices = self._parse_choices_from_json(choices_text)
            if parsed_choices:
                logger.info(f"[CHOICES] Successfully parsed {len(parsed_choices)} choices")
                # If separate_choice_generation is enabled, discard inline choices
                if separate_choice_generation:
                    logger.info(f"[CHOICES] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
                    return (scene_content, None)
                return (scene_content, parsed_choices)
            else:
                # Check if response might have been truncated
                if len(choices_text) < 50:
                    logger.warning(f"[CHOICES] Marker found but choices text is very short ({len(choices_text)} chars). Response may have been truncated. Choices text: {choices_text}")
                else:
                    logger.warning(f"[CHOICES] Marker found but parsing failed. Choices text length: {len(choices_text)}, preview: {choices_text[:200]}")
                return (scene_content, None)
        else:
            # No marker found in cleaned response - try post-processing extraction from raw response
            logger.warning(f"[CHOICES] Marker NOT found in cleaned response. Attempting post-processing extraction...")
            scene_content, extracted_choices = self._extract_choices_from_response_end(response_text)
            if extracted_choices:
                logger.info(f"[CHOICES] Post-processing extracted {len(extracted_choices)} choices from response end")
                # If separate_choice_generation is enabled, discard inline choices
                if separate_choice_generation:
                    logger.info(f"[CHOICES] Separate choice generation enabled - discarding {len(extracted_choices)} inline choices")
                    return (scene_content, None)
                return (scene_content, extracted_choices)
            else:
                logger.warning(f"[CHOICES] Could not extract choices from response. Response length: {len(cleaned_response)} chars")
                return (cleaned_response, None)
    
    async def generate_scene_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """
        Generate a story scene with streaming using multi-message structure for better cache utilization.
        """
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Default prose_style (no db access in this function)
        prose_style = 'balanced'
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE GENERATION STREAMING] Using scene_with_immediate template (has immediate_situation)")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE GENERATION STREAMING] Using scene_without_immediate template (no immediate_situation)")
        
        # Get system prompt from template
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            scene_length_description=scene_length_description,
            choices_count=choices_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        # Check completion mode - multi-message only works with chat completion
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation
            )
            
            raw_chunks = []
            async for chunk in self._generate_stream_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            ):
                raw_chunks.append(chunk)
                cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
                if cleaned_chunk:
                    yield cleaned_chunk
            return
        
        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (most stable → most dynamic)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Add the final task message from prompts.yml (most dynamic - changes every scene)
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE GENERATION STREAMING] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
        # Collect all raw chunks for raw response capture (before cleaning)
        raw_chunks = []
        
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            # Capture raw chunk before cleaning
            raw_chunks.append(chunk)
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
        
        # Write raw response to file after streaming completes (only if prompt_debug is enabled)
        if settings.prompt_debug and raw_chunks:
            try:
                backend_dir = Path(__file__).parent.parent.parent
                raw_response_file = backend_dir / "Raw-Response.txt"
                full_response = ''.join(raw_chunks)
                with open(raw_response_file, 'w', encoding='utf-8') as f:
                    f.write("=" * 80 + "\n")
                    f.write("RAW LLM RESPONSE FOR NEW SCENE GENERATION (STREAMING, MULTI-MESSAGE)\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(full_response)
                    f.write("\n\n" + "=" * 80 + "\n")
                logger.debug(f"Raw LLM response written to {raw_response_file}")
            except Exception as e:
                logger.error(f"Failed to write raw response to file: {e}")
    
    async def generate_scene_variants(self, original_scene: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> str:
        """Generate alternative versions of a scene (non-streaming, legacy endpoint)"""
        
        # Check if this is guided enhancement (has enhancement_guidance) or simple variant
        enhancement_guidance = context.get("enhancement_guidance", "")
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get prose_style from writing preset (default to balanced)
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # POV instruction (default third person)
        pov_instruction = "in third person (he/she/they/character names)"
        
        if enhancement_guidance:
            # Guided enhancement: use scene_guided_enhancement template with original scene
            # Exclude last scene from previous events to avoid duplication
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "scene_guided_enhancement", "scene_guided_enhancement",
                user_id=user_id,
                db=db,
                context=self._format_context_for_scene(context, exclude_last_scene=True),
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                pov_instruction=pov_instruction
            )
        else:
            # Simple variant: use same templates as new scene generation for cache optimization
            # Choose template based on whether we have immediate_situation
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            if has_immediate:
                template_key = "scene_with_immediate"
            else:
                template_key = "scene_without_immediate"
            
            # Get task instruction from prompts.yml
            tone = context.get('tone', '')
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                db=db,
                context=self._format_context_for_scene(context, exclude_last_scene=False),
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation,
                pov_instruction=pov_instruction,
                task_instruction=task_instruction
            )
        
        max_tokens = prompt_manager.get_max_tokens("scene_with_immediate", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    # NOTE: generate_scene_variants_streaming was removed - it was dead code (never called)
    # Use generate_variant_with_choices_streaming instead for streaming variant generation
    
    async def generate_scene_continuation(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> str:
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
        
        # Get choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        
        # Enhance system prompt with POV consistency requirement
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            user_id=user_id,
            db=db,
            context=self._format_context_for_continuation(context),
            choices_count=choices_count
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
    
    async def generate_scene_continuation_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> AsyncGenerator[str, None]:
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
        
        # Get choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            user_id=user_id,
            db=db,
            context=self._format_context_for_continuation(context),
            choices_count=choices_count
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
    
    def _fix_incomplete_json_array(self, json_str: str) -> Optional[str]:
        """
        Attempt to fix an incomplete JSON array by extracting valid complete entries.
        Returns fixed JSON string or None if fixing is not possible.
        """
        if not json_str or not json_str.strip().startswith('['):
            return None
        
        try:
            # Remove the opening bracket
            content = json_str.lstrip('[').strip()
            
            # Try to extract complete string entries
            # Pattern: "..." followed by comma or end
            entries = []
            current_pos = 0
            in_string = False
            escaped = False
            start_pos = None
            
            i = 0
            while i < len(content):
                char = content[i]
                
                if escaped:
                    escaped = False
                    i += 1
                    continue
                
                if char == '\\':
                    escaped = True
                    i += 1
                    continue
                
                if char == '"':
                    if not in_string:
                        # Start of a new string
                        in_string = True
                        start_pos = i
                    else:
                        # End of string - check if it's followed by comma or whitespace
                        end_pos = i + 1
                        # Look ahead for comma or end of content
                        remaining = content[end_pos:].lstrip()
                        if not remaining or remaining.startswith(',') or remaining.startswith(']'):
                            # This is a complete string entry
                            entry = content[start_pos:end_pos]
                            entries.append(entry)
                            in_string = False
                            # Skip past comma if present
                            if remaining.startswith(','):
                                i = end_pos + remaining.find(',') + 1
                                continue
                            elif remaining.startswith(']'):
                                break
                    i += 1
                    continue
                
                i += 1
            
            # If we found any complete entries, reconstruct the JSON array
            if entries:
                fixed_json = '[' + ', '.join(entries) + ']'
                logger.info(f"[CHOICES PARSE] Fixed incomplete JSON: extracted {len(entries)} complete entries")
                return fixed_json
            
            # Fallback: try to close the last incomplete string if we're in one
            if in_string and start_pos is not None:
                # Close the current string
                incomplete_entry = content[start_pos:] + '"'
                # Remove trailing comma if present
                incomplete_entry = re.sub(r',\s*$', '', incomplete_entry)
                fixed_json = '[' + incomplete_entry + ']'
                logger.info(f"[CHOICES PARSE] Fixed incomplete JSON: closed last string")
                return fixed_json
            
            return None
        except Exception as e:
            logger.warning(f"[CHOICES PARSE] Error fixing incomplete JSON: {e}")
            return None
    
    def _fix_malformed_json_escaping(self, text: str) -> str:
        """
        Fix common LLM JSON escaping issues:
        - Mixed quote escaping like \"' or \'
        - Double-escaped quotes like \\"
        - Unescaped quotes inside strings
        """
        # Fix patterns like \"' (escaped double quote followed by single quote)
        text = re.sub(r'\\"\'', '"', text)
        text = re.sub(r'\'\"', '"', text)
        # Fix escaped single quotes that shouldn't be escaped in JSON
        text = re.sub(r"\\\'", "'", text)
        # Fix double-escaped quotes
        text = re.sub(r'\\\\\"', '\\"', text)
        # Fix patterns like \'' (escaped single quote followed by single quote)
        text = re.sub(r"\\''", "'", text)
        return text
    
    def _extract_choices_with_regex(self, text: str) -> Optional[List[str]]:
        """
        Fallback method to extract choices using regex when JSON parsing fails.
        Looks for quoted strings that appear to be choices.
        Handles escaped quotes (\\") inside strings.
        """
        choices = []
        
        # First try double-quoted strings, handling escaped quotes
        # Pattern: (?:[^"\\]|\\.) matches either:
        #   - [^"\\] = any char except quote or backslash
        #   - \\. = backslash followed by any char (escaped char like \")
        # Minimum 10 chars, no maximum limit
        double_quoted = re.findall(r'"((?:[^"\\]|\\.){10,})"', text)
        for match in double_quoted:
            # Unescape: convert \" to " and \' to '
            cleaned = match.replace('\\"', '"').replace("\\'", "'").strip()
            # Filter out things that look like JSON keys or formatting
            if cleaned and not cleaned.startswith('{') and not cleaned.endswith(':') and 'choices' not in cleaned.lower():
                choices.append(cleaned)
        
        # If we didn't get enough, try single-quoted strings
        if len(choices) < 2:
            single_quoted = re.findall(r"'((?:[^'\\]|\\.){10,})'", text)
            for match in single_quoted:
                cleaned = match.replace('\\"', '"').replace("\\'", "'").strip()
                if cleaned and cleaned not in choices and not cleaned.startswith('{'):
                    choices.append(cleaned)
        
        if len(choices) >= 2:
            logger.info(f"[CHOICES PARSE] Regex fallback extracted {len(choices)} choices")
            return choices[:6]  # Limit to reasonable number
        
        return None
    
    def _parse_choices_from_json(self, text: str) -> Optional[List[str]]:
        """
        Parse choices from JSON array string.
        Handles various formats and extracts valid choices.
        Returns None if parsing fails.
        """
        if not text or not text.strip():
            logger.warning("[CHOICES PARSE] Empty text provided")
            return None
            
        try:
            # Clean the text - remove any markdown code blocks
            original_text = text
            text = text.strip()
            
            # Handle markdown code blocks (```json ... ``` or ``` ... ```)
            # Improved markdown removal that handles various formats
            if '```' in text:
                # Strategy 1: Use regex to extract content between code block markers
                # This handles both ```json and ``` markers
                code_block_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
                if code_block_match:
                    # Extract content from inside code blocks
                    cleaned_text = code_block_match.group(1).strip()
                    logger.debug(f"[CHOICES PARSE] Extracted content from markdown code block, length: {len(cleaned_text)}")
                else:
                    # Fallback: Remove lines that are just ``` markers
                    lines = text.split('\n')
                    filtered_lines = []
                    inside_code_block = False
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith('```'):
                            inside_code_block = not inside_code_block
                            continue  # Skip the marker line
                        # Add line if we're inside a code block (content) or outside (no code blocks)
                        # But if we're inside, we want the content
                        if inside_code_block or not any('```' in l for l in lines):
                            filtered_lines.append(line)
                    cleaned_text = '\n'.join(filtered_lines).strip()
                    
                    # Strategy 2: If that didn't work, try regex removal of markers
                    if '```' in cleaned_text:
                        # Remove any remaining ``` markers
                        cleaned_text = re.sub(r'```[a-z]*\s*\n?', '', cleaned_text, flags=re.IGNORECASE)
                        cleaned_text = cleaned_text.strip()
                
                text = cleaned_text
                logger.debug(f"[CHOICES PARSE] Removed markdown code blocks, final text length: {len(text)}")
            
            # Helper function to validate and return choices
            def validate_and_return_choices(choices: Any) -> Optional[List[str]]:
                """Validate parsed choices and return cleaned list"""
                if isinstance(choices, list) and len(choices) >= 2:
                    # Clean and validate each choice
                    cleaned_choices = []
                    for i, choice in enumerate(choices):
                        if isinstance(choice, str):
                            cleaned = choice.strip()
                            # Remove any leading/trailing quotes that might have been double-escaped
                            cleaned = cleaned.strip('"\'')
                            if len(cleaned) > 5:  # Minimum reasonable choice length
                                cleaned_choices.append(cleaned)
                            else:
                                logger.debug(f"[CHOICES PARSE] Choice {i+1} too short: {len(cleaned)} chars")
                        else:
                            logger.debug(f"[CHOICES PARSE] Choice {i+1} not a string: {type(choice)}")
                    
                    if len(cleaned_choices) >= 2:
                        logger.info(f"[CHOICES PARSE] Successfully parsed {len(cleaned_choices)} choices")
                        return cleaned_choices
                    else:
                        logger.warning(f"[CHOICES PARSE] Not enough valid choices: {len(cleaned_choices)} < 2")
                else:
                    logger.warning(f"[CHOICES PARSE] Invalid format: got {type(choices)}, length: {len(choices) if isinstance(choices, list) else 'N/A'}")
                return None
            
            # === STRATEGY 1: Try to parse as {"choices": [...]} wrapper first ===
            # This is the format we request in the prompt
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "choices" in parsed:
                    choices = parsed["choices"]
                    result = validate_and_return_choices(choices)
                    if result:
                        return result
            except json.JSONDecodeError:
                pass
            
            # === STRATEGY 2: Try with malformed escaping fixes ===
            fixed_text = self._fix_malformed_json_escaping(text)
            if fixed_text != text:
                try:
                    parsed = json.loads(fixed_text)
                    if isinstance(parsed, dict) and "choices" in parsed:
                        choices = parsed["choices"]
                        result = validate_and_return_choices(choices)
                        if result:
                            logger.info("[CHOICES PARSE] Succeeded after fixing malformed escaping")
                            return result
                    elif isinstance(parsed, list):
                        result = validate_and_return_choices(parsed)
                        if result:
                            logger.info("[CHOICES PARSE] Succeeded after fixing malformed escaping (array)")
                            return result
                except json.JSONDecodeError:
                    pass
            
            # === STRATEGY 3: Try to find JSON array directly ===
            # First check if we have an incomplete array (starts with [ but doesn't end with ])
            incomplete_match = None
            if text.strip().startswith('[') and not text.strip().endswith(']'):
                # Try to find the opening bracket and extract everything after it
                bracket_pos = text.find('[')
                if bracket_pos != -1:
                    incomplete_match = text[bracket_pos:]
            
            # Use non-greedy match first, then try greedy if that fails
            json_match = re.search(r'\[.*?\]', text, re.DOTALL)
            if not json_match:
                # Try greedy match in case array spans multiple lines
                json_match = re.search(r'\[.*\]', text, re.DOTALL)
            
            # If we found a complete match, use it
            if json_match:
                json_str = json_match.group(0)
                
                try:
                    choices = json.loads(json_str)
                    return validate_and_return_choices(choices)
                except json.JSONDecodeError as e:
                    logger.warning(f"[CHOICES PARSE] JSON decode error: {e}, JSON string: {json_str[:200]}")
                    
                    # Try with malformed escaping fixes
                    fixed_json_str = self._fix_malformed_json_escaping(json_str)
                    try:
                        choices = json.loads(fixed_json_str)
                        result = validate_and_return_choices(choices)
                        if result:
                            logger.info("[CHOICES PARSE] Succeeded after fixing array escaping")
                            return result
                    except json.JSONDecodeError:
                        pass
                    
                    # Try to fix common JSON issues - remove trailing commas
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    try:
                        choices = json.loads(json_str)
                        return validate_and_return_choices(choices)
                    except json.JSONDecodeError as e2:
                        logger.warning(f"[CHOICES PARSE] Still failed after cleanup: {e2}")
                        # Try to fix incomplete JSON
                        fixed_json = self._fix_incomplete_json_array(json_str)
                        if fixed_json:
                            try:
                                choices = json.loads(fixed_json)
                                return validate_and_return_choices(choices)
                            except json.JSONDecodeError:
                                pass
            elif incomplete_match:
                # We have an incomplete array, try to fix it
                logger.warning(f"[CHOICES PARSE] Incomplete JSON array detected, attempting to fix. Text preview: {incomplete_match[:200]}")
                fixed_json = self._fix_incomplete_json_array(incomplete_match)
                if fixed_json:
                    try:
                        choices = json.loads(fixed_json)
                        return validate_and_return_choices(choices)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[CHOICES PARSE] Failed to parse fixed incomplete JSON: {e}")
            
            # === STRATEGY 4: Regex fallback - extract quoted strings directly ===
            logger.info("[CHOICES PARSE] Trying regex fallback to extract choices")
            regex_choices = self._extract_choices_with_regex(original_text)
            if regex_choices:
                return regex_choices
            
            # If we get here, all parsing attempts failed
            # Check if text looks like it was cut off (incomplete JSON)
            if text.strip().startswith('[') and not text.strip().endswith(']'):
                logger.warning(f"[CHOICES PARSE] Incomplete JSON array detected (starts with '[' but doesn't end with ']'). Text may have been truncated. Text preview: {text[:200]}")
            elif text.strip().startswith('{') and not text.strip().endswith('}'):
                logger.warning(f"[CHOICES PARSE] Incomplete JSON object detected. Text may have been truncated. Text preview: {text[:200]}")
            elif '```json' in text.lower() or '```' in text:
                logger.warning(f"[CHOICES PARSE] Markdown code block found but no valid JSON inside. Text preview: {text[:200]}")
            else:
                logger.warning(f"[CHOICES PARSE] No valid JSON found in text. Text preview: {text[:200]}")
            
            return None
        except (json.JSONDecodeError, ValueError, AttributeError, Exception) as e:
            logger.warning(f"[CHOICES PARSE] Failed to parse choices from JSON: {e}, text preview: {text[:200] if 'text' in locals() and text else 'empty'}")
            return None
    
    def _extract_choices_from_response_end(self, full_text: str) -> Tuple[str, Optional[List[str]]]:
        """
        Extract choices from the end of a response.
        Looks for choices in the last ~1500 chars where they typically appear.
        
        Returns:
            Tuple of (scene_content, parsed_choices) where parsed_choices may be None
        """
        if not full_text:
            return (full_text, None)
        
        # Only search in the last portion of the response
        search_region = full_text[-1500:] if len(full_text) > 1500 else full_text
        search_start = len(full_text) - len(search_region)
        
        # Try multiple marker patterns
        marker_patterns = [
            r'###\s*CHOICES\s*###',
            r'##\s*CHOICES\s*##', 
            r'#\s*CHOICES\s*#',
            r'\n\s*CHOICES\s*:\s*\n',
            r'\n\s*\*\*CHOICES\*\*\s*\n',
        ]
        
        for pattern in marker_patterns:
            match = re.search(pattern, search_region, re.IGNORECASE)
            if match:
                # Calculate position in full text
                marker_pos = search_start + match.start()
                scene = full_text[:marker_pos].strip()
                choices_text = full_text[marker_pos + len(match.group()):].strip()
                parsed = self._parse_choices_from_json(choices_text)
                if parsed:
                    logger.info(f"[CHOICES EXTRACTION] Found marker '{match.group().strip()}' at position {marker_pos}")
                    return (scene, parsed)
        
        # Fallback: Look for JSON array at the very end
        json_match = re.search(r'\[\s*"[^"]+"\s*(?:,\s*"[^"]+"\s*)+\]\s*$', search_region)
        if json_match:
            parsed = self._parse_choices_from_json(json_match.group())
            if parsed and len(parsed) >= 2:
                marker_pos = search_start + json_match.start()
                scene = full_text[:marker_pos].strip()
                logger.info(f"[CHOICES EXTRACTION] Found JSON array at end (position {marker_pos})")
                return (scene, parsed)
        
        return (full_text, None)
    
    async def generate_scene_with_choices_streaming(
        self, 
        context: Dict[str, Any], 
        user_id: int, 
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate scene content and choices in a single streaming call.
        Uses multi-message structure for better cache utilization.
        
        Yields tuples of (chunk, scene_complete, parsed_choices)
        - chunk: Scene content chunk (only yielded before marker)
        - scene_complete: True when scene content is done (marker found)
        - parsed_choices: List of choices if successfully parsed, None otherwise
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get scene length, choices count, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Determine if we have an immediate situation (for task instruction selection)
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        logger.info(f"[SCENE GEN STREAMING] has_immediate={has_immediate}")
        
        # Get POV from writing preset (default to third person)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Create POV instruction for template
        if pov == 'first':
            pov_instruction = "in first person (I/me/my)"
        elif pov == 'second':
            pov_instruction = "in second person (you/your)"
        else:
            pov_instruction = "in third person (he/she/they/character names)"
        
        # === ALWAYS use scene_with_immediate for system prompt (cache consistency) ===
        # The task instruction will vary based on has_immediate, but system prompt stays the same
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Enhance system prompt with POV instruction for choices (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # Add buffer for choices section when generating scene with choices
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)
        max_tokens = base_max_tokens + choices_buffer_tokens
        logger.info(f"[SCENE WITH CHOICES STREAMING] Using max_tokens: {max_tokens} (base: {base_max_tokens} + {choices_buffer_tokens} buffer for {choices_count} choices)")
        
        # Check completion mode - multi-message only works with chat completion
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            
            # Get task instruction from prompts.yml
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            tone = context.get('tone', '')
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            # Only append choices reminder if separate_choice_generation is NOT enabled
            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_instruction = task_instruction + "\n\n" + choices_reminder
            
            _, user_prompt = prompt_manager.get_prompt_pair(
                "scene_with_immediate", "scene_with_immediate",
                user_id=user_id,
                db=db,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation,
                pov_instruction=pov_instruction,
                task_instruction=task_instruction
            )
            
            scene_buffer = []
            choices_buffer = []
            found_marker = False
            rolling_buffer = ""
            total_chunks = 0
            raw_chunks = []
            
            async for chunk in self._generate_stream_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            ):
                total_chunks += 1
                raw_chunks.append(chunk)
                cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
                if not cleaned_chunk:
                    continue
                
                if not found_marker:
                    rolling_buffer += cleaned_chunk
                    if CHOICES_MARKER in rolling_buffer:
                        parts = rolling_buffer.split(CHOICES_MARKER, 1)
                        scene_part = parts[0]
                        choices_part = parts[1] if len(parts) > 1 else ""
                        if scene_part:
                            yield (scene_part, False, None)
                        scene_buffer.append(scene_part)
                        if choices_part:
                            choices_buffer.append(choices_part)
                        found_marker = True
                        rolling_buffer = ""
                    else:
                        if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                            excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                            excess = rolling_buffer[:excess_length]
                            scene_buffer.append(excess)
                            yield (excess, False, None)
                            rolling_buffer = rolling_buffer[excess_length:]
                else:
                    choices_buffer.append(cleaned_chunk)
            
            if not found_marker and rolling_buffer:
                scene_buffer.append(rolling_buffer)
                yield (rolling_buffer, False, None)
            
            parsed_choices = None
            if found_marker and choices_buffer:
                choices_text = ''.join(choices_buffer).strip()
                parsed_choices = self._parse_choices_from_json(choices_text)
            
            # If separate_choice_generation is enabled, discard any inline choices
            if separate_choice_generation and parsed_choices:
                logger.info(f"[CHOICES TEXT COMPLETION] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
                parsed_choices = None
            
            yield ("", True, parsed_choices)
            return
        
        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (most stable → most dynamic)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Get task instruction and choices reminder from prompts.yml
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        # Only append choices reminder if separate_choice_generation is NOT enabled
        # When enabled, choices will be generated in a separate LLM call for higher quality
        if not separate_choice_generation:
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
        else:
            logger.info(f"[SCENE WITH CHOICES STREAMING] Separate choice generation enabled - skipping choices reminder in task")
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        raw_chunks = []  # Collect raw chunks before cleaning
        chars_processed = 0  # Track position in response for position-aware cleaning
        
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            total_chunks += 1
            
            # Handle thinking content - yield it but don't add to scene buffer
            # Thinking chunks are prefixed with __THINKING__:
            if chunk.startswith("__THINKING__:"):
                # Yield thinking chunk for frontend display, but don't process for scene/choices
                yield (chunk, False, None)
                continue
            
            raw_chunks.append(chunk)  # Capture raw chunk before cleaning
            
            # Pass position to cleaner for position-aware cleaning
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk, chars_processed)
            chars_processed += len(chunk)  # Update position after cleaning
            
            if not cleaned_chunk:
                continue
            
            if not found_marker:
                # Add to rolling buffer
                rolling_buffer += cleaned_chunk
                
                # Check if marker is in rolling buffer
                if CHOICES_MARKER in rolling_buffer:
                    # Split: before marker goes to scene, after to choices
                    parts = rolling_buffer.split(CHOICES_MARKER, 1)
                    scene_part = parts[0]  # Everything before marker - guaranteed to be new content
                    choices_part = parts[1] if len(parts) > 1 else ""
                    
                    # scene_part is guaranteed to be new content (rolling_buffer only has unyielded content)
                    # Yield ALL of it to preserve complete scene text before marker
                    if scene_part:
                        yield (scene_part, False, None)
                    
                    scene_buffer.append(scene_part)
                    
                    # Buffer the choices part - DO NOT YIELD
                    if choices_part:
                        choices_buffer.append(choices_part)
                    
                    found_marker = True
                    rolling_buffer = ""  # Clear rolling buffer
                    # Continue reading to get all choice chunks
                else:
                    # Keep rolling buffer small (only last len(MARKER) chars needed)
                    # to detect marker split across chunks
                    if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                        # Yield the excess (keeping last MARKER length in buffer)
                        excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                        excess = rolling_buffer[:excess_length]
                        scene_buffer.append(excess)
                        yield (excess, False, None)
                        rolling_buffer = rolling_buffer[excess_length:]
            else:
                # After marker, buffer for choice parsing - DO NOT YIELD
                choices_buffer.append(cleaned_chunk)
        
        # After stream ends, yield any remaining rolling buffer content
        if not found_marker and rolling_buffer:
            scene_buffer.append(rolling_buffer)
            yield (rolling_buffer, False, None)
        
        # Build full response for logging
        full_scene_content = ''.join(scene_buffer)
        full_response = full_scene_content + (''.join(choices_buffer) if choices_buffer else '')
        raw_full_response = ''.join(raw_chunks)  # Combined raw chunks before cleaning
        
        # Print raw LLM response to console for scene generation with choices (streaming)
        logger.info("=" * 80)
        logger.info("RAW LLM RESPONSE - SCENE GENERATION WITH CHOICES (STREAMING)")
        logger.info("=" * 80)
        logger.info(f"Full response text ({len(raw_full_response)} chars, {total_chunks} chunks):")
        logger.info(raw_full_response)
        logger.info("=" * 80)
        
        # Write raw response to file (using raw chunks before cleaning, only if prompt_debug is enabled)
        if settings.prompt_debug:
            try:
                backend_dir = Path(__file__).parent.parent.parent
                raw_response_file = backend_dir / "Raw-Response.txt"
                with open(raw_response_file, 'w', encoding='utf-8') as f:
                    f.write("=" * 80 + "\n")
                    f.write("RAW LLM RESPONSE FOR NEW SCENE GENERATION (STREAMING)\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(raw_full_response)
                    f.write("\n\n" + "=" * 80 + "\n")
                logger.debug(f"Raw LLM response written to {raw_response_file}")
            except Exception as e:
                logger.error(f"Failed to write raw response to file: {e}")
        
        # Parse choices from buffer
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if parsed_choices:
                logger.info(f"[CHOICES STREAMING] Successfully parsed {len(parsed_choices)} choices")
            else:
                # Check if response might have been truncated
                if len(choices_text) < 50:
                    logger.warning(f"[CHOICES STREAMING] Marker found but choices text is very short ({len(choices_text)} chars). Response may have been truncated. Choices text: {choices_text}")
                else:
                    logger.warning(f"[CHOICES STREAMING] Marker found but parsing failed. Choices text length: {len(choices_text)}, preview: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES STREAMING] Marker not found during streaming after {total_chunks} chunks. Attempting post-processing extraction...")
                # Try to extract choices from the end of the raw response
                scene_content, extracted_choices = self._extract_choices_from_response_end(raw_full_response)
                if extracted_choices:
                    logger.info(f"[CHOICES STREAMING] Post-processing extracted {len(extracted_choices)} choices from response end")
                    parsed_choices = extracted_choices
                    # Update scene buffer with clean content (without choices)
                    scene_buffer = [scene_content]
                else:
                    logger.warning(f"[CHOICES STREAMING] ERROR: Could not extract choices from response. Full response length: {len(full_response)} chars")
            else:
                logger.warning(f"[CHOICES STREAMING] Marker found but choices_buffer is empty")
        
        # If separate_choice_generation is enabled, discard any inline choices and return None
        # This signals to the caller to use the separate generate_choices() function
        if separate_choice_generation:
            if parsed_choices:
                logger.info(f"[CHOICES STREAMING] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
            parsed_choices = None
        
        # Yield final completion with parsed choices
        yield ("", True, parsed_choices)
    
    async def generate_variant_with_choices_streaming(
        self,
        original_scene: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate scene variant and choices in a single streaming call.
        Same pattern as generate_scene_with_choices_streaming.
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Log inputs for debugging
        logger.info(f"Variant generation - context type: {type(context)}")
        
        # Get scene length, choices count, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Check if this is guided enhancement (has enhancement_guidance) or simple variant
        enhancement_guidance = context.get("enhancement_guidance", "")
        
        # Get POV from writing preset (default to third person)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Create POV instruction for template
        if pov == 'first':
            pov_instruction = "in first person (I/me/my)"
        elif pov == 'second':
            pov_instruction = "in second person (you/your)"
        else:
            pov_instruction = "in third person (he/she/they/character names)"
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION (for cache hits) ===
        # Always use scene_with_immediate for system prompt consistency
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Enhance system prompt with POV instruction for choices (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION (for cache hits) ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        tone = context.get('tone', '')
        if enhancement_guidance:
            # Guided enhancement: use task_guided_enhancement from prompts.yml
            task_content = prompt_manager.get_enhancement_task_instruction(
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                prose_style=prose_style,
                tone=tone,
                skip_choices_reminder=separate_choice_generation
            )
            logger.info(f"[GUIDED ENHANCEMENT] Using multi-message structure with enhancement task")
        else:
            # Simple variant: use same task instruction as scene generation
            immediate_situation = context.get("current_situation") or ""
            immediate_situation = str(immediate_situation) if immediate_situation else ""
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            
            task_content = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            
            # Only append choices reminder if separate_choice_generation is NOT enabled
            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        # Add buffer for choices section - dynamic based on choices_count
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)  # At least 300, or 50 per choice
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        logger.info(f"[VARIANT WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages, max_tokens={max_tokens}")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        
        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            total_chunks += 1
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if not cleaned_chunk:
                continue
            
            if not found_marker:
                # Add to rolling buffer
                rolling_buffer += cleaned_chunk
                
                # Check if marker is in rolling buffer
                if CHOICES_MARKER in rolling_buffer:
                    # Split: before marker goes to scene, after to choices
                    parts = rolling_buffer.split(CHOICES_MARKER, 1)
                    scene_part = parts[0]  # Everything before marker - guaranteed to be new content
                    choices_part = parts[1] if len(parts) > 1 else ""
                    
                    # scene_part is guaranteed to be new content (rolling_buffer only has unyielded content)
                    # Yield ALL of it to preserve complete scene text before marker
                    if scene_part:
                        yield (scene_part, False, None)
                    
                    scene_buffer.append(scene_part)
                    
                    # Buffer the choices part - DO NOT YIELD
                    if choices_part:
                        choices_buffer.append(choices_part)
                    
                    found_marker = True
                    rolling_buffer = ""  # Clear rolling buffer
                    # Continue reading to get all choice chunks
                else:
                    # Keep rolling buffer small (only last len(MARKER) chars needed)
                    if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                        excess = rolling_buffer[:excess_length]
                        scene_buffer.append(excess)
                        yield (excess, False, None)
                        rolling_buffer = rolling_buffer[excess_length:]
            else:
                # After marker, buffer for choice parsing - DO NOT YIELD
                choices_buffer.append(cleaned_chunk)
        
        # After stream ends, yield any remaining rolling buffer content
        if not found_marker and rolling_buffer:
            scene_buffer.append(rolling_buffer)
            yield (rolling_buffer, False, None)
        
        # Parse choices from buffer
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if not parsed_choices:
                logger.warning(f"[CHOICES VARIANT] Marker found but parsing failed. Choices text: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES VARIANT] ERROR: ###CHOICES### marker not found after {total_chunks} chunks")
                logger.warning(f"[CHOICES VARIANT] Scene buffer length: {len(''.join(scene_buffer))} chars")
            else:
                logger.warning(f"[CHOICES VARIANT] Marker found but choices_buffer is empty")
        
        # If separate_choice_generation is enabled, discard any inline choices
        if separate_choice_generation and parsed_choices:
            logger.info(f"[CHOICES VARIANT] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
            parsed_choices = None
        
        yield ("", True, parsed_choices)
    
    async def generate_continuation_with_choices_streaming(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate scene continuation and choices in a single streaming call.
        
        Uses the SAME multi-message structure as scene generation and choice generation
        for maximum cache hits. Messages 1-N are identical (system prompt, foundation,
        chapter, entity states, scene batches). Only the final message differs
        (current scene + continuation instruction instead of new scene + choice request).
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get POV and prose_style from writing preset (SAME as scene generation - critical for cache hits)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Get choices count, scene length, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length = generation_prefs.get("scene_length", "medium")
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_map = {"short": "short (50-100 words)", "medium": "medium (100-150 words)", "long": "long (150-250 words)"}
        scene_length_description = scene_length_map.get(scene_length, "medium (100-150 words)")
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION (for cache hits) ===
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Add POV consistency requirement to system prompt (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION (for cache hits) ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        # The context already has current scene excluded (via exclude_scene_id in context_manager)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        # Instead of new scene + choice request, we send current scene + continuation instruction
        # Get current scene content and continuation prompt from context
        current_scene_content = context.get("current_scene_content", "") or context.get("current_content", "")
        continuation_prompt = context.get("continuation_prompt", "Continue this scene with more details and development.")
        
        # Clean scene content to remove any instruction tags or formatting artifacts
        cleaned_scene_content = self._clean_instruction_tags(current_scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)
        
        # Build final message inline (like generate_choices does)
        # Only include choices reminder if separate_choice_generation is NOT enabled
        if separate_choice_generation:
            choices_reminder_text = ""
        else:
            choices_reminder_text = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
        
        # Get prose style and tone reminders
        prose_style_reminder = prompt_manager.get_prose_style_reminder(prose_style)
        tone = context.get('tone', '')
        tone_reminder = prompt_manager.get_tone_reminder(tone)
        
        final_message = f"""=== CURRENT SCENE TO CONTINUE ===
{cleaned_scene_content}

=== CONTINUATION INSTRUCTION ===
{continuation_prompt}

Write a compelling continuation that follows naturally from the scene above.
Focus on engaging narrative and dialogue. Do not repeat previous content.
Write approximately {scene_length_description} in length.

{prose_style_reminder}
{tone_reminder}

{choices_reminder_text}"""
        
        messages.append({"role": "user", "content": final_message})
        
        # Add buffer for choices section - dynamic based on choices_count
        base_max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)  # At least 300, or 50 per choice
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        logger.info(f"[CONTINUATION] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write continuation prompt debug file: {e}")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        
        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if not cleaned_chunk:
                continue
            
            if not found_marker:
                # Add to rolling buffer
                rolling_buffer += cleaned_chunk
                
                # Check if marker is in rolling buffer
                if CHOICES_MARKER in rolling_buffer:
                    # Split: before marker goes to scene, after to choices
                    parts = rolling_buffer.split(CHOICES_MARKER, 1)
                    scene_part = parts[0]  # Everything before marker - guaranteed to be new content
                    choices_part = parts[1] if len(parts) > 1 else ""
                    
                    # scene_part is guaranteed to be new content (rolling_buffer only has unyielded content)
                    # Yield ALL of it to preserve complete scene text before marker
                    if scene_part:
                        yield (scene_part, False, None)
                    
                    scene_buffer.append(scene_part)
                    
                    # Buffer the choices part - DO NOT YIELD
                    if choices_part:
                        choices_buffer.append(choices_part)
                    
                    found_marker = True
                    rolling_buffer = ""  # Clear rolling buffer
                    # Continue reading to get all choice chunks
                else:
                    # Keep rolling buffer small (only last len(MARKER) chars needed)
                    if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                        excess = rolling_buffer[:excess_length]
                        scene_buffer.append(excess)
                        yield (excess, False, None)
                        rolling_buffer = rolling_buffer[excess_length:]
            else:
                # After marker, buffer for choice parsing - DO NOT YIELD
                choices_buffer.append(cleaned_chunk)
        
        # After stream ends, yield any remaining rolling buffer content
        if not found_marker and rolling_buffer:
            scene_buffer.append(rolling_buffer)
            yield (rolling_buffer, False, None)
        
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if not parsed_choices:
                logger.warning(f"[CHOICES CONTINUATION] Marker found but parsing failed. Choices text: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES CONTINUATION] Marker NOT found")
            else:
                logger.warning(f"[CHOICES CONTINUATION] Marker found but choices_buffer is empty")
        
        # If separate_choice_generation is enabled, discard any inline choices
        if separate_choice_generation and parsed_choices:
            logger.info(f"[CHOICES CONTINUATION] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
            parsed_choices = None
        
        yield ("", True, parsed_choices)
    
    async def generate_concluding_scene_streaming(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a chapter-concluding scene in a streaming fashion.
        Unlike other scene generation methods, this does NOT generate choices
        as chapter endings are meant to conclude rather than branch.
        
        Uses the SAME multi-message structure as scene generation for maximum cache hits.
        Messages 1-N are identical (system prompt, foundation, chapter, entity states, 
        scene batches). Only the final message differs (chapter conclusion instruction).
        
        Args:
            context: Scene generation context from context_manager
            chapter_info: Dictionary with chapter_number, chapter_title, chapter_location, 
                         chapter_time_period, chapter_scenario
            user_id: User ID for LLM settings
            user_settings: User settings dictionary
            db: Database session for prompt templates
            
        Yields:
            str: Scene content chunks as they're generated
        """
        # Get POV and prose_style from writing preset (SAME as scene generation - critical for cache hits)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Get scene length from user settings (for consistency with other generation methods)
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION FOR CACHE ALIGNMENT ===
        # This ensures messages 1-N are identical between chapter conclusion and choice generation,
        # enabling cache hits when generating choices after a chapter conclusion.
        # Chapter-specific instructions are in the final user message instead.
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=True  # Chapter conclusions don't include choices in the scene
        )
        
        if not system_prompt or not system_prompt.strip():
            logger.error("[CONCLUDING SCENE] System prompt is empty for scene_with_immediate")
            raise ValueError("Failed to load system prompt for chapter conclusion")
        
        # Add POV consistency requirement
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD MULTI-MESSAGE STRUCTURE (for cache hits on context) ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # === FINAL MESSAGE: Simple chapter conclusion instruction (inline like continuation) ===
        # Chapter context is already in the multi-message structure, so we just need the task
        chapter_number = chapter_info.get("chapter_number", 1)
        
        # Get prose style and tone reminders
        prose_style_reminder = prompt_manager.get_prose_style_reminder(prose_style)
        tone = context.get('tone', '')
        tone_reminder = prompt_manager.get_tone_reminder(tone)
        
        final_message = f"""=== CHAPTER CONCLUSION INSTRUCTION ===

Write a compelling conclusion for Chapter {chapter_number} that:
1. Brings this chapter to a natural and satisfying end
2. Provides closure for the chapter's events while leaving the overall story open
3. Sets up anticipation for what might come next
4. Ends at a natural chapter break point

Write approximately {scene_length_description} in length.
Write ONLY narrative content. Do not include any choices, options, or questions for the reader.

{prose_style_reminder}
{tone_reminder}

Chapter Conclusion:"""
        
        messages.append({"role": "user", "content": final_message})
        
        max_tokens = prompt_manager.get_max_tokens("chapter_conclusion", user_settings)
        logger.info(f"[CONCLUDING SCENE] Using multi-message structure: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "temperature": 1.0,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write chapter conclusion prompt debug file: {e}")
        
        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:
                yield cleaned_chunk
        
        logger.info("[CONCLUDING SCENE STREAMING] Generation complete")
    
    # =====================================================================
    # MULTI-GENERATION METHODS (n > 1)
    # These methods handle generating multiple completions in a single API call
    # =====================================================================
    
    async def _generate_stream_with_messages_multi(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[Tuple[str, bool, List[str]], None]:
        """
        Core streaming helper for n > 1 completions.
        
        Streams the first completion (index 0) to the frontend while accumulating
        all n completions in the background.
        
        Yields:
            Tuple of (chunk, is_complete, contents_list)
            - During streaming: (chunk_text, False, [])
            - On completion: ("", True, [content_0, content_1, ..., content_n-1])
        """
        client = self.get_user_client(user_id, user_settings)
        
        # Inject NSFW filter into system message if needed (SAME as _generate_stream_with_messages)
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if should_inject_nsfw_filter(user_allow_nsfw):
            # Find and modify system message, or add one
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"[MULTI-GEN] NSFW filter injected for user {user_id}")
        
        # Get generation params and add n parameter
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        gen_params["stream"] = True
        
        # Add n to extra_body
        if "extra_body" not in gen_params:
            gen_params["extra_body"] = {}
        gen_params["extra_body"]["n"] = n
        
        # Get timeout from user settings
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total
        
        logger.info(f"[MULTI-GEN] Starting streaming with n={n}")
        
        try:
            response = await acompletion(**gen_params)
            
            # Track content for each completion index
            contents = [""] * n
            chunk_count = 0
            
            async for chunk in response:
                chunk_count += 1
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    # Process all choices in the chunk
                    for choice in chunk.choices:
                        idx = choice.index if hasattr(choice, 'index') else 0
                        if idx >= n:
                            continue  # Safety check
                        
                        delta = choice.delta if hasattr(choice, 'delta') else None
                        if delta and hasattr(delta, 'content') and delta.content:
                            contents[idx] += delta.content
                            
                            # Only stream index 0 to the frontend
                            if idx == 0:
                                yield (delta.content, False, [])
            
            logger.info(f"[MULTI-GEN] Streaming complete: {chunk_count} chunks, {n} completions")
            for i, content in enumerate(contents):
                logger.info(f"[MULTI-GEN] Content {i}: {len(content)} chars")
            
            # Yield final result with all contents
            yield ("", True, contents)
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[MULTI-GEN] Streaming failed: {error_msg}")
            raise ValueError(f"Multi-generation streaming failed: {error_msg}")
    
    async def _generate_multi_completions(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> List[str]:
        """
        Non-streaming helper for n > 1 completions.
        
        Returns:
            List of n completion contents
        """
        client = self.get_user_client(user_id, user_settings)
        
        # Inject NSFW filter into system message if needed (SAME as _generate_stream_with_messages)
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if should_inject_nsfw_filter(user_allow_nsfw):
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"[MULTI-GEN] NSFW filter injected for user {user_id}")
        
        # Get generation params and add n parameter
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        # Add n to extra_body
        if "extra_body" not in gen_params:
            gen_params["extra_body"] = {}
        gen_params["extra_body"]["n"] = n
        
        # Get timeout from user settings
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total
        
        logger.info(f"[MULTI-GEN] Starting non-streaming with n={n}")
        
        try:
            response = await acompletion(**gen_params)
            
            # Extract content from each choice
            contents = []
            for choice in response.choices:
                content = choice.message.content if hasattr(choice.message, 'content') else ""
                contents.append(content)
            
            logger.info(f"[MULTI-GEN] Non-streaming complete: {len(contents)} completions")
            return contents
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[MULTI-GEN] Non-streaming failed: {error_msg}")
            raise ValueError(f"Multi-generation failed: {error_msg}")
    
    async def generate_scene_with_choices_streaming_multi(
        self, 
        context: Dict[str, Any], 
        user_id: int, 
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[Dict[str, Any]]]], None]:
        """
        Generate n scene variants with choices in a single streaming call (Combined + Streaming).
        
        Streams the first variant to the frontend while accumulating all n variants.
        Each variant's choices are parsed from its content.
        
        Yields:
            Tuple of (chunk, is_complete, variants_data)
            - During streaming: (chunk_text, False, None)
            - On completion: ("", True, [{"content": str, "choices": list}, ...])
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get scene length, choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get POV and prose style from writing preset
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Build system prompt (same as single generation)
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # Calculate max tokens
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        # Build messages
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Get task instruction
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        if not separate_choice_generation:
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN SCENE] Starting combined streaming with n={n}")
        
        # Track streaming content for first variant (index 0)
        streaming_buffer = ""
        found_marker_in_stream = False
        
        async for chunk, is_complete, contents in self._generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                # Stream chunk from index 0 to frontend
                streaming_buffer += chunk
                
                # Check for marker in streaming buffer
                if not found_marker_in_stream and CHOICES_MARKER in streaming_buffer:
                    # Only yield content before the marker
                    parts = streaming_buffer.split(CHOICES_MARKER, 1)
                    yield (parts[0], False, None)
                    found_marker_in_stream = True
                elif not found_marker_in_stream:
                    # Keep buffer small, yield excess
                    if len(streaming_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(streaming_buffer) - len(CHOICES_MARKER)
                        yield (streaming_buffer[:excess_length], False, None)
                        streaming_buffer = streaming_buffer[excess_length:]
            else:
                # Streaming complete - process all n contents
                variants_data = []
                
                for idx, content in enumerate(contents):
                    # Clean the content
                    cleaned_content = self._clean_scene_content(content)
                    
                    # Extract scene and choices
                    scene_content, parsed_choices = self._extract_choices_from_response_end(cleaned_content)
                    
                    # If separate_choice_generation is enabled, discard inline choices
                    if separate_choice_generation:
                        parsed_choices = None
                    
                    variants_data.append({
                        "content": scene_content.strip(),
                        "choices": parsed_choices or []
                    })
                    
                    logger.info(f"[MULTI-GEN SCENE] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")
                
                yield ("", True, variants_data)
    
    async def generate_scene_with_choices_multi(
        self, 
        context: Dict[str, Any], 
        user_id: int, 
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[Dict[str, Any]]:
        """
        Generate n scene variants with choices in a single non-streaming call (Combined + Non-streaming).
        
        Returns:
            List of dicts: [{"content": str, "choices": list}, ...]
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get scene settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get POV and prose style
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Build system prompt
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        # Build messages
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        if not separate_choice_generation:
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN SCENE] Starting combined non-streaming with n={n}")
        
        # Get all completions
        contents = await self._generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )
        
        # Process each completion
        variants_data = []
        for idx, content in enumerate(contents):
            cleaned_content = self._clean_scene_content(content)
            scene_content, parsed_choices = self._extract_choices_from_response_end(cleaned_content)
            
            if separate_choice_generation:
                parsed_choices = None
            
            variants_data.append({
                "content": scene_content.strip(),
                "choices": parsed_choices or []
            })
            
            logger.info(f"[MULTI-GEN SCENE] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")
        
        return variants_data
    
    async def generate_scene_streaming_multi(
        self, 
        context: Dict[str, Any], 
        user_id: int, 
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate n scene variants without choices (Separate + Streaming).
        
        Yields:
            Tuple of (chunk, is_complete, contents_list)
            - During streaming: (chunk_text, False, None)
            - On completion: ("", True, [content_0, ..., content_n-1])
        """
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Build system prompt with skip_choices=True
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=True  # Don't include choices in generation
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        # Don't add choices reminder - separate generation
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN SCENE] Starting separate streaming with n={n}")
        
        async for chunk, is_complete, contents in self._generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                yield (chunk, False, None)
            else:
                # Clean all contents
                cleaned_contents = [self._clean_scene_content(c).strip() for c in contents]
                yield ("", True, cleaned_contents)
    
    async def generate_scene_multi(
        self, 
        context: Dict[str, Any], 
        user_id: int, 
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[str]:
        """
        Generate n scene variants without choices (Separate + Non-streaming).
        
        Returns:
            List of scene contents
        """
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=True
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN SCENE] Starting separate non-streaming with n={n}")
        
        contents = await self._generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )
        
        return [self._clean_scene_content(c).strip() for c in contents]
    
    async def generate_choices_for_variants(
        self,
        scene_contents: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session]
    ) -> List[List[str]]:
        """
        Generate choices for multiple scene variants in parallel.
        
        Args:
            scene_contents: List of scene content strings
            context: Scene generation context
            user_id: User ID
            user_settings: User settings dict
            db: Database session
            
        Returns:
            List of choice lists, one per scene content
        """
        import asyncio
        
        logger.info(f"[MULTI-GEN CHOICES] Generating choices for {len(scene_contents)} variants in parallel")
        
        # Create tasks for parallel execution
        tasks = [
            self.generate_choices(content, context, user_id, user_settings, db)
            for content in scene_contents
        ]
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results, converting exceptions to empty lists
        all_choices = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[MULTI-GEN CHOICES] Failed for variant {idx}: {result}")
                all_choices.append([])
            else:
                all_choices.append(result)
                logger.info(f"[MULTI-GEN CHOICES] Variant {idx}: {len(result)} choices")
        
        return all_choices
    
    async def generate_concluding_scene_streaming_multi(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate n concluding scene variants (streaming, no choices).
        
        Yields:
            Tuple of (chunk, is_complete, contents_list)
        """
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        scene_length_description = self._get_scene_length_description(scene_length)
        
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Build system prompt for concluding scene
        system_prompt = prompt_manager.get_prompt(
            "chapter_conclusion", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Build task instruction for chapter conclusion
        task_content = prompt_manager.get_prompt(
            "chapter_conclusion", "user",
            user_id=user_id,
            db=db,
            chapter_number=chapter_info.get("chapter_number", 1),
            chapter_title=chapter_info.get("chapter_title", ""),
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN CONCLUSION] Starting streaming with n={n}")
        
        async for chunk, is_complete, contents in self._generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                yield (chunk, False, None)
            else:
                cleaned_contents = [self._clean_scene_content(c).strip() for c in contents]
                yield ("", True, cleaned_contents)
    
    async def generate_concluding_scene_multi(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[str]:
        """
        Generate n concluding scene variants (non-streaming, no choices).
        
        Returns:
            List of scene contents
        """
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        scene_length_description = self._get_scene_length_description(scene_length)
        
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        system_prompt = prompt_manager.get_prompt(
            "chapter_conclusion", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        task_content = prompt_manager.get_prompt(
            "chapter_conclusion", "user",
            user_id=user_id,
            db=db,
            chapter_number=chapter_info.get("chapter_number", 1),
            chapter_title=chapter_info.get("chapter_title", ""),
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN CONCLUSION] Starting non-streaming with n={n}")
        
        contents = await self._generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )
        
        return [self._clean_scene_content(c).strip() for c in contents]
    
    async def regenerate_scene_variant_streaming_multi(
        self,
        db: Session,
        scene_id: int,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        custom_prompt: Optional[str] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[Dict[str, Any]]]], None]:
        """
        Regenerate n scene variants with choices (streaming).
        Uses the same context as the original scene.
        
        Yields:
            Tuple of (chunk, is_complete, variants_data)
        """
        CHOICES_MARKER = "###CHOICES###"
        
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Build system prompt
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Add custom prompt or regeneration instruction
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        
        if custom_prompt and custom_prompt.strip():
            task_content = f"Regenerate the scene with the following guidance: {custom_prompt.strip()}\n\n"
            task_content += prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
        else:
            task_content = "Regenerate this scene with a fresh take, maintaining the same context but with different creative choices.\n\n"
            task_content += prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
        
        if not separate_choice_generation:
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN VARIANT] Starting streaming regeneration with n={n} for scene {scene_id}")
        
        streaming_buffer = ""
        found_marker_in_stream = False
        
        async for chunk, is_complete, contents in self._generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                streaming_buffer += chunk
                
                if not found_marker_in_stream and CHOICES_MARKER in streaming_buffer:
                    parts = streaming_buffer.split(CHOICES_MARKER, 1)
                    yield (parts[0], False, None)
                    found_marker_in_stream = True
                elif not found_marker_in_stream:
                    if len(streaming_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(streaming_buffer) - len(CHOICES_MARKER)
                        yield (streaming_buffer[:excess_length], False, None)
                        streaming_buffer = streaming_buffer[excess_length:]
            else:
                variants_data = []
                
                for idx, content in enumerate(contents):
                    cleaned_content = self._clean_scene_content(content)
                    scene_content, parsed_choices = self._extract_choices_from_response_end(cleaned_content)
                    
                    if separate_choice_generation:
                        parsed_choices = None
                    
                    variants_data.append({
                        "content": scene_content.strip(),
                        "choices": parsed_choices or []
                    })
                    
                    logger.info(f"[MULTI-GEN VARIANT] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")
                
                yield ("", True, variants_data)
    
    async def regenerate_scene_variant_multi(
        self,
        db: Session,
        scene_id: int,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        custom_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Regenerate n scene variants with choices (non-streaming).
        
        Returns:
            List of dicts: [{"content": str, "choices": list}, ...]
        """
        CHOICES_MARKER = "###CHOICES###"
        
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        
        if custom_prompt and custom_prompt.strip():
            task_content = f"Regenerate the scene with the following guidance: {custom_prompt.strip()}\n\n"
            task_content += prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
        else:
            task_content = "Regenerate this scene with a fresh take, maintaining the same context but with different creative choices.\n\n"
            task_content += prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
        
        if not separate_choice_generation:
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[MULTI-GEN VARIANT] Starting non-streaming regeneration with n={n} for scene {scene_id}")
        
        contents = await self._generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )
        
        variants_data = []
        for idx, content in enumerate(contents):
            cleaned_content = self._clean_scene_content(content)
            scene_content, parsed_choices = self._extract_choices_from_response_end(cleaned_content)
            
            if separate_choice_generation:
                parsed_choices = None
            
            variants_data.append({
                "content": scene_content.strip(),
                "choices": parsed_choices or []
            })
            
            logger.info(f"[MULTI-GEN VARIANT] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")
        
        return variants_data
    
    # =====================================================================
    # END OF MULTI-GENERATION METHODS
    # =====================================================================
    
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
    
    async def generate_choices(self, scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> List[str]:
        """
        Generate narrative choices for the given scene.
        
        Uses the SAME multi-message structure as scene generation for maximum cache hits.
        Messages 1-N are identical to scene generation (system prompt, foundation, chapter,
        entity states, scene batches). Only the final message differs (new scene + choice request).
        """
        
        # Override reasoning_effort to "disabled" for choice generation
        # Reasoning models waste tokens on thinking, leaving nothing for actual choices
        # This ensures choices are generated directly without consuming tokens on reasoning
        import copy
        choice_user_settings = copy.deepcopy(user_settings)
        if 'llm_settings' in choice_user_settings:
            choice_user_settings['llm_settings']['reasoning_effort'] = 'disabled'
        else:
            choice_user_settings['reasoning_effort'] = 'disabled'
        logger.info("[CHOICES] Overriding reasoning_effort to 'disabled' for choice generation")
        
        # Get POV from writing preset (SAME as scene generation - critical for cache hits)
        pov = 'third'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
        
        # Get choices count, scene length, and separate_choice_generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length = generation_prefs.get("scene_length", "medium")
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_map = {"short": "short (50-100 words)", "medium": "medium (100-150 words)", "long": "long (150-250 words)"}
        scene_length_description = scene_length_map.get(scene_length, "medium (100-150 words)")
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION ===
        # This ensures the system message is identical and cacheable
        # Use get_prompt instead of get_prompt_pair to avoid user prompt template errors
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Add POV consistency requirement to system prompt (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        # DO NOT modify context before this call - must be identical to scene generation
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        # Instead of task instruction, we send the new scene + choice generation request
        # Clean scene content to remove any instruction tags or formatting artifacts
        cleaned_scene_content = self._clean_instruction_tags(scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)
        
        # Build POV instruction string for template substitution
        if pov == "first":
            pov_instruction = "in first person perspective (using 'I', 'me', 'my')"
        elif pov == "second":
            pov_instruction = "in second person perspective (using 'you', 'your')"
        else:  # third or default
            pov_instruction = "in third person perspective (using 'he', 'she', 'they', character names)"
        
        # Use choice_generation.user template from YAML instead of hardcoded text
        final_message = prompt_manager.get_prompt(
            "choice_generation", "user",
            scene_content=cleaned_scene_content,
            choices_count=choices_count,
            pov_instruction=pov_instruction
        )
        
        messages.append({"role": "user", "content": final_message})
        
        # Calculate max tokens - use YAML settings or user settings
        base_max_tokens = prompt_manager.get_max_tokens("choice_generation", user_settings)
        # Ensure at least enough tokens for the requested number of choices
        dynamic_max_tokens = max(base_max_tokens, choices_count * 75)
        max_tokens = dynamic_max_tokens
        
        logger.info(f"[CHOICES] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output to prompt_choice_sent.json for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_choice_sent.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write choice prompt debug file: {e}")
        
        # Use the multi-message generation method with reasoning disabled
        response = await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=choice_user_settings,  # Use modified settings with reasoning disabled
            max_tokens=max_tokens
        )
        
        # Parse choices from response using JSON format
        choices = self._parse_choices_from_json(response)
        
        # If parsing failed or we don't have enough choices, return empty list
        # This signals to the API layer that choice generation failed
        if not choices or len(choices) < 2:
            logger.warning(f"[CHOICES] Failed to parse choices from JSON. Response: {response[:200]}")
            return []
        
        return choices
    
    async def generate_scenario(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a creative scenario based on user selections and characters"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "scenario_generation", "scenario_generation",
            context=self._format_context_for_scenario(context),
            elements=self._format_elements_for_scenario(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scenario", user_settings)
        
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
            max_tokens = prompt_manager.get_max_tokens("complete_plot", user_settings)
        else:
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "plot_generation", "single_plot_point",
                context=self._format_context_for_plot(context),
                point_name=self._get_plot_point_name(context.get("plot_point_index", 0))
            )
            max_tokens = prompt_manager.get_max_tokens("single_plot_point", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Log raw LLM response for debugging
        logger.warning("=" * 80)
        logger.warning("RAW LLM RESPONSE - PLOT GENERATION")
        logger.warning("=" * 80)
        logger.warning(f"Plot Type: {plot_type}")
        logger.warning(f"Response Length: {len(response)} characters")
        logger.warning("-" * 80)
        logger.warning(f"RAW RESPONSE:\n{response}")
        logger.warning("=" * 80)
        
        if plot_type == "complete":
            parsed_points = self._parse_plot_points_json(response)
            return parsed_points
        else:
            return [response]
    
    async def generate_summary(self, story_content: str, story_context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a comprehensive story summary
        
        Can use either the main LLM or the extraction LLM based on user settings.
        If use_extraction_llm_for_summary is True and extraction model is enabled,
        uses the extraction model for faster (but potentially lower quality) summaries.
        """
        
        # Check if user wants to use extraction LLM for summaries
        use_extraction_llm = user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False)
        extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False)
        
        # Try extraction LLM if requested and enabled
        if use_extraction_llm and extraction_enabled:
            try:
                from .extraction_service import ExtractionLLMService
                
                logger.info(f"[SUMMARY] Using extraction LLM for summary generation (user_id={user_id})")
                
                # Get extraction model settings
                ext_settings = user_settings.get('extraction_model_settings', {})
                extraction_service = ExtractionLLMService(
                    url=ext_settings.get('url', 'http://localhost:1234/v1'),
                    model=ext_settings.get('model_name', 'qwen2.5-3b-instruct'),
                    api_key=ext_settings.get('api_key', ''),
                    temperature=ext_settings.get('temperature', 0.3),
                    max_tokens=ext_settings.get('max_tokens', 1000)
                )
                
                # Get prompts from centralized prompt manager
                system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                    "story_summary", "story_summary",
                    story_context=self._format_context_for_summary(story_context),
                    story_content=story_content
                )
                
                max_tokens = prompt_manager.get_max_tokens("story_summary", user_settings)
                
                # Generate summary with extraction model
                summary = await extraction_service.generate_summary(
                    story_content=story_content,
                    story_context=self._format_context_for_summary(story_context),
                    system_prompt=system_prompt,
                    max_tokens=max_tokens
                )
                
                logger.info(f"[SUMMARY] Successfully generated summary with extraction LLM (user_id={user_id}, length={len(summary)})")
                return summary.strip()
                
            except Exception as e:
                logger.warning(f"[SUMMARY] Extraction LLM failed, falling back to main LLM: {e}")
                # Fall through to main LLM
        
        # Use main LLM (default behavior or fallback)
        logger.info(f"[SUMMARY] Using main LLM for summary generation (user_id={user_id})")
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_summary", "story_summary",
            story_context=self._format_context_for_summary(story_context),
            story_content=story_content
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_summary", user_settings)
        
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
    
    def _get_scene_length_description(self, scene_length: str) -> str:
        """Convert scene_length setting to word range description"""
        length_map = {
            "short": "approximately 100-150 words",
            "medium": "approximately 200-300 words", 
            "long": "approximately 400-500 words"
        }
        return length_map.get(scene_length, "approximately 200-300 words")
    
    def _format_characters_section(self, characters: Any, include_voice_style: bool = True) -> str:
        """
        Format characters section for context.
        
        Args:
            characters: Either a list of character dicts or a dict with active_characters/inactive_characters
            include_voice_style: Whether to include voice style in character descriptions (default: True)
            
        Returns:
            Formatted characters string
        """
        if not characters:
            return ""
        
        char_descriptions = []
        
        # Check if characters is a dict with active_characters/inactive_characters
        if isinstance(characters, dict) and "active_characters" in characters:
            active_chars = characters.get("active_characters", [])
            inactive_chars = characters.get("inactive_characters", [])
            
            # Active characters - full details
            if active_chars:
                char_descriptions.append("Active Characters (in this chapter):")
                for char in active_chars:
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
                    if char.get('fears'):
                        char_desc += f". Fears & Weaknesses: {char['fears']}"
                    if char.get('appearance'):
                        char_desc += f". Appearance: {char['appearance']}"
                    # Add voice/speech style if specified and requested
                    if include_voice_style and char.get('voice_style'):
                        voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                        if voice_instruction:
                            char_desc += f"\n  {voice_instruction}"
                    char_descriptions.append(char_desc)
            
            # Inactive characters - brief format
            if inactive_chars:
                char_descriptions.append("\nInactive Characters (available for reference):")
                for char in inactive_chars:
                    char_desc = f"- {char.get('name', 'Unknown')}"
                    if char.get('role'):
                        char_desc += f" ({char['role']})"
                    char_descriptions.append(char_desc)
        else:
            # Legacy format - list of character dicts
            for char in characters:
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
                if char.get('fears'):
                    char_desc += f". Fears & Weaknesses: {char['fears']}"
                if char.get('appearance'):
                    char_desc += f". Appearance: {char['appearance']}"
                # Add voice/speech style if specified and requested
                if include_voice_style and char.get('voice_style'):
                    voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                    if voice_instruction:
                        char_desc += f"\n  {voice_instruction}"
                char_descriptions.append(char_desc)
        
        if char_descriptions:
            return f"Characters:\n{chr(10).join(char_descriptions)}"
        return ""
    
    def _format_character_voice_styles(self, characters: Any) -> str:
        """
        Format character voice/dialogue styles as a separate section.
        
        This creates a dedicated, prominent section for character dialogue instructions
        to ensure the LLM follows them.
        
        Args:
            characters: Either a list of character dicts or a dict with active_characters/inactive_characters
            
        Returns:
            Formatted voice styles string, or empty string if no voice styles defined
        """
        if not characters:
            return ""
        
        voice_styles = []
        
        # Get all characters (active only for voice styles)
        if isinstance(characters, dict) and "active_characters" in characters:
            chars_to_process = characters.get("active_characters", [])
        else:
            chars_to_process = characters if isinstance(characters, list) else []
        
        for char in chars_to_process:
            if char.get('voice_style'):
                voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                if voice_instruction:
                    char_name = char.get('name', 'Unknown')
                    voice_styles.append(f"{char_name}:\n  {voice_instruction}")
        
        if voice_styles:
            return "\n\n".join(voice_styles)
        return ""
    
    def _format_context_as_messages(self, context: Dict[str, Any], scene_batch_size: int = 10) -> List[Dict[str, str]]:
        """
        Format context as multiple user messages for better LLM cache utilization.
        
        By splitting context into multiple user messages, we improve cache hit rates:
        - Earlier messages (story foundation, chapter summaries) remain stable
        - Only later messages (semantic events, recent scenes) change frequently
        - Scenes are batched into groups aligned with extraction intervals for optimal caching
        - Semantic events placed between completed batches and recent scenes to avoid invalidating batch caches
        
        Message order (most stable → most dynamic):
        1. Story Foundation: genre, tone, setting, scenario, characters
        2. Chapter Context: story_so_far, previous/current chapter summaries
        3. Entity States: character states, locations, objects
        4. Scene Batches: completed scene batches (stable per batch)
        5. Semantic Events: relevant past events from semantic search (changes each generation)
        6. Recent Scenes: active batch of most recent scenes (changes each scene) ← Most relevant, closest to instruction
        
        Order ensures: Past scenes → Past events → Most recent scenes
        
        Args:
            context: Context dictionary from context_manager
            scene_batch_size: Number of scenes per batch for caching optimization (default: 10)
            
        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        messages = []
        
        # === MESSAGE 1: Story Foundation (stable per story) ===
        foundation_parts = []
        
        if context.get("genre"):
            foundation_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            foundation_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            foundation_parts.append(f"Setting: {context['world_setting']}")
        
        if context.get("scenario"):
            foundation_parts.append(f"Story Scenario: {context['scenario']}")
        
        if context.get("initial_premise"):
            foundation_parts.append(f"Initial Premise: {context['initial_premise']}")
        
        # Characters section (without voice styles - those go in a separate message)
        characters = context.get("characters")
        if characters:
            char_text = self._format_characters_section(characters, include_voice_style=False)
            if char_text:
                foundation_parts.append(char_text)
        
        # Chapter metadata (stable per chapter)
        if context.get("chapter_location"):
            foundation_parts.append(f"Chapter Location: {context['chapter_location']}")
        if context.get("chapter_time_period"):
            foundation_parts.append(f"Chapter Time Period: {context['chapter_time_period']}")
        if context.get("chapter_scenario"):
            foundation_parts.append(f"Chapter Scenario: {context['chapter_scenario']}")
        
        if foundation_parts:
            messages.append({
                "role": "user",
                "content": "=== STORY FOUNDATION ===\n" + "\n\n".join(foundation_parts)
            })
        
        # === MESSAGE 1.5: Character Dialogue Styles (separate for prominence) ===
        # This is placed in its own message to ensure the LLM treats voice styles as important
        if characters:
            voice_styles_text = self._format_character_voice_styles(characters)
            if voice_styles_text:
                messages.append({
                    "role": "user",
                    "content": "=== CHARACTER DIALOGUE STYLES ===\nIMPORTANT: Each character below has a specific way of speaking. You MUST write their dialogue following these instructions exactly.\n\n" + voice_styles_text
                })
        
        # === MESSAGE 2: Chapter Summaries (stable per chapter, changes on summary updates) ===
        summary_parts = []
        
        if context.get("story_so_far"):
            summary_parts.append(f"Story So Far:\n{context['story_so_far']}")
        
        if context.get("previous_chapter_summary"):
            summary_parts.append(f"Previous Chapter Summary:\n{context['previous_chapter_summary']}")
        
        if context.get("current_chapter_summary"):
            summary_parts.append(f"Current Chapter Summary:\n{context['current_chapter_summary']}")
        
        if summary_parts:
            messages.append({
                "role": "user", 
                "content": "=== CHAPTER CONTEXT ===\n" + "\n\n".join(summary_parts)
            })
        
        # === MESSAGE 2.5: Chapter Plot Guidance (from brainstorming) ===
        chapter_plot = context.get("chapter_plot")
        arc_phase = context.get("arc_phase")
        
        if chapter_plot or arc_phase:
            plot_parts = []
            
            if arc_phase:
                plot_parts.append(f"Story Arc Phase: {arc_phase.get('name', 'Unknown')}")
                if arc_phase.get('description'):
                    plot_parts.append(f"Phase Goal: {arc_phase['description']}")
            
            if chapter_plot:
                if chapter_plot.get('summary'):
                    plot_parts.append(f"Chapter Summary: {chapter_plot['summary']}")
                if chapter_plot.get('key_events'):
                    events = chapter_plot['key_events']
                    if isinstance(events, list):
                        # Format as story beats, not a checklist
                        events_formatted = "\n  - ".join(events)
                        plot_parts.append(f"Story Beats (weave in naturally across scenes):\n  - {events_formatted}")
                if chapter_plot.get('climax'):
                    plot_parts.append(f"Building Toward: {chapter_plot['climax']}")
                if chapter_plot.get('resolution'):
                    plot_parts.append(f"Chapter Resolution: {chapter_plot['resolution']}")
            
            if plot_parts:
                # Get header and footer from prompts.yml
                header = prompt_manager.get_raw_prompt("pacing.chapter_plot_header") or "=== CHAPTER PLOT GUIDANCE ==="
                footer = prompt_manager.get_raw_prompt("pacing.chapter_plot_footer") or ""
                
                messages.append({
                    "role": "user",
                    "content": header.strip() + "\n" + "\n".join(plot_parts) + footer
                })
        
        # === MESSAGES 3+: Scene Batches (batch-aligned for optimal caching) ===
        # Note: Entity states and relevant events are now combined in "Relevant Context" section
        # which is placed immediately before Recent Scenes
        previous_scenes_text = context.get("previous_scenes", "")
        
        # Extract the combined "Relevant Context" section (contains semantic events + entity states)
        # This is the new format from SemanticContextManager
        relevant_context_match = None
        interaction_history_match = None
        if previous_scenes_text:
            relevant_context_match = re.search(
                r'Relevant Context:\n(.*?)(?=\n\nRecent Scenes:|$)',
                previous_scenes_text, re.DOTALL
            )
            # Extract CHARACTER INTERACTION HISTORY (placed before Relevant Context)
            interaction_history_match = re.search(
                r'CHARACTER INTERACTION HISTORY:\n(.*?)(?=\n\nRelevant Context:|\n\nRecent Scenes:|$)',
                previous_scenes_text, re.DOTALL
            )
        
        if previous_scenes_text:
            # Extract recent scenes section
            recent_match = re.search(r'Recent Scenes:(.*?)$', previous_scenes_text, re.DOTALL)
            if recent_match:
                scenes_text = recent_match.group(1).strip()
                scene_messages = self._batch_scenes_as_messages(scenes_text, scene_batch_size)
                
                # Separate completed batches from the active "Recent Scenes" batch
                # The last message in scene_messages is always the "Recent Scenes" batch
                if len(scene_messages) > 1:
                    # We have both completed batches and recent scenes
                    completed_batches = scene_messages[:-1]  # All except the last
                    recent_scenes_batch = scene_messages[-1]  # The last one (Recent Scenes)
                    
                    # Add completed batches first
                    messages.extend(completed_batches)
                    
                    # Add Character Interaction History (stable, placed before Relevant Context for cache optimization)
                    if interaction_history_match:
                        messages.append({
                            "role": "user",
                            "content": "=== CHARACTER INTERACTION HISTORY ===\n(Factual record of what has occurred between characters)\n\n" + interaction_history_match.group(1).strip()
                        })
                    
                    # Add Relevant Context (combined semantic + entity states) before recent scenes
                    if relevant_context_match:
                        messages.append({
                            "role": "user",
                            "content": "=== RELEVANT CONTEXT ===\n" + relevant_context_match.group(1).strip()
                        })
                    
                    # Add recent scenes last (most relevant, closest to instruction)
                    messages.append(recent_scenes_batch)
                elif len(scene_messages) == 1:
                    # Only one batch (the recent scenes batch)
                    # Add Character Interaction History before Relevant Context if it exists
                    if interaction_history_match:
                        messages.append({
                            "role": "user",
                            "content": "=== CHARACTER INTERACTION HISTORY ===\n(Factual record of what has occurred between characters)\n\n" + interaction_history_match.group(1).strip()
                        })
                    # Add Relevant Context before it if it exists
                    if relevant_context_match:
                        messages.append({
                            "role": "user",
                            "content": "=== RELEVANT CONTEXT ===\n" + relevant_context_match.group(1).strip()
                        })
                    messages.extend(scene_messages)
                else:
                    # No scene messages (shouldn't happen, but handle gracefully)
                    messages.extend(scene_messages)
            elif not relevant_context_match and not interaction_history_match:
                # No structured sections found, use the whole previous_scenes as-is
                # This handles the case where context_manager returns simple scene list
                messages.append({
                    "role": "user",
                    "content": "=== STORY PROGRESS ===\n" + previous_scenes_text
                })
            else:
                # We have relevant_context_match or interaction_history_match but no recent scenes
                if interaction_history_match:
                    messages.append({
                        "role": "user",
                        "content": "=== CHARACTER INTERACTION HISTORY ===\n(Factual record of what has occurred between characters)\n\n" + interaction_history_match.group(1).strip()
                    })
                if relevant_context_match:
                    messages.append({
                        "role": "user",
                        "content": "=== RELEVANT CONTEXT ===\n" + relevant_context_match.group(1).strip()
                    })
        
        # Add pacing guidance at the end (dynamic, changes each scene)
        # This is placed AFTER all cached messages to preserve cache hits
        pacing_guidance = context.get("pacing_guidance")
        if pacing_guidance:
            messages.append({
                "role": "user",
                "content": f"=== CURRENT PROGRESS ===\n{pacing_guidance}"
            })
        
        return messages
    
    def _batch_scenes_as_messages(self, scenes_text: str, batch_size: int = 10) -> List[Dict[str, str]]:
        """
        Parse scenes and group them into batch-aligned messages for optimal caching.
        
        Context manager now provides batch-aligned scenes, so:
        - All batches except the last are complete (have all scenes from batch_start to batch_end)
        - The last batch is the "active" batch that changes each scene
        
        Complete batches use fixed headers (=== SCENES 41-50 ===) for stable caching.
        Active batch uses fixed header (=== RECENT SCENES ===) for stable caching.
        
        Args:
            scenes_text: Raw text containing scenes in format "Scene XX: content"
            batch_size: Number of scenes per batch (default: 10)
            
        Returns:
            List of message dicts, one per batch
        """
        messages = []
        
        # Parse individual scenes using regex
        # Pattern matches "Scene XX:" followed by content until next "Scene XX:" or end
        scene_pattern = re.compile(r'Scene\s+(\d+):\s*(.*?)(?=Scene\s+\d+:|$)', re.DOTALL)
        matches = list(scene_pattern.finditer(scenes_text))
        
        if not matches:
            # No scene pattern found, return as single message
            if scenes_text.strip():
                messages.append({
                    "role": "user",
                    "content": "=== RECENT SCENES ===\n" + scenes_text.strip()
                })
            return messages
        
        # Group scenes by batch
        # Batch boundaries: 1-10, 11-20, 21-30, etc. (based on scene numbers, not indices)
        batches: Dict[int, List[Tuple[int, str]]] = {}
        
        for match in matches:
            scene_num = int(match.group(1))
            scene_content = match.group(2).strip()
            
            # Calculate batch number (0-indexed): scenes 1-10 -> batch 0, 11-20 -> batch 1, etc.
            batch_num = (scene_num - 1) // batch_size
            
            if batch_num not in batches:
                batches[batch_num] = []
            batches[batch_num].append((scene_num, scene_content))
        
        if not batches:
            return messages
        
        # Sort batches by batch number
        sorted_batch_nums = sorted(batches.keys())
        
        # The last batch in sorted order is the active batch (changes each scene)
        # All other batches are complete and stable (context_manager guarantees this)
        last_batch_idx = len(sorted_batch_nums) - 1
        
        for idx, batch_num in enumerate(sorted_batch_nums):
            scenes_in_batch = batches[batch_num]
            # Sort scenes within batch by scene number
            scenes_in_batch.sort(key=lambda x: x[0])
            
            # Calculate FIXED batch range based on batch number
            # Batch 4 is always scenes 41-50, batch 5 is always 51-60, etc.
            batch_start = batch_num * batch_size + 1
            batch_end = batch_start + batch_size - 1
            
            # Get actual scene numbers in this batch
            actual_scene_nums = [s[0] for s in scenes_in_batch]
            actual_start = min(actual_scene_nums)
            actual_end = max(actual_scene_nums)
            
            # Format scenes without "Scene X:" prefix to avoid teaching LLM bad habits
            formatted_scenes = []
            for scene_num, content in scenes_in_batch:
                formatted_scenes.append(content)
            
            batch_content = "\n\n".join(formatted_scenes)
            
            # Last batch is always the active batch (changes each scene)
            # All other batches are complete and stable (context_manager guarantees this)
            is_active_batch = (idx == last_batch_idx)
            
            if is_active_batch:
                # Active batch - use FIXED header for stable caching (scene numbers change content, not header)
                header = f"=== RECENT SCENES ==="
            else:
                # Complete batch - use FIXED batch boundaries for stable caching
                header = f"=== SCENES {batch_start}-{batch_end} ==="
            
            messages.append({
                "role": "user",
                "content": f"{header}\n{batch_content}"
            })
        
        logger.debug(f"[SCENE BATCHING] Created {len(messages)} batch messages from {len(matches)} scenes (batch_size={batch_size})")
        
        return messages
    
    def _format_context_for_scene(self, context: Dict[str, Any], exclude_last_scene: bool = False) -> str:
        """Format context for scene generation, handling active/inactive characters
        
        Args:
            context: Context dictionary
            exclude_last_scene: If True, exclude the most recent scene from previous_scenes
                              (used for guided enhancement to avoid duplication)
        """
        context_parts = []
        
        # Check if this is the first scene with user prompt
        is_first_scene = context.get("is_first_scene", False)
        user_prompt_provided = context.get("user_prompt_provided", False)
        enhancement_guidance = context.get("enhancement_guidance", "")
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            context_parts.append(f"Setting: {context['world_setting']}")
        
        # For first scene with user prompt, prioritize user prompt over scenario
        if is_first_scene and user_prompt_provided and context.get("current_situation"):
            # User prompt takes precedence for first scene
            if context.get("scenario"):
                context_parts.append(f"Story Scenario (for reference): {context['scenario']}")
        else:
            # Normal order: scenario first
            if context.get("scenario"):
                context_parts.append(f"Story Scenario: {context['scenario']}")
        
        if context.get("initial_premise"):
            context_parts.append(f"Initial Premise: {context['initial_premise']}")
        
        # Handle characters - check if we have active/inactive separation
        characters = context.get("characters")
        if characters:
            # Check if characters is a dict with active_characters/inactive_characters
            if isinstance(characters, dict) and "active_characters" in characters:
                # Format active and inactive characters separately
                active_chars = characters.get("active_characters", [])
                inactive_chars = characters.get("inactive_characters", [])
                
                char_descriptions = []
                
                # Active characters - full details
                if active_chars:
                    char_descriptions.append("Active Characters (in this chapter):")
                    for char in active_chars:
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
                        if char.get('fears'):
                            char_desc += f". Fears & Weaknesses: {char['fears']}"
                        if char.get('appearance'):
                            char_desc += f". Appearance: {char['appearance']}"
                        # Add voice/speech style if specified
                        if char.get('voice_style'):
                            voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                            if voice_instruction:
                                char_desc += f"\n  {voice_instruction}"
                        char_descriptions.append(char_desc)
                
                # Inactive characters - brief format
                if inactive_chars:
                    char_descriptions.append("\nInactive Characters (available for reference):")
                    for char in inactive_chars:
                        char_desc = f"- {char.get('name', 'Unknown')}"
                        if char.get('role'):
                            char_desc += f" ({char['role']})"
                        char_descriptions.append(char_desc)
                
                if char_descriptions:
                    context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
            else:
                # Legacy format - all characters are active
                char_descriptions = []
                for char in characters:
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
                    if char.get('fears'):
                        char_desc += f". Fears & Weaknesses: {char['fears']}"
                    if char.get('appearance'):
                        char_desc += f". Appearance: {char['appearance']}"
                    # Add voice/speech style if specified
                    if char.get('voice_style'):
                        voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                        if voice_instruction:
                            char_desc += f"\n  {voice_instruction}"
                    char_descriptions.append(char_desc)
                context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
        
        # Add chapter-specific context if available
        if context.get("chapter_location"):
            context_parts.append(f"Chapter Location: {context['chapter_location']}")
        if context.get("chapter_time_period"):
            context_parts.append(f"Chapter Time Period: {context['chapter_time_period']}")
        if context.get("chapter_scenario"):
            context_parts.append(f"Chapter Scenario: {context['chapter_scenario']}")
        
        # Add story_so_far if available (summary of all previous chapters)
        story_so_far = context.get("story_so_far")
        if story_so_far:
            logger.info(f"[CONTEXT FORMAT] Including story_so_far ({len(story_so_far)} chars)")
            context_parts.append(f"Story So Far:\n{story_so_far}")
        else:
            logger.info("[CONTEXT FORMAT] story_so_far is None or empty, not including")
        
        # Add previous chapter summary if available
        previous_chapter_summary = context.get("previous_chapter_summary")
        if previous_chapter_summary:
            logger.info(f"[CONTEXT FORMAT] Including previous_chapter_summary ({len(previous_chapter_summary)} chars)")
            context_parts.append(f"Previous Chapter Summary:\n{previous_chapter_summary}")
        else:
            logger.info("[CONTEXT FORMAT] previous_chapter_summary is None or empty, not including")
        
        # Add current chapter summary if available (summary of this chapter's progress so far)
        current_chapter_summary = context.get("current_chapter_summary")
        if current_chapter_summary:
            logger.info(f"[CONTEXT FORMAT] Including current_chapter_summary ({len(current_chapter_summary)} chars)")
            context_parts.append(f"Current Chapter Summary:\n{current_chapter_summary}")
        else:
            logger.info("[CONTEXT FORMAT] current_chapter_summary is None or empty, not including")
        
        # Parse and organize previous_scenes into clear sections
        if context.get("previous_scenes"):
            previous_scenes_text = context['previous_scenes']
            
            # Exclude last scene if requested (for guided enhancement)
            if exclude_last_scene and previous_scenes_text:
                import re
                # Find all scene markers (Scene N: pattern)
                # Match everything from "Scene N:" to either next "Scene M:" or end of string
                scene_pattern = r'(Scene \d+:.*?)(?=\n\nScene \d+:|$)'
                scenes = re.findall(scene_pattern, previous_scenes_text, re.DOTALL)
                
                if scenes:
                    # Find the position of the last scene in the original text
                    # Get all scene numbers to find the highest one
                    scene_numbers = []
                    for scene_text in scenes:
                        match = re.search(r'Scene (\d+):', scene_text)
                        if match:
                            scene_numbers.append((int(match.group(1)), scene_text))
                    
                    if scene_numbers:
                        # Sort by scene number and get the highest
                        scene_numbers.sort(key=lambda x: x[0])
                        last_scene_num, last_scene_text = scene_numbers[-1]
                        
                        # Remove the last scene from the text
                        # Find the position of the last scene and remove it
                        last_scene_start = previous_scenes_text.rfind(f"Scene {last_scene_num}:")
                        if last_scene_start != -1:
                            # Remove from the last scene marker to the end
                            # But preserve any content before it (like summaries)
                            previous_scenes_text = previous_scenes_text[:last_scene_start].rstrip()
                            logger.info(f"Excluded Scene {last_scene_num} from previous events for guided enhancement")
            
            # Parse previous_scenes_text into organized sections
            import re
            
            # Try NEW format first: "Relevant Context:" combined section
            relevant_context_match = re.search(r'Relevant Context:\n(.*?)(?=\n\nRecent Scenes:|$)', previous_scenes_text, re.DOTALL)
            recent_scenes_match = re.search(r'Recent Scenes:(.*?)$', previous_scenes_text, re.DOTALL)
            
            # Extract CHARACTER INTERACTION HISTORY (if present) - placed before Relevant Context for cache optimization
            interaction_history_match = re.search(r'CHARACTER INTERACTION HISTORY:\n(.*?)(?=\n\nRelevant Context:|$)', previous_scenes_text, re.DOTALL)
            interaction_history_content = interaction_history_match.group(0).strip() if interaction_history_match else None
            
            # Extract Current Chapter Summary (if present) - works with both old and new format
            current_chapter_summary_match = re.search(r'Current Chapter Summary[^:]*:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Context|CHARACTER INTERACTION HISTORY|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Active Objects)|$)', previous_scenes_text, re.DOTALL)
            current_chapter_summary = current_chapter_summary_match.group(1).strip() if current_chapter_summary_match else None
            
            if relevant_context_match:
                # NEW FORMAT: Combined "Relevant Context" section
                relevant_context_content = relevant_context_match.group(1).strip()
                recent_scenes_content = recent_scenes_match.group(1).strip() if recent_scenes_match else None
                
                # Add Current Chapter Progress (positioned before relevant context)
                if current_chapter_summary:
                    context_parts.append("Current Chapter Progress:")
                    context_parts.append(f"  Current Chapter Summary:\n  {current_chapter_summary.replace(chr(10), chr(10) + '  ')}")
                
                # Add Character Interaction History (stable, placed before Relevant Context for cache optimization)
                if interaction_history_content:
                    context_parts.append(f"\n{interaction_history_content}")
                
                # Add Relevant Context (combined semantic events + entity states)
                if relevant_context_content:
                    context_parts.append(f"\nRelevant Context:\n{relevant_context_content}")
                
                # Add Recent Scenes
                if recent_scenes_content:
                    context_parts.append(f"\nRecent Scenes:\n{recent_scenes_content}")
            else:
                # OLD FORMAT (backward compatibility): Separate sections
                recent_scenes_content = re.search(r'Recent Scenes:\s*(.*?)(?=\n+(?:Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
                recent_scenes_content = recent_scenes_content.group(1).strip() if recent_scenes_content else None
                
                # Extract Relevant Past Events (semantic search results)
                relevant_events_match = re.search(r'Relevant Past Events:\s*(.*?)(?=\n+(?:Recent Scenes|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
                relevant_events_content = relevant_events_match.group(1).strip() if relevant_events_match else None
                
                # Extract Entity States sections (may have leading newlines)
                entity_states_match = re.search(r'\n*(CURRENT CHARACTER STATES:.*?)(?=\n+(?:CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events)|$)', previous_scenes_text, re.DOTALL)
                entity_states_content = entity_states_match.group(1).strip() if entity_states_match else None
                
                locations_match = re.search(r'\n*CURRENT LOCATIONS:\s*(.*?)(?=\n+(?:IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES)|$)', previous_scenes_text, re.DOTALL)
                locations_content = locations_match.group(1).strip() if locations_match else None
                
                # Support both old and new object header names (may have leading newlines)
                objects_match = re.search(r'\n*(?:Notable Objects|Active Objects):\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
                if not objects_match:
                    objects_match = re.search(r'\n*IMPORTANT OBJECTS:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
                objects_content = objects_match.group(1).strip() if objects_match else None
                
                # Build organized context sections
                # Add Current State section if we have entity states
                if entity_states_content or locations_content or objects_content:
                    context_parts.append("Current State:")
                    
                    if entity_states_content:
                        context_parts.append(f"  {entity_states_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if locations_content:
                        context_parts.append(f"\n  CURRENT LOCATIONS:\n  {locations_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if objects_content:
                        context_parts.append(f"\n  Active Objects:\n  {objects_content.replace(chr(10), chr(10) + '  ')}")
                
                # Add Current Chapter Progress
                if current_chapter_summary or recent_scenes_content or relevant_events_content:
                    context_parts.append("\nCurrent Chapter Progress:")
                    
                    if current_chapter_summary:
                        context_parts.append(f"  Current Chapter Summary:\n  {current_chapter_summary.replace(chr(10), chr(10) + '  ')}")
                    
                    if relevant_events_content:
                        context_parts.append(f"\n  Relevant Past Events (from semantic search):\n  {relevant_events_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if recent_scenes_content:
                        context_parts.append(f"\n  Recent Scenes:\n  {recent_scenes_content.replace(chr(10), chr(10) + '  ')}")
                
                # If parsing failed, fall back to original format
                if not (current_chapter_summary or recent_scenes_content or relevant_events_content or entity_states_content):
                    context_parts.append(f"Previous Events:\n{previous_scenes_text}")
        
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
        
        if context.get("continuation_prompt"):
            context_parts.append(f"Continuation instruction: {context['continuation_prompt']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_choices(self, context: Dict[str, Any]) -> str:
        """Format context for choice generation
        CRITICAL: Reuse _format_context_for_scene() to ensure identical formatting
        This maximizes LLM cache hits by keeping the initial prompt parts identical
        """
        # Reuse the same formatting as scene generation to maximize cache hits
        return self._format_context_for_scene(context, exclude_last_scene=False)
    
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
    
    def _parse_plot_points_json(self, response: str) -> List[str]:
        """Parse plot points from JSON response"""
        plot_points = []
        
        logger.warning("=" * 80)
        logger.warning("PARSING PLOT POINTS FROM JSON")
        logger.warning("=" * 80)
        logger.warning(f"Input response length: {len(response)} characters")
        
        try:
            # Clean response - remove markdown code blocks if present
            response_clean = response.strip()
            
            # Remove markdown code blocks (```json ... ``` or ``` ... ```)
            if response_clean.startswith("```"):
                # Find the closing ```
                end_idx = response_clean.find("```", 3)
                if end_idx != -1:
                    response_clean = response_clean[3:end_idx].strip()
                    # Remove "json" if it's ```json
                    if response_clean.startswith("json"):
                        response_clean = response_clean[4:].strip()
            
            logger.warning(f"Cleaned response (first 200 chars): {response_clean[:200]}...")
            
            # Parse JSON
            try:
                data = json.loads(response_clean)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                logger.error(f"Response that failed to parse: {response_clean[:500]}")
                # Try to extract JSON from the response if it's embedded in text
                # Look for JSON object with plot_points key
                json_start = response_clean.find('{"plot_points"')
                if json_start == -1:
                    json_start = response_clean.find("{'plot_points'")
                if json_start != -1:
                    # Find matching closing brace
                    brace_count = 0
                    json_end = json_start
                    for i, char in enumerate(response_clean[json_start:], start=json_start):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    
                    if json_end > json_start:
                        json_str = response_clean[json_start:json_end]
                        logger.warning("Found JSON-like structure, attempting to parse...")
                        try:
                            # Replace single quotes with double quotes if needed
                            if "'" in json_str and '"' not in json_str:
                                json_str = json_str.replace("'", '"')
                            data = json.loads(json_str)
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Failed to parse extracted JSON: {json_err}")
                            raise ValueError(f"Failed to parse JSON from response: {e}")
                    else:
                        raise ValueError(f"Failed to parse JSON from response: {e}")
                else:
                    raise ValueError(f"Failed to parse JSON from response: {e}")
            
            # Extract plot_points from JSON
            if isinstance(data, dict) and "plot_points" in data:
                plot_points = data["plot_points"]
                if not isinstance(plot_points, list):
                    raise ValueError(f"plot_points is not a list, got {type(plot_points)}")
                
                # Validate and clean each plot point
                plot_point_names = ["Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"]
                cleaned_points = []
                for i, point in enumerate(plot_points):
                    if not isinstance(point, str):
                        point = str(point)
                    point = point.strip()
                    
                    # Remove any plot point name prefixes that might be in the text
                    for name in plot_point_names:
                        # Remove patterns like "Opening Hook:", "Opening Hook -", etc.
                        point = re.sub(rf'^{re.escape(name)}\s*[:-]\s*', '', point, flags=re.IGNORECASE)
                    
                    if point and len(point) > 10:  # Minimum length check
                        cleaned_points.append(point)
                        logger.warning(f"Extracted plot point #{len(cleaned_points)}: {point[:100]}...")
                    else:
                        logger.warning(f"Rejected plot point #{i+1} (too short or empty): '{point[:50] if point else 'empty'}...'")
                
                plot_points = cleaned_points
                
                logger.warning(f"Total plot points extracted from JSON: {len(plot_points)}")
            else:
                raise ValueError(f"JSON does not contain 'plot_points' key. Keys found: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Response that failed: {response[:500]}")
            raise ValueError(f"Failed to parse plot points from JSON response: {str(e)}")
        
        # Ensure we have exactly 5 plot points
        if len(plot_points) < 5:
            logger.warning(f"WARNING: Only {len(plot_points)} plot points extracted from JSON, using fallback for remaining")
            fallback_points = [
                "The story begins with an intriguing hook that draws readers in.",
                "A pivotal event changes everything and sets the main conflict in motion.",
                "Challenges and obstacles test the characters' resolve and growth.",
                "The climax brings all conflicts to a head in an intense confrontation.",
                "The resolution ties up loose ends and shows character transformation."
            ]
            plot_points.extend(fallback_points[len(plot_points):])
        
        logger.warning("-" * 80)
        logger.warning("FINAL PARSED PLOT POINTS FROM JSON:")
        for i, point in enumerate(plot_points[:5], 1):
            logger.warning(f"{i}. {point[:150]}...")
        logger.warning("=" * 80)
        
        return plot_points[:5]
    
    def _parse_plot_points(self, response: str) -> List[str]:
        """Parse plot points from response - handles multiple formats"""
        plot_points = []
        
        logger.warning("=" * 80)
        logger.warning("PARSING PLOT POINTS")
        logger.warning("=" * 80)
        logger.warning(f"Input response length: {len(response)} characters")
        logger.warning(f"Input response lines: {len(response.split(chr(10)))} lines")
        
        # Plot point names for pattern matching
        plot_point_names = ["Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"]
        plot_point_pattern = "|".join(plot_point_names)
        
        # Try multiple parsing strategies
        # Strategy 1: Look for numbered list format (1. Opening Hook:, 2. Inciting Incident:, etc.)
        numbered_pattern = re.compile(
            r'^\s*\d+\.\s*(?:' + plot_point_pattern + r')?\s*:?\s*(.+)$',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Strategy 2: Look for plot point names with colons
        named_pattern = re.compile(
            r'^\s*(?:' + plot_point_pattern + r')\s*:?\s*(.+)$',
            re.IGNORECASE | re.MULTILINE
        )
        
        # Strategy 3: Look for markdown bold format
        markdown_pattern = re.compile(
            r'\*\*(' + plot_point_pattern + r')\*\*\s*:?\s*(.+?)(?=\n\s*(?:\d+\.|' + plot_point_pattern + r'|\*\*|$))',
            re.IGNORECASE | re.DOTALL
        )
        
        # Strategy 4: Line-by-line parsing with continuation
        lines = response.split('\n')
        current_point = ""
        found_any_marker = False
        
        for line in lines:
            original_line = line
            line = line.strip()
            if not line:
                # Empty line - if we have a current point, it might be complete
                if current_point and found_any_marker:
                    clean_point = self._clean_plot_point(current_point, plot_point_names)
                    if clean_point and len(clean_point) > 20:
                        plot_points.append(clean_point)
                        logger.warning(f"Extracted plot point #{len(plot_points)}: {clean_point[:100]}...")
                    current_point = ""
                    found_any_marker = False
                continue
            
            # Check if this line starts a new plot point
            is_new_point = False
            
            # Check for numbered format (1., 2., etc.)
            if re.match(r'^\d+\.\s*', line):
                is_new_point = True
                found_any_marker = True
                logger.warning(f"Found numbered marker: {line[:50]}...")
            
            # Check for plot point name at start
            elif re.match(r'^(' + plot_point_pattern + r')\s*:?\s*', line, re.IGNORECASE):
                is_new_point = True
                found_any_marker = True
                logger.warning(f"Found named marker: {line[:50]}...")
            
            # Check for markdown bold
            elif re.search(r'\*\*(' + plot_point_pattern + r')\*\*', line, re.IGNORECASE):
                is_new_point = True
                found_any_marker = True
                logger.warning(f"Found markdown marker: {line[:50]}...")
            
            # Check for bullet points
            elif re.match(r'^[\-\*\•]\s+', line):
                is_new_point = True
                found_any_marker = True
                logger.warning(f"Found bullet marker: {line[:50]}...")
            
            if is_new_point:
                # Save previous point if exists
                if current_point:
                    clean_point = self._clean_plot_point(current_point, plot_point_names)
                    if clean_point and len(clean_point) > 20:
                        plot_points.append(clean_point)
                        logger.warning(f"Extracted plot point #{len(plot_points)}: {clean_point[:100]}...")
                    else:
                        logger.warning(f"Rejected plot point (too short): '{clean_point[:50] if clean_point else 'empty'}...'")
                current_point = line
            else:
                # Continuation of current point
                if current_point:
                    current_point += " " + line
                elif not found_any_marker:
                    # No markers found yet, might be plain text format
                    # Check if line looks like it could be a plot point
                    if len(line) > 20 and not re.match(r'^[A-Z\s]+$', line):  # Not all caps (likely a heading)
                        current_point = line
                        found_any_marker = True
        
        # Don't forget the last point
        if current_point:
            clean_point = self._clean_plot_point(current_point, plot_point_names)
            if clean_point and len(clean_point) > 20:
                plot_points.append(clean_point)
                logger.warning(f"Extracted plot point #{len(plot_points)}: {clean_point[:100]}...")
            else:
                logger.warning(f"Rejected final plot point (too short): '{clean_point[:50] if clean_point else 'empty'}...'")
        
        # If we didn't find any markers, try to split by common separators
        if len(plot_points) == 0:
            logger.warning("No plot points found with markers, trying alternative parsing...")
            # Try splitting by double newlines or numbered patterns
            sections = re.split(r'\n\s*\n|\d+\.\s*', response)
            for section in sections:
                section = section.strip()
                if section and len(section) > 20:
                    # Remove any plot point names from the start
                    clean_section = self._clean_plot_point(section, plot_point_names)
                    if clean_section and len(clean_section) > 20:
                        plot_points.append(clean_section)
                        logger.warning(f"Extracted plot point #{len(plot_points)} (alternative method): {clean_section[:100]}...")
        
        logger.warning(f"Total plot points extracted: {len(plot_points)}")
        
        # Ensure we have exactly 5 plot points
        if len(plot_points) < 5:
            logger.warning(f"WARNING: Only {len(plot_points)} plot points extracted, using fallback for remaining")
            logger.warning(f"Response format analysis: Found markers={found_any_marker}, Response preview: {response[:200]}...")
            fallback_points = [
                "The story begins with an intriguing hook that draws readers in.",
                "A pivotal event changes everything and sets the main conflict in motion.",
                "Challenges and obstacles test the characters' resolve and growth.",
                "The climax brings all conflicts to a head in an intense confrontation.",
                "The resolution ties up loose ends and shows character transformation."
            ]
            plot_points.extend(fallback_points[len(plot_points):])
        
        logger.warning("-" * 80)
        logger.warning("FINAL PARSED PLOT POINTS:")
        for i, point in enumerate(plot_points[:5], 1):
            logger.warning(f"{i}. {point[:150]}...")
        logger.warning("=" * 80)
        
        return plot_points[:5]
    
    def _clean_plot_point(self, text: str, plot_point_names: List[str]) -> str:
        """Clean a plot point by removing markers and formatting"""
        clean_text = text.strip()
        
        # Remove leading numbers and dots (1., 2., etc.)
        clean_text = re.sub(r'^\d+\.\s*', '', clean_text)
        
        # Remove leading bullets
        clean_text = re.sub(r'^[\-\*\•]\s+', '', clean_text)
        
        # Remove markdown bold formatting
        plot_point_pattern = "|".join(plot_point_names)
        clean_text = re.sub(r'^\*\*(' + plot_point_pattern + r')\*\*\s*:?\s*', '', clean_text, flags=re.IGNORECASE)
        
        # Remove plot point names with colons
        clean_text = re.sub(r'^(' + plot_point_pattern + r')\s*:?\s*', '', clean_text, flags=re.IGNORECASE)
        
        # Remove any remaining leading markers
        clean_text = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_text)
        
        # Clean up extra whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        return clean_text

    # Scene Variant Database Operations
    def _get_active_branch_id(self, db: Session, story_id: int) -> int:
        """Get the active branch ID for a story."""
        from ...models import StoryBranch
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        return active_branch.id if active_branch else None
    
    def create_scene_with_variant(
        self, 
        db: Session,
        story_id: int, 
        sequence_number: int, 
        content: str,
        title: str = None,
        custom_prompt: str = None,
        choices: List[Dict[str, Any]] = None,
        generation_method: str = "auto",
        branch_id: int = None
    ) -> Tuple[Any, Any]:
        """Create a new scene with its first variant"""
        from ...models import Scene, SceneVariant, SceneChoice, StoryFlow
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # Check if a scene already exists for this sequence in this story/branch
        existing_flow_query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.sequence_number == sequence_number
        )
        if branch_id:
            existing_flow_query = existing_flow_query.filter(StoryFlow.branch_id == branch_id)
        existing_flow = existing_flow_query.first()
        
        if existing_flow:
            # Return the existing scene and variant instead of creating duplicates
            existing_scene = db.query(Scene).filter(Scene.id == existing_flow.scene_id).first()
            existing_variant = db.query(SceneVariant).filter(SceneVariant.id == existing_flow.scene_variant_id).first()
            logger.warning(f"Scene already exists for story {story_id} sequence {sequence_number} (branch {branch_id}), returning existing scene {existing_scene.id}")
            return existing_scene, existing_variant
        
        # Create the logical scene
        scene = Scene(
            story_id=story_id,
            branch_id=branch_id,
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
        self._update_story_flow(db, story_id, sequence_number, scene.id, variant.id, branch_id=branch_id)
        
        db.commit()
        logger.info(f"Successfully created scene {scene.id} with variant {variant.id} at sequence {sequence_number} (branch {branch_id})")
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
            story.id, db, custom_prompt=custom_prompt, exclude_scene_id=scene_id
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

    def switch_to_variant(self, db: Session, story_id: int, scene_id: int, variant_id: int, branch_id: int = None) -> bool:
        """Switch the active variant for a scene in the story flow"""
        from ...models import StoryFlow, SceneVariant
        
        # Verify the variant exists
        variant = db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
        if not variant or variant.scene_id != scene_id:
            return False
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # Update story flow to use this variant (filtered by branch)
        flow_query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.scene_id == scene_id
        )
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        flow_entry = flow_query.first()
        
        if flow_entry:
            flow_entry.scene_variant_id = variant_id
            db.commit()
            logger.info(f"Switched to variant {variant_id} for scene {scene_id} in story {story_id} (branch {branch_id})")
            return True
        
        return False

    def get_scene_variants(self, db: Session, scene_id: int) -> List[Any]:
        """Get all variants for a scene"""
        from ...models import SceneVariant
        
        return db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(SceneVariant.variant_number)\
            .all()

    def get_active_scene_count(self, db: Session, story_id: int, chapter_id: Optional[int] = None, branch_id: int = None) -> int:
        """
        Get count of active scenes from StoryFlow.
        
        Args:
            db: Database session
            story_id: Story ID
            chapter_id: Optional chapter ID to filter scenes by chapter
            branch_id: Optional branch ID for filtering
            
        Returns:
            Count of active scenes in the story flow
        """
        from ...models import StoryFlow, Scene
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.is_active == True
        )
        
        if branch_id:
            query = query.filter(StoryFlow.branch_id == branch_id)
        
        if chapter_id:
            # Join with Scene to filter by chapter
            query = query.join(Scene).filter(Scene.chapter_id == chapter_id)
        
        return query.count()
    
    def get_active_story_flow(self, db: Session, story_id: int, branch_id: int = None) -> List[Dict[str, Any]]:
        """Get the active story flow with scene variants"""
        from ...models import StoryFlow, Scene, SceneVariant, SceneChoice
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # Get the story flow ordered by sequence (filtered by branch)
        flow_query = db.query(StoryFlow).filter(StoryFlow.story_id == story_id)
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        flow_entries = flow_query.order_by(StoryFlow.sequence_number).all()
        
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

    def _update_story_flow(self, db: Session, story_id: int, sequence_number: int, scene_id: int, variant_id: int, branch_id: int = None):
        """Update or create story flow entry"""
        from ...models import StoryFlow
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # Check if flow entry already exists for this sequence (filtered by branch)
        existing_flow_query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.sequence_number == sequence_number
        )
        if branch_id:
            existing_flow_query = existing_flow_query.filter(StoryFlow.branch_id == branch_id)
        existing_flow = existing_flow_query.first()
        
        if existing_flow:
            # Update existing entry
            existing_flow.scene_id = scene_id
            existing_flow.scene_variant_id = variant_id
        else:
            # Create new flow entry
            flow_entry = StoryFlow(
                story_id=story_id,
                branch_id=branch_id,
                sequence_number=sequence_number,
                scene_id=scene_id,
                scene_variant_id=variant_id
            )
            db.add(flow_entry)

    async def delete_scenes_from_sequence(self, db: Session, story_id: int, sequence_number: int, skip_restoration: bool = False, branch_id: int = None) -> bool:
        """Delete all scenes from a given sequence number onwards"""
        start_time = time.perf_counter()
        trace_id = f"scene-del-{uuid.uuid4()}"
        status = "error"
        story_flows_deleted = 0
        scenes_deleted = 0
        try:
            from ...models import StoryFlow, Scene
            
            # Get active branch if not specified
            phase_start = time.perf_counter()
            if branch_id is None:
                branch_id = self._get_active_branch_id(db, story_id)
            logger.info(f"[DELETE:START] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} branch_id={branch_id} skip_restoration={skip_restoration}")
            
            # Phase 1: Delete all StoryFlow entries for this story with sequence_number >= sequence_number (filtered by branch)
            phase_start = time.perf_counter()
            flow_delete_query = db.query(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.sequence_number >= sequence_number
            )
            if branch_id:
                flow_delete_query = flow_delete_query.filter(StoryFlow.branch_id == branch_id)
            story_flows_deleted = flow_delete_query.delete()
            logger.info(f"[DELETE:PHASE] trace_id={trace_id} phase=delete_story_flows duration_ms={(time.perf_counter()-phase_start)*1000:.2f} flows_deleted={story_flows_deleted}")
            
            # Phase 2: Get scenes to delete (don't use bulk delete to ensure cascades work) - filtered by branch
            phase_start = time.perf_counter()
            scene_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= sequence_number
            )
            if branch_id:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scenes_to_delete = scene_query.all()
            logger.info(f"[DELETE:PHASE] trace_id={trace_id} phase=query_scenes duration_ms={(time.perf_counter()-phase_start)*1000:.2f} scenes_found={len(scenes_to_delete)}")
            
            # NOTE: Semantic cleanup (embeddings, character moments, plot events) is now handled
            # as a background task by the API endpoint to avoid blocking the response.
            # This method only handles fast database deletions.
            logger.info(f"[DELETE:CONTEXT] trace_id={trace_id} scenes_to_delete={len(scenes_to_delete)} sequence_start={sequence_number} scene_ids={[s.id for s in scenes_to_delete[:5]]}{'...' if len(scenes_to_delete) > 5 else ''}")
            
            # Restore NPCTracking from snapshot after scene deletion (skip if doing in background)
            if not skip_restoration:
                try:
                    from ...models import Story, NPCTracking, NPCTrackingSnapshot
                    
                    # Find the last remaining scene's sequence number
                    last_remaining_scene = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.sequence_number < sequence_number
                    ).order_by(Scene.sequence_number.desc()).first()
                    
                    if last_remaining_scene:
                        # Get snapshot for the last remaining scene
                        snapshot = db.query(NPCTrackingSnapshot).filter(
                            NPCTrackingSnapshot.story_id == story_id,
                            NPCTrackingSnapshot.scene_sequence == last_remaining_scene.sequence_number
                        ).first()
                        
                        if snapshot:
                            # Restore NPCTracking from snapshot
                            snapshot_data = snapshot.snapshot_data or {}
                            
                            # Delete all existing NPC tracking records for this story
                            db.query(NPCTracking).filter(
                                NPCTracking.story_id == story_id
                            ).delete()
                            
                            # Restore from snapshot
                            for character_name, npc_data in snapshot_data.items():
                                tracking = NPCTracking(
                                    story_id=story_id,
                                    character_name=character_name,
                                    entity_type=npc_data.get("entity_type", "CHARACTER"),
                                    total_mentions=npc_data.get("total_mentions", 0),
                                    scene_count=npc_data.get("scene_count", 0),
                                    importance_score=npc_data.get("importance_score", 0.0),
                                    frequency_score=npc_data.get("frequency_score", 0.0),
                                    significance_score=npc_data.get("significance_score", 0.0),
                                    first_appearance_scene=npc_data.get("first_appearance_scene"),
                                    last_appearance_scene=npc_data.get("last_appearance_scene"),
                                    has_dialogue_count=npc_data.get("has_dialogue_count", 0),
                                    has_actions_count=npc_data.get("has_actions_count", 0),
                                    crossed_threshold=npc_data.get("crossed_threshold", False),
                                    user_prompted=npc_data.get("user_prompted", False),
                                    profile_extracted=npc_data.get("profile_extracted", False),
                                    converted_to_character=npc_data.get("converted_to_character", False),
                                    extracted_profile=npc_data.get("extracted_profile", {})
                                )
                                db.add(tracking)
                            
                            logger.info(f"[DELETE] Restored NPC tracking from snapshot for scene {last_remaining_scene.sequence_number} (story {story_id})")
                        else:
                            logger.warning(f"[DELETE] No snapshot found for last remaining scene {last_remaining_scene.sequence_number}, NPC tracking may be inconsistent")
                    else:
                        # No remaining scenes - delete all NPC tracking
                        db.query(NPCTracking).filter(
                            NPCTracking.story_id == story_id
                        ).delete()
                        logger.info(f"[DELETE] No remaining scenes, deleted all NPC tracking for story {story_id}")
                        
                except Exception as e:
                    # Don't fail scene deletion if NPC tracking restoration fails
                    logger.warning(f"[DELETE] Failed to restore NPC tracking from snapshot after scene deletion: {e}")
                    import traceback
                    logger.warning(f"[DELETE] Traceback: {traceback.format_exc()}")
            
            # Get min and max deleted sequence numbers for batch invalidation (before deleting scenes)
            if scenes_to_delete:
                min_deleted_seq = min(scene.sequence_number for scene in scenes_to_delete)
                max_deleted_seq = max(scene.sequence_number for scene in scenes_to_delete)
            else:
                min_deleted_seq = sequence_number
                max_deleted_seq = sequence_number
            
            # Get affected chapter IDs before deleting scenes
            affected_chapter_ids = set()
            for scene in scenes_to_delete:
                if scene.chapter_id:
                    affected_chapter_ids.add(scene.chapter_id)
            logger.info(f"[DELETE:CONTEXT] trace_id={trace_id} affected_chapters={list(affected_chapter_ids)}")
            
            # Phase 2.5: Clear leads_to_scene_id references in SceneChoice before deleting scenes
            # This prevents foreign key constraint violations
            if scenes_to_delete:
                from ...models import SceneChoice
                scene_ids_to_delete = [s.id for s in scenes_to_delete]
                phase_start = time.perf_counter()
                leads_to_cleared = db.query(SceneChoice).filter(
                    SceneChoice.leads_to_scene_id.in_(scene_ids_to_delete)
                ).update({SceneChoice.leads_to_scene_id: None}, synchronize_session='fetch')
                logger.info(f"[DELETE:PHASE] trace_id={trace_id} phase=clear_leads_to_refs duration_ms={(time.perf_counter()-phase_start)*1000:.2f} refs_cleared={leads_to_cleared}")
            
            # Phase 3: Delete each scene individually to trigger cascade relationships
            phase_start = time.perf_counter()
            scenes_deleted = 0
            total_scenes = len(scenes_to_delete)
            batch_log_interval = max(1, total_scenes // 10) if total_scenes > 10 else 1  # Log every 10% or every scene if < 10
            
            logger.info(f"[DELETE:SCENE_LOOP:START] trace_id={trace_id} total_scenes={total_scenes}")
            for i, scene in enumerate(scenes_to_delete):
                scene_start = time.perf_counter()
                db.delete(scene)
                scenes_deleted += 1
                scene_duration = (time.perf_counter() - scene_start) * 1000
                
                # Log progress every batch_log_interval scenes or if a single delete takes > 100ms
                if (i + 1) % batch_log_interval == 0 or scene_duration > 100:
                    elapsed_ms = (time.perf_counter() - phase_start) * 1000
                    logger.info(f"[DELETE:PROGRESS] trace_id={trace_id} progress={i+1}/{total_scenes} ({((i+1)/total_scenes*100):.1f}%) elapsed_ms={elapsed_ms:.2f} last_scene_ms={scene_duration:.2f} scene_id={scene.id}")
            
            loop_duration = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[DELETE:SCENE_LOOP:END] trace_id={trace_id} scenes_deleted={scenes_deleted} duration_ms={loop_duration:.2f} avg_per_scene_ms={loop_duration/max(1,scenes_deleted):.2f}")
            
            # Phase 4: Recalculate scenes_count and invalidate affected batches for affected chapters
            phase_start = time.perf_counter()
            from ...models import Chapter, ChapterSummaryBatch
            from ...api.chapters import update_chapter_summary_from_batches
            
            logger.info(f"[DELETE:CHAPTER_UPDATE:START] trace_id={trace_id} chapters_to_update={len(affected_chapter_ids)}")
            for chapter_idx, chapter_id in enumerate(affected_chapter_ids):
                chapter_start = time.perf_counter()
                chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
                if chapter:
                    chapter.scenes_count = self.get_active_scene_count(db, story_id, chapter_id, branch_id=chapter.branch_id)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} new_scenes_count={chapter.scenes_count}")
                    
                    # Invalidate batches that overlap with deleted scenes
                    affected_batches = db.query(ChapterSummaryBatch).filter(
                        ChapterSummaryBatch.chapter_id == chapter_id,
                        ChapterSummaryBatch.start_scene_sequence <= max_deleted_seq,
                        ChapterSummaryBatch.end_scene_sequence >= min_deleted_seq
                    ).all()
                    
                    if affected_batches:
                        for batch in affected_batches:
                            db.delete(batch)
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} batches_invalidated={len(affected_batches)}")
                        
                        # Recalculate summary from remaining batches
                        summary_start = time.perf_counter()
                        update_chapter_summary_from_batches(chapter_id, db)
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} summary_recalc_ms={(time.perf_counter()-summary_start)*1000:.2f}")
                    
                    # Update last_extraction_scene_count and last_summary_scene_count to max remaining sequence
                    # This prevents extraction/summary from being skipped due to negative scene counts
                    remaining_scenes = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.chapter_id == chapter_id,
                        Scene.is_deleted == False
                    ).all()
                    
                    if remaining_scenes:
                        max_remaining_seq = max(s.sequence_number for s in remaining_scenes)
                        # Only lower them, never raise them (scenes were deleted, not added)
                        if chapter.last_extraction_scene_count and chapter.last_extraction_scene_count > max_remaining_seq:
                            chapter.last_extraction_scene_count = max_remaining_seq
                            logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} extraction_count_updated_to={max_remaining_seq}")
                        if chapter.last_summary_scene_count and chapter.last_summary_scene_count > max_remaining_seq:
                            chapter.last_summary_scene_count = max_remaining_seq
                            logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} summary_count_updated_to={max_remaining_seq}")
                        if chapter.last_plot_extraction_scene_count and chapter.last_plot_extraction_scene_count > max_remaining_seq:
                            chapter.last_plot_extraction_scene_count = max_remaining_seq
                            logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} plot_extraction_count_updated_to={max_remaining_seq}")
                        # Restore plot_progress from batches instead of resetting to None
                        # This preserves events from earlier batches that are still valid
                        from ...services.chapter_progress_service import ChapterProgressService
                        progress_service = ChapterProgressService(db)
                        progress_service.update_plot_progress_from_batches(chapter.id)
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} plot_progress_restored_from_batches")
                    else:
                        chapter.last_extraction_scene_count = 0
                        chapter.last_summary_scene_count = 0
                        chapter.last_plot_extraction_scene_count = 0
                        # No remaining scenes, so restore from batches (will set to None if no batches)
                        from ...services.chapter_progress_service import ChapterProgressService
                        progress_service = ChapterProgressService(db)
                        progress_service.update_plot_progress_from_batches(chapter.id)
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} extraction_summary_plot_count_reset_to=0")
                    
                    chapter_duration = (time.perf_counter() - chapter_start) * 1000
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} chapter_update_ms={chapter_duration:.2f}")
            
            chapter_phase_duration = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[DELETE:CHAPTER_UPDATE:END] trace_id={trace_id} chapters_updated={len(affected_chapter_ids)} duration_ms={chapter_phase_duration:.2f}")
            
            # Invalidate and restore entity states using batch system (skip if doing in background)
            if not skip_restoration:
                try:
                    from ...models import Story, UserSettings, Scene
                    from ...services.entity_state_service import EntityStateService
                    
                    # Get story to find owner_id
                    story = db.query(Story).filter(Story.id == story_id).first()
                    if story:
                        # Get user settings
                        user_settings_obj = db.query(UserSettings).filter(
                            UserSettings.user_id == story.owner_id
                        ).first()
                        
                        if user_settings_obj:
                            user_settings = user_settings_obj.to_dict()
                            entity_service = EntityStateService(
                                user_id=story.owner_id,
                                user_settings=user_settings
                            )
                            
                            # Invalidate batches that overlap with deleted scenes
                            entity_service.invalidate_entity_batches_for_scenes(
                                db, story_id, min_deleted_seq, max_deleted_seq
                            )
                            
                            # Check if remaining scenes form a complete batch (filtered by branch)
                            remaining_scene_query = db.query(Scene).filter(
                                Scene.story_id == story_id,
                                Scene.sequence_number < sequence_number
                            )
                            if branch_id:
                                remaining_scene_query = remaining_scene_query.filter(Scene.branch_id == branch_id)
                            last_remaining_scene = remaining_scene_query.order_by(Scene.sequence_number.desc()).first()

                            if last_remaining_scene:
                                batch_threshold = user_settings.get("context_summary_threshold", 5)
                                last_sequence = last_remaining_scene.sequence_number
                                is_complete_batch = (last_sequence % batch_threshold) == 0

                                if is_complete_batch:
                                    # Complete batch - recalculate (will re-extract)
                                    await entity_service.recalculate_entity_states_from_batches(
                                        db, story_id, story.owner_id, user_settings, max_deleted_seq, branch_id=branch_id
                                    )
                                    logger.info(f"[DELETE] Recalculated entity states (complete batch) for story {story_id} branch {branch_id}")
                                else:
                                    # Incomplete batch - only restore, don't re-extract
                                    entity_service.restore_from_last_complete_batch(
                                        db, story_id, max_deleted_seq, branch_id=branch_id
                                    )
                                    logger.info(f"[DELETE] Restored entity states from last complete batch (incomplete batch remains, waiting for threshold) for story {story_id} branch {branch_id}")
                            else:
                                # No remaining scenes on this branch - clear entity states for this branch only
                                from ...models import CharacterState, LocationState, ObjectState
                                char_del_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
                                loc_del_query = db.query(LocationState).filter(LocationState.story_id == story_id)
                                obj_del_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
                                if branch_id:
                                    char_del_query = char_del_query.filter(CharacterState.branch_id == branch_id)
                                    loc_del_query = loc_del_query.filter(LocationState.branch_id == branch_id)
                                    obj_del_query = obj_del_query.filter(ObjectState.branch_id == branch_id)
                                char_del_query.delete()
                                loc_del_query.delete()
                                obj_del_query.delete()
                                logger.info(f"[DELETE] No remaining scenes, cleared entity states for story {story_id} branch {branch_id}")
                        else:
                            logger.warning(f"[DELETE] No user settings found for story owner {story.owner_id}, skipping entity state restoration")
                    else:
                        logger.warning(f"[DELETE] Story {story_id} not found, skipping entity state restoration")
                except Exception as e:
                    # Don't fail scene deletion if entity state restoration fails
                    logger.warning(f"[DELETE] Failed to restore entity states after scene deletion: {e}")
                    import traceback
                    logger.warning(f"[DELETE] Traceback: {traceback.format_exc()}")
            
            # Phase 5: Commit the transaction
            phase_start = time.perf_counter()
            logger.info(f"[DELETE:COMMIT:START] trace_id={trace_id} story_id={story_id}")
            db.commit()
            commit_duration = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[DELETE:COMMIT:END] trace_id={trace_id} commit_duration_ms={commit_duration:.2f}")
            status = "success"
            
            total_duration = (time.perf_counter() - start_time) * 1000
            logger.info(f"[DELETE:END] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} flows_deleted={story_flows_deleted} scenes_deleted={scenes_deleted} total_duration_ms={total_duration:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"[DELETE:ERROR] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} error={e}")
            db.rollback()
            return False
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if duration_ms > 15000:
                logger.error(f"[DELETE:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
            elif duration_ms > 5000:
                logger.warning(f"[DELETE:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
            else:
                logger.info(f"[DELETE:DONE] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")

    async def _generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> str:
        """
        Generate with pre-constructed messages array for better cache utilization.
        
        This method accepts a list of messages (system + multiple user messages) and sends
        them directly to the LLM. By splitting context into multiple user messages,
        we improve cache hit rates since earlier messages remain stable while only
        later messages change.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            user_id: User ID for client configuration
            user_settings: User settings dict
            max_tokens: Max tokens for generation
            temperature: Temperature for generation
            skip_nsfw_filter: Whether to skip NSFW filter injection
            
        Returns:
            Generated text content
        """
        client = self.get_user_client(user_id, user_settings)
        
        # Check completion mode - multi-message only works with chat completion
        if client.completion_mode == "text":
            # For text completion, fall back to combining messages into single prompt
            logger.warning("Multi-message generation not supported for text completion mode, combining messages")
            combined_prompt = "\n\n".join([
                msg["content"] for msg in messages if msg["role"] == "user"
            ])
            system_prompt = next((msg["content"] for msg in messages if msg["role"] == "system"), "")
            return await self._generate_text_completion(
                combined_prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            )
        
        # Inject NSFW filter into system message if needed
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # Find and modify system message, or add one
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"NSFW filter injected for user {user_id}")
        
        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        # Get timeout from user settings or fallback to system default
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total
        
        try:
            response = await acompletion(**gen_params)
            
            # Check finish_reason for truncation
            if hasattr(response, 'choices') and len(response.choices) > 0:
                finish_reason = getattr(response.choices[0], 'finish_reason', None)
                if finish_reason == 'length':
                    logger.warning(f"[TRUNCATION] Response truncated due to token limit! max_tokens={max_tokens}")
                elif finish_reason:
                    logger.debug(f"[GENERATION] Finish reason: {finish_reason}")
            
            return response.choices[0].message.content
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Multi-message generation failed for user {user_id}: {error_msg}")
            raise ValueError(f"LLM generation failed: {error_msg}")

    async def _generate_stream_with_messages(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Streaming generation with pre-constructed messages array for better cache utilization.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            user_id: User ID for client configuration
            user_settings: User settings dict
            max_tokens: Max tokens for generation
            temperature: Temperature for generation
            skip_nsfw_filter: Whether to skip NSFW filter injection
            
        Yields:
            Generated text chunks
        """
        client = self.get_user_client(user_id, user_settings)
        
        # Check completion mode - multi-message only works with chat completion
        if client.completion_mode == "text":
            # For text completion, fall back to combining messages into single prompt
            logger.warning("Multi-message streaming not supported for text completion mode, combining messages")
            combined_prompt = "\n\n".join([
                msg["content"] for msg in messages if msg["role"] == "user"
            ])
            system_prompt = next((msg["content"] for msg in messages if msg["role"] == "system"), "")
            async for chunk in self._generate_stream_text_completion(
                combined_prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            ):
                yield chunk
            return
        
        # Inject NSFW filter into system message if needed
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # Find and modify system message, or add one
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"NSFW filter injected for streaming user {user_id}")
        
        # Get streaming parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        gen_params["stream"] = True
        
        # Get timeout from user settings or fallback to system default
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total
        
        # Write prompt to file for debugging (only if prompt_debug is enabled)
        if settings.prompt_debug:
            try:
                import os
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": gen_params.get('max_tokens'),
                        "temperature": gen_params.get('temperature'),
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write prompt debug file: {e}")
        
        try:
            response = await acompletion(**gen_params)
            
            # Track reasoning content for logging
            has_reasoning = False
            reasoning_chars = 0
            content_chars = 0
            chunk_count = 0
            
            async for chunk in response:
                chunk_count += 1
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    
                    # Debug: Log first few chunks to see what fields are available
                    if chunk_count <= 3:
                        logger.debug(f"[STREAM DEBUG] Chunk {chunk_count} reasoning_content: {getattr(delta, 'reasoning_content', None)}")
                    
                    # Check for reasoning_content (LiteLLM's standardized field for all providers)
                    # This works for OpenRouter, Anthropic, DeepSeek, etc. when using proper LiteLLM params
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        has_reasoning = True
                        reasoning_chars += len(delta.reasoning_content)
                        # Yield reasoning with special prefix for frontend to detect
                        yield f"__THINKING__:{delta.reasoning_content}"
                    
                    # Regular content
                    if hasattr(delta, 'content') and delta.content:
                        content_chars += len(delta.content)
                        yield delta.content
            
            # Log summary
            logger.info(f"[MULTI-MSG STREAMING] chunks={chunk_count}, content_chars={content_chars}, reasoning_chars={reasoning_chars}")
            if chunk_count > 0 and content_chars == 0:
                logger.warning(f"[MULTI-MSG STREAMING] Received {chunk_count} chunks but no content! Model may need higher max_tokens or reasoning disabled.")
            if has_reasoning:
                logger.info(f"[MULTI-MSG REASONING] Streamed {reasoning_chars} chars of reasoning content")
                        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Multi-message streaming failed for user {user_id}: {error_msg}")
            raise ValueError(f"LLM streaming failed: {error_msg}")
