"""
NPC Tracking Service

Tracks NPCs (Non-Player Characters) mentioned in scenes, calculates importance scores,
and automatically includes them in context when they cross an importance threshold.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from ..models import (
    NPCMention, NPCTracking, NPCTrackingSnapshot, StoryCharacter, Character, Scene, Story, StoryBranch
)
from ..services.llm.service import UnifiedLLMService
from ..services.llm.extraction_service import ExtractionLLMService
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


class NPCTrackingService:
    """
    Service for tracking and managing NPCs in stories.
    
    Responsibilities:
    - Extract NPCs from scenes using LLM
    - Track mentions and calculate importance scores
    - Extract full character profiles when threshold crossed
    - Format NPCs for inclusion in context or character suggestions
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any]):
        self.user_id = user_id
        self.user_settings = user_settings
        self.llm_service = UnifiedLLMService()
        self.importance_threshold = user_settings.get("npc_importance_threshold", settings.npc_importance_threshold)
        self.extraction_service = None  # Will be initialized conditionally
    
    async def extract_npcs_from_scenes_batch(
        self,
        db: Session,
        story_id: int,
        scenes: List[Tuple[int, int, str]],  # List of (scene_id, scene_sequence, scene_content) tuples
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Batch extract NPCs from multiple scenes in a single LLM call, then store them.
        
        Args:
            db: Database session
            story_id: Story ID
            scenes: List of (scene_id, scene_sequence, scene_content) tuples
            branch_id: Optional branch ID for filtering
            
        Returns:
            Dictionary with extraction results:
            - npcs_tracked: Total NPCs tracked
            - scenes_processed: Number of scenes processed
            - extraction_successful: Whether extraction completed
        """
        logger.info(f"[NPC-EXTRACT-BATCH] Starting batch extraction: story_id={story_id}, branch_id={branch_id}, num_scenes={len(scenes)}")
        if scenes:
            scene_ids = [s[0] for s in scenes]
            scene_seqs = [s[1] for s in scenes]
            logger.info(f"[NPC-EXTRACT-BATCH] Scene IDs: {scene_ids}, Sequences: {scene_seqs}")
        
        if not scenes:
            return {
                "npcs_tracked": 0,
                "scenes_processed": 0,
                "extraction_successful": False
            }
        
        try:
            # Get list of explicit characters in the story (filtered by branch)
            from ..models import StoryCharacter, Character
            char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
            if branch_id:
                char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
            story_characters = char_query.all()
            logger.info(f"[NPC-EXTRACT-BATCH] Found {len(story_characters)} explicit characters to exclude")
            
            explicit_character_names = set()
            explicit_name_parts = set()  # For partial matching (e.g., "Alice" matches "Alice Smith")
            for sc in story_characters:
                character = db.query(Character).filter(Character.id == sc.character_id).first()
                if character:
                    name_lower = character.name.lower()
                    explicit_character_names.add(name_lower)
                    # Add individual name parts for partial matching
                    for part in name_lower.split():
                        if len(part) > 2:  # Skip short parts like "a", "of"
                            explicit_name_parts.add(part)

            # Concatenate scenes with clear markers
            scenes_text = []
            for scene_id, scene_sequence, scene_content in scenes:
                scenes_text.append(f"=== SCENE {scene_sequence} (ID: {scene_id}) ===\n{scene_content}\n")
            
            batch_content = "\n".join(scenes_text)
            
            # Extract NPCs from all scenes at once
            npc_data = await self._extract_npcs_with_llm_batch(
                batch_content,
                list(explicit_character_names),
                explicit_name_parts=explicit_name_parts
            )
            
            if not npc_data or "npcs" not in npc_data:
                logger.warning(f"No NPCs extracted from batch of {len(scenes)} scenes")
                return {
                    "npcs_tracked": 0,
                    "scenes_processed": len(scenes),
                    "extraction_successful": False
                }
            
            # Post-process: Map NPCs to scenes using text verification
            from ..utils.scene_verification import map_npcs_to_scenes
            scenes_for_verification = [(scene_id, scene_content) for scene_id, _, scene_content in scenes]
            extracted_npcs = npc_data.get("npcs", [])
            
            # Validate NPCs before mapping (filters generic entities, explicit chars, and non-CHARACTER types)
            validated_npcs = self._validate_npcs(extracted_npcs, explicit_name_parts=explicit_name_parts)
            
            scene_npc_map = map_npcs_to_scenes(validated_npcs, scenes_for_verification)
            
            # Store NPCs for each scene
            total_npcs_tracked = 0
            for scene_id, scene_sequence, scene_content in scenes:
                npcs_for_scene = scene_npc_map.get(scene_id, [])
                
                # Verify scene exists before processing (prevents foreign key violations)
                scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
                if not scene_exists:
                    logger.warning(f"Scene {scene_id} doesn't exist yet, skipping NPC mentions for this scene")
                    continue
                
                for npc_data_scene in npcs_for_scene:
                    npc_name = npc_data_scene.get('name', '').strip()
                    if not npc_name:
                        logger.debug(f"[NPC-EXTRACT-BATCH] Skipping NPC with empty name")
                        continue

                    # Convert string booleans to actual booleans
                    def to_bool(value):
                        if isinstance(value, bool):
                            return value
                        if isinstance(value, str):
                            return value.lower() in ('true', '1', 'yes')
                        return bool(value)
                    
                    # Store mention with IntegrityError handling
                    try:
                        logger.info(f"[NPC-EXTRACT-BATCH] Creating NPCMention: name='{npc_name}', story_id={story_id}, branch_id={branch_id}, scene_id={scene_id}, seq={scene_sequence}")
                        mention = NPCMention(
                            story_id=story_id,
                            branch_id=branch_id,
                            scene_id=scene_id,
                            character_name=npc_name,
                            sequence_number=scene_sequence,
                            mention_count=npc_data_scene.get("mention_count", 1),
                            has_dialogue=to_bool(npc_data_scene.get("has_dialogue", False)),
                            has_actions=to_bool(npc_data_scene.get("has_actions", False)),
                            has_relationships=to_bool(npc_data_scene.get("has_relationships", False)),
                            context_snippets=npc_data_scene.get("context_snippets", []),
                            extracted_properties=npc_data_scene.get("properties", {})
                        )
                        db.add(mention)
                        db.flush()  # Flush to catch constraint violations immediately
                        
                        # Update or create tracking record
                        await self._update_npc_tracking(
                            db, story_id, npc_name, scene_sequence, npc_data_scene, branch_id=branch_id
                        )
                        
                        total_npcs_tracked += 1
                    except IntegrityError as ie:
                        db.rollback()
                        error_msg = str(ie).lower()
                        if "foreign key" in error_msg and "scene_id" in error_msg:
                            logger.warning(f"Scene {scene_id} was deleted during extraction, skipping NPC mention for {npc_name}")
                            break  # Skip remaining NPCs for this scene
                        elif "duplicate key" in error_msg or "unique constraint" in error_msg:
                            logger.debug(f"NPC mention already exists (race condition), skipping: {npc_name} in scene {scene_id}")
                            continue
                        else:
                            # Re-raise if it's a different integrity error
                            raise
                
                # Create snapshot after all NPCs for this scene are processed
                # Pass chapter_id for chapter-aware NPC tiering
                scene_chapter_id = scene_exists.chapter_id if scene_exists else None
                self._create_npc_tracking_snapshot(db, story_id, scene_id, scene_sequence, branch_id=branch_id, chapter_id=scene_chapter_id)

            db.commit()
            logger.info(f"Batch extracted and stored {total_npcs_tracked} NPCs from {len(scenes)} scenes")
            
            return {
                "npcs_tracked": total_npcs_tracked,
                "scenes_processed": len(scenes),
                "extraction_successful": True
            }
            
        except Exception as e:
            logger.error(f"Failed to batch extract NPCs: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            db.rollback()
            return {
                "npcs_tracked": 0,
                "scenes_processed": len(scenes) if scenes else 0,
                "extraction_successful": False
            }
    
    def _get_extraction_service(self) -> Optional[ExtractionLLMService]:
        """
        Get or create extraction service if enabled in user settings
        
        Returns:
            ExtractionLLMService instance or None if not enabled
        """
        service_defaults = settings.service_defaults.get('extraction_service', {})
        npc_max_tokens = service_defaults.get('npc_tracking_max_tokens', 1500)
        return ExtractionLLMService.from_settings(self.user_settings, max_tokens_override=npc_max_tokens)

    async def _extract_npcs_with_llm_batch(
        self,
        batch_content: str,
        explicit_character_names: List[str],
        explicit_name_parts: Optional[set] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract NPCs from multiple scenes in batch.
        Tries extraction model first, falls back to main LLM if enabled.

        Returns JSON with NPC information (not mapped to scenes).
        """
        # Try extraction model first if enabled
        extraction_service = self._get_extraction_service()
        if extraction_service:
            try:
                logger.info(f"Using extraction model for batch NPC extraction (user {self.user_id})")
                npc_data = await extraction_service.extract_npcs_batch(
                    batch_content=batch_content,
                    explicit_character_names=explicit_character_names
                )
                
                # Validate NPCs
                raw_npcs = npc_data.get('npcs', []) if npc_data else []
                logger.info(f"[NPC-EXTRACT-BATCH] Raw NPCs from extraction model: {[n.get('name') for n in raw_npcs]}")
                validated_npcs = self._validate_npcs(raw_npcs, explicit_name_parts=explicit_name_parts)
                logger.info(f"[NPC-EXTRACT-BATCH] Validated NPCs: {[n.get('name') for n in validated_npcs]}")
                if validated_npcs:
                    logger.info(f"Extraction model successfully extracted {len(validated_npcs)} NPCs from batch")
                    return {'npcs': validated_npcs}
                else:
                    logger.warning("Extraction model returned no valid NPCs from batch, falling back to main LLM")
            except Exception as e:
                logger.warning(f"Extraction model batch extraction failed: {e}, falling back to main LLM")
                # Continue to fallback
        
        # Fallback to main LLM
        fallback_enabled = self.user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
        if not fallback_enabled and extraction_service:
            logger.warning("Extraction model failed and fallback disabled, returning empty results")
            return {'npcs': []}
        
        try:
            logger.info(f"Using main LLM for batch NPC extraction (user {self.user_id})")
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Analyze these story scenes and extract ALL named entities that are NOT in the explicit character list.

{batch_content}

Explicit Characters (already tracked): {explicit_names_str}

For each entity, classify as either:
- CHARACTER: Sentient beings with agency (humans, aliens, robots, sentient animals, named individuals)
- ENTITY: Non-character entities (locations, objects, organizations, projects, groups, forces, concepts)

For each extracted entity, identify:
- Name (exact name as mentioned)
- Entity type (CHARACTER or ENTITY)
- Mention count (total mentions across all scenes)
- Has dialogue (true/false - has dialogue in any scene)
- Has actions (true/false - performs actions in any scene)
- Has relationships (true/false - interacts with other characters)
- Context snippets (array of 2-3 short text snippets mentioning this entity from any scene)
- Properties:
  - role: Their role in the story
  - description: A one-sentence description based on what's shown in the scenes

Return ONLY valid JSON in this exact format:
{{
  "npcs": [
    {{
      "name": "Entity name",
      "entity_type": "CHARACTER",
      "mention_count": 3,
      "has_dialogue": true,
      "has_actions": true,
      "has_relationships": true,
      "context_snippets": ["snippet 1", "snippet 2"],
      "properties": {{
        "role": "role description",
        "description": "One-sentence description of the entity"
      }}
    }}
  ]
}}

If no entities found, return {{"npcs": []}}. Return ONLY the JSON, no other text."""
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt="You are an expert at analyzing narrative text and extracting named entities. Classify each entity as CHARACTER or ENTITY and provide descriptions.",
                max_tokens=settings.service_defaults.get('extraction_service', {}).get('character_assistant_max_tokens', 3000)
            )
            
            logger.warning(f"RAW LLM RESPONSE - NPC TRACKING BATCH:\n{response}")
            
            # Clean and parse JSON response
            response_clean = clean_llm_json(response.strip())
            
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            npc_data = json.loads(response_clean)
            return npc_data
            
        except Exception as e:
            logger.error(f"Main LLM batch NPC extraction failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def extract_npcs_from_scene(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        scene_content: str,
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Extract NPCs from a scene and store mentions.
        
        Args:
            db: Database session
            story_id: Story ID
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            scene_content: Scene content text
            branch_id: Optional branch ID for filtering
            
        Returns:
            Dictionary with extraction results
        """
        results = {
            "npcs_found": 0,
            "npcs_tracked": 0,
            "extraction_successful": False
        }
        
        # Get active branch if not specified
        if branch_id is None:
            from ..models import StoryBranch
            from sqlalchemy import and_
            active_branch = db.query(StoryBranch).filter(
                and_(
                    StoryBranch.story_id == story_id,
                    StoryBranch.is_active == True
                )
            ).first()
            branch_id = active_branch.id if active_branch else None
        
        try:
            # Get list of explicit characters in the story (filtered by branch)
            char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
            if branch_id:
                char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
            story_characters = char_query.all()
            
            explicit_character_names = set()
            explicit_name_parts = set()  # For partial matching
            for sc in story_characters:
                character = db.query(Character).filter(Character.id == sc.character_id).first()
                if character:
                    name_lower = character.name.lower()
                    explicit_character_names.add(name_lower)
                    for part in name_lower.split():
                        if len(part) > 2:
                            explicit_name_parts.add(part)

            # Extract NPCs using LLM
            npc_data = await self._extract_npcs_with_llm(
                scene_content,
                scene_sequence,
                list(explicit_character_names),
                explicit_name_parts=explicit_name_parts
            )
            
            if not npc_data or "npcs" not in npc_data:
                logger.warning(f"No NPCs extracted from scene {scene_id}")
                return results
            
            results["npcs_found"] = len(npc_data["npcs"])
            
            # Verify scene exists before processing (prevents foreign key violations)
            scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
            if not scene_exists:
                logger.warning(f"Scene {scene_id} doesn't exist, cannot create NPC mentions")
                return results
            
            # Store mentions and update tracking
            for npc in npc_data["npcs"]:
                npc_name = npc.get("name", "").strip()
                if not npc_name:
                    continue

                # Convert string booleans to actual booleans (LLM sometimes returns 'true'/'false' as strings)
                def to_bool(value):
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.lower() in ('true', '1', 'yes')
                    return bool(value)
                
                # Store mention with IntegrityError handling
                try:
                    mention = NPCMention(
                        story_id=story_id,
                        branch_id=branch_id,
                        scene_id=scene_id,
                        character_name=npc_name,
                        sequence_number=scene_sequence,
                        mention_count=npc.get("mention_count", 1),
                        has_dialogue=to_bool(npc.get("has_dialogue", False)),
                        has_actions=to_bool(npc.get("has_actions", False)),
                        has_relationships=to_bool(npc.get("has_relationships", False)),
                        context_snippets=npc.get("context_snippets", []),
                        extracted_properties=npc.get("properties", {})
                    )
                    db.add(mention)
                    db.flush()  # Flush to catch constraint violations immediately
                    
                    # Update or create tracking record
                    await self._update_npc_tracking(
                        db, story_id, npc_name, scene_sequence, npc, branch_id=branch_id
                    )
                    
                    results["npcs_tracked"] += 1
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "foreign key" in error_msg and "scene_id" in error_msg:
                        logger.warning(f"Scene {scene_id} was deleted during extraction, stopping NPC extraction")
                        break  # Stop processing NPCs for this scene
                    elif "duplicate key" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"NPC mention already exists (race condition), skipping: {npc_name} in scene {scene_id}")
                        continue
                    else:
                        # Re-raise if it's a different integrity error
                        raise
            
            # Create snapshot after all NPCs for this scene are processed
            # Pass chapter_id for chapter-aware NPC tiering
            scene_chapter_id = scene_exists.chapter_id if scene_exists else None
            self._create_npc_tracking_snapshot(db, story_id, scene_id, scene_sequence, branch_id=branch_id, chapter_id=scene_chapter_id)

            db.commit()
            results["extraction_successful"] = True
            logger.info(f"Extracted {results['npcs_tracked']} NPCs from scene {scene_id}")
            
        except Exception as e:
            logger.error(f"Failed to extract NPCs from scene {scene_id}: {e}")
            db.rollback()
        
        return results
    
    async def _extract_npcs_with_llm(
        self,
        scene_content: str,
        scene_sequence: int,
        explicit_character_names: List[str],
        explicit_name_parts: Optional[set] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract NPCs from a scene.
        Tries extraction model first, falls back to main LLM if enabled.

        Returns JSON with NPC information.
        """
        # Try extraction model first if enabled
        extraction_service = self._get_extraction_service()
        if extraction_service:
            try:
                logger.info(f"Using extraction model for NPC extraction (user {self.user_id})")
                npc_data = await extraction_service.extract_npcs(
                    scene_content=scene_content,
                    scene_sequence=scene_sequence,
                    explicit_character_names=explicit_character_names
                )
                
                # Validate NPCs
                validated_npcs = self._validate_npcs(npc_data.get('npcs', []) if npc_data else [], explicit_name_parts=explicit_name_parts)
                if validated_npcs:
                    logger.info(f"Extraction model successfully extracted {len(validated_npcs)} NPCs")
                    return {'npcs': validated_npcs}
                else:
                    logger.warning("Extraction model returned no valid NPCs, falling back to main LLM")
            except Exception as e:
                logger.warning(f"Extraction model failed: {e}, falling back to main LLM")
                # Continue to fallback
        
        # Fallback to main LLM
        fallback_enabled = self.user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
        if not fallback_enabled and extraction_service:
            logger.warning("Extraction model failed and fallback disabled, returning empty results")
            return {'npcs': []}
        
        try:
            logger.info(f"Using main LLM for NPC extraction (user {self.user_id})")
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Analyze this story scene and extract ALL named entities that are NOT in the explicit character list.

Scene (Sequence #{scene_sequence}):
{scene_content}

Explicit Characters (already tracked): {explicit_names_str}

For each entity, classify as either:
- CHARACTER: Sentient beings with agency (humans, aliens, robots, sentient animals, named individuals)
- ENTITY: Non-character entities (locations, objects, organizations, projects, groups, forces, concepts)

For each extracted entity, identify:
- Name (exact name as mentioned)
- Entity type (CHARACTER or ENTITY)
- Mention count (how many times mentioned in this scene)
- Has dialogue (true/false)
- Has actions (true/false - performs actions in scene)
- Has relationships (true/false - interacts with other characters)
- Context snippets (array of 2-3 short text snippets mentioning this entity)
- Properties:
  - role: Their role in the story
  - description: A one-sentence description based on what's shown in the scene

Return ONLY valid JSON in this exact format:
{{
  "npcs": [
    {{
      "name": "Entity name",
      "entity_type": "CHARACTER",
      "mention_count": 3,
      "has_dialogue": true,
      "has_actions": true,
      "has_relationships": true,
      "context_snippets": ["snippet 1", "snippet 2"],
      "properties": {{
        "role": "role description",
        "description": "One-sentence description of the entity"
      }}
    }}
  ]
}}

If no entities found, return {{"npcs": []}}. Return ONLY the JSON, no other text."""
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt="You are a precise story analysis assistant. Extract NPCs and named entities from scenes. Classify each as CHARACTER or ENTITY and provide descriptions. Return only valid JSON.",
                max_tokens=settings.service_defaults.get('extraction_service', {}).get('character_assistant_max_tokens', 2000)
            )
            
            logger.warning(f"RAW LLM RESPONSE - NPC TRACKING:\n{response}")
            
            # Clean and parse JSON
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            response_clean = clean_llm_json(response_clean)
            
            npc_data = json.loads(response_clean)
            return npc_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Cleaned response was: {response_clean}")
            return None
        except Exception as e:
            logger.error(f"Main LLM NPC extraction failed: {e}")
            return None
    
    def _validate_npcs(self, npcs: List[Dict[str, Any]], explicit_name_parts: Optional[set] = None) -> List[Dict[str, Any]]:
        """
        Validate and normalize NPC dictionaries.

        Args:
            npcs: List of raw NPC dictionaries
            explicit_name_parts: Set of lowercase name parts from explicit story characters
                                 (e.g. {"alice", "smith", "bob"})

        Returns:
            List of validated NPC dictionaries
        """
        import re

        if explicit_name_parts is None:
            explicit_name_parts = set()

        # Patterns for generic/plural entities that should be excluded
        GENERIC_PATTERNS = [
            r'^(guards?|soldiers?|troops?|units?|forces?|creatures?|beings?|figures?|entities?|shadows?|lights?|voices?|sounds?|noises?|bolts?|projectiles?)$',  # Just "guards", "shadows", "bolts"
            r'^(the|a|an)\s+(guard|soldier|troop|unit|force|creature|being|figure|entity|shadow|light|voice|sound|noise|bolt|projectile)s?$',  # "the creature", "a guard"
            r'^[a-z]+\s+(guards?|soldiers?|troops?|units?|forces?|creatures?|beings?|figures?|entities?|shadows?|lights?|voices?|sounds?|noises?|bolts?)$',  # "alien creatures", "plasma bolts"
            r'^(plasma|energy|laser|plasma)\s+(bolts?|projectiles?|beams?)$',  # "plasma bolts", "energy beams"
            r'^(elongated|strange|alien|mysterious)\s+(figures?|creatures?|beings?|entities?)$',  # "elongated figures", "strange creatures"
        ]
        
        # Specific generic terms to always exclude
        GENERIC_TERMS = {
            'guards', 'guard', 'soldiers', 'soldier', 'troops', 'troop', 'units', 'unit',
            'forces', 'force', 'creatures', 'creature', 'beings', 'being', 'figures', 'figure',
            'entities', 'entity', 'shadows', 'shadow', 'lights', 'light', 'voices', 'voice',
            'sounds', 'sound', 'noises', 'noise', 'bolts', 'bolt', 'projectiles', 'projectile',
            'plasma bolts', 'plasma bolt', 'elongated figures', 'elongated figure',
        }
        
        validated = []
        for npc in npcs:
            try:
                name = npc.get('name', '').strip()
                if not name:
                    logger.warning(f"Skipping NPC with missing name: {npc}")
                    continue
                
                # Get entity_type and validate it
                entity_type = npc.get('entity_type', 'CHARACTER')
                if entity_type and isinstance(entity_type, str):
                    entity_type = entity_type.upper()
                else:
                    entity_type = 'CHARACTER'

                # Reject non-CHARACTER entities (objects, locations, etc.)
                if entity_type != 'CHARACTER':
                    logger.debug(f"Filtered out non-CHARACTER entity: {name} (type={entity_type})")
                    continue

                name_lower = name.lower()

                # Filter out explicit story characters (partial name matching)
                if explicit_name_parts:
                    npc_parts = [p for p in name_lower.split() if len(p) > 2]
                    if name_lower in explicit_name_parts or any(p in explicit_name_parts for p in npc_parts):
                        logger.debug(f"Filtered out explicit character match: {name}")
                        continue

                # Require at least one capitalized word (proper noun heuristic).
                # Catches descriptors like "children", "wife", "old man" while
                # allowing proper names like "Mrs. Johnson", "Old Man Jenkins".
                if not any(word[0].isupper() for word in name.split() if word and word[0].isalpha()):
                    logger.debug(f"Filtered out non-proper-noun name: {name}")
                    continue

                # Filter out generic/plural entities
                # Check against generic terms
                if name_lower in GENERIC_TERMS:
                    logger.debug(f"Filtered out generic term: {name}")
                    continue
                
                # Check against patterns
                is_generic = False
                for pattern in GENERIC_PATTERNS:
                    if re.match(pattern, name_lower):
                        logger.debug(f"Filtered out generic entity matching pattern '{pattern}': {name}")
                        is_generic = True
                        break
                
                if is_generic:
                    continue
                
                # For CHARACTER type, ensure it's not a plural (characters should be singular)
                if entity_type == 'CHARACTER':
                    # Check if it's a plural noun (simple heuristic)
                    if name_lower.endswith('s') and len(name_lower) > 3 and not name[0].isupper():
                        # Lowercase plural - likely generic
                        logger.debug(f"Filtered out likely plural character name: {name}")
                        continue
                
                # Normalize fields
                mention_count = npc.get('mention_count', 0)
                try:
                    mention_count = int(mention_count)
                    mention_count = max(mention_count, 0)
                except (ValueError, TypeError):
                    mention_count = 1
                
                has_dialogue = bool(npc.get('has_dialogue', False))
                has_actions = bool(npc.get('has_actions', False))
                has_relationships = bool(npc.get('has_relationships', False))
                
                context_snippets = npc.get('context_snippets', [])
                if not isinstance(context_snippets, list):
                    context_snippets = []
                
                properties = npc.get('properties', {})
                if not isinstance(properties, dict):
                    properties = {}
                
                validated.append({
                    'name': name,
                    'entity_type': entity_type,  # Include entity_type in validated data
                    'mention_count': mention_count,
                    'has_dialogue': has_dialogue,
                    'has_actions': has_actions,
                    'has_relationships': has_relationships,
                    'context_snippets': context_snippets,
                    'properties': properties
                })
                
            except Exception as e:
                logger.warning(f"Failed to validate NPC: {npc}, error: {e}")
                continue
        
        return validated
    
    def _find_canonical_name(
        self,
        db: Session,
        story_id: int,
        character_name: str,
        branch_id: int = None
    ) -> Optional[str]:
        """
        Find canonical name for a character (handles duplicates like 'Reynolds' vs 'Sheriff Reynolds', 'Vortex' vs 'vortex')
        
        Returns the canonical name if a match is found, None otherwise.
        """
        from difflib import SequenceMatcher
        
        # Get all existing NPCs for this story (filtered by branch)
        npc_query = db.query(NPCTracking).filter(NPCTracking.story_id == story_id)
        if branch_id:
            npc_query = npc_query.filter(NPCTracking.branch_id == branch_id)
        existing_npcs = npc_query.all()
        
        name_lower = character_name.lower().strip()
        
        # First check for exact case-insensitive match (e.g., "Vortex" vs "vortex")
        for npc in existing_npcs:
            existing_lower = npc.character_name.lower().strip()
            if name_lower == existing_lower and character_name != npc.character_name:
                # Case-insensitive duplicate - use the one with more mentions, or the capitalized version
                if npc.total_mentions > 0:
                    return npc.character_name
                elif character_name[0].isupper() and npc.character_name[0].islower():
                    return character_name  # Prefer capitalized version
                else:
                    return npc.character_name
        
        # Check for exact substring matches
        for npc in existing_npcs:
            existing_lower = npc.character_name.lower().strip()
            
            # If one name is a substring of the other, use the longer one
            if name_lower in existing_lower and name_lower != existing_lower:
                return npc.character_name  # Use existing (longer) name
            elif existing_lower in name_lower and name_lower != existing_lower:
                return character_name  # Use longer new name
        
        # Check for high similarity (>0.8)
        for npc in existing_npcs:
            existing_lower = npc.character_name.lower().strip()
            similarity = SequenceMatcher(None, name_lower, existing_lower).ratio()
            if similarity > 0.8 and name_lower != existing_lower:
                # Use the name with more mentions (more established)
                if npc.total_mentions > 5:
                    return npc.character_name
                else:
                    return character_name
        
        return None
    
    async def _update_npc_tracking(
        self,
        db: Session,
        story_id: int,
        character_name: str,
        scene_sequence: int,
        npc_data: Dict[str, Any],
        branch_id: int = None
    ):
        """Update or create NPC tracking record with deduplication and entity type"""
        try:
            # Check for duplicates
            canonical_name = self._find_canonical_name(db, story_id, character_name, branch_id=branch_id)
            if canonical_name and canonical_name != character_name:
                logger.info(f"Merging '{character_name}' → '{canonical_name}'")
                character_name = canonical_name
            
            # Get or create tracking record (filtered by branch)
            track_query = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.character_name == character_name
            )
            if branch_id:
                track_query = track_query.filter(NPCTracking.branch_id == branch_id)
            tracking = track_query.first()
            
            if not tracking:
                # Get entity_type from npc_data, default to CHARACTER
                entity_type = npc_data.get("entity_type", "CHARACTER")
                if entity_type and isinstance(entity_type, str):
                    entity_type = entity_type.upper()
                else:
                    entity_type = "CHARACTER"
                
                tracking = NPCTracking(
                    story_id=story_id,
                    branch_id=branch_id,
                    character_name=character_name,
                    entity_type=entity_type,  # Store entity type
                    first_appearance_scene=scene_sequence,
                    last_appearance_scene=scene_sequence,
                    total_mentions=0,
                    scene_count=0,
                    has_dialogue_count=0,
                    has_actions_count=0
                )
                db.add(tracking)
            else:
                # Update entity_type if it's different (shouldn't happen often, but handle it)
                entity_type = npc_data.get("entity_type", "CHARACTER")
                if entity_type and isinstance(entity_type, str):
                    entity_type = entity_type.upper()
                    if tracking.entity_type != entity_type:
                        logger.info(f"Updating entity_type for '{character_name}': {tracking.entity_type} → {entity_type}")
                        tracking.entity_type = entity_type
            
            # Initialize None values to 0 (safety check for existing records)
            if tracking.total_mentions is None:
                tracking.total_mentions = 0
            if tracking.has_dialogue_count is None:
                tracking.has_dialogue_count = 0
            if tracking.has_actions_count is None:
                tracking.has_actions_count = 0
            if tracking.scene_count is None:
                tracking.scene_count = 0
            
            # Update metrics
            tracking.total_mentions += npc_data.get("mention_count", 1)
            tracking.last_appearance_scene = scene_sequence
            
            # Convert string booleans to actual booleans
            def to_bool(value):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes')
                return bool(value)
            
            if to_bool(npc_data.get("has_dialogue", False)):
                tracking.has_dialogue_count += 1
            
            if to_bool(npc_data.get("has_actions", False)):
                tracking.has_actions_count += 1
            
            # Recalculate importance score
            await self._calculate_importance_score(db, story_id, tracking)
            
            # Check if threshold crossed
            if tracking.importance_score >= self.importance_threshold and not tracking.crossed_threshold:
                tracking.crossed_threshold = True
                logger.info(f"NPC '{character_name}' crossed importance threshold (score: {tracking.importance_score:.2f})")
                
                # Extract full profile if enabled
                if settings.npc_auto_extract_profile:
                    await self._extract_npc_profile(db, story_id, character_name)
            
            tracking.last_calculated = datetime.now()
            db.commit()

        except Exception as e:
            logger.error(f"Failed to update NPC tracking: {e}")
            db.rollback()

    async def track_npc(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        npc_data: Dict[str, Any],
        branch_id: int = None
    ) -> bool:
        """
        Track a single NPC from extraction results.
        Creates NPCMention and updates tracking record.

        Args:
            db: Database session
            story_id: Story ID
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            npc_data: NPC data dict with name, mention_count, has_dialogue, has_actions, etc.
            branch_id: Branch ID for branch isolation

        Returns:
            True if NPC was tracked successfully, False otherwise
        """
        try:
            npc_name = npc_data.get('name', '').strip()
            if not npc_name:
                return False

            # Convert string booleans to actual booleans
            def to_bool(value):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes')
                return bool(value)

            mention_count = npc_data.get('mention_count', 1)
            has_dialogue = to_bool(npc_data.get('has_dialogue', False))
            has_actions = to_bool(npc_data.get('has_actions', False))
            has_relationships = to_bool(npc_data.get('has_relationships', False))

            # Only track if significant enough
            if mention_count < 2 and not has_dialogue and not has_actions:
                return False

            # Verify scene exists
            scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
            if not scene_exists:
                logger.warning(f"Scene {scene_id} doesn't exist, skipping NPC mention for {npc_name}")
                return False

            # Create NPCMention with IntegrityError handling
            try:
                mention = NPCMention(
                    story_id=story_id,
                    branch_id=branch_id,
                    scene_id=scene_id,
                    character_name=npc_name,
                    sequence_number=scene_sequence,
                    mention_count=mention_count,
                    has_dialogue=has_dialogue,
                    has_actions=has_actions,
                    has_relationships=has_relationships,
                    context_snippets=npc_data.get('context_snippets', []),
                    extracted_properties=npc_data.get('properties', {})
                )
                db.add(mention)
                db.flush()

                # Update tracking record
                await self._update_npc_tracking(
                    db, story_id, npc_name, scene_sequence, npc_data,
                    branch_id=branch_id
                )
                return True

            except IntegrityError as ie:
                db.rollback()
                error_msg = str(ie).lower()
                if "foreign key" in error_msg and "scene_id" in error_msg:
                    logger.warning(f"Scene {scene_id} was deleted during extraction, skipping NPC mention for {npc_name}")
                elif "duplicate key" in error_msg or "unique constraint" in error_msg:
                    logger.debug(f"NPC mention already exists (race condition), skipping: {npc_name} in scene {scene_id}")
                else:
                    raise
                return False

        except Exception as e:
            logger.error(f"Failed to track NPC {npc_data.get('name', 'unknown')}: {e}")
            return False

    def _create_npc_tracking_snapshot(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        branch_id: int = None,
        chapter_id: int = None
    ):
        """
        Create a snapshot of all NPC tracking data for a scene.
        This enables fast rollback on scene deletion without recalculation.

        Also pre-calculates tiered NPC lists for context building, ensuring
        cache stability - all scenes until the next extraction use the same lists.

        Args:
            db: Database session
            story_id: Story ID
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            branch_id: Optional branch ID for filtering
            chapter_id: Optional chapter ID for chapter-aware tiering
        """
        try:
            from sqlalchemy import desc

            # Get all current NPC tracking records for this story (filtered by branch)
            npc_query = db.query(NPCTracking).filter(NPCTracking.story_id == story_id)
            if branch_id:
                npc_query = npc_query.filter(NPCTracking.branch_id == branch_id)
            all_npcs = npc_query.order_by(desc(NPCTracking.importance_score)).all()

            # Build raw snapshot data (for rollback)
            snapshot_data = {}
            for npc in all_npcs:
                snapshot_data[npc.character_name] = {
                    "total_mentions": npc.total_mentions or 0,
                    "scene_count": npc.scene_count or 0,
                    "importance_score": npc.importance_score or 0.0,
                    "frequency_score": npc.frequency_score or 0.0,
                    "significance_score": npc.significance_score or 0.0,
                    "first_appearance_scene": npc.first_appearance_scene,
                    "last_appearance_scene": npc.last_appearance_scene,
                    "has_dialogue_count": npc.has_dialogue_count or 0,
                    "has_actions_count": npc.has_actions_count or 0,
                    "crossed_threshold": npc.crossed_threshold or False,
                    "entity_type": npc.entity_type or "CHARACTER",
                    "user_prompted": npc.user_prompted or False,
                    "profile_extracted": npc.profile_extracted or False,
                    "converted_to_character": npc.converted_to_character or False,
                    "extracted_profile": npc.extracted_profile or {}
                }

            # === PRE-CALCULATE TIERED NPC LISTS FOR CONTEXT ===
            # This ensures all scenes until the next extraction use the same NPC lists
            active_window = self.user_settings.get("npc_active_recency_window", settings.npc_active_recency_window)
            inactive_window = self.user_settings.get("npc_inactive_recency_window", settings.npc_inactive_recency_window)
            use_chapter_awareness = self.user_settings.get("npc_use_chapter_awareness", settings.npc_use_chapter_awareness)
            limit = 10  # Max NPCs per tier

            # Get NPCs in current chapter (if chapter awareness is enabled)
            chapter_npc_names = set()
            if use_chapter_awareness and chapter_id:
                chapter_scenes = db.query(Scene).filter(
                    Scene.chapter_id == chapter_id,
                    Scene.is_deleted == False
                ).all()
                chapter_scene_ids = [s.id for s in chapter_scenes]
                if chapter_scene_ids:
                    chapter_mentions = db.query(NPCMention.character_name).filter(
                        NPCMention.scene_id.in_(chapter_scene_ids)
                    ).distinct().all()
                    chapter_npc_names = {m[0].lower() for m in chapter_mentions}

            # Calculate tiered lists
            active_npcs_for_context = []
            inactive_npcs_for_context = []

            for npc in all_npcs:
                # Skip NPCs that haven't crossed threshold or are converted to characters
                if not npc.crossed_threshold or npc.converted_to_character:
                    continue

                # Skip non-CHARACTER entities (objects, locations, etc.)
                if npc.entity_type and npc.entity_type.upper() != 'CHARACTER':
                    continue

                last_appearance = npc.last_appearance_scene or 0
                scenes_since_appearance = scene_sequence - last_appearance
                in_current_chapter = npc.character_name.lower() in chapter_npc_names

                # Determine tier
                is_active = scenes_since_appearance <= active_window or in_current_chapter
                is_inactive = not is_active and scenes_since_appearance <= inactive_window

                if is_active and len(active_npcs_for_context) < limit:
                    profile = npc.extracted_profile or {}
                    active_npcs_for_context.append({
                        "name": npc.character_name,
                        "role": profile.get("role", "NPC"),
                        "description": profile.get("description", ""),
                        "personality": ", ".join(profile.get("personality", [])),
                        "background": profile.get("background", ""),
                        "goals": profile.get("goals", ""),
                        "relationships": profile.get("relationships", {})
                    })
                elif is_inactive and len(inactive_npcs_for_context) < limit:
                    profile = npc.extracted_profile or {}
                    inactive_npcs_for_context.append({
                        "name": npc.character_name,
                        "role": profile.get("role", "NPC")
                    })

            # Store pre-calculated lists in snapshot_data with special keys
            snapshot_data["_active_npcs_for_context"] = active_npcs_for_context
            snapshot_data["_inactive_npcs_for_context"] = inactive_npcs_for_context
            snapshot_data["_snapshot_scene_sequence"] = scene_sequence
            snapshot_data["_chapter_id"] = chapter_id

            # Delete existing snapshot for this scene if it exists (in case of regeneration)
            existing_query = db.query(NPCTrackingSnapshot).filter(
                NPCTrackingSnapshot.scene_id == scene_id
            )
            if branch_id is not None:
                existing_query = existing_query.filter(NPCTrackingSnapshot.branch_id == branch_id)
            existing_snapshot = existing_query.first()
            if existing_snapshot:
                db.delete(existing_snapshot)

            # Create new snapshot
            snapshot = NPCTrackingSnapshot(
                scene_id=scene_id,
                scene_sequence=scene_sequence,
                story_id=story_id,
                branch_id=branch_id,
                snapshot_data=snapshot_data
            )
            db.add(snapshot)
            db.commit()

            logger.info(f"[NPC SNAPSHOT] Created snapshot for scene {scene_id} (seq {scene_sequence}): "
                       f"{len(active_npcs_for_context)} active, {len(inactive_npcs_for_context)} inactive NPCs for context")

        except Exception as e:
            logger.error(f"Failed to create NPC tracking snapshot for scene {scene_id}: {e}")
            db.rollback()
    
    async def _calculate_importance_score(
        self,
        db: Session,
        story_id: int,
        tracking: NPCTracking,
        apply_recency_factor: bool = True
    ):
        """
        Calculate importance score (0-100 scale):
        - More mentions = higher score
        - More scenes = higher score
        - Dialogue/actions boost score
        - Optional recency factor that decays score for NPCs not seen recently
        
        Formula: 
        - Base score (0-70): mention count + scene coverage
        - Significance bonus (0-30): dialogue + actions
        - Recency factor (optional): multiplier based on scenes since last appearance
        
        Args:
            db: Database session
            story_id: Story ID
            tracking: NPCTracking record to update
            apply_recency_factor: If True, apply recency decay to the score
        """
        try:
            import math
            from sqlalchemy import desc

            # Get branch_id from tracking record for filtering
            branch_id = tracking.branch_id

            # Get total scenes in story (excluding deleted), filtered by branch
            scene_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            )
            if branch_id is not None:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            total_scenes = scene_query.count()

            if total_scenes == 0:
                tracking.importance_score = 0.0
                tracking.frequency_score = 0.0
                tracking.significance_score = 0.0
                return

            # Safely handle None values
            total_mentions = tracking.total_mentions or 0
            scene_count = tracking.scene_count or 0
            has_dialogue_count = tracking.has_dialogue_count or 0
            has_actions_count = tracking.has_actions_count or 0

            # Update scene count from mentions (filtered by branch)
            mention_query = db.query(NPCMention.scene_id).filter(
                NPCMention.story_id == story_id,
                NPCMention.character_name == tracking.character_name
            )
            if branch_id is not None:
                mention_query = mention_query.filter(NPCMention.branch_id == branch_id)
            scene_count_query = mention_query.distinct().count()
            tracking.scene_count = scene_count_query
            scene_count = scene_count_query
            
            # FREQUENCY SCORE (0-70): Mentions + Scene Coverage
            # - Mention score: logarithmic scale (1-10 mentions=10pts, 100 mentions=40pts, 300+=50pts)
            # - Scene score: linear (percentage of scenes × 20)
            if total_mentions > 0:
                mention_score = min(10 + (math.log10(total_mentions) * 20), 50)
            else:
                mention_score = 0
            
            scene_percentage = scene_count / total_scenes
            scene_score = scene_percentage * 20
            
            frequency_score = mention_score + scene_score  # Max 70
            tracking.frequency_score = frequency_score
            
            # SIGNIFICANCE SCORE (0-30): Dialogue + Actions
            significance_score = 0.0
            
            # Has dialogue in scenes (0-15 points)
            if has_dialogue_count > 0:
                dialogue_score = min(has_dialogue_count * 3, 15)
                significance_score += dialogue_score
            
            # Has actions in scenes (0-15 points)
            if has_actions_count > 0:
                action_score = min(has_actions_count * 3, 15)
                significance_score += action_score
            
            tracking.significance_score = significance_score
            
            # BASE COMBINED SCORE (0-100)
            base_score = min(frequency_score + significance_score, 100.0)
            
            # RECENCY FACTOR (optional): Apply decay for NPCs not seen recently
            # This makes NPCs naturally "fade" if they haven't appeared, but preserves
            # their base importance so they can quickly regain prominence if they reappear
            if apply_recency_factor and tracking.last_appearance_scene is not None:
                # Get current scene sequence
                latest_scene = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False
                ).order_by(desc(Scene.sequence_number)).first()
                
                if latest_scene:
                    current_scene = latest_scene.sequence_number
                    scenes_since_appearance = current_scene - (tracking.last_appearance_scene or 0)
                    
                    # Use inactive_recency_window as the decay window
                    # NPCs within this window get full score, beyond it they decay
                    decay_window = self.user_settings.get("npc_inactive_recency_window", 
                                                          settings.npc_inactive_recency_window)
                    
                    if scenes_since_appearance <= decay_window:
                        # Within window - no decay
                        recency_factor = 1.0
                    else:
                        # Beyond window - apply gradual decay
                        # Score decays to minimum of 30% over additional decay_window scenes
                        excess_scenes = scenes_since_appearance - decay_window
                        decay_rate = min(excess_scenes / decay_window, 1.0)  # 0 to 1
                        recency_factor = max(0.3, 1.0 - (decay_rate * 0.7))  # Decays from 1.0 to 0.3
                    
                    # Apply recency factor
                    tracking.importance_score = base_score * recency_factor
                    
                    if recency_factor < 1.0:
                        logger.debug(f"NPC '{tracking.character_name}': base_score={base_score:.1f}, "
                                   f"recency_factor={recency_factor:.2f}, final_score={tracking.importance_score:.1f}")
                else:
                    tracking.importance_score = base_score
            else:
                tracking.importance_score = base_score
            
        except Exception as e:
            logger.error(f"Failed to calculate importance score: {e}")
            tracking.importance_score = 0.0
            tracking.frequency_score = 0.0
            tracking.significance_score = 0.0
    
    async def recalculate_all_scores(
        self,
        db: Session,
        story_id: int,
        branch_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Recalculate importance scores for all NPCs in a story (optionally filtered by branch)."""
        try:
            npcs_query = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id
            )
            if branch_id is not None:
                npcs_query = npcs_query.filter(NPCTracking.branch_id == branch_id)
            npcs = npcs_query.all()

            recalculated_count = 0
            for npc in npcs:
                await self._calculate_importance_score(db, story_id, npc)
                recalculated_count += 1

            db.commit()

            logger.info(f"Recalculated {recalculated_count} NPC scores for story {story_id} (branch {branch_id})")
            
            return {
                "success": True,
                "npcs_recalculated": recalculated_count
            }
        except Exception as e:
            logger.error(f"Failed to recalculate scores: {e}")
            db.rollback()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _extract_npc_profile(
        self,
        db: Session,
        story_id: int,
        character_name: str,
        branch_id: Optional[int] = None
    ):
        """
        Extract full character profile for an NPC using LLM analysis of all scenes.
        """
        try:
            from ..models import StoryFlow
            from ..models.scene_variant import SceneVariant

            # Find scenes containing this NPC by searching active variant content directly.
            # npc_mentions is often incomplete, so text search is more reliable.
            scene_query = db.query(Scene.sequence_number, SceneVariant.content).join(
                StoryFlow, StoryFlow.scene_id == Scene.id
            ).join(
                SceneVariant, SceneVariant.id == StoryFlow.scene_variant_id
            ).filter(
                Scene.story_id == story_id,
                Scene.is_deleted == False,
                StoryFlow.is_active == True,
                SceneVariant.content.ilike(f'%{character_name}%')
            )
            if branch_id is not None:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scene_rows = scene_query.order_by(Scene.sequence_number).all()

            if not scene_rows:
                logger.warning(f"No scene content found for NPC '{character_name}', cannot extract profile")
                return

            # Cap at 15 scenes to keep prompt reasonable — pick evenly spaced ones
            if len(scene_rows) > 15:
                step = len(scene_rows) / 15
                scene_rows = [scene_rows[int(i * step)] for i in range(15)]

            scenes_data = [{"sequence": seq, "content": content} for seq, content in scene_rows]
            
            # Build context for LLM
            scenes_text = "\n\n".join([
                f"Scene {s['sequence']}: {s['content']}"
                for s in scenes_data
            ])
            
            prompt = f"""Analyze all appearances of the character "{character_name}" across these scenes and extract a complete character profile.

Scenes where {character_name} appears:
{scenes_text}

Extract a comprehensive character profile including:
- Name (exact name)
- Role in the story (protagonist, antagonist, ally, mentor, etc.)
- Description (physical and personality description based on what's shown)
- Personality traits (array of traits inferred from actions/dialogue)
- Background (what can be inferred about their past/background)
- Goals (what they seem to want or be working toward)
- Relationships (object mapping character names to relationship descriptions)
- Appearance (physical description if mentioned)

Return ONLY valid JSON in this exact format:
{{
  "name": "{character_name}",
  "role": "role in story",
  "description": "comprehensive description",
  "personality": ["trait1", "trait2", "trait3"],
  "background": "background information",
  "goals": "character goals",
  "relationships": {{
    "OtherCharacter": "relationship description"
  }},
  "appearance": "physical description"
}}

Return ONLY the JSON, no other text."""
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt="You are an expert literary analyst. Extract comprehensive character profiles from story scenes. Return only valid JSON.",
                max_tokens=settings.service_defaults.get('extraction_service', {}).get('npc_tracking_max_tokens', 1500)
            )
            
            # Clean and parse JSON
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            response_clean = clean_llm_json(response_clean)
            
            profile = json.loads(response_clean)
            
            # Validate profile has meaningful content
            has_content = (
                profile.get("description") or 
                profile.get("personality") or 
                profile.get("background") or 
                profile.get("goals") or
                profile.get("appearance")
            )
            
            if not has_content:
                logger.warning(f"Profile extraction for '{character_name}' returned empty data, skipping storage")
                return
            
            # Update tracking record only if profile has content (filtered by branch)
            tracking_query = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.character_name == character_name
            )
            if branch_id is not None:
                tracking_query = tracking_query.filter(NPCTracking.branch_id == branch_id)
            tracking = tracking_query.first()

            if tracking:
                tracking.extracted_profile = profile
                tracking.profile_extracted = True
                db.commit()
                logger.info(f"Extracted profile for NPC '{character_name}' (branch {branch_id}) with content")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse NPC profile JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to extract NPC profile: {e}")
    
    def mark_npc_as_converted(
        self,
        db: Session,
        story_id: int,
        character_name: str,
        branch_id: Optional[int] = None
    ) -> bool:
        """
        Mark an NPC as converted to explicit character.

        Args:
            db: Database session
            story_id: Story ID
            character_name: Character name (case-insensitive match)
            branch_id: Optional branch ID for branch isolation

        Returns:
            True if NPC was found and marked, False otherwise
        """
        try:
            # Find NPC by name (case-insensitive), filtered by branch
            npc_query = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                func.lower(NPCTracking.character_name) == character_name.lower()
            )
            if branch_id is not None:
                npc_query = npc_query.filter(NPCTracking.branch_id == branch_id)
            npc = npc_query.first()

            if npc:
                npc.converted_to_character = True
                # Don't commit here - let the caller handle commit
                logger.info(f"Marked NPC '{character_name}' (branch {branch_id}) as converted to explicit character")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to mark NPC as converted: {e}")
            return False
    
    def get_npcs_as_suggestions(
        self,
        db: Session,
        story_id: int,
        min_importance: float = 0.0,
        entity_type: str = "CHARACTER",  # Filter by entity type
        branch_id: int = None
    ) -> List[Dict[str, Any]]:
        """
        Get NPCs formatted as character suggestions for discovery.
        
        Returns format compatible with CharacterAssistantService suggestions.
        Excludes NPCs that have been converted to explicit characters.
        
        Args:
            db: Database session
            story_id: Story ID
            min_importance: Minimum importance score to include (0.0 = all NPCs)
            entity_type: Filter by entity type ("CHARACTER" or "ENTITY"), defaults to "CHARACTER"
            branch_id: Optional branch ID for filtering
        """
        logger.info(f"[NPC-SUGGESTIONS] Getting suggestions: story_id={story_id}, branch_id={branch_id}, min_importance={min_importance}, entity_type={entity_type}")
        
        try:
            # Query with entity type filter (handle NULL values and missing column for backward compatibility)
            from sqlalchemy import or_
            
            # Build base query
            query = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.converted_to_character == False,  # Exclude converted NPCs
                NPCTracking.importance_score >= min_importance
            )
            
            # DEBUG: Count before branch filter
            count_before_branch = query.count()
            logger.info(f"[NPC-SUGGESTIONS] NPCs before branch filter: {count_before_branch}")
            
            # Filter by branch if specified
            if branch_id:
                query = query.filter(NPCTracking.branch_id == branch_id)
                count_after_branch = query.count()
                logger.info(f"[NPC-SUGGESTIONS] NPCs after branch filter (branch_id={branch_id}): {count_after_branch}")
            
            # Add entity_type filter if column exists in database
            # Check if column exists by inspecting the table
            try:
                from sqlalchemy import inspect
                inspector = inspect(db.bind)
                columns = [col['name'] for col in inspector.get_columns('npc_tracking')]
                
                if 'entity_type' in columns:
                    # Column exists, apply filter
                    if entity_type == "CHARACTER":
                        # Include CHARACTERs and NULL values (for backward compatibility)
                        query = query.filter(
                            or_(
                                NPCTracking.entity_type == entity_type,
                                NPCTracking.entity_type.is_(None)
                            )
                        )
                    else:
                        # For ENTITY type, only match exact type
                        query = query.filter(NPCTracking.entity_type == entity_type)
                else:
                    # Column doesn't exist yet (migration not run), skip entity_type filter
                    logger.debug("entity_type column not found in database, skipping filter (migration may not have run)")
            except Exception as e:
                # If inspection fails, skip entity_type filter (backward compatibility)
                logger.debug(f"Could not check for entity_type column, skipping filter: {e}")
                pass
            
            # Get all NPCs first
            npcs = query.order_by(NPCTracking.importance_score.desc()).all()

            # Filter out NPCs that match existing story_characters
            # Get existing story character names for this story/branch
            from ..models import StoryCharacter, Character
            existing_chars_query = db.query(Character.name).join(
                StoryCharacter, StoryCharacter.character_id == Character.id
            ).filter(StoryCharacter.story_id == story_id)
            if branch_id:
                existing_chars_query = existing_chars_query.filter(StoryCharacter.branch_id == branch_id)
            existing_char_names = {name.lower() for (name,) in existing_chars_query.all()}

            # Build a set of name variations for existing characters
            # e.g., "Alice Smith" -> {"alice smith", "alice", "smith", "mr. smith", "mr smith"}
            existing_name_parts = set()
            for name in existing_char_names:
                existing_name_parts.add(name)
                # Add individual words (first name, last name)
                for part in name.split():
                    if len(part) > 2:  # Skip very short parts like "a", "of"
                        existing_name_parts.add(part)
                        # Also add with common titles
                        existing_name_parts.add(f"mr. {part}")
                        existing_name_parts.add(f"mr {part}")
                        existing_name_parts.add(f"mrs. {part}")
                        existing_name_parts.add(f"mrs {part}")
                        existing_name_parts.add(f"ms. {part}")
                        existing_name_parts.add(f"ms {part}")
                        existing_name_parts.add(f"dr. {part}")
                        existing_name_parts.add(f"dr {part}")

            logger.info(f"[NPC-SUGGESTIONS] Existing character name parts to filter: {existing_name_parts}")

            # Filter out NPCs that match existing characters
            def matches_existing_character(npc_name: str) -> bool:
                npc_lower = npc_name.lower().strip()
                # Direct match
                if npc_lower in existing_name_parts:
                    return True
                # Check if any part of NPC name matches existing character parts
                # e.g., "Ali Malik" should match if "ali" exists
                npc_parts = npc_lower.split()
                for part in npc_parts:
                    if len(part) > 2 and part in existing_name_parts:
                        return True
                # Check if NPC name without title matches
                for title in ['mr. ', 'mr ', 'mrs. ', 'mrs ', 'ms. ', 'ms ', 'dr. ', 'dr ']:
                    if npc_lower.startswith(title):
                        without_title = npc_lower[len(title):]
                        if without_title in existing_name_parts:
                            return True
                        # Also check parts of the name without title
                        for part in without_title.split():
                            if len(part) > 2 and part in existing_name_parts:
                                return True
                return False

            npcs = [npc for npc in npcs if not matches_existing_character(npc.character_name)]
            logger.info(f"[NPC-SUGGESTIONS] NPCs after filtering existing characters: {len(npcs)}")

            # Filter out obvious non-character entities (objects, materials, locations)
            # These are commonly misclassified by the extraction model
            NON_CHARACTER_PATTERNS = {
                # Materials
                'marble', 'granite', 'wood', 'stone', 'tile', 'tiles', 'glass', 'metal',
                'calacatta', 'carrara', 'quartz', 'porcelain', 'ceramic',
                # Furniture/fixtures
                'countertop', 'counter', 'workbench', 'bench', 'table', 'chair', 'cabinet',
                'sink', 'faucet', 'island', 'shelf', 'shelves', 'drawer', 'door',
                # Construction/tools
                'compressor', 'drill', 'saw', 'hammer', 'equipment', 'tool', 'tools',
                'sheeting', 'plastic', 'pipe', 'pipes', 'wire', 'wires', 'cable',
                # Rooms/locations
                'sunroom', 'kitchen', 'bathroom', 'bedroom', 'living room', 'garage',
                'basement', 'attic', 'hallway', 'patio', 'deck', 'porch',
                # Food/drinks
                'coffee', 'tea', 'water', 'wine', 'beer', 'food', 'meal',
                # Nature/weather
                'sun', 'moon', 'rain', 'wind', 'sky', 'cloud', 'clouds', 'tree', 'trees',
                # Other objects
                'lighting', 'pendant', 'lamp', 'light', 'sample', 'samples',
                'traffic', 'car', 'cars', 'vehicle', 'vehicles', 'phone', 'computer',
                # Generic role-based descriptors (not actual names)
                'wife', 'husband', 'waiter', 'waitress', 'driver', 'stranger',
                'guard', 'soldier', 'servant', 'maid', 'butler', 'clerk',
            }

            def is_likely_object(npc_name: str) -> bool:
                npc_lower = npc_name.lower().strip()
                # Check if any word in the name is a known non-character pattern
                words = npc_lower.split()
                for word in words:
                    if word in NON_CHARACTER_PATTERNS:
                        return True
                # Check for multi-word patterns
                if npc_lower in NON_CHARACTER_PATTERNS:
                    return True
                # Check if the full name contains a non-character pattern
                for pattern in NON_CHARACTER_PATTERNS:
                    if pattern in npc_lower:
                        return True
                return False

            npcs = [npc for npc in npcs if not is_likely_object(npc.character_name)]
            logger.info(f"[NPC-SUGGESTIONS] NPCs after filtering objects: {len(npcs)}")

            # Post-process to remove duplicates (case-insensitive and substring matches)
            # This handles existing duplicates in the database
            
            # Deduplicate by case-insensitive name and substring matches
            # e.g., "Reynolds" and "Sheriff Reynolds" should be merged
            seen_names = {}  # Maps normalized name to NPC object
            deduplicated_npcs = []
            
            for npc in npcs:
                name_lower = npc.character_name.lower().strip()
                name_words = set(name_lower.split())  # Split into words for better matching
                
                # Check for exact match first
                if name_lower in seen_names:
                    existing = seen_names[name_lower]
                    # Merge: keep the one with higher importance or more mentions
                    if (npc.importance_score > existing.importance_score or 
                        (npc.importance_score == existing.importance_score and npc.total_mentions > existing.total_mentions)):
                        deduplicated_npcs.remove(existing)
                        deduplicated_npcs.append(npc)
                        seen_names[name_lower] = npc
                    continue
                
                # Check for substring matches (e.g., "reynolds" in "sheriff reynolds")
                merged = False
                for existing_lower, existing_npc in list(seen_names.items()):
                    existing_words = set(existing_lower.split())
                    
                    # If one name's words are a subset of the other, they're the same person
                    # e.g., {"reynolds"} is subset of {"sheriff", "reynolds"}
                    if name_words.issubset(existing_words) or existing_words.issubset(name_words):
                        # Same person - prefer the one with higher importance score, then longer name
                        if (npc.importance_score > existing_npc.importance_score or
                            (npc.importance_score == existing_npc.importance_score and 
                             len(npc.character_name) > len(existing_npc.character_name))):
                            # New NPC is better, replace existing
                            deduplicated_npcs.remove(existing_npc)
                            deduplicated_npcs.append(npc)
                            seen_names[existing_lower] = npc
                            seen_names[name_lower] = npc
                        else:
                            # Existing NPC is better, keep it
                            seen_names[name_lower] = existing_npc
                        merged = True
                        break
                    
                    # Also check if one name contains the other as a substring
                    # (handles cases where words aren't split properly)
                    if name_lower in existing_lower or existing_lower in name_lower:
                        # Same person - prefer higher importance score, then longer name
                        if (npc.importance_score > existing_npc.importance_score or
                            (npc.importance_score == existing_npc.importance_score and 
                             len(npc.character_name) > len(existing_npc.character_name))):
                            deduplicated_npcs.remove(existing_npc)
                            deduplicated_npcs.append(npc)
                            seen_names[existing_lower] = npc
                            seen_names[name_lower] = npc
                        else:
                            seen_names[name_lower] = existing_npc
                        merged = True
                        break
                
                if not merged:
                    # New unique name
                    seen_names[name_lower] = npc
                    deduplicated_npcs.append(npc)
            
            # Sort deduplicated list by importance score
            deduplicated_npcs.sort(key=lambda x: x.importance_score or 0.0, reverse=True)
            
            # Filter out generic entities (even if they exist in DB as CHARACTER)
            # This provides immediate filtering without requiring database cleanup
            GENERIC_ENTITY_NAMES = {
                'guards', 'guard', 'soldiers', 'soldier', 'troops', 'troop',
                'creatures', 'creature', 'beings', 'being', 'figures', 'figure',
                'entities', 'entity', 'shadows', 'shadow', 'forces', 'force',
                'bolts', 'bolt', 'plasma bolts', 'energy beams', 'elongated figures',
                'plasma bolt', 'energy beam', 'elongated figure'
            }
            
            filtered_npcs = [
                npc for npc in deduplicated_npcs 
                if npc.character_name.lower() not in GENERIC_ENTITY_NAMES
            ]
            
            # Use filtered list
            suggestions = []
            for npc in filtered_npcs:
                profile = npc.extracted_profile or {}
                
                # Get preview from extracted description
                preview = profile.get("description", "")
                
                if not preview:
                    # Try first mention's extracted properties
                    first_mention = db.query(NPCMention).filter(
                        NPCMention.story_id == story_id,
                        NPCMention.character_name == npc.character_name
                    ).order_by(NPCMention.sequence_number).first()
                    
                    if first_mention and first_mention.extracted_properties:
                        preview = first_mention.extracted_properties.get("description", "")
                
                if not preview:
                    # Last resort: use first context snippet
                    first_mention = db.query(NPCMention).filter(
                        NPCMention.story_id == story_id,
                        NPCMention.character_name == npc.character_name
                    ).order_by(NPCMention.sequence_number).first()
                    
                    if first_mention and first_mention.context_snippets:
                        preview = first_mention.context_snippets[0][:100] + "..."
                
                if not preview:
                    preview = "Character mentioned in story"
                
                # Format as character suggestion
                # New formula produces 0-100 scale directly
                raw_score = npc.importance_score or 0.0
                
                # Handle old scores (>100) by capping them, new scores are already 0-100
                importance_percentage = int(min(raw_score, 100))
                
                suggestion = {
                    "name": npc.character_name,
                    "mention_count": npc.total_mentions or 0,
                    "importance_score": importance_percentage,
                    "first_appearance_scene": npc.first_appearance_scene or 0,
                    "last_appearance_scene": npc.last_appearance_scene or 0,
                    "is_in_library": False,  # NPCs are not in library yet
                    "is_npc": True,  # Flag to indicate this is an NPC
                    "preview": preview,  # Use extracted description
                    "scenes": []  # Will be populated if needed
                }
                
                suggestions.append(suggestion)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to get NPCs as suggestions: {e}")
            return []
    
    def _get_active_branch_id(self, db: Session, story_id: int) -> int:
        """Get the active branch ID for a story."""
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        return active_branch.id if active_branch else None
    
    def get_important_npcs_for_context(
        self,
        db: Session,
        story_id: int,
        limit: int = 10,
        branch_id: int = None
    ) -> List[Dict[str, Any]]:
        """
        Get most important NPCs formatted for context inclusion.
        
        DEPRECATED: Use get_tiered_npcs_for_context() for recency-aware NPC inclusion.
        This method is kept for backward compatibility and returns all threshold-crossing NPCs.
        
        Returns format compatible with explicit character format.
        Only includes NPCs that have crossed threshold, ordered by importance score.
        Excludes NPCs that have been converted to explicit characters.
        
        Args:
            db: Database session
            story_id: Story ID
            limit: Maximum number of NPCs to return (default: 10)
            branch_id: Optional branch ID for filtering
            
        Returns:
            List of NPCs formatted as characters, sorted by importance (most important first)
        """
        # Delegate to tiered method and return only active NPCs for backward compatibility
        result = self.get_tiered_npcs_for_context(
            db=db,
            story_id=story_id,
            current_scene_sequence=None,  # No recency filtering
            chapter_id=None,
            limit=limit,
            branch_id=branch_id
        )
        return result.get("active_npcs", [])

    def _get_cross_story_npcs(
        self,
        db: Session,
        current_story_id: int,
        world_id: Optional[int],
        explicit_character_names: Optional[set],
        current_npc_names: set,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get important NPCs from sibling stories in the same world.

        Returns inactive-tier entries (name + role + source label) for NPCs that:
        - Crossed threshold in a sibling story
        - Are CHARACTER type (not ENTITY)
        - Are not already in the current story's NPC list
        - Are not explicit characters in the current story

        Args:
            db: Database session
            current_story_id: Current story ID (excluded from query)
            world_id: World ID to find sibling stories
            explicit_character_names: Lowercase names of explicit characters to exclude
            current_npc_names: Lowercase names of NPCs already in current story's tiers
            limit: Max cross-story NPCs to include

        Returns:
            List of inactive-tier NPC dicts with source label
        """
        if not world_id:
            return []

        try:
            from ..models import Story

            # Find sibling stories in the same world
            sibling_stories = db.query(Story).filter(
                Story.world_id == world_id,
                Story.id != current_story_id
            ).all()

            if not sibling_stories:
                return []

            sibling_ids = [s.id for s in sibling_stories]
            sibling_titles = {s.id: s.title for s in sibling_stories}

            # Build canonical branch map: each sibling uses current_branch_id
            branch_conditions = []
            for s in sibling_stories:
                canonical = s.current_branch_id
                if canonical is None:
                    active = db.query(StoryBranch).filter(
                        StoryBranch.story_id == s.id,
                        StoryBranch.is_active == True
                    ).first()
                    canonical = active.id if active else None
                if canonical is not None:
                    branch_conditions.append(
                        and_(NPCTracking.story_id == s.id,
                             or_(NPCTracking.branch_id == canonical, NPCTracking.branch_id.is_(None)))
                    )
                else:
                    branch_conditions.append(
                        and_(NPCTracking.story_id == s.id, NPCTracking.branch_id.is_(None))
                    )

            # Query threshold-crossing CHARACTER NPCs from sibling stories
            from sqlalchemy import desc
            sibling_npcs = db.query(NPCTracking).filter(
                NPCTracking.story_id.in_(sibling_ids),
                NPCTracking.crossed_threshold == True,
                NPCTracking.converted_to_character == False,
                or_(NPCTracking.entity_type == "CHARACTER", NPCTracking.entity_type.is_(None)),
                or_(*branch_conditions) if branch_conditions else True
            ).order_by(desc(NPCTracking.importance_score)).all()

            if not sibling_npcs:
                return []

            explicit_names = explicit_character_names or set()
            # Build name parts for partial matching (e.g. "ali" matches "ali malik")
            explicit_name_parts = set()
            for name in explicit_names:
                explicit_name_parts.add(name)
                for part in name.split():
                    if len(part) > 2:
                        explicit_name_parts.add(part)

            cross_story_npcs = []
            seen_names = set()

            for npc in sibling_npcs:
                if len(cross_story_npcs) >= limit:
                    break

                name_lower = npc.character_name.lower()

                # Skip if already in current story's tiers
                if name_lower in current_npc_names:
                    continue

                # Skip if it matches an explicit character (partial name matching)
                npc_parts = [p for p in name_lower.split() if len(p) > 2]
                if name_lower in explicit_name_parts or any(p in explicit_name_parts for p in npc_parts):
                    continue

                # Dedup across sibling stories — keep the one with richest profile
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

                profile = npc.extracted_profile or {}
                source_title = sibling_titles.get(npc.story_id, "another story")
                role = profile.get("role", "NPC")

                cross_story_npcs.append({
                    "name": npc.character_name,
                    "role": f"{role} [From '{source_title}']",
                    "description": profile.get("description", ""),
                })

            if cross_story_npcs:
                logger.info(f"[NPC TIERED] Cross-story: {len(cross_story_npcs)} NPCs from world {world_id}: "
                           f"{[n['name'] for n in cross_story_npcs]}")

            return cross_story_npcs

        except Exception as e:
            logger.warning(f"[NPC TIERED] Failed to get cross-story NPCs: {e}")
            return []

    def get_tiered_npcs_for_context(
        self,
        db: Session,
        story_id: int,
        current_scene_sequence: Optional[int] = None,
        chapter_id: Optional[int] = None,
        limit: int = 10,
        branch_id: int = None,
        world_id: Optional[int] = None,
        explicit_character_names: Optional[set] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get NPCs formatted for context inclusion with tiered recency-based filtering.

        IMPORTANT: This method first tries to load pre-calculated NPC lists from the
        most recent NPC tracking snapshot. This ensures cache stability - all scenes
        until the next extraction use the exact same NPC lists.

        Falls back to dynamic calculation only for old snapshots without pre-calculated lists.

        Returns NPCs in three tiers based on recency:
        - TIER 1 (Active): Appeared in last N scenes OR in current chapter - full details
        - TIER 2 (Inactive): Appeared in last M scenes but not Tier 1 - brief mention (name + role)
        - TIER 3 (Dormant): Haven't appeared in last M scenes - excluded from context

        When world_id is provided, also includes important NPCs from sibling stories
        in the same world as inactive-tier entries (name + role + source story label).

        Args:
            db: Database session
            story_id: Story ID
            current_scene_sequence: Current scene sequence number for recency calculation
            chapter_id: Current chapter ID for chapter-awareness
            limit: Maximum number of NPCs per tier (default: 10)
            branch_id: Optional branch ID for filtering
            world_id: Optional world ID for cross-story NPC inclusion
            explicit_character_names: Optional set of lowercase explicit character names
                to exclude from cross-story NPC results (avoids duplication)

        Returns:
            Dictionary with:
            - active_npcs: List of NPCs with full details (Tier 1)
            - inactive_npcs: List of NPCs with brief details (Tier 2)
        """
        try:
            from sqlalchemy import desc

            # Get active branch if not specified
            if branch_id is None:
                branch_id = self._get_active_branch_id(db, story_id)

            # If no current scene sequence provided, get the latest scene sequence
            if current_scene_sequence is None:
                latest_scene = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False
                ).order_by(desc(Scene.sequence_number)).first()
                current_scene_sequence = latest_scene.sequence_number if latest_scene else 0

            # === TRY TO LOAD FROM SNAPSHOT FIRST ===
            # Find the most recent snapshot at or before current scene
            snapshot_query = db.query(NPCTrackingSnapshot).filter(
                NPCTrackingSnapshot.story_id == story_id,
                NPCTrackingSnapshot.scene_sequence <= current_scene_sequence
            )
            if branch_id is not None:
                snapshot_query = snapshot_query.filter(NPCTrackingSnapshot.branch_id == branch_id)
            snapshot = snapshot_query.order_by(desc(NPCTrackingSnapshot.scene_sequence)).first()

            if snapshot and snapshot.snapshot_data:
                # Check if snapshot has pre-calculated context lists
                active_npcs = snapshot.snapshot_data.get("_active_npcs_for_context")
                inactive_npcs = snapshot.snapshot_data.get("_inactive_npcs_for_context")

                if active_npcs is not None and inactive_npcs is not None:
                    logger.info(f"[NPC TIERED] Using pre-calculated lists from snapshot (scene {snapshot.scene_sequence}): "
                               f"{len(active_npcs)} active, {len(inactive_npcs)} inactive")
                    # Append cross-story world NPCs to inactive tier
                    cross_story = self._get_cross_story_npcs(
                        db, story_id, world_id, explicit_character_names,
                        {npc.get("name", "").lower() for npc in active_npcs + inactive_npcs},
                        limit
                    )
                    if cross_story:
                        inactive_npcs = list(inactive_npcs) + cross_story
                    return {
                        "active_npcs": active_npcs,
                        "inactive_npcs": inactive_npcs
                    }
                else:
                    logger.info(f"[NPC TIERED] Snapshot {snapshot.scene_sequence} has no pre-calculated lists, falling back to dynamic calculation")

            # === FALLBACK: DYNAMIC CALCULATION ===
            # This path is used for old snapshots or when no snapshot exists
            logger.info(f"[NPC TIERED] No valid snapshot found, using dynamic calculation for scene {current_scene_sequence}")

            # Get recency window settings from user settings or config defaults
            active_window = self.user_settings.get("npc_active_recency_window", settings.npc_active_recency_window)
            inactive_window = self.user_settings.get("npc_inactive_recency_window", settings.npc_inactive_recency_window)
            use_chapter_awareness = self.user_settings.get("npc_use_chapter_awareness", settings.npc_use_chapter_awareness)

            # Get NPCs in current chapter (if chapter awareness is enabled)
            chapter_npc_names = set()
            if use_chapter_awareness and chapter_id:
                # Get all scenes in this chapter
                chapter_scenes = db.query(Scene).filter(
                    Scene.chapter_id == chapter_id,
                    Scene.is_deleted == False
                ).all()
                chapter_scene_ids = [s.id for s in chapter_scenes]

                # Get NPCs that appear in any of these scenes
                if chapter_scene_ids:
                    chapter_mentions = db.query(NPCMention.character_name).filter(
                        NPCMention.scene_id.in_(chapter_scene_ids)
                    ).distinct().all()
                    chapter_npc_names = {m[0].lower() for m in chapter_mentions}

            # Log configuration
            logger.info(f"[NPC TIERED] Dynamic calc config: active_window={active_window}, inactive_window={inactive_window}, "
                       f"chapter_awareness={use_chapter_awareness}, current_scene={current_scene_sequence}")

            # Get ALL NPCs that crossed threshold for this story/branch (including NULL branch_id for shared NPCs)
            # Filter to CHARACTER entity_type only (or NULL for legacy data)
            npcs_query = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.crossed_threshold == True,
                NPCTracking.converted_to_character == False,
                or_(NPCTracking.entity_type == "CHARACTER", NPCTracking.entity_type.is_(None))
            )
            if branch_id:
                npcs_query = npcs_query.filter(NPCTracking.branch_id == branch_id)
            all_npcs = npcs_query.order_by(desc(NPCTracking.importance_score)).all()

            logger.info(f"[NPC TIERED] Total NPCs that crossed threshold: {len(all_npcs)}")

            # Categorize NPCs into tiers
            active_npcs = []
            inactive_npcs = []
            dormant_count = 0

            for npc in all_npcs:
                last_appearance = npc.last_appearance_scene or 0
                scenes_since_appearance = current_scene_sequence - last_appearance

                # Check if NPC is in current chapter
                in_current_chapter = npc.character_name.lower() in chapter_npc_names

                # Determine tier
                is_active = False
                is_inactive = False

                # Tier 1: Active - appeared recently OR in current chapter
                if scenes_since_appearance <= active_window or in_current_chapter:
                    is_active = True
                # Tier 2: Inactive - appeared within inactive window but not active
                elif scenes_since_appearance <= inactive_window:
                    is_inactive = True
                # Tier 3: Dormant - excluded
                else:
                    dormant_count += 1

                tier_label = "ACTIVE" if is_active else ("INACTIVE" if is_inactive else "DORMANT")
                chapter_note = " (in chapter)" if in_current_chapter else ""
                logger.debug(f"[NPC TIERED]   {npc.character_name}: last_scene={last_appearance}, "
                           f"scenes_ago={scenes_since_appearance}, tier={tier_label}{chapter_note}")

                if is_active and len(active_npcs) < limit:
                    profile = npc.extracted_profile or {}
                    active_npcs.append({
                        "name": npc.character_name,
                        "role": profile.get("role", "NPC"),
                        "description": profile.get("description", ""),
                        "personality": ", ".join(profile.get("personality", [])),
                        "background": profile.get("background", ""),
                        "goals": profile.get("goals", ""),
                        "relationships": profile.get("relationships", {})
                    })
                elif is_inactive and len(inactive_npcs) < limit:
                    profile = npc.extracted_profile or {}
                    inactive_npcs.append({
                        "name": npc.character_name,
                        "role": profile.get("role", "NPC")
                    })

            logger.info(f"[NPC TIERED] Dynamic result: {len(active_npcs)} active, {len(inactive_npcs)} inactive, "
                       f"{dormant_count} dormant (excluded)")

            # Append cross-story world NPCs to inactive tier
            cross_story = self._get_cross_story_npcs(
                db, story_id, world_id, explicit_character_names,
                {npc.get("name", "").lower() for npc in active_npcs + inactive_npcs},
                limit
            )
            if cross_story:
                inactive_npcs.extend(cross_story)

            return {
                "active_npcs": active_npcs,
                "inactive_npcs": inactive_npcs
            }

        except Exception as e:
            logger.error(f"Failed to get tiered NPCs for context: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"active_npcs": [], "inactive_npcs": []}

