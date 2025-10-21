"""
Character Memory Service

Handles extraction, storage, and retrieval of character-specific moments
for maintaining character consistency across long narratives.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from .semantic_memory import get_semantic_memory_service
from .llm.service import UnifiedLLMService
from ..models import CharacterMemory, Character, Scene, MomentType
from ..config import settings

logger = logging.getLogger(__name__)


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
                embedding_id = await self.semantic_memory.add_character_moment(
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
                
                # Create database record
                char_memory = CharacterMemory(
                    character_id=character.id,
                    scene_id=scene_id,
                    story_id=story_id,
                    moment_type=MomentType(moment_type),
                    content=content,
                    embedding_id=embedding_id,
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
    
    async def _llm_extract_moments(
        self,
        scene_content: str,
        character_names: List[str],
        user_id: int,
        user_settings: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to extract character moments from scene
        
        Args:
            scene_content: Scene text
            character_names: List of character names in the story
            user_id: User ID
            user_settings: User settings
            
        Returns:
            List of moment dictionaries
        """
        try:
            prompt = f"""Analyze the following scene and extract significant character moments for these characters: {', '.join(character_names)}

Scene:
{scene_content}

For each significant character moment, identify:
1. Character name
2. Moment type: "action" (physical action), "dialogue" (important speech), "development" (character growth/change), or "relationship" (interaction with others)
3. Brief description of the moment (1-2 sentences)
4. Confidence (0-100): How significant is this moment for the character?

Format your response as a list, one moment per line:
CHARACTER_NAME | MOMENT_TYPE | DESCRIPTION | CONFIDENCE

Only include moments that are significant for character development or plot. Skip minor actions or dialogue.
"""
            
            system_prompt = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
            
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                user_settings=user_settings,
                system_prompt=system_prompt,
                max_tokens=500
            )
            
            # Parse response
            moments = []
            lines = response.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or '|' not in line:
                    continue
                
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 4:
                    continue
                
                try:
                    character_name = parts[0]
                    moment_type = parts[1].lower()
                    content = parts[2]
                    confidence = int(re.sub(r'[^\d]', '', parts[3]) or '70')
                    
                    # Validate moment_type
                    if moment_type not in ['action', 'dialogue', 'development', 'relationship']:
                        moment_type = 'action'
                    
                    moments.append({
                        'character_name': character_name,
                        'moment_type': moment_type,
                        'content': content,
                        'confidence': min(max(confidence, 0), 100)
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse moment line: {line} - {e}")
                    continue
            
            return moments
            
        except Exception as e:
            logger.error(f"LLM moment extraction failed: {e}")
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
    
    def delete_character_moments(self, scene_id: int, db: Session):
        """
        Delete all character moments for a scene
        
        Args:
            scene_id: Scene ID
            db: Database session
        """
        try:
            moments = db.query(CharacterMemory).filter(
                CharacterMemory.scene_id == scene_id
            ).all()
            
            # Delete from vector database
            if self.semantic_memory:
                for moment in moments:
                    try:
                        # Note: ChromaDB delete is handled in semantic_memory service
                        pass
                    except Exception as e:
                        logger.warning(f"Failed to delete embedding {moment.embedding_id}: {e}")
            
            # Delete from database
            db.query(CharacterMemory).filter(
                CharacterMemory.scene_id == scene_id
            ).delete()
            
            db.commit()
            logger.info(f"Deleted character moments for scene {scene_id}")
            
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

