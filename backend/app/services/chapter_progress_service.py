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
                "scene_count": 0
            }
        
        key_events = chapter.chapter_plot.get("key_events", [])
        total_events = len(key_events)
        
        # Get progress from stored data or initialize
        progress_data = chapter.plot_progress or {
            "completed_events": [],
            "scene_count": 0,
            "climax_reached": False,
            "last_updated": None
        }
        
        completed_events = progress_data.get("completed_events", [])
        
        # Calculate remaining events
        remaining_events = [e for e in key_events if e not in completed_events]
        
        # Calculate progress percentage
        progress_percentage = (len(completed_events) / total_events * 100) if total_events > 0 else 0
        
        return {
            "has_plot": True,
            "completed_events": completed_events,
            "total_events": total_events,
            "progress_percentage": round(progress_percentage, 1),
            "remaining_events": remaining_events,
            "climax_reached": progress_data.get("climax_reached", False),
            "scene_count": progress_data.get("scene_count", 0),
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
        # Get existing progress or initialize
        progress_data = chapter.plot_progress or {
            "completed_events": [],
            "scene_count": 0,
            "climax_reached": False,
            "last_updated": None
        }
        
        # Merge new completed events (avoid duplicates)
        existing_completed = set(progress_data.get("completed_events", []))
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
        
        # Save to database
        chapter.plot_progress = progress_data
        self.db.commit()
        
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
        
        Args:
            chapter: The chapter to update
            event: The event description
            completed: Whether the event is completed
            
        Returns:
            Updated progress data
        """
        # Get existing progress or initialize
        progress_data = chapter.plot_progress or {
            "completed_events": [],
            "scene_count": 0,
            "climax_reached": False,
            "last_updated": None
        }
        
        completed_events = set(progress_data.get("completed_events", []))
        
        if completed:
            completed_events.add(event)
        else:
            completed_events.discard(event)
        
        progress_data["completed_events"] = list(completed_events)
        progress_data["last_updated"] = datetime.utcnow().isoformat()
        
        # Save to database
        chapter.plot_progress = progress_data
        self.db.commit()
        
        logger.info(f"Toggled event '{event[:50]}...' to {completed} for chapter {chapter.id}")
        
        return progress_data
    
    def generate_pacing_guidance(self, chapter: Chapter) -> str:
        """
        Generate adaptive pacing guidance based on chapter progress.
        
        The guidance becomes more directive as the chapter progresses:
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
        
        # If all events are covered, no guidance needed
        if not remaining_events:
            # But if climax not reached, guide toward it
            if not progress["climax_reached"] and progress.get("climax"):
                return f"All key events have occurred. Now move toward the climax: {progress['climax']}"
            return ""
        
        progress_pct = progress["progress_percentage"]
        climax = progress.get("climax", "")
        
        # Format remaining events as a concise list
        remaining_str = ", ".join(remaining_events[:3])  # Limit to first 3 for brevity
        if len(remaining_events) > 3:
            remaining_str += f" (+{len(remaining_events) - 3} more)"
        
        if progress_pct < 50:
            # Subtle - just remind of what's coming
            return f"Story beats to weave in naturally: {remaining_str}"
        
        elif progress_pct < 80:
            # Moderate - suggest incorporating soon
            guidance = f"The chapter is progressing well ({int(progress_pct)}% complete). "
            guidance += f"Consider incorporating these elements soon: {remaining_str}."
            if climax:
                guidance += f" Building toward: {climax}"
            return guidance
        
        else:
            # Directive - explicitly prompt
            guidance = f"IMPORTANT: The chapter is nearing its conclusion ({int(progress_pct)}% complete). "
            guidance += f"Now is the time to address: {remaining_str}."
            if climax:
                guidance += f" Move toward the climax: {climax}"
            return guidance
    
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
        
        Args:
            scene_content: The generated scene text
            key_events: List of planned key events to check for
            llm_service: The LLM service to use for extraction
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
            
            # Make LLM call
            response = await llm_service.generate(
                prompt=user_prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.3  # Low temperature for consistent extraction
            )
            
            # Parse response as JSON array
            cleaned = clean_llm_json(response)
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

