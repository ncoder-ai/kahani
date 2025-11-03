"""
Character Assistant Service

Analyzes story content to detect new characters, rank them by importance,
and extract detailed character information using LLM.
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from ..models import (
    Character, StoryCharacter, Scene, SceneVariant, Chapter, Story
)
from ..services.llm.service import UnifiedLLMService
from ..services.llm.prompts import prompt_manager

logger = logging.getLogger(__name__)


def clean_llm_json(json_str: str) -> str:
    """
    Clean common JSON errors from LLM responses.
    
    Common issues:
    - Unquoted values (e.g., name: John instead of name: "John")
    - Trailing commas
    - Comments
    - Incomplete JSON fragments
    """
    # Remove any leading/trailing whitespace
    json_str = json_str.strip()
    
    # If the response is very short or looks like a fragment, return empty array
    if len(json_str) < 10 or json_str in ['"name"', '\n    "name"', 'name', '[]', '{}']:
        return '[]'
    
    # If the response looks like a fragment (starts with a key), try to wrap it
    if json_str.startswith('"') and not json_str.startswith('[') and not json_str.startswith('{'):
        # This might be a single string, wrap it in an array
        json_str = f'[{json_str}]'
    elif json_str.startswith('name') or json_str.startswith('"name"'):
        # This looks like a single object fragment, wrap it in an array
        json_str = f'[{json_str}]'
    
    # Fix unquoted values in key-value pairs
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


class CharacterAssistantService:
    """
    Service for character detection and analysis in stories.
    
    Responsibilities:
    - Analyze scene content to detect character mentions
    - Rank characters by importance and relevance
    - Extract detailed character profiles using LLM
    - Provide suggestions for character creation
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any]):
        self.user_id = user_id
        self.user_settings = user_settings
        self.llm_service = UnifiedLLMService()
        
        # Get user-configurable thresholds
        self.importance_threshold = user_settings.get('character_assistant_settings', {}).get('importance_threshold', 70)
        self.mention_threshold = user_settings.get('character_assistant_settings', {}).get('mention_threshold', 5)
    
    async def analyze_chapter_for_characters(
        self,
        db: Session,
        story_id: int,
        chapter_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze a chapter's scenes to detect character mentions.
        
        Args:
            db: Database session
            story_id: Story ID
            chapter_id: Chapter ID (optional, defaults to current chapter)
            
        Returns:
            List of character suggestions with mention counts and context
        """
        try:
            # Get chapter scenes
            if chapter_id:
                scenes = db.query(Scene).filter(
                    and_(
                        Scene.story_id == story_id,
                        Scene.chapter_id == chapter_id,
                        Scene.is_deleted == False
                    )
                ).order_by(Scene.sequence_number).all()
            else:
                # Get current chapter (most recent)
                current_chapter = db.query(Chapter).filter(
                    Chapter.story_id == story_id
                ).order_by(desc(Chapter.chapter_number)).first()
                
                if not current_chapter:
                    return []
                
                scenes = db.query(Scene).filter(
                    and_(
                        Scene.story_id == story_id,
                        Scene.chapter_id == current_chapter.id,
                        Scene.is_deleted == False
                    )
                ).order_by(Scene.sequence_number).all()
            
            if not scenes:
                return []
            
            # Get existing story characters for filtering
            existing_story_chars = db.query(StoryCharacter).filter(
                StoryCharacter.story_id == story_id
            ).all()
            existing_character_ids = {sc.character_id for sc in existing_story_chars}
            
            # First pass: Extract from characters_present JSON field
            character_mentions = {}
            
            for scene in scenes:
                # Get active variant for this scene
                active_variant = self._get_active_variant(db, scene.id)
                if not active_variant:
                    continue
                
                # Extract from characters_present field
                characters_present = active_variant.characters_present or []
                for char_name in characters_present:
                    if char_name and isinstance(char_name, str):
                        char_name = char_name.strip()
                        if char_name:
                            if char_name not in character_mentions:
                                character_mentions[char_name] = {
                                    'name': char_name,
                                    'mention_count': 0,
                                    'scenes': [],
                                    'context_snippets': []
                                }
                            character_mentions[char_name]['mention_count'] += 1
                            character_mentions[char_name]['scenes'].append(scene.sequence_number)
            
            # Second pass: LLM analysis for deeper character extraction
            scene_contents = []
            scene_content_map = {}  # Map scene number to content for mention counting
            for scene in scenes:
                active_variant = self._get_active_variant(db, scene.id)
                if active_variant and active_variant.content:
                    scene_content = active_variant.content
                    scene_contents.append(f"Scene {scene.sequence_number}: {scene_content}")
                    scene_content_map[scene.sequence_number] = scene_content
            
            if scene_contents:
                llm_characters = await self._extract_characters_with_llm(scene_contents)
                
                # Merge LLM results with existing mentions and count actual appearances
                for char_data in llm_characters:
                    char_name = char_data.get('name', '').strip()
                    if not char_name:
                        continue
                    
                    if char_name not in character_mentions:
                        character_mentions[char_name] = {
                            'name': char_name,
                            'mention_count': 0,
                            'scenes': [],
                            'context_snippets': []
                        }
                    
                    # Count actual mentions and track scene appearances
                    # Search for character name in all scenes (case-insensitive)
                    import re
                    char_name_lower = char_name.lower()
                    # Pattern to match the name as a whole word (case-insensitive)
                    pattern = re.compile(r'\b' + re.escape(char_name) + r'\b', re.IGNORECASE)
                    
                    for scene_num, scene_content in scene_content_map.items():
                        # Count mentions in this scene
                        mentions_in_scene = len(pattern.findall(scene_content))
                        if mentions_in_scene > 0:
                            character_mentions[char_name]['mention_count'] += mentions_in_scene
                            if scene_num not in character_mentions[char_name]['scenes']:
                                character_mentions[char_name]['scenes'].append(scene_num)
                    
                    # Add context snippet from LLM
                    context = char_data.get('context', '')
                    if context:
                        character_mentions[char_name]['context_snippets'].append(context)
            
            # Filter out characters already in library
            suggestions = []
            for char_name, char_data in character_mentions.items():
                # Check if character exists in user's library
                existing_char = db.query(Character).filter(
                    and_(
                        Character.name == char_name,
                        Character.creator_id == self.user_id
                    )
                ).first()
                
                if not existing_char:
                    # Calculate importance score
                    importance_score = self._calculate_importance_score(char_data)
                    
                    suggestions.append({
                        'name': char_name,
                        'mention_count': char_data['mention_count'],
                        'importance_score': importance_score,
                        'first_appearance_scene': min(char_data['scenes']) if char_data['scenes'] else 0,
                        'last_appearance_scene': max(char_data['scenes']) if char_data['scenes'] else 0,
                        'is_in_library': False,
                        'preview': char_data['context_snippets'][0] if char_data['context_snippets'] else '',
                        'scenes': char_data['scenes']
                    })
            
            # Sort by importance score (descending)
            suggestions.sort(key=lambda x: x['importance_score'], reverse=True)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to analyze chapter for characters: {e}")
            return []
    
    async def extract_character_details(
        self,
        db: Session,
        story_id: int,
        character_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract detailed character information using LLM analysis.
        
        Args:
            db: Database session
            story_id: Story ID
            character_name: Name of character to analyze
            
        Returns:
            Character details dictionary or None if extraction fails
        """
        response_clean = ""
        try:
            # Get all scenes where character appears
            character_scenes = await self._get_character_scenes(db, story_id, character_name)
            
            if not character_scenes:
                return None
            
            # Build context string for LLM
            scene_contexts = []
            for scene_data in character_scenes:
                scene_contexts.append(f"Scene {scene_data['sequence']}: {scene_data['content']}")
            
            character_scenes_text = "\n\n".join(scene_contexts)
            
            # Get LLM prompts
            system_prompt = prompt_manager.get_prompt("character_assistant.extraction", "system")
            user_prompt = prompt_manager.get_prompt("character_assistant.extraction", "user").format(
                character_name=character_name,
                character_scenes=character_scenes_text
            )
            
            # Call LLM
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=1500
            )
            
            # Parse JSON response
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Clean common JSON errors
            response_clean = clean_llm_json(response_clean)
            
            # Debug logging
            logger.debug(f"LLM response for character extraction: {response_clean[:200]}...")
            
            character_details = json.loads(response_clean)
            
            # Normalize fields that should be strings (convert lists to strings if needed)
            if isinstance(character_details.get('goals'), list):
                character_details['goals'] = ', '.join(str(g) for g in character_details['goals'])
            elif not isinstance(character_details.get('goals'), str):
                character_details['goals'] = str(character_details.get('goals', ''))
            
            if isinstance(character_details.get('fears'), list):
                character_details['fears'] = ', '.join(str(f) for f in character_details['fears'])
            elif not isinstance(character_details.get('fears'), str):
                character_details['fears'] = str(character_details.get('fears', ''))
            
            # Ensure other string fields are strings
            for field in ['name', 'description', 'background', 'appearance', 'suggested_role']:
                if field in character_details and not isinstance(character_details[field], str):
                    character_details[field] = str(character_details[field])
            
            # Ensure personality_traits is a list
            if 'personality_traits' in character_details:
                if isinstance(character_details['personality_traits'], str):
                    # Split comma-separated or newline-separated traits
                    character_details['personality_traits'] = [
                        t.strip() for t in re.split(r'[,;\n]', character_details['personality_traits']) 
                        if t.strip()
                    ]
                elif not isinstance(character_details['personality_traits'], list):
                    character_details['personality_traits'] = []
            else:
                character_details['personality_traits'] = []
            
            # Add metadata
            character_details['confidence'] = 0.85  # Could be calculated based on scene count
            character_details['scenes_analyzed'] = [s['sequence'] for s in character_scenes]
            
            return character_details
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.error(f"Raw response: {response_clean[:500]}")
            raise ValueError(f"Failed to parse character analysis response: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to extract character details: {e}")
            logger.error(f"Raw response: {response_clean[:500]}")
            raise Exception(f"Failed to extract character details: {str(e)}")
    
    async def check_character_importance(
        self,
        db: Session,
        story_id: int,
        chapter_id: Optional[int] = None
    ) -> bool:
        """
        Check if any new characters cross the importance threshold.
        
        Args:
            db: Database session
            story_id: Story ID
            chapter_id: Chapter ID (optional)
            
        Returns:
            True if important characters detected, False otherwise
        """
        try:
            suggestions = await self.analyze_chapter_for_characters(db, story_id, chapter_id)
            
            # Check if any character meets the thresholds
            for suggestion in suggestions:
                if (suggestion['importance_score'] >= self.importance_threshold and 
                    suggestion['mention_count'] >= self.mention_threshold):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check character importance: {e}")
            return False
    
    def _get_active_variant(self, db: Session, scene_id: int) -> Optional[SceneVariant]:
        """Get the active variant for a scene."""
        # For now, get the first variant (this could be improved with story flow logic)
        return db.query(SceneVariant).filter(
            SceneVariant.scene_id == scene_id
        ).order_by(SceneVariant.variant_number).first()
    
    async def _extract_characters_with_llm(self, scene_contents: List[str]) -> List[Dict[str, str]]:
        """Extract characters using LLM analysis."""
        response_clean = ""
        try:
            scene_content_text = "\n\n".join(scene_contents)
            
            # Validation: Check if scene content is empty or too short
            if not scene_content_text or len(scene_content_text) < 10:
                logger.warning("Scene content is empty or too short, skipping LLM analysis")
                return []
            
            # Log what we're sending to LLM
            logger.info(f"Calling LLM for character detection")
            logger.info(f"Scene content length: {len(scene_content_text)} chars")
            logger.info(f"Number of scenes: {len(scene_contents)}")
            
            try:
                system_prompt = prompt_manager.get_prompt("character_assistant.detection", "system")
                logger.info(f"System prompt loaded: {len(system_prompt)} chars")
            except Exception as e:
                logger.error(f"Failed to load system prompt: {e}")
                raise
            
            try:
                user_prompt_template = prompt_manager.get_prompt("character_assistant.detection", "user")
                logger.info(f"User prompt template loaded: {len(user_prompt_template)} chars")
                user_prompt = user_prompt_template.format(scene_content=scene_content_text)
                logger.info(f"User prompt formatted: {len(user_prompt)} chars")
            except Exception as e:
                logger.error(f"Failed to format user prompt: {e}")
                logger.error(f"Template: {user_prompt_template[:200]}")
                raise
            
            logger.debug(f"System prompt: {system_prompt[:200]}...")
            logger.debug(f"User prompt: {user_prompt[:500]}...")
            
            try:
                logger.info("Calling LLM service.generate()...")
                response = await self.llm_service.generate(
                    prompt=user_prompt,
                    user_id=self.user_id,
                    user_settings=self.user_settings,
                    system_prompt=system_prompt,
                    max_tokens=2000
                )
                logger.info("LLM service.generate() completed")
            except Exception as e:
                logger.error(f"LLM service.generate() failed: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise
            
            # Log raw LLM response
            logger.info(f"Raw LLM response received (length: {len(response)})")
            logger.info(f"Raw response: {response[:500]}")
            
            # Parse JSON response
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            response_clean = clean_llm_json(response_clean)
            
            # Debug logging
            logger.info(f"LLM response for character detection (length: {len(response_clean)}): {response_clean}")
            
            return json.loads(response_clean)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.error(f"Cleaned response: {response_clean[:500]}")
            logger.info("Falling back to characters_present data only")
            return []
        except Exception as e:
            logger.error(f"LLM character detection failed: {e}")
            logger.error(f"Cleaned response: {response_clean[:500]}")
            logger.info("Falling back to characters_present data only")
            return []
    
    async def _get_character_scenes(
        self,
        db: Session,
        story_id: int,
        character_name: str
    ) -> List[Dict[str, Any]]:
        """Get all scenes where a character appears."""
        scenes = []
        
        # Get all scenes in the story
        story_scenes = db.query(Scene).filter(
            and_(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            )
        ).order_by(Scene.sequence_number).all()
        
        for scene in story_scenes:
            active_variant = self._get_active_variant(db, scene.id)
            if not active_variant or not active_variant.content:
                continue
            
            # Check if character is mentioned in this scene
            content_lower = active_variant.content.lower()
            char_name_lower = character_name.lower()
            
            if char_name_lower in content_lower:
                scenes.append({
                    'sequence': scene.sequence_number,
                    'content': active_variant.content,
                    'scene_id': scene.id
                })
        
        return scenes
    
    def _calculate_importance_score(self, char_data: Dict[str, Any]) -> int:
        """
        Calculate importance score for a character based on various factors.
        
        Factors:
        - Mention count (0-40 points)
        - Scene spread (0-20 points) 
        - Recent appearances (0-20 points)
        - Context richness (0-20 points)
        """
        score = 0
        
        # Mention count (0-40 points)
        mention_count = char_data.get('mention_count', 0)
        score += min(mention_count * 2, 40)
        
        # Scene spread (0-20 points)
        scenes = char_data.get('scenes', [])
        if scenes:
            scene_spread = max(scenes) - min(scenes) + 1
            score += min(scene_spread * 2, 20)
        
        # Recent appearances (0-20 points)
        # This would need story context to determine what's "recent"
        # For now, give points based on total scenes
        score += min(len(scenes) * 3, 20)
        
        # Context richness (0-20 points)
        context_snippets = char_data.get('context_snippets', [])
        if context_snippets:
            # Longer context snippets suggest more important character
            avg_context_length = sum(len(snippet) for snippet in context_snippets) / len(context_snippets)
            score += min(int(avg_context_length / 10), 20)
        
        return min(score, 100)  # Cap at 100
