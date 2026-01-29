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
from .templates import TextCompletionTemplateManager
from .thinking_parser import ThinkingTagParser
from .content_cleaner import (
    clean_scene_content,
    clean_scene_numbers,
    clean_instruction_tags,
    clean_scene_numbers_chunk,
)
from .choice_parser import (
    fix_incomplete_json_array,
    fix_malformed_json_escaping,
    extract_choices_with_regex,
    parse_choices_from_json,
    extract_choices_from_response_end,
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
        # This is important for completion_mode and other settings that affect API calls
        try:
            client = LLMClient(user_settings)
            # Update cache with new client
            self._client_cache[user_id] = client
            logger.info(f"Created/updated LLM client for user {user_id} with provider {client.api_type}, completion_mode={client.completion_mode}")
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
    
    async def _generate_text_completion(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> str:
        """Internal method for text completion generation.

        Wrapper for LLMGenerationCore.generate_text_completion.
        """
        return await self._generation_core.generate_text_completion(
            prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
        )
    
    async def _direct_http_fallback(self, client, messages, max_tokens, temperature, stream, user_settings: Optional[Dict[str, Any]] = None):
        """Direct HTTP fallback for LM Studio when LiteLLM fails.

        Wrapper for LLMGenerationCore.direct_http_fallback.
        """
        return await self._generation_core.direct_http_fallback(
            client, messages, max_tokens, temperature, stream, user_settings
        )
    
    async def _direct_http_text_completion_fallback(self, client, prompt, max_tokens, temperature, stream, user_settings: Optional[Dict[str, Any]] = None):
        """Direct HTTP call to /v1/completions endpoint for text completion.

        Wrapper for LLMGenerationCore.direct_http_text_completion_fallback.
        """
        return await self._generation_core.direct_http_text_completion_fallback(
            client, prompt, max_tokens, temperature, stream, user_settings
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
    
    async def _generate_text_completion_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        skip_nsfw_filter: bool = False
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming text completion generation.

        Wrapper for LLMGenerationCore.generate_text_completion_stream.
        """
        async for chunk in self._generation_core.generate_text_completion_stream(
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
            "summary_generation", "story_chapters",
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
        
        # Check completion mode - multi-message only works with chat completion
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                db=db,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation
            )
            response_text = await self._generate_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            )
            return self._clean_scene_numbers(response_text)
        
        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        # Build messages array with context split into stable/dynamic parts
        
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (most stable → most dynamic)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Add the final task message from prompts.yml (most dynamic - changes every scene)
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE GENERATION] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
        # Call LLM with multi-message structure
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if should_inject_nsfw_filter(user_allow_nsfw):
            messages[0]["content"] = messages[0]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
        
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
        
        # Add buffer for choices section when generating scene with choices
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        max_tokens = base_max_tokens + 300  # Extra tokens for choices section
        logger.info(f"[SCENE WITH CHOICES] Using max_tokens: {max_tokens} (base: {base_max_tokens} + 300 buffer for choices)")
        
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                db=db,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation
            )
            response_text = await self._generate_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            )
            cleaned_response = self._clean_scene_numbers(response_text)
            
        else:
            # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
            messages = [{"role": "system", "content": system_prompt.strip()}]
            
            # Get scene batch size from user settings for cache optimization
            scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
            
            # Add context as multiple user messages (most stable → most dynamic)
            context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
            messages.extend(context_messages)
            
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
            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
            else:
                logger.info(f"[SCENE WITH CHOICES] Separate choice generation enabled - skipping choices reminder in task")
            
            messages.append({"role": "user", "content": task_content})
            
            logger.info(f"[SCENE WITH CHOICES] Using multi-message structure: {len(messages)} messages")
            
            # Apply NSFW filter
            from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
            user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
            
            if should_inject_nsfw_filter(user_allow_nsfw):
                messages[0]["content"] = messages[0]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            
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
        
        # Check completion mode - multi-message only works with chat completion
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            _, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation
            )
            
            raw_chunks = []
            async for chunk in self._generate_stream_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            ):
                raw_chunks.append(chunk)
                cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
                if cleaned_chunk:
                    yield cleaned_chunk
            return
        
        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (most stable → most dynamic)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # Add the final task message from prompts.yml (most dynamic - changes every scene)
        has_immediate = bool(immediate_situation and immediate_situation.strip())
        tone = context.get('tone', '')
        task_content = prompt_manager.get_task_instruction(
            has_immediate=has_immediate,
            prose_style=prose_style,
            tone=tone,
            immediate_situation=immediate_situation or "",
            scene_length_description=scene_length_description
        )
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE GENERATION STREAMING] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
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
    
    async def generate_scene_variants(self, original_scene: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> str:
        """Generate alternative versions of a scene (non-streaming, legacy endpoint)"""
        
        # Check if this is guided enhancement (has enhancement_guidance) or simple variant
        enhancement_guidance = context.get("enhancement_guidance", "")
        
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
        immediate_situation = context.get("current_situation") or ""
        immediate_situation = str(immediate_situation) if immediate_situation else ""
        
        # POV instruction (default third person)
        pov_instruction = "in third person (he/she/they/character names)"
        
        if enhancement_guidance:
            # Guided enhancement: use scene_guided_enhancement template with original scene
            # Exclude last scene from previous events to avoid duplication
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "scene_guided_enhancement", "scene_guided_enhancement",
                user_id=user_id,
                db=db,
                context=self._format_context_for_scene(context, exclude_last_scene=True),
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                pov_instruction=pov_instruction
            )
        else:
            # Simple variant: use same templates as new scene generation for cache optimization
            # Choose template based on whether we have immediate_situation
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            if has_immediate:
                template_key = "scene_with_immediate"
            else:
                template_key = "scene_without_immediate"
            
            # Get task instruction from prompts.yml
            tone = context.get('tone', '')
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                template_key, template_key,
                user_id=user_id,
                db=db,
                context=self._format_context_for_scene(context, exclude_last_scene=False),
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation,
                pov_instruction=pov_instruction,
                task_instruction=task_instruction
            )
        
        max_tokens = prompt_manager.get_max_tokens("scene_with_immediate", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    # NOTE: generate_scene_variants_streaming was removed - it was dead code (never called)
    # Use generate_variant_with_choices_streaming instead for streaming variant generation
    
    async def generate_scene_continuation(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> str:
        """Generate continuation content for an existing scene"""
        
        # Detect POV from current scene content
        current_content = context.get("current_content", "")
        previous_scenes = context.get("previous_scenes", "")
        
        # Detect POV from current scene and previous scenes
        pov = self._detect_pov(current_content)
        if previous_scenes:
            previous_pov = self._detect_pov(previous_scenes)
            # Prefer POV from previous scenes if available (more context)
            if previous_pov != 'third' or pov == 'third':
                pov = previous_pov
        
        # Get choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        
        # Enhance system prompt with POV consistency requirement
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            user_id=user_id,
            db=db,
            context=self._format_context_for_continuation(context),
            choices_count=choices_count
        )
        
        if pov == 'first':
            system_prompt += "\n\nIMPORTANT: Continue the story in first person perspective (using 'I', 'me', 'my'). Maintain consistency with the established first-person narrative style."
        else:
            system_prompt += "\n\nIMPORTANT: Continue the story in third person perspective (using 'he', 'she', 'they', character names). Maintain consistency with the established third-person narrative style."
        
        max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_continuation_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], db: Optional[Session] = None) -> AsyncGenerator[str, None]:
        """Generate continuation content for an existing scene with streaming"""
        
        # Detect POV from current scene content
        current_content = context.get("current_content", "") or context.get("current_scene_content", "")
        previous_scenes = context.get("previous_scenes", "")
        
        # Detect POV from current scene and previous scenes
        pov = self._detect_pov(current_content)
        if previous_scenes:
            previous_pov = self._detect_pov(previous_scenes)
            # Prefer POV from previous scenes if available (more context)
            if previous_pov != 'third' or pov == 'third':
                pov = previous_pov
        
        # Get choices count from user settings
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            user_id=user_id,
            db=db,
            context=self._format_context_for_continuation(context),
            choices_count=choices_count
        )
        
        # Enhance system prompt with POV consistency requirement
        if pov == 'first':
            system_prompt += "\n\nIMPORTANT: Continue the story in first person perspective (using 'I', 'me', 'my'). Maintain consistency with the established first-person narrative style."
        else:
            system_prompt += "\n\nIMPORTANT: Continue the story in third person perspective (using 'he', 'she', 'they', character names). Maintain consistency with the established third-person narrative style."
        
        max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
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
        
        # Add buffer for choices section when generating scene with choices
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)
        max_tokens = base_max_tokens + choices_buffer_tokens
        logger.info(f"[SCENE WITH CHOICES STREAMING] Using max_tokens: {max_tokens} (base: {base_max_tokens} + {choices_buffer_tokens} buffer for {choices_count} choices)")
        
        # Check completion mode - multi-message only works with chat completion
        client = self.get_user_client(user_id, user_settings)
        completion_mode = client.completion_mode
        
        if completion_mode == "text":
            # Text completion mode - fall back to single prompt approach
            formatted_context = self._format_context_for_scene(context)
            
            # Get task instruction from prompts.yml
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            tone = context.get('tone', '')
            task_instruction = prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )
            # Only append choices reminder if separate_choice_generation is NOT enabled
            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_instruction = task_instruction + "\n\n" + choices_reminder
            
            _, user_prompt = prompt_manager.get_prompt_pair(
                "scene_with_immediate", "scene_with_immediate",
                user_id=user_id,
                db=db,
                context=formatted_context,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                immediate_situation=immediate_situation,
                pov_instruction=pov_instruction,
                task_instruction=task_instruction
            )
            
            scene_buffer = []
            choices_buffer = []
            found_marker = False
            rolling_buffer = ""
            total_chunks = 0
            raw_chunks = []
            
            async for chunk in self._generate_stream_text_completion(
                user_prompt, user_id, user_settings, system_prompt, max_tokens, None, False
            ):
                total_chunks += 1
                raw_chunks.append(chunk)
                cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
                if not cleaned_chunk:
                    continue
                
                if not found_marker:
                    rolling_buffer += cleaned_chunk
                    if CHOICES_MARKER in rolling_buffer:
                        parts = rolling_buffer.split(CHOICES_MARKER, 1)
                        scene_part = parts[0]
                        choices_part = parts[1] if len(parts) > 1 else ""
                        if scene_part:
                            yield (scene_part, False, None)
                        scene_buffer.append(scene_part)
                        if choices_part:
                            choices_buffer.append(choices_part)
                        found_marker = True
                        rolling_buffer = ""
                    else:
                        if len(rolling_buffer) > len(CHOICES_MARKER) * 2:
                            excess_length = len(rolling_buffer) - len(CHOICES_MARKER)
                            excess = rolling_buffer[:excess_length]
                            scene_buffer.append(excess)
                            yield (excess, False, None)
                            rolling_buffer = rolling_buffer[excess_length:]
                else:
                    choices_buffer.append(cleaned_chunk)
            
            if not found_marker and rolling_buffer:
                scene_buffer.append(rolling_buffer)
                yield (rolling_buffer, False, None)
            
            parsed_choices = None
            if found_marker and choices_buffer:
                choices_text = ''.join(choices_buffer).strip()
                parsed_choices = self._parse_choices_from_json(choices_text)
            
            # If separate_choice_generation is enabled, discard any inline choices
            if separate_choice_generation and parsed_choices:
                logger.info(f"[CHOICES TEXT COMPLETION] Separate choice generation enabled - discarding {len(parsed_choices)} inline choices")
                parsed_choices = None
            
            yield ("", True, parsed_choices)
            return
        
        # === MULTI-MESSAGE STRUCTURE FOR BETTER CACHING ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (most stable → most dynamic)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
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
            choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
            if choices_reminder:
                task_content = task_content + "\n\n" + choices_reminder
        else:
            logger.info(f"[SCENE WITH CHOICES STREAMING] Separate choice generation enabled - skipping choices reminder in task")
        
        messages.append({"role": "user", "content": task_content})
        
        logger.info(f"[SCENE WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages (1 system + {len(context_messages)} context + 1 task)")
        
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
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION (for cache hits) ===
        # Always use scene_with_immediate for system prompt consistency
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
        
        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION (for cache hits) ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
        # === ONLY THIS FINAL MESSAGE IS DIFFERENT ===
        tone = context.get('tone', '')
        if enhancement_guidance:
            # Guided enhancement: use task_guided_enhancement from prompts.yml
            task_content = prompt_manager.get_enhancement_task_instruction(
                original_scene=original_scene,
                enhancement_guidance=enhancement_guidance,
                scene_length_description=scene_length_description,
                choices_count=choices_count,
                prose_style=prose_style,
                tone=tone,
                skip_choices_reminder=separate_choice_generation
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
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
        
        messages.append({"role": "user", "content": task_content})
        
        # Add buffer for choices section - dynamic based on choices_count
        base_max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)  # At least 300, or 50 per choice
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        logger.info(f"[VARIANT WITH CHOICES STREAMING] Using multi-message structure: {len(messages)} messages, max_tokens={max_tokens}")
        
        scene_buffer = []
        choices_buffer = []
        found_marker = False
        rolling_buffer = ""  # Buffer to detect marker across chunks
        total_chunks = 0
        
        # Use multi-message streaming for cache optimization
        async for chunk in self._generate_stream_with_messages(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            max_tokens=max_tokens
        ):
            total_chunks += 1
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
        
        # Parse choices from buffer
        parsed_choices = None
        if found_marker and choices_buffer:
            choices_text = ''.join(choices_buffer).strip()
            parsed_choices = self._parse_choices_from_json(choices_text)
            if not parsed_choices:
                logger.warning(f"[CHOICES VARIANT] Marker found but parsing failed. Choices text: {choices_text[:200]}")
        else:
            if not found_marker:
                logger.warning(f"[CHOICES VARIANT] ERROR: ###CHOICES### marker not found after {total_chunks} chunks")
                logger.warning(f"[CHOICES VARIANT] Scene buffer length: {len(''.join(scene_buffer))} chars")
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
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION (for cache hits) ===
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Add POV consistency requirement to system prompt (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION (for cache hits) ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        # The context already has current scene excluded (via exclude_scene_id in context_manager)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
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
            choices_reminder_text = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
        
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
        
        # Add buffer for choices section - dynamic based on choices_count
        base_max_tokens = prompt_manager.get_max_tokens("scene_continuation", user_settings)
        choices_buffer_tokens = max(300, choices_count * 50)  # At least 300, or 50 per choice
        max_tokens = base_max_tokens + choices_buffer_tokens
        
        logger.info(f"[CONTINUATION] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}")
        
        # Write debug output for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
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
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION FOR CACHE ALIGNMENT ===
        # This ensures messages 1-N are identical between chapter conclusion and choice generation,
        # enabling cache hits when generating choices after a chapter conclusion.
        # Chapter-specific instructions are in the final user message instead.
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=True  # Chapter conclusions don't include choices in the scene
        )
        
        if not system_prompt or not system_prompt.strip():
            logger.error("[CONCLUDING SCENE] System prompt is empty for scene_with_immediate")
            raise ValueError("Failed to load system prompt for chapter conclusion")
        
        # Add POV consistency requirement
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD MULTI-MESSAGE STRUCTURE (for cache hits on context) ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
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
                prompt_file_path = self._get_prompt_debug_path("prompt_sent.json")
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
        
        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION ===
        # This ensures the system message is identical and cacheable
        # Use get_prompt instead of get_prompt_pair to avoid user prompt template errors
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )
        
        # Add POV consistency requirement to system prompt (from template)
        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder
        
        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION ===
        messages = [{"role": "system", "content": system_prompt.strip()}]
        
        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        
        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        # DO NOT modify context before this call - must be identical to scene generation
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)
        
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
        final_message = prompt_manager.get_prompt(
            "choice_generation", "user",
            scene_content=cleaned_scene_content,
            choices_count=choices_count,
            pov_instruction=pov_instruction
        )
        
        messages.append({"role": "user", "content": final_message})
        
        # Calculate max tokens - use YAML settings or user settings
        base_max_tokens = prompt_manager.get_max_tokens("choice_generation", user_settings)
        # Ensure at least enough tokens for the requested number of choices
        dynamic_max_tokens = max(base_max_tokens, choices_count * 75)
        max_tokens = dynamic_max_tokens
        
        logger.info(f"[CHOICES] Using multi-message structure for cache optimization: {len(messages)} messages, max_tokens={max_tokens}, requested_choices={choices_count}")
        
        # Write debug output to prompt_choice_sent.json for debugging cache issues
        from ...config import settings
        if settings.prompt_debug:
            try:
                import json
                prompt_file_path = self._get_prompt_debug_path("prompt_choice_sent.json")
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
        Extract completed plot events using the SAME multi-message structure as scene generation.

        This leverages LLM prompt caching - messages 1-N are identical to scene generation,
        only the final message differs (the generated scene + extraction request).

        Since the main LLM just wrote the scene, it has full context and understanding
        of what happened. This typically produces better extraction than a separate model.

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

        # Get scene length and choices count from user settings (for system prompt consistency)
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
        scene_length_description = self._get_scene_length_description(scene_length)

        # === USE SAME SYSTEM PROMPT AS SCENE GENERATION FOR CACHE HITS ===
        system_prompt = prompt_manager.get_prompt(
            "scene_with_immediate", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description,
            choices_count=choices_count,
            skip_choices=separate_choice_generation
        )

        # === BUILD SAME MULTI-MESSAGE STRUCTURE AS SCENE GENERATION ===
        messages = [{"role": "system", "content": system_prompt.strip()}]

        # Get scene batch size from user settings for cache optimization
        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10

        # Add context as multiple user messages (SAME as scene generation - all CACHED)
        context_messages = self._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)

        # === ADD THE GENERATED SCENE AS ASSISTANT MESSAGE ===
        # This simulates that the LLM just generated this scene
        cleaned_scene = self._clean_scene_numbers(scene_content)
        messages.append({"role": "assistant", "content": cleaned_scene})

        # === FINAL USER MESSAGE: EXTRACTION REQUEST ===
        # Format key events as a list for the prompt
        key_events_formatted = json.dumps(key_events, indent=2, ensure_ascii=False)

        extraction_prompt = prompt_manager.get_prompt(
            "chapter_progress.context_aware_extraction", "user",
            key_events=key_events_formatted
        )
        messages.append({"role": "user", "content": extraction_prompt})

        logger.info(f"[PLOT_EXTRACTION_CONTEXT] Using multi-message structure: {len(messages)} messages, checking {len(key_events)} events")

        # Use low temperature for consistent extraction
        import copy
        extraction_settings = copy.deepcopy(user_settings)
        if 'llm_settings' not in extraction_settings:
            extraction_settings['llm_settings'] = {}
        extraction_settings['llm_settings']['temperature'] = 0.3
        # Disable reasoning for extraction - we want direct JSON output
        extraction_settings['llm_settings']['reasoning_effort'] = 'disabled'

        # Generate response
        try:
            response = await self._generate_with_messages(
                messages=messages,
                user_id=user_id,
                user_settings=extraction_settings,
                max_tokens=500  # JSON array of events doesn't need many tokens
            )

            logger.info(f"[PLOT_EXTRACTION_CONTEXT] Raw response: {response[:300] if response else 'None'}...")

            # Parse response as JSON array
            from ..chapter_progress_service import clean_llm_json
            cleaned = clean_llm_json(response)
            completed = json.loads(cleaned)

            if not isinstance(completed, list):
                logger.warning(f"[PLOT_EXTRACTION_CONTEXT] Response is not a list: {type(completed)}")
                return []

            # Validate that returned events are in the original list
            valid_events = [e for e in completed if e in key_events]

            logger.info(f"[PLOT_EXTRACTION_CONTEXT] Extracted {len(valid_events)} valid events from scene")
            return valid_events

        except json.JSONDecodeError as e:
            logger.warning(f"[PLOT_EXTRACTION_CONTEXT] Failed to parse JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"[PLOT_EXTRACTION_CONTEXT] Extraction failed: {e}")
            return []

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
                "plot_generation", "complete_plot",
                context=self._format_context_for_plot(context)
            )
            max_tokens = prompt_manager.get_max_tokens("complete_plot", user_settings)
        else:
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "plot_generation", "single_plot_point",
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
                
                logger.info(f"[SUMMARY] Using extraction LLM for summary generation (user_id={user_id})")
                
                # Get extraction model settings
                ext_settings = user_settings.get('extraction_model_settings', {})
                llm_settings = user_settings.get('llm_settings', {})
                timeout_total = llm_settings.get('timeout_total', 240)
                extraction_service = ExtractionLLMService(
                    url=ext_settings.get('url', 'http://localhost:1234/v1'),
                    model=ext_settings.get('model_name', 'qwen2.5-3b-instruct'),
                    api_key=ext_settings.get('api_key', ''),
                    temperature=ext_settings.get('temperature', 0.3),
                    max_tokens=ext_settings.get('max_tokens', 1000),
                    timeout_total=timeout_total
                )
                
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
        3. Chapter Context: story_so_far, previous/current chapter summaries (per chapter)
        4. Chapter Plot Guidance: story beats from brainstorming (per chapter)
        5. Completed Scene Batches: stable scene history (per batch)
        6. Character Interaction History: firsts between characters (rarely changes)
        7. Character Relationships: relationship arcs and strength (occasionally changes)
        8. Character States: entity states, locations, objects (periodically changes)
        ──── cache break point ────
        9. Relevant Context: semantic search results (changes every scene)
        10. Recent Scenes: active scene batch (changes every scene)
        11. Story Focus: working memory, threads, character attention (changes every scene)
        12. Current Progress: pacing guidance (changes every scene)
        13. Continuity Warnings: unresolved contradictions (if any)

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
        
        # Chapter metadata (stable per chapter)
        if context.get("chapter_location"):
            foundation_parts.append(f"Chapter Location: {context['chapter_location']}")
        if context.get("chapter_time_period"):
            foundation_parts.append(f"Chapter Time Period: {context['chapter_time_period']}")
        if context.get("chapter_scenario"):
            foundation_parts.append(f"Chapter Scenario: {context['chapter_scenario']}")
        
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
        
        # === MESSAGE 2: Chapter Summaries (stable per chapter, changes on summary updates) ===
        summary_parts = []
        
        if context.get("story_so_far"):
            summary_parts.append(f"Story So Far:\n{context['story_so_far']}")
        
        if context.get("previous_chapter_summary"):
            summary_parts.append(f"Previous Chapter Summary:\n{context['previous_chapter_summary']}")
        
        if context.get("current_chapter_summary"):
            summary_parts.append(f"Current Chapter Summary:\n{context['current_chapter_summary']}")
        
        if summary_parts:
            messages.append({
                "role": "user", 
                "content": "=== CHAPTER CONTEXT ===\n" + "\n\n".join(summary_parts)
            })
        
        # === MESSAGE 2.5: Chapter Plot Guidance (from brainstorming) ===
        chapter_plot = context.get("chapter_plot")
        arc_phase = context.get("arc_phase")
        
        if chapter_plot or arc_phase:
            plot_parts = []
            
            if arc_phase:
                plot_parts.append(f"Story Arc Phase: {arc_phase.get('name', 'Unknown')}")
                if arc_phase.get('description'):
                    plot_parts.append(f"Phase Goal: {arc_phase['description']}")
            
            if chapter_plot:
                if chapter_plot.get('summary'):
                    plot_parts.append(f"Chapter Summary: {chapter_plot['summary']}")
                if chapter_plot.get('key_events'):
                    events = chapter_plot['key_events']
                    if isinstance(events, list):
                        # Format as story beats, not a checklist
                        events_formatted = "\n  - ".join(events)
                        plot_parts.append(f"Story Beats (weave in naturally across scenes):\n  - {events_formatted}")
                if chapter_plot.get('climax'):
                    plot_parts.append(f"Building Toward: {chapter_plot['climax']}")
                if chapter_plot.get('resolution'):
                    plot_parts.append(f"Chapter Resolution: {chapter_plot['resolution']}")
            
            if plot_parts:
                # Get header and footer from prompts.yml
                header = prompt_manager.get_raw_prompt("pacing.chapter_plot_header") or "=== CHAPTER PLOT GUIDANCE ==="
                footer = prompt_manager.get_raw_prompt("pacing.chapter_plot_footer") or ""
                
                messages.append({
                    "role": "user",
                    "content": header.strip() + "\n" + "\n".join(plot_parts) + footer
                })
        
        # === MESSAGES 3+: Scene Batches + Suffix Sections ===
        #
        # Message order after scene batches (most stable → most dynamic):
        #   A. Completed scene batches (stable per batch, cached)
        #   B. CHARACTER INTERACTION HISTORY (rarely changes, often cached)
        #   C. CHARACTER RELATIONSHIPS (changes occasionally, sometimes cached)
        #   D. CHARACTER STATES (entity states/locations/objects, changes periodically)
        #   ──── cache break point (below changes every scene) ────
        #   E. RELEVANT CONTEXT (semantic search results, changes every scene)
        #   F. RECENT SCENES (active scene batch, changes every scene)
        #   G. STORY FOCUS (working memory/threads, changes every scene)
        #   H. CURRENT PROGRESS (pacing guidance, changes every scene)
        #   I. CONTINUITY WARNINGS (if any)
        #
        # Character info grouped together (B-C-D) for coherence.
        # Most volatile sections (E-I) at the end, closest to generation instruction.

        previous_scenes_text = context.get("previous_scenes", "")

        # --- Extract structured sections from previous_scenes_text via regex ---
        relevant_context_match = None
        interaction_history_match = None
        recent_match = None

        if previous_scenes_text:
            interaction_history_match = re.search(
                r'CHARACTER INTERACTION HISTORY:\n(.*?)(?=\n\nRelevant Context:|\n\nRecent Scenes:|$)',
                previous_scenes_text, re.DOTALL
            )
            relevant_context_match = re.search(
                r'Relevant Context:\n(.*?)(?=\n\nRecent Scenes:|$)',
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

        # --- C. CHARACTER RELATIONSHIPS (changes occasionally) ---
        relationship_context = context.get("relationship_context")
        if relationship_context and relationship_context.get("relationships"):
            rel_parts = []

            for rel in relationship_context["relationships"][:6]:  # Limit for token efficiency
                chars = " <-> ".join(rel["characters"])
                strength = rel.get("strength", 0)
                if strength > 0:
                    indicator = "+" * min(int(strength * 3) + 1, 3)
                elif strength < 0:
                    indicator = "-" * min(int(abs(strength) * 3) + 1, 3)
                else:
                    indicator = "~"

                rel_parts.append(
                    f"{chars}: {rel.get('type', 'unknown')} [{indicator}]\n"
                    f"  Arc: {rel.get('arc', 'developing')}"
                )

            rel_text = "\n".join(rel_parts)

            if relationship_context.get("neglected"):
                neglected_chars = [" & ".join(n["characters"]) for n in relationship_context["neglected"]]
                rel_text += f"\n\nNeglected (consider reconnecting): {', '.join(neglected_chars)}"

            messages.append({
                "role": "user",
                "content": f"=== CHARACTER RELATIONSHIPS ===\n{rel_text}"
            })

        # --- D. CHARACTER STATES (entity states, locations, objects) ---
        # Prefer entity_states_text from context dict (passed separately by SemanticContextManager)
        entity_states_text = context.get("entity_states_text")
        if entity_states_text:
            messages.append({
                "role": "user",
                "content": f"=== CHARACTER STATES ===\n{entity_states_text}"
            })

        # --- E. RELEVANT CONTEXT (semantic search results only, changes every scene) ---
        if relevant_context_match:
            messages.append({
                "role": "user",
                "content": "=== RELEVANT CONTEXT ===\n" + relevant_context_match.group(1).strip()
            })

        # --- F. RECENT SCENES (active scene batch, changes every scene) ---
        if recent_scenes_message:
            messages.append(recent_scenes_message)

        # --- G. STORY FOCUS (working memory + active threads) ---
        story_focus = context.get("story_focus")
        if story_focus:
            focus_parts = []

            if story_focus.get("active_threads"):
                focus_parts.append(f"Unresolved threads: {'; '.join(story_focus['active_threads'][:3])}")
            if story_focus.get("recent_focus"):
                focus_parts.append(f"Recent focus: {', '.join(story_focus['recent_focus'][:2])}")
            if story_focus.get("character_spotlight"):
                spotlight = [f"{k} ({v})" for k, v in list(story_focus['character_spotlight'].items())[:2]]
                focus_parts.append(f"Character attention: {', '.join(spotlight)}")

            if focus_parts:
                messages.append({
                    "role": "user",
                    "content": "=== STORY FOCUS ===\n" + "\n".join(focus_parts)
                })

        # --- H. CURRENT PROGRESS (pacing guidance, changes every scene) ---
        pacing_guidance = context.get("pacing_guidance")
        if pacing_guidance:
            messages.append({
                "role": "user",
                "content": f"=== CURRENT PROGRESS ===\n{pacing_guidance}"
            })

        # --- I. CONTINUITY WARNINGS (if any) ---
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
        
        # Add story_so_far if available (summary of all previous chapters)
        story_so_far = context.get("story_so_far")
        if story_so_far:
            logger.info(f"[CONTEXT FORMAT] Including story_so_far ({len(story_so_far)} chars)")
            context_parts.append(f"Story So Far:\n{story_so_far}")
        else:
            logger.info("[CONTEXT FORMAT] story_so_far is None or empty, not including")
        
        # Add previous chapter summary if available
        previous_chapter_summary = context.get("previous_chapter_summary")
        if previous_chapter_summary:
            logger.info(f"[CONTEXT FORMAT] Including previous_chapter_summary ({len(previous_chapter_summary)} chars)")
            context_parts.append(f"Previous Chapter Summary:\n{previous_chapter_summary}")
        else:
            logger.info("[CONTEXT FORMAT] previous_chapter_summary is None or empty, not including")
        
        # Add current chapter summary if available (summary of this chapter's progress so far)
        current_chapter_summary = context.get("current_chapter_summary")
        if current_chapter_summary:
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
        chapter_id: int = None
    ) -> Tuple[Any, Any]:
        """Create a new scene with its first variant.

        Wrapper for SceneDatabaseOperations.create_scene_with_variant.
        """
        return self._scene_db_ops.create_scene_with_variant(
            db, story_id, sequence_number, content, title,
            custom_prompt, choices, generation_method, branch_id, chapter_id
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
        """Create a new variant for an existing scene"""
        from ...models import Scene, SceneVariant, Story
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
        context = await context_manager.build_scene_generation_context(
            story.id, db, custom_prompt=custom_prompt, exclude_scene_id=scene_id, branch_id=effective_branch_id
        )
        
        # Generate new content using the original scene as base
        original_variant = db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id, SceneVariant.is_original == True)\
            .first()
        
        if original_variant:
            # Generate variant based on original
            new_content = await self.generate_scene_variants(
                original_scene=original_variant.content,
                context=context,
                user_id=user_id,
                user_settings=user_settings or {}
            )
        else:
            # Generate new scene if no original exists
            new_content = await self.generate_scene(
                context=context,
                user_id=user_id,
                user_settings=user_settings or {}
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
        
        # Check completion mode - multi-message only works with chat completion
        if client.completion_mode == "text":
            # For text completion, fall back to combining messages into single prompt
            logger.warning("Multi-message generation not supported for text completion mode, combining messages")
            combined_prompt = "\n\n".join([
                msg["content"] for msg in messages if msg["role"] == "user"
            ])
            system_prompt = next((msg["content"] for msg in messages if msg["role"] == "system"), "")
            return await self._generate_text_completion(
                combined_prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            )
        
        # Inject NSFW filter into system message if needed
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # Find and modify system message, or add one
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"NSFW filter injected for user {user_id}")
        
        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        # Get timeout from user settings or fallback to system default
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
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
            
            return response.choices[0].message.content
            
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
        
        # Check completion mode - multi-message only works with chat completion
        if client.completion_mode == "text":
            # For text completion, fall back to combining messages into single prompt
            logger.warning("Multi-message streaming not supported for text completion mode, combining messages")
            combined_prompt = "\n\n".join([
                msg["content"] for msg in messages if msg["role"] == "user"
            ])
            system_prompt = next((msg["content"] for msg in messages if msg["role"] == "system"), "")
            async for chunk in self._generate_stream_text_completion(
                combined_prompt, user_id, user_settings, system_prompt, max_tokens, temperature, skip_nsfw_filter
            ):
                yield chunk
            return
        
        # Inject NSFW filter into system message if needed
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False
        
        if not skip_nsfw_filter and should_inject_nsfw_filter(user_allow_nsfw):
            # Find and modify system message, or add one
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"NSFW filter injected for streaming user {user_id}")
        
        # Get streaming parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        gen_params["stream"] = True
        
        # Get timeout from user settings or fallback to system default
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
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
                        content_chars += len(delta.content)
                        yield delta.content

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
