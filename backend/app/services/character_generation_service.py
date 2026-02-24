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
                if story_context.get('world_description'):
                    context_parts.append(f"World Description: {story_context['world_description']}")
                if story_context.get('existing_characters'):
                    chars = story_context['existing_characters']
                    if isinstance(chars, list) and chars:
                        context_parts.append(f"Existing Characters in Story: {', '.join(chars)}")

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
    
    async def enrich_character(
        self,
        character_data: Dict[str, Any],
        story_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Fill in empty fields of an existing character profile using LLM.

        Args:
            character_data: Existing character fields from the Character model
            story_context: Optional story context (genre, tone, world_setting, description)

        Returns:
            Dictionary with only the newly filled fields
        """
        # Fields that can be enriched
        enrichable_fields = ['gender', 'background', 'goals', 'fears', 'appearance']

        # Identify which fields are empty
        empty_fields = []
        for field in enrichable_fields:
            value = character_data.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                empty_fields.append(field)

        # Always suggest voice style if not set
        has_voice_style = character_data.get('voice_style')
        if not has_voice_style:
            empty_fields.append('suggested_voice_style')

        if not empty_fields:
            logger.info("No empty fields to enrich")
            return {}

        # Build existing fields summary
        existing_parts = []
        if character_data.get('name'):
            existing_parts.append(f"Name: {character_data['name']}")
        if character_data.get('description'):
            existing_parts.append(f"Description: {character_data['description']}")
        if character_data.get('gender'):
            existing_parts.append(f"Gender: {character_data['gender']}")
        if character_data.get('personality_traits'):
            traits = character_data['personality_traits']
            if isinstance(traits, list):
                existing_parts.append(f"Personality Traits: {', '.join(traits)}")
        if character_data.get('background'):
            existing_parts.append(f"Background: {character_data['background']}")
        if character_data.get('goals'):
            existing_parts.append(f"Goals: {character_data['goals']}")
        if character_data.get('fears'):
            existing_parts.append(f"Fears: {character_data['fears']}")
        if character_data.get('appearance'):
            existing_parts.append(f"Appearance: {character_data['appearance']}")
        if character_data.get('voice_style'):
            vs = character_data['voice_style']
            if isinstance(vs, dict) and vs.get('preset'):
                existing_parts.append(f"Voice Style: {vs['preset']}")

        existing_fields_str = "\n".join(existing_parts)
        empty_fields_str = ", ".join(empty_fields)

        # Build story context string
        story_context_str = ""
        if story_context:
            context_parts = []
            if story_context.get('genre'):
                context_parts.append(f"Genre: {story_context['genre']}")
            if story_context.get('tone'):
                context_parts.append(f"Tone: {story_context['tone']}")
            if story_context.get('world_setting'):
                context_parts.append(f"World Setting: {story_context['world_setting']}")
            if story_context.get('description'):
                context_parts.append(f"Story Description: {story_context['description']}")
            if context_parts:
                story_context_str = "\n\nStory Context:\n" + "\n".join(context_parts)

        try:
            system_prompt = prompt_manager.get_prompt("character_assistant.enrichment", "system")
            user_prompt_template = prompt_manager.get_prompt("character_assistant.enrichment", "user")

            formatted_user_prompt = user_prompt_template.format(
                existing_fields=existing_fields_str,
                empty_fields=empty_fields_str,
                story_context=story_context_str
            )

            response = await self.llm_service.generate(
                prompt=formatted_user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=settings.service_defaults.get('character_generation', {}).get('max_tokens', 2000),
                temperature=settings.service_defaults.get('character_generation', {}).get('temperature', 0.8)
            )

            response_clean = clean_llm_json(response.strip())

            try:
                enriched_fields = json.loads(response_clean)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse enrichment JSON: {e}")
                raise ValueError(f"Failed to parse enrichment response: {str(e)}")

            # Only return fields that were actually empty
            result = {}
            for field in empty_fields:
                if field in enriched_fields and enriched_fields[field]:
                    value = enriched_fields[field]
                    if isinstance(value, str):
                        result[field] = value.strip()
                    else:
                        result[field] = value

            # Also pass through suggested_voice_style if present
            if 'suggested_voice_style' in enriched_fields and enriched_fields['suggested_voice_style']:
                result['suggested_voice_style'] = enriched_fields['suggested_voice_style']

            logger.info(f"Enriched {len(result)} fields: {list(result.keys())}")
            return result

        except Exception as e:
            logger.error(f"Failed to enrich character: {e}")
            raise ValueError(f"Failed to enrich character: {str(e)}")

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

