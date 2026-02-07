"""
Chapter Summary Service

Handles generation and management of chapter summaries including:
- Full chapter summaries
- Incremental summary updates
- Story-so-far generation
- Batch summary management
"""

import time
import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session

from ..models import (
    Chapter, Scene, Story, User, UserSettings,
    ChapterSummaryBatch, StoryFlow
)
from .llm.service import UnifiedLLMService
from .llm.prompts import prompt_manager

logger = logging.getLogger(__name__)


class ChapterSummaryService:
    """Service for managing chapter summaries."""

    def __init__(self, db: Session, user_id: int, user_settings: Optional[dict] = None):
        self.db = db
        self.user_id = user_id
        self.llm_service = UnifiedLLMService()
        self._user_settings = user_settings

    def _get_user_settings(self) -> Optional[dict]:
        """Get user settings with caching."""
        if self._user_settings is None:
            user_settings_obj = self.db.query(UserSettings).filter(
                UserSettings.user_id == self.user_id
            ).first()
            self._user_settings = user_settings_obj.to_dict() if user_settings_obj else None

            # Add allow_nsfw from user
            if self._user_settings is not None:
                user = self.db.query(User).filter(User.id == self.user_id).first()
                if user:
                    self._user_settings['allow_nsfw'] = user.allow_nsfw

        return self._user_settings

    async def generate_chapter_summary(self, chapter_id: int) -> str:
        """
        Generate a summary of the chapter's scenes WITH CONTEXT from previous chapters.
        This is stored in chapter.auto_summary and represents ONLY this chapter's content,
        but the LLM receives previous chapter summaries to maintain consistency.

        Note: Filters by branch_id to ensure only chapters from the same branch are included.
        """
        op_start = time.perf_counter()
        trace_id = f"chap-sum-{uuid.uuid4()}"
        status = "error"
        summary_text = ""

        try:
            chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                logger.warning(f"[CHAPTER:SUMMARY:SKIP] trace_id={trace_id} chapter_id={chapter_id} reason=not_found")
                return ""

            logger.info(f"[CHAPTER:SUMMARY:START] trace_id={trace_id} chapter_id={chapter_id} story_id={chapter.story_id} branch_id={chapter.branch_id}")

            # Get ALL PREVIOUS chapters' summaries for context (filtered by branch_id)
            previous_chapters_query = self.db.query(Chapter).filter(
                Chapter.story_id == chapter.story_id,
                Chapter.chapter_number < chapter.chapter_number
            )
            if chapter.branch_id:
                previous_chapters_query = previous_chapters_query.filter(Chapter.branch_id == chapter.branch_id)
            previous_chapters = previous_chapters_query.order_by(Chapter.chapter_number).all()

            previous_summaries = []
            for ch in previous_chapters:
                if ch.auto_summary:
                    previous_summaries.append(f"Chapter {ch.chapter_number} ({ch.title or 'Untitled'}): {ch.auto_summary}")

            # Get all scenes in THIS chapter with their active variants
            scene_query = self.db.query(Scene).filter(Scene.chapter_id == chapter_id)
            if chapter.branch_id:
                scene_query = scene_query.filter(Scene.branch_id == chapter.branch_id)
            scenes = scene_query.order_by(Scene.sequence_number).all()

            if not scenes:
                logger.warning(f"[CHAPTER:SUMMARY:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_scenes")
                return "No scenes in this chapter yet."

            # Build scene content from active variants
            scene_contents = []
            for scene in scenes:
                flow = self.db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()

                if flow and flow.scene_variant:
                    scene_contents.append(f"Scene {scene.sequence_number}: {flow.scene_variant.content}")

            if not scene_contents:
                logger.warning(f"[CHAPTER:SUMMARY:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_active_variants")
                return "No content available to summarize."

            # Prepare context for LLM
            combined_content = "\n\n".join(scene_contents)
            context_section = ""
            if previous_summaries:
                context_section = f"Previous Chapters (for context):\n{chr(10).join(previous_summaries)}\n\n"

            # Get prompt from prompts.yml
            prompt = prompt_manager.get_prompt(
                "chapter_summary", "user",
                user_id=self.user_id, db=self.db,
                context_section=context_section,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title or 'Untitled',
                scenes_content=combined_content
            )
            if not prompt:
                prompt = f"{context_section}Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}\n\nScenes:\n{combined_content}\n\nSummarize this chapter factually."

            user_settings = self._get_user_settings()

            # Get system prompt
            system_prompt = prompt_manager.get_prompt("chapter_summary", "system", user_id=self.user_id, db=self.db)
            if not system_prompt:
                system_prompt = "You are a helpful assistant that creates concise narrative summaries."

            # Generate summary - no max_tokens override, uses user settings
            llm_start = time.perf_counter()
            summary = await self._generate_with_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                user_settings=user_settings,
                trace_context=f"chapter_summary_{chapter_id}"
            )
            logger.info(f"[CHAPTER:SUMMARY:LLM] trace_id={trace_id} duration_ms={(time.perf_counter() - llm_start) * 1000:.2f}")

            # Update chapter
            chapter.auto_summary = summary
            if scenes:
                chapter.last_summary_scene_count = max(s.sequence_number for s in scenes)
            else:
                chapter.last_summary_scene_count = 0
            self.db.commit()
            summary_text = summary

            status = "success"
            logger.info(f"[CHAPTER] Generated summary for chapter {chapter_id}: {len(summary)} chars trace_id={trace_id}")

            return summary

        except Exception as e:
            logger.error(f"[CHAPTER:SUMMARY:ERROR] trace_id={trace_id} chapter_id={chapter_id} error={e}")
            return ""
        finally:
            duration_ms = (time.perf_counter() - op_start) * 1000
            if duration_ms > 15000:
                logger.error(f"[CHAPTER:SUMMARY:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(summary_text)}")
            elif duration_ms > 5000:
                logger.warning(f"[CHAPTER:SUMMARY:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(summary_text)}")
            else:
                logger.info(f"[CHAPTER:SUMMARY:DONE] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(summary_text)}")

    async def generate_chapter_summary_incremental(self, chapter_id: int, max_new_scenes: int = None) -> str:
        """
        Generate or extend chapter summary incrementally.

        Instead of re-summarizing all scenes, this:
        1. Takes existing summary (if exists)
        2. Gets only NEW scenes since last summary
        3. Asks LLM to create cohesive summary combining existing + new

        Args:
            chapter_id: The chapter to summarize.
            max_new_scenes: If set, limit the number of new scenes processed per call.
                            Useful for backfills to avoid exceeding context window.
        """
        op_start = time.perf_counter()
        trace_id = f"chap-sum-inc-{uuid.uuid4()}"
        status = "error"
        combined_summary = ""

        try:
            chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                logger.warning(f"[CHAPTER:SUMMARY:INC:SKIP] trace_id={trace_id} chapter_id={chapter_id} reason=not_found")
                return ""

            logger.info(f"[CHAPTER:SUMMARY:INC:START] trace_id={trace_id} chapter_id={chapter_id} story_id={chapter.story_id} branch_id={chapter.branch_id}")

            # Get scenes since last summary
            last_summary_count = chapter.last_summary_scene_count or 0
            new_scene_query = self.db.query(Scene).filter(
                Scene.chapter_id == chapter_id,
                Scene.sequence_number > last_summary_count
            )
            if chapter.branch_id:
                new_scene_query = new_scene_query.filter(Scene.branch_id == chapter.branch_id)
            new_scene_query = new_scene_query.order_by(Scene.sequence_number)
            if max_new_scenes:
                new_scene_query = new_scene_query.limit(max_new_scenes)
            new_scenes = new_scene_query.all()

            if not new_scenes:
                logger.info(f"[CHAPTER:SUMMARY:INC:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_new_scenes")
                status = "no_new_scenes"
                return chapter.auto_summary or ""

            # Build scene content from active variants
            scene_contents = []
            for scene in new_scenes:
                flow = self.db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()

                if flow and flow.scene_variant:
                    scene_contents.append(f"Scene {scene.sequence_number}: {flow.scene_variant.content}")

            if not scene_contents:
                logger.info(f"[CHAPTER:SUMMARY:INC:EMPTY] trace_id={trace_id} chapter_id={chapter_id} reason=no_active_variants")
                status = "no_active_variants"
                return chapter.auto_summary or ""

            new_scenes_text = "\n\n".join(scene_contents)

            # Get previous chapter summary for narrative continuity
            previous_chapter_text = ""
            if chapter.chapter_number > 1:
                previous_chapter_query = self.db.query(Chapter).filter(
                    Chapter.story_id == chapter.story_id,
                    Chapter.chapter_number == chapter.chapter_number - 1,
                    Chapter.auto_summary.isnot(None)
                )
                if chapter.branch_id:
                    previous_chapter_query = previous_chapter_query.filter(Chapter.branch_id == chapter.branch_id)
                previous_chapter = previous_chapter_query.first()
                if previous_chapter and previous_chapter.auto_summary:
                    previous_chapter_text = f"\nPrevious Chapter Summary:\n{previous_chapter.auto_summary}\n"

            # Build prompt based on whether we have existing summary
            existing_summary = chapter.auto_summary

            if existing_summary:
                prompt = prompt_manager.get_prompt(
                    "chapter_summary_incremental", "user",
                    user_id=self.user_id, db=self.db,
                    previous_chapter_text=previous_chapter_text,
                    last_summary_count=last_summary_count,
                    existing_summary=existing_summary,
                    new_scenes_start=last_summary_count + 1,
                    new_scenes_end=chapter.scenes_count,
                    new_scenes_text=new_scenes_text
                )
                template_key = "chapter_summary_incremental"
            else:
                prompt = prompt_manager.get_prompt(
                    "chapter_summary_initial", "user",
                    user_id=self.user_id, db=self.db,
                    previous_chapter_text=previous_chapter_text,
                    chapter_number=chapter.chapter_number,
                    chapter_title=chapter.title or 'Untitled',
                    new_scenes_text=new_scenes_text
                )
                template_key = "chapter_summary_initial"

            if not prompt:
                prompt = f"{previous_chapter_text}Chapter {chapter.chapter_number}: {chapter.title or 'Untitled'}\n\nScenes:\n{new_scenes_text}\n\nSummarize factually."

            user_settings = self._get_user_settings()

            system_prompt = prompt_manager.get_prompt(template_key, "system", user_id=self.user_id, db=self.db)
            if not system_prompt:
                system_prompt = "You are a story state tracker. Extract facts, not prose."

            # Generate summary - no max_tokens override, uses user settings
            llm_start = time.perf_counter()
            batch_summary = await self._generate_with_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                user_settings=user_settings,
                trace_context=f"chapter_summary_inc_{chapter_id}"
            )
            logger.info(f"[CHAPTER:SUMMARY:INC:LLM] trace_id={trace_id} duration_ms={(time.perf_counter() - llm_start) * 1000:.2f}")

            # Determine scene range for this batch
            batch_start = last_summary_count + 1
            batch_end = max(s.sequence_number for s in new_scenes)

            # Check if batch already exists for this scene range (upsert logic)
            existing_batch = self.db.query(ChapterSummaryBatch).filter(
                ChapterSummaryBatch.chapter_id == chapter_id,
                ChapterSummaryBatch.start_scene_sequence == batch_start,
                ChapterSummaryBatch.end_scene_sequence == batch_end
            ).first()

            if existing_batch:
                # Update existing batch
                existing_batch.summary = batch_summary
                self.db.flush()
                logger.info(f"[CHAPTER:SUMMARY:BATCH] Updated existing batch for chapter {chapter_id}: scenes {batch_start}-{batch_end}")
            else:
                # Create new batch
                batch = ChapterSummaryBatch(
                    chapter_id=chapter_id,
                    start_scene_sequence=batch_start,
                    end_scene_sequence=batch_end,
                    summary=batch_summary
                )
                self.db.add(batch)
                self.db.flush()

            # Update chapter's auto_summary from all batches
            update_chapter_summary_from_batches(chapter_id, self.db)

            # Get batch count for logging
            all_batches = self.db.query(ChapterSummaryBatch).filter(
                ChapterSummaryBatch.chapter_id == chapter_id
            ).all()

            combined_summary = chapter.auto_summary or ""

            logger.info(f"[CHAPTER] {'Extended' if existing_summary else 'Created'} summary for chapter {chapter_id}: {len(batch_summary)} chars (scenes {batch_start}-{batch_end}), total batches: {len(all_batches)}, trace_id={trace_id}")
            status = "success"
            return combined_summary

        except Exception as e:
            logger.error(f"[CHAPTER:SUMMARY:INC:ERROR] trace_id={trace_id} chapter_id={chapter_id} error={e}")
            status = "error"
            raise

        finally:
            duration_ms = (time.perf_counter() - op_start) * 1000
            if duration_ms > 15000:
                logger.error(f"[CHAPTER:SUMMARY:INC:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(combined_summary)}")
            elif duration_ms > 5000:
                logger.warning(f"[CHAPTER:SUMMARY:INC:SLOW] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(combined_summary)}")
            else:
                logger.info(f"[CHAPTER:SUMMARY:INC:DONE] trace_id={trace_id} chapter_id={chapter_id} status={status} duration_ms={duration_ms:.2f} summary_len={len(combined_summary)}")

    async def generate_chapter_summary_incremental_cache_friendly(
        self,
        chapter_id: int,
        scene_generation_context: dict,
        max_new_scenes: int = None
    ) -> str:
        """
        Generate chapter summary using cache-friendly multi-message structure.

        This version uses the same message prefix as scene generation to maximize
        LLM cache hits. It should be called AFTER scene generation and extractions
        complete, when the ~13,000 token prefix is already cached.

        Args:
            chapter_id: The chapter to summarize
            scene_generation_context: The context dict from scene generation
            max_new_scenes: If set, limit the number of new scenes processed per call

        Returns:
            The combined chapter summary
        """
        op_start = time.perf_counter()
        trace_id = f"chap-sum-cf-{uuid.uuid4()}"
        status = "error"
        combined_summary = ""

        try:
            chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                logger.warning(f"[CHAPTER:SUMMARY:CF:SKIP] trace_id={trace_id} chapter_id={chapter_id} reason=not_found")
                return ""

            logger.info(f"[CHAPTER:SUMMARY:CF:START] trace_id={trace_id} chapter_id={chapter_id} story_id={chapter.story_id}")

            # Get the last summarized scene count
            last_summary_count = chapter.last_summary_scene_count or 0

            # Get new scenes since last summary
            new_scenes_query = self.db.query(Scene).join(StoryFlow).filter(
                StoryFlow.story_id == chapter.story_id,
                StoryFlow.is_active == True,
                Scene.chapter_id == chapter_id,
                Scene.is_deleted == False,
                Scene.sequence_number > last_summary_count
            ).order_by(Scene.sequence_number)

            if max_new_scenes:
                new_scenes_query = new_scenes_query.limit(max_new_scenes)

            new_scenes = new_scenes_query.all()

            if not new_scenes:
                logger.info(f"[CHAPTER:SUMMARY:CF:SKIP] trace_id={trace_id} chapter_id={chapter_id} reason=no_new_scenes last_summary_count={last_summary_count}")
                return chapter.auto_summary or ""

            # Build scene content
            scene_contents = []
            for scene in new_scenes:
                flow = self.db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()
                if flow and flow.scene_variant:
                    scene_contents.append(f"Scene {scene.sequence_number}: {flow.scene_variant.content}")

            if not scene_contents:
                logger.warning(f"[CHAPTER:SUMMARY:CF:EMPTY] trace_id={trace_id} chapter_id={chapter_id}")
                return chapter.auto_summary or ""

            scenes_content = "\n\n".join(scene_contents)

            # Get previous chapter summary for context
            context_section = ""
            if chapter.chapter_number > 1:
                previous_chapter_query = self.db.query(Chapter).filter(
                    Chapter.story_id == chapter.story_id,
                    Chapter.chapter_number == chapter.chapter_number - 1,
                    Chapter.auto_summary.isnot(None)
                )
                if chapter.branch_id:
                    previous_chapter_query = previous_chapter_query.filter(Chapter.branch_id == chapter.branch_id)
                previous_chapter = previous_chapter_query.first()
                if previous_chapter and previous_chapter.auto_summary:
                    context_section = f"Previous Chapter Summary:\n{previous_chapter.auto_summary}\n\n"

            user_settings = self._get_user_settings()

            # Use cache-friendly LLM method
            llm_start = time.perf_counter()
            batch_summary = await self.llm_service.generate_chapter_summary_cache_friendly(
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title,
                scenes_content=scenes_content,
                context=scene_generation_context,
                user_id=self.user_id,
                user_settings=user_settings,
                db=self.db,
                context_section=context_section
            )
            logger.info(f"[CHAPTER:SUMMARY:CF:LLM] trace_id={trace_id} duration_ms={(time.perf_counter() - llm_start) * 1000:.2f}")

            # Determine scene range for this batch
            batch_start = last_summary_count + 1
            batch_end = max(s.sequence_number for s in new_scenes)

            # Check if batch already exists (upsert)
            existing_batch = self.db.query(ChapterSummaryBatch).filter(
                ChapterSummaryBatch.chapter_id == chapter_id,
                ChapterSummaryBatch.start_scene_sequence == batch_start,
                ChapterSummaryBatch.end_scene_sequence == batch_end
            ).first()

            if existing_batch:
                existing_batch.summary = batch_summary
                self.db.flush()
                logger.info(f"[CHAPTER:SUMMARY:CF:BATCH] Updated batch for chapter {chapter_id}: scenes {batch_start}-{batch_end}")
            else:
                batch = ChapterSummaryBatch(
                    chapter_id=chapter_id,
                    start_scene_sequence=batch_start,
                    end_scene_sequence=batch_end,
                    summary=batch_summary
                )
                self.db.add(batch)
                self.db.flush()

            # Update chapter's auto_summary from all batches
            update_chapter_summary_from_batches(chapter_id, self.db)

            combined_summary = chapter.auto_summary or ""
            status = "success"
            logger.info(f"[CHAPTER:SUMMARY:CF] Generated for chapter {chapter_id}: {len(batch_summary)} chars (scenes {batch_start}-{batch_end}), trace_id={trace_id}")
            return combined_summary

        except Exception as e:
            logger.error(f"[CHAPTER:SUMMARY:CF:ERROR] trace_id={trace_id} chapter_id={chapter_id} error={e}")
            status = "error"
            raise

        finally:
            duration_ms = (time.perf_counter() - op_start) * 1000
            if duration_ms > 15000:
                logger.error(f"[CHAPTER:SUMMARY:CF:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f}")
            elif duration_ms > 5000:
                logger.warning(f"[CHAPTER:SUMMARY:CF:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f}")
            else:
                logger.info(f"[CHAPTER:SUMMARY:CF:DONE] trace_id={trace_id} status={status} duration_ms={duration_ms:.2f}")

    async def generate_story_so_far(self, chapter_id: int, auto_commit: bool = True) -> Optional[str]:
        """
        Generate "Story So Far" for a chapter using LLM rolling consolidation.
        Does NOT include the current chapter's summary.

        Rolling consolidation approach:
        - For chapter N, combine chapter (N-1)'s story_so_far + chapter (N-1)'s auto_summary
        - Call LLM with the story_so_far prompt to produce a consolidated ~600-800 word summary
        - This keeps input bounded regardless of how many chapters exist

        Returns None if there are no previous chapters with summaries.
        Note: Filters by branch_id to ensure only chapters from the same branch are included.
        """
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return None

        story_id = chapter.story_id

        # Get all previous chapters ordered by chapter_number
        previous_chapters_query = self.db.query(Chapter).filter(
            Chapter.story_id == story_id,
            Chapter.chapter_number < chapter.chapter_number
        )
        if chapter.branch_id:
            previous_chapters_query = previous_chapters_query.filter(Chapter.branch_id == chapter.branch_id)
        previous_chapters = previous_chapters_query.order_by(Chapter.chapter_number).all()

        # Filter to chapters that have summaries
        chapters_with_summaries = [ch for ch in previous_chapters if ch.auto_summary]

        if not chapters_with_summaries:
            logger.info(f"[CHAPTER] No previous chapter summaries available for chapter {chapter_id}")
            chapter.story_so_far = None
            if auto_commit:
                self.db.commit()
            else:
                self.db.flush()
            return None

        # For only one previous chapter, use its auto_summary directly (no consolidation needed)
        if len(chapters_with_summaries) == 1:
            only_ch = chapters_with_summaries[0]
            story_so_far = f"=== Chapter {only_ch.chapter_number}: {only_ch.title or 'Untitled'} ===\n{only_ch.auto_summary}"
            chapter.story_so_far = story_so_far
            if auto_commit:
                self.db.commit()
            else:
                self.db.flush()
            logger.info(f"[CHAPTER] story_so_far for chapter {chapter_id}: single previous chapter, {len(story_so_far)} chars (no consolidation needed)")
            return story_so_far

        # Rolling consolidation: combine previous story_so_far + latest chapter's summary
        # Use the most recent previous chapter's story_so_far if available
        latest_prev = chapters_with_summaries[-1]
        earlier_chapters = chapters_with_summaries[:-1]

        # Build the combined_chapters input for the LLM prompt
        # If the second-to-last chapter has a story_so_far, use that + latest chapter summary
        # Otherwise, fall back to concatenating all summaries (first-time consolidation)
        if latest_prev.story_so_far:
            combined_chapters = f"CONSOLIDATED STORY SO FAR (Chapters 1-{latest_prev.chapter_number - 1}):\n{latest_prev.story_so_far}\n\n"
            combined_chapters += f"=== Chapter {latest_prev.chapter_number}: {latest_prev.title or 'Untitled'} ===\n{latest_prev.auto_summary}"
        else:
            # No prior consolidation exists — combine all chapter summaries
            parts = []
            for ch in chapters_with_summaries:
                parts.append(f"=== Chapter {ch.chapter_number}: {ch.title or 'Untitled'} ===\n{ch.auto_summary}")
            combined_chapters = "\n\n".join(parts)

        # Fetch story metadata for the prompt template
        story = self.db.query(Story).filter(Story.id == story_id).first()
        genre = story.genre if story and story.genre else "fiction"
        content_rating = story.content_rating if story and story.content_rating else "sfw"
        tone = story.tone if story and story.tone else "neutral"

        # Get prompts from prompts.yml
        system_prompt = prompt_manager.get_prompt(
            "story_so_far", "system",
            user_id=self.user_id, db=self.db
        )
        if not system_prompt:
            system_prompt = "You are a story state tracker. Consolidate chapter facts into a single state document."

        user_prompt = prompt_manager.get_prompt(
            "story_so_far", "user",
            user_id=self.user_id, db=self.db,
            genre=genre,
            content_rating=content_rating,
            tone=tone,
            combined_chapters=combined_chapters
        )
        if not user_prompt:
            user_prompt = f"Consolidate these chapter summaries into a single factual summary:\n\n{combined_chapters}\n\nAim for 600-800 words. Facts only."

        user_settings = self._get_user_settings()

        # Generate consolidated story_so_far via LLM
        story_so_far = await self._generate_with_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            user_settings=user_settings,
            trace_context=f"story_so_far_{chapter_id}"
        )

        # Update chapter
        chapter.story_so_far = story_so_far
        if auto_commit:
            self.db.commit()
        else:
            self.db.flush()

        total_chars = len(story_so_far)
        logger.info(f"[CHAPTER] Consolidated story_so_far for chapter {chapter_id} from {len(chapters_with_summaries)} previous chapters: {total_chars} chars")

        return story_so_far

    async def _generate_with_llm(
        self,
        prompt: str,
        system_prompt: str,
        user_settings: Optional[dict],
        trace_context: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate content using either extraction LLM or main LLM based on user settings.
        """
        use_extraction_llm = user_settings.get('generation_preferences', {}).get('use_extraction_llm_for_summary', False) if user_settings else False
        extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False) if user_settings else False

        if use_extraction_llm and extraction_enabled:
            try:
                from .llm.extraction_service import ExtractionLLMService
                logger.info(f"[CHAPTER:SUMMARY] Using extraction LLM for {trace_context}")

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

                from litellm import acompletion
                params = extraction_service._get_generation_params(max_tokens=max_tokens)
                response = await acompletion(
                    **params,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    timeout=extraction_service.timeout.total * 2
                )
                result = response.choices[0].message.content.strip()
                logger.info(f"[CHAPTER:SUMMARY] Successfully generated with extraction LLM for {trace_context} (length={len(result)})")
                return result

            except Exception as e:
                logger.warning(f"[CHAPTER:SUMMARY] Extraction LLM failed for {trace_context}, falling back to main LLM: {e}")

        # Use main LLM (default or fallback)
        logger.info(f"[CHAPTER:SUMMARY] Using main LLM for {trace_context}")
        return await self.llm_service.generate(
            prompt=prompt,
            user_id=self.user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )


# Module-level helper functions (for use by other modules)

def combine_chapter_batches(chapter_id: int, db: Session) -> Optional[str]:
    """
    Get the latest chapter summary from batches.

    Each batch stores the complete cumulative summary up to that point.
    Returns None if no batches exist.
    """
    latest_batch = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).order_by(ChapterSummaryBatch.end_scene_sequence.desc()).first()

    if not latest_batch:
        return None

    return latest_batch.summary


def update_chapter_summary_from_batches(chapter_id: int, db: Session) -> None:
    """
    Update chapter.auto_summary and last_summary_scene_count from current batches.
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return

    batches = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).order_by(ChapterSummaryBatch.start_scene_sequence).all()

    if batches:
        chapter.auto_summary = combine_chapter_batches(chapter_id, db)
        chapter.last_summary_scene_count = max(b.end_scene_sequence for b in batches)
    else:
        chapter.auto_summary = None
        chapter.last_summary_scene_count = 0

    db.commit()


def invalidate_chapter_batches_for_scene(scene_id: int, db: Session) -> None:
    """
    Invalidate chapter summary batches if scene was part of summarized range.
    This should be called when a scene's content is modified.
    """
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene or not scene.chapter_id:
        return

    chapter = db.query(Chapter).filter(Chapter.id == scene.chapter_id).first()
    if not chapter:
        return

    # Find batches that contain this scene
    affected_batches = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter.id,
        ChapterSummaryBatch.start_scene_sequence <= scene.sequence_number,
        ChapterSummaryBatch.end_scene_sequence >= scene.sequence_number
    ).all()

    if affected_batches:
        for batch in affected_batches:
            db.delete(batch)

        logger.info(f"[INVALIDATE] Invalidated {len(affected_batches)} batch(es) for chapter {chapter.id} due to scene {scene_id} modification")

        # Recalculate summary from remaining batches
        update_chapter_summary_from_batches(chapter.id, db)
