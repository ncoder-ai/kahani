"""
Chapter Progress Service

Tracks chapter plot progress, extracts completed events from scenes,
and generates adaptive pacing guidance for the LLM.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from ..models.chapter import Chapter
from .llm.prompts import PromptManager

logger = logging.getLogger(__name__)
prompt_manager = PromptManager()


def clean_llm_json(json_str: str) -> str:
    """Clean common LLM JSON formatting issues."""
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()


class ChapterProgressService:
    """
    Service for tracking chapter plot progress.
    
    Responsibilities:
    - Extract completed plot events from generated scenes
    - Track which key events have occurred
    - Generate adaptive pacing guidance based on progress
    - Provide progress information for UI display
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_chapter_progress(self, chapter: Chapter) -> Dict[str, Any]:
        """
        Get the current progress for a chapter.
        
        Returns:
            Dict with completed_events, total_events, progress_percentage, etc.
        """
        if not chapter.chapter_plot:
            return {
                "has_plot": False,
                "completed_events": [],
                "total_events": 0,
                "progress_percentage": 0,
                "remaining_events": [],
                "climax_reached": False,
                "resolution_reached": False,
                "scene_count": 0
            }
        
        key_events = chapter.chapter_plot.get("key_events", [])
        total_events = len(key_events)
        
        # Get progress from stored data or initialize
        progress_data = chapter.plot_progress or {
            "completed_events": [],
            "scene_count": 0,
            "climax_reached": False,
            "resolution_reached": False,
            "last_updated": None
        }
        
        completed_events = progress_data.get("completed_events", [])
        
        # Calculate remaining events
        remaining_events = [e for e in key_events if e not in completed_events]
        
        # Calculate progress percentage
        progress_percentage = (len(completed_events) / total_events * 100) if total_events > 0 else 0
        
        # Get actual scene count from database (more accurate than stored value)
        actual_scene_count = 0
        try:
            from ..models.scene import Scene
            actual_scene_count = self.db.query(Scene).filter(
                Scene.chapter_id == chapter.id,
                Scene.is_deleted == False
            ).count()
        except Exception as e:
            logger.warning(f"[CHAPTER PROGRESS] Failed to get scene count: {e}")
            # Fall back to stored value
            actual_scene_count = progress_data.get("scene_count", 0)
        
        return {
            "has_plot": True,
            "completed_events": completed_events,
            "total_events": total_events,
            "progress_percentage": round(progress_percentage, 1),
            "remaining_events": remaining_events,
            "climax_reached": progress_data.get("climax_reached", False),
            "resolution_reached": progress_data.get("resolution_reached", False),
            "scene_count": actual_scene_count,  # Use actual scene count, not stored
            "climax": chapter.chapter_plot.get("climax"),
            "resolution": chapter.chapter_plot.get("resolution"),
            "key_events": key_events
        }
    
    def update_progress(
        self,
        chapter: Chapter,
        new_completed_events: List[str],
        scene_count: Optional[int] = None,
        climax_reached: bool = False
    ) -> Dict[str, Any]:
        """
        Update the progress for a chapter.
        
        Args:
            chapter: The chapter to update
            new_completed_events: List of newly completed event descriptions
            scene_count: Current scene count (optional, auto-calculated if not provided)
            climax_reached: Whether the climax has been reached
            
        Returns:
            Updated progress data
        """
        from sqlalchemy.orm.attributes import flag_modified
        
        # Refresh to get latest state from database
        # This ensures we have the most recent plot_progress before updating
        self.db.refresh(chapter)
        
        # Create a NEW dict (not reference) to ensure SQLAlchemy detects change
        # This is critical - SQLAlchemy doesn't detect in-place mutations of JSON columns
        existing_progress = chapter.plot_progress or {}
        progress_data = {
            "completed_events": list(existing_progress.get("completed_events", [])),
            "scene_count": existing_progress.get("scene_count", 0),
            "climax_reached": existing_progress.get("climax_reached", False),
            "resolution_reached": existing_progress.get("resolution_reached", False),
            "last_updated": existing_progress.get("last_updated")
        }
        
        # Merge new completed events (avoid duplicates)
        existing_completed = set(progress_data["completed_events"])
        existing_completed.update(new_completed_events)
        
        # Update scene count
        if scene_count is not None:
            progress_data["scene_count"] = scene_count
        else:
            # Auto-calculate from chapter's scenes
            progress_data["scene_count"] = len(chapter.scenes) if chapter.scenes else 0
        
        # Update climax status (once True, stays True)
        if climax_reached or progress_data.get("climax_reached", False):
            progress_data["climax_reached"] = True
        
        # Update completed events
        progress_data["completed_events"] = list(existing_completed)
        progress_data["last_updated"] = datetime.utcnow().isoformat()
        
        # Assign NEW dict and flag as modified to ensure SQLAlchemy persists the change
        chapter.plot_progress = progress_data
        flag_modified(chapter, "plot_progress")
        self.db.commit()
        self.db.refresh(chapter)
        
        logger.info(f"Updated chapter {chapter.id} progress: {len(existing_completed)} events completed")
        
        return progress_data
    
    def toggle_event_completion(
        self,
        chapter: Chapter,
        event: str,
        completed: bool
    ) -> Dict[str, Any]:
        """
        Manually toggle an event's completion status.
        DEPRECATED: Use toggle_event_completion_with_batch instead.
        
        Args:
            chapter: The chapter to update
            event: The event description
            completed: Whether the event is completed
            
        Returns:
            Updated progress data
        """
        # Get existing progress or initialize - make a copy to ensure SQLAlchemy detects the change
        existing_progress = chapter.plot_progress or {}
        progress_data = {
            "completed_events": list(existing_progress.get("completed_events", [])),
            "scene_count": existing_progress.get("scene_count", 0),
            "climax_reached": existing_progress.get("climax_reached", False),
            "resolution_reached": existing_progress.get("resolution_reached", False),
            "last_updated": existing_progress.get("last_updated")
        }

        completed_events = set(progress_data.get("completed_events", []))

        if completed:
            completed_events.add(event)
        else:
            completed_events.discard(event)

        progress_data["completed_events"] = list(completed_events)
        progress_data["last_updated"] = datetime.utcnow().isoformat()

        # Assign a new dict to ensure SQLAlchemy detects the change
        chapter.plot_progress = progress_data

        # Force SQLAlchemy to detect the change by flagging the attribute as modified
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(chapter, "plot_progress")

        self.db.commit()
        self.db.refresh(chapter)

        logger.info(f"Toggled event '{event[:50]}...' to {completed} for chapter {chapter.id}")

        return chapter.plot_progress
    
    # ==================== BATCH-BASED PLOT PROGRESS METHODS ====================
    
    def get_latest_plot_progress_from_batches(self, chapter_id: int) -> Optional[List[str]]:
        """
        Get the latest plot progress from batches.
        Returns the completed_events from the latest batch (highest end_scene_sequence).
        """
        from ..models import ChapterPlotProgressBatch
        
        latest_batch = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter_id
        ).order_by(ChapterPlotProgressBatch.end_scene_sequence.desc()).first()
        
        if not latest_batch:
            return None
        
        return latest_batch.completed_events or []
    
    def update_plot_progress_from_batches(self, chapter_id: int) -> None:
        """
        Update chapter.plot_progress and last_plot_extraction_scene_count from current batches.
        Similar to update_chapter_summary_from_batches.
        """
        from ..models import ChapterPlotProgressBatch
        from sqlalchemy.orm.attributes import flag_modified
        
        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return
        
        batches = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter_id
        ).order_by(ChapterPlotProgressBatch.start_scene_sequence).all()
        
        if batches:
            latest_batch = max(batches, key=lambda b: b.end_scene_sequence)
            chapter.plot_progress = {
                "completed_events": latest_batch.completed_events or [],
                "scene_count": latest_batch.end_scene_sequence,
                "last_updated": datetime.utcnow().isoformat()
            }
            chapter.last_plot_extraction_scene_count = latest_batch.end_scene_sequence
        else:
            chapter.plot_progress = None
            chapter.last_plot_extraction_scene_count = 0
        
        flag_modified(chapter, "plot_progress")
        self.db.commit()
        
        logger.info(f"[PLOT_PROGRESS:RESTORE] Restored progress from batches for chapter {chapter_id}")
    
    def invalidate_plot_progress_batches_for_scene(self, scene_id: int) -> None:
        """
        Invalidate plot progress batches if scene was part of extracted range.
        Called when a scene is deleted or modified.
        
        Since batches are cumulative (each batch includes events from previous batches),
        we must also delete all subsequent batches when a batch is invalidated.
        """
        from ..models import Scene, ChapterPlotProgressBatch
        
        scene = self.db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene or not scene.chapter_id:
            return
        
        chapter = self.db.query(Chapter).filter(Chapter.id == scene.chapter_id).first()
        if not chapter:
            return
        
        # Find the first batch that contains this scene
        affected_batch = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter.id,
            ChapterPlotProgressBatch.start_scene_sequence <= scene.sequence_number,
            ChapterPlotProgressBatch.end_scene_sequence >= scene.sequence_number
        ).first()
        
        if affected_batch:
            # Delete this batch AND all subsequent batches (since they're cumulative)
            batches_to_delete = self.db.query(ChapterPlotProgressBatch).filter(
                ChapterPlotProgressBatch.chapter_id == chapter.id,
                ChapterPlotProgressBatch.start_scene_sequence >= affected_batch.start_scene_sequence
            ).all()
            
            for batch in batches_to_delete:
                self.db.delete(batch)
            
            logger.info(f"[PLOT_PROGRESS:INVALIDATE] Invalidated {len(batches_to_delete)} batch(es) for chapter {chapter.id} due to scene {scene_id} modification (scene seq {scene.sequence_number})")
            
            # Recalculate progress from remaining batches
            self.update_plot_progress_from_batches(chapter.id)
    
    def create_plot_progress_batch(
        self,
        chapter: Chapter,
        start_sequence: int,
        end_sequence: int,
        completed_events: List[str]
    ) -> None:
        """
        Create a new plot progress batch with cumulative events.
        Preserves manually toggled events from the current chapter.plot_progress.
        """
        from ..models import ChapterPlotProgressBatch
        from sqlalchemy.orm.attributes import flag_modified
        
        # Get previous batch's events to make this cumulative
        previous_batch = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter.id,
            ChapterPlotProgressBatch.end_scene_sequence < start_sequence
        ).order_by(ChapterPlotProgressBatch.end_scene_sequence.desc()).first()
        
        # Merge with previous events (cumulative)
        all_events = set(previous_batch.completed_events or []) if previous_batch else set()
        all_events.update(completed_events)
        
        # IMPORTANT: Also preserve any manually toggled events from current progress
        # This ensures user's manual toggles aren't lost when new batches are created
        current_progress = chapter.plot_progress or {}
        current_completed = set(current_progress.get("completed_events", []))
        all_events.update(current_completed)
        
        # Create new batch
        batch = ChapterPlotProgressBatch(
            chapter_id=chapter.id,
            start_scene_sequence=start_sequence,
            end_scene_sequence=end_sequence,
            completed_events=list(all_events)
        )
        self.db.add(batch)
        self.db.flush()
        
        # Update chapter's plot_progress from batches
        self.update_plot_progress_from_batches(chapter.id)
        
        logger.info(f"[PLOT_PROGRESS:BATCH] Created batch for chapter {chapter.id} scenes {start_sequence}-{end_sequence} with {len(all_events)} cumulative events")
    
    def toggle_event_completion_with_batch(
        self,
        chapter: Chapter,
        event: str,
        completed: bool
    ) -> Dict[str, Any]:
        """
        Manually toggle an event's completion status.
        Updates both chapter.plot_progress AND the latest batch to keep them in sync.
        """
        from ..models import ChapterPlotProgressBatch
        from sqlalchemy.orm.attributes import flag_modified
        
        # Get existing progress or initialize
        existing_progress = chapter.plot_progress or {}
        progress_data = {
            "completed_events": list(existing_progress.get("completed_events", [])),
            "scene_count": existing_progress.get("scene_count", 0),
            "climax_reached": existing_progress.get("climax_reached", False),
            "resolution_reached": existing_progress.get("resolution_reached", False),
            "last_updated": existing_progress.get("last_updated")
        }

        completed_events = set(progress_data.get("completed_events", []))

        if completed:
            completed_events.add(event)
        else:
            completed_events.discard(event)

        progress_data["completed_events"] = list(completed_events)
        progress_data["last_updated"] = datetime.utcnow().isoformat()

        # Update chapter.plot_progress
        chapter.plot_progress = progress_data
        flag_modified(chapter, "plot_progress")

        # ALSO update the latest batch to keep it in sync
        # This ensures the manual toggle persists even if new batches are created
        latest_batch = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter.id
        ).order_by(ChapterPlotProgressBatch.end_scene_sequence.desc()).first()

        if latest_batch:
            batch_events = set(latest_batch.completed_events or [])
            if completed:
                batch_events.add(event)
            else:
                batch_events.discard(event)
            latest_batch.completed_events = list(batch_events)
            flag_modified(latest_batch, "completed_events")

        self.db.commit()
        self.db.refresh(chapter)

        logger.info(f"[PLOT_PROGRESS:TOGGLE] Toggled event '{event[:50]}...' to {completed} for chapter {chapter.id}")

        return chapter.plot_progress

    def toggle_milestone_completion(
        self,
        chapter: Chapter,
        milestone: str,
        completed: bool
    ) -> Dict[str, Any]:
        """
        Manually toggle the completion status of a milestone (climax or resolution).

        Args:
            chapter: The chapter to update
            milestone: Either "climax" or "resolution"
            completed: Whether the milestone is completed

        Returns:
            Updated progress data
        """
        from sqlalchemy.orm.attributes import flag_modified

        if milestone not in ("climax", "resolution"):
            raise ValueError(f"Invalid milestone: {milestone}. Must be 'climax' or 'resolution'.")

        # Get existing progress or initialize
        existing_progress = chapter.plot_progress or {}
        progress_data = {
            "completed_events": list(existing_progress.get("completed_events", [])),
            "scene_count": existing_progress.get("scene_count", 0),
            "climax_reached": existing_progress.get("climax_reached", False),
            "resolution_reached": existing_progress.get("resolution_reached", False),
            "last_updated": existing_progress.get("last_updated")
        }

        # Update the milestone status
        if milestone == "climax":
            progress_data["climax_reached"] = completed
        else:  # resolution
            progress_data["resolution_reached"] = completed

        progress_data["last_updated"] = datetime.utcnow().isoformat()

        # Update chapter.plot_progress
        chapter.plot_progress = progress_data
        flag_modified(chapter, "plot_progress")

        self.db.commit()
        self.db.refresh(chapter)

        logger.info(f"[PLOT_PROGRESS:MILESTONE] Toggled {milestone}_reached to {completed} for chapter {chapter.id}")

        return chapter.plot_progress
    
    def generate_pacing_guidance(self, chapter: Chapter) -> str:
        """
        Generate adaptive pacing guidance based on chapter progress.
        
        Uses prompts from prompts.yml for all guidance text.
        
        The guidance becomes more directive as the chapter progresses:
        - 0% progress: Focus on atmosphere, setup, character grounding
        - < 50% progress: Subtle reminder of remaining events
        - 50-80% progress: Moderate suggestion to incorporate events
        - > 80% progress: Explicit directive to address remaining events
        
        Returns:
            Pacing guidance string for the LLM, or empty string if no guidance needed
        """
        if not chapter.chapter_plot:
            return ""
        
        progress = self.get_chapter_progress(chapter)
        
        if not progress["has_plot"]:
            return ""
        
        remaining_events = progress["remaining_events"]
        completed_count = len(progress["completed_events"])
        total_events = progress["total_events"]
        scene_count = progress["scene_count"]
        progress_pct = progress["progress_percentage"]
        climax = progress.get("climax", "")
        
        parts = []
        
        # Progress summary line (from prompts.yml)
        summary = prompt_manager.get_raw_prompt(
            "pacing.progress_summary",
            completed_count=completed_count,
            total_events=total_events,
            scene_count=scene_count
        )
        if summary:
            parts.append(summary)
        else:
            # Fallback if prompt not found
            parts.append(f"Chapter Progress: {completed_count}/{total_events} story beats completed, Scene {scene_count}")
        
        # If all events are covered, guide toward climax/resolution
        if not remaining_events:
            if not progress["climax_reached"] and climax:
                complete_guidance = prompt_manager.get_raw_prompt(
                    "pacing.progress_complete",
                    climax=climax
                )
                if complete_guidance:
                    parts.append(complete_guidance)
            return "\n".join(parts)
        
        # Format remaining events for substitution
        remaining_str = ", ".join(remaining_events[:3])
        if len(remaining_events) > 3:
            remaining_str += f" (+{len(remaining_events) - 3} more)"
        remaining_all = ", ".join(remaining_events)
        
        # At 0% progress (no events completed yet) - focus on setup
        if completed_count == 0:
            early_guidance = prompt_manager.get_raw_prompt("pacing.progress_early")
            if early_guidance:
                parts.append(early_guidance)
            else:
                parts.append("Focus on THIS SCENE: Establish atmosphere, ground the characters. No rush to hit plot points.")
            return "\n".join(parts)
        
        # Progress-based guidance
        if progress_pct < 50:
            # Low progress - subtle reminder
            low_guidance = prompt_manager.get_raw_prompt(
                "pacing.progress_low",
                remaining_events=remaining_str
            )
            if low_guidance:
                parts.append(low_guidance)
            else:
                parts.append(f"Story beats to weave in naturally: {remaining_str}")
        
        elif progress_pct < 80:
            # Mid progress - moderate suggestion
            mid_guidance = prompt_manager.get_raw_prompt(
                "pacing.progress_mid",
                remaining_events=remaining_all,
                climax=climax
            )
            if mid_guidance:
                parts.append(mid_guidance)
            else:
                parts.append(f"Story beats still ahead: {remaining_all}")
                if climax:
                    parts.append(f"Building toward: {climax}")
        
        else:
            # High progress - more directive
            high_guidance = prompt_manager.get_raw_prompt(
                "pacing.progress_high",
                remaining_events=remaining_all,
                climax=climax
            )
            if high_guidance:
                parts.append(high_guidance)
            else:
                parts.append(f"Final story beats to address: {remaining_all}")
                if climax:
                    parts.append(f"Building toward climax: {climax}")
        
        return "\n".join(parts)
    
    async def extract_completed_events(
        self,
        scene_content: str,
        key_events: List[str],
        llm_service,
        user_id: int,
        user_settings: Dict[str, Any]
    ) -> List[str]:
        """
        Use LLM to identify which key events occurred in the scene.
        Uses extraction LLM if configured, otherwise falls back to main LLM.
        
        Args:
            scene_content: The generated scene text
            key_events: List of planned key events to check for
            llm_service: The LLM service to use for extraction (fallback)
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            
        Returns:
            List of event descriptions that occurred in the scene
        """
        if not key_events:
            return []
        
        try:
            # Get prompts for event extraction
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "chapter_progress.event_extraction",
                "chapter_progress.event_extraction",
                scene_content=scene_content,
                key_events=json.dumps(key_events, indent=2)
            )
            
            # Check if extraction LLM is enabled
            extraction_enabled = user_settings.get('extraction_model_settings', {}).get('enabled', False)
            
            response = None
            
            if extraction_enabled:
                try:
                    from .llm.extraction_service import ExtractionLLMService
                    
                    logger.info(f"[PLOT_PROGRESS] Using extraction LLM for event extraction (user_id={user_id})")
                    
                    # Get extraction model settings
                    ext_settings = user_settings.get('extraction_model_settings', {})
                    llm_settings = user_settings.get('llm_settings', {})
                    timeout_total = llm_settings.get('timeout_total', 240)
                    extraction_service = ExtractionLLMService(
                        url=ext_settings.get('url', 'http://localhost:1234/v1'),
                        model=ext_settings.get('model_name', 'qwen2.5-3b-instruct'),
                        api_key=ext_settings.get('api_key', ''),
                        temperature=ext_settings.get('temperature', 0.3),
                        max_tokens=ext_settings.get('max_tokens', 500),
                        timeout_total=timeout_total
                    )
                    
                    # Generate with extraction model - use user's max_tokens setting
                    user_max_tokens = user_settings.get('llm_settings', {}).get('max_tokens', 2048)
                    response = await extraction_service.generate(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        max_tokens=user_max_tokens
                    )
                    
                    logger.info(f"[PLOT_PROGRESS] Successfully extracted events with extraction LLM")
                    
                except Exception as e:
                    logger.warning(f"[PLOT_PROGRESS] Extraction LLM failed, falling back to main LLM: {e}")
                    response = None  # Fall through to main LLM
            
            # Use main LLM if extraction LLM not enabled or failed
            if response is None:
                user_max_tokens = user_settings.get('llm_settings', {}).get('max_tokens', 2048)
                response = await llm_service.generate(
                    prompt=user_prompt,
                    user_id=user_id,
                    user_settings=user_settings,
                    system_prompt=system_prompt,
                    max_tokens=user_max_tokens,
                    temperature=0.3  # Low temperature for consistent extraction
                )
            
            # Parse response as JSON array
            logger.info(f"[PLOT_PROGRESS] Raw LLM response: {response[:500] if response else 'None'}...")
            cleaned = clean_llm_json(response)
            logger.info(f"[PLOT_PROGRESS] Cleaned JSON: {cleaned[:300] if cleaned else 'None'}...")
            completed = json.loads(cleaned)
            
            if not isinstance(completed, list):
                logger.warning(f"Event extraction returned non-list: {type(completed)}")
                return []
            
            # Validate that returned events are in the original list
            valid_events = [e for e in completed if e in key_events]
            
            logger.info(f"Extracted {len(valid_events)} completed events from scene")
            return valid_events
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse event extraction response: {e}")
            return []
        except Exception as e:
            logger.error(f"Error extracting completed events: {e}")
            return []
    
    async def extract_and_update_progress(
        self,
        chapter: Chapter,
        scene_content: str,
        llm_service,
        user_id: int,
        user_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract completed events from a scene and update chapter progress.
        
        Args:
            chapter: The chapter to update
            scene_content: The generated scene text
            llm_service: The LLM service to use for extraction
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            
        Returns:
            Updated progress data
        """
        if not chapter.chapter_plot:
            return {}
        
        # Refresh chapter to get latest plot_progress from database
        # This prevents reading stale data when processing multiple scenes in a loop
        self.db.refresh(chapter)
        
        key_events = chapter.chapter_plot.get("key_events", [])
        
        # Get already completed events
        progress = chapter.plot_progress or {}
        already_completed = set(progress.get("completed_events", []))
        
        # Only check for events that haven't been completed yet
        remaining_events = [e for e in key_events if e not in already_completed]
        
        if not remaining_events:
            # All events already completed, just update scene count
            return self.update_progress(chapter, [])
        
        # Extract newly completed events
        new_completed = await self.extract_completed_events(
            scene_content=scene_content,
            key_events=remaining_events,
            llm_service=llm_service,
            user_id=user_id,
            user_settings=user_settings
        )
        
        # Check if climax was reached
        climax = chapter.chapter_plot.get("climax", "")
        climax_reached = False
        if climax and climax.lower() in scene_content.lower():
            climax_reached = True
        
        # Update progress
        return self.update_progress(
            chapter=chapter,
            new_completed_events=new_completed,
            climax_reached=climax_reached
        )

