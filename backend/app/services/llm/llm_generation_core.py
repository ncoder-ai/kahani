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

from litellm import acompletion

from .thinking_parser import ThinkingTagParser
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
                logger.error(f"LLM generation failed for user {user_id}: {error_msg}")
                raise ValueError(f"LLM generation failed: {error_msg}")

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
