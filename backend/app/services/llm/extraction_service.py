"""
Extraction LLM Service

Provider-agnostic service for using small local models (via OpenAI-compatible APIs)
for extraction tasks like plot event extraction. Optimized for fast, cost-effective extraction.
"""

import litellm
from typing import Dict, Any, List, Tuple, Optional, Union
import logging
import time
import json
import re
import httpx
from .prompts import prompt_manager

logger = logging.getLogger(__name__)


def extract_json_robust(text: str) -> Union[Dict, List]:
    """
    Robustly extract JSON from LLM response text.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Extra content after valid JSON
    - Whitespace and formatting issues

    Returns:
        Parsed JSON (dict or list)

    Raises:
        json.JSONDecodeError if no valid JSON found
    """
    if not text:
        raise json.JSONDecodeError("Empty response", text, 0)

    original_text = text
    text = text.strip()

    # Step 1: Remove markdown code blocks
    if text.startswith("```"):
        # Find the end of the opening line (```json or just ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]

    # Remove trailing ``` if present
    if "```" in text:
        # Find first ``` and take everything before it
        end_marker = text.find("```")
        if end_marker != -1:
            text = text[:end_marker]

    text = text.strip()

    # Step 2: Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Step 3: Find first complete JSON object or array using brace matching
    start_char = None
    end_char = None
    start_idx = -1

    # Find first { or [
    for i, char in enumerate(text):
        if char == '{':
            start_char = '{'
            end_char = '}'
            start_idx = i
            break
        elif char == '[':
            start_char = '['
            end_char = ']'
            start_idx = i
            break

    if start_idx == -1:
        raise json.JSONDecodeError("No JSON object or array found", original_text, 0)

    # Count braces/brackets to find matching end
    depth = 0
    in_string = False
    escape_next = False
    end_idx = -1

    for i in range(start_idx, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == '\\' and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == start_char:
            depth += 1
        elif char == end_char:
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break

    if end_idx == -1:
        raise json.JSONDecodeError("Unclosed JSON structure", original_text, start_idx)

    json_str = text[start_idx:end_idx]

    try:
        result = json.loads(json_str)
        logger.debug(f"[JSON_EXTRACT] Successfully extracted JSON from position {start_idx} to {end_idx}")
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"[JSON_EXTRACT] Brace-matched JSON failed to parse: {e}")
        raise json.JSONDecodeError(f"Extracted JSON invalid: {e}", original_text, start_idx)

# Thinking tag patterns for different models
THINKING_PATTERNS = {
    "qwen3": re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE),
    "deepseek": re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE),
    "kimi": re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE),  # Kimi uses same format
    "glm": re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE),  # GLM also uses <think> tags
    # Models that use API parameters only (no pattern needed):
    # - mistral: Uses API parameter (prompt_mode=null)
    # - gemini: Uses API parameter (thinkingBudget=0)
    # - openai: Uses API parameter (reasoning_effort=none)
}


