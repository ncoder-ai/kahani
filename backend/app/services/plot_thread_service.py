"""
Plot Thread Service

Handles extraction, storage, and retrieval of plot events and story threads
for maintaining narrative coherence across long stories.
"""

import logging
import re
import hashlib
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from .semantic_memory import get_semantic_memory_service
from .llm.service import UnifiedLLMService
from ..models import PlotEvent, Scene, EventType
from ..config import settings

logger = logging.getLogger(__name__)


class PlotThreadService:
    """
    Service for tracking and managing plot threads
    
    Features:
    - Automatic plot event extraction from scenes
    - Thread tracking and resolution detection
    - Semantic search for related events
    - Plot coherence analysis
    """
    
    def __init__(self):
        """Initialize plot thread service"""
        try:
            self.semantic_memory = get_semantic_memory_service()
        except RuntimeError:
            logger.warning("Semantic memory service not initialized")
            self.semantic_memory = None
        
        self.llm_service = UnifiedLLMService()
    
    async def extract_plot_events(
        self,
        scene_id: int,
        scene_content: str,
        story_id: int,
        sequence_number: int,
        chapter_id: Optional[int],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Session
    ) -> List[PlotEvent]:
        """
        Extract plot events from a scene using LLM
        
        Args:
            scene_id: Scene ID
            scene_content: Scene content text
            story_id: Story ID
            sequence_number: Scene sequence number
            chapter_id: Optional chapter ID
            user_id: User ID for LLM calls
            user_settings: User settings for LLM
            db: Database session
            
        Returns:
            List of created PlotEvent objects
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available, skipping event extraction")
            return []
        
        try:
            # Extract events using LLM
            events_data = await self._llm_extract_events(
                scene_content,
                story_id,
                user_id,
                user_settings,
                db
            )
            
            # Create PlotEvent entries
            created_events = []
            for event_data in events_data:
                event_type = event_data.get('event_type', 'complication')
                description = event_data.get('description', '')
                importance = event_data.get('importance', 50)
                confidence = event_data.get('confidence', 70)
                involved_chars = event_data.get('involved_characters', [])
                
                # Skip low-confidence or low-importance extractions
                if confidence < settings.extraction_confidence_threshold or importance < 30:
                    logger.info(f"Skipping low-confidence/importance event (conf: {confidence}, imp: {importance})")
                    continue
                
                # Generate thread ID based on event description
                thread_id = self._generate_thread_id(description, event_type)
                
                # Generate unique event ID
                event_id = f"{story_id}_{scene_id}_{thread_id}_{len(created_events)}"
                
                # Create embedding
                embedding_id = await self.semantic_memory.add_plot_event(
                    event_id=event_id,
                    story_id=story_id,
                    scene_id=scene_id,
                    event_type=event_type,
                    description=description,
                    metadata={
                        'sequence': sequence_number,
                        'is_resolved': False,
                        'involved_characters': involved_chars,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Create database record
                plot_event = PlotEvent(
                    story_id=story_id,
                    scene_id=scene_id,
                    event_type=EventType(event_type),
                    description=description,
                    embedding_id=embedding_id,
                    thread_id=thread_id,
                    is_resolved=False,
                    sequence_order=sequence_number,
                    chapter_id=chapter_id,
                    involved_characters=involved_chars,
                    extracted_automatically=True,
                    confidence_score=confidence,
                    importance_score=importance
                )
                
                db.add(plot_event)
                created_events.append(plot_event)
            
            db.commit()
            logger.info(f"Extracted {len(created_events)} plot events from scene {scene_id}")
            
            return created_events
            
        except Exception as e:
            logger.error(f"Failed to extract plot events: {e}", exc_info=True)
            db.rollback()
            return []
    
    async def _llm_extract_events(
        self,
        scene_content: str,
        story_id: int,
        user_id: int,
        user_settings: Dict[str, Any],
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to extract plot events from scene
        
        Args:
            scene_content: Scene text
            story_id: Story ID
            user_id: User ID
            user_settings: User settings
            db: Database session
            
        Returns:
            List of event dictionaries
        """
        try:
            # Get context about existing threads
            existing_threads = await self.get_unresolved_threads(story_id, db)
            thread_context = ""
            if existing_threads:
                thread_list = [f"- {t['description']}" for t in existing_threads[:5]]
                thread_context = f"\n\nActive plot threads to consider:\n{chr(10).join(thread_list)}"
            
            prompt = f"""Analyze the following scene and extract significant plot events.{thread_context}

Scene:
{scene_content}

For each significant plot event, identify:
1. Event type: "introduction" (new element), "complication" (conflict/challenge), "revelation" (discovery/twist), or "resolution" (solving a thread)
2. Description: Brief description of the event (1-2 sentences)
3. Importance (0-100): How significant is this event for the overall plot?
4. Confidence (0-100): How certain are you this is a significant plot event?
5. Involved characters: Names of characters involved (comma-separated, or "none")

Format your response as a list, one event per line:
EVENT_TYPE | DESCRIPTION | IMPORTANCE | CONFIDENCE | INVOLVED_CHARACTERS

Only include events that significantly advance or impact the plot. Skip minor actions or conversations.
"""
            
            system_prompt = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=500
            )
            
            # Parse response
            events = []
            lines = response.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or '|' not in line:
                    continue
                
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 5:
                    continue
                
                try:
                    event_type = parts[0].lower()
                    description = parts[1]
                    importance = int(re.sub(r'[^\d]', '', parts[2]) or '50')
                    confidence = int(re.sub(r'[^\d]', '', parts[3]) or '70')
                    involved_chars_str = parts[4].lower()
                    
                    # Validate event_type
                    if event_type not in ['introduction', 'complication', 'revelation', 'resolution']:
                        event_type = 'complication'
                    
                    # Parse involved characters
                    involved_chars = []
                    if involved_chars_str and involved_chars_str != 'none':
                        involved_chars = [c.strip() for c in involved_chars_str.split(',') if c.strip()]
                    
                    events.append({
                        'event_type': event_type,
                        'description': description,
                        'importance': min(max(importance, 0), 100),
                        'confidence': min(max(confidence, 0), 100),
                        'involved_characters': involved_chars
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse event line: {line} - {e}")
                    continue
            
            return events
            
        except Exception as e:
            logger.error(f"LLM event extraction failed: {e}")
            return []
    
    def _generate_thread_id(self, description: str, event_type: str) -> str:
        """
        Generate a thread ID based on event description
        
        Uses simple keyword matching to group related events
        """
        # Normalize description
        desc_lower = description.lower()
        
        # Extract key nouns/concepts (simple heuristic)
        # In production, could use NER or more sophisticated methods
        words = re.findall(r'\b[a-z]{4,}\b', desc_lower)
        
        # Use most significant words for thread ID
        if words:
            key_words = '_'.join(sorted(words[:3]))
            thread_hash = hashlib.md5(key_words.encode()).hexdigest()[:8]
            return f"{event_type}_{thread_hash}"
        else:
            # Fallback to hash of full description
            thread_hash = hashlib.md5(description.encode()).hexdigest()[:8]
            return f"{event_type}_{thread_hash}"
    
    async def get_unresolved_threads(
        self,
        story_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get all unresolved plot threads for a story
        
        Args:
            story_id: Story ID
            db: Database session
            
        Returns:
            List of unresolved plot events
        """
        try:
            events = db.query(PlotEvent).filter(
                PlotEvent.story_id == story_id,
                PlotEvent.is_resolved == False
            ).order_by(PlotEvent.sequence_order).all()
            
            threads = []
            for event in events:
                threads.append({
                    'id': event.id,
                    'thread_id': event.thread_id,
                    'event_type': event.event_type.value,
                    'description': event.description,
                    'scene_id': event.scene_id,
                    'sequence': event.sequence_order,
                    'importance': event.importance_score,
                    'involved_characters': event.involved_characters,
                    'created_at': event.created_at.isoformat() if event.created_at else None
                })
            
            return threads
            
        except Exception as e:
            logger.error(f"Failed to get unresolved threads: {e}")
            return []
    
    async def get_related_plot_events(
        self,
        query_text: str,
        story_id: int,
        top_k: int = 5,
        only_unresolved: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get semantically related plot events
        
        Args:
            query_text: Query text (current scene/situation)
            story_id: Story ID
            top_k: Number of results
            only_unresolved: Only return unresolved threads
            
        Returns:
            List of related plot events
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available")
            return []
        
        try:
            events = await self.semantic_memory.search_related_plot_events(
                query_text=query_text,
                story_id=story_id,
                top_k=top_k,
                only_unresolved=only_unresolved
            )
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to get related plot events: {e}")
            return []
    
    async def mark_thread_resolved(
        self,
        thread_id: str,
        story_id: int,
        resolution_scene_id: int,
        db: Session
    ) -> bool:
        """
        Mark a plot thread as resolved
        
        Args:
            thread_id: Thread ID
            story_id: Story ID
            resolution_scene_id: Scene where thread is resolved
            db: Database session
            
        Returns:
            True if successful
        """
        try:
            events = db.query(PlotEvent).filter(
                PlotEvent.story_id == story_id,
                PlotEvent.thread_id == thread_id,
                PlotEvent.is_resolved == False
            ).all()
            
            for event in events:
                event.is_resolved = True
                event.resolution_scene_id = resolution_scene_id
                event.resolved_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"Marked thread {thread_id} as resolved in scene {resolution_scene_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark thread resolved: {e}")
            db.rollback()
            return False
    
    async def get_plot_timeline(
        self,
        story_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get chronological plot timeline
        
        Args:
            story_id: Story ID
            db: Database session
            
        Returns:
            List of plot events in chronological order
        """
        try:
            events = db.query(PlotEvent).filter(
                PlotEvent.story_id == story_id
            ).order_by(PlotEvent.sequence_order).all()
            
            timeline = []
            for event in events:
                timeline.append({
                    'id': event.id,
                    'scene_id': event.scene_id,
                    'sequence': event.sequence_order,
                    'event_type': event.event_type.value,
                    'description': event.description,
                    'thread_id': event.thread_id,
                    'is_resolved': event.is_resolved,
                    'importance': event.importance_score,
                    'involved_characters': event.involved_characters,
                    'created_at': event.created_at.isoformat() if event.created_at else None,
                    'resolved_at': event.resolved_at.isoformat() if event.resolved_at else None
                })
            
            return timeline
            
        except Exception as e:
            logger.error(f"Failed to get plot timeline: {e}")
            return []
    
    def delete_plot_events(self, scene_id: int, db: Session):
        """
        Delete all plot events for a scene
        
        Args:
            scene_id: Scene ID
            db: Database session
        """
        try:
            events = db.query(PlotEvent).filter(
                PlotEvent.scene_id == scene_id
            ).all()
            
            # Delete from vector database (handled in semantic_memory service)
            if self.semantic_memory:
                for event in events:
                    try:
                        # Note: Implement delete in semantic_memory if needed
                        pass
                    except Exception as e:
                        logger.warning(f"Failed to delete embedding {event.embedding_id}: {e}")
            
            # Delete from database
            db.query(PlotEvent).filter(
                PlotEvent.scene_id == scene_id
            ).delete()
            
            db.commit()
            logger.info(f"Deleted plot events for scene {scene_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete plot events: {e}")
            db.rollback()


# Global service instance
_plot_thread_service: Optional[PlotThreadService] = None


def get_plot_thread_service() -> PlotThreadService:
    """Get the global plot thread service instance"""
    global _plot_thread_service
    if _plot_thread_service is None:
        _plot_thread_service = PlotThreadService()
    return _plot_thread_service

