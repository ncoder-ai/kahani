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

from ..models import (
    NPCMention, NPCTracking, StoryCharacter, Character, Scene, Story
)
from ..services.llm.service import UnifiedLLMService
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
    
    async def extract_npcs_from_scenes_batch(
        self,
        db: Session,
        story_id: int,
        scenes: List[Tuple[int, int, str]]  # List of (scene_id, scene_sequence, scene_content) tuples
    ) -> Dict[str, Any]:
        """
        Batch extract NPCs from multiple scenes in a single LLM call, then store them.
        
        Args:
            db: Database session
            story_id: Story ID
            scenes: List of (scene_id, scene_sequence, scene_content) tuples
            
        Returns:
            Dictionary with extraction results:
            - npcs_tracked: Total NPCs tracked
            - scenes_processed: Number of scenes processed
            - extraction_successful: Whether extraction completed
        """
        if not scenes:
            return {
                "npcs_tracked": 0,
                "scenes_processed": 0,
                "extraction_successful": False
            }
        
        try:
            # Get list of explicit characters in the story
            from ..models import StoryCharacter, Character
            story_characters = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id
            ).all()
            
            explicit_character_names = set()
            for sc in story_characters:
                character = db.query(Character).filter(Character.id == sc.character_id).first()
                if character:
                    explicit_character_names.add(character.name.lower())
            
            # Concatenate scenes with clear markers
            scenes_text = []
            for scene_id, scene_sequence, scene_content in scenes:
                scenes_text.append(f"=== SCENE {scene_sequence} (ID: {scene_id}) ===\n{scene_content}\n")
            
            batch_content = "\n".join(scenes_text)
            
            # Extract NPCs from all scenes at once
            npc_data = await self._extract_npcs_with_llm_batch(
                batch_content,
                list(explicit_character_names)
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
            
            scene_npc_map = map_npcs_to_scenes(extracted_npcs, scenes_for_verification)
            
            # Store NPCs for each scene
            total_npcs_tracked = 0
            for scene_id, scene_sequence, scene_content in scenes:
                npcs_for_scene = scene_npc_map.get(scene_id, [])
                
                for npc_data_scene in npcs_for_scene:
                    npc_name = npc_data_scene.get('name', '').strip()
                    if not npc_name or npc_name.lower() in explicit_character_names:
                        continue
                    
                    # Convert string booleans to actual booleans
                    def to_bool(value):
                        if isinstance(value, bool):
                            return value
                        if isinstance(value, str):
                            return value.lower() in ('true', '1', 'yes')
                        return bool(value)
                    
                    # Store mention
                    mention = NPCMention(
                        story_id=story_id,
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
                    
                    # Update or create tracking record
                    await self._update_npc_tracking(
                        db, story_id, npc_name, scene_sequence, npc_data_scene
                    )
                    
                    total_npcs_tracked += 1
            
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
    
    async def _extract_npcs_with_llm_batch(
        self,
        batch_content: str,
        explicit_character_names: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract NPCs from multiple scenes in batch.
        
        Returns JSON with NPC information (not mapped to scenes).
        """
        try:
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Analyze these story scenes and extract ALL named entities (characters, beings, entities) 
that are NOT in the explicit character list.

{batch_content}

Explicit Characters (already tracked): {explicit_names_str}

Extract ALL named entities that:
- Are mentioned by name
- Are NOT in the explicit character list above
- Could be characters, NPCs, entities, beings, or important figures
- Have dialogue, perform actions, or have relationships in any scene

For each NPC, identify:
- Name (exact name as mentioned)
- Mention count (total mentions across all scenes)
- Has dialogue (true/false - has dialogue in any scene)
- Has actions (true/false - performs actions in any scene)
- Has relationships (true/false - interacts with other characters)
- Context snippets (array of 2-3 short text snippets mentioning this NPC from any scene)
- Properties (role, description, etc. if mentioned)

Return ONLY valid JSON in this exact format:
{{
  "npcs": [
    {{
      "name": "NPC name",
      "mention_count": 3,
      "has_dialogue": true,
      "has_actions": true,
      "has_relationships": true,
      "context_snippets": ["snippet 1", "snippet 2"],
      "properties": {{
        "role": "role description",
        "description": "brief description"
      }}
    }}
  ]
}}

If no NPCs found, return {{"npcs": []}}. Return ONLY the JSON, no other text."""
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt="You are an expert at analyzing narrative text and extracting named entities.",
                max_tokens=2000
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
            
            import json
            npc_data = json.loads(response_clean)
            return npc_data
            
        except Exception as e:
            logger.error(f"Failed to extract NPCs with LLM (batch): {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def extract_npcs_from_scene(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        scene_content: str
    ) -> Dict[str, Any]:
        """
        Extract NPCs from a scene and store mentions.
        
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
            "npcs_found": 0,
            "npcs_tracked": 0,
            "extraction_successful": False
        }
        
        try:
            # Get list of explicit characters in the story
            story_characters = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id
            ).all()
            
            explicit_character_names = set()
            for sc in story_characters:
                character = db.query(Character).filter(Character.id == sc.character_id).first()
                if character:
                    explicit_character_names.add(character.name.lower())
            
            # Extract NPCs using LLM
            npc_data = await self._extract_npcs_with_llm(
                scene_content,
                scene_sequence,
                list(explicit_character_names)
            )
            
            if not npc_data or "npcs" not in npc_data:
                logger.warning(f"No NPCs extracted from scene {scene_id}")
                return results
            
            results["npcs_found"] = len(npc_data["npcs"])
            
            # Store mentions and update tracking
            for npc in npc_data["npcs"]:
                npc_name = npc.get("name", "").strip()
                if not npc_name or npc_name.lower() in explicit_character_names:
                    continue  # Skip if already an explicit character
                
                # Convert string booleans to actual booleans (LLM sometimes returns 'true'/'false' as strings)
                def to_bool(value):
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.lower() in ('true', '1', 'yes')
                    return bool(value)
                
                # Store mention
                mention = NPCMention(
                    story_id=story_id,
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
                
                # Update or create tracking record
                await self._update_npc_tracking(
                    db, story_id, npc_name, scene_sequence, npc
                )
                
                results["npcs_tracked"] += 1
            
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
        explicit_character_names: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract NPCs from a scene.
        
        Returns JSON with NPC information.
        """
        try:
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Analyze this story scene and extract ALL named entities (characters, beings, entities) 
that are NOT in the explicit character list.

Scene (Sequence #{scene_sequence}):
{scene_content}

Explicit Characters (already tracked): {explicit_names_str}

Extract ALL named entities that:
- Are mentioned by name
- Are NOT in the explicit character list above
- Could be characters, NPCs, entities, beings, or important figures
- Have dialogue, perform actions, or have relationships in the scene

For each NPC, identify:
- Name (exact name as mentioned)
- Mention count (how many times mentioned in this scene)
- Has dialogue (true/false)
- Has actions (true/false - performs actions in scene)
- Has relationships (true/false - interacts with other characters)
- Context snippets (array of 2-3 short text snippets mentioning this NPC)
- Properties (role, description, etc. if mentioned)

Return ONLY valid JSON in this exact format:
{{
  "npcs": [
    {{
      "name": "NPC name",
      "mention_count": 3,
      "has_dialogue": true,
      "has_actions": true,
      "has_relationships": true,
      "context_snippets": ["snippet 1", "snippet 2"],
      "properties": {{
        "role": "role description",
        "description": "brief description"
      }}
    }}
  ]
}}

If no NPCs found, return {{"npcs": []}}. Return ONLY the JSON, no other text."""
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt="You are a precise story analysis assistant. Extract NPCs and named entities from scenes. Return only valid JSON.",
                max_tokens=1000
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
            logger.error(f"Failed to extract NPCs: {e}")
            return None
    
    async def _update_npc_tracking(
        self,
        db: Session,
        story_id: int,
        character_name: str,
        scene_sequence: int,
        npc_data: Dict[str, Any]
    ):
        """Update or create NPC tracking record"""
        try:
            # Get or create tracking record
            tracking = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.character_name == character_name
            ).first()
            
            if not tracking:
                tracking = NPCTracking(
                    story_id=story_id,
                    character_name=character_name,
                    first_appearance_scene=scene_sequence,
                    last_appearance_scene=scene_sequence,
                    total_mentions=0,
                    scene_count=0,
                    has_dialogue_count=0,
                    has_actions_count=0
                )
                db.add(tracking)
            
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
    
    async def _calculate_importance_score(
        self,
        db: Session,
        story_id: int,
        tracking: NPCTracking
    ):
        """
        Calculate importance score based on frequency and significance.
        
        Formula:
        - Frequency score: (scene_count / total_scenes) * 0.4 + (total_mentions / avg_mentions) * 0.1
        - Significance score: (has_dialogue_count / scene_count) * 0.3 + (has_actions_count / scene_count) * 0.2
        - Combined: frequency_score + significance_score
        """
        try:
            # Get total scenes in story
            total_scenes = db.query(Scene).filter(Scene.story_id == story_id).count()
            
            if total_scenes == 0:
                tracking.importance_score = 0.0
                tracking.frequency_score = 0.0
                tracking.significance_score = 0.0
                return
            
            # Initialize None values to 0 (safety check)
            if tracking.total_mentions is None:
                tracking.total_mentions = 0
            if tracking.has_dialogue_count is None:
                tracking.has_dialogue_count = 0
            if tracking.has_actions_count is None:
                tracking.has_actions_count = 0
            if tracking.scene_count is None:
                tracking.scene_count = 0
            
            # Calculate frequency score
            scene_ratio = tracking.scene_count / total_scenes if total_scenes > 0 else 0
            # Average mentions per scene (rough estimate)
            avg_mentions = tracking.total_mentions / max(tracking.scene_count, 1) if tracking.scene_count > 0 else 0
            mention_ratio = 1.0 if avg_mentions == 0 else min(tracking.total_mentions / (avg_mentions * total_scenes), 1.0) if avg_mentions > 0 else 0
            
            frequency_score = (scene_ratio * 0.4) + (mention_ratio * 0.1)
            
            # Calculate significance score
            dialogue_ratio = (tracking.has_dialogue_count / tracking.scene_count) if tracking.scene_count > 0 else 0
            actions_ratio = (tracking.has_actions_count / tracking.scene_count) if tracking.scene_count > 0 else 0
            
            significance_score = (dialogue_ratio * 0.3) + (actions_ratio * 0.2)
            
            # Update scene count (count distinct scenes)
            scene_count_query = db.query(NPCMention.scene_id).filter(
                NPCMention.story_id == story_id,
                NPCMention.character_name == tracking.character_name
            ).distinct().count()
            
            tracking.scene_count = scene_count_query
            tracking.frequency_score = frequency_score
            tracking.significance_score = significance_score
            tracking.importance_score = frequency_score + significance_score
            
        except Exception as e:
            logger.error(f"Failed to calculate importance score: {e}")
    
    async def _extract_npc_profile(
        self,
        db: Session,
        story_id: int,
        character_name: str
    ):
        """
        Extract full character profile for an NPC using LLM analysis of all scenes.
        """
        try:
            # Get all scenes where NPC appears
            mentions = db.query(NPCMention).filter(
                NPCMention.story_id == story_id,
                NPCMention.character_name == character_name
            ).order_by(NPCMention.sequence_number).all()
            
            if not mentions:
                return
            
            # Get scene contents
            scenes_data = []
            for mention in mentions:
                scene = db.query(Scene).filter(Scene.id == mention.scene_id).first()
                if scene:
                    scenes_data.append({
                        "sequence": mention.sequence_number,
                        "content": scene.content or ""
                    })
            
            if not scenes_data:
                return
            
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
                max_tokens=1500
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
            
            # Update tracking record
            tracking = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.character_name == character_name
            ).first()
            
            if tracking:
                tracking.extracted_profile = profile
                tracking.profile_extracted = True
                db.commit()
                logger.info(f"Extracted profile for NPC '{character_name}'")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse NPC profile JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to extract NPC profile: {e}")
    
    def mark_npc_as_converted(
        self,
        db: Session,
        story_id: int,
        character_name: str
    ) -> bool:
        """
        Mark an NPC as converted to explicit character.
        
        Args:
            db: Database session
            story_id: Story ID
            character_name: Character name (case-insensitive match)
            
        Returns:
            True if NPC was found and marked, False otherwise
        """
        try:
            # Find NPC by name (case-insensitive)
            npc = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                func.lower(NPCTracking.character_name) == character_name.lower()
            ).first()
            
            if npc:
                npc.converted_to_character = True
                # Don't commit here - let the caller handle commit
                logger.info(f"Marked NPC '{character_name}' as converted to explicit character")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to mark NPC as converted: {e}")
            return False
    
    def get_npcs_as_suggestions(
        self,
        db: Session,
        story_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get NPCs that crossed threshold formatted as character suggestions.
        
        Returns format compatible with CharacterAssistantService suggestions.
        Excludes NPCs that have been converted to explicit characters.
        """
        try:
            npcs = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.crossed_threshold == True,
                NPCTracking.converted_to_character == False  # Exclude converted NPCs
            ).all()
            
            suggestions = []
            for npc in npcs:
                profile = npc.extracted_profile or {}
                
                # Format as character suggestion
                suggestion = {
                    "name": npc.character_name,
                    "mention_count": npc.total_mentions or 0,
                    "importance_score": int((npc.importance_score or 0.0) * 100),  # Scale to 0-100
                    "first_appearance_scene": npc.first_appearance_scene or 0,
                    "last_appearance_scene": npc.last_appearance_scene or 0,
                    "is_in_library": False,  # NPCs are not in library yet
                    "is_npc": True,  # Flag to indicate this is an NPC
                    "preview": profile.get("description", "NPC mentioned in story"),
                    "scenes": []  # Will be populated if needed
                }
                
                suggestions.append(suggestion)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to get NPCs as suggestions: {e}")
            return []
    
    def get_important_npcs_for_context(
        self,
        db: Session,
        story_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most important NPCs formatted for context inclusion.
        
        Returns format compatible with explicit character format.
        Only includes NPCs that have crossed threshold, ordered by importance score.
        Excludes NPCs that have been converted to explicit characters.
        
        Args:
            db: Database session
            story_id: Story ID
            limit: Maximum number of NPCs to return (default: 10)
            
        Returns:
            List of NPCs formatted as characters, sorted by importance (most important first)
        """
        try:
            from sqlalchemy import desc
            
            # Log threshold being used
            logger.warning(f"[NPC CONTEXT] Importance threshold: {self.importance_threshold}")
            
            # Get ALL NPCs for this story to show what's available
            all_npcs = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.converted_to_character == False
            ).order_by(desc(NPCTracking.importance_score)).all()
            
            # Log all NPCs with their scores and threshold status
            logger.warning(f"[NPC CONTEXT] Total NPCs in story: {len(all_npcs)}")
            for npc in all_npcs:
                threshold_status = "✓ CROSSED" if npc.crossed_threshold else "✗ BELOW"
                logger.warning(f"[NPC CONTEXT]   - {npc.character_name}: importance_score={npc.importance_score:.2f}, threshold={self.importance_threshold:.2f}, status={threshold_status}")
            
            # Get NPCs that crossed threshold, ordered by importance score (most important first)
            npcs = db.query(NPCTracking).filter(
                NPCTracking.story_id == story_id,
                NPCTracking.crossed_threshold == True,
                NPCTracking.converted_to_character == False  # Exclude converted NPCs
            ).order_by(desc(NPCTracking.importance_score)).limit(limit).all()
            
            logger.warning(f"[NPC CONTEXT] NPCs that crossed threshold: {len(npcs)} (limit: {limit})")
            
            characters = []
            for npc in npcs:
                profile = npc.extracted_profile or {}
                
                # Format as character for context
                character = {
                    "name": npc.character_name,
                    "role": profile.get("role", "NPC"),
                    "description": profile.get("description", ""),
                    "personality": ", ".join(profile.get("personality", [])),
                    "background": profile.get("background", ""),
                    "goals": profile.get("goals", ""),
                    "relationships": profile.get("relationships", {})
                }
                
                characters.append(character)
                logger.warning(f"[NPC CONTEXT]   INCLUDED: {npc.character_name} (score: {npc.importance_score:.2f})")
            
            if len(characters) == 0:
                logger.warning(f"[NPC CONTEXT] No NPCs included in context - check if any NPCs have crossed threshold ({self.importance_threshold})")
            
            logger.warning(f"[NPC CONTEXT] Returning {len(characters)} NPCs for context inclusion")
            return characters
            
        except Exception as e:
            logger.error(f"Failed to get NPCs for context: {e}")
            return []

