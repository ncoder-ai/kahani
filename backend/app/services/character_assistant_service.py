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
from sqlalchemy import and_, desc, func, or_
from ..models import (
    Character, StoryCharacter, Scene, SceneVariant, Chapter, Story
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
    - Unquoted values (e.g., name: John instead of name: "John")
    - Trailing commas
    - Comments
    - Incomplete JSON fragments
    - Unterminated strings (truncated responses)
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
    
    # Handle truncated responses (common when max_tokens is reached)
    # First, try to close any unterminated strings at the end
    # Count quotes - if odd number, we have an unterminated string
    quote_count = json_str.count('"')
    if quote_count % 2 == 1:
        # Find the last quote and see if we need to close a string
        last_quote_pos = json_str.rfind('"')
        if last_quote_pos >= 0:
            # Check if we're in the middle of a string value (not a key)
            # Look backwards from the last quote to see if there's a colon before the previous quote
            before_last_quote = json_str[:last_quote_pos]
            prev_quote_pos = before_last_quote.rfind('"')
            if prev_quote_pos >= 0:
                between_quotes = json_str[prev_quote_pos + 1:last_quote_pos]
                if ':' in between_quotes:
                    # This looks like a key, so the last quote starts a value - close it
                    json_str = json_str + '"'
    
    # If response ends abruptly (no closing bracket), try to close it
    if json_str.startswith('[') and not json_str.rstrip().endswith(']'):
        # Find the last complete object (ends with })
        last_complete_obj = json_str.rfind('}')
        if last_complete_obj > 0:
            # Extract up to the last complete object and close the array
            json_str = json_str[:last_complete_obj + 1] + ']'
        else:
            # No complete objects found, return empty array
            return '[]'
    elif json_str.startswith('{') and not json_str.rstrip().endswith('}'):
        # Find last complete key-value pair and close the object
        # Look for pattern: "key": "value",
        last_complete_pair = json_str.rfind(',')
        if last_complete_pair > 0:
            json_str = json_str[:last_complete_pair] + '}'
        else:
            # Try to close it anyway by removing trailing incomplete content
            json_str = json_str.rstrip().rstrip(',') + '}'
    
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
        self.extraction_service = None  # Will be initialized conditionally
        
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
        DEPRECATED: This method is inefficient and redundant.
        Use NPCTrackingService.get_npcs_as_suggestions() instead.
        
        This method re-extracts characters that NPCTracking already found,
        causing unnecessary LLM calls and timeouts. It sends ALL scene content
        to the LLM, which can cause 504 Gateway Timeout errors.
        
        Args:
            db: Database session
            story_id: Story ID
            chapter_id: Chapter ID (optional, defaults to current chapter)
            
        Returns:
            Empty list (deprecated - use NPC tracking instead)
        """
        logger.warning(
            f"analyze_chapter_for_characters() is deprecated for story {story_id}. "
            "Use NPCTrackingService.get_npcs_as_suggestions() instead. "
            "This method causes timeouts and redundant LLM calls."
        )
        # Return empty list - force callers to use NPC tracking
        return []
    
    async def _analyze_chapter_for_characters_OLD(
        self,
        db: Session,
        story_id: int,
        chapter_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        OLD IMPLEMENTATION - DEPRECATED
        Kept for reference only - do not use.
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

            # Get timeout from user's LLM settings
            llm_settings = user_settings.get('llm_settings', {})
            timeout_total = llm_settings.get('timeout_total', 240)

            # Create extraction service
            return ExtractionLLMService(
                url=url,
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_total=timeout_total
            )
        except Exception as e:
            logger.warning(f"Failed to initialize extraction service: {e}")
            return None

    async def extract_character_details(
        self,
        db: Session,
        story_id: int,
        character_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract detailed character information using LLM analysis.
        Tries extraction model first, falls back to main LLM if enabled.
        
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
            
            # Try extraction model first if enabled
            extraction_service = self._get_extraction_service()
            if extraction_service:
                try:
                    logger.info(f"Using extraction model for character detail extraction (user {self.user_id})")
                    character_details = await extraction_service.extract_character_details(
                        character_name=character_name,
                        character_scenes_text=character_scenes_text
                    )
                    
                    # Normalize and validate character details
                    normalized = self._normalize_character_details(character_details, character_scenes)
                    if normalized:
                        logger.info(f"Extraction model successfully extracted character details for {character_name}")
                        return normalized
                    else:
                        logger.warning("Extraction model returned invalid character details, falling back to main LLM")
                except Exception as e:
                    logger.warning(f"Extraction model failed: {e}, falling back to main LLM")
                    # Continue to fallback
            
            # Fallback to main LLM
            fallback_enabled = self.user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
            if not fallback_enabled and extraction_service:
                logger.warning("Extraction model failed and fallback disabled, returning None")
                return None
            
            logger.info(f"Using main LLM for character detail extraction (user {self.user_id})")
            
            # Get LLM prompts
            system_prompt = prompt_manager.get_prompt("character_assistant.extraction", "system")
            user_prompt = prompt_manager.get_prompt("character_assistant.extraction", "user").format(
                character_name=character_name,
                character_scenes=character_scenes_text
            )
            
            # Call LLM with increased token limit for detailed character extraction
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=settings.service_defaults.get('extraction_service', {}).get('character_profile_max_tokens', 3000)
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
            
            # Try to parse JSON, with fallback for truncated responses
            try:
                character_details = json.loads(response_clean)
            except json.JSONDecodeError as json_err:
                # If JSON parsing fails, try to extract partial data
                logger.warning(f"JSON parse error: {json_err}. Attempting to extract partial data from truncated response.")
                logger.debug(f"Truncated response: {response_clean[:1000]}")
                
                # Try to find the last complete JSON object in the response
                # Look for complete key-value pairs we can extract
                character_details = self._extract_partial_character_details(response_clean, character_name)
                
                if not character_details:
                    # If we can't extract anything, re-raise the original error
                    logger.error(f"Failed to extract any character details from truncated response")
                    raise ValueError(f"Failed to parse character analysis response (truncated): {str(json_err)}")
            
            # Normalize and validate
            normalized = self._normalize_character_details(character_details, character_scenes)
            return normalized
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.error(f"Raw response: {response_clean[:500]}")
            raise ValueError(f"Failed to parse character analysis response: {str(e)}")
        except Exception as e:
            logger.error(f"Main LLM character detail extraction failed: {e}")
            logger.error(f"Raw response: {response_clean[:500]}")
            raise Exception(f"Failed to extract character details: {str(e)}")
    
    def _extract_partial_character_details(self, truncated_json: str, character_name: str) -> Optional[Dict[str, Any]]:
        """
        Try to extract character details from a truncated JSON response.
        
        Args:
            truncated_json: Partial/incomplete JSON string
            character_name: Name of the character being extracted
            
        Returns:
            Partial character details dictionary or None if nothing can be extracted
        """
        try:
            # Try to find complete key-value pairs using regex
            # Pattern: "key": "value" or "key": value
            import re
            
            details = {"name": character_name}
            
            # Extract common character fields
            field_patterns = {
                "description": r'"description"\s*:\s*"([^"]*)"',
                "background": r'"background"\s*:\s*"([^"]*)"',
                "goals": r'"goals"\s*:\s*"([^"]*)"',
                "fears": r'"fears"\s*:\s*"([^"]*)"',
                "appearance": r'"appearance"\s*:\s*"([^"]*)"',
                "suggested_role": r'"suggested_role"\s*:\s*"([^"]*)"',
            }
            
            for field, pattern in field_patterns.items():
                match = re.search(pattern, truncated_json)
                if match:
                    details[field] = match.group(1)
            
            # Extract personality_traits (array)
            traits_match = re.search(r'"personality_traits"\s*:\s*\[(.*?)\]', truncated_json, re.DOTALL)
            if traits_match:
                traits_str = traits_match.group(1)
                # Extract individual trait strings
                trait_matches = re.findall(r'"([^"]*)"', traits_str)
                details["personality_traits"] = trait_matches
            else:
                # Try to find partial array
                traits_match = re.search(r'"personality_traits"\s*:\s*\[(.*)', truncated_json, re.DOTALL)
                if traits_match:
                    traits_str = traits_match.group(1)
                    trait_matches = re.findall(r'"([^"]*)"', traits_str)
                    details["personality_traits"] = trait_matches
                else:
                    details["personality_traits"] = []
            
            # Only return if we extracted at least one field (besides name)
            if len(details) > 1:
                logger.info(f"Extracted partial character details for {character_name}: {list(details.keys())}")
                return details
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract partial character details: {e}")
            return None
    
    def _normalize_character_details(self, character_details: Dict[str, Any], character_scenes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Normalize and validate character details dictionary
        
        Args:
            character_details: Raw character details dictionary
            character_scenes: List of scenes where character appears
            
        Returns:
            Normalized character details or None if invalid
        """
        if not isinstance(character_details, dict) or not character_details.get('name'):
            return None
        
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
        
        # Normalize suggested_voice_style
        if 'suggested_voice_style' not in character_details or not character_details['suggested_voice_style']:
            character_details['suggested_voice_style'] = 'neutral'
        
        return character_details
    
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
    
    def _get_active_variant(self, db: Session, scene_id: int, branch_id: int = None) -> Optional[SceneVariant]:
        """Get the active variant for a scene."""
        from ..models import StoryFlow
        
        # Try to get active variant from StoryFlow first (including NULL branch_id for shared scenes)
        flow_query = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene_id,
            StoryFlow.is_active == True
        )
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        flow = flow_query.first()
        
        if flow and flow.scene_variant_id:
            return db.query(SceneVariant).filter(SceneVariant.id == flow.scene_variant_id).first()
        
        # Fallback: get the first variant
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
                logger.debug(f"System prompt loaded: {len(system_prompt)} chars")
            except Exception as e:
                logger.error(f"Failed to load system prompt: {e}")
                raise
            
            try:
                user_prompt_template = prompt_manager.get_prompt("character_assistant.detection", "user")
                logger.debug(f"User prompt template loaded: {len(user_prompt_template)} chars")
                user_prompt = user_prompt_template.format(scene_content=scene_content_text)
                logger.debug(f"User prompt formatted: {len(user_prompt)} chars")
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
                    max_tokens=settings.service_defaults.get('extraction_service', {}).get('character_assistant_max_tokens', 2000)
                )
                logger.info("LLM service.generate() completed")
            except Exception as e:
                logger.error(f"LLM service.generate() failed: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise
            
            # Log raw LLM response
            logger.debug(f"Raw LLM response received (length: {len(response)})")
            logger.debug(f"Raw response: {response[:500]}")
            
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
            
            # Parse and filter to only CHARACTER entity types
            all_entities = json.loads(response_clean)
            character_list = []
            for entity in all_entities:
                entity_type = entity.get('entity_type', 'CHARACTER').upper()
                if entity_type == 'CHARACTER':
                    character_list.append(entity)
                else:
                    logger.debug(f"Filtered out non-character entity: {entity.get('name')} (type: {entity_type})")
            
            return character_list
            
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
        character_name: str,
        max_scenes: int = 10,
        branch_id: int = None
    ) -> List[Dict[str, Any]]:
        """
        Get most relevant scenes where character appears using semantic search.
        
        Instead of ALL scenes, get the top N most relevant ones to avoid timeouts.
        """
        # Get active branch if not specified
        if branch_id is None:
            from ..models import StoryBranch
            active_branch = db.query(StoryBranch).filter(
                and_(
                    StoryBranch.story_id == story_id,
                    StoryBranch.is_active == True
                )
            ).first()
            branch_id = active_branch.id if active_branch else None
        
        try:
            # Try semantic search first for better relevance
            from ..services.semantic_memory import get_semantic_memory_service
            semantic_service = get_semantic_memory_service()
            
            if semantic_service:
                # Search for scenes featuring this character
                query = f"scenes featuring {character_name}, {character_name}'s actions and dialogue"
                
                # Use semantic search to find most relevant scenes
                results = await semantic_service.search_similar_scenes(
                    query_text=query,
                    story_id=story_id,
                    top_k=max_scenes,
                    use_reranking=True
                )
                
                if results:
                    scenes = []
                    for result in results:
                        scene_id = result.get('scene_id')
                        scene = db.query(Scene).filter(Scene.id == scene_id).first()
                        # Filter by branch
                        if scene and (branch_id is None or scene.branch_id == branch_id or scene.branch_id is None):
                            variant = self._get_active_variant(db, scene.id, branch_id=branch_id)
                            if variant and variant.content:
                                # Verify character is actually mentioned
                                if character_name.lower() in variant.content.lower():
                                    scenes.append({
                                        'sequence': scene.sequence_number,
                                        'content': variant.content,
                                        'scene_id': scene.id
                                    })
                    
                    if scenes:
                        logger.info(f"Found {len(scenes)} relevant scenes for {character_name} using semantic search")
                        return scenes
        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to text search: {e}")
        
        # Fallback: text search but limit results to avoid timeouts (including NULL branch_id for shared scenes)
        scenes = []
        scene_query = db.query(Scene).filter(
            and_(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            )
        )
        if branch_id:
            scene_query = scene_query.filter(Scene.branch_id == branch_id)
        story_scenes = scene_query.order_by(Scene.sequence_number).all()
        
        for scene in story_scenes:
            if len(scenes) >= max_scenes:
                break
                
            variant = self._get_active_variant(db, scene.id, branch_id=branch_id)
            if not variant or not variant.content:
                continue
            
            # Check if character is mentioned in this scene
            if character_name.lower() in variant.content.lower():
                scenes.append({
                    'sequence': scene.sequence_number,
                    'content': variant.content,
                    'scene_id': scene.id
                })
        
        logger.info(f"Found {len(scenes)} scenes for {character_name} using text search (limited to {max_scenes})")
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
