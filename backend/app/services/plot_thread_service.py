"""
Plot Thread Service

Handles extraction, storage, and retrieval of plot events and story threads
for maintaining narrative coherence across long stories.
"""

import logging
import re
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime

from .semantic_memory import get_semantic_memory_service
from .llm.service import UnifiedLLMService
from ..models import PlotEvent, Scene, EventType
from ..config import settings

logger = logging.getLogger(__name__)


def clean_llm_json(json_str: str) -> str:
    """
    Clean common JSON errors from LLM responses.
    """
    # Fix unquoted values in key-value pairs
    json_str = re.sub(
        r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,}\]])',
        r': "\1"\2',
        json_str
    )
    
    # Remove trailing commas before closing brackets
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Remove comments
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    return json_str


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
    
    async def extract_plot_events_from_scenes_batch(
        self,
        scenes: List[Tuple[int, int, Optional[int], str]],  # List of (scene_id, sequence_number, chapter_id, scene_content)
        story_id: int,
        user_id: int,
        user_settings: Dict[str, Any],
        db: Session
    ) -> Dict[int, List[PlotEvent]]:
        """
        Batch extract plot events from multiple scenes in a single LLM call.
        
        Args:
            scenes: List of (scene_id, sequence_number, chapter_id, scene_content) tuples
            story_id: Story ID
            user_id: User ID for LLM calls
            user_settings: User settings for LLM
            db: Database session
            
        Returns:
            Dictionary mapping scene_id to list of created PlotEvent objects
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available, skipping batch event extraction")
            return {}
        
        if not scenes:
            return {}
        
        try:
            # Check if plot events already exist for any scene (avoid duplicates)
            scene_ids = [scene_id for scene_id, _, _, _ in scenes]
            existing_events = db.query(PlotEvent).filter(
                PlotEvent.scene_id.in_(scene_ids)
            ).all()
            
            if existing_events:
                existing_scene_ids = set(e.scene_id for e in existing_events)
                logger.info(f"Plot events already exist for {len(existing_scene_ids)} scenes, skipping extraction to avoid duplicates")
                # Return existing events grouped by scene_id
                scene_event_map = {}
                for event in existing_events:
                    if event.scene_id not in scene_event_map:
                        scene_event_map[event.scene_id] = []
                    scene_event_map[event.scene_id].append(event)
                return scene_event_map
            
            # Concatenate scenes with clear markers
            scenes_text = []
            for scene_id, sequence_number, chapter_id, scene_content in scenes:
                scenes_text.append(f"=== SCENE {sequence_number} (ID: {scene_id}) ===\n{scene_content}\n")
            
            batch_content = "\n".join(scenes_text)
            
            # Get context about existing threads
            existing_threads = await self.get_unresolved_threads(story_id, db)
            thread_context = ""
            if existing_threads:
                thread_list = [f"- {t['description']}" for t in existing_threads[:5]]
                thread_context = f"\n\nActive plot threads to consider:\n{chr(10).join(thread_list)}"
            
            # Extract events from all scenes at once
            events_data = await self._llm_extract_events_batch(
                batch_content,
                story_id,
                user_id,
                user_settings,
                db
            )
            
            if not events_data:
                logger.warning(f"No plot events extracted from batch of {len(scenes)} scenes")
                return {}
            
            # Post-process: Map events to scenes using text verification
            from ..utils.scene_verification import map_events_to_scenes
            scenes_for_verification = [(scene_id, scene_content) for scene_id, _, _, scene_content in scenes]
            scene_event_map = map_events_to_scenes(events_data, scenes_for_verification)
            
            # Create PlotEvent entries for each scene
            all_created_events = {}
            
            for scene_id, sequence_number, chapter_id, scene_content in scenes:
                events_for_scene = scene_event_map.get(scene_id, [])
                created_events = []
                
                for event_data in events_for_scene:
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
                    
                    # Check if embedding_id already exists
                    potential_embedding_id = f"plot_{event_id}"
                    existing_embedding = db.query(PlotEvent).filter(
                        PlotEvent.embedding_id == potential_embedding_id
                    ).first()
                    
                    if existing_embedding:
                        logger.debug(f"Plot event with embedding_id {potential_embedding_id} already exists, skipping")
                        continue
                    
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
                    
                    # Double-check embedding_id doesn't exist (race condition protection)
                    final_check = db.query(PlotEvent).filter(
                        PlotEvent.embedding_id == embedding_id
                    ).first()
                    
                    if final_check:
                        logger.debug(f"Plot event with embedding_id {embedding_id} was created concurrently, skipping")
                        continue
                    
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
                
                if created_events:
                    all_created_events[scene_id] = created_events
            
            try:
                db.commit()
                total_events = sum(len(events) for events in all_created_events.values())
                logger.info(f"Batch extracted {total_events} plot events from {len(scenes)} scenes")
            except Exception as commit_error:
                from sqlalchemy.exc import IntegrityError
                if isinstance(commit_error, IntegrityError) or "UNIQUE constraint failed: plot_events.embedding_id" in str(commit_error):
                    logger.warning(f"Duplicate plot event detected during batch commit, rolling back")
                    db.rollback()
                    # Return empty - will be handled by per-scene fallback
                    return {}
                else:
                    raise
            
            return all_created_events
            
        except Exception as e:
            from sqlalchemy.exc import IntegrityError
            if isinstance(e, IntegrityError) or "UNIQUE constraint failed: plot_events.embedding_id" in str(e):
                logger.warning(f"Duplicate plot event detected in batch extraction, returning empty")
                db.rollback()
                return {}
            else:
                logger.error(f"Failed to batch extract plot events: {e}", exc_info=True)
                db.rollback()
                return {}
    
    async def _llm_extract_events_batch(
        self,
        batch_content: str,
        story_id: int,
        user_id: int,
        user_settings: Dict[str, Any],
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to extract plot events from multiple scenes in batch.
        
        Returns list of event dictionaries (not mapped to scenes).
        """
        try:
            # Get context about existing threads
            existing_threads = await self.get_unresolved_threads(story_id, db)
            thread_context = ""
            if existing_threads:
                thread_list = [f"- {t['description']}" for t in existing_threads[:5]]
                thread_context = f"\n\nActive plot threads to consider:\n{chr(10).join(thread_list)}"
            
            prompt = f"""Analyze the following scenes and extract significant plot events.{thread_context}

{batch_content}

For each significant plot event, identify:
1. Event type: "introduction" (new element), "complication" (conflict/challenge), "revelation" (discovery/twist), or "resolution" (solving a thread)
2. Description: Brief description of the event (1-2 sentences)
3. Importance (0-100): How significant is this event for the overall plot?
4. Confidence (0-100): How certain are you this is a significant plot event?
5. Involved characters: Names of characters involved (array of strings, or empty array)

Return ONLY valid JSON in this exact format:
{{
  "events": [
    {{
      "event_type": "complication",
      "description": "Description of the event",
      "importance": 85,
      "confidence": 95,
      "involved_characters": ["Character1", "Character2"]
    }}
  ]
}}

If no events found, return {{"events": []}}. Return ONLY the JSON, no other text."""
            
            system_prompt = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=1500  # More tokens for batch
            )
            
            logger.warning(f"RAW LLM RESPONSE - PLOT EVENTS BATCH:\n{response}")
            
            # Parse JSON response
            events = []
            try:
                # Clean response (remove markdown code blocks if present)
                response_clean = response.strip()
                if response_clean.startswith("```json"):
                    response_clean = response_clean[7:]
                if response_clean.startswith("```"):
                    response_clean = response_clean[3:]
                if response_clean.endswith("```"):
                    response_clean = response_clean[:-3]
                response_clean = response_clean.strip()
                
                # Clean common JSON errors from LLM
                response_clean = clean_llm_json(response_clean)
                
                # Parse JSON
                data = json.loads(response_clean)
                
                # Extract events array
                events_list = data.get('events', [])
                
                # Validate and normalize events
                for event in events_list:
                    try:
                        event_type = event.get('event_type', 'complication').strip().lower()
                        description = event.get('description', '').strip()
                        importance = event.get('importance', 50)
                        confidence = event.get('confidence', 70)
                        involved_chars = event.get('involved_characters', [])
                        
                        # Validate event_type
                        if event_type not in ['introduction', 'complication', 'revelation', 'resolution']:
                            logger.warning(f"Invalid event_type '{event_type}', defaulting to 'complication'")
                            event_type = 'complication'
                        
                        # Validate importance and confidence
                        try:
                            importance = int(importance)
                            importance = min(max(importance, 0), 100)
                        except (ValueError, TypeError):
                            importance = 50
                        
                        try:
                            confidence = int(confidence)
                            confidence = min(max(confidence, 0), 100)
                        except (ValueError, TypeError):
                            confidence = 70
                        
                        # Normalize involved_characters (handle string or array)
                        if isinstance(involved_chars, str):
                            if involved_chars.lower() == 'none' or not involved_chars.strip():
                                involved_chars = []
                            else:
                                involved_chars = [c.strip() for c in involved_chars.split(',') if c.strip()]
                        elif not isinstance(involved_chars, list):
                            involved_chars = []
                        else:
                            involved_chars = [str(c).strip() for c in involved_chars if c and str(c).strip()]
                        
                        if description:
                            events.append({
                                'event_type': event_type,
                                'description': description,
                                'importance': importance,
                                'confidence': confidence,
                                'involved_characters': involved_chars
                            })
                        else:
                            logger.warning(f"Skipping event with missing description: {event}")
                            
                    except Exception as e:
                        logger.warning(f"Failed to validate event: {event}, error: {e}")
                        continue
                        
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.debug(f"Original response was: {response}")
                logger.debug(f"Cleaned response was: {response_clean}")
                return []
            except Exception as e:
                logger.error(f"Failed to parse events response: {e}")
                return []
            
            logger.warning(f"PARSING RESULT: Extracted {len(events)} plot events from JSON")
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to extract plot events with LLM (batch): {e}")
            return []
    
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
            # Check if plot events already exist for this scene (avoid duplicates in batch processing)
            existing_events = db.query(PlotEvent).filter(
                PlotEvent.scene_id == scene_id
            ).all()
            
            if existing_events:
                logger.info(f"Plot events already exist for scene {scene_id}, skipping extraction to avoid duplicates")
                return existing_events
            
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
                
                # Check if embedding_id already exists (additional safety check)
                potential_embedding_id = f"plot_{event_id}"
                existing_embedding = db.query(PlotEvent).filter(
                    PlotEvent.embedding_id == potential_embedding_id
                ).first()
                
                if existing_embedding:
                    logger.debug(f"Plot event with embedding_id {potential_embedding_id} already exists, skipping")
                    continue
                
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
                
                # Double-check embedding_id doesn't exist (race condition protection)
                final_check = db.query(PlotEvent).filter(
                    PlotEvent.embedding_id == embedding_id
                ).first()
                
                if final_check:
                    logger.debug(f"Plot event with embedding_id {embedding_id} was created concurrently, skipping")
                    continue
                
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
            
            try:
                db.commit()
                logger.info(f"Extracted {len(created_events)} plot events from scene {scene_id}")
            except Exception as commit_error:
                # Handle race condition where embedding_id was inserted concurrently
                from sqlalchemy.exc import IntegrityError
                if isinstance(commit_error, IntegrityError) or "UNIQUE constraint failed: plot_events.embedding_id" in str(commit_error):
                    logger.warning(f"Duplicate plot event detected during commit for scene {scene_id}, rolling back and returning existing events")
                    db.rollback()
                    # Return existing events instead
                    existing_events = db.query(PlotEvent).filter(
                        PlotEvent.scene_id == scene_id
                    ).all()
                    return existing_events
                else:
                    raise
            
            return created_events
            
        except Exception as e:
            # Check if it's a duplicate key error
            from sqlalchemy.exc import IntegrityError
            if isinstance(e, IntegrityError) or "UNIQUE constraint failed: plot_events.embedding_id" in str(e):
                logger.warning(f"Duplicate plot event detected for scene {scene_id}, returning existing events")
                db.rollback()
                # Return existing events instead
                try:
                    existing_events = db.query(PlotEvent).filter(
                        PlotEvent.scene_id == scene_id
                    ).all()
                    return existing_events
                except Exception as query_error:
                    logger.error(f"Failed to query existing events: {query_error}")
                    return []
            else:
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
5. Involved characters: Names of characters involved (array of strings, or empty array)

