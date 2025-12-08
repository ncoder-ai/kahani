"""
Entity State Service

Tracks and updates the state of characters, locations, and objects throughout a story.
Uses LLM to extract state changes from scenes and maintains authoritative truth.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from ..models import (
    Character, CharacterState, LocationState, ObjectState,
    Story, Scene, StoryCharacter, EntityStateBatch, StoryBranch
)
from ..services.llm.service import UnifiedLLMService
from ..services.llm.extraction_service import ExtractionLLMService
from ..services.llm.prompts import prompt_manager
from ..config import settings

logger = logging.getLogger(__name__)


def clean_llm_json(json_str: str) -> str:
    """
    Clean common JSON errors from LLM responses.
    
    Common issues:
    - Unquoted values (e.g., location: above instead of location: "above")
    - Trailing commas
    - Comments
    """
    # Fix unquoted values in key-value pairs
    # Pattern: "key": value, or "key": value}
    # Replace with: "key": "value", or "key": "value"}
    # This regex finds: "key": <word_without_quotes>
    json_str = re.sub(
        r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,}\]])',
        r': "\1"\2',
        json_str
    )
    
    # Remove trailing commas before closing brackets
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Remove comments (// or /* */)
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    return json_str


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
        self.extraction_service = None  # Will be initialized conditionally
    
    def _get_active_branch_id(self, db: Session, story_id: int) -> int:
        """Get the active branch ID for a story."""
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        return active_branch.id if active_branch else None
    
    async def extract_and_update_states(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        scene_content: str,
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Extract state changes from a scene and update all entity states.
        
        Args:
            db: Database session
            story_id: Story ID
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            scene_content: Scene content text
            branch_id: Optional branch ID (if not provided, uses active branch)
            
        Returns:
            Dictionary with extraction results
        """
        results = {
            "characters_updated": 0,
            "locations_updated": 0,
            "objects_updated": 0,
            "extraction_successful": False
        }
        
        # Verify scene exists before processing (prevents foreign key violations)
        scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene_exists:
            logger.warning(f"Scene {scene_id} doesn't exist, cannot extract entity states")
            return results
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        try:
            # Get story characters for context (filtered by branch)
            char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
            if branch_id:
                char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
            story_characters = char_query.all()
            
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
                        db, story_id, scene_sequence, char_update, branch_id=branch_id
                    )
                    results["characters_updated"] += 1
            
            # Update location states
            if "locations" in state_changes:
                for loc_update in state_changes["locations"]:
                    await self._update_location_state(
                        db, story_id, scene_sequence, loc_update, branch_id=branch_id
                    )
                    results["locations_updated"] += 1
            
            # Update object states
            if "objects" in state_changes:
                for obj_update in state_changes["objects"]:
                    await self._update_object_state(
                        db, story_id, scene_sequence, obj_update, branch_id=branch_id
                    )
                    results["objects_updated"] += 1
            
            results["extraction_successful"] = True
            logger.info(f"Updated entity states for scene {scene_id}: {results}")
            
            # Check if we should create a batch snapshot (every 5 scenes, matching chapter summary batch threshold)
            batch_threshold = self.user_settings.get("context_summary_threshold", 5)
            if scene_sequence % batch_threshold == 0:
                # Find the start of this batch
                batch_start = ((scene_sequence - 1) // batch_threshold) * batch_threshold + 1
                batch_end = scene_sequence
                
                # Create batch snapshot
                try:
                    self.create_entity_state_batch_snapshot(
                        db, story_id, batch_start, batch_end, branch_id=branch_id
                    )
                except Exception as e:
                    # Don't fail extraction if batch creation fails
                    logger.warning(f"Failed to create entity state batch snapshot: {e}")
            
        except Exception as e:
            logger.error(f"Failed to extract and update entity states: {e}")
        
        return results
    
    def _get_extraction_service(self) -> Optional[ExtractionLLMService]:
        """
        Get or create extraction service if enabled in user settings
        
        Returns:
            ExtractionLLMService instance or None if not enabled
        """
        # Check if extraction model is enabled
        extraction_settings = self.user_settings.get('extraction_model_settings', {})
        if not extraction_settings.get('enabled', False):
            return None
        
        try:
            # Get extraction model configuration
            ext_defaults = settings._yaml_config.get('extraction_model', {})
            url = extraction_settings.get('url', ext_defaults.get('url'))
            model = extraction_settings.get('model_name', ext_defaults.get('model_name'))
            api_key = extraction_settings.get('api_key', ext_defaults.get('api_key', ''))
            temperature = extraction_settings.get('temperature', ext_defaults.get('temperature'))
            max_tokens = extraction_settings.get('max_tokens', ext_defaults.get('max_tokens'))
            
            # Create extraction service
            return ExtractionLLMService(
                url=url,
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.warning(f"Failed to initialize extraction service: {e}")
            return None
    
    async def _extract_state_changes(
        self,
        scene_content: str,
        scene_sequence: int,
        character_names: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract state changes from a scene.
        Tries extraction model first, falls back to main LLM if enabled.
        
        Returns JSON with character, location, and object updates.
        """
        # Try extraction model first if enabled
        extraction_service = self._get_extraction_service()
        if extraction_service:
            try:
                logger.info(f"Using extraction model for entity state extraction (user {self.user_id})")
                state_changes = await extraction_service.extract_entity_states(
                    scene_content=scene_content,
                    scene_sequence=scene_sequence,
                    character_names=character_names
                )
                
                # Validate state changes
                validated = self._validate_state_changes(state_changes)
                if validated:
                    logger.info(f"Extraction model successfully extracted entity states")
                    return validated
                else:
                    logger.warning("Extraction model returned no valid state changes, falling back to main LLM")
            except Exception as e:
                logger.warning(f"Extraction model failed: {e}, falling back to main LLM")
                # Continue to fallback
        
        # Fallback to main LLM
        fallback_enabled = self.user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
        if not fallback_enabled and extraction_service:
            logger.warning("Extraction model failed and fallback disabled, returning empty results")
            return {'characters': [], 'locations': [], 'objects': []}
        
        try:
            logger.info(f"Using main LLM for entity state extraction (user {self.user_id})")
            
            # Get prompts from centralized prompts.yml
            system_prompt = prompt_manager.get_prompt("entity_state_extraction.single", "system")
            user_prompt = prompt_manager.get_prompt(
                "entity_state_extraction.single", "user",
                scene_sequence=scene_sequence,
                scene_content=scene_content,
                character_names=', '.join(character_names)
            )

            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=1000
            )
            
            logger.warning(f"RAW LLM RESPONSE - ENTITY STATES:\n{response}")
            
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
            
            # Clean common JSON errors from LLM
            response_clean = clean_llm_json(response_clean)
            
            state_changes = json.loads(response_clean)
            return self._validate_state_changes(state_changes)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Original response was: {response}")
            logger.debug(f"Cleaned response was: {response_clean}")
            return None
        except Exception as e:
            logger.error(f"Main LLM entity state extraction failed: {e}")
            return None
    
    def _validate_state_changes(self, state_changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize state changes dictionary
        
        Args:
            state_changes: Raw state changes dictionary
            
        Returns:
            Validated state changes dictionary
        """
        if not isinstance(state_changes, dict):
            return {'characters': [], 'locations': [], 'objects': []}
        
        validated = {
            'characters': [],
            'locations': [],
            'objects': []
        }
        
        # Validate characters
        characters = state_changes.get('characters', [])
        if isinstance(characters, list):
            for char in characters:
                if isinstance(char, dict) and char.get('name'):
                    validated['characters'].append(char)
        
        # Validate locations
        locations = state_changes.get('locations', [])
        if isinstance(locations, list):
            for loc in locations:
                if isinstance(loc, dict) and loc.get('name'):
                    validated['locations'].append(loc)
        
        # Validate objects
        objects = state_changes.get('objects', [])
        if isinstance(objects, list):
            for obj in objects:
                if isinstance(obj, dict) and obj.get('name'):
                    validated['objects'].append(obj)
        
        return validated
    
    async def _update_character_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        char_update: Dict[str, Any],
        branch_id: int = None
    ):
        """Update or create character state from extracted changes"""
        try:
            char_name = char_update.get("name")
            if not char_name:
                return
            
            # Find character by name in this story (filtered by branch)
            char_query = db.query(StoryCharacter).join(Character).filter(
                StoryCharacter.story_id == story_id,
                Character.name == char_name
            )
            if branch_id:
                char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
            story_char = char_query.first()
            
            if not story_char:
                logger.warning(f"Character '{char_name}' not found in story {story_id} (branch {branch_id})")
                return
            
            # Get or create character state (filtered by branch)
            state_query = db.query(CharacterState).filter(
                CharacterState.character_id == story_char.character_id,
                CharacterState.story_id == story_id
            )
            if branch_id:
                state_query = state_query.filter(CharacterState.branch_id == branch_id)
            char_state = state_query.first()
            
            if not char_state:
                char_state = CharacterState(
                    character_id=story_char.character_id,
                    story_id=story_id,
                    branch_id=branch_id,
                    possessions=[],
                    knowledge=[],
                    secrets=[],
                    relationships={},
                    recent_actions=[],
                    recent_decisions=[],
                    full_state={}
                )
                db.add(char_state)
                try:
                    db.flush()  # Flush to catch constraint violations immediately
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "duplicate" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"Character state already exists (race condition), reloading: {char_name}")
                        # Reload the state that was created by another process
                        state_query = db.query(CharacterState).filter(
                            CharacterState.character_id == story_char.character_id,
                            CharacterState.story_id == story_id
                        )
                        if branch_id:
                            state_query = state_query.filter(CharacterState.branch_id == branch_id)
                        char_state = state_query.first()
                        if not char_state:
                            logger.error(f"Failed to reload character state after race condition: {char_name}")
                            return
                    else:
                        # Re-raise if it's a different integrity error
                        raise
            
            # Update fields
            char_state.last_updated_scene = scene_sequence
            
            if char_update.get("location"):
                char_state.current_location = char_update["location"]
            
            if char_update.get("emotional_state"):
                char_state.emotional_state = char_update["emotional_state"]
            
            if char_update.get("physical_condition"):
                char_state.physical_condition = char_update["physical_condition"]
            
            if char_update.get("current_attire"):
                char_state.appearance = char_update["current_attire"]
            
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
            
            try:
                db.commit()
                logger.debug(f"Updated character state for {char_name}")
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"Failed to commit character state update for {char_name}: {ie}")
                # Don't re-raise - allow processing to continue
            
        except Exception as e:
            logger.error(f"Failed to update character state: {e}")
            db.rollback()
    
    async def _update_location_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        loc_update: Dict[str, Any],
        branch_id: int = None
    ):
        """Update or create location state from extracted changes"""
        try:
            loc_name = loc_update.get("name")
            if not loc_name:
                return
            
            # Get or create location state (filtered by branch)
            state_query = db.query(LocationState).filter(
                LocationState.story_id == story_id,
                LocationState.location_name == loc_name
            )
            if branch_id:
                state_query = state_query.filter(LocationState.branch_id == branch_id)
            loc_state = state_query.first()
            
            if not loc_state:
                loc_state = LocationState(
                    story_id=story_id,
                    branch_id=branch_id,
                    location_name=loc_name,
                    notable_features=[],
                    current_occupants=[],
                    significant_events=[],
                    full_state={}
                )
                db.add(loc_state)
                try:
                    db.flush()  # Flush to catch constraint violations immediately
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "duplicate" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"Location state already exists (race condition), reloading: {loc_name}")
                        # Reload the state that was created by another process
                        state_query = db.query(LocationState).filter(
                            LocationState.story_id == story_id,
                            LocationState.location_name == loc_name
                        )
                        if branch_id:
                            state_query = state_query.filter(LocationState.branch_id == branch_id)
                        loc_state = state_query.first()
                        if not loc_state:
                            logger.error(f"Failed to reload location state after race condition: {loc_name}")
                            return
                    else:
                        # Re-raise if it's a different integrity error
                        raise
            
            # Update fields
            loc_state.last_updated_scene = scene_sequence
            
            if loc_update.get("condition"):
                loc_state.condition = loc_update["condition"]
            
            if loc_update.get("atmosphere"):
                loc_state.atmosphere = loc_update["atmosphere"]
            
            if loc_update.get("occupants"):
                loc_state.current_occupants = loc_update["occupants"]
            
            try:
                db.commit()
                logger.debug(f"Updated location state for {loc_name}")
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"Failed to commit location state update for {loc_name}: {ie}")
                # Don't re-raise - allow processing to continue
            
        except Exception as e:
            logger.error(f"Failed to update location state: {e}")
            db.rollback()
    
    async def _update_object_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        obj_update: Dict[str, Any],
        branch_id: int = None
    ):
        """Update or create object state from extracted changes"""
        try:
            obj_name = obj_update.get("name")
            if not obj_name:
                return
            
            # Get or create object state (filtered by branch)
            state_query = db.query(ObjectState).filter(
                ObjectState.story_id == story_id,
                ObjectState.object_name == obj_name
            )
            if branch_id:
                state_query = state_query.filter(ObjectState.branch_id == branch_id)
            obj_state = state_query.first()
            
            if not obj_state:
                obj_state = ObjectState(
                    story_id=story_id,
                    branch_id=branch_id,
                    object_name=obj_name,
                    powers=[],
                    limitations=[],
                    previous_owners=[],
                    recent_events=[],
                    full_state={}
                )
                db.add(obj_state)
                try:
                    db.flush()  # Flush to catch constraint violations immediately
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "duplicate" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"Object state already exists (race condition), reloading: {obj_name}")
                        # Reload the state that was created by another process
                        state_query = db.query(ObjectState).filter(
                            ObjectState.story_id == story_id,
                            ObjectState.object_name == obj_name
                        )
                        if branch_id:
                            state_query = state_query.filter(ObjectState.branch_id == branch_id)
                        obj_state = state_query.first()
                        if not obj_state:
                            logger.error(f"Failed to reload object state after race condition: {obj_name}")
                            return
                    else:
                        # Re-raise if it's a different integrity error
                        raise
            
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
                # Find character ID by name (filter by branch to avoid cross-branch contamination)
                story_char_query = db.query(StoryCharacter).join(Character).filter(
                    StoryCharacter.story_id == story_id,
                    Character.name == owner_name
                )
                if branch_id:
                    story_char_query = story_char_query.filter(StoryCharacter.branch_id == branch_id)
                story_char = story_char_query.first()
                if story_char:
                    obj_state.current_owner_id = story_char.character_id
            
            try:
                db.commit()
                logger.debug(f"Updated object state for {obj_name}")
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"Failed to commit object state update for {obj_name}: {ie}")
                # Don't re-raise - allow processing to continue
            
        except Exception as e:
            logger.error(f"Failed to update object state: {e}")
            db.rollback()
    
    def get_character_state(
        self,
        db: Session,
        character_id: int,
        story_id: int,
        branch_id: int = None
    ) -> Optional[CharacterState]:
        """Get current character state (optionally filtered by branch)"""
        query = db.query(CharacterState).filter(
            CharacterState.character_id == character_id,
            CharacterState.story_id == story_id
        )
        if branch_id:
            query = query.filter(CharacterState.branch_id == branch_id)
        return query.first()
    
    def get_all_character_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[CharacterState]:
        """Get all character states for a story (optionally filtered by branch)"""
        query = db.query(CharacterState).filter(
            CharacterState.story_id == story_id
        )
        if branch_id:
            query = query.filter(CharacterState.branch_id == branch_id)
        return query.all()
    
    def get_location_state(
        self,
        db: Session,
        story_id: int,
        location_name: str,
        branch_id: int = None
    ) -> Optional[LocationState]:
        """Get current location state (optionally filtered by branch)"""
        query = db.query(LocationState).filter(
            LocationState.story_id == story_id,
            LocationState.location_name == location_name
        )
        if branch_id:
            query = query.filter(LocationState.branch_id == branch_id)
        return query.first()
    
    def get_all_location_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[LocationState]:
        """Get all location states for a story (optionally filtered by branch)"""
        query = db.query(LocationState).filter(
            LocationState.story_id == story_id
        )
        if branch_id:
            query = query.filter(LocationState.branch_id == branch_id)
        return query.all()
    
    def get_object_state(
        self,
        db: Session,
        story_id: int,
        object_name: str,
        branch_id: int = None
    ) -> Optional[ObjectState]:
        """Get current object state (optionally filtered by branch)"""
        query = db.query(ObjectState).filter(
            ObjectState.story_id == story_id,
            ObjectState.object_name == object_name
        )
        if branch_id:
            query = query.filter(ObjectState.branch_id == branch_id)
        return query.first()
    
    def get_all_object_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[ObjectState]:
        """Get all object states for a story (optionally filtered by branch)"""
        query = db.query(ObjectState).filter(
            ObjectState.story_id == story_id
        )
        if branch_id:
            query = query.filter(ObjectState.branch_id == branch_id)
        return query.all()
    
    def create_entity_state_batch_snapshot(
        self,
        db: Session,
        story_id: int,
        start_scene_sequence: int,
        end_scene_sequence: int,
        branch_id: int = None
    ) -> Optional[EntityStateBatch]:
        """
        Create a snapshot of current entity states as a batch.
        
        Args:
            db: Database session
            story_id: Story ID
            start_scene_sequence: First scene sequence in batch
            end_scene_sequence: Last scene sequence in batch
            branch_id: Optional branch ID for filtering
            
        Returns:
            Created EntityStateBatch or None if no states exist
        """
        try:
            # Get all current entity states (filtered by branch)
            char_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            if branch_id:
                char_query = char_query.filter(CharacterState.branch_id == branch_id)
            character_states = char_query.all()
            
            loc_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            if branch_id:
                loc_query = loc_query.filter(LocationState.branch_id == branch_id)
            location_states = loc_query.all()
            
            obj_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id:
                obj_query = obj_query.filter(ObjectState.branch_id == branch_id)
            object_states = obj_query.all()
            
            # Convert to JSON snapshots
            character_snapshot = [state.to_dict() for state in character_states]
            location_snapshot = [state.to_dict() for state in location_states]
            object_snapshot = [state.to_dict() for state in object_states]
            
            # Only create batch if there are states to snapshot
            if not (character_snapshot or location_snapshot or object_snapshot):
                logger.debug(f"No entity states to snapshot for story {story_id} (branch {branch_id})")
                return None
            
            # Create batch snapshot
            batch = EntityStateBatch(
                story_id=story_id,
                branch_id=branch_id,
                start_scene_sequence=start_scene_sequence,
                end_scene_sequence=end_scene_sequence,
                character_states_snapshot=character_snapshot,
                location_states_snapshot=location_snapshot,
                object_states_snapshot=object_snapshot
            )
            
            db.add(batch)
            db.flush()
            
            logger.info(f"Created entity state batch snapshot for story {story_id} (branch {branch_id}): scenes {start_scene_sequence}-{end_scene_sequence} ({len(character_snapshot)} characters, {len(location_snapshot)} locations, {len(object_snapshot)} objects)")
            
            return batch
            
        except Exception as e:
            logger.error(f"Failed to create entity state batch snapshot: {e}")
            return None
    
    def get_last_valid_batch(
        self,
        db: Session,
        story_id: int,
        max_scene_sequence: int,
        branch_id: int = None
    ) -> Optional[EntityStateBatch]:
        """
        Find the last valid batch that doesn't overlap with deleted scenes.
        
        Args:
            db: Database session
            story_id: Story ID
            max_scene_sequence: Maximum scene sequence to consider (scenes after this are deleted)
            branch_id: Optional branch ID to filter by
            
        Returns:
            Last valid EntityStateBatch or None
        """
        # Find the last batch where end_scene_sequence < max_scene_sequence
        batch_query = db.query(EntityStateBatch).filter(
            EntityStateBatch.story_id == story_id,
            EntityStateBatch.end_scene_sequence < max_scene_sequence
        )
        if branch_id is not None:
            batch_query = batch_query.filter(EntityStateBatch.branch_id == branch_id)
        batch = batch_query.order_by(EntityStateBatch.end_scene_sequence.desc()).first()
        
        return batch
    
    def restore_entity_states_from_batch(
        self,
        db: Session,
        batch: EntityStateBatch
    ) -> Dict[str, int]:
        """
        Restore entity states from a batch snapshot.
        
        Args:
            db: Database session
            batch: EntityStateBatch to restore from
            
        Returns:
            Dictionary with counts of restored states
        """
        try:
            # Delete existing entity states for this story
            db.query(CharacterState).filter(
                CharacterState.story_id == batch.story_id
            ).delete()
            db.query(LocationState).filter(
                LocationState.story_id == batch.story_id
            ).delete()
            db.query(ObjectState).filter(
                ObjectState.story_id == batch.story_id
            ).delete()
            
            # Restore character states
            char_count = 0
            for char_dict in batch.character_states_snapshot:
                char_state = CharacterState(**{k: v for k, v in char_dict.items() if k != 'id' and k != 'updated_at'})
                db.add(char_state)
                char_count += 1
            
            # Restore location states
            loc_count = 0
            for loc_dict in batch.location_states_snapshot:
                loc_state = LocationState(**{k: v for k, v in loc_dict.items() if k != 'id' and k != 'updated_at'})
                db.add(loc_state)
                loc_count += 1
            
            # Restore object states
            obj_count = 0
            for obj_dict in batch.object_states_snapshot:
                obj_state = ObjectState(**{k: v for k, v in obj_dict.items() if k != 'id' and k != 'updated_at'})
                db.add(obj_state)
                obj_count += 1
            
            db.flush()
            
            logger.info(f"Restored entity states from batch {batch.id}: {char_count} characters, {loc_count} locations, {obj_count} objects")
            
            return {
                "characters_restored": char_count,
                "locations_restored": loc_count,
                "objects_restored": obj_count
            }
            
        except Exception as e:
            logger.error(f"Failed to restore entity states from batch: {e}")
            db.rollback()
            return {"characters_restored": 0, "locations_restored": 0, "objects_restored": 0}
    
    def invalidate_entity_batches_for_scenes(
        self,
        db: Session,
        story_id: int,
        min_seq: int,
        max_seq: int,
        branch_id: int = None
    ) -> int:
        """
        Delete entity state batches that overlap with deleted scenes.
        
        Args:
            db: Database session
            story_id: Story ID
            min_seq: Minimum scene sequence deleted
            max_seq: Maximum scene sequence deleted
            branch_id: Optional branch ID to filter by
            
        Returns:
            Number of batches deleted
        """
        affected_batches_query = db.query(EntityStateBatch).filter(
            EntityStateBatch.story_id == story_id,
            EntityStateBatch.start_scene_sequence <= max_seq,
            EntityStateBatch.end_scene_sequence >= min_seq
        )
        if branch_id is not None:
            affected_batches_query = affected_batches_query.filter(EntityStateBatch.branch_id == branch_id)
        affected_batches = affected_batches_query.all()
        
        if affected_batches:
            count = len(affected_batches)
            for batch in affected_batches:
                db.delete(batch)
            logger.info(f"Invalidated {count} entity state batch(es) for story {story_id} (scenes {min_seq}-{max_seq})")
            return count
        
        return 0
    
    def restore_from_last_complete_batch(
        self,
        db: Session,
        story_id: int,
        max_deleted_sequence: int,
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Restore entity states from last complete batch without re-extraction.
        Used when deletion leaves an incomplete batch - we restore and wait for threshold.
        
        Args:
            db: Database session
            story_id: Story ID
            max_deleted_sequence: Maximum scene sequence that was deleted
            branch_id: Optional branch ID to filter by
            
        Returns:
            Dictionary with restoration results
        """
        try:
            # Find last valid batch before deleted scenes
            last_valid_batch = self.get_last_valid_batch(db, story_id, max_deleted_sequence, branch_id=branch_id)
            
            # Delete all existing entity states (filtered by branch)
            char_delete_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            loc_delete_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            obj_delete_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id is not None:
                char_delete_query = char_delete_query.filter(CharacterState.branch_id == branch_id)
                loc_delete_query = loc_delete_query.filter(LocationState.branch_id == branch_id)
                obj_delete_query = obj_delete_query.filter(ObjectState.branch_id == branch_id)
            char_delete_query.delete()
            loc_delete_query.delete()
            obj_delete_query.delete()
            
            # Restore from last valid batch if exists
            if last_valid_batch:
                restore_results = self.restore_entity_states_from_batch(db, last_valid_batch)
                logger.info(f"[DELETE] Restored entity states from batch {last_valid_batch.id} (scenes 1-{last_valid_batch.end_scene_sequence})")
                return {
                    **restore_results,
                    "restoration_successful": True
                }
            else:
                logger.info(f"[DELETE] No valid batch found, entity states cleared")
                return {
                    "characters_restored": 0,
                    "locations_restored": 0,
                    "objects_restored": 0,
                    "restoration_successful": True
                }
            
        except Exception as e:
            logger.error(f"Failed to restore entity states from last complete batch: {e}")
            db.rollback()
            return {
                "characters_restored": 0,
                "locations_restored": 0,
                "objects_restored": 0,
                "restoration_successful": False
            }
    
    async def recalculate_entity_states_from_batches(
        self,
        db: Session,
        story_id: int,
        user_id: int,
        user_settings: Dict[str, Any],
        max_deleted_sequence: int,
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Recalculate entity states using batch system after scene deletion.
        Only re-extracts if remaining scenes form a complete batch.
        
        Args:
            db: Database session
            story_id: Story ID
            user_id: User ID
            user_settings: User settings
            max_deleted_sequence: Maximum scene sequence that was deleted
            branch_id: Optional branch ID to filter by
            
        Returns:
            Dictionary with recalculation results
        """
        try:
            # Find last valid batch before deleted scenes
            last_valid_batch = self.get_last_valid_batch(db, story_id, max_deleted_sequence, branch_id=branch_id)
            
            # Delete all existing entity states (filtered by branch)
            char_delete_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            loc_delete_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            obj_delete_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id is not None:
                char_delete_query = char_delete_query.filter(CharacterState.branch_id == branch_id)
                loc_delete_query = loc_delete_query.filter(LocationState.branch_id == branch_id)
                obj_delete_query = obj_delete_query.filter(ObjectState.branch_id == branch_id)
            char_delete_query.delete()
            loc_delete_query.delete()
            obj_delete_query.delete()
            
            # Restore from last valid batch if exists
            if last_valid_batch:
                restore_results = self.restore_entity_states_from_batch(db, last_valid_batch)
                start_sequence = last_valid_batch.end_scene_sequence + 1
                logger.info(f"Restored entity states from batch {last_valid_batch.id} (scenes 1-{last_valid_batch.end_scene_sequence})")
            else:
                restore_results = {"characters_restored": 0, "locations_restored": 0, "objects_restored": 0}
                start_sequence = 1
                logger.info(f"No valid batch found, starting from scene 1")
            
            # Get all remaining scenes after the last valid batch (filtered by branch)
            from ..models import Scene, StoryFlow
            remaining_scenes_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= start_sequence
            )
            if branch_id is not None:
                remaining_scenes_query = remaining_scenes_query.filter(Scene.branch_id == branch_id)
            remaining_scenes = remaining_scenes_query.order_by(Scene.sequence_number).all()
            
            if not remaining_scenes:
                logger.info(f"No remaining scenes to process after batch restoration")
                db.commit()
                return {
                    **restore_results,
                    "scenes_processed": 0,
                    "recalculation_successful": True
                }
            
            # Check if remaining scenes form a complete batch
            batch_threshold = self.user_settings.get("context_summary_threshold", 5)
            last_remaining_sequence = remaining_scenes[-1].sequence_number
            
            # Check if we have a complete batch (last scene sequence is a multiple of threshold)
            is_complete_batch = (last_remaining_sequence % batch_threshold) == 0
            
            if not is_complete_batch:
                # Incomplete batch - only restore, don't re-extract
                logger.info(f"[DELETE] Incomplete batch remaining (last scene: {last_remaining_sequence}, threshold: {batch_threshold}). Restored from batch, waiting for threshold.")
                db.commit()
                return {
                    **restore_results,
                    "scenes_processed": 0,
                    "recalculation_successful": True,
                    "incomplete_batch": True
                }
            
            # Complete batch - re-extract entity states for remaining scenes
            scenes_processed = 0
            for scene in remaining_scenes:
                # Get active variant content
                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()
                
                if flow and flow.scene_variant:
                    scene_content = flow.scene_variant.content
                    await self.extract_and_update_states(
                        db=db,
                        story_id=story_id,
                        scene_id=scene.id,
                        scene_sequence=scene.sequence_number,
                        scene_content=scene_content
                    )
                    scenes_processed += 1
            
            db.commit()
            
            logger.info(f"Recalculated entity states: restored from batch, then processed {scenes_processed} remaining scenes")
            
            return {
                **restore_results,
                "scenes_processed": scenes_processed,
                "recalculation_successful": True
            }
            
        except Exception as e:
            logger.error(f"Failed to recalculate entity states from batches: {e}")
            db.rollback()
            return {
                "characters_restored": 0,
                "locations_restored": 0,
                "objects_restored": 0,
                "scenes_processed": 0,
                "recalculation_successful": False
            }

