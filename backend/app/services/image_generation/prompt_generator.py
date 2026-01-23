"""
Prompt Generator for Image Generation

Uses LLM to convert scene content and character descriptions into
optimized image generation prompts.
"""

import logging
from typing import Optional, List, Dict, Any

from ..llm.service import UnifiedLLMService
from ..llm.prompts import PromptManager

logger = logging.getLogger(__name__)


class ImagePromptGenerator:
    """Generates optimized image prompts from story content using LLM"""

    def __init__(
        self,
        llm_service: UnifiedLLMService,
        prompt_manager: PromptManager,
        use_extraction_llm: bool = False
    ):
        self.llm_service = llm_service
        self.prompt_manager = prompt_manager
        self.use_extraction_llm = use_extraction_llm

    async def generate_portrait_prompt(
        self,
        character_name: str,
        appearance: str,
        style_preset: str = "illustrated",
        additional_context: Optional[str] = None
    ) -> str:
        """
        Generate an optimized portrait prompt from character appearance description.

        Args:
            character_name: Name of the character
            appearance: Character's appearance description
            style_preset: Art style preset (illustrated, anime, photorealistic, etc.)
            additional_context: Optional additional context about the character

        Returns:
            Optimized image generation prompt
        """
        try:
            # Get the prompt template
            template = self.prompt_manager.get_prompt(
                "image_prompt_generation",
                "portrait_from_appearance"
            )

            if not template:
                # Fallback if template not found
                logger.warning("Portrait prompt template not found, using fallback")
                return self._fallback_portrait_prompt(character_name, appearance, style_preset)

            # Format the template
            prompt = template.format(
                character_name=character_name,
                appearance=appearance,
                style_preset=style_preset,
                additional_context=additional_context or ""
            )

            # Generate with LLM
            response = await self.llm_service.generate_simple(
                prompt=prompt,
                max_tokens=200,
                temperature=0.7,
                use_extraction_llm=self.use_extraction_llm
            )

            # Clean up the response
            generated_prompt = response.strip()

            # Remove any explanatory text the LLM might have added
            if ":" in generated_prompt and len(generated_prompt.split(":")[0]) < 20:
                generated_prompt = ":".join(generated_prompt.split(":")[1:]).strip()

            return generated_prompt

        except Exception as e:
            logger.error(f"Error generating portrait prompt: {e}")
            return self._fallback_portrait_prompt(character_name, appearance, style_preset)

    async def generate_scene_prompt(
        self,
        scene_content: str,
        characters: List[Dict[str, str]],
        location: Optional[str] = None,
        mood: Optional[str] = None,
        style_preset: str = "illustrated",
        chapter_context: Optional[str] = None
    ) -> str:
        """
        Generate an optimized scene image prompt from scene content.

        Args:
            scene_content: The text content of the scene
            characters: List of character dicts with 'name' and 'appearance'
            location: Scene location/setting
            mood: Emotional tone of the scene
            style_preset: Art style preset
            chapter_context: Optional broader chapter context

        Returns:
            Optimized image generation prompt
        """
        try:
            # Get the prompt template
            template = self.prompt_manager.get_prompt(
                "image_prompt_generation",
                "scene_to_image_prompt"
            )

            if not template:
                logger.warning("Scene prompt template not found, using fallback")
                return self._fallback_scene_prompt(scene_content, characters, location, mood, style_preset)

            # Format character list
            characters_str = ", ".join([
                f"{c['name']} ({c.get('appearance', 'no description')})"
                for c in characters
            ]) if characters else "No specific characters"

            # Format the template
            prompt = template.format(
                scene_content=scene_content[:1500],  # Limit length
                characters=characters_str,
                location=location or "unspecified",
                mood=mood or "neutral",
                style_preset=style_preset,
                chapter_context=chapter_context or ""
            )

            # Generate with LLM
            response = await self.llm_service.generate_simple(
                prompt=prompt,
                max_tokens=300,
                temperature=0.7,
                use_extraction_llm=self.use_extraction_llm
            )

            # Clean up the response
            generated_prompt = response.strip()

            # Remove any explanatory text
            if ":" in generated_prompt and len(generated_prompt.split(":")[0]) < 20:
                generated_prompt = ":".join(generated_prompt.split(":")[1:]).strip()

            return generated_prompt

        except Exception as e:
            logger.error(f"Error generating scene prompt: {e}")
            return self._fallback_scene_prompt(scene_content, characters, location, mood, style_preset)

    def _fallback_portrait_prompt(
        self,
        character_name: str,
        appearance: str,
        style_preset: str
    ) -> str:
        """Fallback portrait prompt without LLM"""
        style_suffix = self._get_style_suffix(style_preset)
        return f"portrait of {character_name}, {appearance}, {style_suffix}"

    def _fallback_scene_prompt(
        self,
        scene_content: str,
        characters: List[Dict[str, str]],
        location: Optional[str],
        mood: Optional[str],
        style_preset: str
    ) -> str:
        """Fallback scene prompt without LLM"""
        # Extract key visual elements from the scene
        parts = []

        if location:
            parts.append(location)

        if characters:
            char_names = [c['name'] for c in characters[:3]]  # Limit to 3 characters
            parts.append(", ".join(char_names))

        if mood:
            parts.append(f"{mood} atmosphere")

        # Take first sentence or two from scene for context
        first_part = scene_content[:200].split('.')[0]
        if first_part:
            parts.append(first_part)

        style_suffix = self._get_style_suffix(style_preset)
        parts.append(style_suffix)

        return ", ".join(parts)

    def _get_style_suffix(self, style_preset: str) -> str:
        """Get style-specific prompt suffix"""
        style_suffixes = {
            "illustrated": "digital art, illustration, vibrant colors",
            "semi_realistic": "semi-realistic, detailed, cinematic lighting",
            "anime": "anime style, detailed, masterpiece quality",
            "photorealistic": "photorealistic, detailed, 8k resolution",
            "fantasy": "fantasy art, magical, ethereal lighting",
            "noir": "noir style, high contrast, dramatic shadows",
        }
        return style_suffixes.get(style_preset, style_suffixes["illustrated"])
