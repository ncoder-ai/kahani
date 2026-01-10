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
        
        # Text completion settings
        self.completion_mode = self.llm_config.get('completion_mode', 'chat')
        self.text_completion_template = self.llm_config.get('text_completion_template')
        self.text_completion_preset = self.llm_config.get('text_completion_preset', 'llama3')
        
        # Reasoning/Thinking settings
        self.reasoning_effort = self.llm_config.get('reasoning_effort')  # None = auto, "disabled", "low", "medium", "high"
        self.show_thinking_content = self.llm_config.get('show_thinking_content', True)
        
        # Advanced sampler settings (from sampler_settings in user_settings)
        self.sampler_settings = user_settings.get('sampler_settings', {})
        
        logger.info(f"LLMClient initialized: completion_mode={self.completion_mode}, api_type={self.api_type}, model={self.model_name}, reasoning_effort={self.reasoning_effort}")
        
        # Configure LiteLLM model string based on provider
        self.model_string = self._build_model_string()
        
        # Set LiteLLM configuration
        self._configure_litellm()
    
    def _build_model_string(self) -> str:
        """Build LiteLLM model string based on provider type"""
        if self.api_type == "openai":
            return self.model_name
        elif self.api_type == "openai-compatible" or self.api_type == "openai_compatible":
            # Check if this is OpenRouter - needs special prefix for reasoning support
            if "openrouter" in self.api_url.lower():
                return f"openrouter/{self.model_name}"
            # For other OpenAI-compatible APIs, use openai/ prefix
            # As per LiteLLM docs: model="openai/mistral"
            return f"openai/{self.model_name}"
        elif self.api_type == "tabbyapi":
            # TabbyAPI is OpenAI-compatible, use openai/ prefix
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
        # For openai-compatible and tabbyapi, we pass api_base per-request in get_generation_params()
        # The backend will add the appropriate /v1 path for each provider
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
        
        # Suppress cost calculation warnings for custom models
        litellm.suppress_debug_info = True
        
        # Disable cost calculation for unknown models to prevent warnings
        litellm.drop_params = True
        
        # Suppress cost calculation warnings for custom models
        import os
        os.environ["LITELLM_LOG"] = "ERROR"  # Only show errors, not warnings
        os.environ["LITELLM_LOG_LEVEL"] = "ERROR"
        
        # Additional debug suppression
        os.environ["LITELLM_SUPPRESS_DEBUG_INFO"] = "true"
        os.environ["LITELLM_DROP_PARAMS"] = "true"
        
        # Disable cost calculation completely
        try:
            litellm.cost_calculator = None
        except:
            pass
        
        # Monkey patch the cost calculation to prevent warnings
        try:
            def dummy_cost_calculator(*args, **kwargs):
                return None
            litellm.response_cost_calculator = dummy_cost_calculator
        except:
            pass
        
        # Disable all debug output
        try:
            litellm.set_verbose = False
            litellm.suppress_debug_info = True
            litellm.drop_params = True
        except:
            pass
        
        logger.info(f"Configured LiteLLM for {self.api_type} with model {self.model_string}")
    
    def _add_enabled_samplers(self, extra_body: Dict[str, Any]) -> Dict[str, Any]:
        """Add enabled samplers from sampler_settings to extra_body.
        
        Only samplers with enabled=True are added to the request.
        This allows users to selectively enable/disable individual samplers.
        """
        if not self.sampler_settings:
            return extra_body
        
        # Map of sampler names to their API parameter names
        # Most are 1:1 but some may need special handling
        sampler_map = {
            # Basic Sampling
            "temperature_last": "temperature_last",
            "smoothing_factor": "smoothing_factor",
            "min_p": "min_p",
            "top_a": "top_a",
            
            # Token Control
            "min_tokens": "min_tokens",
            "token_healing": "token_healing",
            "add_bos_token": "add_bos_token",
            "ban_eos_token": "ban_eos_token",
            
            # Penalties
            "frequency_penalty": "frequency_penalty",
            "presence_penalty": "presence_penalty",
            "penalty_range": "penalty_range",
            "repetition_decay": "repetition_decay",
            
            # Advanced Sampling
            "tfs": "tfs",
            "typical": "typical",
            "skew": "skew",
            
            # XTC (Exclude Top Choices)
            "xtc_probability": "xtc_probability",
            "xtc_threshold": "xtc_threshold",
            
            # DRY (Don't Repeat Yourself)
            "dry_multiplier": "dry_multiplier",
            "dry_base": "dry_base",
            "dry_allowed_length": "dry_allowed_length",
            "dry_range": "dry_range",
            "dry_sequence_breakers": "dry_sequence_breakers",
            
            # Mirostat
            "mirostat_mode": "mirostat_mode",
            "mirostat_tau": "mirostat_tau",
            "mirostat_eta": "mirostat_eta",
            
            # Dynamic Temperature
            "max_temp": "max_temp",
            "min_temp": "min_temp",
            "temp_exponent": "temp_exponent",
            
            # Constraints
            "banned_strings": "banned_strings",
            "banned_tokens": "banned_tokens",
            "allowed_tokens": "allowed_tokens",
            "stop": "stop",
            
            # Other
            "cfg_scale": "cfg_scale",
            "negative_prompt": "negative_prompt",
            "speculative_ngram": "speculative_ngram",
        }
        
        enabled_count = 0
        for sampler_key, api_param in sampler_map.items():
            sampler_config = self.sampler_settings.get(sampler_key, {})
            
            # Check if this sampler is enabled and has a value
            if isinstance(sampler_config, dict) and sampler_config.get('enabled', False):
                value = sampler_config.get('value')
                
                # Skip empty/null values
                if value is None:
                    continue
                
                # Skip empty strings for string-type samplers
                if isinstance(value, str) and value.strip() == '':
                    continue
                
                # Skip empty lists for array-type samplers
                if isinstance(value, list) and len(value) == 0:
                    continue
                
                extra_body[api_param] = value
                enabled_count += 1
        
        if enabled_count > 0:
            logger.info(f"Added {enabled_count} enabled samplers to extra_body")
            logger.debug(f"Enabled samplers: {[k for k, v in self.sampler_settings.items() if isinstance(v, dict) and v.get('enabled')]}")
        
        return extra_body
    
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
            from ...config import settings
            service_defaults = settings.service_defaults.get('llm_client', {})
            params["max_tokens"] = service_defaults.get('default_max_tokens', 2048)
        
        if temperature is not None:
            params["temperature"] = temperature
        elif self.temperature is not None:
            params["temperature"] = self.temperature
        else:
            from ...config import settings
            service_defaults = settings.service_defaults.get('llm_client', {})
            params["temperature"] = service_defaults.get('default_temperature', 0.7)
        
        # Only add top_p if explicitly set (don't default to 1.0)
        if self.top_p is not None:
            params["top_p"] = self.top_p
        
        # Add API base and key for openai-compatible and tabbyapi providers
        # Pass api_base per-request so LiteLLM uses it directly without modification
        if self.api_type in ["openai-compatible", "tabbyapi"]:
            # Add /v1 to the base URL for these providers
            api_base_url = f"{self.api_url}/v1" if not self.api_url.endswith("/v1") else self.api_url
            params["api_base"] = api_base_url
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
        elif self.api_type in ["openai-compatible", "tabbyapi", "lm_studio"]:
            # For OpenAI-compatible APIs, use extra_body for non-standard params
            extra_body = {}
            if self.top_k is not None:
                extra_body["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                extra_body["repetition_penalty"] = self.repetition_penalty
            
            # Add enabled advanced samplers from sampler_settings
            extra_body = self._add_enabled_samplers(extra_body)
            
            if extra_body:
                params["extra_body"] = extra_body
        
        # Add reasoning/thinking parameters
        is_openrouter = "openrouter" in self.api_url.lower()
        
        if self.reasoning_effort and self.reasoning_effort != "disabled":
            if is_openrouter:
                # OpenRouter: use top-level reasoning_effort with allowed_openai_params
                # This is required for LiteLLM to properly handle reasoning_content in streaming
                params["reasoning_effort"] = self.reasoning_effort
                params["allowed_openai_params"] = ["reasoning_effort"]
                logger.info(f"Reasoning effort set to: {self.reasoning_effort} (OpenRouter)")
            else:
                # Other providers: use extra_body approach
                if "extra_body" not in params:
                    params["extra_body"] = {}
                params["extra_body"]["reasoning"] = {"effort": self.reasoning_effort}
                logger.info(f"Reasoning effort set to: {self.reasoning_effort} via extra_body")
        elif self.reasoning_effort == "disabled":
            # Disable reasoning entirely
            if "extra_body" not in params:
                params["extra_body"] = {}
            params["extra_body"]["include_reasoning"] = False
            logger.info("Reasoning disabled via include_reasoning=False")
        
        logger.info(f"Final generation params: {params}")
        return params
    
    def get_streaming_params(self, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """Get generation parameters for streaming API calls"""
        params = self.get_generation_params(max_tokens, temperature)
        params["stream"] = True
        return params
    
    def get_text_completion_params(self, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """
        Get generation parameters for text completion API calls.
        
        Similar to get_generation_params() but for /v1/completions endpoint.
        Uses 'prompt' field instead of 'messages'.
        """
        params = {
            "model": self.model_string,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        
        # Add optional parameters if set
        if self.top_p is not None:
            params["top_p"] = self.top_p
        
        # Add API base URL for OpenAI-compatible providers
        if self.api_type in ["openai-compatible", "openai_compatible", "tabbyapi", "lm_studio"]:
            # Ensure URL ends with /v1
            api_url = self.api_url.rstrip('/')
            if not api_url.endswith('/v1'):
                api_url += '/v1'
            params["api_base"] = api_url
            
            if self.api_key:
                params["api_key"] = self.api_key
        
        # Add provider-specific parameters
        if self.api_type == "koboldcpp":
            if self.top_k is not None:
                params["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                params["repetition_penalty"] = self.repetition_penalty
        elif self.api_type in ["openai-compatible", "tabbyapi", "lm_studio"]:
            # For OpenAI-compatible APIs, use extra_body for non-standard params
            extra_body = {}
            if self.top_k is not None:
                extra_body["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                extra_body["repetition_penalty"] = self.repetition_penalty
            
            # Add enabled advanced samplers from sampler_settings
            extra_body = self._add_enabled_samplers(extra_body)
            
            if extra_body:
                params["extra_body"] = extra_body
        
        logger.info(f"Final text completion params: model={params.get('model')}, api_base={params.get('api_base')}, has_prompt={('prompt' in params)}")
        logger.debug(f"Full text completion params: {params}")
        return params
    
    def get_text_completion_streaming_params(self, max_tokens: Optional[int] = None, temperature: Optional[float] = None) -> Dict[str, Any]:
        """Get generation parameters for streaming text completion API calls"""
        params = self.get_text_completion_params(max_tokens, temperature)
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
                if self.api_type in ["openai_compatible", "tabbyapi"]:
                    return False, f"API endpoint not found. The system automatically adds '/v1' to your URL. Please check that your base URL is correct: {self.api_url}"
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