Return ONLY valid JSON in this exact format:
{{
  "events": [
    {{
      "event_type": "complication",
      "description": "Description of the event",
      "importance": 85,
      "confidence": 95,
      "involved_characters": ["Character1", "Character2"]
    }}
  ]
}}

If no events found, return {{"events": []}}. Return ONLY the JSON, no other text."""
            
            system_prompt = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=500
            )
            
            logger.warning(f"RAW LLM RESPONSE - PLOT EVENTS:\n{response}")
            
            # Parse JSON response
            events = []
            try:
                # Clean response (remove markdown code blocks if present)
                response_clean = response.strip()
                if response_clean.startswith("```json"):
                    response_clean = response_clean[7:]
                if response_clean.startswith("```"):
                    response_clean = response_clean[3:]
                if response_clean.endswith("```"):
                    response_clean = response_clean[:-3]
                response_clean = response_clean.strip()
                
                # Clean common JSON errors from LLM
                response_clean = clean_llm_json(response_clean)
                
                # Parse JSON
                data = json.loads(response_clean)
                
                # Extract events array
                events_list = data.get('events', [])
                
                # Validate and normalize events
                for event in events_list:
                    try:
                        event_type = event.get('event_type', 'complication').strip().lower()
                        description = event.get('description', '').strip()
                        importance = event.get('importance', 50)
                        confidence = event.get('confidence', 70)
                        involved_chars = event.get('involved_characters', [])
                        
                        # Validate event_type
                        if event_type not in ['introduction', 'complication', 'revelation', 'resolution']:
                            logger.warning(f"Invalid event_type '{event_type}', defaulting to 'complication'")
                            event_type = 'complication'
                        
                        # Validate importance and confidence
                        try:
                            importance = int(importance)
                            importance = min(max(importance, 0), 100)
                        except (ValueError, TypeError):
                            importance = 50
                        
                        try:
                            confidence = int(confidence)
                            confidence = min(max(confidence, 0), 100)
                        except (ValueError, TypeError):
                            confidence = 70
                        
                        # Normalize involved_characters (handle string or array)
                        if isinstance(involved_chars, str):
                            if involved_chars.lower() == 'none' or not involved_chars.strip():
                                involved_chars = []
                            else:
                                involved_chars = [c.strip() for c in involved_chars.split(',') if c.strip()]
                        elif not isinstance(involved_chars, list):
                            involved_chars = []
                        else:
                            involved_chars = [str(c).strip() for c in involved_chars if c and str(c).strip()]
                        
                        if description:
                            events.append({
                                'event_type': event_type,
                                'description': description,
                                'importance': importance,
                                'confidence': confidence,
                                'involved_characters': involved_chars
                            })
                        else:
                            logger.warning(f"Skipping event with missing description: {event}")
                            
                    except Exception as e:
                        logger.warning(f"Failed to validate event: {event}, error: {e}")
                        continue
                        
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.debug(f"Original response was: {response}")
                logger.debug(f"Cleaned response was: {response_clean}")
                return []
            except Exception as e:
                logger.error(f"Failed to parse events response: {e}")
                return []
            
            logger.warning(f"PARSING RESULT: Extracted {len(events)} plot events from JSON")
            
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
            
            # Delete from vector database (ChromaDB)
            if self.semantic_memory:
                for event in events:
                    try:
                        # Delete embedding from ChromaDB using embedding_id
                        self.semantic_memory.plot_events_collection.delete(
                            ids=[event.embedding_id]
                        )
                        logger.debug(f"Deleted plot event embedding {event.embedding_id} from ChromaDB")
                    except Exception as e:
                        logger.warning(f"Failed to delete embedding {event.embedding_id}: {e}")
            
            # Delete from database
            db.query(PlotEvent).filter(
                PlotEvent.scene_id == scene_id
            ).delete()
            
            db.commit()
            logger.info(f"Deleted {len(events)} plot events for scene {scene_id}")
            
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

