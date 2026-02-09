"""
Prompt Generator for Image Generation

Uses LLM to convert scene content and character descriptions into
optimized image generation prompts for models like Flux.
"""

import logging
from typing import Optional, List, Dict, Any

from ..llm.service import UnifiedLLMService
from ..llm.prompts import PromptManager

logger = logging.getLogger(__name__)


class ImagePromptGenerator:
    """Generates optimized image prompts from story content using LLM.

    Routes to either the main LLM or extraction LLM based on user's
    `use_extraction_llm_for_image_prompts` setting.
    """

    def __init__(
        self,
        user_id: int,
        user_settings: Dict[str, Any],
        llm_service: UnifiedLLMService,
        prompt_manager: PromptManager,
    ):
        self.user_id = user_id
        self.user_settings = user_settings
        self.llm_service = llm_service
        self.prompt_manager = prompt_manager

        # Check user's preference for which LLM to use for image prompts
        img_settings = user_settings.get('image_generation_settings', {})
        self.use_extraction_llm = img_settings.get('use_extraction_llm_for_prompts', False)
        ext_settings = user_settings.get('extraction_model_settings', {})
        self.extraction_enabled = ext_settings.get('enabled', False)

    def _get_template(self, template_name: str) -> str:
        """Get an image prompt template directly from the YAML cache.

        The standard get_prompt() method expects system/user prompt pairs and
        uses a hardcoded yaml_mapping. Image prompt templates are flat text
        templates under 'image_prompt_generation', so we access the cache directly.
        """
        self.prompt_manager._check_reload()
        cache = self.prompt_manager._prompts_cache or {}
        template = cache.get("image_prompt_generation", {}).get(template_name, "")
        if isinstance(template, str):
            return template.strip()
        return ""

    async def _generate(self, prompt: str, max_tokens: int = 200) -> str:
        """Route generation to the appropriate LLM based on user settings.

        Same pattern as UnifiedLLMService.generate_summary() in service.py.
        """
        if self.use_extraction_llm and self.extraction_enabled:
            try:
                from ..llm.extraction_service import ExtractionLLMService

                ext = self.user_settings.get('extraction_model_settings', {})
                llm_settings = self.user_settings.get('llm_settings', {})
                timeout_total = llm_settings.get('timeout_total', 240)

                service = ExtractionLLMService(
                    url=ext.get('url', 'http://localhost:1234/v1'),
                    model=ext.get('model_name', 'qwen2.5-3b-instruct'),
                    api_key=ext.get('api_key', ''),
                    temperature=0.7,
                    max_tokens=max_tokens,
                    timeout_total=timeout_total,
                )
                logger.info(f"[IMAGE_PROMPT] Using extraction LLM for prompt generation")
                return await service.generate(prompt=prompt)
            except Exception as e:
                logger.warning(f"[IMAGE_PROMPT] Extraction LLM failed, falling back to main LLM: {e}")

        # Main LLM (default or fallback)
        logger.info(f"[IMAGE_PROMPT] Using main LLM for prompt generation")
        return await self.llm_service.generate(
            prompt=prompt,
            user_id=self.user_id,
            user_settings=self.user_settings,
            max_tokens=max_tokens,
            temperature=0.7,
        )

    def _clean_response(self, text: str) -> str:
        """Remove explanatory prefixes the LLM might add."""
        text = text.strip()
        # Remove "Prompt:" or "Image prompt:" type prefixes
        if ":" in text and len(text.split(":")[0]) < 20:
            text = ":".join(text.split(":")[1:]).strip()
        return text

    async def generate_portrait_prompt(
        self,
        character_name: str,
        appearance: str,
        style_preset: str = "illustrated",
        additional_context: Optional[str] = None
    ) -> str:
        """Generate an optimized portrait prompt from character appearance description."""
        try:
            template = self._get_template("portrait_from_appearance")

            if not template:
                logger.warning("Portrait prompt template not found, using fallback")
                return self._fallback_portrait_prompt(character_name, appearance, style_preset)

            prompt = template.format(
                character_name=character_name,
                appearance=appearance,
                style_preset=style_preset,
                additional_context=additional_context or ""
            )

            response = await self._generate(prompt, max_tokens=200)
            return self._clean_response(response)

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
        """Generate an optimized scene image prompt from scene content."""
        try:
            template = self._get_template("scene_to_image_prompt")

            if not template:
                logger.warning("Scene prompt template not found, using fallback")
                return self._fallback_scene_prompt(scene_content, characters, location, mood, style_preset)

            # Format character list with appearances
            characters_str = ", ".join([
                f"{c['name']} ({c.get('appearance', 'no description')})"
                for c in characters
            ]) if characters else "No specific characters"

            prompt = template.format(
                scene_content=scene_content[:1500],
                characters=characters_str,
                location=location or "unspecified",
                mood=mood or "neutral",
                style_preset=style_preset,
                chapter_context=chapter_context or ""
            )

            response = await self._generate(prompt, max_tokens=150)
            return self._clean_response(response)

        except Exception as e:
            logger.error(f"Error generating scene prompt: {e}")
            return self._fallback_scene_prompt(scene_content, characters, location, mood, style_preset)

    async def generate_character_in_context_prompt(
        self,
        character_name: str,
        base_appearance: str,
        current_state: Dict[str, Any],
        style_preset: str = "illustrated",
        scene_content: Optional[str] = None,
        character_background: Optional[str] = None,
    ) -> str:
        """Generate an image prompt for a character using LLM with few-shot examples.

        Sends all raw character data to the LLM along with examples of good prompts.
        The LLM handles ethnicity inference, gender, filtering measurements, etc.
        """
        try:
            template = self._get_template("character_in_context")

            if not template:
                logger.warning("Character prompt template not found, using fallback")
                return self._fallback_character_in_context_prompt(
                    character_name, base_appearance, current_state, style_preset)

            # Format items held
            items = current_state.get("items_in_hand")
            if isinstance(items, list):
                items_str = ", ".join(items)
            else:
                items_str = items or "nothing"

            # Map emotional_state to a simple facial expression keyword
            emotion_raw = current_state.get("emotional_state") or ""
            facial_expression = self._simplify_emotion(emotion_raw)

            # Truncate scene content for location/attire fallback
            scene_text_truncated = (scene_content[:500] + "...") if scene_content and len(scene_content) > 500 else (scene_content or "not provided")

            prompt = template.format(
                character_name=character_name,
                character_background=character_background or "not provided",
                base_appearance=base_appearance or "not provided",
                current_attire=current_state.get("appearance") or "not specified",
                facial_expression=facial_expression,
                position=current_state.get("current_position") or "not specified",
                location=current_state.get("current_location") or "not specified",
                items_held=items_str,
                scene_text=scene_text_truncated,
            )

            response = await self._generate(prompt, max_tokens=150)
            result = self._clean_response(response)
            logger.info(f"[IMAGE_PROMPT] Character prompt: {result[:200]}")
            return result

        except Exception as e:
            logger.error(f"Error generating character prompt: {e}")
            return self._fallback_character_in_context_prompt(
                character_name, base_appearance, current_state, style_preset)

    @staticmethod
    def _simplify_emotion(emotion: str) -> str:
        """Map complex emotional states to simple facial expression keywords for image generation."""
        if not emotion:
            return "neutral expression"
        emotion_lower = emotion.lower()
        # Map to simple, image-safe facial expressions
        mapping = {
            "happy": "smiling", "joy": "smiling", "excited": "smiling",
            "amused": "smiling", "pleased": "smiling", "delighted": "smiling",
            "sad": "somber expression", "grief": "somber expression",
            "melancholy": "somber expression", "sorrowful": "somber expression",
            "angry": "frowning", "furious": "frowning", "irritated": "frowning",
            "frustrated": "frowning", "annoyed": "frowning",
            "afraid": "wide-eyed", "scared": "wide-eyed", "terrified": "wide-eyed",
            "fearful": "wide-eyed", "panic": "wide-eyed",
            "surprised": "surprised expression", "shocked": "surprised expression",
            "astonished": "surprised expression",
            "nervous": "slight smile", "anxious": "pensive expression",
            "worried": "pensive expression", "uneasy": "pensive expression",
            "confident": "confident expression", "determined": "determined expression",
            "resolute": "determined expression",
            "calm": "calm expression", "serene": "calm expression",
            "peaceful": "calm expression", "relaxed": "relaxed expression",
            "thoughtful": "thoughtful expression", "pensive": "pensive expression",
            "contemplative": "thoughtful expression",
            "tired": "tired expression", "exhausted": "tired expression",
            "weary": "tired expression",
        }
        # Check each keyword against the emotion string
        for keyword, expression in mapping.items():
            if keyword in emotion_lower:
                return expression
        # Default: neutral
        return "neutral expression"

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
        parts = []

        if location:
            parts.append(location)

        if characters:
            char_names = [c['name'] for c in characters[:3]]
            parts.append(", ".join(char_names))

        if mood:
            parts.append(f"{mood} atmosphere")

        first_part = scene_content[:200].split('.')[0]
        if first_part:
            parts.append(first_part)

        style_suffix = self._get_style_suffix(style_preset)
        parts.append(style_suffix)

        return ", ".join(parts)

    def _fallback_character_in_context_prompt(
        self,
        character_name: str,
        base_appearance: str,
        current_state: Dict[str, Any],
        style_preset: str
    ) -> str:
        """Fallback character-in-context prompt without LLM"""
        location = current_state.get("current_location") or ""
        emotional_state = current_state.get("emotional_state") or ""
        style_suffix = self._get_style_suffix(style_preset)

        # Always use base appearance (from character card) as the foundation
        parts = [f"portrait of {character_name}", base_appearance]
        # Add state appearance changes on top if different from base
        state_appearance = current_state.get("appearance")
        if state_appearance and state_appearance != base_appearance:
            parts.append(state_appearance)
        if location:
            parts.append(f"in {location}")
        if emotional_state:
            parts.append(f"{emotional_state} expression")
        parts.append(style_suffix)
        return ", ".join(parts)

    def _get_style_suffix(self, style_preset: str) -> str:
        """Get style-specific prompt suffix for modern models (Flux, z-image)"""
        style_suffixes = {
            "illustrated": "in a digital illustration style with vibrant colors",
            "semi_realistic": "in a semi-realistic cinematic style",
            "anime": "in anime art style",
            "photorealistic": "photorealistic, natural lighting",
            "fantasy": "in a fantasy art style with dramatic lighting",
            "noir": "in film noir style, black and white, dramatic shadows",
        }
        return style_suffixes.get(style_preset, style_suffixes["illustrated"])

