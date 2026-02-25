"""
Multi-variant generation module - handles n-sampling scene generation.

Extracted from UnifiedLLMService to reduce file size and improve maintainability.
These methods generate multiple scene variants in a single API call using n parameter.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator, TYPE_CHECKING

from sqlalchemy.orm import Session
from litellm import acompletion

from ...config import settings
from .prompts import prompt_manager

if TYPE_CHECKING:
    from .service import UnifiedLLMService

logger = logging.getLogger(__name__)


class MultiVariantGeneration:
    """
    Handles multi-variant (n-sampling) scene generation.

    Takes a reference to the parent UnifiedLLMService to access shared methods.
    """

    def __init__(self, service: 'UnifiedLLMService'):
        """Initialize with reference to parent service."""
        self._service = service

    async def generate_stream_with_messages_multi(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[Tuple[str, bool, List[str]], None]:
        """
        Core streaming helper for n > 1 completions.

        Streams the first completion (index 0) to the frontend while accumulating
        all n completions in the background.

        Yields:
            Tuple of (chunk, is_complete, contents_list)
            - During streaming: (chunk_text, False, [])
            - On completion: ("", True, [content_0, content_1, ..., content_n-1])
        """
        client = self._service.get_user_client(user_id, user_settings)

        # Inject NSFW filter into system message if needed
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False

        if should_inject_nsfw_filter(user_allow_nsfw):
            # Find and modify system message, or add one
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"[MULTI-GEN] NSFW filter injected for user {user_id}")

        # Get generation params and add n parameter
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        gen_params["stream"] = True

        # Add n to extra_body
        if "extra_body" not in gen_params:
            gen_params["extra_body"] = {}
        gen_params["extra_body"]["n"] = n

        # Get timeout from user settings
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total

        logger.info(f"[MULTI-GEN] Starting streaming with n={n}")

        try:
            response = await acompletion(**gen_params)

            # Track content for each completion index
            contents = [""] * n
            chunk_count = 0

            async for chunk in response:
                chunk_count += 1
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    # Process all choices in the chunk
                    for choice in chunk.choices:
                        idx = choice.index if hasattr(choice, 'index') else 0
                        if idx >= n:
                            continue  # Safety check

                        delta = choice.delta if hasattr(choice, 'delta') else None
                        if delta and hasattr(delta, 'content') and delta.content:
                            contents[idx] += delta.content

                            # Only stream index 0 to the frontend
                            if idx == 0:
                                yield (delta.content, False, [])

            logger.info(f"[MULTI-GEN] Streaming complete: {chunk_count} chunks, {n} completions")
            for i, content in enumerate(contents):
                logger.info(f"[MULTI-GEN] Content {i}: {len(content)} chars")

            # Yield final result with all contents
            yield ("", True, contents)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[MULTI-GEN] Streaming failed: {error_msg}")
            raise ValueError(f"Multi-generation streaming failed: {error_msg}")

    async def generate_multi_completions(
        self,
        messages: List[Dict[str, str]],
        user_id: int,
        user_settings: Dict[str, Any],
        n: int,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> List[str]:
        """
        Non-streaming helper for n > 1 completions.

        Returns:
            List of n completion contents
        """
        client = self._service.get_user_client(user_id, user_settings)

        # Inject NSFW filter into system message if needed
        from ...utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
        user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False

        if should_inject_nsfw_filter(user_allow_nsfw):
            system_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), None)
            if system_idx is not None:
                messages[system_idx]["content"] = messages[system_idx]["content"].strip() + "\n\n" + get_nsfw_prevention_prompt()
            else:
                messages.insert(0, {"role": "system", "content": get_nsfw_prevention_prompt()})
            logger.debug(f"[MULTI-GEN] NSFW filter injected for user {user_id}")

        # Get generation params and add n parameter
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages

        # Add n to extra_body
        if "extra_body" not in gen_params:
            gen_params["extra_body"] = {}
        gen_params["extra_body"]["n"] = n

        # Get timeout from user settings
        user_timeout = user_settings.get('llm_settings', {}).get('timeout_total') if user_settings else None
        gen_params["timeout"] = user_timeout if user_timeout is not None else settings.llm_timeout_total

        logger.info(f"[MULTI-GEN] Starting non-streaming with n={n}")

        try:
            response = await acompletion(**gen_params)

            # Extract content from each choice
            contents = []
            for choice in response.choices:
                content = choice.message.content if hasattr(choice.message, 'content') else ""
                contents.append(content)

            logger.info(f"[MULTI-GEN] Non-streaming complete: {len(contents)} completions")
            return contents

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[MULTI-GEN] Non-streaming failed: {error_msg}")
            raise ValueError(f"Multi-generation failed: {error_msg}")

    async def generate_scene_with_choices_streaming_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[Dict[str, Any]]]], None]:
        """
        Generate n scene variants with choices in a single streaming call (Combined + Streaming).

        Streams the first variant to the frontend while accumulating all n variants.
        Each variant's choices are parsed from its content.

        Yields:
            Tuple of (chunk, is_complete, variants_data)
            - During streaming: (chunk_text, False, None)
            - On completion: ("", True, [{"content": str, "choices": list}, ...])
        """
        CHOICES_MARKER = "###CHOICES###"

        # Get settings for max_tokens calculation
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

        # Calculate max tokens
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        # Use cache-friendly helper for consistent message prefix
        messages = await self._service._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction using helper
        task_content = self._service._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=not separate_choice_generation
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN SCENE] Starting combined streaming with n={n}")

        # Track streaming content for first variant (index 0)
        streaming_buffer = ""
        found_marker_in_stream = False

        async for chunk, is_complete, contents in self.generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                # Stream chunk from index 0 to frontend
                streaming_buffer += chunk

                # Check for marker in streaming buffer
                if not found_marker_in_stream and CHOICES_MARKER in streaming_buffer:
                    # Only yield content before the marker
                    parts = streaming_buffer.split(CHOICES_MARKER, 1)
                    yield (parts[0], False, None)
                    found_marker_in_stream = True
                elif not found_marker_in_stream:
                    # Keep buffer small, yield excess
                    if len(streaming_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(streaming_buffer) - len(CHOICES_MARKER)
                        yield (streaming_buffer[:excess_length], False, None)
                        streaming_buffer = streaming_buffer[excess_length:]
            else:
                # Streaming complete - process all n contents
                variants_data = []

                for idx, content in enumerate(contents):
                    # Clean the content
                    cleaned_content = self._service._clean_scene_content(content)

                    # Extract scene and choices
                    scene_content, parsed_choices = self._service._extract_choices_from_response_end(cleaned_content)

                    # If separate_choice_generation is enabled, discard inline choices
                    if separate_choice_generation:
                        parsed_choices = None

                    variants_data.append({
                        "content": scene_content.strip(),
                        "choices": parsed_choices or []
                    })

                    logger.info(f"[MULTI-GEN SCENE] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")

                yield ("", True, variants_data)

    async def generate_scene_with_choices_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[Dict[str, Any]]:
        """
        Generate n scene variants with choices in a single non-streaming call (Combined + Non-streaming).

        Returns:
            List of dicts: [{"content": str, "choices": list}, ...]
        """
        CHOICES_MARKER = "###CHOICES###"

        # Get settings for max_tokens calculation
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

        # Calculate max tokens
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        # Use cache-friendly helper for consistent message prefix
        messages = await self._service._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction using helper
        task_content = self._service._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=not separate_choice_generation
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN SCENE] Starting combined non-streaming with n={n}")

        # Get all completions
        contents = await self.generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )

        # Process each completion
        variants_data = []
        for idx, content in enumerate(contents):
            cleaned_content = self._service._clean_scene_content(content)
            scene_content, parsed_choices = self._service._extract_choices_from_response_end(cleaned_content)

            if separate_choice_generation:
                parsed_choices = None

            variants_data.append({
                "content": scene_content.strip(),
                "choices": parsed_choices or []
            })

            logger.info(f"[MULTI-GEN SCENE] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")

        return variants_data

    async def generate_scene_streaming_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate n scene variants without choices (Separate + Streaming).

        Yields:
            Tuple of (chunk, is_complete, contents_list)
            - During streaming: (chunk_text, False, None)
            - On completion: ("", True, [content_0, ..., content_n-1])
        """
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        # Use cache-friendly helper for consistent message prefix
        messages = await self._service._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction using helper - no choices reminder for separate generation
        task_content = self._service._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=False
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN SCENE] Starting separate streaming with n={n}")

        async for chunk, is_complete, contents in self.generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                yield (chunk, False, None)
            else:
                # Clean all contents
                cleaned_contents = [self._service._clean_scene_content(c).strip() for c in contents]
                yield ("", True, cleaned_contents)

    async def generate_scene_multi(
        self,
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[str]:
        """
        Generate n scene variants without choices (Separate + Non-streaming).

        Returns:
            List of scene contents
        """
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        # Use cache-friendly helper for consistent message prefix
        messages = await self._service._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction using helper - no choices reminder for separate generation
        task_content = self._service._build_scene_task_message(
            context=context,
            user_settings=user_settings,
            db=db,
            include_choices_reminder=False
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN SCENE] Starting separate non-streaming with n={n}")

        contents = await self.generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )

        return [self._service._clean_scene_content(c).strip() for c in contents]

    async def generate_choices_for_variants(
        self,
        scene_contents: List[str],
        context: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session]
    ) -> List[List[str]]:
        """
        Generate choices for multiple scene variants in parallel.

        Args:
            scene_contents: List of scene content strings
            context: Scene generation context
            user_id: User ID
            user_settings: User settings dict
            db: Database session

        Returns:
            List of choice lists, one per scene content
        """
        import asyncio

        logger.info(f"[MULTI-GEN CHOICES] Generating choices for {len(scene_contents)} variants in parallel")

        # Create tasks for parallel execution
        tasks = [
            self._service.generate_choices(content, context, user_id, user_settings, db)
            for content in scene_contents
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, converting exceptions to empty lists
        all_choices = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[MULTI-GEN CHOICES] Failed for variant {idx}: {result}")
                all_choices.append([])
            else:
                all_choices.append(result)
                logger.info(f"[MULTI-GEN CHOICES] Variant {idx}: {len(result)} choices")

        return all_choices

    async def generate_concluding_scene_streaming_multi(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> AsyncGenerator[Tuple[str, bool, Optional[List[str]]], None]:
        """
        Generate n concluding scene variants (streaming, no choices).

        Yields:
            Tuple of (chunk, is_complete, contents_list)
        """
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        scene_length_description = self._service._get_scene_length_description(scene_length)

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

        # Build system prompt for concluding scene
        system_prompt = prompt_manager.get_prompt(
            "chapter_conclusion", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description
        )

        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder

        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        messages = [{"role": "system", "content": system_prompt.strip()}]

        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._service._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)

        # Build task instruction for chapter conclusion
        task_content = prompt_manager.get_prompt(
            "chapter_conclusion", "user",
            user_id=user_id,
            db=db,
            chapter_number=chapter_info.get("chapter_number", 1),
            chapter_title=chapter_info.get("chapter_title", ""),
            scene_length_description=scene_length_description
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN CONCLUSION] Starting streaming with n={n}")

        async for chunk, is_complete, contents in self.generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                yield (chunk, False, None)
            else:
                cleaned_contents = [self._service._clean_scene_content(c).strip() for c in contents]
                yield ("", True, cleaned_contents)

    async def generate_concluding_scene_multi(
        self,
        context: Dict[str, Any],
        chapter_info: Dict[str, Any],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Optional[Session],
        n: int
    ) -> List[str]:
        """
        Generate n concluding scene variants (non-streaming, no choices).

        Returns:
            List of scene contents
        """
        generation_prefs = user_settings.get("generation_preferences", {})
        scene_length = generation_prefs.get("scene_length", "medium")
        scene_length_description = self._service._get_scene_length_description(scene_length)

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

        system_prompt = prompt_manager.get_prompt(
            "chapter_conclusion", "system",
            user_id=user_id,
            db=db,
            scene_length_description=scene_length_description
        )

        pov_reminder = prompt_manager.get_pov_reminder(pov)
        if pov_reminder:
            system_prompt += "\n\n" + pov_reminder

        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        messages = [{"role": "system", "content": system_prompt.strip()}]

        scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10) if user_settings else 10
        context_messages = self._service._format_context_as_messages(context, scene_batch_size=scene_batch_size)
        messages.extend(context_messages)

        task_content = prompt_manager.get_prompt(
            "chapter_conclusion", "user",
            user_id=user_id,
            db=db,
            chapter_number=chapter_info.get("chapter_number", 1),
            chapter_title=chapter_info.get("chapter_title", ""),
            scene_length_description=scene_length_description
        )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN CONCLUSION] Starting non-streaming with n={n}")

        contents = await self.generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )

        return [self._service._clean_scene_content(c).strip() for c in contents]

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
        """
        Regenerate n scene variants with choices (streaming).
        Uses the same context as the original scene.

        Yields:
            Tuple of (chunk, is_complete, variants_data)
        """
        CHOICES_MARKER = "###CHOICES###"

        # Get settings for max_tokens calculation
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

        # Calculate max tokens
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        # Use cache-friendly helper for consistent message prefix
        messages = await self._service._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction
        if custom_prompt and custom_prompt.strip():
            # Guided variant: Use different task instruction with custom guidance
            # This intentionally breaks cache as the user wants different behavior
            scene_length = generation_prefs.get("scene_length", "medium")
            scene_length_description = self._service._get_scene_length_description(scene_length)

            # Get prose_style from writing preset
            prose_style = 'balanced'
            if db and user_id:
                from ...models.writing_style_preset import WritingStylePreset
                active_preset = db.query(WritingStylePreset).filter(
                    WritingStylePreset.user_id == user_id,
                    WritingStylePreset.is_active == True
                ).first()
                if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style

            immediate_situation = context.get("current_situation") or ""
            immediate_situation = str(immediate_situation) if immediate_situation else ""
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            tone = context.get('tone', '')

            task_content = f"Regenerate the scene with the following guidance: {custom_prompt.strip()}\n\n"
            task_content += prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )

            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
        else:
            # Simple regeneration: Use EXACT same task instruction as scene generation
            # This enables 100% cache hit rate
            task_content = self._service._build_scene_task_message(
                context=context,
                user_settings=user_settings,
                db=db,
                include_choices_reminder=not separate_choice_generation
            )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN VARIANT] Starting streaming regeneration with n={n} for scene {scene_id}, guided={bool(custom_prompt)}")

        streaming_buffer = ""
        found_marker_in_stream = False

        async for chunk, is_complete, contents in self.generate_stream_with_messages_multi(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        ):
            if not is_complete:
                streaming_buffer += chunk

                if not found_marker_in_stream and CHOICES_MARKER in streaming_buffer:
                    parts = streaming_buffer.split(CHOICES_MARKER, 1)
                    yield (parts[0], False, None)
                    found_marker_in_stream = True
                elif not found_marker_in_stream:
                    if len(streaming_buffer) > len(CHOICES_MARKER) * 2:
                        excess_length = len(streaming_buffer) - len(CHOICES_MARKER)
                        yield (streaming_buffer[:excess_length], False, None)
                        streaming_buffer = streaming_buffer[excess_length:]
            else:
                variants_data = []

                for idx, content in enumerate(contents):
                    cleaned_content = self._service._clean_scene_content(content)
                    scene_content, parsed_choices = self._service._extract_choices_from_response_end(cleaned_content)

                    if separate_choice_generation:
                        parsed_choices = None

                    variants_data.append({
                        "content": scene_content.strip(),
                        "choices": parsed_choices or []
                    })

                    logger.info(f"[MULTI-GEN VARIANT] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")

                yield ("", True, variants_data)

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
        """
        Regenerate n scene variants with choices (non-streaming).

        Returns:
            List of dicts: [{"content": str, "choices": list}, ...]
        """
        CHOICES_MARKER = "###CHOICES###"

        # Get settings for max_tokens calculation
        generation_prefs = user_settings.get("generation_preferences", {})
        choices_count = generation_prefs.get("choices_count", 4)
        separate_choice_generation = generation_prefs.get("separate_choice_generation", False)

        # Calculate max tokens
        max_tokens = prompt_manager.get_max_tokens("scene_generation", user_settings)

        # Use cache-friendly helper for consistent message prefix
        messages = await self._service._build_cache_friendly_message_prefix(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        # Build task instruction
        if custom_prompt and custom_prompt.strip():
            # Guided variant: Use different task instruction with custom guidance
            scene_length = generation_prefs.get("scene_length", "medium")
            scene_length_description = self._service._get_scene_length_description(scene_length)

            # Get prose_style from writing preset
            prose_style = 'balanced'
            if db and user_id:
                from ...models.writing_style_preset import WritingStylePreset
                active_preset = db.query(WritingStylePreset).filter(
                    WritingStylePreset.user_id == user_id,
                    WritingStylePreset.is_active == True
                ).first()
                if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
                    prose_style = active_preset.prose_style

            immediate_situation = context.get("current_situation") or ""
            immediate_situation = str(immediate_situation) if immediate_situation else ""
            has_immediate = bool(immediate_situation and immediate_situation.strip())
            tone = context.get('tone', '')

            task_content = f"Regenerate the scene with the following guidance: {custom_prompt.strip()}\n\n"
            task_content += prompt_manager.get_task_instruction(
                has_immediate=has_immediate,
                prose_style=prose_style,
                tone=tone,
                immediate_situation=immediate_situation or "",
                scene_length_description=scene_length_description
            )

            if not separate_choice_generation:
                choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
                if choices_reminder:
                    task_content = task_content + "\n\n" + choices_reminder
        else:
            # Simple regeneration: Use EXACT same task instruction as scene generation
            task_content = self._service._build_scene_task_message(
                context=context,
                user_settings=user_settings,
                db=db,
                include_choices_reminder=not separate_choice_generation
            )

        messages.append({"role": "user", "content": task_content})

        logger.info(f"[MULTI-GEN VARIANT] Starting non-streaming regeneration with n={n} for scene {scene_id}, guided={bool(custom_prompt)}")

        contents = await self.generate_multi_completions(
            messages=messages,
            user_id=user_id,
            user_settings=user_settings,
            n=n,
            max_tokens=max_tokens
        )

        variants_data = []
        for idx, content in enumerate(contents):
            cleaned_content = self._service._clean_scene_content(content)
            scene_content, parsed_choices = self._service._extract_choices_from_response_end(cleaned_content)

            if separate_choice_generation:
                parsed_choices = None

            variants_data.append({
                "content": scene_content.strip(),
                "choices": parsed_choices or []
            })

            logger.info(f"[MULTI-GEN VARIANT] Variant {idx}: {len(scene_content)} chars, {len(parsed_choices or [])} choices")

        return variants_data
