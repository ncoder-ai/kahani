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
            filename: Name of the debug file (e.g., 'prompt_sent.txt', 'prompt_choice_sent.txt')
        
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
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.txt")
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    f.write("=" * 80 + "\n")
                    f.write("STREAMING SCENE GENERATION PROMPT (EXACTLY AS SENT TO LLM)\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"SYSTEM PROMPT:\n{system_prompt_log}\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"USER PROMPT:\n{user_prompt_log}\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"GENERATION PARAMETERS:\n")
                    f.write(f"  max_tokens: {gen_params.get('max_tokens')}\n")
                    f.write(f"  temperature: {gen_params.get('temperature')}\n")
                    f.write(f"  model: {client.model_string}\n")
                    f.write("-" * 80 + "\n")
                    f.write("FULL MESSAGES ARRAY (JSON):\n")
                    f.write(json.dumps(gen_params["messages"], indent=2, ensure_ascii=False))
                    f.write("\n")
                    f.write("=" * 80 + "\n")
            except Exception as e:
                pass  # Silently fail if file writing fails
        
        try:
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
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.txt")
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    f.write("=" * 80 + "\n")
                    f.write("STREAMING SCENE GENERATION PROMPT (EXACTLY AS SENT TO LLM - TEXT COMPLETION)\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"SYSTEM PROMPT:\n{system_prompt or '(none)'}\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"USER PROMPT:\n{prompt.strip()}\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"RENDERED PROMPT (FULL - EXACTLY AS SENT):\n{rendered_prompt}\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"GENERATION PARAMETERS:\n")
                    f.write(f"  max_tokens: {gen_params.get('max_tokens')}\n")
                    f.write(f"  temperature: {gen_params.get('temperature')}\n")
                    f.write(f"  model: {client.model_string}\n")
                    f.write(f"  prompt (in gen_params): {gen_params.get('prompt', '')[:200]}...\n")
                    f.write("=" * 80 + "\n")
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
    
    def _clean_scene_numbers(self, content: str) -> str:
        """Remove scene numbers and titles from the beginning of generated content"""
        # Remove patterns like "Scene 7:", "Scene 7: Title", etc. from the start
        content = re.sub(r'^Scene\s+\d+:.*?(\n|$)', '', content, flags=re.IGNORECASE).strip()
        # Also remove standalone scene titles that might start with numbers
        content = re.sub(r'^\d+[:.]\s*[A-Z][^.\n]*(\n|$)', '', content).strip()
        return content
    
    def _clean_instruction_tags(self, content: str) -> str:
        """Remove instruction tags like [/inst][inst] that may appear in LLM responses"""
        # Remove [/inst] and [inst] tags (with or without closing brackets)
        content = re.sub(r'\[/inst\]\s*\[inst\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[/inst\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[inst\]', '', content, flags=re.IGNORECASE)
        return content.strip()
    
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
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
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
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
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
            choices_count=choices_count
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
            task_content = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
            
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
                return (scene_content, parsed_choices)
            else:
                # Check if response might have been truncated
                if len(choices_text) < 50:
                    logger.warning(f"[CHOICES] Marker found but choices text is very short ({len(choices_text)} chars). Response may have been truncated. Choices text: {choices_text}")
                else:
                    logger.warning(f"[CHOICES] Marker found but parsing failed. Choices text length: {len(choices_text)}, preview: {choices_text[:200]}")
                return (scene_content, None)
        else:
            # No marker found, return scene without choices
            logger.warning(f"[CHOICES] Marker NOT found in response. Response length: {len(cleaned_response)} chars")
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
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
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
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
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
            
            # Try to find JSON array - look for pattern like ["choice1", "choice2"]
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
                    # CRITICAL FIX: Validate and return here - this was missing!
                    return validate_and_return_choices(choices)
                except json.JSONDecodeError as e:
                    logger.warning(f"[CHOICES PARSE] JSON decode error: {e}, JSON string: {json_str[:200]}")
                    # Try to fix common JSON issues
                    # Remove trailing commas
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    try:
                        choices = json.loads(json_str)
                        return validate_and_return_choices(choices)
                    except json.JSONDecodeError as e2:
                        logger.warning(f"[CHOICES PARSE] Still failed after cleanup: {e2}")
                        # Try to fix incomplete JSON
                        json_str = self._fix_incomplete_json_array(json_str)
                        if json_str:
                            try:
                                choices = json.loads(json_str)
                                return validate_and_return_choices(choices)
                            except json.JSONDecodeError:
                                pass
                        # Fallback: try parsing the raw text directly
                        logger.debug(f"[CHOICES PARSE] Trying fallback: parse raw text directly")
                        try:
                            choices = json.loads(text.strip())
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
            
            # Final fallback: try parsing the entire text as JSON (might be plain JSON without markdown)
            logger.debug(f"[CHOICES PARSE] Trying final fallback: parse entire text as JSON")
            try:
                choices = json.loads(text.strip())
                return validate_and_return_choices(choices)
            except json.JSONDecodeError:
                pass
            
            # If we get here, all parsing attempts failed
            # Check if text looks like it was cut off (incomplete JSON)
            if text.strip().startswith('[') and not text.strip().endswith(']'):
                logger.warning(f"[CHOICES PARSE] Incomplete JSON array detected (starts with '[' but doesn't end with ']'). Text may have been truncated. Text preview: {text[:200]}")
            elif '```json' in text.lower() or '```' in text:
                logger.warning(f"[CHOICES PARSE] Markdown code block found but no valid JSON array inside. Text preview: {text[:200]}")
            else:
                logger.warning(f"[CHOICES PARSE] No JSON array found in text. Text preview: {text[:200]}")
            
            return None
        except (json.JSONDecodeError, ValueError, AttributeError, Exception) as e:
            logger.warning(f"[CHOICES PARSE] Failed to parse choices from JSON: {e}, text preview: {text[:200] if 'text' in locals() and text else 'empty'}")
            return None
    
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
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE GEN STREAMING] Using scene_with_immediate template")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE GEN STREAMING] Using scene_without_immediate template")
        
        # Get POV from writing preset (default to third person)
        pov = 'third'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
        
        # Create POV instruction for template
        if pov == 'first':
            pov_instruction = "in first person (I/me/my)"
        elif pov == 'second':
            pov_instruction = "in second person (you/your)"
        else:
            pov_instruction = "in third person (he/she/they/character names)"
        
        # Get system prompt from template
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count
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
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            # Append choices reminder
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_instruction = task_instruction + "\n\n" + choices_reminder
            
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
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
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
        if choices_reminder:
            task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        raw_chunks = []  # Collect raw chunks before cleaning
        
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            total_chunks += 1
            raw_chunks.append(chunk)  # Capture raw chunk before cleaning
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
                logger.warning(f"[CHOICES STREAMING] ERROR: ###CHOICES### marker not found after {total_chunks} chunks. Full response length: {len(full_response)} chars")
            else:
                logger.warning(f"[CHOICES STREAMING] Marker found but choices_buffer is empty")
        
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
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Check if this is guided enhancement (has enhancement_guidance) or simple variant
        enhancement_guidance = context.get("enhancement_guidance", "")
        
        # Get POV from writing preset (default to third person)
        pov = 'third'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
        
        # Create POV instruction for template
        if pov == 'first':
            pov_instruction = "in first person (I/me/my)"
        elif pov == 'second':
            pov_instruction = "in second person (you/your)"
        else:
            pov_instruction = "in third person (he/she/they/character names)"
        
        if enhancement_guidance:
            # Guided enhancement: use scene_guided_enhancement template with original scene
            # Exclude last scene from previous events to avoid duplication
            formatted_context = self._format_context_for_scene(context, exclude_last_scene=True)
            logger.warning(f"[GUIDED ENHANCEMENT] scene_length_description: {scene_length_description}")
            logger.warning(f"[GUIDED ENHANCEMENT] choices_count: {choices_count}")
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "scene_guided_enhancement", "scene_guided_enhancement",
                user_id=user_id,
                db=db,
                context=formatted_context,
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                pov_instruction=pov_instruction
            )
            logger.warning(f"[GUIDED ENHANCEMENT] Prompt length: {len(user_prompt)} chars")
            logger.warning(f"[GUIDED ENHANCEMENT] Prompt contains scene_length_description: {'scene_length_description' in user_prompt or scene_length_description in user_prompt}")
        else:
            # Simple variant: use the same prompt template as new scene generation
            # Extract immediate_situation from context for template variable
            immediate_situation = context.get("current_situation") or ""
            immediate_situation = str(immediate_situation) if immediate_situation else ""
            
            # Choose template based on whether we have immediate_situation
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            if has_immediate:
                template_key = "scene_with_immediate"
            else:
                template_key = "scene_without_immediate"
            
            # Get task instruction from prompts.yml
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
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
        
        # Enhance system prompt with POV instruction for choices (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # Log prompts for debugging
        
        if not user_prompt or not user_prompt.strip():
            logger.error("Empty user prompt generated for variant generation")
            raise ValueError("Generated empty user prompt for variant generation")
        
        # Add buffer for choices section - dynamic based on choices_count
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)  # At least 300, or 50 per choice
        max_tokens = base_max_tokens + choices_buffer_tokens
        logger.info(f"[VARIANT WITH CHOICES STREAMING] Using max_tokens: {max_tokens} (base: {base_max_tokens} + {choices_buffer_tokens} buffer for {choices_count} choices)")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
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
        
        # Get choices count and scene length from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length = generation_prefs.get("scene_length", "medium")
        scene_length_map = {"short": "short (50-100 words)", "medium": "medium (100-150 words)", "long": "long (150-250 words)"}
        scene_length_description = scene_length_map.get(scene_length, "medium (100-150 words)")
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION (for cache hits) ===
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count
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
        choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
        
        # Get current scene content and continuation prompt from context
        current_scene_content = context.get("current_scene_content", "") or context.get("current_content", "")
        continuation_prompt = context.get("continuation_prompt", "Continue this scene with more details and development.")
        
        # Clean scene content to remove any instruction tags or formatting artifacts
        cleaned_scene_content = self._clean_instruction_tags(current_scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)
        
        final_message = f"""=== CURRENT SCENE TO CONTINUE ===
{cleaned_scene_content}

=== CONTINUATION INSTRUCTION ===
{continuation_prompt}

Write a compelling continuation that follows naturally from the scene above. Focus on engaging narrative and dialogue. Do not repeat previous content.

After completing the continuation, add ###CHOICES### followed by {choices_count} narrative choices.

{choices_reminder}

Output choices as valid JSON: {{"choices": ["choice 1", "choice 2", ...]}}"""
        
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
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.txt")
                client = self.get_user_client(user_id, user_settings)
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    f.write("=" * 80 + "\n")
                    f.write("CONTINUATION STREAMING PROMPT (EXACTLY AS SENT TO LLM)\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"NUMBER OF MESSAGES: {len(messages)}\n")
                    f.write("-" * 80 + "\n")
                    for i, msg in enumerate(messages):
                        f.write(f"MESSAGE {i+1} [{msg['role'].upper()}]:\n")
                        f.write(msg['content'][:500] + "..." if len(msg['content']) > 500 else msg['content'])
                        f.write("\n" + "-" * 40 + "\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"GENERATION PARAMETERS:\n")
                    f.write(f"  max_tokens: {max_tokens}\n")
                    f.write(f"  model: {client.model_string}\n")
                    f.write("-" * 80 + "\n")
                    f.write("FULL MESSAGES ARRAY (JSON):\n")
                    f.write(json.dumps(messages, indent=2, ensure_ascii=False))
                    f.write("\n")
                    f.write("=" * 80 + "\n")
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
        # Format context for prompt
        formatted_context = self._format_context_for_scene(context)
        
        # Get chapter conclusion prompts from prompt_manager
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "chapter_conclusion", "chapter_conclusion",
            user_id=user_id,
            db=db,
            context=formatted_context,
            chapter_number=chapter_info.get("chapter_number", 1),
            chapter_title=chapter_info.get("chapter_title", "Untitled"),
            chapter_location=chapter_info.get("chapter_location", "Unknown"),
            chapter_time_period=chapter_info.get("chapter_time_period", "Unknown"),
            chapter_scenario=chapter_info.get("chapter_scenario", "None")
        )
        
        if not system_prompt or not system_prompt.strip():
            logger.error("[CONCLUDING SCENE] System prompt is empty for chapter_conclusion")
            raise ValueError("Failed to load system prompt for chapter conclusion")
        if not user_prompt or not user_prompt.strip():
            logger.error("[CONCLUDING SCENE] User prompt is empty for chapter_conclusion")
            raise ValueError("Failed to load user prompt for chapter conclusion")
        
        max_tokens = prompt_manager.get_max_tokens("chapter_conclusion")
        logger.info(f"[CONCLUDING SCENE STREAMING] Starting generation with max_tokens: {max_tokens}")
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:
                yield cleaned_chunk
        
        logger.info("[CONCLUDING SCENE STREAMING] Generation complete")
    
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
        
        # Get choices count and scene length from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length = generation_prefs.get("scene_length", "medium")
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
            choices_count=choices_count
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
        choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
        
        # Clean scene content to remove any instruction tags or formatting artifacts
        cleaned_scene_content = self._clean_instruction_tags(scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)
        
        final_message = f"""=== SCENE JUST GENERATED ===
{cleaned_scene_content}

=== GENERATE CHOICES ===
Based on the scene above, generate {choices_count} narrative choices for what happens next.

{choices_reminder}

Output ONLY valid JSON in this exact format:
{{"choices": ["choice 1", "choice 2", "choice 3", "choice 4"]}}"""
        
        messages.append({"role": "user", "content": final_message})
        
        # Calculate max tokens
        base_max_tokens = prompt_manager.get_max_tokens("choice_generation", user_settings)
        dynamic_max_tokens = max(base_max_tokens, choices_count * 50)
        max_tokens = dynamic_max_tokens
        
        logger.info(f"[CHOICES] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output to prompt_choice_sent.txt for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_choice_sent.txt")
                client = self.get_user_client(user_id, user_settings)
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    f.write("=" * 80 + "\n")
                    f.write("CHOICE GENERATION PROMPT (EXACTLY AS SENT TO LLM)\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"NUMBER OF MESSAGES: {len(messages)}\n")
                    f.write("-" * 80 + "\n")
                    for i, msg in enumerate(messages):
                        f.write(f"MESSAGE {i+1} [{msg['role'].upper()}]:\n")
                        f.write(msg['content'][:500] + "..." if len(msg['content']) > 500 else msg['content'])
                        f.write("\n" + "-" * 40 + "\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"GENERATION PARAMETERS:\n")
                    f.write(f"  max_tokens: {max_tokens}\n")
                    f.write(f"  model: {client.model_string}\n")
                    f.write("-" * 80 + "\n")
                    f.write("FULL MESSAGES ARRAY (JSON):\n")
                    f.write(json.dumps(messages, indent=2, ensure_ascii=False))
                    f.write("\n")
                    f.write("=" * 80 + "\n")
            except Exception as e:
                logger.warning(f"Failed to write choice prompt debug file: {e}")
        
        # Use the multi-message generation method
        response = await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
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
    
    def _get_scene_length_description(self, scene_length: str) -> str:
        """Convert scene_length setting to word range description"""
        length_map = {
            "short": "approximately 100-150 words",
            "medium": "approximately 200-300 words", 
            "long": "approximately 400-500 words"
        }
        return length_map.get(scene_length, "approximately 200-300 words")
    
    def _format_characters_section(self, characters: Any) -> str:
        """
        Format characters section for context.
        
        Args:
            characters: Either a list of character dicts or a dict with active_characters/inactive_characters
            
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
                char_descriptions.append(char_desc)
        
        if char_descriptions:
            return f"Characters:\n{chr(10).join(char_descriptions)}"
        return ""
    
    def _format_context_as_messages(self, context: Dict[str, Any], scene_batch_size: int = 10) -> List[Dict[str, str]]:
        """
        Format context as multiple user messages for better LLM cache utilization.
        
        By splitting context into multiple user messages, we improve cache hit rates:
        - Earlier messages (story foundation, chapter summaries) remain stable
        - Only later messages (entity states, recent scenes) change frequently
        - Scenes are batched into groups aligned with extraction intervals for optimal caching
        
        Message order (most stable → most dynamic):
        1. Story Foundation: genre, tone, setting, scenario, characters
        2. Chapter Context: story_so_far, previous/current chapter summaries
        3. Entity States: character states, locations, objects
        4. Semantic Events: relevant past events from semantic search (stable)
        5. Scene Batches: completed scene batches (stable per batch)
        6. Recent Scenes: active batch of most recent scenes (changes each scene)
        
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
        
        # Characters section
        characters = context.get("characters")
        if characters:
            char_text = self._format_characters_section(characters)
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
        
        # === MESSAGE 3: Entity States (changes every N scenes when extraction runs) ===
        entity_parts = []
        previous_scenes_text = context.get("previous_scenes", "")
        
        if previous_scenes_text:
            # Extract entity states sections from previous_scenes
            # These are formatted by SemanticContextManager._get_entity_states()
            
            # Character states
            entity_states_match = re.search(
                r'CURRENT CHARACTER STATES:(.*?)(?=\n\n(?:CURRENT LOCATIONS|Notable Objects|Recent Scenes|Relevant Past Events)|$)', 
                previous_scenes_text, re.DOTALL
            )
            if entity_states_match:
                entity_parts.append(f"CURRENT CHARACTER STATES:{entity_states_match.group(1).strip()}")
            
            # Locations
            locations_match = re.search(
                r'CURRENT LOCATIONS:(.*?)(?=\n\n(?:Notable Objects|Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES)|$)',
                previous_scenes_text, re.DOTALL
            )
            if locations_match:
                entity_parts.append(f"CURRENT LOCATIONS:{locations_match.group(1).strip()}")
            
            # Objects
            objects_match = re.search(
                r'Notable Objects:(.*?)(?=\n\n(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)',
                previous_scenes_text, re.DOTALL
            )
            if objects_match:
                entity_parts.append(f"Notable Objects:{objects_match.group(1).strip()}")
        
        if entity_parts:
            messages.append({
                "role": "user",
                "content": "=== CURRENT STATE ===\n" + "\n\n".join(entity_parts)
            })
        
        # === MESSAGE 4: Semantic Events (stable - only changes when semantic search results change) ===
        if previous_scenes_text:
            # Extract semantic/relevant events if present - these are stable between extractions
            relevant_match = re.search(
                r'Relevant Past Events:(.*?)(?=\n\n(?:Recent Scenes|CURRENT CHARACTER STATES|CURRENT LOCATIONS|Notable Objects)|$)',
                previous_scenes_text, re.DOTALL
            )
            if relevant_match:
                messages.append({
                    "role": "user",
                    "content": "=== RELEVANT PAST EVENTS ===\n" + relevant_match.group(1).strip()
                })
        
        # === MESSAGES 5+: Scene Batches (batch-aligned for optimal caching) ===
        if previous_scenes_text:
            # Extract recent scenes section
            recent_match = re.search(r'Recent Scenes:(.*?)$', previous_scenes_text, re.DOTALL)
            if recent_match:
                scenes_text = recent_match.group(1).strip()
                scene_messages = self._batch_scenes_as_messages(scenes_text, scene_batch_size)
                messages.extend(scene_messages)
            elif not relevant_match:
                # No structured sections found, use the whole previous_scenes as-is
                # This handles the case where context_manager returns simple scene list
                messages.append({
                    "role": "user",
                    "content": "=== STORY PROGRESS ===\n" + previous_scenes_text
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
            
            # Format scenes
            formatted_scenes = []
            for scene_num, content in scenes_in_batch:
                formatted_scenes.append(f"Scene {scene_num}:  {content}")
            
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
            
            # Extract Current Chapter Summary (if present)
            # Support both old "IMPORTANT OBJECTS:" and new "Notable Objects:" for backward compatibility
            # Note: Sections may have leading newlines, so we match them flexibly
            current_chapter_summary_match = re.search(r'Current Chapter Summary[^:]*:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
            current_chapter_summary = current_chapter_summary_match.group(1).strip() if current_chapter_summary_match else None
            
            # Extract Recent Scenes section
            recent_scenes_match = re.search(r'Recent Scenes:\s*(.*?)(?=\n+(?:Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
            recent_scenes_content = recent_scenes_match.group(1).strip() if recent_scenes_match else None
            
            # Extract Relevant Past Events (semantic search results)
            relevant_events_match = re.search(r'Relevant Past Events:\s*(.*?)(?=\n+(?:Recent Scenes|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
            relevant_events_content = relevant_events_match.group(1).strip() if relevant_events_match else None
            
            # Extract Entity States sections (may have leading newlines)
            entity_states_match = re.search(r'\n*(CURRENT CHARACTER STATES:.*?)(?=\n+(?:CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events)|$)', previous_scenes_text, re.DOTALL)
            entity_states_content = entity_states_match.group(1).strip() if entity_states_match else None
            
            locations_match = re.search(r'\n*CURRENT LOCATIONS:\s*(.*?)(?=\n+(?:IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES)|$)', previous_scenes_text, re.DOTALL)
            locations_content = locations_match.group(1).strip() if locations_match else None
            
            # Support both old and new object header names (may have leading newlines)
            # Try new format first, then fall back to old format
            objects_match = re.search(r'\n*Notable Objects:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
            if not objects_match:
                objects_match = re.search(r'\n*IMPORTANT OBJECTS:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
            objects_content = objects_match.group(1).strip() if objects_match else None
            
            # Build organized context sections
            # NEW ORDER: Entity states come BEFORE chapter progress and scenes (reduces recency bias)
            
            # Add Current State section if we have entity states (positioned early as reference material)
            if entity_states_content or locations_content or objects_content:
                context_parts.append("Current State:")
                
                if entity_states_content:
                    context_parts.append(f"  {entity_states_content.replace(chr(10), chr(10) + '  ')}")
                
                if locations_content:
                    context_parts.append(f"\n  CURRENT LOCATIONS:\n  {locations_content.replace(chr(10), chr(10) + '  ')}")
                
                if objects_content:
                    context_parts.append(f"\n  Notable Objects:\n  {objects_content.replace(chr(10), chr(10) + '  ')}")
            
            # Add Current Chapter Progress (positioned after entity states, before scenes)
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
        try:
            from ...models import StoryFlow, Scene
            
            # Get active branch if not specified
            if branch_id is None:
                branch_id = self._get_active_branch_id(db, story_id)
            
            # First, delete all StoryFlow entries for this story with sequence_number >= sequence_number (filtered by branch)
            flow_delete_query = db.query(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.sequence_number >= sequence_number
            )
            if branch_id:
                flow_delete_query = flow_delete_query.filter(StoryFlow.branch_id == branch_id)
            story_flows_deleted = flow_delete_query.delete()
            
            # Get scenes to delete (don't use bulk delete to ensure cascades work) - filtered by branch
            scene_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= sequence_number
            )
            if branch_id:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scenes_to_delete = scene_query.all()
            
            # NOTE: Semantic cleanup (embeddings, character moments, plot events) is now handled
            # as a background task by the API endpoint to avoid blocking the response.
            # This method only handles fast database deletions.
            logger.info(f"[DELETE] Will delete {len(scenes_to_delete)} scenes (sequence {sequence_number} onwards)")
            
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
            
            # Delete each scene individually to trigger cascade relationships
            scenes_deleted = 0
            for scene in scenes_to_delete:
                db.delete(scene)
                scenes_deleted += 1
            
            # Recalculate scenes_count and invalidate affected batches for affected chapters
            from ...models import Chapter, ChapterSummaryBatch
            from ...api.chapters import update_chapter_summary_from_batches
            
            for chapter_id in affected_chapter_ids:
                chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
                if chapter:
                    chapter.scenes_count = self.get_active_scene_count(db, story_id, chapter_id)
                    logger.info(f"[DELETE] Updated chapter {chapter_id} scenes_count to {chapter.scenes_count}")
                    
                    # Invalidate batches that overlap with deleted scenes
                    affected_batches = db.query(ChapterSummaryBatch).filter(
                        ChapterSummaryBatch.chapter_id == chapter_id,
                        ChapterSummaryBatch.start_scene_sequence <= max_deleted_seq,
                        ChapterSummaryBatch.end_scene_sequence >= min_deleted_seq
                    ).all()
                    
                    if affected_batches:
                        for batch in affected_batches:
                            db.delete(batch)
                        logger.info(f"[DELETE] Invalidated {len(affected_batches)} batch(es) for chapter {chapter_id} due to scene deletion")
                        
                        # Recalculate summary from remaining batches
                        update_chapter_summary_from_batches(chapter_id, db)
                    
                    # Update last_extraction_scene_count to max remaining sequence
                    # This prevents extraction from being skipped due to negative scene counts
                    remaining_scenes = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.chapter_id == chapter_id,
                        Scene.is_deleted == False
                    ).all()
                    
                    if remaining_scenes:
                        max_remaining_seq = max(s.sequence_number for s in remaining_scenes)
                        # Only lower it, never raise it (scenes were deleted, not added)
                        if chapter.last_extraction_scene_count and chapter.last_extraction_scene_count > max_remaining_seq:
                            chapter.last_extraction_scene_count = max_remaining_seq
                            logger.info(f"[DELETE] Updated chapter {chapter_id} last_extraction_scene_count to {max_remaining_seq}")
                    else:
                        chapter.last_extraction_scene_count = 0
                        logger.info(f"[DELETE] Reset chapter {chapter_id} last_extraction_scene_count to 0 (no remaining scenes)")
            
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
                            
                            # Check if remaining scenes form a complete batch
                            last_remaining_scene = db.query(Scene).filter(
                                Scene.story_id == story_id,
                                Scene.sequence_number < sequence_number
                            ).order_by(Scene.sequence_number.desc()).first()
                            
                            if last_remaining_scene:
                                batch_threshold = user_settings.get("context_summary_threshold", 5)
                                last_sequence = last_remaining_scene.sequence_number
                                is_complete_batch = (last_sequence % batch_threshold) == 0
                                
                                if is_complete_batch:
                                    # Complete batch - recalculate (will re-extract)
                                    await entity_service.recalculate_entity_states_from_batches(
                                        db, story_id, story.owner_id, user_settings, max_deleted_seq
                                    )
                                    logger.info(f"[DELETE] Recalculated entity states (complete batch) for story {story_id}")
                                else:
                                    # Incomplete batch - only restore, don't re-extract
                                    entity_service.restore_from_last_complete_batch(
                                        db, story_id, max_deleted_seq
                                    )
                                    logger.info(f"[DELETE] Restored entity states from last complete batch (incomplete batch remains, waiting for threshold) for story {story_id}")
                            else:
                                # No remaining scenes - just clear entity states
                                from ...models import CharacterState, LocationState, ObjectState
                                db.query(CharacterState).filter(CharacterState.story_id == story_id).delete()
                                db.query(LocationState).filter(LocationState.story_id == story_id).delete()
                                db.query(ObjectState).filter(ObjectState.story_id == story_id).delete()
                                logger.info(f"[DELETE] No remaining scenes, cleared entity states for story {story_id}")
                        else:
                            logger.warning(f"[DELETE] No user settings found for story owner {story.owner_id}, skipping entity state restoration")
                    else:
                        logger.warning(f"[DELETE] Story {story_id} not found, skipping entity state restoration")
                except Exception as e:
                    # Don't fail scene deletion if entity state restoration fails
                    logger.warning(f"[DELETE] Failed to restore entity states after scene deletion: {e}")
                    import traceback
                    logger.warning(f"[DELETE] Traceback: {traceback.format_exc()}")
            
            # Commit the transaction
            db.commit()
            
            logger.info(f"Deleted {story_flows_deleted} story flows and {scenes_deleted} scenes from sequence {sequence_number} onwards for story {story_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete scenes from sequence {sequence_number} for story {story_id}: {e}")
            db.rollback()
            return False

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
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.txt")
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    f.write("=" * 80 + "\n")
                    f.write("MULTI-MESSAGE STREAMING PROMPT (EXACTLY AS SENT TO LLM)\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"NUMBER OF MESSAGES: {len(messages)}\n")
                    f.write("-" * 80 + "\n")
                    for i, msg in enumerate(messages):
                        f.write(f"MESSAGE {i+1} [{msg['role'].upper()}]:\n")
                        f.write(msg['content'][:500] + "..." if len(msg['content']) > 500 else msg['content'])
                        f.write("\n" + "-" * 40 + "\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"GENERATION PARAMETERS:\n")
                    f.write(f"  max_tokens: {gen_params.get('max_tokens')}\n")
                    f.write(f"  temperature: {gen_params.get('temperature')}\n")
                    f.write(f"  model: {client.model_string}\n")
                    f.write("-" * 80 + "\n")
                    f.write("FULL MESSAGES ARRAY (JSON):\n")
                    f.write(json.dumps(messages, indent=2, ensure_ascii=False))
                    f.write("\n")
                    f.write("=" * 80 + "\n")
            except Exception as e:
                logger.warning(f"Failed to write prompt debug file: {e}")
        
        try:
            response = await acompletion(**gen_params)
            
            async for chunk in response:
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        yield delta.content
                        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Multi-message streaming failed for user {user_id}: {error_msg}")
            raise ValueError(f"LLM streaming failed: {error_msg}")
