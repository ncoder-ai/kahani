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
    """
    Clean common LLM JSON formatting issues and extract valid JSON.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Extra content after valid JSON
    - Whitespace and formatting issues
    """
    if not json_str:
        return json_str

    text = json_str.strip()

    # Step 1: Remove markdown code blocks
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]

    # Remove trailing ``` and everything after first ```
    if "```" in text:
        end_marker = text.find("```")
        if end_marker != -1:
            text = text[:end_marker]

    text = text.strip()

    # Step 2: Find first complete JSON using brace matching
    start_char = None
    end_char = None
    start_idx = -1

    for i, char in enumerate(text):
        if char == '{':
            start_char = '{'
            end_char = '}'
            start_idx = i
            break
        elif char == '[':
            start_char = '['
            end_char = ']'
            start_idx = i
            break

    if start_idx == -1:
        return text  # No JSON found, return as-is

    # Count braces/brackets to find matching end
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start_idx, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == '\\' and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == start_char:
            depth += 1
        elif char == end_char:
            depth -= 1
            if depth == 0:
                # Found complete JSON, return just this part
                return text[start_idx:i + 1]

    # If we get here, JSON wasn't complete - return what we have
    return text


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

    def get_all_chapter_events(self, chapter_plot: dict) -> list:
        """
        Combine key_events + climax + resolution into one ordered list.
        Brainstorm output stays unchanged, we just flatten at tracking time.
        """
        events = list(chapter_plot.get("key_events", []))
        if chapter_plot.get("climax"):
            events.append(chapter_plot["climax"])
        if chapter_plot.get("resolution"):
            events.append(chapter_plot["resolution"])
        return events

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
        
        # Use unified event list (key_events + climax + resolution)
        all_events = self.get_all_chapter_events(chapter.chapter_plot)
        total_events = len(all_events)

        # Get progress from stored data or initialize
        progress_data = chapter.plot_progress or {
            "completed_events": [],
            "scene_count": 0,
            "climax_reached": False,
            "resolution_reached": False,
            "last_updated": None
        }

        completed_events = progress_data.get("completed_events", [])

        # Calculate remaining events from unified list
        remaining_events = [e for e in all_events if e not in completed_events]

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
            "key_events": chapter.chapter_plot.get("key_events", []),
            "all_events": all_events  # Unified list for reference
        }
    
    def update_progress(
        self,
        chapter: Chapter,
        new_completed_events: List[str],
        scene_count: Optional[int] = None,
        climax_reached: bool = False,
        resolution_reached: bool = False
    ) -> Dict[str, Any]:
        """
        Update the progress for a chapter.

        Args:
            chapter: The chapter to update
            new_completed_events: List of newly completed event descriptions
            scene_count: Current scene count (optional, auto-calculated if not provided)
            climax_reached: Whether the climax has been reached
            resolution_reached: Whether the resolution has been reached

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

        # Update resolution status (once True, stays True)
        if resolution_reached or progress_data.get("resolution_reached", False):
            progress_data["resolution_reached"] = True

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
            # Union all events from all batches - handles overlapping batch ranges
            # Toggle function is responsible for removing events from ALL batches when toggled off
            all_events = set()
            for batch in batches:
                all_events.update(batch.completed_events or [])

            # Derive climax_reached and resolution_reached from completed events
            climax = chapter.chapter_plot.get("climax", "") if chapter.chapter_plot else ""
            resolution = chapter.chapter_plot.get("resolution", "") if chapter.chapter_plot else ""
            climax_reached = climax in all_events if climax else False
            resolution_reached = resolution in all_events if resolution else False

            chapter.plot_progress = {
                "completed_events": list(all_events),
                "scene_count": latest_batch.end_scene_sequence,
                "climax_reached": climax_reached,
                "resolution_reached": resolution_reached,
                "last_updated": datetime.utcnow().isoformat()
            }
            chapter.last_plot_extraction_scene_count = latest_batch.end_scene_sequence
        else:
            chapter.plot_progress = None
            chapter.last_plot_extraction_scene_count = 0
        
        flag_modified(chapter, "plot_progress")
        self.db.commit()

        logger.info(f"[PLOT_PROGRESS:RESTORE] Restored progress from batches for chapter {chapter_id}")

    def restore_from_last_valid_batch(
        self,
        chapter_id: int,
        min_deleted_seq: int
    ) -> None:
        """
        Restore plot progress from the last batch that ends BEFORE the deleted scenes.
        Used when scenes are deleted - we rollback to the last valid state.

        Args:
            chapter_id: The chapter ID
            min_deleted_seq: The minimum sequence number of deleted scenes
        """
        from ..models import ChapterPlotProgressBatch
        from sqlalchemy.orm.attributes import flag_modified

        chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return

        # Find the last batch that ends BEFORE the deleted scenes
        last_valid_batch = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter_id,
            ChapterPlotProgressBatch.end_scene_sequence < min_deleted_seq
        ).order_by(ChapterPlotProgressBatch.end_scene_sequence.desc()).first()

        if last_valid_batch:
            # Restore from this batch's state
            all_events = set(last_valid_batch.completed_events or [])

            climax = chapter.chapter_plot.get("climax", "") if chapter.chapter_plot else ""
            resolution = chapter.chapter_plot.get("resolution", "") if chapter.chapter_plot else ""
            climax_reached = climax in all_events if climax else False
            resolution_reached = resolution in all_events if resolution else False

            chapter.plot_progress = {
                "completed_events": list(all_events),
                "scene_count": last_valid_batch.end_scene_sequence,
                "climax_reached": climax_reached,
                "resolution_reached": resolution_reached,
                "last_updated": datetime.utcnow().isoformat()
            }
            chapter.last_plot_extraction_scene_count = last_valid_batch.end_scene_sequence
            logger.info(f"[PLOT_PROGRESS:ROLLBACK] Restored from batch ending at scene {last_valid_batch.end_scene_sequence} with {len(all_events)} events for chapter {chapter_id}")
        else:
            # No valid batch before deleted scenes - reset to empty
            chapter.plot_progress = None
            chapter.last_plot_extraction_scene_count = 0
            logger.info(f"[PLOT_PROGRESS:ROLLBACK] No valid batch found before scene {min_deleted_seq}, reset to empty for chapter {chapter_id}")

        flag_modified(chapter, "plot_progress")
        self.db.commit()

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
        Create or update a plot progress batch with cumulative events.
        Uses upsert logic to avoid duplicate batches for the same scene range.
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

        # NOTE: We intentionally do NOT preserve chapter.plot_progress events here.
        # Manual toggles update batches directly via toggle_event_completion_with_batch(),
        # so preservation would be redundant and could propagate bad extraction data.
        # ChapterPlotProgressBatch is the single source of truth.

        # Check if batch already exists for this scene range (upsert logic)
        existing_batch = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter.id,
            ChapterPlotProgressBatch.start_scene_sequence == start_sequence,
            ChapterPlotProgressBatch.end_scene_sequence == end_sequence
        ).first()

        if existing_batch:
            # Update existing batch
            existing_batch.completed_events = list(all_events)
            flag_modified(existing_batch, "completed_events")
            self.db.flush()
            logger.info(f"[PLOT_PROGRESS:BATCH] Updated existing batch for chapter {chapter.id} scenes {start_sequence}-{end_sequence} with {len(all_events)} cumulative events")
        else:
            # Create new batch
            batch = ChapterPlotProgressBatch(
                chapter_id=chapter.id,
                start_scene_sequence=start_sequence,
                end_scene_sequence=end_sequence,
                completed_events=list(all_events)
            )
            self.db.add(batch)
            self.db.flush()
            logger.info(f"[PLOT_PROGRESS:BATCH] Created batch for chapter {chapter.id} scenes {start_sequence}-{end_sequence} with {len(all_events)} cumulative events")

        # Update chapter's plot_progress from batches
        self.update_plot_progress_from_batches(chapter.id)
    
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

        # Refresh to get latest committed data
        self.db.refresh(chapter)

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

        # Update batches to keep them in sync with manual toggles
        all_batches = self.db.query(ChapterPlotProgressBatch).filter(
            ChapterPlotProgressBatch.chapter_id == chapter.id
        ).all()

        if completed:
            # When toggling ON: add to the latest batch only (will be inherited by future batches)
            latest_batch = max(all_batches, key=lambda b: b.end_scene_sequence) if all_batches else None
            if latest_batch:
                batch_events = set(latest_batch.completed_events or [])
                batch_events.add(event)
                latest_batch.completed_events = list(batch_events)
                flag_modified(latest_batch, "completed_events")
        else:
            # When toggling OFF: remove from ALL batches (since union is used for display)
            for batch in all_batches:
                batch_events = set(batch.completed_events or [])
                if event in batch_events:
                    batch_events.discard(event)
                    batch.completed_events = list(batch_events)
                    flag_modified(batch, "completed_events")

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
        from ..models import ChapterPlotProgressBatch
        from sqlalchemy.orm.attributes import flag_modified

        if milestone not in ("climax", "resolution"):
            raise ValueError(f"Invalid milestone: {milestone}. Must be 'climax' or 'resolution'.")

        # Get the actual event text for this milestone
        milestone_event = None
        if chapter.chapter_plot:
            milestone_event = chapter.chapter_plot.get(milestone)

        # Get existing progress or initialize
        existing_progress = chapter.plot_progress or {}
        progress_data = {
            "completed_events": list(existing_progress.get("completed_events", [])),
            "scene_count": existing_progress.get("scene_count", 0),
            "climax_reached": existing_progress.get("climax_reached", False),
            "resolution_reached": existing_progress.get("resolution_reached", False),
            "last_updated": existing_progress.get("last_updated")
        }

        # Update the milestone flag
        if milestone == "climax":
            progress_data["climax_reached"] = completed
        else:  # resolution
            progress_data["resolution_reached"] = completed

        # Also update completed_events and batches for the actual event
        if milestone_event:
            completed_events = set(progress_data.get("completed_events", []))

            if completed:
                completed_events.add(milestone_event)
            else:
                completed_events.discard(milestone_event)

            progress_data["completed_events"] = list(completed_events)

            # Update batches to keep them in sync (same logic as toggle_event_completion_with_batch)
            all_batches = self.db.query(ChapterPlotProgressBatch).filter(
                ChapterPlotProgressBatch.chapter_id == chapter.id
            ).all()

            if completed:
                # When toggling ON: add to the latest batch only
                latest_batch = max(all_batches, key=lambda b: b.end_scene_sequence) if all_batches else None
                if latest_batch:
                    batch_events = set(latest_batch.completed_events or [])
                    batch_events.add(milestone_event)
                    latest_batch.completed_events = list(batch_events)
                    flag_modified(latest_batch, "completed_events")
            else:
                # When toggling OFF: remove from ALL batches
                for batch in all_batches:
                    batch_events = set(batch.completed_events or [])
                    if milestone_event in batch_events:
                        batch_events.discard(milestone_event)
                        batch.completed_events = list(batch_events)
                        flag_modified(batch, "completed_events")

        progress_data["last_updated"] = datetime.utcnow().isoformat()

        # Update chapter.plot_progress
        chapter.plot_progress = progress_data
        flag_modified(chapter, "plot_progress")

        self.db.commit()
        self.db.refresh(chapter)

        logger.info(f"[PLOT_PROGRESS:MILESTONE] Toggled {milestone}_reached to {completed} for chapter {chapter.id}")

        return chapter.plot_progress
    
    def generate_pacing_guidance(self, chapter: Chapter, plot_check_mode: str = "all") -> str:
        """
        Generate adaptive pacing guidance based on chapter progress.

        Uses prompts from prompts.yml for all guidance text.

        The guidance becomes more directive as the chapter progresses:
        - 0% progress: Focus on atmosphere, setup, character grounding
        - < 50% progress: Subtle reminder of remaining events
        - 50-80% progress: Moderate suggestion to incorporate events
        - > 80% progress: Explicit directive to address remaining events

        When plot_check_mode is "1" (strict), explicitly highlights the next beat to focus on.

        Args:
            chapter: The chapter to generate guidance for
            plot_check_mode: "1" for strict (next beat only), "3" for flexible, "all" for full

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
        
        # Format remaining events based on plot_check_mode
        # Mode "1": only show the next beat
        # Mode "3": only show next 3 beats
        # Mode "all": show all remaining beats
        if plot_check_mode == "1":
            events_to_show = remaining_events[:1]
        elif plot_check_mode == "3":
            events_to_show = remaining_events[:3]
        else:
            events_to_show = remaining_events

        remaining_str = ", ".join(events_to_show)
        remaining_all = ", ".join(events_to_show)  # Same as remaining_str when mode limits beats

        # When in strict mode ("1"), explicitly highlight the next beat to work towards
        # Skip progress-based guidance since we're already showing the explicit beat
        if plot_check_mode == "1" and remaining_events:
            next_beat = remaining_events[0]
            strict_guidance = prompt_manager.get_raw_prompt(
                "pacing.strict_next_beat",
                next_beat=next_beat
            )
            if strict_guidance:
                parts.append(strict_guidance)
            else:
                parts.append(f">>> NEXT BEAT TO WORK TOWARDS: {next_beat}")
                parts.append("Focus on setting up or completing this specific story beat in this scene.")
            # Return here to avoid duplicate beat listing in progress guidance
            return "\n".join(parts)

        # When in flexible mode ("3"), highlight the next few beats to focus on
        # Skip progress-based guidance since we're already showing the explicit beats
        if plot_check_mode == "3" and remaining_events:
            next_beats = remaining_events[:3]
            flexible_guidance = prompt_manager.get_raw_prompt(
                "pacing.flexible_next_beats",
                next_beats=", ".join(next_beats),
                count=len(next_beats)
            )
            if flexible_guidance:
                parts.append(flexible_guidance)
            else:
                parts.append(f">>> NEXT BEATS TO WORK TOWARDS: {', '.join(next_beats)}")
                parts.append("Focus on these upcoming story beats - progress through them naturally.")
            # Return here to avoid duplicate beat listing in progress guidance
            return "\n".join(parts)

        # At 0% progress (no events completed yet) - focus on setup
        if completed_count == 0:
            early_guidance = prompt_manager.get_raw_prompt("pacing.progress_early")
            if early_guidance:
                parts.append(early_guidance)
            else:
                parts.append("Focus on THIS SCENE: Establish atmosphere, ground the characters. No rush to hit plot points.")
            return "\n".join(parts)

        # Progress-based guidance (only for "all" mode - strict/flexible modes return above)
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
        user_settings: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> List[str]:
        """
        Use LLM to identify which key events occurred in the scene.
        Always uses cache-friendly multi-message structure matching scene generation.

        Args:
            scene_content: The generated scene text
            key_events: List of planned key events to check for
            llm_service: The LLM service to use
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            context: Context dict from scene generation (built if not provided)
            db: Database session for context building and preset lookups

        Returns:
            List of event descriptions that occurred in the scene
        """
        if not key_events:
            return []

        try:
            # Build context if not provided
            if context is None and db is not None:
                try:
                    from .context_manager import ContextManager
                    context_manager = ContextManager(user_id, user_settings)
                    # Get story_id from the chapter
                    story_id = self.db.query(Chapter).filter(Chapter.id == self.db.query(Scene).first().chapter_id).first().story_id if self.db else None
                    if story_id:
                        context = await context_manager.build_scene_generation_context(
                            story_id=story_id,
                            db=db
                        )
                        logger.info(f"[PLOT_PROGRESS] Built context for cache-friendly extraction")
                except Exception as ctx_err:
                    logger.warning(f"[PLOT_PROGRESS] Failed to build context: {ctx_err}")
                    context = {}

            # Always use cache-friendly extraction
            return await llm_service.extract_plot_events_with_context(
                scene_content=scene_content,
                key_events=key_events,
                context=context or {},
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )

        except Exception as e:
            logger.error(f"Error extracting completed events: {e}")
            return []
    
    async def extract_and_update_progress(
        self,
        chapter: Chapter,
        scene_content: str,
        llm_service,
        user_id: int,
        user_settings: Dict[str, Any],
        plot_check_mode: str = "1"
    ) -> Dict[str, Any]:
        """
        Extract completed events from a scene and update chapter progress.

        Args:
            chapter: The chapter to update
            scene_content: The generated scene text
            llm_service: The LLM service to use for extraction
            user_id: User ID for LLM call
            user_settings: User settings for LLM call
            plot_check_mode: How many events to check - "1" (strict), "3", or "all"

        Returns:
            Updated progress data
        """
        if not chapter.chapter_plot:
            return {}

        # Refresh chapter to get latest plot_progress from database
        # This prevents reading stale data when processing multiple scenes in a loop
        self.db.refresh(chapter)

        # Get ALL events as unified list (key_events + climax + resolution)
        all_events = self.get_all_chapter_events(chapter.chapter_plot)

        # Get already completed events
        progress = chapter.plot_progress or {}
        already_completed = set(progress.get("completed_events", []))

        # Only check for events that haven't been completed yet
        remaining_events = [e for e in all_events if e not in already_completed]

        if not remaining_events:
            # All events already completed, just update scene count
            return self.update_progress(chapter, [])

        # Apply plot_check_mode filter
        if plot_check_mode == "1":
            events_to_check = remaining_events[:1]
        elif plot_check_mode == "3":
            events_to_check = remaining_events[:3]
        else:  # "all"
            events_to_check = remaining_events

        # Extract newly completed events via LLM
        new_completed = await self.extract_completed_events(
            scene_content=scene_content,
            key_events=events_to_check,
            llm_service=llm_service,
            user_id=user_id,
            user_settings=user_settings
        )

        # Derive climax_reached and resolution_reached from completed events
        climax = chapter.chapter_plot.get("climax", "")
        resolution = chapter.chapter_plot.get("resolution", "")

        all_completed = already_completed.union(new_completed)
        climax_reached = climax in all_completed if climax else False
        resolution_reached = resolution in all_completed if resolution else False

        # Update progress
        return self.update_progress(
            chapter=chapter,
            new_completed_events=new_completed,
            climax_reached=climax_reached,
            resolution_reached=resolution_reached
        )