class ExtractionLLMService:
    """Extraction service for small models via OpenAI-compatible APIs or cloud providers"""

    # Cloud providers that LiteLLM routes natively (no api_base needed)
    CLOUD_PROVIDERS = {
        'openai', 'anthropic', 'groq', 'mistral', 'deepseek', 'together_ai',
        'fireworks_ai', 'openrouter', 'perplexity', 'deepinfra', 'gemini',
        'cohere', 'ai21', 'cerebras', 'sambanova', 'novita', 'xai',
    }

    def __init__(self, url: str = "", model: str = "", api_key: str = "",
                 temperature: float = 0.3, max_tokens: Optional[int] = None,
                 timeout_total: float = 240,
                 top_p: float = 1.0, repetition_penalty: float = 1.0,
                 min_p: float = 0.0, thinking_disable_method: str = "none",
                 thinking_disable_custom: str = "",
                 api_type: str = "openai-compatible"):
        """
        Initialize extraction service

        Args:
            url: API endpoint URL (required for local providers, optional for cloud)
            model: Model name to use
            api_key: API key if required (empty string for local servers)
            temperature: Temperature for generation (default 0.3 for more deterministic)
            max_tokens: Maximum tokens for response (None = let server decide, model stops naturally)
            timeout_total: Total timeout in seconds for requests (default 240, from user settings)
            top_p: Top-p (nucleus) sampling (default 1.0)
            repetition_penalty: Repetition penalty (default 1.0 = disabled)
            min_p: Minimum probability threshold (default 0.0)
            thinking_disable_method: Method to disable thinking output (none, qwen3, deepseek, mistral, gemini, openai, kimi, glm, custom)
            thinking_disable_custom: Custom regex pattern for thinking tag removal when method is "custom"
            api_type: Provider type (default "openai-compatible"). Cloud providers use LiteLLM native routing.
        """
        self.api_type = api_type
        self.is_cloud = api_type in self.CLOUD_PROVIDERS

        if self.is_cloud:
            # Cloud providers: URL is optional, LiteLLM routes natively
            self.url = url.rstrip('/') if url else ""
        else:
            # Local providers: URL is required
            self.url = url.rstrip('/') if url else ""
            # Ensure URL ends with /v1 for OpenAI-compatible endpoints
            if self.url and not self.url.endswith('/v1'):
                self.url = f"{self.url}/v1"

        self.model = model
        self.api_key = api_key or "not-needed"  # Some servers don't require key
        self.temperature = temperature
        self.max_tokens = max_tokens  # None = no limit (model stops naturally after producing output)
        self.timeout_total = timeout_total

        # Advanced sampling parameters
        self.top_p = top_p
        self.repetition_penalty = repetition_penalty
        self.min_p = min_p

        # Thinking disable settings
        self.thinking_disable_method = thinking_disable_method
        self.thinking_disable_custom = thinking_disable_custom
        self._thinking_pattern = self._compile_thinking_pattern()

        # Use timeout from user settings
        self.timeout_total = timeout_total

        # Configure LiteLLM
        self._configure_litellm()

    @classmethod
    def from_settings(
        cls,
        user_settings: Dict[str, Any],
        *,
        max_tokens_override: Optional[int] = None,
        temperature_override: Optional[float] = None,
    ) -> Optional['ExtractionLLMService']:
        """Create an ExtractionLLMService from user_settings dict.

        This is the single centralized factory for all extraction service instantiation.
        All callers should use this instead of constructing directly.

        Args:
            user_settings: Full user settings dict (with 'extraction_model_settings' and 'llm_settings' keys)
            max_tokens_override: Override the configured max_tokens (e.g. for NPC tracking)
            temperature_override: Override the configured temperature (e.g. for image prompts)

        Returns:
            ExtractionLLMService instance, or None if URL/model not configured
        """
        from ...config import settings as app_settings

        ext_settings = user_settings.get('extraction_model_settings', {})
        ext_defaults = app_settings._yaml_config.get('extraction_model', {})
        llm_settings = user_settings.get('llm_settings', {})

        url = ext_settings.get('url', ext_defaults.get('url', ''))
        model = ext_settings.get('model_name', ext_defaults.get('model_name', ''))
        api_type = ext_settings.get('api_type', ext_defaults.get('api_type', 'openai-compatible'))

        # Cloud providers don't need a URL
        is_cloud = api_type in cls.CLOUD_PROVIDERS
        if not model or (not url and not is_cloud):
            return None

        api_key = ext_settings.get('api_key', ext_defaults.get('api_key', ''))
        temperature = temperature_override if temperature_override is not None else ext_settings.get('temperature', ext_defaults.get('temperature', 0.3))
        max_tokens = max_tokens_override if max_tokens_override is not None else ext_settings.get('max_tokens', ext_defaults.get('max_tokens'))
        timeout_total = llm_settings.get('timeout_total', 240)

        # Advanced sampling
        top_p = ext_settings.get('top_p', ext_defaults.get('top_p', 1.0))
        repetition_penalty = ext_settings.get('repetition_penalty', ext_defaults.get('repetition_penalty', 1.0))
        min_p = ext_settings.get('min_p', ext_defaults.get('min_p', 0.0))

        # Thinking settings
        thinking_disable_method = ext_settings.get('thinking_disable_method', ext_defaults.get('thinking_disable_method', 'none'))
        thinking_disable_custom = ext_settings.get('thinking_disable_custom', ext_defaults.get('thinking_disable_custom', ''))

        return cls(
            url=url or '',
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_total=timeout_total,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            min_p=min_p,
            thinking_disable_method=thinking_disable_method,
            thinking_disable_custom=thinking_disable_custom,
            api_type=api_type,
        )

    def _compile_thinking_pattern(self) -> Optional[re.Pattern]:
        """Compile the regex pattern for thinking tag removal based on method"""
        method = self.thinking_disable_method

        if method == "none" or method == "glm":
            return None
        elif method == "custom" and self.thinking_disable_custom:
            try:
                return re.compile(self.thinking_disable_custom, re.IGNORECASE | re.DOTALL)
            except re.error as e:
                logger.warning(f"Invalid custom thinking pattern '{self.thinking_disable_custom}': {e}")
                return None
        elif method in THINKING_PATTERNS:
            return THINKING_PATTERNS[method]
        else:
            # API-based methods (mistral, gemini, openai) don't need patterns
            return None

    def _strip_thinking_tags(self, content: str) -> str:
        """Remove thinking tags and their content from response.

        For thinking models, the response is: <think>reasoning</think>actual output
        We strip the thinking block and return only the actual output.
        """
        if not self._thinking_pattern or not content:
            return content

        original_len = len(content)
        cleaned = self._thinking_pattern.sub("", content).strip()

        if len(cleaned) < original_len:
            logger.debug(f"Stripped thinking tags: {original_len} -> {len(cleaned)} chars")

        return cleaned

    def _get_prompt_prefix(self, allow_thinking: bool = False) -> str:
        """Get any prompt prefix needed for thinking disable (e.g., /no_think for Qwen3)"""
        if allow_thinking:
            return ""
        if self.thinking_disable_method == "qwen3":
            return "/no_think "
        return ""
    
    def _configure_litellm(self):
        """Configure LiteLLM for extraction service"""
        # Disable verbose logging
        litellm.set_verbose = False
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        
        # Set environment variables to suppress warnings
        import os
        os.environ["LITELLM_LOG"] = "ERROR"
        os.environ["LITELLM_LOG_LEVEL"] = "ERROR"
        os.environ["LITELLM_SUPPRESS_DEBUG_INFO"] = "true"
        os.environ["LITELLM_DROP_PARAMS"] = "true"
        
        logger.info(f"ExtractionLLMService configured: url={self.url}, model={self.model}")
    
    def _build_model_string(self) -> str:
        """Build LiteLLM model string based on provider type"""
        if self.is_cloud:
            if self.api_type == "openai":
                return self.model  # OpenAI is default in LiteLLM
            return f"{self.api_type}/{self.model}"
        # Local providers: use openai/ prefix for OpenAI-compatible APIs
        return f"openai/{self.model}"
    
    def _get_generation_params(self, max_tokens: Optional[int] = None, allow_thinking: bool = False) -> Dict[str, Any]:
        """Get generation parameters for API calls.

        max_tokens precedence: explicit arg > self.max_tokens > omitted (server decides).
        Omitting max_tokens lets thinking models (Qwen3, DeepSeek) use tokens for
        reasoning without hitting an artificial ceiling. The model stops naturally
        after producing the requested JSON, and timeout is the safety net.

        When allow_thinking is True, API-specific thinking disable parameters are skipped
        so the model can use chain-of-thought reasoning.
        """
        resolved_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        params = {
            "model": self._build_model_string(),
            "api_key": self.api_key,
            "temperature": self.temperature,
        }
        # Only set api_base for local providers (cloud providers use LiteLLM native routing)
        if not self.is_cloud and self.url:
            params["api_base"] = self.url
        if resolved_max_tokens is not None:
            params["max_tokens"] = resolved_max_tokens

        # Build extra_body for non-standard params (needed for KoboldCpp and other OpenAI-compat servers)
        extra_body = {}

        # Add advanced sampling parameters to extra_body
        if self.top_p < 1.0:
            params["top_p"] = self.top_p  # Standard OpenAI param

        if self.repetition_penalty != 1.0:
            extra_body["repetition_penalty"] = self.repetition_penalty

        if self.min_p > 0.0:
            extra_body["min_p"] = self.min_p

        # Add API-specific thinking disable parameters (only when NOT allowing thinking)
        if not allow_thinking:
            if self.thinking_disable_method == "mistral":
                params["prompt_mode"] = None
            elif self.thinking_disable_method == "openai":
                params["reasoning_effort"] = "none"
            elif self.thinking_disable_method == "gemini":
                params["thinking_config"] = {"thinking_budget": 0}
            elif self.thinking_disable_method == "glm":
                # GLM models support enable_thinking=False in chat template
                # Pass via extra_body for vLLM/OpenAI-compatible servers
                extra_body["chat_template_kwargs"] = {"enable_thinking": False}

        # Only add extra_body if it has content
        if extra_body:
            params["extra_body"] = extra_body

        # Log the params being used (excluding api_key)
        log_params = {k: v for k, v in params.items() if k != "api_key"}
        logger.info(f"[EXTRACTION] Generation params: temp={params.get('temperature')}, top_p={params.get('top_p', 1.0)}, allow_thinking={allow_thinking}, extra_body={extra_body if extra_body else 'none'}")

        return params
    
    async def test_connection(self) -> Tuple[bool, str, float]:
        """
        Test if the extraction endpoint is available
        
        Returns:
            Tuple of (success: bool, message: str, response_time: float)
        """
        start_time = time.time()
        try:
            from litellm import acompletion
            
            # Simple test request — apply prompt prefix (e.g. /no_think for Qwen3)
            prefix = self._get_prompt_prefix()
            test_prompt = f"{prefix}Say 'OK'" if prefix else "Say 'OK'"
            params = self._get_generation_params(max_tokens=10)
            response = await acompletion(
                **params,
                messages=[{"role": "user", "content": test_prompt}],
                timeout=self.timeout_total
            )

            response_time = time.time() - start_time
            content = response.choices[0].message.content
            # Strip thinking tags if present
            content = self._strip_thinking_tags(content) if content else content
            
            if content:
                return True, f"Connection successful (model responded)", response_time
            else:
                return False, "Model responded but returned empty content", response_time
            
        except Exception as e:
            response_time = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Extraction model connection test failed: {error_msg}")
            
            # Provide helpful error messages
            if "404" in error_msg or "Not Found" in error_msg:
                return False, f"Endpoint not found at {self.url}. Check if the service is running.", response_time
            elif "401" in error_msg or "Unauthorized" in error_msg:
                return False, "Authentication failed. Check your API key.", response_time
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                return False, f"Cannot connect to {self.url}. Is the service running?", response_time
            else:
                return False, f"Connection failed: {error_msg}", response_time

    async def check_health(self, timeout: float = 3.0) -> Tuple[bool, str]:
        """
        Quick connectivity check - verify extraction server is reachable without doing inference.

        Args:
            timeout: Maximum time to wait for response (default 3 seconds)

        Returns:
            Tuple of (is_healthy: bool, message: str)
        """
        # Cloud providers: skip health check, assume available
        if self.is_cloud:
            logger.debug(f"Skipping health check for cloud extraction provider: {self.api_type}")
            return True, f"Cloud provider {self.api_type} - assuming available"

        # Ensure URL has /v1 suffix
        base_url = self.url
        if not base_url.endswith('/v1'):
            base_url = f"{base_url}/v1"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

                # Try /models endpoint (standard OpenAI-compatible endpoint)
                try:
                    response = await client.get(f"{base_url}/models", headers=headers)
                    if response.status_code < 500:
                        return True, "Extraction server is reachable"
                    elif response.status_code >= 500:
                        return False, f"Extraction server error (status {response.status_code})"
                except httpx.HTTPStatusError:
                    pass  # Try fallback

                # Fallback: try base URL
                response = await client.get(base_url, headers=headers)
                if response.status_code < 500:
                    return True, "Extraction server is reachable"
                else:
                    return False, f"Extraction server returned error status {response.status_code}"

        except httpx.ConnectError:
            return False, f"Cannot connect to extraction server at {self.url}. Is it running?"
        except httpx.TimeoutException:
            return False, f"Extraction server at {self.url} is not responding (timeout after {timeout}s)"
        except Exception as e:
            return False, f"Extraction health check failed: {str(e)}"

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        allow_thinking: bool = False
    ) -> str:
        """
        Generic text generation method for extraction tasks.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens for response
            allow_thinking: When True, skip thinking disable (let model use CoT)

        Returns:
            Generated text response
        """
        try:
            from litellm import acompletion

            params = self._get_generation_params(max_tokens=max_tokens, allow_thinking=allow_thinking)

            # Apply prompt prefix if needed (e.g., /no_think for Qwen3)
            prefix = self._get_prompt_prefix(allow_thinking=allow_thinking)
            final_prompt = f"{prefix}{prompt}" if prefix else prompt

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": final_prompt})

            response = await acompletion(
                **params,
                messages=messages,
                timeout=self.timeout_total
            )

            content = response.choices[0].message.content
            content = content.strip() if content else ""

            # Strip thinking tags if configured
            content = self._strip_thinking_tags(content)

            return content

        except Exception as e:
            logger.error(f"Extraction model generation failed: {e}")
            raise

    async def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        allow_thinking: bool = False
    ) -> str:
        """
        Generate using a full message array (for cache-friendly unified extraction).

        This method accepts the same message structure as the main LLM,
        enabling unified code paths for both extraction LLM and main LLM.

        Args:
            messages: Full message array with role/content dicts
            max_tokens: Maximum tokens for response
            allow_thinking: When True, skip thinking disable (let model use CoT)

        Returns:
            Generated text response
        """
        try:
            from litellm import acompletion

            params = self._get_generation_params(max_tokens=max_tokens, allow_thinking=allow_thinking)

            # Apply prompt prefix to last user message if needed (e.g., /no_think for Qwen3)
            prefix = self._get_prompt_prefix(allow_thinking=allow_thinking)
            if prefix:
                messages = [msg.copy() for msg in messages]  # Don't mutate original
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = f"{prefix}{messages[i]['content']}"
                        break

            response = await acompletion(
                **params,
                messages=messages,
                timeout=self.timeout_total
            )

            content = response.choices[0].message.content
            content = content.strip() if content else ""

            # Strip thinking tags if configured
            content = self._strip_thinking_tags(content)

            return content

        except Exception as e:
            logger.error(f"Extraction model generation_with_messages failed: {e}")
            raise

    async def extract_plot_events(
        self, 
        scene_content: str, 
        thread_context: str = "",
        system_prompt: str = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
    ) -> List[Dict[str, Any]]:
        """
        Extract plot events from a single scene
        
        Args:
            scene_content: Scene text to analyze
            thread_context: Context about existing plot threads
            system_prompt: System prompt for the model
            
        Returns:
            List of event dictionaries
        """
        try:
            from litellm import acompletion
            
            # Build prompt
            prompt = f"""Analyze the following scene and extract significant plot events.{thread_context}

Scene:
{scene_content}

For each significant plot event, identify:
1. Event type: "introduction" (new element), "complication" (conflict/challenge), "revelation" (discovery/twist), or "resolution" (solving a thread)
2. Description: Brief description of the event (1-2 sentences)
3. Importance (0-100): How significant is this event for the overall plot?
4. Confidence (0-100): How certain are you this is a significant plot event?
5. Involved characters: Names of characters involved (array of strings, or empty array)

Return ONLY valid JSON in this exact format:
{{
  "events": [
    {{
      "event_type": "complication",
      "description": "Description of the event",
      "importance": 85,
      "confidence": 95,
      "involved_characters": ["Character1", "Character2"]
    }}
  ]
}}

If no events found, return {{"events": []}}. Return ONLY the JSON, no other text."""
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            return self._parse_json_response(content)
            
        except Exception as e:
            logger.error(f"Failed to extract plot events with extraction model: {e}")
            raise
    
    async def extract_plot_events_batch(
        self,
        scenes_content: str,
        thread_context: str = "",
        system_prompt: str = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
    ) -> List[Dict[str, Any]]:
        """
        Extract plot events from multiple scenes in batch
        
        Args:
            scenes_content: Multiple scenes text (with scene markers)
            thread_context: Context about existing plot threads
            system_prompt: System prompt for the model
            
        Returns:
            List of event dictionaries
        """
        try:
            from litellm import acompletion
            
            # Build batch prompt
            prompt = f"""Analyze the following scenes and extract significant plot events.{thread_context}

Scenes:
{scenes_content}

For each significant plot event, identify:
1. Event type: "introduction" (new element), "complication" (conflict/challenge), "revelation" (discovery/twist), or "resolution" (solving a thread)
2. Description: Brief description of the event (1-2 sentences)
3. Importance (0-100): How significant is this event for the overall plot?
4. Confidence (0-100): How certain are you this is a significant plot event?
5. Involved characters: Names of characters involved (array of strings, or empty array)

Return ONLY valid JSON in this exact format:
{{
  "events": [
    {{
      "event_type": "complication",
      "description": "Description of the event",
      "importance": 85,
      "confidence": 95,
      "involved_characters": ["Character1", "Character2"]
    }}
  ]
}}

If no events found, return {{"events": []}}. Return ONLY the JSON, no other text."""
            
            params = self._get_generation_params(max_tokens=self.max_tokens * 2)  # Allow more tokens for batch
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total * 2  # Longer timeout for batch
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            return self._parse_json_response(content)
            
        except Exception as e:
            logger.error(f"Failed to extract plot events (batch) with extraction model: {e}")
            raise
    
    def _parse_json_response(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse JSON response from model, handling common formatting issues
        
        Args:
            content: Raw response content
            
        Returns:
            List of event dictionaries
        """
        try:
            # Clean response (remove markdown code blocks if present)
            response_clean = content.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Parse JSON
            data = json.loads(response_clean)
            
            # Extract events array
            events_list = data.get('events', [])
            
            if not isinstance(events_list, list):
                logger.warning(f"Expected events array, got {type(events_list)}")
                return []
            
            return events_list
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nContent: {content[:500]}")
            raise ValueError(f"Invalid JSON response from extraction model: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            raise
    
    def _parse_json_dict(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON response as dictionary (for non-array responses)
        
        Args:
            content: Raw response content
            
        Returns:
            Dictionary from JSON response
        """
        try:
            # Clean response (remove markdown code blocks if present)
            response_clean = content.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Parse JSON
            data = json.loads(response_clean)
            
            if not isinstance(data, dict):
                logger.warning(f"Expected dictionary, got {type(data)}")
                return {}
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nContent: {content[:500]}")
            raise ValueError(f"Invalid JSON response from extraction model: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            raise
    
    async def extract_character_moments(
        self,
        scene_content: str,
        character_names: List[str],
        system_prompt: str = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
    ) -> List[Dict[str, Any]]:
        """
        Extract character moments from a single scene
        
        Args:
            scene_content: Scene text to analyze
            character_names: List of character names to look for
            system_prompt: System prompt for the model
            
        Returns:
            List of moment dictionaries
        """
        try:
            from litellm import acompletion
            
            prompt = f"""Analyze the following scene and extract significant character moments for these characters: {', '.join(character_names)}

Scene:
{scene_content}

For each significant character moment, identify:
1. Character name
2. Moment type: "action" (physical action), "dialogue" (important speech), "development" (character growth/change), or "relationship" (interaction with others)
3. Brief description of the moment (1-2 sentences)
4. Confidence (0-100): How significant is this moment for the character?

Return ONLY valid JSON in this exact format:
{{
  "moments": [
    {{
      "character_name": "Character Name",
      "moment_type": "action",
      "content": "Description of the moment",
      "confidence": 85
    }}
  ]
}}

If no moments found, return {{"moments": []}}. Return ONLY the JSON, no other text."""
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total
            )
            
            content = response.choices[0].message.content.strip()
            data = self._parse_json_dict(content)
            return data.get('moments', [])
            
        except Exception as e:
            logger.error(f"Failed to extract character moments with extraction model: {e}")
            raise
    
    async def extract_character_moments_batch(
        self,
        batch_content: str,
        character_names: List[str],
        system_prompt: str = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
    ) -> List[Dict[str, Any]]:
        """
        Extract character moments from multiple scenes in batch
        
        Args:
            batch_content: Multiple scenes text (with scene markers)
            character_names: List of character names to look for
            system_prompt: System prompt for the model
            
        Returns:
            List of moment dictionaries
        """
        try:
            from litellm import acompletion
            
            prompt = f"""Analyze the following scenes and extract significant character moments for these characters: {', '.join(character_names)}

{batch_content}

For each significant character moment, identify:
1. Character name
2. Moment type: "action" (physical action), "dialogue" (important speech), "development" (character growth/change), or "relationship" (interaction with others)
3. Brief description of the moment (1-2 sentences)
4. Confidence (0-100): How significant is this moment for the character?

Return ONLY valid JSON in this exact format:
{{
  "moments": [
    {{
      "character_name": "Character Name",
      "moment_type": "action",
      "content": "Description of the moment",
      "confidence": 85
    }}
  ]
}}

If no moments found, return {{"moments": []}}. Return ONLY the JSON, no other text."""
            
            params = self._get_generation_params(max_tokens=self.max_tokens * 2)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total * 2
            )
            
            content = response.choices[0].message.content.strip()
            data = self._parse_json_dict(content)
            return data.get('moments', [])
            
        except Exception as e:
            logger.error(f"Failed to extract character moments (batch) with extraction model: {e}")
            raise
    
    async def extract_npcs(
        self,
        scene_content: str,
        scene_sequence: int,
        explicit_character_names: List[str],
        system_prompt: str = "You are a precise story analysis assistant. Extract NPCs and named entities from scenes. Return only valid JSON."
    ) -> Dict[str, Any]:
        """
        Extract NPCs from a scene
        
        Args:
            scene_content: Scene text to analyze
            scene_sequence: Scene sequence number
            explicit_character_names: List of characters already tracked (exclude these)
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with 'npcs' array
        """
        try:
            from litellm import acompletion
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Extract ONLY NAMED PEOPLE from this scene.

