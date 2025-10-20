"""
Entity State Service

Tracks and updates the state of characters, locations, and objects throughout a story.
Uses LLM to extract state changes from scenes and maintains authoritative truth.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..models import (
    Character, CharacterState, LocationState, ObjectState,
    Story, Scene, StoryCharacter
)
from ..services.llm.service import UnifiedLLMService

logger = logging.getLogger(__name__)


class EntityStateService:
    """
    Service for managing entity states (characters, locations, objects).
    
    Responsibilities:
    - Extract state changes from scenes using LLM
    - Update entity state database records
    - Provide current state for context assembly
    - Track relationships, possessions, locations
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any]):
        self.user_id = user_id
        self.user_settings = user_settings
        self.llm_service = UnifiedLLMService()
    
    async def extract_and_update_states(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        scene_content: str
    ) -> Dict[str, Any]:
        """
        Extract state changes from a scene and update all entity states.
        
        Args:
            db: Database session
            story_id: Story ID
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            scene_content: Scene content text
            
        Returns:
            Dictionary with extraction results
        """
        results = {
            "characters_updated": 0,
            "locations_updated": 0,
            "objects_updated": 0,
            "extraction_successful": False
        }
        
        try:
            # Get story characters for context
            story_characters = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id
            ).all()
            
            character_names = [
                db.query(Character).filter(Character.id == sc.character_id).first().name
                for sc in story_characters
            ]
            
            # Extract state changes using LLM
            state_changes = await self._extract_state_changes(
                scene_content,
                scene_sequence,
                character_names
            )
            
            if not state_changes:
                logger.warning(f"No state changes extracted from scene {scene_id}")
                return results
            
            # Update character states
            if "characters" in state_changes:
                for char_update in state_changes["characters"]:
                    await self._update_character_state(
                        db, story_id, scene_sequence, char_update
                    )
                    results["characters_updated"] += 1
            
            # Update location states
            if "locations" in state_changes:
                for loc_update in state_changes["locations"]:
                    await self._update_location_state(
                        db, story_id, scene_sequence, loc_update
                    )
                    results["locations_updated"] += 1
            
            # Update object states
            if "objects" in state_changes:
                for obj_update in state_changes["objects"]:
                    await self._update_object_state(
                        db, story_id, scene_sequence, obj_update
                    )
                    results["objects_updated"] += 1
            
            results["extraction_successful"] = True
            logger.info(f"Updated entity states for scene {scene_id}: {results}")
            
        except Exception as e:
            logger.error(f"Failed to extract and update entity states: {e}")
        
        return results
    
    async def _extract_state_changes(
        self,
        scene_content: str,
        scene_sequence: int,
        character_names: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract state changes from a scene.
        
        Returns JSON with character, location, and object updates.
        """
        try:
            prompt = f"""Analyze this story scene and extract entity state changes.

Scene (Sequence #{scene_sequence}):
{scene_content}

Known Characters: {', '.join(character_names)}

Extract the following as JSON:
1. Character state changes (location, emotional state, possessions, knowledge, relationships)
2. Location information (name, condition, atmosphere, occupants)
3. Important objects (name, location, owner, condition)

Return ONLY valid JSON in this exact format:
{{
  "characters": [
    {{
      "name": "character name",
      "location": "current location or null",
      "emotional_state": "brief emotional state or null",
      "physical_condition": "condition or null",
      "possessions_gained": ["item1", "item2"],
      "possessions_lost": ["item3"],
      "knowledge_gained": ["fact1", "fact2"],
      "relationship_changes": {{"other_char": "relationship description"}}
    }}
  ],
  "locations": [
    {{
      "name": "location name",
      "condition": "condition description or null",
      "atmosphere": "atmosphere description or null",
      "occupants": ["character1", "character2"]
    }}
  ],
  "objects": [
    {{
      "name": "object name",
      "location": "where it is",
      "owner": "who has it or null",
      "condition": "its condition or null",
      "significance": "why it matters or null"
    }}
  ]
}}

If no changes for a category, use empty array. Return ONLY the JSON, no other text."""

            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt="You are a precise story analysis assistant. Extract entity state changes and return only valid JSON.",
                max_tokens=1000
            )
            
            # Parse JSON response
            # Clean up response (remove markdown code blocks if present)
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            state_changes = json.loads(response_clean)
            return state_changes
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response was: {response}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract state changes: {e}")
            return None
    
    async def _update_character_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        char_update: Dict[str, Any]
    ):
        """Update or create character state from extracted changes"""
        try:
            char_name = char_update.get("name")
            if not char_name:
                return
            
            # Find character by name in this story
            story_char = db.query(StoryCharacter).join(Character).filter(
                StoryCharacter.story_id == story_id,
                Character.name == char_name
            ).first()
            
            if not story_char:
                logger.warning(f"Character '{char_name}' not found in story {story_id}")
                return
            
            # Get or create character state
            char_state = db.query(CharacterState).filter(
                CharacterState.character_id == story_char.character_id,
                CharacterState.story_id == story_id
            ).first()
            
            if not char_state:
                char_state = CharacterState(
                    character_id=story_char.character_id,
                    story_id=story_id,
                    possessions=[],
                    knowledge=[],
                    secrets=[],
                    relationships={},
                    recent_actions=[],
                    recent_decisions=[],
                    full_state={}
                )
                db.add(char_state)
            
            # Update fields
            char_state.last_updated_scene = scene_sequence
            
            if char_update.get("location"):
                char_state.current_location = char_update["location"]
            
            if char_update.get("emotional_state"):
                char_state.emotional_state = char_update["emotional_state"]
            
            if char_update.get("physical_condition"):
                char_state.physical_condition = char_update["physical_condition"]
            
            # Update possessions
            if char_update.get("possessions_gained"):
                current_poss = char_state.possessions or []
                char_state.possessions = list(set(current_poss + char_update["possessions_gained"]))
            
            if char_update.get("possessions_lost"):
                current_poss = char_state.possessions or []
                char_state.possessions = [p for p in current_poss if p not in char_update["possessions_lost"]]
            
            # Update knowledge
            if char_update.get("knowledge_gained"):
                current_knowledge = char_state.knowledge or []
                char_state.knowledge = list(set(current_knowledge + char_update["knowledge_gained"]))
            
            # Update relationships
            if char_update.get("relationship_changes"):
                current_relationships = char_state.relationships or {}
                current_relationships.update(char_update["relationship_changes"])
                char_state.relationships = current_relationships
            
            db.commit()
            logger.debug(f"Updated character state for {char_name}")
            
        except Exception as e:
            logger.error(f"Failed to update character state: {e}")
            db.rollback()
    
    async def _update_location_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        loc_update: Dict[str, Any]
    ):
        """Update or create location state from extracted changes"""
        try:
            loc_name = loc_update.get("name")
            if not loc_name:
                return
            
            # Get or create location state
            loc_state = db.query(LocationState).filter(
                LocationState.story_id == story_id,
                LocationState.location_name == loc_name
            ).first()
            
            if not loc_state:
                loc_state = LocationState(
                    story_id=story_id,
                    location_name=loc_name,
                    notable_features=[],
                    current_occupants=[],
                    significant_events=[],
                    full_state={}
                )
                db.add(loc_state)
            
            # Update fields
            loc_state.last_updated_scene = scene_sequence
            
            if loc_update.get("condition"):
                loc_state.condition = loc_update["condition"]
            
            if loc_update.get("atmosphere"):
                loc_state.atmosphere = loc_update["atmosphere"]
            
            if loc_update.get("occupants"):
                loc_state.current_occupants = loc_update["occupants"]
            
            db.commit()
            logger.debug(f"Updated location state for {loc_name}")
            
        except Exception as e:
            logger.error(f"Failed to update location state: {e}")
            db.rollback()
    
    async def _update_object_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        obj_update: Dict[str, Any]
    ):
        """Update or create object state from extracted changes"""
        try:
            obj_name = obj_update.get("name")
            if not obj_name:
                return
            
            # Get or create object state
            obj_state = db.query(ObjectState).filter(
                ObjectState.story_id == story_id,
                ObjectState.object_name == obj_name
            ).first()
            
            if not obj_state:
                obj_state = ObjectState(
                    story_id=story_id,
                    object_name=obj_name,
                    powers=[],
                    limitations=[],
                    previous_owners=[],
                    recent_events=[],
                    full_state={}
                )
                db.add(obj_state)
            
            # Update fields
            obj_state.last_updated_scene = scene_sequence
            
            if obj_update.get("location"):
                obj_state.current_location = obj_update["location"]
            
            if obj_update.get("condition"):
                obj_state.condition = obj_update["condition"]
            
            if obj_update.get("significance"):
                obj_state.significance = obj_update["significance"]
            
            # Update owner if specified
            if obj_update.get("owner"):
                owner_name = obj_update["owner"]
                # Find character ID by name
                story_char = db.query(StoryCharacter).join(Character).filter(
                    StoryCharacter.story_id == story_id,
                    Character.name == owner_name
                ).first()
                if story_char:
                    obj_state.current_owner_id = story_char.character_id
            
            db.commit()
            logger.debug(f"Updated object state for {obj_name}")
            
        except Exception as e:
            logger.error(f"Failed to update object state: {e}")
            db.rollback()
    
    def get_character_state(
        self,
        db: Session,
        character_id: int,
        story_id: int
    ) -> Optional[CharacterState]:
        """Get current character state"""
        return db.query(CharacterState).filter(
            CharacterState.character_id == character_id,
            CharacterState.story_id == story_id
        ).first()
    
    def get_all_character_states(
        self,
        db: Session,
        story_id: int
    ) -> List[CharacterState]:
        """Get all character states for a story"""
        return db.query(CharacterState).filter(
            CharacterState.story_id == story_id
        ).all()
    
    def get_location_state(
        self,
        db: Session,
        story_id: int,
        location_name: str
    ) -> Optional[LocationState]:
        """Get current location state"""
        return db.query(LocationState).filter(
            LocationState.story_id == story_id,
            LocationState.location_name == location_name
        ).first()
    
    def get_all_location_states(
        self,
        db: Session,
        story_id: int
    ) -> List[LocationState]:
        """Get all location states for a story"""
        return db.query(LocationState).filter(
            LocationState.story_id == story_id
        ).all()
    
    def get_object_state(
        self,
        db: Session,
        story_id: int,
        object_name: str
    ) -> Optional[ObjectState]:
        """Get current object state"""
        return db.query(ObjectState).filter(
            ObjectState.story_id == story_id,
            ObjectState.object_name == object_name
        ).first()
    
    def get_all_object_states(
        self,
        db: Session,
        story_id: int
    ) -> List[ObjectState]:
        """Get all object states for a story"""
        return db.query(ObjectState).filter(
            ObjectState.story_id == story_id
        ).all()

