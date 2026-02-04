"""
LLM Generation Core

Extracted from UnifiedLLMService to handle core LLM generation operations
including chat completion, text completion, streaming, and HTTP fallbacks.
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

import httpx
from litellm import acompletion

from .thinking_parser import ThinkingTagParser
from .templates import TextCompletionTemplateManager
from ...config import settings

if TYPE_CHECKING:
    from .client import LLMClient

logger = logging.getLogger(__name__)


class LLMConnectionError(Exception):
    """Raised when LLM server is unavailable or connection fails."""
    pass


class LLMGenerationCore:
    """
    Handles core LLM generation operations.

    This class is used by UnifiedLLMService to separate generation logic
    from other service concerns.
    """

    def __init__(self, service: 'UnifiedLLMService'):
        """
        Initialize with a reference to the parent service.

        Args:
            service: The UnifiedLLMService instance that owns this generator.
        """
        self._service = service

    def _get_prompt_debug_path(self, filename: str) -> str:
        """Get the path for prompt debug files, handling both Docker and bare-metal environments."""
        # Check if we're in Docker (working directory is /app)
        if os.path.exists("/app") and os.getcwd().startswith("/app"):
            # Docker: use mounted logs directory
            return f"/app/root_logs/{filename}"
        else:
            # Bare-metal: use logs directory relative to project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
            logs_dir = os.path.join(project_root, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            return os.path.join(logs_dir, filename)

    async def generate(
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

        client = self._service.get_user_client(user_id, user_settings)

        # Check completion mode and branch accordingly
        completion_mode = client.completion_mode
        logger.debug(f"User {user_id} generation mode: {completion_mode} (from client.completion_mode={client.completion_mode})")
        if completion_mode == "text":
            logger.debug(f"Using text completion API for user {user_id}")
            return await self.generate_text_completion(
                prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            )

        logger.debug(f"Using chat completion API for user {user_id}")

        # Inject NSFW filter if needed
        from ...utils.content_filter import inject_nsfw_filter_if_needed
        final_system_prompt = inject_nsfw_filter_if_needed(
            system_prompt=system_prompt,
            user_settings=user_settings,
            user_id=user_id,
            skip_nsfw_filter=skip_nsfw_filter,
            context="chat completion"
        )
        messages = []
        if final_system_prompt:
            messages.append({"role": "system", "content": final_system_prompt})

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
                    raise LLMConnectionError(f"API endpoint not found. For TabbyAPI and similar services, try adding '/v1' to your URL: {client.api_url}/v1")
                else:
                    raise LLMConnectionError(f"API endpoint not found at {client.api_url}. Please check your URL.")
            elif "401" in error_msg or "Unauthorized" in error_msg:
                raise LLMConnectionError(f"Authentication failed. Please check your API key.")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise LLMConnectionError(f"Access forbidden. Please check your API key and permissions.")
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                raise LLMConnectionError(f"Cannot connect to {client.api_url}. Please check if the service is running and accessible.")
            else:
                # Fallback to direct HTTP for LM Studio and TabbyAPI
                if client.api_type in ["lm_studio", "openai_compatible"]:
                    logger.info(f"Attempting direct HTTP fallback for {client.api_type}")
                    return await self.direct_http_fallback(client, messages, max_tokens, temperature, False, user_settings)
                else:
                    logger.error(f"LLM generation failed for user {user_id}: {error_msg}")
                    raise ValueError(f"LLM generation failed: {error_msg}")

    async def generate_text_completion(
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

        client = self._service.get_user_client(user_id, user_settings)

        # Inject NSFW filter if needed
        from ...utils.content_filter import inject_nsfw_filter_if_needed
        system_prompt = inject_nsfw_filter_if_needed(
            system_prompt=system_prompt,
            user_settings=user_settings,
            user_id=user_id,
            skip_nsfw_filter=skip_nsfw_filter,
            context="text completion"
        )

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
            return await self.direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, False, user_settings)

        # For other providers, try LiteLLM
        try:
            logger.info(f"Text completion with {client.model_string} for user {user_id}")
            logger.debug(f"Calling text_completion with model={gen_params['model']}, prompt_length={len(gen_params['prompt'])}")

            # Use litellm.text_completion for text completion (synchronous, run in thread)
            from litellm import text_completion

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

    async def direct_http_fallback(self, client, messages, max_tokens, temperature, stream, user_settings: Optional[Dict[str, Any]] = None):
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

    async def direct_http_text_completion_fallback(self, client, prompt, max_tokens, temperature, stream, user_settings: Optional[Dict[str, Any]] = None):
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

    async def generate_stream(
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

        client = self._service.get_user_client(user_id, user_settings)

        # Check completion mode and branch accordingly
        completion_mode = client.completion_mode
        logger.debug(f"User {user_id} streaming generation mode: {completion_mode} (from client.completion_mode={client.completion_mode})")
        if completion_mode == "text":
            logger.debug(f"Using text completion streaming API for user {user_id}")
            async for chunk in self.generate_text_completion_stream(
                prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            ):
                yield chunk
            return

        logger.debug(f"Using chat completion streaming API for user {user_id}")

        # Inject NSFW filter if needed
        from ...utils.content_filter import inject_nsfw_filter_if_needed
        final_system_prompt = inject_nsfw_filter_if_needed(
            system_prompt=system_prompt,
            user_settings=user_settings,
            user_id=user_id,
            skip_nsfw_filter=skip_nsfw_filter,
            context="chat streaming"
        )
        messages = []
        if final_system_prompt:
            messages.append({"role": "system", "content": final_system_prompt})

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

                # Check for reasoning content - different providers use different field names:
                # - reasoning_content: LiteLLM's standardized field (Anthropic, DeepSeek)
                # - reasoning: OpenRouter's field for models like GLM-4.7
                delta = chunk.choices[0].delta
                reasoning_text = None
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    reasoning_text = delta.reasoning_content
                elif hasattr(delta, 'reasoning') and delta.reasoning:
                    reasoning_text = delta.reasoning

                if reasoning_text:
                    has_reasoning = True
                    reasoning_chars += len(reasoning_text)
                    # Yield reasoning with special prefix for frontend to detect
                    yield f"__THINKING__:{reasoning_text}"

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
            error_msg = str(e)
            logger.error(f"LLM streaming failed for user {user_id}: {error_msg}")
            # Raise specific exception for connection errors so endpoints can handle gracefully
            if any(keyword in error_msg.lower() for keyword in ['connection', 'connect', 'timeout', 'unreachable', 'refused']):
                raise LLMConnectionError(f"Cannot connect to LLM server: {error_msg}")
            raise ValueError(f"LLM streaming failed: {error_msg}")

    async def generate_text_completion_stream(
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

        client = self._service.get_user_client(user_id, user_settings)

        # Inject NSFW filter if needed
        from ...utils.content_filter import inject_nsfw_filter_if_needed
        system_prompt = inject_nsfw_filter_if_needed(
            system_prompt=system_prompt,
            user_settings=user_settings,
            user_id=user_id,
            skip_nsfw_filter=skip_nsfw_filter,
            context="text completion streaming"
        )

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
            async for chunk in await self.direct_http_text_completion_fallback(client, rendered_prompt, max_tokens, temperature, True, user_settings):
                yield chunk
            return

        # For other providers, try LiteLLM
        try:
            logger.info(f"Streaming text completion with {client.model_string} for user {user_id}")
            logger.debug(f"Calling text_completion (streaming) with model={gen_params['model']}, prompt_length={len(gen_params['prompt'])}")

            # Use litellm.text_completion for text completion
            # text_completion returns a synchronous generator when stream=True
            from litellm import text_completion

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
