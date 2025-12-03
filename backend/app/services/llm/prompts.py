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
        
        # Handle SYSTEM prompts - use writing style presets for specific generation types only
        if prompt_type == "system":
            # Define which generation types should use user writing presets
            # These are the core story writing operations that should respect user's writing style
            user_preset_enabled_types = {
                "scene_with_immediate",       # Scenes with continue choice
                "scene_without_immediate",    # Scenes without continue choice
                "scene_continuation",          # Scene continuations
                "scene_guided_enhancement",   # Scene guided enhancement
                "story_summary",               # Story summaries (uses summary_system_prompt)
                "scenario_generation"          # Story scenario/premise generation
                # NOTE: scene_variants removed - now uses scene_with/without_immediate
            }
            
            # Only use user presets for enabled generation types
            if template_key in user_preset_enabled_types and user_id and db:
                try:
                    # Get user's active writing style preset
                    active_preset = db.query(WritingStylePreset).filter(
                        WritingStylePreset.user_id == user_id,
                        WritingStylePreset.is_active == True
                    ).first()
                    
                    if active_preset:
                        # For story summaries, check if there's a specific override
                        if template_key == "story_summary" and active_preset.summary_system_prompt:
                            style_prompt = active_preset.summary_system_prompt
                            logger.debug(f"Using custom summary system prompt from preset '{active_preset.name}'")
                        else:
                            # Use universal system prompt for other enabled generations
                            style_prompt = active_preset.system_prompt
                            logger.debug(f"Using universal system prompt from preset '{active_preset.name}' for {template_key}")
                        
                        if style_prompt:
                            # Get POV from preset if available
                            pov = getattr(active_preset, 'pov', None) if hasattr(active_preset, 'pov') else None
                            
                            # Get technical requirements from YAML (with POV substitution)
                            yaml_full_prompt = self._get_yaml_prompt(template_key, "system")
                            technical_requirements = self._extract_technical_requirements(yaml_full_prompt, pov)
                            
                            # Build POV-related values for both prose instruction and template variables
                            pov_instruction_prose = ""
                            pov_instruction_var = ""  # For {pov_instruction} template variable
                            pov_perspective_var = ""  # For {pov_perspective} template variable
                            
                            if pov == "first":
                                pov_instruction_prose = "\n\nWrite in first person perspective (using 'I', 'me', 'my') to create an immersive experience."
                                pov_instruction_var = "in first person perspective (using 'I', 'me', 'my')"
                                pov_perspective_var = "First person perspective (I/me/my)"
                            elif pov == "second":
                                pov_instruction_prose = "\n\nWrite in second person perspective (using 'you', 'your') to create an immersive interactive experience."
                                pov_instruction_var = "in second person perspective (using 'you', 'your')"
                                pov_perspective_var = "Second person perspective (you/your)"
                            else:  # third or not pov
                                pov_instruction_prose = "\n\nWrite in third person perspective (using 'he', 'she', 'they', character names) to maintain story immersion."
                                pov_instruction_var = "in third person perspective (using 'he', 'she', 'they', character names)"
                                pov_perspective_var = "Third person perspective (he/she/they/name)"
                            
                            # Add POV template variables to template_vars for substitution
                            template_vars_with_pov = dict(template_vars)
                            template_vars_with_pov['pov_instruction'] = pov_instruction_var
                            template_vars_with_pov['pov_perspective'] = pov_perspective_var
                            
                            # Combine: style + POV instruction + technical requirements
                            if technical_requirements:
                                combined_prompt = f"{style_prompt.strip()}{pov_instruction_prose}\n\n{technical_requirements}"
                                logger.debug(f"Combined user preset style with POV ({pov or 'third'}) and technical requirements from YAML for {template_key}")
                            else:
                                # No technical requirements found, combine style + POV only
                                combined_prompt = f"{style_prompt.strip()}{pov_instruction_prose}"
                                logger.debug(f"Combined user preset style with POV ({pov or 'third'}) (no technical requirements) for {template_key}")
                            
                            return self._substitute_variables(combined_prompt, **template_vars_with_pov)
                            
                except Exception as e:
                    logger.warning(f"Error querying writing style preset: {e}")
            else:
                logger.debug(f"Using YAML prompts for {template_key} (not user preset enabled)")
            
            # Fallback to YAML system prompt
            # For templates with technical requirements, extract style and combine with technical requirements
            # For others, use full prompt as-is
            yaml_full_prompt = self._get_yaml_prompt(template_key, "system")
            if yaml_full_prompt:
                templates_with_tech_requirements = {
                    "scene_with_immediate", "scene_without_immediate",
                    "scene_guided_enhancement", "scene_continuation"
                    # NOTE: scene_variants removed - now uses scene_with/without_immediate
                }
                
                if template_key in templates_with_tech_requirements:
                    # Extract style portion and technical requirements separately for consistency
                    style_portion = self._extract_style_portion(yaml_full_prompt)
                    # Default to third person POV when no preset
                    technical_requirements = self._extract_technical_requirements(yaml_full_prompt, "third")
                    
                    # Default to third person POV when no preset
                    pov_instruction_prose = "\n\nWrite in third person perspective (using 'he', 'she', 'they', character names) to maintain story immersion."
                    
                    # Add default POV template variables for substitution
                    template_vars_with_pov = dict(template_vars)
                    template_vars_with_pov['pov_instruction'] = "in third person perspective (using 'he', 'she', 'they', character names)"
                    template_vars_with_pov['pov_perspective'] = "Third person perspective (he/she/they/name)"
                    
                    if technical_requirements:
                        combined_prompt = f"{style_portion}{pov_instruction_prose}\n\n{technical_requirements}"
                        logger.debug(f"Using extracted YAML style + POV + technical requirements for template {template_key}")
                    else:
                        combined_prompt = f"{style_portion}{pov_instruction_prose}"
                        logger.debug(f"Using extracted YAML style + POV for template {template_key}")
                    
                    return self._substitute_variables(combined_prompt, **template_vars_with_pov)
                else:
                    # Use as-is (may not have technical sections)
                    logger.debug(f"Using YAML system prompt for template {template_key}")
                    return self._substitute_variables(yaml_full_prompt, **template_vars)
            
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
                logger.info(f"[GET_PROMPT] Using YAML user prompt for template {template_key}")
                logger.info(f"[GET_PROMPT] Prompt text length: {len(prompt_text)}")
                logger.info(f"[GET_PROMPT] Template vars provided: {list(template_vars.keys())}")
                # Check if prompt contains the variables we're trying to substitute
                if "{immediate_situation}" in prompt_text:
                    logger.info(f"[GET_PROMPT] Prompt contains {{immediate_situation}} variable")
                    # Ensure immediate_situation is in template_vars if the prompt needs it
                    if "immediate_situation" not in template_vars:
                        logger.error(f"[GET_PROMPT] CRITICAL: Prompt requires immediate_situation but it's not in template_vars!")
                        logger.error(f"[GET_PROMPT] Available template_vars: {list(template_vars.keys())}")
                        # Add it as empty string to prevent KeyError
                        template_vars["immediate_situation"] = ""
                    else:
                        logger.info(f"[GET_PROMPT] immediate_situation is in template_vars, value: '{template_vars.get('immediate_situation', 'NOT FOUND')}'")
                if "{scene_length_description}" in prompt_text:
                    logger.info(f"[GET_PROMPT] Prompt contains {{scene_length_description}} variable")
                logger.info(f"[GET_PROMPT] About to call _substitute_variables with keys: {list(template_vars.keys())}")
                return self._substitute_variables(prompt_text, **template_vars)
            
            # Priority 2: Built-in fallback
            prompt_text = self._get_fallback_prompt(template_key, "user")
            if prompt_text:
                logger.debug(f"[GET_PROMPT] Using fallback user prompt for template {template_key}")
                return self._substitute_variables(prompt_text, **template_vars)
        
        logger.warning(f"No prompt found for template_key: {template_key}, prompt_type: {prompt_type}")
        return ""
    
    def _extract_style_portion(self, full_prompt: str) -> str:
        """
        Extract the style portion from a full system prompt.
        Style portion is everything before "FORMATTING REQUIREMENTS" or "CRITICAL SPECIFICITY REQUIREMENTS".
        """
        if not full_prompt:
            return ""
        
        # Find where technical requirements start
        formatting_marker = "FORMATTING REQUIREMENTS:"
        specificity_marker = "CRITICAL SPECIFICITY REQUIREMENTS:"
        
        formatting_pos = full_prompt.find(formatting_marker)
        specificity_pos = full_prompt.find(specificity_marker)
        
        # Find the earliest technical section
        tech_start = None
        if formatting_pos != -1 and specificity_pos != -1:
            tech_start = min(formatting_pos, specificity_pos)
        elif formatting_pos != -1:
            tech_start = formatting_pos
        elif specificity_pos != -1:
            tech_start = specificity_pos
        
        if tech_start is not None:
            # Extract everything before technical requirements
            style = full_prompt[:tech_start].strip()
            return style
        
        # If no technical markers found, return the full prompt (might be a simple style-only prompt)
        return full_prompt.strip()
    
    def _extract_technical_requirements(self, full_prompt: str, pov: Optional[str] = None) -> str:
        """
        Extract technical requirements (formatting + choices) from a full system prompt.
        Returns everything from "CRITICAL SPECIFICITY REQUIREMENTS" or "FORMATTING REQUIREMENTS" onwards.
        Optionally substitutes POV instructions based on pov parameter.
        """
        if not full_prompt:
            return ""
        
        # Find where technical requirements start
        formatting_marker = "FORMATTING REQUIREMENTS:"
        specificity_marker = "CRITICAL SPECIFICITY REQUIREMENTS:"
        
        formatting_pos = full_prompt.find(formatting_marker)
        specificity_pos = full_prompt.find(specificity_marker)
        
        # Find the earliest technical section
        tech_start = None
        if formatting_pos != -1 and specificity_pos != -1:
            tech_start = min(formatting_pos, specificity_pos)
        elif formatting_pos != -1:
            tech_start = formatting_pos
        elif specificity_pos != -1:
            tech_start = specificity_pos
        
        if tech_start is not None:
            # Extract everything from technical requirements onwards
            technical = full_prompt[tech_start:].strip()
            
            # Substitute POV in choices requirements if pov is specified
            if pov and "CHOICES GENERATION REQUIREMENTS" in technical:
                if pov == "first":
                    # Replace third person instructions with first person
                    technical = technical.replace(
                        "use third person (he/she/they/character name) NOT first person (I/me/my) or second person (you/your)",
                        "use first person (I/me/my) NOT second person (you/your) or third person (he/she/they)"
                    )
                    technical = technical.replace(
                        "Write choices in THIRD PERSON perspective describing what the character does, NOT what \"I do\" or \"you do\".",
                        "Write choices in FIRST PERSON perspective describing what I do, NOT what \"you do\" or third person descriptions."
                    )
                    technical = technical.replace(
                        "Example: \"Jack approaches the door cautiously\" NOT \"I approach the door cautiously\" or \"You approach the door cautiously\"",
                        "Example: \"I approach the door cautiously\" NOT \"You approach the door cautiously\" or \"Jack approaches the door cautiously\""
                    )
                elif pov == "second":
                    # Replace third person instructions with second person
                    technical = technical.replace(
                        "use third person (he/she/they/character name) NOT first person (I/me/my) or second person (you/your)",
                        "use second person (you/your) NOT first person (I/me/my) or third person (he/she/they)"
                    )
                    technical = technical.replace(
                        "Write choices in THIRD PERSON perspective describing what the character does, NOT what \"I do\" or \"you do\".",
                        "Write choices in SECOND PERSON perspective describing what you do, NOT what \"I do\" or third person descriptions."
                    )
                    technical = technical.replace(
                        "Example: \"Jack approaches the door cautiously\" NOT \"I approach the door cautiously\" or \"You approach the door cautiously\"",
                        "Example: \"You approach the door cautiously\" NOT \"I approach the door cautiously\" or \"Jack approaches the door cautiously\""
                    )
                # For third person or None, keep as-is (already third person)
            
            return technical
        
        # If no technical markers found, return empty (no technical requirements)
        return ""
    
    def _compose_scene_system_prompt(self, template_key: str) -> str:
        """
        Compose a scene system prompt from base components.
        
        For scene types that use the composable structure, this combines:
        - scene_base.system (core writing instructions)
        - scene_base.formatting (standard formatting rules)
        - scene_base.choices (choices generation instructions)
        
        Note: {pov_instruction} placeholder is left intact for later substitution
        by _substitute_variables() with the actual POV from template vars.
        
        Args:
            template_key: The scene template key
            
        Returns:
            Composed system prompt or empty string if not a composable scene type
        """
        # ALL scene types that generate choices use composable base components
        # This ensures consistent choice generation instructions across all scene types
        composable_scene_types = {
            "scene_with_immediate",
            "scene_without_immediate",
            "scene_guided_enhancement",
            "scene_continuation"
        }
        
        if template_key not in composable_scene_types:
            return ""
        
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        if not scene_base:
            logger.debug(f"[PROMPTS] No scene_base found in YAML, falling back to individual prompt")
            return ""
        
        base_system = scene_base.get("system", "").strip()
        formatting = scene_base.get("formatting", "").strip()
        choices = scene_base.get("choices", "").strip()
        
        if not base_system:
            return ""
        
        # Compose the full system prompt
        # Note: {pov_instruction} and {choices_count} placeholders are preserved
        # for later substitution by _substitute_variables()
        composed = base_system
        if formatting:
            composed += "\n\n" + formatting
        if choices:
            composed += "\n\n" + choices
        
        logger.debug(f"[PROMPTS] Composed scene system prompt for {template_key} (length: {len(composed)})")
        return composed
    
    def _get_user_choices_reminder(self) -> str:
        """Get the user choices reminder from scene_base for appending to scene user prompts"""
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        return scene_base.get("user_choices_reminder", "").strip()
    
    def get_user_choices_reminder(self, **template_vars) -> str:
        """
        Public method to get the user choices reminder with variable substitution.
        
        Args:
            **template_vars: Variables to substitute (e.g., choices_count)
            
        Returns:
            The choices reminder text with variables substituted
        """
        reminder = self._get_user_choices_reminder()
        if reminder and template_vars:
            return self._substitute_variables(reminder, **template_vars)
        return reminder
    
    def get_task_instruction(self, has_immediate: bool, **template_vars) -> str:
        """
        Get task instruction for multi-message structure from scene_base.
        
        Args:
            has_immediate: Whether there's an immediate_situation (determines which template)
            **template_vars: Variables to substitute (e.g., immediate_situation, scene_length_description)
            
        Returns:
            The task instruction text with variables substituted
        """
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        template_key = "task_with_immediate" if has_immediate else "task_without_immediate"
        instruction = scene_base.get(template_key, "").strip()
        
        if instruction and template_vars:
            return self._substitute_variables(instruction, **template_vars)
        return instruction
    
    def get_continuation_task_instruction(
        self, 
        current_scene_content: str, 
        continuation_prompt: str, 
        choices_count: int = 4
    ) -> str:
        """
        Get task instruction for scene continuation from scene_base.task_continuation.
        
        This is used by generate_continuation_with_choices_streaming() for the final
        message in the multi-message structure. Context is sent separately.
        
        Args:
            current_scene_content: The scene content to continue
            continuation_prompt: User's continuation instruction
            choices_count: Number of choices to generate
            
        Returns:
            The task instruction text with variables substituted and choices reminder appended
        """
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        instruction = scene_base.get("task_continuation", "").strip()
        
        if not instruction:
            # Fallback if template not found
            instruction = f"""=== CURRENT SCENE TO CONTINUE ===
{current_scene_content}

=== CONTINUATION INSTRUCTION ===
{continuation_prompt}

Write a compelling continuation that follows naturally from the scene above. Focus on engaging narrative and dialogue. Do not repeat previous content."""
        else:
            instruction = self._substitute_variables(
                instruction, 
                current_scene_content=current_scene_content,
                continuation_prompt=continuation_prompt
            )
        
        # Append choices reminder
        choices_reminder = self.get_user_choices_reminder(choices_count=choices_count)
        if choices_reminder:
            instruction = instruction + "\n\n" + choices_reminder
        
        return instruction
    
    def get_enhancement_task_instruction(
        self, 
        original_scene: str, 
        enhancement_guidance: str, 
        scene_length_description: str = "medium (100-150 words)",
        choices_count: int = 4
    ) -> str:
        """
        Get task instruction for guided enhancement from scene_base.task_guided_enhancement.
        
        This is used by generate_scene_variants_with_choices_streaming() for the final
        message in the multi-message structure. Context is sent separately.
        
        Args:
            original_scene: The original scene to enhance
            enhancement_guidance: User's enhancement request
            scene_length_description: Target scene length description
            choices_count: Number of choices to generate
            
        Returns:
            The task instruction text with variables substituted and choices reminder appended
        """
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        instruction = scene_base.get("task_guided_enhancement", "").strip()
        
        if not instruction:
            # Fallback if template not found
            instruction = f"""=== ORIGINAL SCENE ===
{original_scene}

=== ENHANCEMENT REQUEST ===
{enhancement_guidance}

Rewrite the scene above incorporating the requested enhancement.
Maintain the same core events and outcomes. Keep consistency with established story elements.
Write approximately {scene_length_description} in length."""
        else:
            instruction = self._substitute_variables(
                instruction, 
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description
            )
        
        # Append choices reminder
        choices_reminder = self.get_user_choices_reminder(choices_count=choices_count)
        if choices_reminder:
            instruction = instruction + "\n\n" + choices_reminder
        
        return instruction
    
    def get_chapter_conclusion_task_instruction(
        self,
        chapter_number: int = 1,
        chapter_title: str = "Untitled",
        chapter_location: str = "Unknown",
        chapter_time_period: str = "Unknown",
        chapter_scenario: str = "None"
    ) -> str:
        """
        Get task instruction for chapter conclusion from scene_base.task_chapter_conclusion.
        
        This is used by generate_concluding_scene_streaming() for the final
        message in the multi-message structure. Context is sent separately.
        
        Args:
            chapter_number: The chapter number
            chapter_title: The chapter title
            chapter_location: The chapter location
            chapter_time_period: The chapter time period
            chapter_scenario: The chapter scenario
            
        Returns:
            The task instruction text with variables substituted
        """
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        instruction = scene_base.get("task_chapter_conclusion", "").strip()
        
        if not instruction:
            # Fallback if template not found
            instruction = f"""=== CHAPTER CONCLUSION INSTRUCTIONS ===

Chapter Information:
- Chapter Number: {chapter_number}
- Title: {chapter_title}
- Location: {chapter_location}
- Time Period: {chapter_time_period}
- Scenario: {chapter_scenario}

Create a chapter conclusion that brings Chapter {chapter_number} to a natural and satisfying end.
Write ONLY the narrative content. Do not include any choices, options, or questions for the reader.

Chapter Conclusion:"""
        else:
            instruction = self._substitute_variables(
                instruction,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                chapter_location=chapter_location,
                chapter_time_period=chapter_time_period,
                chapter_scenario=chapter_scenario
            )
        
        return instruction
    
    def get_pov_reminder(self, pov: str = 'third') -> str:
        """
        Get POV reminder text from scene_base.pov_reminder with POV substituted.
        
        This is appended to system prompts to remind the LLM about POV consistency
        for choices generation.
        
        Args:
            pov: The POV setting ('first', 'second', or 'third')
            
        Returns:
            The POV reminder text with {pov_instruction} substituted
        """
        if not self._prompts_cache:
            return ""
        
        scene_base = self._prompts_cache.get("scene_base", {})
        reminder = scene_base.get("pov_reminder", "").strip()
        
        if not reminder:
            return ""
        
        # Build pov_instruction based on POV
        if pov == 'first':
            pov_instruction = "in first person perspective (using 'I', 'me', 'my')"
        elif pov == 'second':
            pov_instruction = "in second person perspective (using 'you', 'your')"
        else:  # third or default
            pov_instruction = "in third person perspective (using 'he', 'she', 'they', character names)"
        
        return self._substitute_variables(reminder, pov_instruction=pov_instruction)
    
    def _get_yaml_prompt(self, template_key: str, prompt_type: str) -> str:
        """Get prompt from YAML file"""
        if not self._prompts_cache:
            logger.warning(f"[PROMPTS] YAML cache is empty, cannot retrieve {template_key}.{prompt_type}")
            return ""
        
        # Scene types that use composable base components
        composable_scene_types = {
            "scene_with_immediate",
            "scene_without_immediate",
            "scene_guided_enhancement",
            "scene_continuation"
        }
        
        # For system prompts of composable scene types, compose from base
        if prompt_type == "system" and template_key in composable_scene_types:
            composed = self._compose_scene_system_prompt(template_key)
            if composed:
                return composed
        
        # Map template keys to YAML structure
        yaml_mapping = {
            "scene_with_immediate": ("story_generation", "scene_with_immediate"),
            "scene_without_immediate": ("story_generation", "scene_without_immediate"),
            "scene_guided_enhancement": ("story_generation", "scene_guided_enhancement"),
            "story_summary": ("summary_generation", "story_summary"),
            "choice_generation": ("choice_generation", ""),
            "title_generation": ("story_generation", "titles"),
            "scenario_generation": ("story_generation", "scenario"),
            "scene_continuation": ("story_generation", "scene_continuation"),
            "complete_plot": ("plot_generation", "complete_plot"),
            "single_plot_point": ("plot_generation", "single_plot_point"),
            # NOTE: scene_variants and scene_variants_streaming removed - now uses scene_with/without_immediate
            "story_chapters": ("summary_generation", "story_chapters"),
            "chapter_conclusion": ("chapter_conclusion", ""),
            "character_assistant.extraction": ("character_assistant", "extraction"),
            "character_assistant.detection": ("character_assistant", "detection"),
            "character_assistant.generation": ("character_assistant", "generation"),
            "entity_state_extraction.single": ("entity_state_extraction", "single"),
            "entity_state_extraction.batch": ("entity_state_extraction", "batch")
        }
        
        if template_key not in yaml_mapping:
            logger.warning(f"[PROMPTS] Template key '{template_key}' not found in yaml_mapping")
            return ""
        
        category, function = yaml_mapping[template_key]
        logger.debug(f"[PROMPTS] Looking up {template_key}.{prompt_type} -> category='{category}', function='{function}'")
        
        try:
            if function:
                prompt = self._prompts_cache.get(category, {}).get(function, {}).get(prompt_type, "").strip()
                if prompt:
                    logger.debug(f"[PROMPTS] Found YAML prompt for {template_key}.{prompt_type} (length: {len(prompt)})")
                    # Check for key variables in the prompt
                    if "{immediate_situation}" in prompt:
                        logger.debug(f"[PROMPTS] Prompt contains {{immediate_situation}} variable")
                    if "{scene_length_description}" in prompt:
                        logger.debug(f"[PROMPTS] Prompt contains {{scene_length_description}} variable")
                    if "{context}" in prompt:
                        logger.debug(f"[PROMPTS] Prompt contains {{context}} variable")
                else:
                    logger.warning(f"[PROMPTS] YAML prompt for {template_key}.{prompt_type} is empty. Path: {category}.{function}.{prompt_type}")
                
                # For user prompts of composable scene types, append the choices reminder
                if prompt and prompt_type == "user" and template_key in composable_scene_types:
                    user_choices_reminder = self._get_user_choices_reminder()
                    if user_choices_reminder:
                        prompt = prompt + "\n\n" + user_choices_reminder
                        logger.debug(f"[PROMPTS] Appended user_choices_reminder to {template_key} user prompt")
                
                return prompt
            else:
                # Direct access to category (for choice_generation, chapter_conclusion)
                prompt = self._prompts_cache.get(category, {}).get(prompt_type, "").strip()
                if prompt:
                    logger.debug(f"[PROMPTS] Found YAML prompt for {template_key}.{prompt_type} (length: {len(prompt)})")
                else:
                    logger.warning(f"[PROMPTS] YAML prompt for {template_key}.{prompt_type} is empty. Path: {category}.{prompt_type}")
                    logger.debug(f"[PROMPTS] Available top-level keys in YAML: {list(self._prompts_cache.keys())}")
                    if category in self._prompts_cache:
                        logger.debug(f"[PROMPTS] Keys under '{category}': {list(self._prompts_cache[category].keys())}")
                        logger.debug(f"[PROMPTS] Full structure of '{category}': {self._prompts_cache[category]}")
                    else:
                        logger.warning(f"[PROMPTS] Category '{category}' not found in YAML cache")
                        # Check if it exists with different casing or structure
                        for key in self._prompts_cache.keys():
                            if key.lower() == category.lower():
                                logger.warning(f"[PROMPTS] Found similar key '{key}' (case mismatch?)")
                return prompt
        except Exception as e:
            logger.error(f"[PROMPTS] Error retrieving YAML prompt {template_key}.{prompt_type}: {e}", exc_info=True)
            return ""
    
    def _get_fallback_prompt(self, template_key: str, prompt_type: str) -> str:
        """Get built-in fallback prompt"""
        fallback_prompts = {
            "scene_with_immediate": {
                "system": """You are a creative storytelling assistant. Generate engaging narrative scenes that maintain consistency, develop characters, and advance the plot meaningfully. Write in an immersive style that draws readers in.""",
                "user": """Continue the story naturally based on what happens next. Create an engaging scene that advances the plot and develops the characters."""
            },
            "scene_without_immediate": {
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
                "system": """You are an interactive fiction choice generator. Create engaging story choices that:
1. Are meaningful and impact the story direction
2. Reflect different character approaches or personalities
3. Offer varied consequences and outcomes
4. Maintain consistency with the established story world
5. Give players agency in how they want to proceed
6. Are concise but evocative (Only 1 sentence each)
7. Match the story's POV - use third person (he/she/they/character name) NOT first person (I/me/my) or second person (you/your)

IMPORTANT: Write choices in THIRD PERSON perspective describing what the character does, NOT what "I do" or "you do".
Example: "Jack approaches the door cautiously" NOT "I approach the door cautiously" or "You approach the door cautiously"

Generate exactly {choices_count} choices. Each choice should be just one short sentence, no more than 15 words.

Format: Provide exactly {choices_count} choices as a JSON array: ["Choice 1 text here", "Choice 2 text here", ...]""",
                "user": """Based on this scene:

{scene_content}

Story Context:
{context}

Generate {choices_count} meaningful choices for what happens next. Each choice should:
- Lead to different story outcomes
- Reflect different approaches to the situation
- Be engaging and make the reader want to see what happens
- Be specific to the current scene and context
- Give readers genuine agency in the narrative
- Vary in risk/consequence level

Remember each choice must be only 1 short sentence, no more than 15 words.

Provide exactly {choices_count} choices as a JSON array: ["Choice 1 text here", "Choice 2 text here", ...]"""
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
            "scene_guided_enhancement": {
                "system": """You are a skilled interactive fiction writer. Enhance an existing scene by rewriting it while maintaining the same core events and outcomes, incorporating the specific enhancement requested.""",
                "user": """Story Context:
{context}

Current Scene to Enhance:
{original_scene}

Enhancement Request:
{enhancement_guidance}

Rewrite the scene above incorporating the enhancement while maintaining the same core events and outcomes. Make it engaging and immersive, {scene_length_description}."""
            },
            "complete_plot": {
                "system": """You are a master storyteller. Generate a complete 5-point plot structure that builds naturally from the scenario, creates character arcs, and delivers satisfying resolutions.""",
                "user": """Generate a complete 5-point plot structure that weaves the characters' journeys into a compelling narrative arc."""
            },
            "single_plot_point": {
                "system": """You are a master storyteller. Generate a compelling plot point that is tailored to the characters, builds naturally from the scenario, and advances character development.""",
                "user": """Generate a compelling plot point that naturally incorporates the characters' personalities and the established scenario."""
            },
            "chapter_conclusion": {
                "system": """You are a skilled interactive fiction writer specializing in chapter endings. Create a compelling chapter conclusion that brings the current chapter to a natural and satisfying end, ties up loose threads, sets up anticipation for the next chapter, and maintains consistency with established story elements.""",
                "user": """Based on the story context below, create a chapter conclusion that brings Chapter {chapter_number} to a natural and satisfying end.

{context}

Chapter Information:
- Title: {chapter_title}
- Location: {chapter_location}
- Time Period: {chapter_time_period}
- Scenario: {chapter_scenario}

Create a conclusion that provides closure for this chapter's events, ties up chapter-specific plot threads, sets up anticipation for the next chapter, and maintains the established genre, tone, and writing style.

Chapter Conclusion:"""
            }
        }
        
        return fallback_prompts.get(template_key, {}).get(prompt_type, "")
    
    def _substitute_variables(self, prompt_text: str, **template_vars) -> str:
        """Substitute variables in prompt text"""
        if not prompt_text or not template_vars:
            logger.warning(f"[SUBSTITUTE] No prompt_text or template_vars provided. prompt_text: {bool(prompt_text)}, template_vars: {bool(template_vars)}")
            return prompt_text
        
        try:
            # Check which variables are in the template
            import re
            template_vars_in_text = re.findall(r'\{(\w+)\}', prompt_text)
            missing_vars = set(template_vars_in_text) - set(template_vars.keys())
            if missing_vars:
                logger.warning(f"[SUBSTITUTE] Template requires variables not provided: {missing_vars}")
            
            result = prompt_text.format(**template_vars)
            
            # Check if any variables remain unsubstituted
            remaining_vars = re.findall(r'\{(\w+)\}', result)
            if remaining_vars:
                logger.error(f"[SUBSTITUTE] Variables still unsubstituted after format(): {set(remaining_vars)}")
            
            return result
        except KeyError as e:
            logger.error(f"[SUBSTITUTE] Missing variable {e} in prompt template. Available vars: {list(template_vars.keys())}")
            logger.error(f"[SUBSTITUTE] Prompt text: {prompt_text[:500]}")
            return prompt_text
        except Exception as e:
            logger.error(f"[SUBSTITUTE] Error substituting variables in prompt: {e}", exc_info=True)
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
    
    def get_max_tokens(self, template_key: str, user_settings: Optional[Dict[str, Any]] = None) -> int:
        """Get max_tokens setting for a template
        
        Priority:
        1. User's llm_max_tokens setting (for scene generation types)
        2. YAML file defaults
        3. Hardcoded fallback (2048)
        
        Args:
            template_key: Template identifier (e.g., 'scene_generation')
            user_settings: Optional user settings dict with llm_settings.max_tokens
        
        Returns:
            Max tokens value to use for generation
        """
        # Check user settings first for scene generation types
        # NOTE: scene_variants removed - now uses scene_with/without_immediate
        scene_generation_types = {
            "scene_with_immediate", "scene_without_immediate", "scene", 
            "scene_continuation"
        }
        
        if user_settings and template_key in scene_generation_types:
            try:
                user_max_tokens = user_settings.get("llm_settings", {}).get("max_tokens")
                if user_max_tokens is not None and isinstance(user_max_tokens, int):
                    logger.info(f"Using user max_tokens setting: {user_max_tokens} for {template_key}")
                    return user_max_tokens
            except (KeyError, TypeError, AttributeError):
                pass
        
        # Fall back to YAML defaults
        if not self._prompts_cache:
            return 2048  # Default fallback
        
        try:
            # Map template keys to YAML function names for max_tokens lookup
            # NOTE: scene_variants removed - now uses scene_with/without_immediate (mapped to "scene")
            function_mapping = {
                "scene_with_immediate": "scene",
                "scene_without_immediate": "scene",
                "story_summary": "story_summary",
                "choice_generation": "choices",
                "title_generation": "titles",
                "scenario_generation": "scenario",
                "scene_continuation": "scene_continuation",
                "complete_plot": "complete_plot",
                "single_plot_point": "single_plot_point",
                "story_chapters": "story_chapters"
            }
            
            function_name = function_mapping.get(template_key, template_key)
            yaml_max_tokens = self._prompts_cache.get("settings", {}).get("max_tokens", {}).get(function_name)
            if yaml_max_tokens:
                logger.debug(f"Using YAML max_tokens setting: {yaml_max_tokens} for {template_key}")
                return yaml_max_tokens
            # Fallback to config.yaml service defaults
            from ...config import settings
            return settings.service_defaults.get('prompts', {}).get('default_max_tokens', 2048)
        except (KeyError, TypeError):
            from ...config import settings
            return settings.service_defaults.get('prompts', {}).get('default_max_tokens', 2048)
    
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
                "scene_with_immediate", "scene_without_immediate", "story_summary", 
                "choice_generation", "title_generation", "scenario_generation", 
                "scene_continuation", "scene_guided_enhancement",
                "complete_plot", "single_plot_point", "story_chapters",
                "chapter_conclusion", "character_assistant.extraction", 
                "character_assistant.detection", "character_assistant.generation"
                # NOTE: scene_variants removed - now uses scene_with/without_immediate
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
        logger.info(f"[GET_PROMPT_PAIR] Received template_vars keys: {list(template_vars.keys())}")
        
        system_prompt = self.get_prompt(
            template_key, 
            "system", 
            user_id=user_id, 
            db=db, 
            **template_vars
        )
        
        logger.info(f"[GET_PROMPT_PAIR] Calling get_prompt for user prompt with template_vars keys: {list(template_vars.keys())}")
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