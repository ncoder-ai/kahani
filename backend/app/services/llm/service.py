"""
Unified LLM Service

Provides a clean, unified interface for all LLM operations using LiteLLM
and centralized prompt management. Also handles scene variant database operations.
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List, Tuple
import litellm
from litellm import acompletion
import logging
import re
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import httpx
import time
import uuid

from .client import LLMClient
from .prompts import prompt_manager
from .thinking_parser import ThinkingTagParser
from .content_cleaner import (
    clean_scene_content,
    clean_scene_numbers,
    clean_instruction_tags,
    clean_scene_numbers_chunk,
    clean_scene_numbers_from_summary,
)
from .choice_parser import (
    fix_incomplete_json_array,
    fix_malformed_json_escaping,
    fix_single_quotes_to_double,
    extract_choices_with_regex,
    parse_choices_from_json,
    extract_choices_from_response_end,
    detect_json_array_in_prose,
)
from .plot_parser import (
    get_plot_point_name,
    clean_plot_point,
    parse_plot_points_json,
    parse_plot_points,
    detect_pov,
    PLOT_POINT_NAMES,
)
from .context_formatter import (
    get_scene_length_description,
    format_context_for_titles,
    format_context_for_continuation,
    format_context_for_scenario,
    format_elements_for_scenario,
    format_context_for_plot,
    format_context_for_chapters,
    format_context_for_summary,
    format_characters_section,
    format_character_voice_styles,
    batch_scenes_as_messages,
)
from .scene_database_operations import SceneDatabaseOperations
from .llm_generation_core import LLMGenerationCore
from .multi_variant_generation import MultiVariantGeneration
from ...config import settings

# Import for type hints (will be imported within functions to avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models import Scene, SceneVariant

logger = logging.getLogger(__name__)

class UnifiedLLMService:
    """
    Unified LLM Service using LiteLLM
    
    Features:
    - Multi-provider support through LiteLLM
    - Centralized prompt management
    - User configuration caching
    - Both streaming and non-streaming operations
    - Comprehensive error handling
    """
    
    def __init__(self):
        self._client_cache: Dict[int, LLMClient] = {}
        self._scene_db_ops = SceneDatabaseOperations()
        self._generation_core = LLMGenerationCore(self)
        self._multi_variant = MultiVariantGeneration(self)
    
    def get_user_client(self, user_id: int, user_settings: Dict[str, Any]) -> LLMClient:
        """Get or create LLM client configuration for user"""
        # Always recreate client from user_settings to ensure we have latest settings
        try:
            client = LLMClient(user_settings)
            # Update cache with new client
            self._client_cache[user_id] = client
            logger.info(f"Created/updated LLM client for user {user_id} with provider {client.api_type}")
        except Exception as e:
            logger.error(f"Failed to create LLM client for user {user_id}: {e}")
            raise
        
        # Ensure the global LiteLLM configuration is set correctly for this user
        client._configure_litellm()
        
        return client
    
    async def validate_user_connection(self, user_id: int, user_settings: Dict[str, Any]) -> tuple[bool, str]:
        """Validate user's LLM connection and return detailed error info"""
        try:
            client = self.get_user_client(user_id, user_settings)
            return await client.test_connection()
        except Exception as e:
            return False, f"Failed to create client: {str(e)}"
    
    def invalidate_user_client(self, user_id: int):
        """Invalidate cached client when user updates settings"""
        if user_id in self._client_cache:
            del self._client_cache[user_id]
            logger.info(f"Invalidated LLM client cache for user {user_id}")
    
    def _get_prompt_debug_path(self, filename: str) -> str:
        """Get the path for prompt debug files, handling both Docker and bare-metal environments.
        
        Args:
            filename: Name of the debug file (e.g., 'prompt_sent.json', 'prompt_choice_sent.json')
        
        Returns:
            Full path to the debug file
        """
        # Check if we're in Docker (working directory is /app)
        if os.path.exists("/app") and os.getcwd().startswith("/app"):
            # Docker: use mounted logs directory
            return f"/app/root_logs/{filename}"
        else:
            # Bare-metal: use logs directory relative to project root
            # Go up from service.py: backend/app/services/llm/service.py 
            # -> backend/app/services/llm -> backend/app/services -> backend/app -> backend -> project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
            logs_dir = os.path.join(project_root, "logs")
            os.makedirs(logs_dir, exist_ok=True)  # Ensure directory exists
            return os.path.join(logs_dir, filename)

    async def generate_for_task(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        max_tokens: Optional[int] = None,
        task_type: str = "main",
        force_main_llm: bool = False,
        allow_thinking: Optional[bool] = None,
    ) -> str:
        """Single routing function for all LLM generation.

        task_type:
            "main"       - Main LLM with user's normal settings
            "extraction"  - Extraction LLM if enabled, else main LLM with extraction settings
            "agent"       - Same routing as extraction

        force_main_llm:
            When True, skip extraction LLM even if available (still uses extraction
            settings like low temperature). Used by callers with per-task overrides
            like use_main_llm_for_plot_extraction.

        allow_thinking:
            Controls whether the LLM can use chain-of-thought reasoning.
            None (default) = auto-resolve from user settings:
              - "extraction" tasks → thinking_enabled_extractions (default False)
              - "agent" tasks → thinking_enabled_memory (default True)
            True/False = explicit override.

        When falling back to main LLM for extraction/agent tasks, uses temperature
        and reasoning settings from service_defaults.extraction_service in config.

        For extraction/agent tasks, thinking tags (<think>...</think> etc.) are
        automatically stripped from responses so callers always get clean output.
        """
        if task_type in ("extraction", "agent"):
            # Auto-resolve allow_thinking from per-task user settings if not explicitly set
            if allow_thinking is None:
                ext_settings = user_settings.get('extraction_model_settings', {})
                if task_type == "agent":
                    allow_thinking = ext_settings.get('thinking_enabled_memory', True)
                else:
                    allow_thinking = ext_settings.get('thinking_enabled_extractions', False)

            if not force_main_llm:
                extraction_service = self._get_extraction_service(user_settings)
                if extraction_service:
                    response = await extraction_service.generate_with_messages(messages, max_tokens, allow_thinking=allow_thinking)
                    return self._strip_thinking_from_response(response)

            # Main LLM with extraction-appropriate settings from config
            import copy
            from ...config import settings as app_settings
            ext_defaults = app_settings.service_defaults.get("extraction_service", {})
            fallback_settings = copy.deepcopy(user_settings)
            fallback_settings.setdefault('llm_settings', {})['temperature'] = ext_defaults.get("default_temperature", 0.3)
            if not allow_thinking:
                fallback_settings['llm_settings']['reasoning_effort'] = 'disabled'
            response = await self._generate_with_messages(
                messages=messages,
                user_id=user_id,
                user_settings=fallback_settings,
                max_tokens=max_tokens,
                skip_nsfw_filter=True,
            )
            return self._strip_thinking_from_response(response)

        # Default: main LLM with user's normal settings
        return await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _strip_thinking_from_response(response: str) -> str:
        """Strip thinking/reasoning tags from extraction/agent LLM responses.

        Uses the centralized ThinkingTagParser which handles all known formats
        (<think>, <thinking>, <reasoning>, [THINKING], etc.).
        """
        if not response:
            return response
        from .thinking_parser import strip_thinking_tags
        return strip_thinking_tags(response)

    @staticmethod
    def _will_use_extraction_llm(user_settings: Dict[str, Any], force_main_llm: Optional[bool] = None) -> bool:
        """Check if an extraction/summary call will route to the extraction LLM.

        Returns True when the extraction model is enabled AND force_main_llm is not True.
        """
        if force_main_llm is True:
            return False
        ext_settings = user_settings.get('extraction_model_settings', {})
        return bool(ext_settings.get('enabled', False))

    @staticmethod
    def _build_simple_extraction_messages(system_instruction: str, task_instruction: str) -> List[Dict[str, str]]:
        """Build a minimal 2-message prompt for extraction/summary tasks.

        Used when the extraction LLM is targeted (no KV cache benefit from the
        full scene-generation prefix) or when the user has disabled cache-friendly
        prompts (to save tokens on cloud providers).
        """
        return [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": task_instruction},
        ]

    def _format_plot_for_choices(self, context: Dict[str, Any], user_settings: Optional[Dict[str, Any]] = None) -> str:
        """
        Format chapter plot info for inclusion in choices reminder.

        This provides plot guidance ONLY to choice generation, not scene generation.
        Keeps scenes focused on user directives while choices can steer toward plot.

        Args:
            context: Scene generation context containing chapter_plot, plot_progress, and pacing_guidance
            user_settings: User settings dict containing default_plot_check_mode

        Returns:
            Formatted string for {chapter_plot_for_choices} placeholder, or empty string
        """
        parts = []

        # Get plot_check_mode from user settings (controls how many events to show)
        # "1" = show only next event, "3" = show up to 3, "all" = show all
        plot_check_mode = "1"  # Default to showing just next event
        if user_settings:
            plot_check_mode = user_settings.get("generation_preferences", {}).get("default_plot_check_mode", "1")

        # Get completed events from plot_progress to filter them out
        plot_progress = context.get("plot_progress") or {}
        completed_events = set(plot_progress.get("completed_events", []))

        chapter_plot = context.get("chapter_plot")
        if chapter_plot:
            if chapter_plot.get("key_events"):
                events = chapter_plot["key_events"]
                if isinstance(events, list) and events:
                    # Filter out already completed events
                    remaining_events = [e for e in events if e not in completed_events]

                    if remaining_events:
                        # Limit events based on plot_check_mode setting
                        if plot_check_mode == "1":
                            events_to_show = remaining_events[:1]
                        elif plot_check_mode == "3":
                            events_to_show = remaining_events[:3]
                        else:  # "all"
                            events_to_show = remaining_events

                        if events_to_show:
                            events_str = "; ".join(events_to_show)
                            parts.append(f"Upcoming story beats: {events_str}")
                    else:
                        # All key_events completed - show climax OR resolution (not both)
                        climax_reached = plot_progress.get("climax_reached", False)
                        logger.info(f"[PLOT_FOR_CHOICES] All key_events completed, climax_reached={climax_reached}")
                        if not climax_reached and chapter_plot.get("climax"):
                            # Climax not yet reached - guide toward it
                            parts.append(f"Next beat (climax): {chapter_plot['climax']}")
                        elif climax_reached and chapter_plot.get("resolution"):
                            # Climax done, guide toward resolution
                            parts.append(f"Next beat (resolution): {chapter_plot['resolution']}")

        if parts:
            return "CHAPTER DIRECTION (for choices): " + " | ".join(parts)
        return ""

    async def _build_cache_friendly_message_prefix(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> List[Dict[str, str]]:
        """
        Build the common message prefix for all LLM operations.

        Returns: [system_message, ...context_messages]

        All callers should:
        1. Call this method to get the prefix
        2. Append their specific final message
        3. Send to LLM

        This ensures 100% cache hit rate on the prefix across:
        - Scene generation
        - Variant generation
        - Continuation generation
        - Choice generation
        - All extraction operations
        - Memory operations
        """
        # Short-circuit: if a saved prompt prefix exists (from original scene gen),
        # return it directly. This guarantees byte-identical prefix for variant gen.
        saved_prefix = context.get("_saved_prompt_prefix")
        if saved_prefix:
            logger.info(f"[PREFIX] Using saved prompt prefix ({len(saved_prefix)} messages)")
            return saved_prefix

        # 1. Get user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)

        # 2. Get POV from writing preset
        pov = 'third'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov

        # 3. Build system prompt with CONSISTENT skip_choices setting
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation  # ALWAYS use user setting!
        )
        logger.info(f"[PREFIX] Built system prompt: length={len(system_prompt)}")

        # 4. ALWAYS add POV reminder for cache consistency
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder

        # 4.5. Inject content permission (uncensored or family-friendly) into system prompt
        from ...utils.content_filter import get_content_permission_prompt
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        system_prompt += "\n\n" + get_content_permission_prompt(user_allow_nsfw)

        # 5. Build messages array
        messages = [{"role": "system", "content": system_prompt.strip()}]

        # 6. Add context messages
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)

        # Try to improve semantic scenes with query decomposition + RRF.
        # Internal gates handle skipping: _semantic_improved flag (already ran this cycle),
        # no user_intent (extraction/summary contexts), no db, no extraction service.
        await self._maybe_improve_semantic_scenes(messages, context, user_settings, db, user_id=user_id)
        # Mark as done regardless of success/failure — scene gen's result is the source of truth.
        # Prevents choices from re-running improvement with potentially different results.
        context["_semantic_improved"] = True

        return messages

    def _build_scene_task_message(
        self,
        context: Dict[str, Any],
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        include_choices_reminder: bool = True
    ) -> str:
        """
        Build the task message for new scene generation.

        This is the final message in the multi-message structure that varies per request.
        The prefix (system + context) is built by _build_cache_friendly_message_prefix().

        Args:
            context: Scene generation context
            user_settings: User settings dict
            db: Database session for preset lookups
            include_choices_reminder: Whether to append choices reminder (False for separate choice generation)

        Returns:
            Task message content string
        """
        # Get prose_style from writing preset
        prose_style = 'balanced'
        user_id = context.get('user_id')
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style

        # Get settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)

        # Get immediate_situation from context
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        has_immediate = bool(immediate_situation and immediate_situation.strip())

        # Get task instruction
        tone = context.get('tone', '')
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )

        # Append choices reminder if needed (with plot guidance for choices only)
        if include_choices_reminder:
            chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
            choices_reminder = prompt_manager.get_user_choices_reminder(
                choices_count=choices_count,
                chapter_plot_for_choices=chapter_plot_for_choices
            )
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder

        return task_content

    def _build_variant_task_message(
        self,
        context: Dict[str, Any],
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        original_scene: str = "",
        include_choices_reminder: bool = True
    ) -> str:
        """
        Build the task message for variant generation.

        For guided enhancement (has enhancement_guidance), uses enhancement task.
        For simple variant, uses same task as scene generation.

        Args:
            context: Scene generation context
            user_settings: User settings dict
            db: Database session for preset lookups
            original_scene: Original scene content (for guided enhancement)
            include_choices_reminder: Whether to append choices reminder

        Returns:
            Task message content string
        """
        # Get prose_style from writing preset
        prose_style = 'balanced'
        user_id = context.get('user_id')
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style

        # Get settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)

        # Check if this is guided enhancement
        enhancement_guidance = context.get("enhancement_guidance", "")
        tone = context.get('tone', '')

        if enhancement_guidance:
            # Guided enhancement: use task_guided_enhancement from prompts.yml
            # Get plot guidance for choices (upcoming story beats)
            chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings) if include_choices_reminder else ""
            task_content = prompt_manager.get_enhancement_task_instruction(
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                prose_style=prose_style,
                tone=tone,
                skip_choices_reminder=not include_choices_reminder,
                chapter_plot_for_choices=chapter_plot_for_choices
            )
        else:
            # Simple variant: use same task instruction as scene generation
            immediate_situation = context.get("current_situation") or ""
            immediate_situation = str(immediate_situation) if immediate_situation else ""
            has_immediate = bool(immediate_situation and immediate_situation.strip())

            task_content = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )

            # Append choices reminder if needed (with plot guidance for choices only)
            if include_choices_reminder:
                chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
                choices_reminder = prompt_manager.get_user_choices_reminder(
                    choices_count=choices_count,
                    chapter_plot_for_choices=chapter_plot_for_choices
                )
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder

        return task_content

    def _build_continuation_task_message(
        self,
        context: Dict[str, Any],
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        include_choices_reminder: bool = True
    ) -> str:
        """
        Build the task message for scene continuation.

        Args:
            context: Continuation context with current_scene_content and continuation_prompt
            user_settings: User settings dict
            db: Database session for preset lookups
            include_choices_reminder: Whether to append choices reminder

        Returns:
            Task message content string
        """
        # Get prose_style from writing preset
        prose_style = 'balanced'
        user_id = context.get('user_id')
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style

        # Get settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_map = {"short": "short (50-100 words)", "medium": "medium (100-150 words)", "long": "long (150-250 words)"}
        scene_length_description = scene_length_map.get(scene_length, "medium (100-150 words)")

        # Get current scene content and continuation prompt
        current_scene_content = context.get("current_scene_content", "") or context.get("current_content", "")
        continuation_prompt = context.get("continuation_prompt", "Continue this scene with more details and development.")

        # Clean scene content
        cleaned_scene_content = self._clean_instruction_tags(current_scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)

        # Get prose style and tone reminders
        prose_style_reminder = prompt_manager.get_prose_style_reminder(prose_style)
        tone = context.get('tone', '')
        tone_reminder = prompt_manager.get_tone_reminder(tone)

        # Build choices reminder if needed (with plot guidance for choices only)
        if include_choices_reminder:
            chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
            choices_reminder_text = prompt_manager.get_user_choices_reminder(
                choices_count=choices_count,
                chapter_plot_for_choices=chapter_plot_for_choices
            )
        else:
            choices_reminder_text = ""

        # Build the continuation task message
        task_content = f"""=== CURRENT SCENE TO CONTINUE ===
{cleaned_scene_content}

=== CONTINUATION INSTRUCTION ===
{continuation_prompt}

Write a compelling continuation that follows naturally from the scene above.
Focus on engaging narrative and dialogue. Do not repeat previous content.
Write approximately {scene_length_description} in length.

{prose_style_reminder}
{tone_reminder}

{choices_reminder_text}"""

        return task_content

    def _build_concluding_task_message(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> str:
        """
        Build the task message for chapter-concluding scene.

        Args:
            context: Scene generation context
            chapter_info: Chapter information (chapter_number, title, etc.)
            user_settings: User settings dict
            db: Database session for preset lookups

        Returns:
            Task message content string (no choices - concluding scenes don't have choices)
        """
        # Get prose_style from writing preset
        prose_style = 'balanced'
        user_id = context.get('user_id')
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style

        # Get settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        scene_length_description = self._get_scene_length_description(scene_length)

        # Get chapter info
        chapter_number = chapter_info.get("chapter_number", 1)

        # Get prose style and tone reminders
        prose_style_reminder = prompt_manager.get_prose_style_reminder(prose_style)
        tone = context.get('tone', '')
        tone_reminder = prompt_manager.get_tone_reminder(tone)

        # Build the concluding task message
        task_content = f"""=== CHAPTER CONCLUSION INSTRUCTION ===

Write a compelling conclusion for Chapter {chapter_number} that:
1. Brings this chapter to a natural and satisfying end
2. Provides closure for the chapter's events while leaving the overall story open
3. Sets up anticipation for what might come next
4. Ends at a natural chapter break point

Write approximately {scene_length_description} in length.
Write ONLY narrative content. Do not include any choices, options, or questions for the reader.

{prose_style_reminder}
{tone_reminder}

Chapter Conclusion:"""

        return task_content

    def _parse_choices_from_response(self, response: str) -> Tuple[str, Optional[List[str]]]:
        """
        Parse ###CHOICES### marker from complete response.

        Args:
            response: Complete LLM response text

        Returns:
            Tuple of (scene_content, choices_list or None if no marker found)
        """
        CHOICES_MARKER = "###CHOICES###"
        if CHOICES_MARKER in response:
            parts = response.split(CHOICES_MARKER, 1)
            scene_content = parts[0].strip()
            choices_text = parts[1].strip() if len(parts) > 1 else ""
            choices = self._parse_choices_from_json(choices_text)
            if choices:
                logger.info(f"[CHOICES] Successfully parsed {len(choices)} choices from response")
            else:
                logger.warning(f"[CHOICES] Marker found but parsing failed. Choices text: {choices_text[:200]}")
            return scene_content, choices
        else:
            # No marker found - try post-processing extraction
            scene_content, extracted_choices = self._extract_choices_from_response_end(response)
            if extracted_choices:
                logger.info(f"[CHOICES] Post-processing extracted {len(extracted_choices)} choices from response end")
                return scene_content, extracted_choices
            return response.strip(), None

    async def generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False,
        skip_nsfw_filter: bool = False
    ) -> str:
        """Generic text generation with streaming toggle"""
        if stream:
            # For streaming, collect all chunks and return complete text
            complete_text = ""
            async for chunk in self._generate_stream(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                skip_nsfw_filter=skip_nsfw_filter
            ):
                complete_text += chunk
            return complete_text
        else:
            return await self._generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                skip_nsfw_filter=skip_nsfw_filter
            )
    
    # Remove redundant generate_stream method - use _generate_stream directly
    
    def _log_raw_response(self, response: Any, operation_name: str = "LLM Generation") -> None:
        """
        Log full raw LLM response object to file (only for scene generation debugging)
        
        Args:
            response: The LLM response object
            operation_name: Name of the operation (for logging context)
        """
        if not settings.prompt_debug:
            return
        
        try:
            import json
            backend_dir = Path(__file__).parent.parent.parent
            raw_response_file = backend_dir / "Raw-Response.txt"
            with open(raw_response_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"RAW LLM RESPONSE OBJECT (FULL - BEFORE PARSING)\n")
                f.write(f"Operation: {operation_name}\n")
                f.write("=" * 80 + "\n\n")
                # Convert response object to dict for JSON serialization
                response_dict = {
                    "id": getattr(response, 'id', None),
                    "model": getattr(response, 'model', None),
                    "created": getattr(response, 'created', None),
                    "object": getattr(response, 'object', None),
                    "choices": [
                        {
                            "index": getattr(choice, 'index', None),
                            "message": {
                                "role": getattr(choice.message, 'role', None) if hasattr(choice, 'message') else None,
                                "content": getattr(choice.message, 'content', None) if hasattr(choice, 'message') else None,
                            } if hasattr(choice, 'message') else None,
                            "finish_reason": getattr(choice, 'finish_reason', None),
                        }
                        for choice in getattr(response, 'choices', [])
                    ],
                    "usage": {
                        "prompt_tokens": getattr(response.usage, 'prompt_tokens', None) if hasattr(response, 'usage') else None,
                        "completion_tokens": getattr(response.usage, 'completion_tokens', None) if hasattr(response, 'usage') else None,
                        "total_tokens": getattr(response.usage, 'total_tokens', None) if hasattr(response, 'usage') else None,
                    } if hasattr(response, 'usage') else None,
                }
                f.write(json.dumps(response_dict, indent=2, ensure_ascii=False))
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("PARSED CONTENT (what we extract):\n")
                f.write("=" * 80 + "\n\n")
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    f.write(content)
                f.write("\n\n" + "=" * 80 + "\n")
        except Exception as e:
            logger.error(f"Failed to write full raw response to file: {e}")
    
    async def _generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> str:
        """Internal method for non-streaming generation.

        Wrapper for LLMGenerationCore.generate.
        """
        return await self._generation_core.generate(
            prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
        )
    
    async def _generate_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming generation.

        Wrapper for LLMGenerationCore.generate_stream.
        """
        async for chunk in self._generation_core.generate_stream(
            prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
        ):
            yield chunk

    def _clean_scene_content(self, content: str) -> str:
        """
        Comprehensive cleaning of LLM-generated scene content.
        Delegates to content_cleaner module.
        """
        return clean_scene_content(content)

    def _clean_scene_numbers(self, content: str) -> str:
        """
        Remove scene numbers and LLM junk from generated content.
        Delegates to content_cleaner module.
        """
        return clean_scene_numbers(content)

    def _clean_instruction_tags(self, content: str) -> str:
        """Remove instruction tags. Delegates to content_cleaner module."""
        return clean_instruction_tags(content)

    def _clean_scene_numbers_chunk(self, chunk: str, chars_processed: int = 0) -> str:
        """
        Clean scene numbers and junk from streaming chunks.
        Delegates to content_cleaner module.
        """
        return clean_scene_numbers_chunk(chunk, chars_processed)
    
    # Story Generation Functions
    
    async def generate_story_title(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
        """Generate creative story titles based on story content"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "title_generation", "title_generation",
            context=self._format_context_for_titles(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("titles", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse titles from response
        titles = [title.strip() for title in response.split('\n') if title.strip()]
        
        # Clean up titles
        cleaned_titles = []
        for title in titles:
            cleaned_title = title.strip()
            # Remove common prefixes like "1.", "•", "-", etc.
            cleaned_title = re.sub(r'^[\d\.\-\*\•]\s*', '', cleaned_title)
            # Remove quotes if they wrap the entire title
            if cleaned_title.startswith('"') and cleaned_title.endswith('"'):
                cleaned_title = cleaned_title[1:-1]
            if cleaned_title.startswith("'") and cleaned_title.endswith("'"):
                cleaned_title = cleaned_title[1:-1]
            
            if cleaned_title and len(cleaned_title.split()) <= 8:  # Reasonable title length
                cleaned_titles.append(cleaned_title.strip())
        
        # Ensure we have exactly 5 titles
        if len(cleaned_titles) < 5:
            fallback_titles = [
                "The Journey Begins",
                "Shadows and Light", 
                "Destiny Calls",
                "The Final Choice",
                "Beyond the Horizon"
            ]
            cleaned_titles.extend(fallback_titles[:5-len(cleaned_titles)])
        
        return cleaned_titles[:5]
    
    async def generate_story_chapters(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], chapter_count: int = 5) -> List[str]:
        """Generate a chapter structure for a story"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_chapters", "story_chapters",
            context=self._format_context_for_chapters(context),
            chapter_count=chapter_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_chapters", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse chapters from response
        chapters = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for numbered chapters
            if re.match(r'^[\d\.\-\*]\s*', line):
                # Clean the chapter text
                chapter_text = re.sub(r'^[\d\.\-\*]\s*', '', line).strip()
                if chapter_text and len(chapter_text) > 10:  # Ensure substantial content
                    chapters.append(chapter_text)
        
        # Ensure we have the requested number of chapters
        if len(chapters) < chapter_count:
            fallback_chapters = [
                f"Chapter {i+1}: The story begins to unfold with new challenges and opportunities."
                for i in range(len(chapters), chapter_count)
            ]
            chapters.extend(fallback_chapters)
        
        return chapters[:chapter_count]
    
    async def generate_scene(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> str:
        """
        Generate a story scene using multi-message structure for better cache utilization.
        
        The context is split into multiple user messages to maximize LLM cache hits:
        - Story Foundation (stable per story)
        - Chapter Context (stable per chapter)
        - Entity States (changes every N scenes)
        - Story Progress + Task (changes every scene)
        """
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get prose_style from writing preset (default to balanced)
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Extract immediate_situation from context for template variable
        # This should contain the continuation option text when a choice is made
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE GENERATION] Using scene_with_immediate template (has immediate_situation)")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE GENERATION] Using scene_without_immediate template (no immediate_situation)")
        
        # Get system prompt from template (user prompt will be built from multi-message structure)
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        client = self.get_user_client(user_id, user_settings)

        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        # Use cache-friendly helper for consistent message prefix
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction using helper (no choices for this method)
        task_content = self._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=False
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[SCENE GENERATION] Using multi-message structure: {len(messages)} messages")

        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, None)
        gen_params["messages"] = messages
        
        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value
        
        # Call LLM and get full response object
        response = await acompletion(**gen_params)
        
        # Log raw response for scene generation debugging
        self._log_raw_response(response, "New Scene Generation (Multi-Message)")
        
        # Extract content
        response_text = response.choices[0].message.content
        
        return self._clean_scene_numbers(response_text)
    
    async def generate_scene_with_choices(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> Tuple[str, Optional[List[str]]]:
        """
        Generate scene content and choices in a single non-streaming call.
        Uses multi-message structure for better cache utilization.
        Returns (scene_content, parsed_choices)
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get scene length, choices count, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Get prose_style from writing preset (default to balanced)
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE WITH CHOICES] Using scene_with_immediate template (has immediate_situation)")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE WITH CHOICES] Using scene_without_immediate template (no immediate_situation)")
        
        # Get system prompt from template
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        logger.info(f"[SCENE WITH CHOICES] Using max_tokens: {max_tokens}")

        client = self.get_user_client(user_id, user_settings)

        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        # Use cache-friendly helper for consistent message prefix
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction using helper
        task_content = self._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=not separate_choice_generation
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[SCENE WITH CHOICES] Using multi-message structure: {len(messages)} messages")

        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, None)
        gen_params["messages"] = messages

        # Get timeout from user settings or fallback to system default
        user_timeout = None
        if user_settings:
            llm_settings = user_settings.get('llm_settings', {})
            user_timeout = llm_settings.get('timeout_total')
        timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
        gen_params["timeout"] = timeout_value

        # Call LLM and get full response object
        response = await acompletion(**gen_params)

        # Log raw response for scene generation debugging
        self._log_raw_response(response, "New Scene Generation with Choices (Multi-Message)")

        # Extract content
        response_text = response.choices[0].message.content

        # Print raw LLM response to console for scene generation with choices
        logger.info("=" * 80)
        logger.info("RAW LLM RESPONSE - SCENE GENERATION WITH CHOICES (MULTI-MESSAGE)")
        logger.info("=" * 80)
        logger.info(f"Full response text ({len(response_text)} chars):")
        logger.info(response_text)
        logger.info("=" * 80)

        cleaned_response = self._clean_scene_numbers(response_text)

        # Split scene and choices
        if CHOICES_MARKER in cleaned_response:
            parts = cleaned_response.split(CHOICES_MARKER, 1)
            scene_content = parts[0].strip()
            choices_text = parts[1].strip() if len(parts) > 1 else ""
            
            parsed_choices = self._parse_choices_from_json(choices_text)
            if parsed_choices:
                logger.info(f"[CHOICES] Successfully parsed {len(parsed_choices)} choices")
                # If separate_choice_generation is enabled, discard inline choices
                if separate_choice_generation:
                    logger.info(f"[CHOICES] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
                    return (scene_content, None)
                return (scene_content, parsed_choices)
            else:
                # Check if response might have been truncated
                if len(choices_text) < 50:
                    logger.warning(f"[CHOICES] Marker found but choices text is very short ({len(choices_text)} chars). Response may have been truncated. Choices text: {choices_text}")
                else:
                    logger.warning(f"[CHOICES] Marker found but parsing failed. Choices text length: {len(choices_text)}, preview: {choices_text[:200]}")
                return (scene_content, None)
        else:
            # No marker found in cleaned response - try post-processing extraction from raw response
            logger.warning(f"[CHOICES] Marker NOT found in cleaned response. Attempting post-processing extraction...")
            scene_content, extracted_choices = self._extract_choices_from_response_end(response_text)
            if extracted_choices:
                logger.info(f"[CHOICES] Post-processing extracted {len(extracted_choices)} choices from response end")
                # If separate_choice_generation is enabled, discard inline choices
                if separate_choice_generation:
                    logger.info(f"[CHOICES] Separate choice generation enabled - discarding {len(extracted_choices)} inline choices")
                    return (scene_content, None)
                return (scene_content, extracted_choices)
            else:
                logger.warning(f"[CHOICES] Could not extract choices from response. Response length: {len(cleaned_response)} chars")
                return (cleaned_response, None)

    # =====================================================================
    # UNIFIED NON-STREAMING METHODS (cache-aligned)
    # These use the same message structure as streaming methods for cache hits
    # =====================================================================

    async def generate_variant_with_choices(
        self,
        original_scene: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Tuple[str, Optional[List[str]]]:
        """
        Generate scene variant and choices in a single non-streaming call.

        Uses SAME multi-message structure as streaming methods for maximum cache hits.
        This is the unified non-streaming equivalent of generate_variant_with_choices_streaming().

        Args:
            original_scene: Original scene content (for guided enhancement)
            context: Scene generation context
            user_id: User ID for LLM settings
            user_settings: User settings dict
            db: Database session for preset lookups

        Returns:
            Tuple of (scene_content, choices_list or None)
        """
        logger.info(f"[VARIANT NON-STREAMING] Starting variant generation with cache-friendly structure")

        # Get settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

        # Build cache-friendly message prefix (SAME as streaming version)
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task message (SAME logic as streaming version)
        task_content = self._build_variant_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            original_scene=original_scene,
            include_choices_reminder=not separate_choice_generation
        )
        messages.append({"role": "user", "content": task_content})

        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        logger.info(f"[VARIANT NON-STREAMING] Using {len(messages)} messages, max_tokens={max_tokens}")

        # Generate with multi-message structure
        response = await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        )

        # Clean the response
        cleaned_response = self._clean_scene_numbers(response)

        # Parse choices from response
        scene_content, choices = self._parse_choices_from_response(cleaned_response)

        # If separate_choice_generation is enabled, discard inline choices
        if separate_choice_generation and choices:
            logger.info(f"[VARIANT NON-STREAMING] Separate choice generation enabled - discarding {len(choices)} inline choices")
            choices = None

        return scene_content, choices

    async def generate_continuation_with_choices(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Tuple[str, Optional[List[str]]]:
        """
        Generate scene continuation and choices in a single non-streaming call.

        Uses SAME multi-message structure as streaming methods for maximum cache hits.
        This is the unified non-streaming equivalent of generate_continuation_with_choices_streaming().

        Args:
            context: Continuation context with current_scene_content and continuation_prompt
            user_id: User ID for LLM settings
            user_settings: User settings dict
            db: Database session for preset lookups

        Returns:
            Tuple of (continuation_content, choices_list or None)
        """
        logger.info(f"[CONTINUATION NON-STREAMING] Starting continuation generation with cache-friendly structure")

        # Get settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

        # Build cache-friendly message prefix (SAME as streaming version)
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task message (SAME logic as streaming version)
        task_content = self._build_continuation_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=not separate_choice_generation
        )
        messages.append({"role": "user", "content": task_content})

        max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)

        logger.info(f"[CONTINUATION NON-STREAMING] Using {len(messages)} messages, max_tokens={max_tokens}")

        # Generate with multi-message structure
        response = await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        )

        # Clean the response
        cleaned_response = self._clean_scene_numbers(response)

        # Parse choices from response
        continuation_content, choices = self._parse_choices_from_response(cleaned_response)

        # If separate_choice_generation is enabled, discard inline choices
        if separate_choice_generation and choices:
            logger.info(f"[CONTINUATION NON-STREAMING] Separate choice generation enabled - discarding {len(choices)} inline choices")
            choices = None

        return continuation_content, choices

    async def generate_concluding_scene(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> str:
        """
        Generate a chapter-concluding scene in a non-streaming fashion.

        Uses SAME multi-message structure as streaming methods for maximum cache hits.
        This is the unified non-streaming equivalent of generate_concluding_scene_streaming().

        Unlike other scene generation methods, this does NOT generate choices
        as chapter endings are meant to conclude rather than branch.

        Args:
            context: Scene generation context from context_manager
            chapter_info: Dictionary with chapter_number, chapter_title, etc.
            user_id: User ID for LLM settings
            user_settings: User settings dictionary
            db: Database session for prompt templates

        Returns:
            Scene content string (no choices)
        """
        logger.info(f"[CONCLUDING NON-STREAMING] Starting concluding scene generation with cache-friendly structure")

        # Build cache-friendly message prefix (SAME as streaming version)
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task message (SAME logic as streaming version)
        task_content = self._build_concluding_task_message(
            context=context,
            chapter_info=chapter_info,
            user_settings=user_settings,
            db=db
        )
        messages.append({"role": "user", "content": task_content})

        max_tokens = prompt_manager.get_max_tokens("chapter_conclusion", user_settings)

        logger.info(f"[CONCLUDING NON-STREAMING] Using {len(messages)} messages, max_tokens={max_tokens}")

        # Generate with multi-message structure
        response = await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        )

        # Clean and return the response
        return self._clean_scene_numbers(response)

    async def generate_scene_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """
        Generate a story scene with streaming using multi-message structure for better cache utilization.
        """
        
        # Get scene length and choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Default prose_style (no db access in this function)
        prose_style = 'balanced'
        
        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Choose template based on whether we have immediate_situation
        if immediate_situation and immediate_situation.strip():
            template_key = "scene_with_immediate"
            logger.info(f"[SCENE GENERATION STREAMING] Using scene_with_immediate template (has immediate_situation)")
        else:
            template_key = "scene_without_immediate"
            logger.info(f"[SCENE GENERATION STREAMING] Using scene_without_immediate template (no immediate_situation)")
        
        # Get system prompt from template
        system_prompt = prompt_manager.get_prompt(
            template_key, "system",
            user_id=user_id,
            scene_length_description=scene_length_description,
            choices_count=choices_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        client = self.get_user_client(user_id, user_settings)

        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        # Use cache-friendly helper for consistent message prefix
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=None  # No db access in this method
        )

        # Build task instruction using helper (no choices for this method)
        task_content = self._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=None,
            include_choices_reminder=False
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[SCENE GENERATION STREAMING] Using multi-message structure: {len(messages)} messages")
        
        # Collect all raw chunks for raw response capture (before cleaning)
        raw_chunks = []
        
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            # Capture raw chunk before cleaning
            raw_chunks.append(chunk)
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
        
        # Write raw response to file after streaming completes (only if prompt_debug is enabled)
        if settings.prompt_debug and raw_chunks:
            try:
                backend_dir = Path(__file__).parent.parent.parent
                raw_response_file = backend_dir / "Raw-Response.txt"
                full_response = ''.join(raw_chunks)
                with open(raw_response_file, 'w', encoding='utf-8') as f:
                    f.write("=" * 80 + "\n")
                    f.write("RAW LLM RESPONSE FOR NEW SCENE GENERATION (STREAMING, MULTI-MESSAGE)\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(full_response)
                    f.write("\n\n" + "=" * 80 + "\n")
                logger.debug(f"Raw LLM response written to {raw_response_file}")
            except Exception as e:
                logger.error(f"Failed to write raw response to file: {e}")
    
    # ==========================================================================
    # REMOVED DEPRECATED METHODS
    # ==========================================================================
    # The following methods were removed as they used non-cache-friendly message patterns:
    # - generate_scene_variants() - Use generate_variant_with_choices() instead
    # - generate_scene_continuation() - Use generate_continuation_with_choices() instead
    # - generate_scene_continuation_streaming() - Use generate_continuation_with_choices_streaming() instead
    # ==========================================================================

    def _fix_incomplete_json_array(self, json_str: str) -> Optional[str]:
        """Fix incomplete JSON array. Delegates to choice_parser module."""
        return fix_incomplete_json_array(json_str)

    def _fix_malformed_json_escaping(self, text: str) -> str:
        """Fix malformed JSON escaping. Delegates to choice_parser module."""
        return fix_malformed_json_escaping(text)

    def _extract_choices_with_regex(self, text: str) -> Optional[List[str]]:
        """Extract choices with regex fallback. Delegates to choice_parser module."""
        return extract_choices_with_regex(text)

    def _parse_choices_from_json(self, text: str) -> Optional[List[str]]:
        """Parse choices from JSON. Delegates to choice_parser module."""
        return parse_choices_from_json(text)

    def _extract_choices_from_response_end(self, full_text: str) -> Tuple[str, Optional[List[str]]]:
        """Extract choices from response end. Delegates to choice_parser module."""
        return extract_choices_from_response_end(full_text)

    def _detect_json_array_in_prose(self, text: str, min_scene_length: int = 200) -> Tuple[str, Optional[List[str]]]:
        """Detect JSON array in prose text. Delegates to choice_parser module."""
        return detect_json_array_in_prose(text, min_scene_length)
    
    async def generate_scene_with_choices_streaming(
        self, 
        context: Dict[str, Any], 
        user_id: int, 
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate scene content and choices in a single streaming call.
        Uses multi-message structure for better cache utilization.
        
        Yields tuples of (chunk, scene_complete, parsed_choices)
        - chunk: Scene content chunk (only yielded before marker)
        - scene_complete: True when scene content is done (marker found)
        - parsed_choices: List of choices if successfully parsed, None otherwise
        """
        CHOICES_MARKER = "###CHOICES###"

        # Get scene length, choices count, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        logger.info(f"[SCENE GEN STREAMING] separate_choice_generation={separate_choice_generation}, generation_prefs={generation_prefs}")
        scene_length_description = self._get_scene_length_description(scene_length)

        # Extract immediate_situation from context for template variable
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # Determine if we have an immediate situation (for task instruction selection)
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        logger.info(f"[SCENE GEN STREAMING] has_immediate={has_immediate}")
        
        # Get POV from writing preset (default to third person)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Create POV instruction for template
        if pov == 'first':
            pov_instruction = "in first person (I/me/my)"
        elif pov == 'second':
            pov_instruction = "in second person (you/your)"
        else:
            pov_instruction = "in third person (he/she/they/character names)"
        
        # === ALWAYS use scene_with_immediate for system prompt (cache consistency) ===
        # The task instruction will vary based on has_immediate, but system prompt stays the same
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Enhance system prompt with POV instruction for choices (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        logger.info(f"[SCENE WITH CHOICES STREAMING] Using max_tokens: {max_tokens}")

        client = self.get_user_client(user_id, user_settings)

        # Fast path: saved full prompt = simple variant regeneration.
        # Use the exact prompt from original scene gen — 100% bit-for-bit identical.
        saved_full_prompt = context.get("_saved_full_prompt")
        if saved_full_prompt:
            messages = saved_full_prompt
            logger.info(f"[SCENE GEN STREAMING] Using saved full prompt ({len(messages)} messages)")
        else:
            # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
            # Use helper to build cache-friendly prefix (system + context messages)
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )

            # Get task instruction and choices reminder from prompts.yml
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            tone = context.get('tone', '')
            task_content = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )

            # Only append choices reminder if separate_choice_generation is NOT enabled
            # When enabled, choices will be generated in a separate LLM call for higher quality
            if not separate_choice_generation:
                chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
                choices_reminder = prompt_manager.get_user_choices_reminder(
                    choices_count=choices_count,
                    chapter_plot_for_choices=chapter_plot_for_choices
                )
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
            else:
                logger.info(f"[SCENE WITH CHOICES STREAMING] Separate choice generation enabled - skipping choices reminder in task")

            messages.append({"role": "user", "content": task_content})

            # Save full prompt snapshot for variant regeneration (prefix + task message).
            # Simple variant: uses this as-is (100% identical prompt).
            # Everything else: strips last message, uses as prefix, appends own task.
            context['_prompt_prefix_snapshot'] = json.dumps({"v": 2, "messages": messages})

        # Save prefix for same-request reuse (choices generation after scene gen).
        # MUST be outside the if/else so it's saved for BOTH fast path (saved_full_prompt)
        # and rebuild path. Without this, choice gen can't find the prefix and rebuilds
        # from scratch — potentially getting a different system prompt (cache break).
        context['_saved_prompt_prefix'] = list(messages[:-1])

        logger.info(f"[SCENE WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import time
                # Use timestamp to prevent overwriting - scene vs variant comparison
                ts = int(time.time() * 1000)
                prompt_file_path = self._get_prompt_debug_path(f"prompt_sent_scene_{ts}.json")
                # Also save to standard path for backwards compatibility
                prompt_file_path_std = self._get_prompt_debug_path("prompt_sent_scene.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                with open(prompt_file_path_std, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                logger.info(f"[PROMPT DEBUG] Saved scene prompt to {prompt_file_path}")
            except Exception as e:
                logger.warning(f"Failed to write prompt debug file: {e}")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        raw_chunks = []  # Collect raw chunks before cleaning
        chars_processed = 0  # Track position in response for position-aware cleaning
        
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            total_chunks += 1
            
            # Handle thinking content - yield it but don't add to scene buffer
            # Thinking chunks are prefixed with __THINKING__:
            if chunk.startswith("__THINKING__:"):
                # Yield thinking chunk for frontend display, but don't process for scene/choices
                yield (chunk, False, None)
                continue
            
            raw_chunks.append(chunk)  # Capture raw chunk before cleaning
            
            # Pass position to cleaner for position-aware cleaning
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk, chars_processed)
            chars_processed += len(chunk)  # Update position after cleaning
            
            if not cleaned_chunk:
                continue
            
            if not found_marker:
                # Add to rolling buffer
                rolling_buffer += cleaned_chunk

                # Check if marker is in rolling buffer
                if CHOICES_MARKER in rolling_buffer:
                    # Split: before marker goes to scene, after to choices
                    parts = rolling_buffer.split(CHOICES_MARKER, 1)
                    scene_part = parts[0]  # Everything before marker - guaranteed to be new content
                    choices_part = parts[1] if len(parts) > 1 else ""

                    # scene_part is guaranteed to be new content (rolling_buffer only has unyielded content)
                    # Yield ALL of it to preserve complete scene text before marker
                    if scene_part:
                        yield (scene_part, False, None)

                    scene_buffer.append(scene_part)

                    # Buffer the choices part - DO NOT YIELD
                    if choices_part:
                        choices_buffer.append(choices_part)

                    found_marker = True
                    rolling_buffer = ""  # Clear rolling buffer
                    # Continue reading to get all choice chunks
                else:
                    # === NEW: Detect JSON array start pattern ===
                    # Since story prose NEVER contains JSON arrays, if we see ["
                    # after substantial content, it's likely choices without marker
                    total_scene_len = sum(len(s) for s in scene_buffer) + len(rolling_buffer)
                    json_array_pattern = r'\[\s*["\']'
                    json_match = re.search(json_array_pattern, rolling_buffer)

                    if json_match and total_scene_len > 300:
                        # Found potential JSON array start after substantial content
                        json_start = json_match.start()
                        scene_part = rolling_buffer[:json_start]
                        choices_part = rolling_buffer[json_start:]

                        if scene_part:
                            yield (scene_part, False, None)
                        scene_buffer.append(scene_part)

                        if choices_part:
                            choices_buffer.append(choices_part)

                        found_marker = True  # Treat as if we found marker
                        rolling_buffer = ""
                        logger.info(f"[CHOICES STREAMING] Detected JSON array start at position {total_scene_len - len(rolling_buffer) + json_start}")
                    else:
                        # Keep rolling buffer small (only last len(MARKER) chars needed)
                        # to detect marker split across chunks
                        if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                            # Yield the excess (keeping last MARKER length in buffer)
                            excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                            excess = rolling_buffer[:excess_length]
                            scene_buffer.append(excess)
                            yield (excess, False, None)
                            rolling_buffer = rolling_buffer[excess_length:]
            else:
                # After marker, buffer for choice parsing - DO NOT YIELD
                choices_buffer.append(cleaned_chunk)
        
        # After stream ends, yield any remaining rolling buffer content
        if not found_marker and rolling_buffer:
            scene_buffer.append(rolling_buffer)
            yield (rolling_buffer, False, None)
        
        # Build full response for logging
        full_scene_content = ''.join(scene_buffer)
        full_response = full_scene_content + (''.join(choices_buffer) if choices_buffer else '')
        raw_full_response = ''.join(raw_chunks)  # Combined raw chunks before cleaning
        
        # Print raw LLM response to console for scene generation with choices (streaming)
        logger.info("=" * 80)
        logger.info("RAW LLM RESPONSE - SCENE GENERATION WITH CHOICES (STREAMING)")
        logger.info("=" * 80)
        logger.info(f"Full response text ({len(raw_full_response)} chars, {total_chunks} chunks):")
        logger.info(raw_full_response)
        logger.info("=" * 80)
        
        # Write raw response to file (using raw chunks before cleaning, only if prompt_debug is enabled)
        if settings.prompt_debug:
            try:
                backend_dir = Path(__file__).parent.parent.parent
                raw_response_file = backend_dir / "Raw-Response.txt"
                with open(raw_response_file, 'w', encoding='utf-8') as f:
                    f.write("=" * 80 + "\n")
                    f.write("RAW LLM RESPONSE FOR NEW SCENE GENERATION (STREAMING)\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(raw_full_response)
                    f.write("\n\n" + "=" * 80 + "\n")
                logger.debug(f"Raw LLM response written to {raw_response_file}")
            except Exception as e:
                logger.error(f"Failed to write raw response to file: {e}")
        
        # Parse choices from buffer
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if parsed_choices:
                logger.info(f"[CHOICES STREAMING] Successfully parsed {len(parsed_choices)} choices")
            else:
                # Check if response might have been truncated
                if len(choices_text) < 50:
                    logger.warning(f"[CHOICES STREAMING] Marker found but choices text is very short ({len(choices_text)} chars). Response may have been truncated. Choices text: {choices_text}")
                else:
                    logger.warning(f"[CHOICES STREAMING] Marker found but parsing failed. Choices text length: {len(choices_text)}, preview: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES STREAMING] Marker not found during streaming after {total_chunks} chunks. Attempting post-processing extraction...")
                # Try to extract choices from the end of the raw response
                scene_content, extracted_choices = self._extract_choices_from_response_end(raw_full_response)
                if extracted_choices:
                    logger.info(f"[CHOICES STREAMING] Post-processing extracted {len(extracted_choices)} choices from response end")
                    parsed_choices = extracted_choices
                    # Update scene buffer with clean content (without choices)
                    scene_buffer = [scene_content]
                else:
                    logger.warning(f"[CHOICES STREAMING] ERROR: Could not extract choices from response. Full response length: {len(full_response)} chars")
            else:
                logger.warning(f"[CHOICES STREAMING] Marker found but choices_buffer is empty")
        
        # If separate_choice_generation is enabled, discard any inline choices and return None
        # This signals to the caller to use the separate generate_choices() function
        if separate_choice_generation:
            if parsed_choices:
                logger.info(f"[CHOICES STREAMING] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
            parsed_choices = None
        
        # Yield final completion with parsed choices
        yield ("", True, parsed_choices)
    
    async def generate_variant_with_choices_streaming(
        self,
        original_scene: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate scene variant and choices in a single streaming call.
        Same pattern as generate_scene_with_choices_streaming.
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Log inputs for debugging
        logger.info(f"Variant generation - context type: {type(context)}")
        
        # Get scene length, choices count, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # Check if this is guided enhancement (has enhancement_guidance) or simple variant
        enhancement_guidance = context.get("enhancement_guidance", "")
        
        # Get POV from writing preset (default to third person)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
            if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                prose_style = active_preset.prose_style
        
        # Create POV instruction for template
        if pov == 'first':
            pov_instruction = "in first person (I/me/my)"
        elif pov == 'second':
            pov_instruction = "in second person (you/your)"
        else:
            pov_instruction = "in third person (he/she/they/character names)"
        
        # === USE HELPER FOR CACHE-FRIENDLY MESSAGE PREFIX ===
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        tone = context.get('tone', '')
        if enhancement_guidance:
            # Guided enhancement: use task_guided_enhancement from prompts.yml
            # Get plot guidance for choices (upcoming story beats)
            chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings) if not separate_choice_generation else ""
            task_content = prompt_manager.get_enhancement_task_instruction(
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                prose_style=prose_style,
                tone=tone,
                skip_choices_reminder=separate_choice_generation,
                chapter_plot_for_choices=chapter_plot_for_choices
            )
            logger.info(f"[GUIDED ENHANCEMENT] Using multi-message structure with enhancement task")
        else:
            # Simple variant: use same task instruction as scene generation
            immediate_situation = context.get("current_situation") or ""
            immediate_situation = str(immediate_situation) if immediate_situation else ""
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            
            task_content = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            
            # Only append choices reminder if separate_choice_generation is NOT enabled
            if not separate_choice_generation:
                chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
                choices_reminder = prompt_manager.get_user_choices_reminder(
                    choices_count=choices_count,
                    chapter_plot_for_choices=chapter_plot_for_choices
                )
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder

        messages.append({"role": "user", "content": task_content})

        # Save prefix for same-request reuse (choices generation after variant gen).
        # Guarantees choice gen uses the exact same system prompt + context prefix.
        context['_saved_prompt_prefix'] = list(messages[:-1])

        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        logger.info(f"[VARIANT WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages, max_tokens={max_tokens}")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent_variant.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write variant prompt debug file: {e}")

        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        raw_chunks = []  # Collect raw chunks for fallback extraction

        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            total_chunks += 1
            raw_chunks.append(chunk)
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if not cleaned_chunk:
                continue

            if not found_marker:
                # Add to rolling buffer
                rolling_buffer += cleaned_chunk

                # Check if marker is in rolling buffer
                if CHOICES_MARKER in rolling_buffer:
                    # Split: before marker goes to scene, after to choices
                    parts = rolling_buffer.split(CHOICES_MARKER, 1)
                    scene_part = parts[0]  # Everything before marker - guaranteed to be new content
                    choices_part = parts[1] if len(parts) > 1 else ""

                    # scene_part is guaranteed to be new content (rolling_buffer only has unyielded content)
                    # Yield ALL of it to preserve complete scene text before marker
                    if scene_part:
                        yield (scene_part, False, None)

                    scene_buffer.append(scene_part)

                    # Buffer the choices part - DO NOT YIELD
                    if choices_part:
                        choices_buffer.append(choices_part)

                    found_marker = True
                    rolling_buffer = ""  # Clear rolling buffer
                    # Continue reading to get all choice chunks
                else:
                    # === NEW: Detect JSON array start pattern ===
                    total_scene_len = sum(len(s) for s in scene_buffer) + len(rolling_buffer)
                    json_array_pattern = r'\[\s*["\']'
                    json_match = re.search(json_array_pattern, rolling_buffer)

                    if json_match and total_scene_len > 300:
                        json_start = json_match.start()
                        scene_part = rolling_buffer[:json_start]
                        choices_part = rolling_buffer[json_start:]

                        if scene_part:
                            yield (scene_part, False, None)
                        scene_buffer.append(scene_part)

                        if choices_part:
                            choices_buffer.append(choices_part)

                        found_marker = True
                        rolling_buffer = ""
                        logger.info(f"[CHOICES VARIANT] Detected JSON array start")
                    elif len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                        # Keep rolling buffer small (only last len(MARKER) chars needed)
                        excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                        excess = rolling_buffer[:excess_length]
                        scene_buffer.append(excess)
                        yield (excess, False, None)
                        rolling_buffer = rolling_buffer[excess_length:]
            else:
                # After marker, buffer for choice parsing - DO NOT YIELD
                choices_buffer.append(cleaned_chunk)

        # After stream ends, yield any remaining rolling buffer content
        if not found_marker and rolling_buffer:
            scene_buffer.append(rolling_buffer)
            yield (rolling_buffer, False, None)

        # Build raw response for fallback extraction
        raw_full_response = ''.join(raw_chunks)

        # Parse choices from buffer
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if not parsed_choices:
                logger.warning(f"[CHOICES VARIANT] Marker found but parsing failed. Choices text: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES VARIANT] Marker not found after {total_chunks} chunks. Attempting extraction...")
                # Fallback: try to extract choices from raw response
                scene_content, extracted_choices = self._extract_choices_from_response_end(raw_full_response)
                if extracted_choices:
                    logger.info(f"[CHOICES VARIANT] Extracted {len(extracted_choices)} choices from response")
                    parsed_choices = extracted_choices
                else:
                    logger.warning(f"[CHOICES VARIANT] Could not extract choices. Scene length: {len(''.join(scene_buffer))} chars")
            else:
                logger.warning(f"[CHOICES VARIANT] Marker found but choices_buffer is empty")
        
        # If separate_choice_generation is enabled, discard any inline choices
        if separate_choice_generation and parsed_choices:
            logger.info(f"[CHOICES VARIANT] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
            parsed_choices = None
        
        yield ("", True, parsed_choices)
    
    async def generate_continuation_with_choices_streaming(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate scene continuation and choices in a single streaming call.
        
        Uses the SAME multi-message structure as scene generation and choice generation
        for maximum cache hits. Messages 1-N are identical (system prompt, foundation,
        chapter, entity states, scene batches). Only the final message differs
        (current scene + continuation instruction instead of new scene + choice request).
        """
        CHOICES_MARKER = "###CHOICES###"
        
        # Get POV and prose_style from writing preset (SAME as scene generation - critical for cache hits)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Get choices count, scene length, and separate choice generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length = generation_prefs.get("scene_length", "medium")
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_map = {"short": "short (50-100 words)", "medium": "medium (100-150 words)", "long": "long (150-250 words)"}
        scene_length_description = scene_length_map.get(scene_length, "medium (100-150 words)")
        
        # === USE HELPER FOR CACHE-FRIENDLY MESSAGE PREFIX ===
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        # Instead of new scene + choice request, we send current scene + continuation instruction
        # Get current scene content and continuation prompt from context
        current_scene_content = context.get("current_scene_content", "") or context.get("current_content", "")
        continuation_prompt = context.get("continuation_prompt", "Continue this scene with more details and development.")
        
        # Clean scene content to remove any instruction tags or formatting artifacts
        cleaned_scene_content = self._clean_instruction_tags(current_scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)
        
        # Build final message inline (like generate_choices does)
        # Only include choices reminder if separate_choice_generation is NOT enabled
        if separate_choice_generation:
            choices_reminder_text = ""
        else:
            chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
            choices_reminder_text = prompt_manager.get_user_choices_reminder(
                choices_count=choices_count,
                chapter_plot_for_choices=chapter_plot_for_choices
            )

        # Get prose style and tone reminders
        prose_style_reminder = prompt_manager.get_prose_style_reminder(prose_style)
        tone = context.get('tone', '')
        tone_reminder = prompt_manager.get_tone_reminder(tone)
        
        final_message = f"""=== CURRENT SCENE TO CONTINUE ===
{cleaned_scene_content}

=== CONTINUATION INSTRUCTION ===
{continuation_prompt}

Write a compelling continuation that follows naturally from the scene above.
Focus on engaging narrative and dialogue. Do not repeat previous content.
Write approximately {scene_length_description} in length.

{prose_style_reminder}
{tone_reminder}

{choices_reminder_text}"""
        
        messages.append({"role": "user", "content": final_message})

        # Save prefix for same-request reuse (choices generation after continuation).
        context['_saved_prompt_prefix'] = list(messages[:-1])

        max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)

        logger.info(f"[CONTINUATION] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent_continuation.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write continuation prompt debug file: {e}")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        
        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if not cleaned_chunk:
                continue
            
            if not found_marker:
                # Add to rolling buffer
                rolling_buffer += cleaned_chunk
                
                # Check if marker is in rolling buffer
                if CHOICES_MARKER in rolling_buffer:
                    # Split: before marker goes to scene, after to choices
                    parts = rolling_buffer.split(CHOICES_MARKER, 1)
                    scene_part = parts[0]  # Everything before marker - guaranteed to be new content
                    choices_part = parts[1] if len(parts) > 1 else ""
                    
                    # scene_part is guaranteed to be new content (rolling_buffer only has unyielded content)
                    # Yield ALL of it to preserve complete scene text before marker
                    if scene_part:
                        yield (scene_part, False, None)
                    
                    scene_buffer.append(scene_part)
                    
                    # Buffer the choices part - DO NOT YIELD
                    if choices_part:
                        choices_buffer.append(choices_part)
                    
                    found_marker = True
                    rolling_buffer = ""  # Clear rolling buffer
                    # Continue reading to get all choice chunks
                else:
                    # Keep rolling buffer small (only last len(MARKER) chars needed)
                    if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                        excess = rolling_buffer[:excess_length]
                        scene_buffer.append(excess)
                        yield (excess, False, None)
                        rolling_buffer = rolling_buffer[excess_length:]
            else:
                # After marker, buffer for choice parsing - DO NOT YIELD
                choices_buffer.append(cleaned_chunk)
        
        # After stream ends, yield any remaining rolling buffer content
        if not found_marker and rolling_buffer:
            scene_buffer.append(rolling_buffer)
            yield (rolling_buffer, False, None)
        
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if not parsed_choices:
                logger.warning(f"[CHOICES CONTINUATION] Marker found but parsing failed. Choices text: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES CONTINUATION] Marker NOT found")
            else:
                logger.warning(f"[CHOICES CONTINUATION] Marker found but choices_buffer is empty")
        
        # If separate_choice_generation is enabled, discard any inline choices
        if separate_choice_generation and parsed_choices:
            logger.info(f"[CHOICES CONTINUATION] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
            parsed_choices = None
        
        yield ("", True, parsed_choices)
    
    async def generate_concluding_scene_streaming(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a chapter-concluding scene in a streaming fashion.
        Unlike other scene generation methods, this does NOT generate choices
        as chapter endings are meant to conclude rather than branch.
        
        Uses the SAME multi-message structure as scene generation for maximum cache hits.
        Messages 1-N are identical (system prompt, foundation, chapter, entity states, 
        scene batches). Only the final message differs (chapter conclusion instruction).
        
        Args:
            context: Scene generation context from context_manager
            chapter_info: Dictionary with chapter_number, chapter_title, chapter_location, 
                         chapter_time_period, chapter_scenario
            user_id: User ID for LLM settings
            user_settings: User settings dictionary
            db: Database session for prompt templates
            
        Yields:
            str: Scene content chunks as they're generated
        """
        # Get POV and prose_style from writing preset (SAME as scene generation - critical for cache hits)
        pov = 'third'
        prose_style = 'balanced'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset:
                if hasattr(active_preset, 'pov') and active_preset.pov:
                    pov = active_preset.pov
                if hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style
        
        # Get scene length from user settings (for consistency with other generation methods)
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length_description = self._get_scene_length_description(scene_length)
        
        # === USE HELPER FOR CACHE-FRIENDLY MESSAGE PREFIX ===
        # This ensures cache hits with scene generation and choice generation
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # === FINAL MESSAGE: Simple chapter conclusion instruction (inline like continuation) ===
        # Chapter context is already in the multi-message structure, so we just need the task
        chapter_number = chapter_info.get("chapter_number", 1)
        
        # Get prose style and tone reminders
        prose_style_reminder = prompt_manager.get_prose_style_reminder(prose_style)
        tone = context.get('tone', '')
        tone_reminder = prompt_manager.get_tone_reminder(tone)
        
        final_message = f"""=== CHAPTER CONCLUSION INSTRUCTION ===

Write a compelling conclusion for Chapter {chapter_number} that:
1. Brings this chapter to a natural and satisfying end
2. Provides closure for the chapter's events while leaving the overall story open
3. Sets up anticipation for what might come next
4. Ends at a natural chapter break point

Write approximately {scene_length_description} in length.
Write ONLY narrative content. Do not include any choices, options, or questions for the reader.

{prose_style_reminder}
{tone_reminder}

Chapter Conclusion:"""
        
        messages.append({"role": "user", "content": final_message})
        
        max_tokens = prompt_manager.get_max_tokens("chapter_conclusion", user_settings)
        logger.info(f"[CONCLUDING SCENE] Using multi-message structure: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent_conclusion.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "temperature": 1.0,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write chapter conclusion prompt debug file: {e}")
        
        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:
                yield cleaned_chunk
        
        logger.info("[CONCLUDING SCENE STREAMING] Generation complete")
    
    # =====================================================================
    # MULTI-GENERATION METHODS (n > 1)
    # Wrappers that delegate to MultiVariantGeneration class
    # =====================================================================

    async def _generate_stream_with_messages_multi(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[Tuple[str, bool, List[str]], None]:
        """Wrapper for MultiVariantGeneration.generate_stream_with_messages_multi."""
        async for chunk in self._multi_variant.generate_stream_with_messages_multi(
            messages, user_id, user_settings, n, max_tokens, temperature
        ):
            yield chunk

    async def _generate_multi_completions(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> List[str]:
        """Wrapper for MultiVariantGeneration.generate_multi_completions."""
        return await self._multi_variant.generate_multi_completions(
            messages, user_id, user_settings, n, max_tokens, temperature
        )

    async def generate_scene_with_choices_streaming_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[Dict[str, Any]]]], None]:
        """Wrapper for MultiVariantGeneration.generate_scene_with_choices_streaming_multi."""
        async for chunk in self._multi_variant.generate_scene_with_choices_streaming_multi(
            context, user_id, user_settings, db, n
        ):
            yield chunk

    async def generate_scene_with_choices_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[Dict[str, Any]]:
        """Wrapper for MultiVariantGeneration.generate_scene_with_choices_multi."""
        return await self._multi_variant.generate_scene_with_choices_multi(
            context, user_id, user_settings, db, n
        )

    async def generate_scene_streaming_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """Wrapper for MultiVariantGeneration.generate_scene_streaming_multi."""
        async for chunk in self._multi_variant.generate_scene_streaming_multi(
            context, user_id, user_settings, db, n
        ):
            yield chunk

    async def generate_scene_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[str]:
        """Wrapper for MultiVariantGeneration.generate_scene_multi."""
        return await self._multi_variant.generate_scene_multi(
            context, user_id, user_settings, db, n
        )

    async def generate_choices_for_variants(
        self,
        scene_contents: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session]
    ) -> List[List[str]]:
        """Wrapper for MultiVariantGeneration.generate_choices_for_variants."""
        return await self._multi_variant.generate_choices_for_variants(
            scene_contents, context, user_id, user_settings, db
        )

    async def generate_concluding_scene_streaming_multi(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """Wrapper for MultiVariantGeneration.generate_concluding_scene_streaming_multi."""
        async for chunk in self._multi_variant.generate_concluding_scene_streaming_multi(
            context, chapter_info, user_id, user_settings, db, n
        ):
            yield chunk

    async def generate_concluding_scene_multi(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[str]:
        """Wrapper for MultiVariantGeneration.generate_concluding_scene_multi."""
        return await self._multi_variant.generate_concluding_scene_multi(
            context, chapter_info, user_id, user_settings, db, n
        )

    async def regenerate_scene_variant_streaming_multi(
        self,
        db: Session,
        scene_id: int,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        custom_prompt: Optional[str] = None
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[Dict[str, Any]]]], None]:
        """Wrapper for MultiVariantGeneration.regenerate_scene_variant_streaming_multi."""
        async for chunk in self._multi_variant.regenerate_scene_variant_streaming_multi(
            db, scene_id, context, user_id, user_settings, n, custom_prompt
        ):
            yield chunk

    async def regenerate_scene_variant_multi(
        self,
        db: Session,
        scene_id: int,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        custom_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Wrapper for MultiVariantGeneration.regenerate_scene_variant_multi."""
        return await self._multi_variant.regenerate_scene_variant_multi(
            db, scene_id, context, user_id, user_settings, n, custom_prompt
        )

    # =====================================================================
    # END OF MULTI-GENERATION METHODS
    # =====================================================================
    
    def _detect_pov(self, text: str) -> str:
        """Detect POV. Delegates to plot_parser module."""
        return detect_pov(text)
    
    async def generate_choices(self, scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> List[str]:
        """
        Generate narrative choices for the given scene.
        
        Uses the SAME multi-message structure as scene generation for maximum cache hits.
        Messages 1-N are identical to scene generation (system prompt, foundation, chapter,
        entity states, scene batches). Only the final message differs (new scene + choice request).
        """
        
        # Override reasoning_effort to "disabled" for choice generation
        # Reasoning models waste tokens on thinking, leaving nothing for actual choices
        # This ensures choices are generated directly without consuming tokens on reasoning
        import copy
        choice_user_settings = copy.deepcopy(user_settings)
        if 'llm_settings' in choice_user_settings:
            choice_user_settings['llm_settings']['reasoning_effort'] = 'disabled'
        else:
            choice_user_settings['reasoning_effort'] = 'disabled'
        logger.info("[CHOICES] Overriding reasoning_effort to 'disabled' for choice generation")
        
        # Get POV from writing preset (SAME as scene generation - critical for cache hits)
        pov = 'third'
        if db and user_id:
            from ...models.writing_style_preset import WritingStylePreset
            active_preset = db.query(WritingStylePreset).filter(
                WritingStylePreset.user_id == user_id,
                WritingStylePreset.is_active == True
            ).first()
            if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
                pov = active_preset.pov
        
        # Get choices count, scene length, and separate_choice_generation setting from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        scene_length = generation_prefs.get("scene_length", "medium")
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_map = {"short": "short (50-100 words)", "medium": "medium (100-150 words)", "long": "long (150-250 words)"}
        scene_length_description = scene_length_map.get(scene_length, "medium (100-150 words)")
        
        # === USE HELPER FOR CACHE-FRIENDLY MESSAGE PREFIX ===
        messages = await self._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db,
        )

        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        # Instead of task instruction, we send the new scene + choice generation request
        # Clean scene content to remove any instruction tags or formatting artifacts
        cleaned_scene_content = self._clean_instruction_tags(scene_content)
        cleaned_scene_content = self._clean_scene_numbers(cleaned_scene_content)
        
        # Build POV instruction string for template substitution
        if pov == "first":
            pov_instruction = "in first person perspective (using 'I', 'me', 'my')"
        elif pov == "second":
            pov_instruction = "in second person perspective (using 'you', 'your')"
        else:  # third or default
            pov_instruction = "in third person perspective (using 'he', 'she', 'they', character names)"
        
        # Use choice_generation.user template from YAML instead of hardcoded text
        # Include plot guidance for choices (plot is NOT in prefix, only in choice generation)
        chapter_plot_for_choices = self._format_plot_for_choices(context, user_settings)
        final_message = prompt_manager.get_prompt(
            "choice_generation", "user",
            scene_content=cleaned_scene_content,
            choices_count=choices_count,
            pov_instruction=pov_instruction,
            chapter_plot_for_choices=chapter_plot_for_choices
        )

        messages.append({"role": "user", "content": final_message})
        
        # Calculate max tokens - use YAML settings or user settings
        base_max_tokens = prompt_manager.get_max_tokens("choice_generation", user_settings)
        # Ensure at least enough tokens for the requested number of choices
        dynamic_max_tokens = max(base_max_tokens, choices_count * 75)
        max_tokens = dynamic_max_tokens
        
        logger.info(f"[CHOICES] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}, requested_choices={choices_count}")
        
        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent_choices.json")
                client = self.get_user_client(user_id, user_settings)
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write choice prompt debug file: {e}")
        
        # Use the multi-message generation method with reasoning disabled
        response = await self._generate_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=choice_user_settings,  # Use modified settings with reasoning disabled
            max_tokens=max_tokens
        )
        
        # Log raw response for debugging
        logger.info(f"[CHOICES] Raw LLM response for choice generation: {response}")

        # Parse choices from response using JSON format
        choices = self._parse_choices_from_json(response)

        # If parsing failed or we don't have enough choices, return empty list
        # This signals to the API layer that choice generation failed
        if not choices or len(choices) < 2:
            logger.warning(f"[CHOICES] Failed to parse choices from JSON. Response: {response[:200]}")
            return []

        if len(choices) < choices_count:
            logger.warning(f"[CHOICES] LLM generated fewer choices than requested: got {len(choices)}, wanted {choices_count}")

        return choices

    async def extract_plot_events_with_context(
        self,
        scene_content: str,
        key_events: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> List[str]:
        """
        Extract completed plot events using cache-friendly multi-message structure.

        Uses SAME message structure as choice_generation for maximum cache hits:
        - Messages 1-N identical to scene generation (CACHED)
        - Final USER message contains scene + extraction instruction

        Routes to extraction LLM or main LLM - same structure for both.

        Args:
            scene_content: The generated scene text to analyze
            key_events: List of chapter plot events to check for
            context: The same context dict used for scene generation
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            db: Database session for preset lookups

        Returns:
            List of event descriptions that occurred in the scene (exact matches from key_events)
        """
        if not key_events:
            return []

        # === DETERMINE ROUTING ===
        ext_settings = user_settings.get('extraction_model_settings', {})
        force_main_llm_plot = ext_settings.get('use_main_llm_for_plot_extraction', False)
        use_extraction_llm = self._will_use_extraction_llm(user_settings, force_main_llm_plot)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        # === BUILD FINAL MESSAGE (same for all paths) ===
        cleaned_scene = self._clean_scene_numbers(scene_content)
        key_events_formatted = "\n".join(f"{i+1}. {e.strip()}" for i, e in enumerate(key_events))

        final_message = prompt_manager.get_prompt(
            "plot_extraction", "user",
            scene_content=cleaned_scene,
            key_events=key_events_formatted
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You analyze story scenes to identify which planned plot events have occurred. Return only valid JSON.",
                final_message
            )
            logger.info(f"[PLOT_EXTRACTION] Simple structure: {len(messages)} messages, checking {len(key_events)} events")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[PLOT_EXTRACTION] Cache-friendly structure: {len(messages)} messages, checking {len(key_events)} events")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_plot_extraction.json")
                debug_data = {
                    "extraction_type": "plot_events",
                    "num_key_events": len(key_events),
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": 500,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write plot extraction prompt debug file: {e}")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction", force_main_llm=force_main_llm_plot,
            )

            logger.info(f"[PLOT_EXTRACTION] Raw response: {response[:300] if response else 'None'}...")

            # Parse response as JSON object {"1": true, "2": false}
            from ..chapter_progress_service import clean_llm_json
            cleaned = clean_llm_json(response)
            result = json.loads(cleaned)

            valid_events = []

            if isinstance(result, dict):
                # New format: {"1": true, "2": false}
                for key, value in result.items():
                    if value is True:
                        try:
                            idx = int(key) - 1  # 1-indexed to 0-indexed
                            if 0 <= idx < len(key_events):
                                valid_events.append(key_events[idx])
                        except (ValueError, IndexError):
                            logger.warning(f"[PLOT_EXTRACTION] Invalid event key: {key}")
            elif isinstance(result, list):
                # Legacy format fallback: ["event text"]
                key_events_stripped = {e.strip(): e for e in key_events}
                for e in result:
                    stripped = e.strip() if isinstance(e, str) else e
                    if stripped in key_events_stripped:
                        valid_events.append(key_events_stripped[stripped])
                    elif e in key_events:
                        valid_events.append(e)
            else:
                logger.warning(f"[PLOT_EXTRACTION] Unexpected response type: {type(result)}")
                return []

            logger.info(f"[PLOT_EXTRACTION] Extracted {len(valid_events)} valid events from scene")
            return valid_events

        except json.JSONDecodeError as e:
            logger.warning(f"[PLOT_EXTRACTION] Failed to parse JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"[PLOT_EXTRACTION] Extraction failed: {e}")
            return []

    async def extract_combined_cache_friendly(
        self,
        scene_content: str,
        character_names: List[str],
        explicit_character_names: List[str],
        thread_context: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 4000
    ) -> str:
        """
        Combined extraction (characters, NPCs, plot events, entity states)
        using cache-friendly multi-message structure.

        Routes to extraction LLM or main LLM - same structure for both.

        Args:
            scene_content: The generated scene text to analyze
            character_names: List of explicit character names
            explicit_character_names: List of explicit character names (for NPC exclusion)
            thread_context: Context about active plot threads
            context: The same context dict used for scene generation
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            db: Database session for preset lookups
            max_tokens: Maximum tokens for response

        Returns:
            Raw JSON string response from LLM
        """
        # === DETERMINE ROUTING ===
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        # === BUILD FINAL MESSAGE ===
        cleaned_scene = self._clean_scene_numbers(scene_content)

        character_names_str = ", ".join(character_names) if character_names else "None"
        explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
        thread_section = f"\n\nActive plot threads to consider:{thread_context}" if thread_context else ""

        final_message = prompt_manager.get_prompt(
            "combined_extraction", "user",
            scene_content=cleaned_scene,
            character_names=character_names_str,
            explicit_names=explicit_names_str,
            thread_section=thread_section
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You are a precise story analysis assistant. Extract characters, NPCs, plot events, and entity states. Return only valid JSON.",
                final_message
            )
            logger.info(f"[COMBINED_EXTRACTION] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[COMBINED_EXTRACTION] Cache-friendly structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_combined_extraction.json")
                debug_data = {
                    "extraction_type": "combined",
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write combined extraction prompt debug file: {e}")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
            )
        except Exception as e:
            logger.error(f"[COMBINED_EXTRACTION] Extraction failed: {e}")
            raise

    async def extract_combined_cache_friendly_batch(
        self,
        batch_content: str,
        character_names: List[str],
        explicit_character_names: List[str],
        thread_context: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 4000,
        num_scenes: int = 1
    ) -> str:
        """
        Batch extraction (multiple scenes) using cache-friendly multi-message structure.

        Uses SAME message structure as scene generation for maximum cache hits:
        - System prompt: IDENTICAL to scene generation
        - Context messages: IDENTICAL to scene generation
        - Final USER message: batch extraction instruction (different)

        Args:
            batch_content: Combined scene text with markers (=== SCENE N ===)
            character_names: List of character names
            explicit_character_names: List of explicit character names (for NPC exclusion)
            thread_context: Context about active plot threads
            context: The same context dict used for scene generation
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            db: Database session for preset lookups
            max_tokens: Maximum tokens for response
            num_scenes: Number of scenes in batch

        Returns:
            Raw JSON string response from LLM
        """
        # === DETERMINE ROUTING ===
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        # === BUILD FINAL MESSAGE ===
        character_names_str = ", ".join(character_names) if character_names else "None"
        explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
        thread_section = f"\n\nActive plot threads to consider:{thread_context}" if thread_context else ""
        max_npcs_total = 10
        max_events_total = 8

        final_message = prompt_manager.get_prompt(
            "entity_state_extraction.batch", "user",
            character_names=character_names_str,
            explicit_names=explicit_names_str,
            thread_section=thread_section,
            batch_content=batch_content,
            max_npcs_total=max_npcs_total,
            max_events_total=max_events_total
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You are a precise story analysis assistant. Extract characters, NPCs, plot events, and entity states from scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[BATCH_EXTRACTION] Simple structure: {len(messages)} messages, {num_scenes} scenes")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[BATCH_EXTRACTION] Cache-friendly structure: {len(messages)} messages, {num_scenes} scenes")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_batch_extraction.json")
                debug_data = {
                    "extraction_type": "batch",
                    "num_scenes": num_scenes,
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write batch extraction prompt debug file: {e}")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
            )
        except Exception as e:
            logger.error(f"[BATCH_EXTRACTION] Extraction failed: {e}")
            raise

    async def extract_events_and_npcs_cache_friendly(
        self,
        scene_content: str,
        character_names: List[str],
        explicit_character_names: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 2000
    ) -> str:
        """
        Extract scene events and NPCs in a single cache-friendly LLM call.
        Replaces the old moments+NPCs extraction.

        Returns:
            Raw JSON string with {"events": [...], "npcs": [...]}
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        character_names_str = ", ".join(character_names) if character_names else "None"
        explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"

        final_message = prompt_manager.get_prompt(
            "events_and_npcs", "user",
            scene_content=cleaned_scene,
            character_names=character_names_str,
            explicit_names=explicit_names_str
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract factual events and named NPCs from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[EVENTS_NPCS] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[EVENTS_NPCS] Cache-friendly structure: {len(messages)} messages")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
            )
        except Exception as e:
            logger.error(f"[EVENTS_NPCS] Extraction failed: {e}")
            raise

    async def extract_scene_events_cache_friendly(
        self,
        scene_content: str,
        character_names: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 1500
    ) -> str:
        """
        Extract scene events only (no NPCs) via cache-friendly call.
        Used as fallback when combined extraction fails.

        Returns:
            Raw JSON string with {"events": [...]}
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        character_names_str = ", ".join(character_names) if character_names else "None"

        final_message = prompt_manager.get_prompt(
            "scene_event_extraction.cache_friendly", "user",
            scene_content=cleaned_scene,
            character_names=character_names_str
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract factual events from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[SCENE_EVENTS] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[SCENE_EVENTS] Cache-friendly structure: {len(messages)} messages")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
            )
        except Exception as e:
            logger.error(f"[SCENE_EVENTS] Extraction failed: {e}")
            raise

    async def generate_chapter_summary_cache_friendly(
        self,
        chapter_number: int,
        chapter_title: str,
        scenes_content: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        context_section: str = "",
        max_tokens: int = 1500
    ) -> str:
        """
        Generate chapter summary using cache-friendly multi-message structure.

        Uses the same message prefix as scene generation to maximize cache hits.
        This is called AFTER scene generation and extractions complete, so the
        ~13,000 token prefix should already be cached.

        Args:
            chapter_number: Chapter number for context
            chapter_title: Chapter title for context
            scenes_content: The scene content to summarize
            context: The same context dict used for scene generation
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            db: Database session for preset lookups
            context_section: Optional previous chapter summaries for context
            max_tokens: Maximum tokens for response

        Returns:
            Summary text
        """
        # === DETERMINE ROUTING ===
        use_main_for_summary = not user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False)
        use_extraction_llm = self._will_use_extraction_llm(user_settings, force_main_llm=use_main_for_summary)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        # === BUILD FINAL MESSAGE ===
        final_message = prompt_manager.get_prompt(
            "chapter_summary_cache_friendly", "user",
            context_section=context_section,
            chapter_number=chapter_number,
            chapter_title=chapter_title or 'Untitled',
            scenes_content=scenes_content
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You are a skilled story analyst. Create concise, accurate chapter summaries that capture key events and character developments.",
                final_message
            )
            logger.info(f"[CHAPTER_SUMMARY] Simple structure: {len(messages)} messages, chapter {chapter_number}")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[CHAPTER_SUMMARY] Cache-friendly structure: {len(messages)} messages, chapter {chapter_number}")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
                force_main_llm=use_main_for_summary,
            )
        except Exception as e:
            logger.error(f"[CHAPTER_SUMMARY] Cache-friendly generation failed: {e}")
            raise

    async def extract_entity_states_cache_friendly(
        self,
        scene_content: str,
        character_names: List[str],
        chapter_location: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 2000
    ) -> str:
        """
        Fast entity-only extraction for inline contradiction checking.
        Uses cache-friendly multi-message structure (same prefix as scene generation).

        ONLY extracts entity states (characters, locations, objects).
        Does NOT extract: character moments, NPCs, plot events.

        Args:
            scene_content: The generated scene text to analyze
            character_names: List of character names to track
            chapter_location: Primary location context for the chapter
            context: The same context dict used for scene generation
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            db: Database session for preset lookups
            max_tokens: Maximum tokens for response (smaller than full extraction)

        Returns:
            Raw JSON string with entity states only
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        character_names_str = ", ".join(character_names) if character_names else "None"

        final_message = prompt_manager.get_prompt(
            "entity_only_extraction", "user",
            scene_content=cleaned_scene,
            character_names=character_names_str,
            chapter_location=chapter_location or "unspecified location"
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract entity states (characters, locations, objects) from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[ENTITY_ONLY_EXTRACTION] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[ENTITY_ONLY_EXTRACTION] Cache-friendly structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_entity_extraction.json")
                debug_data = {
                    "extraction_type": "entity_only",
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": max_tokens,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write entity extraction prompt debug file: {e}")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
            )
        except Exception as e:
            logger.error(f"[ENTITY_ONLY_EXTRACTION] Extraction failed: {e}")
            raise

    async def extract_relationship_cache_friendly(
        self,
        scene_content: str,
        character_names: List[str],
        characters_in_scene: List[str],
        previous_relationships: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract relationship changes using cache-friendly multi-message structure.

        Uses SAME message structure as scene generation for maximum cache hits.

        Returns:
            List of relationship dicts, or empty list on failure
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        character_names_str = ", ".join(character_names) if character_names else "None"

        final_message = prompt_manager.get_prompt(
            "relationship_extraction_cache_friendly", "user",
            scene_content=cleaned_scene,
            character_names=character_names_str,
            previous_relationships=previous_relationships or "No previous relationships established."
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract relationship changes between characters from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[RELATIONSHIP_EXTRACTION] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[RELATIONSHIP_EXTRACTION] Cache-friendly structure: {len(messages)} messages")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction",
            )

            if not response:
                return []

            import re
            from ..chapter_progress_service import clean_llm_json
            response_text = response.strip()

            # Try to parse as JSON array
            array_match = re.search(r'\[[\s\S]*\]', response_text)
            if array_match:
                try:
                    data = json.loads(array_match.group())
                    if isinstance(data, list):
                        return data
                except json.JSONDecodeError:
                    cleaned = clean_llm_json(array_match.group())
                    data = json.loads(cleaned)
                    if isinstance(data, list):
                        return data

            return []

        except Exception as e:
            logger.error(f"[RELATIONSHIP_EXTRACTION] Cache-friendly extraction failed: {e}")
            return []

    async def extract_working_memory_cache_friendly(
        self,
        scene_content: str,
        current_focus: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Extract working memory updates using cache-friendly multi-message structure.

        Uses SAME message structure as scene generation for maximum cache hits:
        - Messages 1-N identical to scene generation (CACHED)
        - Final USER message contains scene + extraction instruction

        Routes to extraction LLM or main LLM - same structure for both.

        Args:
            scene_content: The generated scene text to analyze
            current_focus: Current narrative focus for context
            context: The same context dict used for scene generation
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            db: Database session for preset lookups

        Returns:
            Dict with recent_focus and character_spotlight, or None on failure
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)

        final_message = prompt_manager.get_prompt(
            "working_memory_cache_friendly", "user",
            scene_content=cleaned_scene,
            current_focus=current_focus or "None set"
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract working memory updates (narrative focus and character spotlight) from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[WORKING_MEMORY] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[WORKING_MEMORY] Cache-friendly structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_working_memory.json")
                debug_data = {
                    "extraction_type": "working_memory",
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": 512,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write working memory prompt debug file: {e}")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction",
            )

            if not response:
                return None

            # Parse JSON response
            import re
            from ..chapter_progress_service import clean_llm_json
            response_text = response.strip()
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    cleaned = clean_llm_json(json_match.group())
                    return json.loads(cleaned)

            return None

        except Exception as e:
            logger.error(f"[WORKING_MEMORY] Cache-friendly extraction failed: {e}")
            return None

    async def generate_scene_summary_cache_friendly(
        self,
        scene_content: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Optional[Dict[str, str]]:
        """
        Generate a 2-3 sentence factual summary and specific location for contextual embedding.

        Uses cache-friendly multi-message structure (same prefix as scene generation)
        so extraction LLM cache is warm for subsequent extraction calls.

        Returns:
            Dict with 'location' (specific room/area) and 'summary' (2-3 sentences), or None on failure
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        final_message = prompt_manager.get_prompt(
            "scene_summary_for_embedding", "user",
            scene_content=cleaned_scene
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You generate concise factual summaries and location descriptions for story scenes.",
                final_message
            )
            logger.info(f"[SCENE_SUMMARY] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[SCENE_SUMMARY] Cache-friendly structure: {len(messages)} messages")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction",
            )

            if not response:
                return None

            import re
            text = response.strip()
            # Strip markdown formatting
            text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
            text = re.sub(r'#{1,6}\s*', '', text)
            text = re.sub(r'`(.+?)`', r'\1', text)

            # Parse response — format: "Location: kitchen\nSummary: sentence(s)"
            # Summary may span multiple lines (2-3 sentences)
            location = ""
            summary = ""
            loc_match = re.search(r'(?i)^location:\s*(.+)', text, re.MULTILINE)
            # Capture everything after "Summary:" (same line + subsequent lines)
            sum_match = re.search(r'(?i)^summary:\s*(.*)', text, re.MULTILINE | re.DOTALL)

            if loc_match:
                location = loc_match.group(1).strip().rstrip('.')
            if sum_match:
                raw_summary = sum_match.group(1).strip()
                # Join multi-line summary into single string, collapse whitespace
                summary = ' '.join(raw_summary.split())

            # If no "Location:" prefix found, first non-empty line is the location
            if not location:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if lines:
                    first = lines[0]
                    if len(first) < 60 and not re.match(r'(?i)^summary:', first):
                        location = first.rstrip('.')

            # If no "Summary:" prefix found, grab text after location line
            if not summary:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                non_loc_lines = [l for l in lines if l.rstrip('.') != location and not re.match(r'(?i)^location:', l)]
                summary = ' '.join(non_loc_lines) if non_loc_lines else ""

            logger.info(f"[SCENE_SUMMARY] Location: {location}, Summary: {summary[:80]}")
            return {"location": location, "summary": summary}

        except Exception as e:
            logger.error(f"[SCENE_SUMMARY] Cache-friendly generation failed: {e}")
            return None

    async def extract_npcs_cache_friendly(
        self,
        scene_content: str,
        explicit_names: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract NPCs using cache-friendly multi-message structure.

        Uses SAME message structure as scene generation for maximum cache hits.
        Routes to extraction LLM or main LLM - same structure for both.

        Returns:
            List of NPC dicts, or empty list on failure
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        explicit_names_str = ", ".join(explicit_names) if explicit_names else "None"

        final_message = prompt_manager.get_prompt(
            "npc_extraction_cache_friendly", "user",
            scene_content=cleaned_scene,
            explicit_names=explicit_names_str
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract named NPCs (non-player characters) from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[NPC_EXTRACTION] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[NPC_EXTRACTION] Cache-friendly structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_npc_extraction.json")
                debug_data = {
                    "extraction_type": "npc",
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": 1000,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write NPC extraction prompt debug file: {e}")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction",
            )

            if not response:
                return []

            import re
            from ..chapter_progress_service import clean_llm_json
            response_text = response.strip()
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data.get('npcs', [])
                except json.JSONDecodeError:
                    cleaned = clean_llm_json(json_match.group())
                    data = json.loads(cleaned)
                    return data.get('npcs', [])

            return []

        except Exception as e:
            logger.error(f"[NPC_EXTRACTION] Cache-friendly extraction failed: {e}")
            return []

    async def extract_character_moments_cache_friendly(
        self,
        scene_content: str,
        character_names: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract character moments using cache-friendly multi-message structure.

        Uses SAME message structure as scene generation for maximum cache hits.
        Routes to extraction LLM or main LLM - same structure for both.

        Returns:
            List of character moment dicts, or empty list on failure
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)
        character_names_str = ", ".join(character_names) if character_names else "None"

        final_message = prompt_manager.get_prompt(
            "character_moments_cache_friendly", "user",
            scene_content=cleaned_scene,
            character_names=character_names_str
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract significant character moments from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[CHARACTER_MOMENTS] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[CHARACTER_MOMENTS] Cache-friendly structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_character_moments.json")
                debug_data = {
                    "extraction_type": "character_moments",
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": 1000,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write character moments prompt debug file: {e}")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction",
            )

            if not response:
                return []

            import re
            from ..chapter_progress_service import clean_llm_json
            response_text = response.strip()
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data.get('character_moments', [])
                except json.JSONDecodeError:
                    cleaned = clean_llm_json(json_match.group())
                    data = json.loads(cleaned)
                    return data.get('character_moments', [])

            return []

        except Exception as e:
            logger.error(f"[CHARACTER_MOMENTS] Cache-friendly extraction failed: {e}")
            return []

    async def extract_plot_events_fallback_cache_friendly(
        self,
        scene_content: str,
        thread_context: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract plot events (fallback path) using cache-friendly multi-message structure.

        This is different from extract_plot_events_with_context which checks against
        specific key events. This extracts any significant plot events from the scene.

        Uses SAME message structure as scene generation for maximum cache hits.
        Routes to extraction LLM or main LLM - same structure for both.

        Returns:
            List of plot event dicts, or empty list on failure
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        cleaned_scene = self._clean_scene_numbers(scene_content)

        final_message = prompt_manager.get_prompt(
            "plot_events_cache_friendly", "user",
            scene_content=cleaned_scene,
            thread_context=thread_context or "\n(No active threads)"
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract significant plot events from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[PLOT_EVENTS_FALLBACK] Simple structure: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[PLOT_EVENTS_FALLBACK] Cache-friendly structure: {len(messages)} messages")

        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_plot_fallback_extraction.json")
                debug_data = {
                    "extraction_type": "plot_events_fallback",
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": 1000,
                        "temperature": 0.3
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write plot fallback extraction prompt debug file: {e}")

        try:
            response = await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                task_type="extraction",
            )

            if not response:
                return []

            import re
            from ..chapter_progress_service import clean_llm_json
            response_text = response.strip()
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data.get('plot_events', [])
                except json.JSONDecodeError:
                    cleaned = clean_llm_json(json_match.group())
                    data = json.loads(cleaned)
                    return data.get('plot_events', [])

            return []

        except Exception as e:
            logger.error(f"[PLOT_EVENTS_FALLBACK] Cache-friendly extraction failed: {e}")
            return []

    async def extract_chronicle_cache_friendly(
        self,
        scenes_content: str,
        character_names: str,
        existing_state_section: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 3000,
        chapter_location: str = "",
    ) -> str:
        """
        Extract character chronicle entries and location lorebook events
        using cache-friendly multi-message structure with the main LLM.

        Returns:
            Raw JSON string with character_chronicle and location_lorebook arrays.
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        chapter_location_section = ""
        if chapter_location:
            chapter_location_section = f"\n    CHAPTER LOCATION: {chapter_location}\n    Use this to qualify generic room names (e.g., if chapter is set at \"Nishant's suburban home\", use \"Nishant's Kitchen\" not \"Kitchen\")."

        final_message = prompt_manager.get_prompt(
            "chronicle_extraction", "user",
            scenes_content=scenes_content,
            character_names=character_names,
            existing_chronicle_section=existing_state_section,
            chapter_location_section=chapter_location_section,
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You extract character chronicle entries and location lorebook events from story scenes. Return only valid JSON.",
                final_message
            )
            logger.info(f"[CHRONICLE] Simple extraction: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[CHRONICLE] Cache-friendly extraction: {len(messages)} messages")

        # Debug log
        from ...config import settings
        if settings.prompt_debug:
            try:
                prompt_file_path = self._get_prompt_debug_path("prompt_chronicle_extraction.json")
                debug_data = {
                    "extraction_type": "chronicle",
                    "messages": messages,
                    "generation_parameters": {"max_tokens": max_tokens, "temperature": 0.3},
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write chronicle extraction prompt debug file: {e}")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
                force_main_llm=False,
            )
        except Exception as e:
            logger.error(f"[CHRONICLE] Extraction failed: {e}")
            raise

    async def validate_chronicle_cache_friendly(
        self,
        scenes_content: str,
        candidate_entries_json: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 2000,
        existing_chronicle_section: str = "",
    ) -> str:
        """
        Validate candidate chronicle/lorebook entries against scene content.
        Uses extraction LLM (cheaper) since this is a simpler yes/no task.

        Returns:
            Raw JSON string with validated entries and keep/reject verdicts.
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        final_message = prompt_manager.get_prompt(
            "chronicle_validation", "user",
            scenes_content=scenes_content,
            candidate_entries=candidate_entries_json,
            existing_chronicle_section=existing_chronicle_section,
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You validate chronicle and lorebook entries against story scene content. Return only valid JSON.",
                final_message
            )
            logger.info(f"[CHRONICLE_VALIDATION] Simple validation: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[CHRONICLE_VALIDATION] Cache-friendly validation: {len(messages)} messages")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
                force_main_llm=False,
            )
        except Exception as e:
            logger.error(f"[CHRONICLE_VALIDATION] Validation failed: {e}")
            raise

    async def generate_snapshot_cache_friendly(
        self,
        character_name: str,
        original_background: str,
        chronicle_entries: str,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session] = None,
        max_tokens: int = 500,
    ) -> str:
        """
        Generate a character snapshot paragraph from chronicle entries.
        Uses main LLM for quality (cache-friendly prefix for ~95% cache hit).

        Returns:
            Raw snapshot text (paragraph).
        """
        use_extraction_llm = self._will_use_extraction_llm(user_settings)
        use_cache = user_settings.get('generation_preferences', {}).get('use_cache_friendly_prompts', True)

        final_message = prompt_manager.get_prompt(
            "character_snapshot_generation", "user",
            character_name=character_name,
            original_background=original_background,
            chronicle_entries=chronicle_entries,
        )

        if use_extraction_llm or not use_cache:
            messages = self._build_simple_extraction_messages(
                "You generate concise character snapshot paragraphs that summarize a character's current state based on chronicle entries.",
                final_message
            )
            logger.info(f"[SNAPSHOT] Simple generation for {character_name}: {len(messages)} messages")
        else:
            messages = await self._build_cache_friendly_message_prefix(
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db,
            )
            messages.append({"role": "user", "content": final_message})
            logger.info(f"[SNAPSHOT] Cache-friendly generation for {character_name}: {len(messages)} messages")

        try:
            return await self.generate_for_task(
                messages=messages, user_id=user_id, user_settings=user_settings,
                max_tokens=max_tokens, task_type="extraction",
            )
        except Exception as e:
            logger.error(f"[SNAPSHOT] Generation failed for {character_name}: {e}")
            raise

    async def generate_scenario(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a creative scenario based on user selections and characters"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "scenario_generation", "scenario_generation",
            context=self._format_context_for_scenario(context),
            elements=self._format_elements_for_scenario(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scenario", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return response
    
    async def generate_plot_points(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], plot_type: str = "complete") -> List[str]:
        """Generate plot points based on characters and scenario"""
        
        if plot_type == "complete":
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "complete_plot", "complete_plot",
                context=self._format_context_for_plot(context)
            )
            max_tokens = prompt_manager.get_max_tokens("complete_plot", user_settings)
        else:
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "single_plot_point", "single_plot_point",
                context=self._format_context_for_plot(context),
                point_name=self._get_plot_point_name(context.get("plot_point_index", 0))
            )
            max_tokens = prompt_manager.get_max_tokens("single_plot_point", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Log raw LLM response for debugging
        logger.warning("=" * 80)
        logger.warning("RAW LLM RESPONSE - PLOT GENERATION")
        logger.warning("=" * 80)
        logger.warning(f"Plot Type: {plot_type}")
        logger.warning(f"Response Length: {len(response)} characters")
        logger.warning("-" * 80)
        logger.warning(f"RAW RESPONSE:\n{response}")
        logger.warning("=" * 80)
        
        if plot_type == "complete":
            parsed_points = self._parse_plot_points_json(response)
            return parsed_points
        else:
            return [response]
    
    async def generate_summary(self, story_content: str, story_context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a comprehensive story summary
        
        Can use either the main LLM or the extraction LLM based on user settings.
        If use_extraction_llm_for_summary is True and extraction model is enabled,
        uses the extraction model for faster (but potentially lower quality) summaries.
        """
        
        # Check if user wants to use extraction LLM for summaries
        use_extraction_llm = user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False)
        extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False)
        
        # Try extraction LLM if requested and enabled
        if use_extraction_llm and extraction_enabled:
            try:
                from .extraction_service import ExtractionLLMService
                
                extraction_service = ExtractionLLMService.from_settings(user_settings)
                if extraction_service:
                    logger.info(f"[SUMMARY] Using extraction LLM for summary generation (user_id={user_id})")
                
                # Get prompts from centralized prompt manager
                system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                    "story_summary", "story_summary",
                    story_context=self._format_context_for_summary(story_context),
                    story_content=story_content
                )
                
                max_tokens = prompt_manager.get_max_tokens("story_summary", user_settings)
                
                # Generate summary with extraction model
                summary = await extraction_service.generate_summary(
                    story_content=story_content,
                    story_context=self._format_context_for_summary(story_context),
                    system_prompt=system_prompt,
                    max_tokens=max_tokens
                )
                
                logger.info(f"[SUMMARY] Successfully generated summary with extraction LLM (user_id={user_id}, length={len(summary)})")
                return summary.strip()
                
            except Exception as e:
                logger.warning(f"[SUMMARY] Extraction LLM failed, falling back to main LLM: {e}")
                # Fall through to main LLM
        
        # Use main LLM (default behavior or fallback)
        logger.info(f"[SUMMARY] Using main LLM for summary generation (user_id={user_id})")
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_summary", "story_summary",
            story_context=self._format_context_for_summary(story_context),
            story_content=story_content
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_summary", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return response.strip()
    
    # Helper methods for context formatting
    
    def _format_context_for_titles(self, context: Dict[str, Any]) -> str:
        """Format context for title generation. Delegates to context_formatter module."""
        return format_context_for_titles(context)

    def _get_scene_length_description(self, scene_length: str) -> str:
        """Convert scene_length setting. Delegates to context_formatter module."""
        return get_scene_length_description(scene_length)
    
    def _format_characters_section(self, characters: Any, include_voice_style: bool = True) -> str:
        """Format characters section. Delegates to context_formatter module."""
        return format_characters_section(characters, include_voice_style)

    def _format_character_voice_styles(self, characters: Any) -> str:
        """Format character voice styles. Delegates to context_formatter module."""
        return format_character_voice_styles(characters)

    async def _maybe_improve_semantic_scenes(
        self,
        messages: List[Dict[str, str]],
        context: Dict[str, Any],
        user_settings: Dict[str, Any],
        db: Optional[Session],
        user_id: Optional[int] = None,
    ) -> bool:
        """
        Try to improve semantic search results via query decomposition + RRF.

        Splits multi-event user_intent into focused sub-queries using the extraction LLM,
        then re-searches pgvector with each sub-query and merges via Reciprocal Rank Fusion.

        Uses the SAME cache-friendly message prefix for the decomposition call,
        so ExLlamaV3's radix cache gets ~95% hit on the shared prefix tokens.

        Args:
            messages: The message list built by _build_cache_friendly_message_prefix()
            context: The scene context dict
            user_settings: User settings
            db: Database session (needed for boost/filter logic)

        Returns:
            True if messages were updated with improved results, False otherwise
        """
        try:
            # Skip if already improved in this request cycle (e.g., scene gen already ran,
            # now choices/variant gen is calling — context already has improved text)
            if context.get("_semantic_improved"):
                logger.info("[SEMANTIC DECOMPOSE] Skipped: already improved in this request cycle")
                return True

            # Get user_intent
            search_state = context.get("_semantic_search_state")
            user_intent = None
            if search_state:
                user_intent = search_state.get("user_intent")
            if not user_intent:
                user_intent = context.get("current_situation")
            if not user_intent or not user_intent.strip():
                logger.info(f"[SEMANTIC DECOMPOSE] Skipped: no user_intent (search_state={'present' if search_state else 'missing'}, current_situation={bool(context.get('current_situation'))})")
                return False

            # Gate: need db for boost/filter
            if db is None:
                logger.info("[SEMANTIC DECOMPOSE] Skipped: db is None")
                return False

            # Route to extraction LLM if available, otherwise main LLM
            ext_settings = user_settings.get('extraction_model_settings', {})
            use_extraction_model = ext_settings.get('enabled', False)
            extraction_service = self._get_extraction_service(user_settings) if use_extraction_model else None

            # Gate: need context_manager ref and search state
            ctx_mgr = context.get("_context_manager_ref")
            if not ctx_mgr or not search_state:
                logger.info(f"[SEMANTIC DECOMPOSE] Skipped: ctx_mgr={bool(ctx_mgr)}, search_state={bool(search_state)}")
                return False

            # Build char_context early — needed by both cached and fresh paths
            characters = context.get("characters", [])
            if isinstance(characters, dict) and "active_characters" in characters:
                _char_list = characters.get("active_characters", []) + characters.get("inactive_characters", [])
            else:
                _char_list = characters if isinstance(characters, list) else []
            _char_names = [c.get("name", "") for c in _char_list if c.get("name")]
            char_context = f"Characters in this story: {', '.join(_char_names)}\n\n" if _char_names else ""

            # --- Reuse cached intent from context_manager if available ---
            cached_intent = search_state.get("intent_result") if search_state else None
            if cached_intent:
                intent_type = cached_intent.get("intent")
                temporal_type = cached_intent.get("temporal")
                sub_queries = cached_intent.get("queries", [])
                keywords = cached_intent.get("keywords", [])
                logger.info(f"[SEMANTIC DECOMPOSE] Reusing cached intent from context_manager: {intent_type or 'direct'}")

                # Direct/react intent — semantic search was already skipped, nothing to improve
                if intent_type in ("direct", "react") or (not intent_type and not sub_queries):
                    logger.info(f"[SEMANTIC DECOMPOSE] {intent_type or 'direct'} intent — no semantic improvement needed")
                    return False
            else:
                # No cached intent — run classification here (fallback path)
                logger.info(f"[SEMANTIC DECOMPOSE] Attempting query decomposition for: '{user_intent[:100]}...'")

                # Build minimal context — character names with gender for pronoun resolution
                characters = context.get("characters", [])
                if isinstance(characters, dict) and "active_characters" in characters:
                    char_list = characters.get("active_characters", []) + characters.get("inactive_characters", [])
                else:
                    char_list = characters if isinstance(characters, list) else []

                def _infer_gender(char_data: dict) -> str:
                    """Get gender from explicit field, or infer from appearance/description."""
                    explicit = (char_data.get("gender") or "").strip().lower()
                    if explicit:
                        return explicit
                    appearance = (char_data.get("appearance") or "").lower()
                    if any(kw in appearance for kw in ["bust ", "bra ", "36d", "34c", "32b", "hourglass"]):
                        return "female"
                    for field in ["description", "background"]:
                        text = (char_data.get(field) or "").lower()
                        if " she " in text or " her " in text or "wife" in text or "woman" in text or "mother" in text:
                            return "female"
                        if " he " in text or " his " in text or "husband" in text or " man " in text or "father" in text:
                            return "male"
                    return ""

                char_labels = []
                for c in char_list:
                    name = c.get("name", "")
                    if not name:
                        continue
                    parts = [name]
                    gender = _infer_gender(c)
                    if gender:
                        parts.append(gender)
                    role = c.get("role", "")
                    if role:
                        parts.append(role)
                    char_labels.append(f"{parts[0]} ({', '.join(parts[1:])})" if len(parts) > 1 else name)
                char_context = f"Characters in this story: {', '.join(char_labels)}\n\n" if char_labels else ""

                decompose_task = prompt_manager.get_prompt("semantic_decompose", "user", user_intent=user_intent)
                if not decompose_task:
                    logger.warning("[SEMANTIC DECOMPOSE] No prompt found for semantic_decompose, using fallback")
                    decompose_task = f"Classify intent (direct/recall/react) and generate sub-queries.\nReturn JSON: {{\"intent\": \"...\", \"temporal\": \"...\", \"queries\": [...], \"keywords\": [...]}}\n\nText to decompose:\n{user_intent}"
                if extraction_service:
                    _allow_thinking_decompose = ext_settings.get('thinking_enabled_memory', True)
                    decompose_messages = [{"role": "user", "content": char_context + decompose_task}]
                    logger.info(f"[SEMANTIC DECOMPOSE] Using extraction LLM (allow_thinking={_allow_thinking_decompose})")
                    response = await extraction_service.generate_with_messages(
                        messages=decompose_messages,
                        max_tokens=300,
                        allow_thinking=_allow_thinking_decompose
                    )
                else:
                    import copy
                    decompose_messages = copy.deepcopy(messages)
                    decompose_messages.append({"role": "user", "content": char_context + decompose_task})
                    decompose_settings = copy.deepcopy(user_settings)
                    decompose_settings.setdefault('llm_settings', {})['temperature'] = 0.3
                    decompose_settings['llm_settings']['reasoning_effort'] = 'disabled'
                    logger.info("[SEMANTIC DECOMPOSE] Using main LLM with cache-friendly prefix")
                    from ...config import settings as app_settings
                    if app_settings.prompt_debug:
                        try:
                            debug_path = self._get_prompt_debug_path("prompt_sent_decompose.json")
                            with open(debug_path, "w", encoding="utf-8") as f:
                                json.dump({"messages": decompose_messages}, f, indent=2, ensure_ascii=False)
                            logger.info(f"[PROMPT DEBUG] Saved decompose prompt to {debug_path}")
                        except Exception as e:
                            logger.warning(f"Failed to write decompose prompt debug file: {e}")
                    response = await self._generate_with_messages(
                        messages=decompose_messages,
                        user_id=user_id,
                        user_settings=decompose_settings,
                        max_tokens=300,
                        skip_nsfw_filter=True
                    )

                if not response or not response.strip():
                    logger.info("[SEMANTIC DECOMPOSE] Empty response from extraction LLM")
                    return False

                parsed = self._parse_decomposition_response(response)
                if not parsed:
                    logger.info(f"[SEMANTIC DECOMPOSE] No sub-queries parsed, skipping")
                    return False

                intent_type, temporal_type, sub_queries, keywords = parsed

            # Fallback: if recall intent but LLM didn't return keywords,
            # extract action words from sub-queries as basic keywords.
            # No synonym expansion, but at least the original terms are used.
            if intent_type == "recall" and not keywords:
                _stop = {"the", "a", "an", "on", "in", "of", "to", "by", "with", "and", "or",
                         "is", "was", "her", "his", "him", "she", "he", "not", "had", "has",
                         "did", "does", "that", "this", "from", "for", "about", "over", "into"}
                for sq in sub_queries:
                    for w in sq.lower().split():
                        if len(w) >= 4 and w not in _stop:
                            keywords.append(w)
                if keywords:
                    keywords = list(dict.fromkeys(keywords))  # deduplicate preserving order
                    logger.info(f"[SEMANTIC DECOMPOSE] Generated fallback keywords from sub-queries: {keywords}")

            logger.info(f"[SEMANTIC DECOMPOSE] Intent: {intent_type or 'direct (default)'}, "
                       f"Temporal: {temporal_type or 'any (default)'}, "
                       f"Sub-queries: {sub_queries}"
                       + (f", Keywords: {keywords}" if keywords else ""))

            # Try recall agent for recall intents
            improved_text, mq_top_score = None, 0.0

            if intent_type == "recall":
                from ..agent.recall_agent import run_recall_agent

                # Wrap generate_for_task as the LLM interface the agent runner expects
                _self = self
                _user_id = user_id
                _user_settings = user_settings
                _allow_thinking = _user_settings.get('extraction_model_settings', {}).get('thinking_enabled_memory', True)
                class _AgentLLM:
                    async def generate_with_messages(self, messages, max_tokens=None, **kwargs):
                        return await _self.generate_for_task(
                            messages=messages,
                            user_id=_user_id,
                            user_settings=_user_settings,
                            max_tokens=max_tokens,
                            task_type="agent",
                            allow_thinking=_allow_thinking,
                        )
                agent_llm = _AgentLLM()

                agent_result = await run_recall_agent(
                    extraction_service=agent_llm,
                    semantic_memory=ctx_mgr.semantic_memory,
                    context_manager=ctx_mgr,
                    db=db,
                    story_id=search_state.get("story_id", 0),
                    branch_id=search_state.get("branch_id"),
                    user_intent=user_intent,
                    char_context=char_context,
                    exclude_sequences=search_state.get("exclude_sequences"),
                    token_budget=search_state.get("token_budget", 2000),
                    prompt_debug=settings.prompt_debug,
                )
                if agent_result:
                    improved_text, mq_top_score = agent_result
                    logger.info(f"[SEMANTIC DECOMPOSE] Recall agent succeeded")

            # Deterministic pipeline: all non-recall intents, or agent failed/disabled
            if not improved_text:
                improved_text, mq_top_score = await ctx_mgr.search_and_format_multi_query(
                    sub_queries=sub_queries,
                    context=context,
                    db=db,
                    intent_type=intent_type,
                    temporal_type=temporal_type,
                    user_intent=user_intent,
                    keywords=keywords
                )

            if not improved_text:
                logger.info("[SEMANTIC DECOMPOSE] Multi-query search returned no results")
                return False

            # Quality gate: only replace single-query if multi-query found good matches.
            # Content verification scores below 0.6 indicate sub-queries don't match story
            # vocabulary well — single-query keyword matching is likely better.
            min_quality = 0.60
            if mq_top_score < min_quality:
                logger.info(f"[SEMANTIC DECOMPOSE] Multi-query top score {mq_top_score:.3f} < {min_quality} — "
                           f"keeping single-query results (sub-queries too generic)")
                return False

            # Find and replace the RELATED PAST SCENES message
            replaced = False
            for i, msg in enumerate(messages):
                if msg.get("role") == "user" and "=== RELATED PAST SCENES ===" in msg.get("content", ""):
                    messages[i]["content"] = (
                        "=== RELATED PAST SCENES ===\n"
                        "The following scenes from earlier in the story are directly relevant to what happens next. "
                        "Use these details - DO NOT invent or contradict what's described here:\n\n"
                        + improved_text
                    )
                    replaced = True
                    break

            if not replaced:
                # Add as new message before the last message (task message)
                new_msg = {
                    "role": "user",
                    "content": (
                        "=== RELATED PAST SCENES ===\n"
                        "The following scenes from earlier in the story are directly relevant to what happens next. "
                        "Use these details - DO NOT invent or contradict what's described here:\n\n"
                        + improved_text
                    )
                }
                # Insert before the last message (which is the task instruction)
                if len(messages) > 1:
                    messages.insert(-1, new_msg)
                else:
                    messages.append(new_msg)

            # Update context so subsequent calls (choices, variant) in the same request
            # cycle use the improved text — this is critical for TabbyAPI prefix cache hits.
            context["semantic_scenes_text"] = improved_text
            context["_semantic_improved"] = True

            logger.info(f"[SEMANTIC DECOMPOSE] Successfully improved semantic scenes with "
                       f"{len(sub_queries)} sub-queries (replaced={replaced}, top_score={mq_top_score:.3f})")
            return True

        except Exception as e:
            logger.warning(f"[SEMANTIC DECOMPOSE] Failed (falling back to single-query): {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    _VALID_INTENTS = {"direct", "recall", "react"}
    _VALID_TEMPORALS = {"earliest", "latest", "any"}

    def _parse_decomposition_response(self, response: str) -> Optional[tuple]:
        """Parse the intent-aware JSON from the decomposition LLM response.

        Returns:
            (intent_type, temporal_type, queries) tuple where intent_type is one of
            "direct"/"recall"/"react" or None (treated as direct),
            temporal_type is "earliest"/"latest"/"any" or None,
            or None if parsing fails entirely.
        """
        def _extract_fields(result: dict) -> Optional[tuple]:
            """Extract intent, temporal, queries, keywords from a parsed dict."""
            queries = result.get("queries")
            if not isinstance(queries, list) or not all(isinstance(s, str) for s in queries):
                return None
            intent = result.get("intent", "").lower().strip()
            intent = intent if intent in self._VALID_INTENTS else None
            temporal = result.get("temporal", "").lower().strip()
            temporal = temporal if temporal in self._VALID_TEMPORALS else None
            parsed = [s.strip() for s in queries[:6] if s.strip()]
            # Extract LLM-provided keywords (synonym expansions for recall queries)
            kw_raw = result.get("keywords", [])
            keywords = [k.strip().lower() for k in kw_raw if isinstance(k, str) and k.strip()] if isinstance(kw_raw, list) else []
            return (intent, temporal, parsed, keywords) if parsed else None

        try:
            # Strip markdown fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            # Try direct parse
            result = json.loads(cleaned)

            # New format: {"intent": "...", "temporal": "...", "queries": [...]}
            if isinstance(result, dict) and "queries" in result:
                return _extract_fields(result)

            # Handle array-wrapped response: [{"intent": ..., "queries": [...]}]
            if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
                return _extract_fields(result[0])

            # Fallback: plain array (legacy or model ignoring new format)
            if isinstance(result, list) and all(isinstance(s, str) for s in result):
                parsed = [s.strip() for s in result[:6] if s.strip()]
                return (None, None, parsed, []) if parsed else None

            # Try extracting JSON object or array from response
            obj_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if obj_match:
                result = json.loads(obj_match.group())
                if isinstance(result, dict) and "queries" in result:
                    return _extract_fields(result)

            arr_match = re.search(r'\[.*?\]', cleaned, re.DOTALL)
            if arr_match:
                result = json.loads(arr_match.group())
                if isinstance(result, list) and all(isinstance(s, str) for s in result):
                    parsed = [s.strip() for s in result[:6] if s.strip()]
                    return (None, None, parsed, []) if parsed else None

        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"[SEMANTIC DECOMPOSE] JSON parse failed: {e}, response: {response[:200]}")

        return None

    def _get_extraction_service(self, user_settings: Dict[str, Any]):
        """
        Get extraction LLM service if enabled and configured.

        Returns:
            ExtractionLLMService instance or None if not available
        """
        from .extraction_service import ExtractionLLMService
        return ExtractionLLMService.from_settings(user_settings)

    def _format_context_as_messages(self, context: Dict[str, Any], scene_batch_size: int = 10) -> List[Dict[str, str]]:
        """
        Format context as multiple user messages for better LLM cache utilization.

        By splitting context into multiple user messages, we improve cache hit rates:
        - Earlier messages (story foundation, chapter summaries) remain stable
        - Only later messages (semantic events, recent scenes) change frequently
        - Scenes are batched into groups aligned with extraction intervals for optimal caching
        - Character info grouped together for coherence and cache optimization

        Message order (most stable → most dynamic):
        1. Story Foundation: genre, tone, setting, scenario, characters (per story)
        2. Character Dialogue Styles: voice/speech patterns (per story)
        3. Story History: cumulative summary of previous chapters (per chapter)
        4. Chapter Direction: plot milestones, climax, resolution (static per chapter)
        5. Completed Scene Batches: stable scene history (per batch)
        6. Character Interaction History: firsts between characters (rarely changes)
        7. Continuity Warnings: unresolved contradictions (if any)
        8. Current Chapter: location, time, scenario, progress (updates ~every 10 scenes)
        ──── cache break point ────
        10. Recent Scenes: active scene batch (changes every scene)
        11. Relevant Context: character context (changes every scene)
        12. Related Past Scenes: semantic search results (changes every scene)
        13. Pacing Guidance: adaptive next-beat nudge (changes every scene)

        NOTE: Chapter Plot Guidance and Pacing are NOT included in prefix.
        Plot guidance is passed only to choice generation via the task message.

        Args:
            context: Context dictionary from context_manager
            scene_batch_size: Number of scenes per batch for caching optimization (default: 10)

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        messages = []
        
        # === MESSAGE 1: Story Foundation (stable per story) ===
        foundation_parts = []
        
        if context.get("genre"):
            foundation_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            foundation_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            foundation_parts.append(f"Setting: {context['world_setting']}")
        
        if context.get("scenario"):
            foundation_parts.append(f"Story Scenario: {context['scenario']}")
        
        if context.get("initial_premise"):
            foundation_parts.append(f"Initial Premise: {context['initial_premise']}")
        
        # Characters section (without voice styles - those go in a separate message)
        characters = context.get("characters")
        if characters:
            char_text = self._format_characters_section(characters, include_voice_style=False)
            if char_text:
                foundation_parts.append(char_text)

        if foundation_parts:
            messages.append({
                "role": "user",
                "content": "=== STORY FOUNDATION ===\n" + "\n\n".join(foundation_parts)
            })

        # === MESSAGE 1.5: Character Dialogue Styles (separate for prominence) ===
        # This is placed in its own message to ensure the LLM treats voice styles as important
        if characters:
            voice_styles_text = self._format_character_voice_styles(characters)
            if voice_styles_text:
                messages.append({
                    "role": "user",
                    "content": "=== CHARACTER DIALOGUE STYLES ===\nIMPORTANT: Each character below has a specific way of speaking. You MUST write their dialogue following these instructions exactly.\n\n" + voice_styles_text
                })

        # === MESSAGE 2: STORY HISTORY (cumulative summary of previous chapters) ===
        # Only story_so_far - previous_chapter_summary is redundant as it's included in story_so_far
        if context.get("story_so_far"):
            # Clean scene numbers from summary to avoid teaching LLM to generate them
            cleaned_story_so_far = clean_scene_numbers_from_summary(context['story_so_far'])
            messages.append({
                "role": "user",
                "content": "=== STORY HISTORY ===\n" + cleaned_story_so_far
            })

        # === MESSAGE 3: CHAPTER DIRECTION (static chapter arc - does not change per scene) ===
        # Moved BEFORE CURRENT CHAPTER for cache optimization:
        # CHAPTER DIRECTION is static per chapter, while CURRENT CHAPTER updates ~every 10 scenes
        # (auto_summary). Placing static content first means auto_summary updates don't invalidate
        # the ~30K of scene batches + interaction data that follows.
        chapter_plot = context.get("chapter_plot")
        if chapter_plot:
            direction_parts = []

            if chapter_plot.get("key_events"):
                events = chapter_plot["key_events"]
                if isinstance(events, list) and events:
                    events_formatted = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(events))
                    direction_parts.append(f"Plot Milestones:\n{events_formatted}")

            if chapter_plot.get("climax"):
                direction_parts.append(f"Climax: {chapter_plot['climax']}")

            if chapter_plot.get("resolution"):
                direction_parts.append(f"Resolution: {chapter_plot['resolution']}")

            if direction_parts:
                messages.append({
                    "role": "user",
                    "content": "=== CHAPTER DIRECTION ===\n" + "\n\n".join(direction_parts)
                })

        # === MESSAGES 4+: Scene Batches + Suffix Sections ===
        #
        # Full message order (most stable → most dynamic):
        #   1. STORY FOUNDATION (stable per story)
        #   2. CHARACTER DIALOGUE STYLES (stable per story)
        #   3. STORY HISTORY (stable per chapter - cumulative summary)
        #   4. CHAPTER DIRECTION (plot milestones - static per chapter)
        #   A. Completed scene batches (stable per batch, cached)
        #   B. CHARACTER INTERACTION HISTORY (rarely changes, often cached)
        #   F2. CHARACTER DEVELOPMENT LOG (stable, changes only on extraction)
        #   *. CURRENT CHAPTER (location, time, scenario, progress - updates ~every 10 scenes)
        #   ──── DYNAMIC SECTIONS (change every scene, placed at end) ────
        #   G. RECENT SCENES (active scene batch, changes every scene - CACHE BREAKS HERE)
        #   G2. CONTINUITY WARNINGS (changes after each extraction)
        #   H. RELATED PAST SCENES (semantic search — recall intents only)
        #   J. PACING GUIDANCE (adaptive next-beat nudge - LAST before task for max attention)
        #
        # Cache optimization: CURRENT CHAPTER moved after stable sections so its periodic
        # auto_summary updates only invalidate the dynamic tail (which changes every scene anyway).

        previous_scenes_text = context.get("previous_scenes", "")

        # --- Extract structured sections from previous_scenes_text via regex ---
        interaction_history_match = None
        recent_match = None

        if previous_scenes_text:
            interaction_history_match = re.search(
                r'CHARACTER INTERACTION HISTORY:\n(.*?)(?=\n\nRelevant Context:|\n\nRecent Scenes:|$)',
                previous_scenes_text, re.DOTALL
            )
            recent_match = re.search(r'Recent Scenes:(.*?)$', previous_scenes_text, re.DOTALL)

        # --- A. Scene batches (completed + recent) ---
        completed_batch_messages = []
        recent_scenes_message = None

        if recent_match:
            scenes_text = recent_match.group(1).strip()
            scene_messages = self._batch_scenes_as_messages(scenes_text, scene_batch_size)

            if len(scene_messages) > 1:
                completed_batch_messages = scene_messages[:-1]
                recent_scenes_message = scene_messages[-1]
            elif len(scene_messages) == 1:
                recent_scenes_message = scene_messages[0]
        elif previous_scenes_text and not interaction_history_match and not relevant_context_match:
            # No structured sections found — base context_manager returns simple scene list
            completed_batch_messages = [{
                "role": "user",
                "content": "=== STORY PROGRESS ===\n" + previous_scenes_text
            }]

        # Add completed scene batches (stable, cached)
        if completed_batch_messages:
            messages.extend(completed_batch_messages)

        # --- B. CHARACTER INTERACTION HISTORY (rarely changes) ---
        if interaction_history_match:
            messages.append({
                "role": "user",
                "content": "=== CHARACTER INTERACTION HISTORY ===\n(Factual record of what has occurred between characters)\n\n" + interaction_history_match.group(1).strip()
            })

        # --- C. CHARACTER STATES — REMOVED ---
        # Entity states extraction quality was too poor to provide value.
        # Token budget freed up for semantic search results.

        # --- D. CHARACTER RELATIONSHIPS — REMOVED ---
        # Relationship extraction removed — low ROI for the extra LLM call cost.

        # --- E. STORY FOCUS — REMOVED ---
        # Plot events extraction (which fed active_threads) cut. Minimal ROI.
        # Working memory contradictions still available via CONTINUITY WARNINGS.

        # --- F2. CHARACTER DEVELOPMENT LOG (stable, changes only on extraction) ---
        chronicle_context = context.get("chronicle_context")
        if chronicle_context:
            messages.append({
                "role": "user",
                "content": "=== CHARACTER DEVELOPMENT LOG ===\n"
                    "Significant character developments and location events accumulated over the story. "
                    "Use this to maintain consistent characterization and acknowledge past events naturally.\n\n"
                    + chronicle_context
            })

        # --- *. CURRENT CHAPTER (updates ~every 10 scenes when auto_summary refreshes) ---
        # Placed after stable sections (scene batches, interactions, warnings)
        # so that periodic auto_summary updates only invalidate the dynamic tail below.
        current_chapter_parts = []

        if context.get("chapter_location"):
            current_chapter_parts.append(f"Location: {context['chapter_location']}")
        if context.get("chapter_time_period"):
            current_chapter_parts.append(f"Time: {context['chapter_time_period']}")
        if context.get("chapter_scenario"):
            current_chapter_parts.append(f"Scenario: {context['chapter_scenario']}")
        if context.get("current_chapter_summary"):
            # Clean scene numbers from summary to avoid teaching LLM to generate them
            cleaned_summary = clean_scene_numbers_from_summary(context['current_chapter_summary'])
            current_chapter_parts.append(f"Progress So Far:\n{cleaned_summary}")

        if current_chapter_parts:
            messages.append({
                "role": "user",
                "content": "=== CURRENT CHAPTER ===\n" + "\n\n".join(current_chapter_parts)
            })

        # ──── DYNAMIC SECTIONS BELOW (change every scene, cache breaks here) ────

        # --- G. RECENT SCENES (active scene batch, changes every scene - CACHE BREAKS HERE) ---
        if recent_scenes_message:
            messages.append(recent_scenes_message)

        # --- G2. CONTINUITY WARNINGS (changes after each extraction) ---
        contradiction_context = context.get("contradiction_context")
        if contradiction_context:
            messages.append({
                "role": "user",
                "content": "=== CONTINUITY WARNINGS ===\n"
                    "The following continuity issues were detected. "
                    "Naturally address or acknowledge them in your writing "
                    "(e.g., mention travel between locations, explain emotional shifts):\n\n"
                    + "\n".join(contradiction_context)
            })

        # --- H. RELEVANT CONTEXT — REMOVED ---
        # _get_character_context() is a stub (always returns None), so this message
        # was never populated. Kept as placeholder for future CharacterMemoryService.

        # --- I. RELATED PAST SCENES (semantic search results) ---
        semantic_scenes_text = context.get("semantic_scenes_text")
        if semantic_scenes_text:
            messages.append({
                "role": "user",
                "content": "=== RELATED PAST SCENES ===\n"
                    "These are ACTUAL scenes from earlier in the story. When referencing past events, "
                    "use ONLY details found here — do not invent, embellish, or assume what happened. "
                    "If a past event isn't in these scenes, don't reference it.\n\n"
                    + semantic_scenes_text
            })

        # --- J. PACING GUIDANCE (adaptive next-beat nudge - LAST before task) ---
        # Positioned last for maximum LLM attention when generating the scene.
        # Generated by ChapterProgressService.generate_pacing_guidance() with adaptive urgency.
        pacing_guidance = context.get("pacing_guidance")
        if pacing_guidance:
            messages.append({
                "role": "user",
                "content": "=== PACING GUIDANCE ===\n" + pacing_guidance
            })

        return messages
    
    def _batch_scenes_as_messages(self, scenes_text: str, batch_size: int = 10) -> List[Dict[str, str]]:
        """Batch scenes as messages. Delegates to context_formatter module."""
        return batch_scenes_as_messages(scenes_text, batch_size)
    
    def _format_context_for_scene(self, context: Dict[str, Any], exclude_last_scene: bool = False) -> str:
        """Format context for scene generation, handling active/inactive characters
        
        Args:
            context: Context dictionary
            exclude_last_scene: If True, exclude the most recent scene from previous_scenes
                              (used for guided enhancement to avoid duplication)
        """
        context_parts = []
        
        # Check if this is the first scene with user prompt
        is_first_scene = context.get("is_first_scene", False)
        user_prompt_provided = context.get("user_prompt_provided", False)
        enhancement_guidance = context.get("enhancement_guidance", "")
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            context_parts.append(f"Setting: {context['world_setting']}")
        
        # For first scene with user prompt, prioritize user prompt over scenario
        if is_first_scene and user_prompt_provided and context.get("current_situation"):
            # User prompt takes precedence for first scene
            if context.get("scenario"):
                context_parts.append(f"Story Scenario (for reference): {context['scenario']}")
        else:
            # Normal order: scenario first
            if context.get("scenario"):
                context_parts.append(f"Story Scenario: {context['scenario']}")
        
        if context.get("initial_premise"):
            context_parts.append(f"Initial Premise: {context['initial_premise']}")
        
        # Handle characters - check if we have active/inactive separation
        characters = context.get("characters")
        if characters:
            # Check if characters is a dict with active_characters/inactive_characters
            if isinstance(characters, dict) and "active_characters" in characters:
                # Format active and inactive characters separately
                active_chars = characters.get("active_characters", [])
                inactive_chars = characters.get("inactive_characters", [])
                
                char_descriptions = []
                
                # Active characters - full details
                if active_chars:
                    char_descriptions.append("Active Characters (in this chapter):")
                    for char in active_chars:
                        char_desc = f"- {char.get('name', 'Unknown')}"
                        if char.get('role'):
                            char_desc += f" ({char['role']})"
                        char_desc += f": {char.get('description', 'No description')}"
                        if char.get('personality'):
                            char_desc += f". Personality: {char['personality']}"
                        if char.get('background'):
                            char_desc += f". Background: {char['background']}"
                        if char.get('goals'):
                            char_desc += f". Goals: {char['goals']}"
                        if char.get('fears'):
                            char_desc += f". Fears & Weaknesses: {char['fears']}"
                        if char.get('appearance'):
                            char_desc += f". Appearance: {char['appearance']}"
                        # Add voice/speech style if specified
                        if char.get('voice_style'):
                            voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                            if voice_instruction:
                                char_desc += f"\n  {voice_instruction}"
                        char_descriptions.append(char_desc)
                
                # Inactive characters - brief format
                if inactive_chars:
                    char_descriptions.append("\nInactive Characters (available for reference):")
                    for char in inactive_chars:
                        char_desc = f"- {char.get('name', 'Unknown')}"
                        if char.get('role'):
                            char_desc += f" ({char['role']})"
                        char_descriptions.append(char_desc)
                
                if char_descriptions:
                    context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
            else:
                # Legacy format - all characters are active
                char_descriptions = []
                for char in characters:
                    char_desc = f"- {char.get('name', 'Unknown')}"
                    if char.get('role'):
                        char_desc += f" ({char['role']})"
                    char_desc += f": {char.get('description', 'No description')}"
                    if char.get('personality'):
                        char_desc += f". Personality: {char['personality']}"
                    if char.get('background'):
                        char_desc += f". Background: {char['background']}"
                    if char.get('goals'):
                        char_desc += f". Goals: {char['goals']}"
                    if char.get('fears'):
                        char_desc += f". Fears & Weaknesses: {char['fears']}"
                    if char.get('appearance'):
                        char_desc += f". Appearance: {char['appearance']}"
                    # Add voice/speech style if specified
                    if char.get('voice_style'):
                        voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                        if voice_instruction:
                            char_desc += f"\n  {voice_instruction}"
                    char_descriptions.append(char_desc)
                context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
        
        # Add chapter-specific context if available
        if context.get("chapter_location"):
            context_parts.append(f"Chapter Location: {context['chapter_location']}")
        if context.get("chapter_time_period"):
            context_parts.append(f"Chapter Time Period: {context['chapter_time_period']}")
        if context.get("chapter_scenario"):
            context_parts.append(f"Chapter Scenario: {context['chapter_scenario']}")
        
        # Add story_so_far if available (cumulative summary of all previous chapters)
        # Note: previous_chapter_summary removed as it's redundant with story_so_far
        story_so_far = context.get("story_so_far")
        if story_so_far:
            # Clean scene numbers from summary to avoid teaching LLM to generate them
            story_so_far = clean_scene_numbers_from_summary(story_so_far)
            logger.info(f"[CONTEXT FORMAT] Including story_so_far ({len(story_so_far)} chars)")
            context_parts.append(f"Story So Far:\n{story_so_far}")
        else:
            logger.info("[CONTEXT FORMAT] story_so_far is None or empty, not including")

        # Add current chapter summary if available (summary of this chapter's progress so far)
        current_chapter_summary = context.get("current_chapter_summary")
        if current_chapter_summary:
            # Clean scene numbers from summary to avoid teaching LLM to generate them
            current_chapter_summary = clean_scene_numbers_from_summary(current_chapter_summary)
            logger.info(f"[CONTEXT FORMAT] Including current_chapter_summary ({len(current_chapter_summary)} chars)")
            context_parts.append(f"Current Chapter Summary:\n{current_chapter_summary}")
        else:
            logger.info("[CONTEXT FORMAT] current_chapter_summary is None or empty, not including")
        
        # Parse and organize previous_scenes into clear sections
        if context.get("previous_scenes"):
            previous_scenes_text = context['previous_scenes']
            
            # Exclude last scene if requested (for guided enhancement)
            if exclude_last_scene and previous_scenes_text:
                import re
                # Find all scene markers (Scene N: pattern)
                # Match everything from "Scene N:" to either next "Scene M:" or end of string
                scene_pattern = r'(Scene \d+:.*?)(?=\n\nScene \d+:|$)'
                scenes = re.findall(scene_pattern, previous_scenes_text, re.DOTALL)
                
                if scenes:
                    # Find the position of the last scene in the original text
                    # Get all scene numbers to find the highest one
                    scene_numbers = []
                    for scene_text in scenes:
                        match = re.search(r'Scene (\d+):', scene_text)
                        if match:
                            scene_numbers.append((int(match.group(1)), scene_text))
                    
                    if scene_numbers:
                        # Sort by scene number and get the highest
                        scene_numbers.sort(key=lambda x: x[0])
                        last_scene_num, last_scene_text = scene_numbers[-1]
                        
                        # Remove the last scene from the text
                        # Find the position of the last scene and remove it
                        last_scene_start = previous_scenes_text.rfind(f"Scene {last_scene_num}:")
                        if last_scene_start != -1:
                            # Remove from the last scene marker to the end
                            # But preserve any content before it (like summaries)
                            previous_scenes_text = previous_scenes_text[:last_scene_start].rstrip()
                            logger.info(f"Excluded Scene {last_scene_num} from previous events for guided enhancement")
            
            # Parse previous_scenes_text into organized sections
            import re
            
            # Try NEW format first: "Relevant Context:" combined section
            relevant_context_match = re.search(r'Relevant Context:\n(.*?)(?=\n\nRecent Scenes:|$)', previous_scenes_text, re.DOTALL)
            recent_scenes_match = re.search(r'Recent Scenes:(.*?)$', previous_scenes_text, re.DOTALL)
            
            # Extract CHARACTER INTERACTION HISTORY (if present) - placed before Relevant Context for cache optimization
            interaction_history_match = re.search(r'CHARACTER INTERACTION HISTORY:\n(.*?)(?=\n\nRelevant Context:|$)', previous_scenes_text, re.DOTALL)
            interaction_history_content = interaction_history_match.group(0).strip() if interaction_history_match else None
            
            # Extract Current Chapter Summary (if present) - works with both old and new format
            current_chapter_summary_match = re.search(r'Current Chapter Summary[^:]*:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Context|CHARACTER INTERACTION HISTORY|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Active Objects)|$)', previous_scenes_text, re.DOTALL)
            current_chapter_summary = current_chapter_summary_match.group(1).strip() if current_chapter_summary_match else None
            
            if relevant_context_match:
                # NEW FORMAT: Combined "Relevant Context" section
                relevant_context_content = relevant_context_match.group(1).strip()
                recent_scenes_content = recent_scenes_match.group(1).strip() if recent_scenes_match else None
                
                # Add Current Chapter Progress (positioned before relevant context)
                if current_chapter_summary:
                    context_parts.append("Current Chapter Progress:")
                    context_parts.append(f"  Current Chapter Summary:\n  {current_chapter_summary.replace(chr(10), chr(10) + '  ')}")
                
                # Add Character Interaction History (stable, placed before Relevant Context for cache optimization)
                if interaction_history_content:
                    context_parts.append(f"\n{interaction_history_content}")
                
                # Add Relevant Context (combined semantic events + entity states)
                if relevant_context_content:
                    context_parts.append(f"\nRelevant Context:\n{relevant_context_content}")
                
                # Add Recent Scenes
                if recent_scenes_content:
                    context_parts.append(f"\nRecent Scenes:\n{recent_scenes_content}")
            else:
                # OLD FORMAT (backward compatibility): Separate sections
                recent_scenes_content = re.search(r'Recent Scenes:\s*(.*?)(?=\n+(?:Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
                recent_scenes_content = recent_scenes_content.group(1).strip() if recent_scenes_content else None
                
                # Extract Relevant Past Events (semantic search results)
                relevant_events_match = re.search(r'Relevant Past Events:\s*(.*?)(?=\n+(?:Recent Scenes|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
                relevant_events_content = relevant_events_match.group(1).strip() if relevant_events_match else None
                
                # Extract Entity States sections (may have leading newlines)
                entity_states_match = re.search(r'\n*(CURRENT CHARACTER STATES:.*?)(?=\n+(?:CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events)|$)', previous_scenes_text, re.DOTALL)
                entity_states_content = entity_states_match.group(1).strip() if entity_states_match else None
                
                locations_match = re.search(r'\n*CURRENT LOCATIONS:\s*(.*?)(?=\n+(?:IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES)|$)', previous_scenes_text, re.DOTALL)
                locations_content = locations_match.group(1).strip() if locations_match else None
                
                # Support both old and new object header names (may have leading newlines)
                objects_match = re.search(r'\n*(?:Notable Objects|Active Objects):\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
                if not objects_match:
                    objects_match = re.search(r'\n*IMPORTANT OBJECTS:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
                objects_content = objects_match.group(1).strip() if objects_match else None
                
                # Build organized context sections
                # Add Current State section if we have entity states
                if entity_states_content or locations_content or objects_content:
                    context_parts.append("Current State:")
                    
                    if entity_states_content:
                        context_parts.append(f"  {entity_states_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if locations_content:
                        context_parts.append(f"\n  CURRENT LOCATIONS:\n  {locations_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if objects_content:
                        context_parts.append(f"\n  Active Objects:\n  {objects_content.replace(chr(10), chr(10) + '  ')}")
                
                # Add Current Chapter Progress
                if current_chapter_summary or recent_scenes_content or relevant_events_content:
                    context_parts.append("\nCurrent Chapter Progress:")
                    
                    if current_chapter_summary:
                        context_parts.append(f"  Current Chapter Summary:\n  {current_chapter_summary.replace(chr(10), chr(10) + '  ')}")
                    
                    if relevant_events_content:
                        context_parts.append(f"\n  Relevant Past Events (from semantic search):\n  {relevant_events_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if recent_scenes_content:
                        context_parts.append(f"\n  Recent Scenes:\n  {recent_scenes_content.replace(chr(10), chr(10) + '  ')}")
                
                # If parsing failed, fall back to original format
                if not (current_chapter_summary or recent_scenes_content or relevant_events_content or entity_states_content):
                    context_parts.append(f"Previous Events:\n{previous_scenes_text}")
        
        return "\n\n".join(context_parts)
    
    def _format_context_for_continuation(self, context: Dict[str, Any]) -> str:
        """Format context for scene continuation. Delegates to context_formatter module."""
        return format_context_for_continuation(context)

    def _format_context_for_choices(self, context: Dict[str, Any]) -> str:
        """Format context for choice generation - reuses scene formatting for cache hits."""
        return self._format_context_for_scene(context, exclude_last_scene=False)

    def _format_context_for_scenario(self, context: Dict[str, Any]) -> str:
        """Format context for scenario generation. Delegates to context_formatter module."""
        return format_context_for_scenario(context)

    def _format_elements_for_scenario(self, context: Dict[str, Any]) -> str:
        """Format story elements for scenario. Delegates to context_formatter module."""
        return format_elements_for_scenario(context)

    def _format_context_for_plot(self, context: Dict[str, Any]) -> str:
        """Format context for plot generation. Delegates to context_formatter module."""
        return format_context_for_plot(context)

    def _format_context_for_chapters(self, context: Dict[str, Any]) -> str:
        """Format context for chapter generation. Delegates to context_formatter module."""
        return format_context_for_chapters(context)

    def _format_context_for_summary(self, context: Dict[str, Any]) -> str:
        """Format context for summary generation. Delegates to context_formatter module."""
        return format_context_for_summary(context)
    
    def _get_plot_point_name(self, index: int) -> str:
        """Get plot point name by index. Delegates to plot_parser module."""
        return get_plot_point_name(index)
    
    def _parse_plot_points_json(self, response: str) -> List[str]:
        """Parse plot points from JSON. Delegates to plot_parser module."""
        return parse_plot_points_json(response)
    
    def _parse_plot_points(self, response: str) -> List[str]:
        """Parse plot points from response. Delegates to plot_parser module."""
        return parse_plot_points(response)

    def _clean_plot_point(self, text: str, plot_point_names: List[str]) -> str:
        """Clean a plot point. Delegates to plot_parser module."""
        return clean_plot_point(text, plot_point_names)

    # Scene Variant Database Operations
    def _get_active_branch_id(self, db: Session, story_id: int) -> int:
        """Get the active branch ID for a story.

        Wrapper for SceneDatabaseOperations.get_active_branch_id.
        """
        return self._scene_db_ops.get_active_branch_id(db, story_id)
    
    def create_scene_with_variant(
        self,
        db: Session,
        story_id: int,
        sequence_number: int,
        content: str,
        title: str = None,
        custom_prompt: str = None,
        choices: List[Dict[str, Any]] = None,
        generation_method: str = "auto",
        branch_id: int = None,
        chapter_id: int = None,
        entity_states_snapshot: str = None,
        context_snapshot: str = None
    ) -> Tuple[Any, Any]:
        """Create a new scene with its first variant.

        Wrapper for SceneDatabaseOperations.create_scene_with_variant.

        Args:
            entity_states_snapshot: Entity states text at generation time for cache consistency (legacy)
            context_snapshot: Full context snapshot JSON for complete cache consistency
        """
        return self._scene_db_ops.create_scene_with_variant(
            db, story_id, sequence_number, content, title,
            custom_prompt, choices, generation_method, branch_id, chapter_id,
            entity_states_snapshot=entity_states_snapshot,
            context_snapshot=context_snapshot
        )

    async def regenerate_scene_variant(
        self,
        db: Session,
        scene_id: int,
        custom_prompt: str = None,
        user_id: int = None,
        user_settings: dict = None,
        branch_id: int = None
    ) -> Any:
        """
        Create a new variant for an existing scene.

        Uses the unified cache-friendly message structure for better cache hits.
        Returns the variant with scene content and inline choices.
        """
        from ...models import Scene, SceneVariant, Story, SceneChoice
        from ..context_manager import ContextManager

        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            raise ValueError(f"Scene {scene_id} not found")

        # Get the next variant number
        max_variant = db.query(SceneVariant.variant_number)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(desc(SceneVariant.variant_number))\
            .first()

        next_variant_number = (max_variant[0] if max_variant else 0) + 1

        # Get story for context
        story = db.query(Story).filter(Story.id == scene.story_id).first()
        if not story:
            raise ValueError(f"Story {scene.story_id} not found")

        # Use provided branch_id or fall back to story's current branch
        effective_branch_id = branch_id or story.current_branch_id

        # Build context using ContextManager
        context_manager = ContextManager(user_settings=user_settings or {})

        # Get original variant for reference
        original_variant = db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id, SceneVariant.is_original == True)\
            .first()

        # Set enhancement_guidance if custom_prompt was provided (for guided enhancement)
        if custom_prompt:
            context = await context_manager.build_scene_generation_context(
                story.id, db, custom_prompt=custom_prompt, exclude_scene_id=scene_id,
                branch_id=effective_branch_id, is_variant_generation=True
            )
            # Add enhancement_guidance for _build_variant_task_message to pick up
            context["enhancement_guidance"] = custom_prompt
        else:
            context = await context_manager.build_scene_generation_context(
                story.id, db, exclude_scene_id=scene_id, branch_id=effective_branch_id
            )

        # Generate new content with inline choices using unified cache-friendly method
        if original_variant:
            new_content, choices = await self.generate_variant_with_choices(
                original_scene=original_variant.content,
                context=context,
                user_id=user_id,
                user_settings=user_settings or {},
                db=db
            )
        else:
            # Generate new scene if no original exists
            new_content, choices = await self.generate_scene_with_choices(
                context=context,
                user_id=user_id,
                user_settings=user_settings or {},
                db=db
            )

        # Create the new variant
        variant = SceneVariant(
            scene_id=scene_id,
            variant_number=next_variant_number,
            is_original=False,
            content=new_content,
            title=scene.title,
            original_content=original_variant.content if original_variant else new_content,
            generation_prompt=custom_prompt,
            generation_method="regeneration"
        )

        db.add(variant)
        db.flush()  # Get variant ID for choice creation

        # Create choices if parsed from inline generation
        if choices and len(choices) >= 2:
            for idx, choice_text in enumerate(choices, 1):
                choice = SceneChoice(
                    scene_id=scene_id,
                    scene_variant_id=variant.id,
                    branch_id=effective_branch_id,
                    choice_text=choice_text,
                    choice_order=idx
                )
                db.add(choice)
            logger.info(f"Created {len(choices)} inline choices for variant {variant.id}")

        db.commit()

        logger.info(f"Successfully created variant {variant.id} (#{next_variant_number}) for scene {scene_id}")
        return variant

    def switch_to_variant(self, db: Session, story_id: int, scene_id: int, variant_id: int, branch_id: int = None) -> bool:
        """Switch the active variant for a scene in the story flow.

        Wrapper for SceneDatabaseOperations.switch_to_variant.
        """
        return self._scene_db_ops.switch_to_variant(db, story_id, scene_id, variant_id, branch_id)

    def get_scene_variants(self, db: Session, scene_id: int) -> List[Any]:
        """Get all variants for a scene.

        Wrapper for SceneDatabaseOperations.get_scene_variants.
        """
        return self._scene_db_ops.get_scene_variants(db, scene_id)

    def get_active_scene_count(self, db: Session, story_id: int, chapter_id: Optional[int] = None, branch_id: int = None) -> int:
        """
        Get count of active scenes from StoryFlow.

        Wrapper for SceneDatabaseOperations.get_active_scene_count.

        Args:
            db: Database session
            story_id: Story ID
            chapter_id: Optional chapter ID to filter scenes by chapter
            branch_id: Optional branch ID for filtering

        Returns:
            Count of active scenes in the story flow
        """
        return self._scene_db_ops.get_active_scene_count(db, story_id, chapter_id, branch_id)
    
    def get_active_story_flow(self, db: Session, story_id: int, branch_id: int = None, chapter_id: int = None) -> List[Dict[str, Any]]:
        """Get the active story flow with scene variants.

        Wrapper for SceneDatabaseOperations.get_active_story_flow.

        Args:
            chapter_id: If provided, only return scenes for this chapter
        """
        return self._scene_db_ops.get_active_story_flow(db, story_id, branch_id, chapter_id)

    def _update_story_flow(self, db: Session, story_id: int, sequence_number: int, scene_id: int, variant_id: int, branch_id: int = None):
        """Update or create story flow entry.

        Wrapper for SceneDatabaseOperations.update_story_flow.
        """
        return self._scene_db_ops.update_story_flow(db, story_id, sequence_number, scene_id, variant_id, branch_id)

    async def delete_scenes_from_sequence(self, db: Session, story_id: int, sequence_number: int, skip_restoration: bool = False, branch_id: int = None) -> bool:
        """Delete all scenes from a given sequence number onwards.

        Wrapper for SceneDatabaseOperations.delete_scenes_from_sequence.
        """
        return await self._scene_db_ops.delete_scenes_from_sequence(
            db, story_id, sequence_number, skip_restoration, branch_id
        )

    async def _generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> str:
        """
        Generate with pre-constructed messages array for better cache utilization.
        
        This method accepts a list of messages (system + multiple user messages) and sends
        them directly to the LLM. By splitting context into multiple user messages,
        we improve cache hit rates since earlier messages remain stable while only
        later messages change.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            user_id: User ID for client configuration
            user_settings: User settings dict
            max_tokens: Max tokens for generation
            temperature: Temperature for generation
            skip_nsfw_filter: Whether to skip NSFW filter injection
            
        Returns:
            Generated text content
        """
        client = self.get_user_client(user_id, user_settings)

        # Inject content permission (uncensored or family-friendly) into system message
        # Skip if already injected (e.g. by _build_cache_friendly_message_prefix)
        if not skip_nsfw_filter:
            from ...utils.content_filter import get_content_permission_prompt
            user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
            content_prompt = get_content_permission_prompt(user_allow_nsfw)
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                if "CONTENT POLICY:" not in messages[system_idx]["content"] and "CONTENT POLICY -" not in messages[system_idx]["content"]:
                    messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + content_prompt
            else:
                messages.insert(0, {"role": "system", "content": content_prompt})

        # Apply local thinking model control for main LLM
        llm_settings = user_settings.get('llm_settings', {}) if user_settings else {}
        thinking_model_type = llm_settings.get('thinking_model_type') or 'none'
        thinking_enabled_gen = llm_settings.get('thinking_enabled_generation', False)

        if thinking_model_type != 'none' and not thinking_enabled_gen:
            # Apply prompt prefix to suppress thinking (e.g., /no_think for Qwen3)
            if thinking_model_type == 'qwen3':
                messages = [msg.copy() for msg in messages]
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = f"/no_think {messages[i]['content']}"
                        break

        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages

        # Apply API-specific thinking disable params for main LLM
        if thinking_model_type != 'none' and not thinking_enabled_gen:
            if thinking_model_type == 'mistral':
                gen_params["prompt_mode"] = None
            elif thinking_model_type == 'openai':
                gen_params["reasoning_effort"] = "none"
            elif thinking_model_type == 'gemini':
                gen_params["thinking_config"] = {"thinking_budget": 0}
            elif thinking_model_type == 'glm':
                extra = gen_params.get("extra_body", {})
                extra["chat_template_kwargs"] = {"enable_thinking": False}
                gen_params["extra_body"] = extra

        # Get timeout from user settings or fallback to system default
        user_timeout = llm_settings.get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total

        try:
            response = await acompletion(**gen_params)

            # Check finish_reason for truncation
            if hasattr(response, 'choices') and len(response.choices) > 0:
                finish_reason = getattr(response.choices[0], 'finish_reason', None)
                if finish_reason == 'length':
                    logger.warning(f"[TRUNCATION] Response truncated due to token limit! max_tokens={max_tokens}")
                elif finish_reason:
                    logger.debug(f"[GENERATION] Finish reason: {finish_reason}")

            content = response.choices[0].message.content

            # Strip thinking tags from response when local thinking model is enabled
            if thinking_model_type != 'none' and thinking_enabled_gen and content:
                from .extraction_service import THINKING_PATTERNS
                pattern = THINKING_PATTERNS.get(thinking_model_type)
                if not pattern and thinking_model_type == 'custom':
                    custom_pat = llm_settings.get('thinking_model_custom_pattern', '')
                    if custom_pat:
                        try:
                            pattern = re.compile(custom_pat, re.IGNORECASE | re.DOTALL)
                        except re.error:
                            pass
                if pattern:
                    content = pattern.sub("", content).strip()

            return content

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Multi-message generation failed for user {user_id}: {error_msg}")
            raise ValueError(f"LLM generation failed: {error_msg}")

    async def _generate_stream_with_messages(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Streaming generation with pre-constructed messages array for better cache utilization.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            user_id: User ID for client configuration
            user_settings: User settings dict
            max_tokens: Max tokens for generation
            temperature: Temperature for generation
            skip_nsfw_filter: Whether to skip NSFW filter injection
            
        Yields:
            Generated text chunks
        """
        client = self.get_user_client(user_id, user_settings)

        # Inject content permission (uncensored or family-friendly) into system message
        # Skip if already injected (e.g. by _build_cache_friendly_message_prefix)
        if not skip_nsfw_filter:
            from ...utils.content_filter import get_content_permission_prompt
            user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
            content_prompt = get_content_permission_prompt(user_allow_nsfw)
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                if "CONTENT POLICY:" not in messages[system_idx]["content"] and "CONTENT POLICY -" not in messages[system_idx]["content"]:
                    messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + content_prompt
            else:
                messages.insert(0, {"role": "system", "content": content_prompt})

        # Apply local thinking model control for main LLM
        llm_settings = user_settings.get('llm_settings', {}) if user_settings else {}
        thinking_model_type = llm_settings.get('thinking_model_type') or 'none'
        thinking_enabled_gen = llm_settings.get('thinking_enabled_generation', False)

        if thinking_model_type != 'none' and not thinking_enabled_gen:
            # Apply prompt prefix to suppress thinking (e.g., /no_think for Qwen3)
            if thinking_model_type == 'qwen3':
                messages = [msg.copy() for msg in messages]
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        messages[i]["content"] = f"/no_think {messages[i]['content']}"
                        break

        # Get streaming parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        gen_params["stream"] = True

        # Apply API-specific thinking disable params for main LLM
        if thinking_model_type != 'none' and not thinking_enabled_gen:
            if thinking_model_type == 'mistral':
                gen_params["prompt_mode"] = None
            elif thinking_model_type == 'openai':
                gen_params["reasoning_effort"] = "none"
            elif thinking_model_type == 'gemini':
                gen_params["thinking_config"] = {"thinking_budget": 0}
            elif thinking_model_type == 'glm':
                extra = gen_params.get("extra_body", {})
                extra["chat_template_kwargs"] = {"enable_thinking": False}
                gen_params["extra_body"] = extra

        # Get timeout from user settings or fallback to system default
        user_timeout = llm_settings.get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total

        # Write prompt to file for debugging (only if prompt_debug is enabled)
        if settings.prompt_debug:
            try:
                import os
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
                debug_data = {
                    "messages": messages,
                    "generation_parameters": {
                        "max_tokens": gen_params.get('max_tokens'),
                        "temperature": gen_params.get('temperature'),
                        "model": client.model_string
                    }
                }
                with open(prompt_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to write prompt debug file: {e}")
        
        # Check if reasoning should be suppressed (disabled but model may still think)
        suppress_reasoning = client.reasoning_effort == "disabled"
        is_openrouter = "openrouter" in (client.api_url or "").lower()

        try:
            import time
            stream_start = time.monotonic()
            response = await acompletion(**gen_params)

            # Track reasoning content for logging
            has_reasoning = False
            reasoning_chars = 0
            content_chars = 0
            chunk_count = 0
            thinking_signaled = False

            # Stream filter state for local thinking models that embed <think> in content
            # When thinking_model_type is set and thinking is enabled, we parse the content
            # stream to detect <think>...</think> blocks and route them as __THINKING__
            local_think_filter = (thinking_model_type != 'none' and thinking_enabled_gen)
            in_think_block = False
            content_buffer = ""  # Small buffer for tag boundary detection

            async for chunk in response:
                chunk_count += 1
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta

                    # Log first few chunks at INFO level to diagnose empty responses
                    if chunk_count <= 3:
                        delta_fields = {k: v for k, v in vars(delta).items() if v is not None} if hasattr(delta, '__dict__') else str(delta)
                        logger.info(f"[STREAM CHUNK {chunk_count}] fields={delta_fields}")

                    # Check for reasoning content - providers use different field names:
                    # - reasoning_content: LiteLLM's standardized field (Anthropic, DeepSeek)
                    # - reasoning: OpenRouter's field for models like GLM-4.7, Kimi
                    # - thinking: Some models use this field
                    reasoning_text = None
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        reasoning_text = delta.reasoning_content
                    elif hasattr(delta, 'reasoning') and delta.reasoning:
                        reasoning_text = delta.reasoning
                    elif hasattr(delta, 'thinking') and delta.thinking:
                        reasoning_text = delta.thinking

                    if reasoning_text:
                        has_reasoning = True
                        reasoning_chars += len(reasoning_text)
                        if suppress_reasoning:
                            # Yield a single empty thinking marker on first reasoning chunk
                            # so the SSE layer sends thinking_start to the frontend
                            if not thinking_signaled:
                                thinking_signaled = True
                                yield "__THINKING__:"
                        else:
                            # Yield reasoning with special prefix for frontend to detect
                            if not thinking_signaled:
                                thinking_signaled = True
                            yield f"__THINKING__:{reasoning_text}"

                    # Time-based thinking detection for models that think server-side
                    # (e.g. Kimi K2.5 on OpenRouter — no reasoning tokens, just a long
                    # delay before content). If >5s elapsed with no content or reasoning
                    # tokens, signal thinking phase so the UI shows "Thinking..."
                    if (not thinking_signaled and content_chars == 0
                            and reasoning_chars == 0 and is_openrouter
                            and (time.monotonic() - stream_start) > 5.0):
                        thinking_signaled = True
                        logger.info(f"[THINKING DETECT] No content after {time.monotonic() - stream_start:.1f}s — signaling thinking phase")
                        yield "__THINKING__:"

                    # Regular content
                    if hasattr(delta, 'content') and delta.content:
                        text = delta.content

                        # Stream filter for local thinking models (e.g., Qwen3, DeepSeek)
                        # Detects <think>...</think> blocks in the content stream
                        if local_think_filter:
                            content_buffer += text
                            # Process buffer for think tags
                            while content_buffer:
                                if in_think_block:
                                    # Look for </think> closing tag
                                    end_idx = content_buffer.lower().find("</think>")
                                    if end_idx != -1:
                                        # Yield thinking content up to tag
                                        think_text = content_buffer[:end_idx]
                                        if think_text:
                                            reasoning_chars += len(think_text)
                                            yield f"__THINKING__:{think_text}"
                                        content_buffer = content_buffer[end_idx + 8:]  # skip </think>
                                        in_think_block = False
                                    elif len(content_buffer) > 50:
                                        # Flush most of buffer as thinking, keep tail for tag detection
                                        flush = content_buffer[:-8]
                                        content_buffer = content_buffer[-8:]
                                        reasoning_chars += len(flush)
                                        yield f"__THINKING__:{flush}"
                                    else:
                                        break  # Wait for more data
                                else:
                                    # Look for <think> opening tag
                                    start_idx = content_buffer.lower().find("<think>")
                                    if start_idx != -1:
                                        # Yield any content before the tag
                                        before = content_buffer[:start_idx]
                                        if before:
                                            content_chars += len(before)
                                            yield before
                                        content_buffer = content_buffer[start_idx + 7:]  # skip <think>
                                        in_think_block = True
                                        has_reasoning = True
                                        if not thinking_signaled:
                                            thinking_signaled = True
                                    elif len(content_buffer) > 50:
                                        # Flush most of buffer as content, keep tail for tag detection
                                        flush = content_buffer[:-7]
                                        content_buffer = content_buffer[-7:]
                                        content_chars += len(flush)
                                        yield flush
                                    else:
                                        break  # Wait for more data
                        else:
                            content_chars += len(text)
                            yield text

            # Flush remaining buffer for local think filter
            if local_think_filter and content_buffer:
                if in_think_block:
                    reasoning_chars += len(content_buffer)
                    yield f"__THINKING__:{content_buffer}"
                else:
                    content_chars += len(content_buffer)
                    yield content_buffer

            # Log summary
            logger.info(f"[MULTI-MSG STREAMING] chunks={chunk_count}, content_chars={content_chars}, reasoning_chars={reasoning_chars}, thinking_detected={thinking_signaled}")
            if chunk_count > 0 and content_chars == 0:
                if reasoning_chars > 0:
                    logger.warning(f"[MULTI-MSG STREAMING] Got {reasoning_chars} reasoning chars but 0 content chars! Thinking model may have exhausted max_tokens on reasoning.")
                else:
                    logger.warning(f"[MULTI-MSG STREAMING] Received {chunk_count} chunks but no content or reasoning! Check model response format.")
            if has_reasoning:
                logger.info(f"[MULTI-MSG REASONING] Streamed {reasoning_chars} chars of reasoning content (suppressed={suppress_reasoning})")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Multi-message streaming failed for user {user_id}: {error_msg}")
            raise ValueError(f"LLM streaming failed: {error_msg}")