Scene (Sequence #{scene_sequence}):
{scene_content}

Already tracked (SKIP these): {explicit_names_str}

EXAMPLE:
Scene: "The marble countertop gleamed. Dr. Voss checked the chart. A stranger passed by. The coffee grew cold."
Already tracked: None
Output: {{"npcs": [{{"name": "Dr. Voss", "mention_count": 1, "has_dialogue": false, "has_actions": true, "has_relationships": false}}]}}
NOT extracted: marble (material), stranger (no name), coffee (object)

RULES: Only named people who can speak/think/decide. No objects, materials, locations, weather, or unnamed roles.

Return JSON:
{{
  "npcs": [
    {{
      "name": "Person's name",
      "mention_count": 1,
      "has_dialogue": true,
      "has_actions": true,
      "has_relationships": true
    }}
  ]
}}

If no NAMED PEOPLE found, return {{"npcs": []}}. Return ONLY JSON."""
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract NPCs with extraction model: {e}")
            raise
    
    async def extract_npcs_batch(
        self,
        batch_content: str,
        explicit_character_names: List[str],
        system_prompt: str = "You are a precise story analysis assistant. Extract NPCs and named entities from scenes. Return only valid JSON."
    ) -> Dict[str, Any]:
        """
        Extract NPCs from multiple scenes in batch
        
        Args:
            batch_content: Multiple scenes text (with scene markers)
            explicit_character_names: List of characters already tracked (exclude these)
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with 'npcs' array
        """
        try:
            from litellm import acompletion
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Extract ONLY NAMED PEOPLE from these scenes.

{batch_content}

Already tracked (SKIP these): {explicit_names_str}

EXAMPLE:
Scene: "Mrs. Okafor set down her teacup. 'The garden needs work,' she said. The Carrara tiles gleamed. The crowd dispersed outside."
Already tracked: None
Output: {{"npcs": [{{"name": "Mrs. Okafor", "mention_count": 1, "has_dialogue": true, "has_actions": true, "has_relationships": false}}]}}
NOT extracted: Carrara (material), crowd (unnamed group), garden (location), teacup (object)

RULES: Only named people who can speak/think/decide. No objects, materials, locations, weather, or unnamed roles.

Return JSON:
{{
  "npcs": [
    {{
      "name": "Person's name",
      "mention_count": 3,
      "has_dialogue": true,
      "has_actions": true,
      "has_relationships": true
    }}
  ]
}}

If no NAMED PEOPLE found, return {{"npcs": []}}. Return ONLY JSON."""
            
            params = self._get_generation_params(max_tokens=self.max_tokens * 2)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total * 2
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract NPCs (batch) with extraction model: {e}")
            raise
    
    async def extract_entity_states(
        self,
        scene_content: str,
        scene_sequence: int,
        character_names: List[str],
        chapter_location: str = None,
        system_prompt: str = None,
        interaction_types: List[str] = None
    ) -> Dict[str, Any]:
        """
        Extract entity state changes from a scene

        Args:
            scene_content: Scene text to analyze
            scene_sequence: Scene sequence number
            character_names: List of known character names
            chapter_location: Chapter-level location for hierarchical context
            system_prompt: System prompt for the model (optional, uses prompts.yml if not provided)
            interaction_types: List of interaction types to detect (e.g., ["first kiss", "first argument"])

        Returns:
            Dictionary with 'characters', 'locations', 'objects', and optionally 'interactions' arrays
        """
        try:
            from litellm import acompletion

            # Get prompts from centralized prompts.yml (use same template as main LLM fallback)
            if system_prompt is None:
                system_prompt = prompt_manager.get_prompt("entity_state_extraction.single", "system")
                if not system_prompt:
                    system_prompt = "You are a precise story state tracker. Extract entity states as JSON. Focus on FACTS, not interpretation."

            prompt = prompt_manager.get_prompt(
                "entity_state_extraction.single", "user",
                scene_sequence=scene_sequence,
                scene_content=scene_content,
                character_names=', '.join(character_names),
                chapter_location=chapter_location or "Unknown"
            )

            # Add interaction extraction if interaction types are configured
            if interaction_types:
                interaction_section = f"""

INTERACTION TYPES TO DETECT:
The story is tracking these specific interaction types: {json.dumps(interaction_types)}

If ANY of these interactions occur for the FIRST TIME between two characters in this scene,
include them in the "interactions" array. Only report interactions that are EXPLICITLY shown
happening in this scene, not referenced or remembered.

For interactions, return:
{{
  "interaction_type": "the exact type from the list above",
  "character_a": "first character name",
  "character_b": "second character name",
  "description": "brief factual description of what happened"
}}

Include "interactions": [] in your JSON response (empty array if no tracked interactions detected)."""
                prompt += interaction_section

            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total
            )

            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)

        except Exception as e:
            logger.error(f"Failed to extract entity states with extraction model: {e}")
            raise
    
    async def extract_character_details(
        self,
        character_name: str,
        character_scenes_text: str,
        system_prompt: str = "You are a detailed character profiling assistant. Analyze all appearances of a character in a story and extract comprehensive details about them. Be thorough but accurate - only include information that is clearly supported by the text. Return ONLY valid JSON, no other text."
    ) -> Dict[str, Any]:
        """
        Extract detailed character information from scenes
        
        Args:
            character_name: Name of character to analyze
            character_scenes_text: All scenes where character appears (formatted)
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with character details
        """
        try:
            from litellm import acompletion
            
            prompt = f"""Analyze all appearances of "{character_name}" in these scenes and extract character details.

Scenes featuring {character_name}:
{character_scenes_text}

EXAMPLE:
Character: "Elena Voss"
Scenes: Elena adjusts her wire-rimmed glasses as she studies the map. She snaps at Kai for being late but later apologizes. She mentions growing up near the coast. Her hands shake when she sees the photograph.
Output:
{{
  "name": "Elena Voss",
  "description": "A meticulous and sharp-tongued researcher with a troubled past connected to the coast. Quick to anger but capable of remorse.",
  "personality_traits": ["meticulous", "sharp-tongued", "remorseful", "anxious", "determined"],
  "background": "Grew up near the coast. Has an emotional connection to events shown in a photograph.",
  "goals": "Studying the map suggests she is searching for something or investigating a location.",
  "fears": "The photograph triggers visible fear — connected to a past trauma.",
  "appearance": "Wears wire-rimmed glasses. Hands shake under stress.",
  "suggested_role": "protagonist"
}}

Now extract details for "{character_name}". Be concise — traits as single words, descriptions as 1-2 sentences. Only include what the text supports.

Return ONLY JSON:
{{
  "name": "Character Name",
  "description": "2-3 sentence summary",
  "personality_traits": ["trait1", "trait2", "trait3"],
  "background": "Background text",
  "goals": "Goals text",
  "fears": "Fears text",
  "appearance": "Physical description",
  "suggested_role": "role_name"
}}"""
            
            # Use configured max_tokens from initialization
            params = self._get_generation_params(max_tokens=self.max_tokens)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total * 2
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract character details with extraction model: {e}")
            raise
    
    async def generate_summary(
        self,
        story_content: str,
        story_context: str = "",
        system_prompt: str = "You are an expert story analyst. Create a comprehensive summary that captures the essential plot points and character development while maintaining the tone and style of the original story.",
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate a summary of story content using the extraction model
        
        Args:
            story_content: The story text to summarize
            story_context: Additional context about the story (title, genre, etc.)
            system_prompt: System prompt for the model
            max_tokens: Maximum tokens for response (defaults to 2000 for summaries)
            
        Returns:
            Generated summary text
        """
        try:
            from litellm import acompletion
            
            # Use higher max_tokens for summaries (default 2000)
            summary_max_tokens = max_tokens if max_tokens is not None else 2000
            
            # Build user prompt
            context_section = f"Story Context:\n{story_context}\n\n" if story_context else ""
            
            prompt = f"""{context_section}Story Content:
{story_content}

Summarize this story, focusing on plot points, character development, and key conflicts.

EXAMPLE:
Story excerpt: Three scenes where Kai arrives at the cabin, argues with Suri about the plan, and discovers the locked basement door.
Good summary: "Kai arrived at the mountain cabin expecting a quiet retreat, but tension with Suri erupted immediately over their conflicting plans. Their argument revealed deeper trust issues. The discovery of a locked basement door added a new mystery — someone had been here before them."

RULES:
- Cover key plot points and character developments
- Keep character relationships and conflicts central
- Be concise but preserve important details
- Match the story's tone

Summary:"""
            
            params = self._get_generation_params(max_tokens=summary_max_tokens)
            logger.info(f"Generating summary with extraction model: max_tokens={summary_max_tokens}")
            
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout_total * 3  # Longer timeout for summaries
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Summary generated with extraction model: {len(content)} characters")
            return content
            
        except Exception as e:
            logger.error(f"Failed to generate summary with extraction model: {e}")
            raise
    
    def _calculate_batch_timeout(self, num_scenes: int) -> float:
        """
        Calculate timeout for batch extraction based on number of scenes.
        Uses user's timeout_total as base, scales with batch size.

        Args:
            num_scenes: Number of scenes in batch

        Returns:
            Timeout in seconds
        """
        # Use user's timeout as base, scale with batch size: +10 seconds per scene
        # Max: 2x user's timeout (to prevent excessively long waits)
        base_timeout = self.timeout_total
        timeout = base_timeout + (num_scenes * 10)
        return min(timeout, base_timeout * 2)
    
    def _calculate_batch_max_tokens(self, num_scenes: int) -> int:
        """
        Calculate max_tokens for batch extraction based on number of scenes.
        
        Args:
            num_scenes: Number of scenes in batch
            
        Returns:
            Max tokens for response
        """
        # Base: 3000-4000 tokens (3x individual)
        # Scale with batch size
        base_tokens = 3500
        scaled_tokens = int(base_tokens * (1 + num_scenes / 5))
        # Max cap: 8000 tokens
        return min(scaled_tokens, 8000)
    
    def _parse_combined_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse combined JSON response with robust error handling.
        Handles malformed JSON, partial responses, and missing sections.
        
        Args:
            content: Raw response content
            
        Returns:
            Dictionary with 'character_moments', 'npcs', 'plot_events', 'entity_states' keys
            Missing sections will be empty arrays/objects
        """
        result = {
            'character_moments': [],
            'npcs': [],
            'plot_events': [],
            'entity_states': {
                'characters': [],
                'locations': [],
                'objects': []
            }
        }
        
        try:
            # Clean response (remove markdown code blocks if present)
            response_clean = content.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            elif response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Try to parse full JSON
            try:
                data = json.loads(response_clean)
                
                # Extract each section independently
                if 'character_moments' in data and isinstance(data['character_moments'], list):
                    result['character_moments'] = data['character_moments']
                elif 'moments' in data and isinstance(data['moments'], list):
                    # Handle alternative key name
                    result['character_moments'] = data['moments']
                
                if 'npcs' in data:
                    if isinstance(data['npcs'], list):
                        result['npcs'] = data['npcs']
                    elif isinstance(data['npcs'], dict) and 'npcs' in data['npcs']:
                        # Handle nested structure
                        result['npcs'] = data['npcs']['npcs'] if isinstance(data['npcs']['npcs'], list) else []
                
                if 'plot_events' in data and isinstance(data['plot_events'], list):
                    result['plot_events'] = data['plot_events']
                elif 'events' in data and isinstance(data['events'], list):
                    # Handle alternative key name
                    result['plot_events'] = data['events']
                
                # Parse entity_states
                if 'entity_states' in data and isinstance(data['entity_states'], dict):
                    entity_states = data['entity_states']
                    if 'characters' in entity_states and isinstance(entity_states['characters'], list):
                        result['entity_states']['characters'] = entity_states['characters']
                    if 'locations' in entity_states and isinstance(entity_states['locations'], list):
                        result['entity_states']['locations'] = entity_states['locations']
                    if 'objects' in entity_states and isinstance(entity_states['objects'], list):
                        result['entity_states']['objects'] = entity_states['objects']
                
                logger.info(f"Successfully parsed combined extraction: {len(result['character_moments'])} moments, "
                          f"{len(result['npcs'])} NPCs, {len(result['plot_events'])} events, "
                          f"{len(result['entity_states']['characters'])} character states, "
                          f"{len(result['entity_states']['locations'])} location states, "
                          f"{len(result['entity_states']['objects'])} object states")
                return result
                
            except json.JSONDecodeError:
                # Try to extract partial JSON using regex
                import re
                
                # Try to find JSON objects for each section
                moments_match = re.search(r'"character_moments"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if not moments_match:
                    moments_match = re.search(r'"moments"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if moments_match:
                    try:
                        moments_json = json.loads(f'[{moments_match.group(1)}]')
                        result['character_moments'] = moments_json if isinstance(moments_json, list) else []
                    except:
                        pass
                
                npcs_match = re.search(r'"npcs"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if npcs_match:
                    try:
                        npcs_json = json.loads(f'[{npcs_match.group(1)}]')
                        result['npcs'] = npcs_json if isinstance(npcs_json, list) else []
                    except:
                        pass
                
                events_match = re.search(r'"plot_events"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if not events_match:
                    events_match = re.search(r'"events"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if events_match:
                    try:
                        events_json = json.loads(f'[{events_match.group(1)}]')
                        result['plot_events'] = events_json if isinstance(events_json, list) else []
                    except:
                        pass
                
                # Try to parse entity_states with regex (less reliable but attempt it)
                entity_states_match = re.search(r'"entity_states"\s*:\s*\{(.*?)\}', response_clean, re.DOTALL)
                if entity_states_match:
                    try:
                        entity_states_json = json.loads(f'{{{entity_states_match.group(1)}}}')
                        if isinstance(entity_states_json, dict):
                            if 'characters' in entity_states_json and isinstance(entity_states_json['characters'], list):
                                result['entity_states']['characters'] = entity_states_json['characters']
                            if 'locations' in entity_states_json and isinstance(entity_states_json['locations'], list):
                                result['entity_states']['locations'] = entity_states_json['locations']
                            if 'objects' in entity_states_json and isinstance(entity_states_json['objects'], list):
                                result['entity_states']['objects'] = entity_states_json['objects']
                    except:
                        pass
                
                if any(result.values()) or any(result['entity_states'].values()):
                    logger.warning(f"Partially parsed combined extraction using regex: {len(result['character_moments'])} moments, "
                                 f"{len(result['npcs'])} NPCs, {len(result['plot_events'])} events, "
                                 f"{len(result['entity_states']['characters'])} character states")
                    return result
                else:
                    raise
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse combined JSON response: {e}\nContent preview: {content[:500]}")
            # Return empty result instead of raising - caller can fallback
            return result
        except Exception as e:
            logger.error(f"Unexpected error parsing combined response: {e}\nContent preview: {content[:500]}")
            return result
    
    async def extract_all_batch(
        self,
        batch_content: str,
        character_names: List[str],
        explicit_character_names: List[str],
        thread_context: str = "",
        num_scenes: int = 1
    ) -> Dict[str, Any]:
        """
        Extract character moments, NPCs, plot events, and entity states from multiple scenes in a single LLM call.
        This combines four separate extractions into one for efficiency.
        
        Args:
            batch_content: Multiple scenes text (with scene markers)
            character_names: List of explicit character names (for character moments and entity states)
            explicit_character_names: List of characters already tracked (exclude from NPCs)
            thread_context: Context about existing plot threads
            num_scenes: Number of scenes in batch (for timeout/token calculation)
            
        Returns:
            Dictionary with 'character_moments', 'npcs', 'plot_events', 'entity_states' keys
        """
        try:
            from litellm import acompletion
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            character_names_str = ", ".join(character_names) if character_names else "None"
            
            # Build thread context section
            thread_section = f"\n\nActive plot threads to consider:{thread_context}" if thread_context else ""
            
            # Calculate dynamic limits based on batch size
            max_npcs_total = 10
            max_events_total = 8
            
            # Get prompts from centralized prompts.yml
            system_prompt = prompt_manager.get_prompt("entity_state_extraction.batch", "system")
            user_prompt = prompt_manager.get_prompt(
                "entity_state_extraction.batch", "user",
                character_names=character_names_str,
                explicit_names=explicit_names_str,
                thread_section=thread_section,
                batch_content=batch_content,
                max_npcs_total=max_npcs_total,
                max_events_total=max_events_total
            )
            
            # Calculate dynamic timeout and max_tokens
            timeout_seconds = self._calculate_batch_timeout(num_scenes)
            max_tokens = self._calculate_batch_max_tokens(num_scenes)
            
            params = self._get_generation_params(max_tokens=max_tokens)
            logger.info(f"Starting combined extraction: {num_scenes} scenes, timeout={timeout_seconds}s, max_tokens={max_tokens}")
            
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                timeout=timeout_seconds
            )
            
            content = response.choices[0].message.content.strip()
            logger.debug(f"Combined extraction response length: {len(content)} characters")
            
            # Parse with robust error handling
            return self._parse_combined_json_response(content)
            
        except Exception as e:
            logger.error(f"Failed to extract all (combined batch) with extraction model: {e}")
            raise

