"""
Character Memory Service

Handles extraction, storage, and retrieval of character-specific moments
for maintaining character consistency across long narratives.
"""

import logging
import re
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from .semantic_memory import get_semantic_memory_service
from .llm.service import UnifiedLLMService
from .llm.extraction_service import ExtractionLLMService
from ..models import CharacterMemory, Character, Scene, MomentType
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


class CharacterMemoryService:
    """
    Service for tracking and retrieving character moments
    
    Features:
    - Automatic character moment extraction from scenes
    - Semantic search for relevant character moments
    - Character arc timeline construction
    - Relationship tracking
    """
    
    def __init__(self):
        """Initialize character memory service"""
        try:
            self.semantic_memory = get_semantic_memory_service()
        except RuntimeError:
            logger.warning("Semantic memory service not initialized")
            self.semantic_memory = None
        
        self.llm_service = UnifiedLLMService()
        self.extraction_service = None  # Will be initialized conditionally
    
    async def extract_character_moments_from_scenes_batch(
        self,
        scenes: List[Tuple[int, int, Optional[int], str]],  # List of (scene_id, sequence_number, chapter_id, scene_content)
        story_id: int,
        user_id: int,
        user_settings: Dict[str, Any],
        db: Session
    ) -> Dict[int, List[CharacterMemory]]:
        """
        Batch extract character moments from multiple scenes in a single LLM call.
        
        Args:
            scenes: List of (scene_id, sequence_number, chapter_id, scene_content) tuples
            story_id: Story ID
            user_id: User ID for LLM calls
            user_settings: User settings for LLM
            db: Database session
            
        Returns:
            Dictionary mapping scene_id to list of created CharacterMemory objects
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available, skipping batch moment extraction")
            return {}
        
        if not scenes:
            return {}
        
        try:
            # Get story characters
            from ..models import StoryCharacter
            story_characters = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id
            ).all()
            
            if not story_characters:
                logger.info("No characters defined for story, skipping batch extraction")
                return {}
            
            # Build character list for LLM
            character_names = []
            character_map = {}
            for sc in story_characters:
                char = db.query(Character).filter(Character.id == sc.character_id).first()
                if char:
                    character_names.append(char.name)
                    character_map[char.name.lower()] = char
            
            if not character_names:
                return {}
            
            # Concatenate scenes with clear markers
            scenes_text = []
            for scene_id, sequence_number, chapter_id, scene_content in scenes:
                scenes_text.append(f"=== SCENE {sequence_number} (ID: {scene_id}) ===\n{scene_content}\n")
            
            batch_content = "\n".join(scenes_text)
            
            # Extract moments from all scenes at once
            moments_data = await self._llm_extract_moments_batch(
                batch_content,
                character_names,
                user_id,
                user_settings
            )
            
            logger.warning(f"RAW PARSED MOMENTS DATA: {moments_data}")
            logger.warning(f"CHARACTER NAMES FROM DB: {character_names}")
            
            if not moments_data:
                logger.warning(f"No character moments extracted from batch of {len(scenes)} scenes")
                return {}
            
            # Post-process: Map moments to scenes using text verification
            from ..utils.scene_verification import map_moments_to_scenes
            scenes_for_verification = [(scene_id, scene_content) for scene_id, _, _, scene_content in scenes]
            
            # Group moments by character, then map each character's moments to scenes
            all_created_moments = {}
            
            for char_name in character_names:
                # Filter moments for this character
                char_moments = [m for m in moments_data if m.get('character_name', '').strip().lower() == char_name.lower()]
                
                logger.warning(f"Character '{char_name}': Found {len(char_moments)} moments after filtering")
                
                if not char_moments:
                    continue
                
                # Map this character's moments to scenes
                scene_moment_map = map_moments_to_scenes(char_moments, scenes_for_verification, char_name)
                
                logger.warning(f"Character '{char_name}': Mapped to {sum(len(moments) for moments in scene_moment_map.values())} moments across scenes")
                
                # Create CharacterMemory entries for each scene
                for scene_id, sequence_number, chapter_id, scene_content in scenes:
                    moments_for_scene = scene_moment_map.get(scene_id, [])
                    
                    if scene_id not in all_created_moments:
                        all_created_moments[scene_id] = []
                    
                    for moment_data in moments_for_scene:
                        char_name_lower = char_name.lower()
                        
                        if char_name_lower not in character_map:
                            continue
                        
                        character = character_map[char_name_lower]
                        moment_type = moment_data.get('moment_type', 'action')
                        content = moment_data.get('content', '')
                        confidence = moment_data.get('confidence', 70)
                        
                        # Skip low-confidence extractions
                        if confidence < settings.extraction_confidence_threshold:
                            continue
                        
                        # Create embedding
                        embedding_id, embedding_vector = await self.semantic_memory.add_character_moment(
                            character_id=character.id,
                            character_name=character.name,
                            scene_id=scene_id,
                            story_id=story_id,
                            moment_type=moment_type,
                            content=content,
                            metadata={
                                'sequence': sequence_number,
                                'timestamp': datetime.utcnow().isoformat()
                            }
                        )

                        # Check if memory with this embedding_id already exists
                        existing_memory = db.query(CharacterMemory).filter(
                            CharacterMemory.embedding_id == embedding_id
                        ).first()

                        if existing_memory:
                            logger.debug(f"Character moment with embedding_id {embedding_id} already exists, skipping")
                            continue

                        # Create database record with IntegrityError handling
                        try:
                            memory = CharacterMemory(
                                character_id=character.id,
                                scene_id=scene_id,
                                story_id=story_id,
                                moment_type=MomentType(moment_type),
                                content=content,
                                embedding_id=embedding_id,
                                embedding=embedding_vector,
                                sequence_order=sequence_number,
                                chapter_id=chapter_id,
                                extracted_automatically=True,
                                confidence_score=confidence
                            )
                            
                            db.add(memory)
                            db.flush()  # Flush to catch constraint violations immediately
                            all_created_moments[scene_id].append(memory)
                        except IntegrityError as ie:
                            db.rollback()
                            error_msg = str(ie).lower()
                            if "duplicate key" in error_msg or "unique constraint" in error_msg:
                                logger.debug(f"Character moment already exists (race condition), skipping: {embedding_id}")
                                continue
                            else:
                                # Re-raise if it's a different integrity error
                                raise
            
            db.commit()
            total_moments = sum(len(moments) for moments in all_created_moments.values())
            logger.info(f"Batch extracted {total_moments} character moments from {len(scenes)} scenes")
            
            return all_created_moments
            
        except Exception as e:
            logger.error(f"Failed to batch extract character moments: {e}", exc_info=True)
            db.rollback()
            return {}
    
    async def extract_character_moments(
        self,
        scene_id: int,
        scene_content: str,
        story_id: int,
        sequence_number: int,
        chapter_id: Optional[int],
        user_id: int,
        user_settings: Dict[str, Any],
        db: Session
    ) -> List[CharacterMemory]:
        """
        Extract character moments from a scene using LLM
        
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
            List of created CharacterMemory objects
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available, skipping moment extraction")
            return []
        
        try:
            # Get story characters
            from ..models import StoryCharacter
            story_characters = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id
            ).all()
            
            if not story_characters:
                logger.info("No characters defined for story, skipping extraction")
                return []
            
            # Build character list for LLM
            character_names = []
            character_map = {}
            for sc in story_characters:
                char = db.query(Character).filter(Character.id == sc.character_id).first()
                if char:
                    character_names.append(char.name)
                    character_map[char.name.lower()] = char
            
            if not character_names:
                return []
            
            # Extract moments using LLM
            moments_data = await self._llm_extract_moments(
                scene_content,
                character_names,
                user_id,
                user_settings
            )
            
            # Create CharacterMemory entries
            created_moments = []
            for moment_data in moments_data:
                char_name = moment_data.get('character_name', '').strip()
                char_name_lower = char_name.lower()
                
                if char_name_lower not in character_map:
                    logger.warning(f"Character '{char_name}' not found in story")
                    continue
                
                character = character_map[char_name_lower]
                moment_type = moment_data.get('moment_type', 'action')
                content = moment_data.get('content', '')
                confidence = moment_data.get('confidence', 70)
                
                # Skip low-confidence extractions
                if confidence < settings.extraction_confidence_threshold:
                    logger.info(f"Skipping low-confidence moment (confidence: {confidence})")
                    continue
                
                # Create embedding
                embedding_id, embedding_vector = await self.semantic_memory.add_character_moment(
                    character_id=character.id,
                    character_name=character.name,
                    scene_id=scene_id,
                    story_id=story_id,
                    moment_type=moment_type,
                    content=content,
                    metadata={
                        'sequence': sequence_number,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )

                # Check if memory with this embedding_id already exists
                existing_memory = db.query(CharacterMemory).filter(
                    CharacterMemory.embedding_id == embedding_id
                ).first()

                if existing_memory:
                    logger.info(f"Memory with embedding_id {embedding_id} already exists, skipping")
                    continue

                # Create database record
                char_memory = CharacterMemory(
                    character_id=character.id,
                    scene_id=scene_id,
                    story_id=story_id,
                    moment_type=MomentType(moment_type),
                    content=content,
                    embedding_id=embedding_id,
                    embedding=embedding_vector,
                    sequence_order=sequence_number,
                    chapter_id=chapter_id,
                    extracted_automatically=True,
                    confidence_score=confidence
                )
                
                db.add(char_memory)
                created_moments.append(char_memory)
            
            db.commit()
            logger.info(f"Extracted {len(created_moments)} character moments from scene {scene_id}")
            
            return created_moments
            
        except Exception as e:
            logger.error(f"Failed to extract character moments: {e}", exc_info=True)
            db.rollback()
            return []

    async def store_character_moments_batch(
        self,
        story_id: int,
        moments: List[Dict[str, Any]],
        character_map: Dict[str, Any],
        db: Session,
        branch_id: Optional[int] = None
    ) -> int:
        """
        Store pre-extracted character moments (from combined extraction).

        This method stores moments that were already extracted by the combined
        extraction LLM call, without re-extracting them.

        Args:
            story_id: Story ID
            moments: List of moment dicts with keys: character, moment_type, description, confidence, scene_id
            character_map: Dict mapping lowercase character names to Character objects
            db: Database session
            branch_id: Optional branch ID

        Returns:
            Number of moments stored
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available, skipping moment storage")
            return 0

        stored_count = 0

        try:
            for moment_data in moments:
                char_name = moment_data.get('character', '').strip()
                char_name_lower = char_name.lower()

                if char_name_lower not in character_map:
                    logger.debug(f"Character '{char_name}' not found in character_map, skipping")
                    continue

                character = character_map[char_name_lower]
                scene_id = moment_data.get('scene_id')
                moment_type = moment_data.get('moment_type', 'action')
                content = moment_data.get('description', '')
                confidence = moment_data.get('confidence', 70)

                if not scene_id or not content:
                    continue

                # Skip low-confidence extractions
                if confidence < settings.extraction_confidence_threshold:
                    logger.debug(f"Skipping low-confidence moment (confidence: {confidence})")
                    continue

                # Get scene sequence number
                scene = db.query(Scene).filter(Scene.id == scene_id).first()
                sequence_number = scene.sequence_number if scene else 0
                chapter_id = scene.chapter_id if scene else None

                # Create embedding
                embedding_id, embedding_vector = await self.semantic_memory.add_character_moment(
                    character_id=character.id,
                    character_name=character.name,
                    scene_id=scene_id,
                    story_id=story_id,
                    moment_type=moment_type,
                    content=content,
                    metadata={
                        'sequence': sequence_number,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )

                # Check if memory with this embedding_id already exists
                existing_memory = db.query(CharacterMemory).filter(
                    CharacterMemory.embedding_id == embedding_id
                ).first()

                if existing_memory:
                    logger.debug(f"Memory with embedding_id {embedding_id} already exists, skipping")
                    continue

                # Create database record
                char_memory = CharacterMemory(
                    character_id=character.id,
                    scene_id=scene_id,
                    story_id=story_id,
                    moment_type=MomentType(moment_type),
                    content=content,
                    embedding_id=embedding_id,
                    embedding=embedding_vector,
                    sequence_order=sequence_number,
                    chapter_id=chapter_id,
                    extracted_automatically=True,
                    confidence_score=confidence
                )

                db.add(char_memory)
                stored_count += 1

            db.commit()
            logger.info(f"Stored {stored_count} character moments from combined extraction")

            return stored_count

        except Exception as e:
            logger.error(f"Failed to store character moments batch: {e}", exc_info=True)
            db.rollback()
            return 0

    def _get_extraction_service(self, user_settings: Dict[str, Any]) -> Optional[ExtractionLLMService]:
        """
        Get or create extraction service if enabled in user settings
        
        Args:
            user_settings: User settings dictionary
            
        Returns:
            ExtractionLLMService instance or None if not enabled
        """
        return ExtractionLLMService.from_settings(user_settings)

    async def _llm_extract_moments_batch(
        self,
        batch_content: str,
        character_names: List[str],
        user_id: int,
        user_settings: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to extract character moments from multiple scenes in batch.
        Tries extraction model first, falls back to main LLM if enabled.
        
        Args:
            batch_content: Multiple scenes concatenated with scene markers
            character_names: List of character names in the story
            user_id: User ID
            user_settings: User settings
            
        Returns:
            List of moment dictionaries (not mapped to scenes)
        """
        # Try extraction model first if enabled
        extraction_service = self._get_extraction_service(user_settings)
        if extraction_service:
            try:
                logger.info(f"Using extraction model for batch character moment extraction (user {user_id})")
                moments = await extraction_service.extract_character_moments_batch(
                    batch_content=batch_content,
                    character_names=character_names
                )
                
                # Validate and normalize moments
                validated_moments = self._validate_moments(moments)
                if validated_moments:
                    logger.info(f"Extraction model successfully extracted {len(validated_moments)} moments from batch")
                    return validated_moments
                else:
                    logger.warning("Extraction model returned no valid moments from batch, falling back to main LLM")
            except Exception as e:
                logger.warning(f"Extraction model batch extraction failed: {e}, falling back to main LLM")
                # Continue to fallback
        
        # Fallback to main LLM
        fallback_enabled = user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
        if not fallback_enabled and extraction_service:
            logger.warning("Extraction model failed and fallback disabled, returning empty results")
            return []
        
        try:
            logger.info(f"Using main LLM for batch character moment extraction (user {user_id})")
            
            prompt = f"""Analyze the following scenes and extract significant character moments for these characters: {', '.join(character_names)}

{batch_content}

For each significant character moment, identify:
1. Character name
2. Moment type: "action" (physical action), "dialogue" (important speech), "development" (character growth/change), or "relationship" (interaction with others)
3. Brief description of the moment (1-2 sentences)
4. Confidence (0-100): How significant is this moment for the character?

Return ONLY valid JSON in this exact format:
{{
  "moments": [
    {{
      "character_name": "Character Name",
      "moment_type": "action",
      "content": "Description of the moment",
      "confidence": 85
    }}
  ]
}}

If no moments found, return {{"moments": []}}. Return ONLY the JSON, no other text."""
            
            system_prompt = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=settings.service_defaults.get('extraction_service', {}).get('character_memory_batch_max_tokens', 1500)
            )
            
            logger.warning(f"RAW LLM RESPONSE - CHARACTER MOMENTS BATCH:\n{response}")
            
            return self._parse_moments_response(response)
            
        except Exception as e:
            logger.error(f"Main LLM batch character moment extraction failed: {e}")
            return []
    
    async def _llm_extract_moments(
        self,
        scene_content: str,
        character_names: List[str],
        user_id: int,
        user_settings: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to extract character moments from scene
        Tries extraction model first, falls back to main LLM if enabled.
        
        Args:
            scene_content: Scene text
            character_names: List of character names in the story
            user_id: User ID
            user_settings: User settings
            
        Returns:
            List of moment dictionaries
        """
        # Try extraction model first if enabled
        extraction_service = self._get_extraction_service(user_settings)
        if extraction_service:
            try:
                logger.info(f"Using extraction model for character moment extraction (user {user_id})")
                moments = await extraction_service.extract_character_moments(
                    scene_content=scene_content,
                    character_names=character_names
                )
                
                # Validate and normalize moments
                validated_moments = self._validate_moments(moments)
                if validated_moments:
                    logger.info(f"Extraction model successfully extracted {len(validated_moments)} moments")
                    return validated_moments
                else:
                    logger.warning("Extraction model returned no valid moments, falling back to main LLM")
            except Exception as e:
                logger.warning(f"Extraction model failed: {e}, falling back to main LLM")
                # Continue to fallback
        
        # Fallback to main LLM
        fallback_enabled = user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
        if not fallback_enabled and extraction_service:
            logger.warning("Extraction model failed and fallback disabled, returning empty results")
            return []
        
        try:
            logger.info(f"Using main LLM for character moment extraction (user {user_id})")
            
            prompt = f"""Analyze the following scene and extract significant character moments for these characters: {', '.join(character_names)}

Scene:
{scene_content}

For each significant character moment, identify:
1. Character name
2. Moment type: "action" (physical action), "dialogue" (important speech), "development" (character growth/change), or "relationship" (interaction with others)
3. Brief description of the moment (1-2 sentences)
4. Confidence (0-100): How significant is this moment for the character?

Return ONLY valid JSON in this exact format:
{{
  "moments": [
    {{
      "character_name": "Character Name",
      "moment_type": "action",
      "content": "Description of the moment",
      "confidence": 85
    }}
  ]
}}

If no moments found, return {{"moments": []}}. Return ONLY the JSON, no other text."""
            
            system_prompt = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=settings.service_defaults.get('extraction_service', {}).get('character_memory_single_max_tokens', 500)
            )
            
            logger.warning(f"RAW LLM RESPONSE - CHARACTER MOMENTS:\n{response}")
            
            return self._parse_moments_response(response)
            
        except Exception as e:
            logger.error(f"Main LLM character moment extraction failed: {e}")
            return []
    
    def _validate_moments(self, moments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate and normalize moment dictionaries
        
        Args:
            moments: List of raw moment dictionaries
            
        Returns:
            List of validated moment dictionaries
        """
        validated = []
        for moment in moments:
            try:
                char_name = moment.get('character_name', '').strip()
                moment_type = moment.get('moment_type', 'action').strip().lower()
                content = moment.get('content', '').strip()
                confidence = moment.get('confidence', 70)
                
                # Validate moment_type
                if moment_type not in ['action', 'dialogue', 'development', 'relationship']:
                    logger.warning(f"Invalid moment_type '{moment_type}', defaulting to 'action'")
                    moment_type = 'action'
                
                # Validate confidence
                try:
                    confidence = int(confidence)
                    confidence = min(max(confidence, 0), 100)
                except (ValueError, TypeError):
                    confidence = 70
                
                if char_name and content:
                    validated.append({
                        'character_name': char_name,
                        'moment_type': moment_type,
                        'content': content,
                        'confidence': confidence
                    })
                else:
                    logger.warning(f"Skipping moment with missing character_name or content: {moment}")
                    
            except Exception as e:
                logger.warning(f"Failed to validate moment: {moment}, error: {e}")
                continue
        
        return validated
    
    def _parse_moments_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse LLM JSON response for character moments.
        
        Args:
            response: LLM JSON response text
            
        Returns:
            List of moment dictionaries
        """
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
            
            # Extract moments array
            moments_list = data.get('moments', [])
            
            # Validate and normalize moments
            validated_moments = self._validate_moments(moments_list)
            
            logger.warning(f"PARSING RESULT: Extracted {len(validated_moments)} character moments from JSON")
            
            return validated_moments
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Original response was: {response}")
            return []
        except Exception as e:
            logger.error(f"Failed to parse moments response: {e}")
            return []
    
    async def get_character_arc(
        self,
        character_id: int,
        story_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get chronological character arc
        
        Args:
            character_id: Character ID
            story_id: Story ID
            db: Database session
            
        Returns:
            List of character moments in chronological order
        """
        try:
            # Get from database
            moments = db.query(CharacterMemory).filter(
                CharacterMemory.character_id == character_id,
                CharacterMemory.story_id == story_id
            ).order_by(CharacterMemory.sequence_order).all()
            
            arc = []
            for moment in moments:
                arc.append({
                    'id': moment.id,
                    'scene_id': moment.scene_id,
                    'sequence': moment.sequence_order,
                    'moment_type': moment.moment_type.value,
                    'content': moment.content,
                    'confidence': moment.confidence_score,
                    'timestamp': moment.created_at.isoformat() if moment.created_at else datetime.utcnow().isoformat()
                })
            
            return arc
            
        except Exception as e:
            logger.error(f"Failed to get character arc: {e}")
            return []
    
    async def get_relevant_character_moments(
        self,
        character_id: int,
        story_id: int,
        query_text: str,
        top_k: int = 3,
        moment_type: Optional[str] = None,
        db: Session = None
    ) -> List[Dict[str, Any]]:
        """
        Get semantically relevant character moments
        
        Args:
            character_id: Character ID
            story_id: Story ID
            query_text: Query text (current situation)
            top_k: Number of results
            moment_type: Optional filter by moment type
            db: Database session
            
        Returns:
            List of relevant character moments
        """
        if not self.semantic_memory:
            logger.warning("Semantic memory not available")
            return []
        
        try:
            # Search using semantic memory
            moments = await self.semantic_memory.search_character_moments(
                character_id=character_id,
                query_text=query_text,
                story_id=story_id,
                top_k=top_k,
                moment_type=moment_type
            )
            
            # Enrich with database info if needed
            if db:
                for moment in moments:
                    char_memory = db.query(CharacterMemory).filter(
                        CharacterMemory.embedding_id == moment['embedding_id']
                    ).first()
                    
                    if char_memory:
                        moment['content'] = char_memory.content
                        moment['confidence'] = char_memory.confidence_score
            
            return moments
            
        except Exception as e:
            logger.error(f"Failed to get relevant character moments: {e}")
            return []
    
    async def get_character_relationships(
        self,
        character_id: int,
        story_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get relationship moments for a character
        
        Args:
            character_id: Character ID
            story_id: Story ID
            db: Database session
            
        Returns:
            List of relationship moments
        """
        try:
            moments = db.query(CharacterMemory).filter(
                CharacterMemory.character_id == character_id,
                CharacterMemory.story_id == story_id,
                CharacterMemory.moment_type == MomentType.RELATIONSHIP
            ).order_by(CharacterMemory.sequence_order).all()
            
            relationships = []
            for moment in moments:
                relationships.append({
                    'id': moment.id,
                    'scene_id': moment.scene_id,
                    'sequence': moment.sequence_order,
                    'content': moment.content,
                    'confidence': moment.confidence_score,
                    'timestamp': moment.created_at.isoformat() if moment.created_at else datetime.utcnow().isoformat()
                })
            
            return relationships
            
        except Exception as e:
            logger.error(f"Failed to get character relationships: {e}")
            return []
    
    async def delete_character_moments(self, scene_id: int, db: Session):
        """
        Delete all character moments for a scene

        Args:
            scene_id: Scene ID
            db: Database session
        """
        try:
            # Delete from database (embedding vectors are on the row, deleted with it)
            deleted = db.query(CharacterMemory).filter(
                CharacterMemory.scene_id == scene_id
            ).delete()

            db.commit()
            logger.info(f"Deleted {deleted} character moments for scene {scene_id}")

        except Exception as e:
            logger.error(f"Failed to delete character moments: {e}")
            db.rollback()


# Global service instance
_character_memory_service: Optional[CharacterMemoryService] = None


def get_character_memory_service() -> CharacterMemoryService:
    """Get the global character memory service instance"""
    global _character_memory_service
    if _character_memory_service is None:
        _character_memory_service = CharacterMemoryService()
    return _character_memory_service

