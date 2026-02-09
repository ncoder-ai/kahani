"""
Character Generation Service

Generates complete character profiles from freeform text descriptions using LLM.
"""

import logging
import json
import re
from typing import Dict, Any, Optional
from ..services.llm.service import UnifiedLLMService
from ..services.llm.prompts import prompt_manager
from ..config import settings

logger = logging.getLogger(__name__)


def clean_llm_json(json_str: str) -> str:
    """
    Clean common JSON errors from LLM responses.
    
    Common issues:
    - Trailing commas
    - Comments
    - Markdown code blocks
    """
    # Remove any leading/trailing whitespace
    json_str = json_str.strip()
    
    # If the response is very short or looks like a fragment, return empty dict
    if len(json_str) < 10 or json_str in ['"name"', '\n    "name"', 'name', '{}']:
        return '{}'
    
    # Remove markdown code blocks if present
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    json_str = json_str.strip()
    
    # Remove comments (// or /* */)
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    # Remove trailing commas before closing brackets/braces
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Don't try to fix unquoted values - let JSON parser handle it or fail
    # This preserves arrays which should already be properly formatted
    
    return json_str


class CharacterGenerationService:
    """
    Service for generating characters from freeform text descriptions.
    
    Responsibilities:
    - Parse user intent from natural language descriptions
    - Generate complete character profiles using LLM
    - Handle regeneration with variations
    - Validate and structure character data
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any]):
        self.user_id = user_id
        self.user_settings = user_settings
        self.llm_service = UnifiedLLMService()
    
    async def generate_character_from_prompt(
        self,
        user_prompt: str,
        story_context: Optional[Dict[str, Any]] = None,
        previous_generation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete character profile from freeform text description.
        
        Args:
            user_prompt: Freeform text description of the character
            story_context: Optional story context (genre, tone, world_setting)
            previous_generation: Optional previous generation for variation requests
            
        Returns:
            Dictionary with complete character details matching Character model structure
        """
        try:
            # Build story context string if provided
            story_context_str = ""
            if story_context:
                context_parts = []
                if story_context.get('genre'):
                    context_parts.append(f"Genre: {story_context['genre']}")
                if story_context.get('tone'):
                    context_parts.append(f"Tone: {story_context['tone']}")
                if story_context.get('world_setting'):
                    context_parts.append(f"World Setting: {story_context['world_setting']}")
                
                if context_parts:
                    story_context_str = "\n\nStory Context:\n" + "\n".join(context_parts)
            
            # Build regeneration instruction if applicable
            regeneration_instruction = ""
            if previous_generation:
                regeneration_instruction = "\n\nNote: Generate a different variation of this character while maintaining the core concept."
            
            # Get LLM prompts
            system_prompt = prompt_manager.get_prompt("character_assistant.generation", "system")
            user_prompt_template = prompt_manager.get_prompt("character_assistant.generation", "user")
            
            # Format user prompt with variables
            formatted_user_prompt = user_prompt_template.format(
                user_prompt=user_prompt,
                story_context=story_context_str,
                regeneration_instruction=regeneration_instruction
            )
            
            # Call LLM
            response = await self.llm_service.generate(
                prompt=formatted_user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=settings.service_defaults.get('character_generation', {}).get('max_tokens', 2000),
                temperature=settings.service_defaults.get('character_generation', {}).get('temperature', 0.8)
            )
            
            # Parse JSON response
            response_clean = response.strip()
            response_clean = clean_llm_json(response_clean)
            
            # Debug logging
            logger.debug(f"LLM response for character generation: {response_clean[:500]}...")
            
            try:
                character_details = json.loads(response_clean)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse cleaned JSON: {e}")
                logger.error(f"Cleaned JSON: {response_clean[:1000]}")
                raise ValueError(f"Failed to parse JSON response: {str(e)}")
            
            # Log personality traits before validation
            logger.info(f"Raw personality_traits from LLM: {character_details.get('personality_traits')}")
            logger.info(f"Type of personality_traits: {type(character_details.get('personality_traits'))}")
            
            # Validate and normalize the response
            character_details = self._validate_character_data(character_details)
            
            # Log after validation
            logger.info(f"Normalized personality_traits: {character_details.get('personality_traits')}")
            logger.info(f"Number of traits: {len(character_details.get('personality_traits', []))}")
            
            # Ensure we have at least some traits - if empty, try to extract from description
            if not character_details.get('personality_traits') or len(character_details.get('personality_traits', [])) == 0:
                logger.warning("No personality traits found, attempting to extract from description")
                # This is a fallback - ideally the LLM should provide traits
                character_details['personality_traits'] = []
            
            return character_details
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.error(f"Raw response: {response_clean[:500] if 'response_clean' in locals() else 'No response'}")
            raise ValueError(f"Failed to parse character generation response: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to generate character: {e}")
            logger.error(f"Raw response: {response_clean[:500] if 'response_clean' in locals() else 'No response'}")
            raise ValueError(f"Failed to generate character: {str(e)}")
    
    def _validate_character_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize character data from LLM response.
        
        Ensures all required fields are present with appropriate defaults.
        Handles both structured (object) and plain text formats.
        """
        validated = {
            'name': data.get('name', '').strip(),
            'description': data.get('description', '').strip() or '',
            'personality_traits': self._normalize_traits(data.get('personality_traits', [])),
            'background': self._format_structured_field(data.get('background', '')),
            'goals': self._format_structured_field(data.get('goals', '')),
            'fears': self._format_structured_field(data.get('fears', '')),
            'appearance': self._format_structured_field(data.get('appearance', '')),
            # Store structured data separately for frontend display
            'background_structured': data.get('background') if isinstance(data.get('background'), dict) else None,
            'goals_structured': data.get('goals') if isinstance(data.get('goals'), dict) else None,
            'fears_structured': data.get('fears') if isinstance(data.get('fears'), dict) else None,
            'appearance_structured': data.get('appearance') if isinstance(data.get('appearance'), dict) else None,
            # AI-suggested voice style preset
            'suggested_voice_style': data.get('suggested_voice_style', 'neutral'),
        }
        
        # Ensure name is present (required field)
        if not validated['name']:
            # Try to extract name from description if not provided
            if validated['description']:
                # Simple heuristic: first few words might be the name
                words = validated['description'].split()[:3]
                validated['name'] = ' '.join(words)
            else:
                validated['name'] = 'Unnamed Character'
        
        return validated
    
    def _format_structured_field(self, field_data: Any) -> str:
        """Convert structured field (dict) to formatted string or return plain text."""
        if isinstance(field_data, dict):
            # Format as bullet points
            formatted_items = []
            for key, value in field_data.items():
                if value and str(value).strip():
                    # Capitalize first letter of key and format as bullet
                    formatted_key = key.replace('_', ' ').title()
                    formatted_items.append(f"• {formatted_key}: {value}")
            return '\n'.join(formatted_items) if formatted_items else ''
        elif isinstance(field_data, str):
            return field_data.strip() or ''
        else:
            return ''
    
    def _normalize_traits(self, traits: Any) -> list:
        """Normalize personality traits to a list of strings."""
        logger.debug(f"Normalizing traits, input type: {type(traits)}, value: {traits}")
        
        if traits is None:
            logger.warning("personality_traits is None, returning empty list")
            return []
        
        if isinstance(traits, list):
            normalized = [str(t).strip() for t in traits if str(t).strip()]
            logger.debug(f"Normalized from list: {normalized}")
            return normalized
        elif isinstance(traits, str):
            # Try to parse comma-separated or newline-separated traits
            normalized = [t.strip() for t in re.split(r'[,;\n]', traits) if t.strip()]
            logger.debug(f"Normalized from string: {normalized}")
            return normalized
        else:
            logger.warning(f"Unexpected traits type: {type(traits)}, value: {traits}")
            return []

