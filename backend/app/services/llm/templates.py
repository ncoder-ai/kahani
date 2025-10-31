"""
Text Completion Template Manager

Manages pre-built and custom templates for text completion API calls.
Provides templates for popular instruction-tuned models like Llama, Mistral, Qwen, GLM, etc.
"""

import json
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class TextCompletionTemplateManager:
    """
    Manages text completion templates for various instruction-tuned models.
    
    Templates define how to format system prompts and user instructions into
    a single text prompt suitable for text completion APIs.
    """
    
    # Pre-built templates for popular models
    PRESETS = {
        "llama3": {
            "name": "Llama 3 Instruct",
            "description": "Template for Llama 3 / 3.1 / 3.2 Instruct models",
            "compatible_models": ["Llama-3", "Llama-3.1", "Llama-3.2", "Meta-Llama-3"],
            "bos_token": "<|begin_of_text|>",
            "eos_token": "<|eot_id|>",
            "system_prefix": "<|start_header_id|>system<|end_header_id|>\n\n",
            "system_suffix": "<|eot_id|>",
            "instruction_prefix": "<|start_header_id|>user<|end_header_id|>\n\n",
            "instruction_suffix": "<|eot_id|>",
            "response_prefix": "<|start_header_id|>assistant<|end_header_id|>\n\n"
        },
        "mistral": {
            "name": "Mistral Instruct",
            "description": "Template for Mistral Instruct models (v0.1, v0.2, v0.3)",
            "compatible_models": ["Mistral-7B-Instruct", "Mixtral-8x7B-Instruct", "Mistral-Small", "Mistral-Medium"],
            "bos_token": "<s>",
            "eos_token": "</s>",
            "system_prefix": "",  # Mistral doesn't use explicit system role
            "system_suffix": "",
            "instruction_prefix": "[INST] ",
            "instruction_suffix": " [/INST]",
            "response_prefix": ""
        },
        "qwen": {
            "name": "Qwen",
            "description": "Template for Qwen / Qwen2 / QwQ models",
            "compatible_models": ["Qwen", "Qwen2", "Qwen2.5", "QwQ"],
            "bos_token": "<|im_start|>",
            "eos_token": "<|im_end|>",
            "system_prefix": "<|im_start|>system\n",
            "system_suffix": "<|im_end|>\n",
            "instruction_prefix": "<|im_start|>user\n",
            "instruction_suffix": "<|im_end|>\n",
            "response_prefix": "<|im_start|>assistant\n"
        },
        "glm": {
            "name": "GLM",
            "description": "Template for ChatGLM / GLM-4 models",
            "compatible_models": ["ChatGLM", "ChatGLM2", "ChatGLM3", "GLM-4"],
            "bos_token": "[gMASK]<sop>",
            "eos_token": "<eop>",
            "system_prefix": "<|system|>\n",
            "system_suffix": "",
            "instruction_prefix": "<|user|>\n",
            "instruction_suffix": "",
            "response_prefix": "<|assistant|>\n"
        },
        "generic": {
            "name": "Generic",
            "description": "Simple generic template for basic instruction-following models",
            "compatible_models": ["Generic instruction-tuned models"],
            "bos_token": "",
            "eos_token": "",
            "system_prefix": "### System:\n",
            "system_suffix": "\n\n",
            "instruction_prefix": "### User:\n",
            "instruction_suffix": "\n\n",
            "response_prefix": "### Assistant:\n"
        }
    }
    
    @classmethod
    def get_available_presets(cls) -> List[Dict[str, Any]]:
        """
        Get list of available template presets with metadata.
        
        Returns:
            List of preset metadata dictionaries
        """
        presets = []
        for key, template in cls.PRESETS.items():
            presets.append({
                "key": key,
                "name": template["name"],
                "description": template["description"],
                "compatible_models": template["compatible_models"]
            })
        return presets
    
    @classmethod
    def get_preset_template(cls, preset_name: str) -> Optional[Dict[str, str]]:
        """
        Get a specific preset template by name.
        
        Args:
            preset_name: Name of the preset (e.g., "llama3", "mistral")
            
        Returns:
            Template dictionary or None if not found
        """
        return cls.PRESETS.get(preset_name)
    
    @classmethod
    def validate_template(cls, template: Dict[str, str]) -> Tuple[bool, str]:
        """
        Validate that a template has all required fields.
        
        Args:
            template: Template dictionary to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = [
            "bos_token",
            "eos_token",
            "system_prefix",
            "system_suffix",
            "instruction_prefix",
            "instruction_suffix",
            "response_prefix"
        ]
        
        if not isinstance(template, dict):
            return False, "Template must be a dictionary"
        
        missing_fields = [field for field in required_fields if field not in template]
        if missing_fields:
            return False, f"Missing required fields: {', '.join(missing_fields)}"
        
        # Check that all values are strings
        for field, value in template.items():
            if field in required_fields and not isinstance(value, str):
                return False, f"Field '{field}' must be a string"
        
        return True, ""
    
    @classmethod
    def render_template(
        cls,
        template: Dict[str, str],
        system_prompt: str = "",
        user_prompt: str = ""
    ) -> str:
        """
        Render a template with the provided system and user prompts.
        
        Args:
            template: Template dictionary with formatting tokens
            system_prompt: System prompt content
            user_prompt: User instruction content
            
        Returns:
            Fully assembled prompt string ready for text completion
        """
        # Validate template first
        is_valid, error = cls.validate_template(template)
        if not is_valid:
            raise ValueError(f"Invalid template: {error}")
        
        # Build the prompt
        parts = []
        
        # BOS token
        if template["bos_token"]:
            parts.append(template["bos_token"])
        
        # System prompt (if provided)
        if system_prompt and system_prompt.strip():
            parts.append(template["system_prefix"])
            parts.append(system_prompt.strip())
            parts.append(template["system_suffix"])
        
        # User instruction
        parts.append(template["instruction_prefix"])
        parts.append(user_prompt.strip())
        parts.append(template["instruction_suffix"])
        
        # Response prefix (where model starts generating)
        parts.append(template["response_prefix"])
        
        # Note: EOS token is NOT added here - the model will generate it
        
        # Join all parts
        prompt = "".join(parts)
        
        logger.debug(f"Rendered template prompt (length: {len(prompt)})")
        return prompt
    
    @classmethod
    def parse_template_json(cls, template_json: str) -> Optional[Dict[str, str]]:
        """
        Parse a JSON string into a template dictionary.
        
        Args:
            template_json: JSON string representation of template
            
        Returns:
            Template dictionary or None if parsing fails
        """
        if not template_json or not template_json.strip():
            return None
        
        try:
            template = json.loads(template_json)
            is_valid, error = cls.validate_template(template)
            if not is_valid:
                logger.error(f"Invalid template JSON: {error}")
                return None
            return template
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse template JSON: {e}")
            return None
    
    @classmethod
    def template_to_json(cls, template: Dict[str, str]) -> str:
        """
        Convert a template dictionary to JSON string.
        
        Args:
            template: Template dictionary
            
        Returns:
            JSON string representation
        """
        return json.dumps(template, indent=2)
    
    @classmethod
    def get_template_for_user(
        cls,
        template_json: Optional[str],
        preset_name: str = "llama3"
    ) -> Dict[str, str]:
        """
        Get the appropriate template for a user based on their settings.
        
        Args:
            template_json: Custom template JSON string (if any)
            preset_name: Preset name to use if no custom template
            
        Returns:
            Template dictionary
        """
        # Try to use custom template first
        if template_json:
            custom_template = cls.parse_template_json(template_json)
            if custom_template:
                logger.info("Using custom template")
                return custom_template
            else:
                logger.warning("Failed to parse custom template, falling back to preset")
        
        # Fall back to preset
        preset_template = cls.get_preset_template(preset_name)
        if preset_template:
            logger.info(f"Using preset template: {preset_name}")
            return preset_template
        
        # Ultimate fallback to generic
        logger.warning(f"Preset '{preset_name}' not found, using generic template")
        return cls.PRESETS["generic"]


# Convenience function for quick access
def get_template_manager() -> TextCompletionTemplateManager:
    """Get the template manager instance."""
    return TextCompletionTemplateManager()

