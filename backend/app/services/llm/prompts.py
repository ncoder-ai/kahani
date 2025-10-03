"""
Enhanced Prompt Management System

Handles loading and formatting of prompts with priority:
1. User-specific custom prompts from database
2. Default prompts from prompts.yml file
3. Built-in fallback prompts

Supports template variable substitution and dynamic prompt selection.
"""

import yaml
import os
from typing import Dict, Any, Optional, Tuple
import logging
from sqlalchemy.orm import Session
from app.models.prompt_template import PromptTemplate
from app.models.writing_style_preset import WritingStylePreset

logger = logging.getLogger(__name__)

class PromptManager:
    """Enhanced prompt manager with database and YAML support"""
    
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
    
    def get_prompt(
        self, 
        template_key: str, 
        prompt_type: str = "system", 
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
        **template_vars
    ) -> str:
        """
        Get a specific prompt with TWO-TIER system:
        
        SYSTEM PROMPTS (user-customizable):
        1. Active writing style preset's system_prompt (universal)
        2. Active writing style preset's summary_system_prompt (for story_summary only)
        3. Default from YAML file
        4. Built-in fallback
        
        USER PROMPTS (locked for app stability):
        1. YAML file only
        2. Built-in fallback
        
        Args:
            template_key: Template identifier (e.g., 'scene_generation', 'story_summary')
            prompt_type: Type of prompt ('system' or 'user')
            user_id: User ID to check for active writing style preset
            db: Database session for querying presets
            **template_vars: Variables to substitute in the prompt
        
        Returns:
            The requested prompt text with variables substituted
        """
        prompt_text = ""
        
        # Handle SYSTEM prompts - use writing style presets
        if prompt_type == "system":
            if user_id and db:
                try:
                    # Get user's active writing style preset
                    active_preset = db.query(WritingStylePreset).filter(
                        WritingStylePreset.user_id == user_id,
                        WritingStylePreset.is_active == True
                    ).first()
                    
                    if active_preset:
                        # For story summaries, check if there's a specific override
                        if template_key == "story_summary" and active_preset.summary_system_prompt:
                            prompt_text = active_preset.summary_system_prompt
                            logger.debug(f"Using custom summary system prompt from preset '{active_preset.name}'")
                        else:
                            # Use universal system prompt for all other generations
                            prompt_text = active_preset.system_prompt
                            logger.debug(f"Using universal system prompt from preset '{active_preset.name}'")
                        
                        if prompt_text:
                            return self._substitute_variables(prompt_text, **template_vars)
                            
                except Exception as e:
                    logger.warning(f"Error querying writing style preset: {e}")
            
            # Fallback to YAML system prompt
            prompt_text = self._get_yaml_prompt(template_key, "system")
            if prompt_text:
                logger.debug(f"Using YAML system prompt for template {template_key}")
                return self._substitute_variables(prompt_text, **template_vars)
            
            # Final fallback
            prompt_text = self._get_fallback_prompt(template_key, "system")
            if prompt_text:
                logger.debug(f"Using fallback system prompt for template {template_key}")
                return self._substitute_variables(prompt_text, **template_vars)
        
        # Handle USER prompts - ALWAYS from YAML (locked)
        elif prompt_type == "user":
            # Priority 1: YAML file (locked)
            prompt_text = self._get_yaml_prompt(template_key, "user")
            if prompt_text:
                logger.debug(f"Using YAML user prompt for template {template_key}")
                return self._substitute_variables(prompt_text, **template_vars)
            
            # Priority 2: Built-in fallback
            prompt_text = self._get_fallback_prompt(template_key, "user")
            if prompt_text:
                logger.debug(f"Using fallback user prompt for template {template_key}")
                return self._substitute_variables(prompt_text, **template_vars)
        
        logger.warning(f"No prompt found for template_key: {template_key}, prompt_type: {prompt_type}")
        return ""
    
    def _get_yaml_prompt(self, template_key: str, prompt_type: str) -> str:
        """Get prompt from YAML file"""
        if not self._prompts_cache:
            return ""
        
        # Map template keys to YAML structure
        yaml_mapping = {
            "scene_generation": ("story_generation", "scene"),
            "story_summary": ("summary_generation", "story_summary"),
            "choice_generation": ("choice_generation", ""),
            "title_generation": ("story_generation", "titles"),
            "scenario_generation": ("story_generation", "scenario"),
            "scene_continuation": ("story_generation", "scene_continuation"),
            "complete_plot": ("plot_generation", "complete_plot"),
            "single_plot_point": ("plot_generation", "single_plot_point"),
            "scene_variants": ("summary_generation", "scene_variants"),
            "story_chapters": ("summary_generation", "story_chapters")
        }
        
        if template_key not in yaml_mapping:
            return ""
        
        category, function = yaml_mapping[template_key]
        
        try:
            if function:
                return self._prompts_cache.get(category, {}).get(function, {}).get(prompt_type, "").strip()
            else:
                # Direct access to category (for choice_generation)
                return self._prompts_cache.get(category, {}).get(prompt_type, "").strip()
        except Exception as e:
            logger.error(f"Error retrieving YAML prompt {template_key}: {e}")
            return ""
    
    def _get_fallback_prompt(self, template_key: str, prompt_type: str) -> str:
        """Get built-in fallback prompt"""
        fallback_prompts = {
            "scene_generation": {
                "system": """You are a creative storytelling assistant. Generate engaging narrative scenes that maintain consistency, develop characters, and advance the plot meaningfully. Write in an immersive style that draws readers in.""",
                "user": """Continue the story naturally from where it left off. Create an engaging scene that advances the plot and develops the characters."""
            },
            "story_summary": {
                "system": """You are a skilled story analyst. Create concise, accurate summaries that capture the main plot points, character actions, and key events while maintaining the story's tone and style. Focus on what actually happened in the story.""",
                "user": """Please provide a concise summary of the following story content. Focus on the key events, character actions, and plot developments that actually occurred. Keep the summary brief and accurate.

Story Content:
{story_content}

Provide a summary that is approximately 2-3 paragraphs long, capturing the essence of what happened."""
            },
            "choice_generation": {
                "system": """You are a creative storytelling assistant. Generate exactly 4 compelling narrative choices that:
1. Offer meaningfully different story directions
2. Are specific to the current scene and context
3. Give readers genuine agency in the narrative
4. Vary in risk/consequence level
5. Are concise but evocative (1-2 sentences each)

Format each choice as a numbered list (1., 2., 3., 4.) with clear, actionable options.""",
                "user": """Based on this scene content and story context, generate 4 distinct narrative choices for what the protagonist could do next:

Scene: {scene_content}

Context: {context}

Generate 4 specific choices that advance the story in different ways."""
            },
            "title_generation": {
                "system": """You are a creative title generator. Generate 5 compelling story titles that capture the essence of the story, are memorable, and fit the genre and tone.""",
                "user": """Generate 5 compelling titles for this story concept that are intriguing and memorable."""
            },
            "scenario_generation": {
                "system": """You are a creative storytelling assistant. Generate engaging story scenarios that incorporate characters, create meaningful stakes, and establish compelling dramatic tension.""",
                "user": """Create a scenario based on these story elements that places the characters at the center and creates compelling dramatic tension."""
            },
            "scene_continuation": {
                "system": """You are a skilled creative writer. Continue the narrative naturally from where it left off, maintaining consistency with established characters and plot while advancing the story meaningfully.""",
                "user": """Continue this story naturally, following from the established context and any reader choices."""
            },
            "complete_plot": {
                "system": """You are a master storyteller. Generate a complete 5-point plot structure that builds naturally from the scenario, creates character arcs, and delivers satisfying resolutions.""",
                "user": """Generate a complete 5-point plot structure that weaves the characters' journeys into a compelling narrative arc."""
            },
            "single_plot_point": {
                "system": """You are a master storyteller. Generate a compelling plot point that is tailored to the characters, builds naturally from the scenario, and advances character development.""",
                "user": """Generate a compelling plot point that naturally incorporates the characters' personalities and the established scenario."""
            }
        }
        
        return fallback_prompts.get(template_key, {}).get(prompt_type, "")
    
    def _substitute_variables(self, prompt_text: str, **template_vars) -> str:
        """Substitute variables in prompt text"""
        if not prompt_text or not template_vars:
            return prompt_text
        
        try:
            # Log what variables we're substituting (truncate long content)
            log_vars = {k: (v[:100] + '...' if isinstance(v, str) and len(v) > 100 else v) for k, v in template_vars.items()}
            logger.info(f"Substituting variables: {log_vars}")
            
            result = prompt_text.format(**template_vars)
            logger.info(f"Substituted prompt length: {len(result)} characters")
            return result
        except KeyError as e:
            logger.warning(f"Missing variable {e} in prompt template")
            return prompt_text
        except Exception as e:
            logger.error(f"Error substituting variables in prompt: {e}")
            return prompt_text
    
    def get_prompt_with_variables(
        self, 
        template_key: str, 
        prompt_type: str = "system",
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
        **variables
    ) -> str:
        """
        Get a prompt and substitute variables (alias for get_prompt)
        
        Args:
            template_key: Template identifier
            prompt_type: Type of prompt
            user_id: User ID to check for custom prompts
            db: Database session
            **variables: Variables to substitute
        
        Returns:
            The prompt with variables substituted
        """
        return self.get_prompt(template_key, prompt_type, user_id, db, **variables)
    
    def get_all_prompts_for_template(
        self, 
        template_key: str, 
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
        **template_vars
    ) -> Dict[str, str]:
        """
        Get all prompts (system and user) for a specific template
        
        Args:
            template_key: Template identifier
            user_id: User ID to check for custom prompts
            db: Database session
            **template_vars: Variables to substitute
        
        Returns:
            Dictionary with 'system' and 'user' prompts
        """
        return {
            "system": self.get_prompt(template_key, "system", user_id, db, **template_vars),
            "user": self.get_prompt(template_key, "user", user_id, db, **template_vars)
        }
    
    def get_max_tokens(self, template_key: str) -> int:
        """Get max_tokens setting for a template"""
        if not self._prompts_cache:
            return 2048  # Default fallback
        
        try:
            # Map template keys to YAML function names for max_tokens lookup
            function_mapping = {
                "scene_generation": "scene",
                "story_summary": "story_summary",
                "choice_generation": "choices",
                "title_generation": "titles",
                "scenario_generation": "scenario",
                "scene_continuation": "scene_continuation",
                "complete_plot": "complete_plot",
                "single_plot_point": "single_plot_point",
                "scene_variants": "scene_variants",
                "story_chapters": "story_chapters"
            }
            
            function_name = function_mapping.get(template_key, template_key)
            return self._prompts_cache.get("settings", {}).get("max_tokens", {}).get(function_name, 2048)
        except (KeyError, TypeError):
            return 2048
    
    def get_temperature(self, temp_type: str = "default") -> float:
        """Get temperature setting"""
        if not self._prompts_cache:
            return 0.7  # Default fallback
        
        try:
            return self._prompts_cache.get("settings", {}).get("temperature", {}).get(temp_type, 0.7)
        except (KeyError, TypeError):
            return 0.7
    
    def list_available_templates(self) -> Dict[str, Any]:
        """
        List all available prompt templates
        
        Returns:
            Dictionary of all available templates
        """
        return {
            "yaml_prompts": self._prompts_cache or {},
            "supported_template_keys": [
                "scene_generation", "story_summary", "choice_generation", 
                "title_generation", "scenario_generation", "scene_continuation",
                "complete_plot", "single_plot_point", "scene_variants", "story_chapters"
            ]
        }
    
    def get_prompt_pair(
        self, 
        template_key: str, 
        user_prompt_key: str,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
        **template_vars
    ) -> tuple[str, str]:
        """
        Get both system and user prompts as a pair.
        
        Args:
            template_key: Template identifier (e.g., 'story_generation')
            user_prompt_key: Specific user prompt key (e.g., 'scene')
            user_id: User ID to check for active writing style preset
            db: Database session for preset lookup
            **template_vars: Variables for template substitution
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = self.get_prompt(
            template_key, 
            "system", 
            user_id=user_id, 
            db=db, 
            **template_vars
        )
        
        user_prompt = self.get_prompt(
            user_prompt_key, 
            "user", 
            user_id=user_id, 
            db=db, 
            **template_vars
        )
        
        return system_prompt, user_prompt

# Global prompt manager instance
prompt_manager = PromptManager()