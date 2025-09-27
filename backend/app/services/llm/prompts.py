"""
Prompt Management System

Handles loading and formatting of prompts from the centralized prompts.yml file.
"""

import yaml
import os
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    """Manages loading and formatting of prompts from prompts.yml"""
    
    def __init__(self, prompts_file_path: str = None):
        """Initialize prompt manager with path to prompts.yml"""
        if prompts_file_path is None:
            # Default to prompts.yml in the backend directory
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            prompts_file_path = os.path.join(current_dir, "prompts.yml")
        
        self.prompts_file_path = prompts_file_path
        self._prompts_cache: Optional[Dict[str, Any]] = None
        self._load_prompts()
    
    def _load_prompts(self):
        """Load prompts from YAML file"""
        try:
            with open(self.prompts_file_path, 'r', encoding='utf-8') as file:
                self._prompts_cache = yaml.safe_load(file)
            logger.info(f"Loaded prompts from {self.prompts_file_path}")
        except FileNotFoundError:
            logger.error(f"Prompts file not found: {self.prompts_file_path}")
            self._prompts_cache = {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing prompts YAML: {e}")
            self._prompts_cache = {}
        except Exception as e:
            logger.error(f"Unexpected error loading prompts: {e}")
            self._prompts_cache = {}
    
    def reload_prompts(self):
        """Reload prompts from file (useful for development)"""
        self._load_prompts()
    
    def get_prompt(self, category: str, function: str, prompt_type: str = "system") -> str:
        """
        Get a specific prompt from the loaded prompts
        
        Args:
            category: Top-level category (e.g., 'story_generation')
            function: Function name (e.g., 'scene', 'titles')
            prompt_type: 'system' or 'user'
        
        Returns:
            The prompt string, or empty string if not found
        """
        if not self._prompts_cache:
            logger.warning("No prompts loaded")
            return ""
        
        try:
            prompt = self._prompts_cache.get(category, {}).get(function, {}).get(prompt_type, "")
            if not prompt:
                logger.warning(f"Prompt not found: {category}.{function}.{prompt_type}")
            return prompt
        except (KeyError, TypeError) as e:
            logger.error(f"Error accessing prompt {category}.{function}.{prompt_type}: {e}")
            return ""
    
    def get_system_prompt(self, category: str, function: str) -> str:
        """Get system prompt for a function"""
        return self.get_prompt(category, function, "system")
    
    def get_user_prompt(self, category: str, function: str) -> str:
        """Get user prompt for a function"""
        return self.get_prompt(category, function, "user")
    
    def format_prompt(self, prompt_template: str, **kwargs) -> str:
        """
        Format a prompt template with provided variables
        
        Args:
            prompt_template: The prompt template string
            **kwargs: Variables to substitute in the template
        
        Returns:
            Formatted prompt string
        """
        try:
            return prompt_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing variable in prompt template: {e}")
            return prompt_template
        except Exception as e:
            logger.error(f"Error formatting prompt: {e}")
            return prompt_template
    
    def get_max_tokens(self, function: str) -> int:
        """Get max_tokens setting for a function"""
        if not self._prompts_cache:
            return 1024  # Default fallback
        
        try:
            return self._prompts_cache.get("settings", {}).get("max_tokens", {}).get(function, 1024)
        except (KeyError, TypeError):
            return 1024
    
    def get_temperature(self, temp_type: str = "default") -> float:
        """Get temperature setting"""
        if not self._prompts_cache:
            return 0.7  # Default fallback
        
        try:
            return self._prompts_cache.get("settings", {}).get("temperature", {}).get(temp_type, 0.7)
        except (KeyError, TypeError):
            return 0.7
    
    def get_prompt_pair(self, category: str, function: str, **kwargs) -> Tuple[str, str]:
        """
        Get both system and user prompts for a function, formatted with provided variables
        
        Args:
            category: Prompt category
            function: Function name
            **kwargs: Variables to format the prompts with
        
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = self.get_system_prompt(category, function)
        user_prompt = self.get_user_prompt(category, function)
        
        # Format both prompts with provided variables
        system_prompt = self.format_prompt(system_prompt, **kwargs)
        user_prompt = self.format_prompt(user_prompt, **kwargs)
        
        return system_prompt, user_prompt

# Global prompt manager instance
prompt_manager = PromptManager()
