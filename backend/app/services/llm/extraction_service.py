"""
Extraction LLM Service

Provider-agnostic service for using small local models (via OpenAI-compatible APIs)
for extraction tasks like plot event extraction. Optimized for fast, cost-effective extraction.
"""

import litellm
from typing import Dict, Any, List, Tuple, Optional
import logging
import time
import json
import aiohttp
from aiohttp import ClientTimeout
from .prompts import prompt_manager

logger = logging.getLogger(__name__)


class ExtractionLLMService:
    """OpenAI-compatible extraction service for small local models"""
    
    def __init__(self, url: str, model: str, api_key: str = "", 
                 temperature: float = 0.3, max_tokens: int = 1000):
        """
        Initialize extraction service
        
        Args:
            url: OpenAI-compatible API endpoint URL (e.g., http://localhost:1234/v1)
            model: Model name to use
            api_key: API key if required (empty string for local servers)
            temperature: Temperature for generation (default 0.3 for more deterministic)
            max_tokens: Maximum tokens for response (default 1000)
        """
        self.url = url.rstrip('/')
        # Ensure URL ends with /v1 for OpenAI-compatible endpoints
        if not self.url.endswith('/v1'):
            self.url = f"{self.url}/v1"
        
        self.model = model
        self.api_key = api_key or "not-needed"  # Some servers don't require key
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Short timeouts optimized for small local models
        # Base timeout for single extractions, will be increased for batch/combined calls
        self.timeout = ClientTimeout(total=30, connect=5)  # Increased connect timeout for local LLMs
        
        # Configure LiteLLM for OpenAI-compatible endpoint
        self._configure_litellm()
    
    def _configure_litellm(self):
        """Configure LiteLLM for extraction service"""
        # Disable verbose logging
        litellm.set_verbose = False
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        
        # Set environment variables to suppress warnings
        import os
        os.environ["LITELLM_LOG"] = "ERROR"
        os.environ["LITELLM_LOG_LEVEL"] = "ERROR"
        os.environ["LITELLM_SUPPRESS_DEBUG_INFO"] = "true"
        os.environ["LITELLM_DROP_PARAMS"] = "true"
        
        logger.info(f"ExtractionLLMService configured: url={self.url}, model={self.model}")
    
    def _build_model_string(self) -> str:
        """Build LiteLLM model string for OpenAI-compatible endpoint"""
        # Use openai/ prefix for OpenAI-compatible APIs
        return f"openai/{self.model}"
    
    def _get_generation_params(self, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Get generation parameters for API calls"""
        params = {
            "model": self._build_model_string(),
            "api_base": self.url,
            "api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        return params
    
    async def test_connection(self) -> Tuple[bool, str, float]:
        """
        Test if the extraction endpoint is available
        
        Returns:
            Tuple of (success: bool, message: str, response_time: float)
        """
        start_time = time.time()
        try:
            from litellm import acompletion
            
            # Simple test request
            params = self._get_generation_params(max_tokens=10)
            response = await acompletion(
                **params,
                messages=[{"role": "user", "content": "Say 'OK'"}],
                timeout=self.timeout.total
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            if content:
                return True, f"Connection successful (model responded)", response_time
            else:
                return False, "Model responded but returned empty content", response_time
            
        except Exception as e:
            response_time = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Extraction model connection test failed: {error_msg}")
            
            # Provide helpful error messages
            if "404" in error_msg or "Not Found" in error_msg:
                return False, f"Endpoint not found at {self.url}. Check if the service is running.", response_time
            elif "401" in error_msg or "Unauthorized" in error_msg:
                return False, "Authentication failed. Check your API key.", response_time
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                return False, f"Cannot connect to {self.url}. Is the service running?", response_time
            else:
                return False, f"Connection failed: {error_msg}", response_time
    
    async def extract_plot_events(
        self, 
        scene_content: str, 
        thread_context: str = "",
        system_prompt: str = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
    ) -> List[Dict[str, Any]]:
        """
        Extract plot events from a single scene
        
        Args:
            scene_content: Scene text to analyze
            thread_context: Context about existing plot threads
            system_prompt: System prompt for the model
            
        Returns:
            List of event dictionaries
        """
        try:
            from litellm import acompletion
            
            # Build prompt
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
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            return self._parse_json_response(content)
            
        except Exception as e:
            logger.error(f"Failed to extract plot events with extraction model: {e}")
            raise
    
    async def extract_plot_events_batch(
        self,
        scenes_content: str,
        thread_context: str = "",
        system_prompt: str = "You are an expert story analyst skilled at identifying plot events, narrative threads, and story structure."
    ) -> List[Dict[str, Any]]:
        """
        Extract plot events from multiple scenes in batch
        
        Args:
            scenes_content: Multiple scenes text (with scene markers)
            thread_context: Context about existing plot threads
            system_prompt: System prompt for the model
            
        Returns:
            List of event dictionaries
        """
        try:
            from litellm import acompletion
            
            # Build batch prompt
            prompt = f"""Analyze the following scenes and extract significant plot events.{thread_context}

Scenes:
{scenes_content}

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
            
            params = self._get_generation_params(max_tokens=self.max_tokens * 2)  # Allow more tokens for batch
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total * 2  # Longer timeout for batch
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            return self._parse_json_response(content)
            
        except Exception as e:
            logger.error(f"Failed to extract plot events (batch) with extraction model: {e}")
            raise
    
    def _parse_json_response(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse JSON response from model, handling common formatting issues
        
        Args:
            content: Raw response content
            
        Returns:
            List of event dictionaries
        """
        try:
            # Clean response (remove markdown code blocks if present)
            response_clean = content.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Parse JSON
            data = json.loads(response_clean)
            
            # Extract events array
            events_list = data.get('events', [])
            
            if not isinstance(events_list, list):
                logger.warning(f"Expected events array, got {type(events_list)}")
                return []
            
            return events_list
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nContent: {content[:500]}")
            raise ValueError(f"Invalid JSON response from extraction model: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            raise
    
    def _parse_json_dict(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON response as dictionary (for non-array responses)
        
        Args:
            content: Raw response content
            
        Returns:
            Dictionary from JSON response
        """
        try:
            # Clean response (remove markdown code blocks if present)
            response_clean = content.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Parse JSON
            data = json.loads(response_clean)
            
            if not isinstance(data, dict):
                logger.warning(f"Expected dictionary, got {type(data)}")
                return {}
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nContent: {content[:500]}")
            raise ValueError(f"Invalid JSON response from extraction model: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            raise
    
    async def extract_character_moments(
        self,
        scene_content: str,
        character_names: List[str],
        system_prompt: str = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
    ) -> List[Dict[str, Any]]:
        """
        Extract character moments from a single scene
        
        Args:
            scene_content: Scene text to analyze
            character_names: List of character names to look for
            system_prompt: System prompt for the model
            
        Returns:
            List of moment dictionaries
        """
        try:
            from litellm import acompletion
            
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
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total
            )
            
            content = response.choices[0].message.content.strip()
            data = self._parse_json_dict(content)
            return data.get('moments', [])
            
        except Exception as e:
            logger.error(f"Failed to extract character moments with extraction model: {e}")
            raise
    
    async def extract_character_moments_batch(
        self,
        batch_content: str,
        character_names: List[str],
        system_prompt: str = "You are an expert literary analyst skilled at identifying significant character moments and development in narratives."
    ) -> List[Dict[str, Any]]:
        """
        Extract character moments from multiple scenes in batch
        
        Args:
            batch_content: Multiple scenes text (with scene markers)
            character_names: List of character names to look for
            system_prompt: System prompt for the model
            
        Returns:
            List of moment dictionaries
        """
        try:
            from litellm import acompletion
            
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
            
            params = self._get_generation_params(max_tokens=self.max_tokens * 2)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total * 2
            )
            
            content = response.choices[0].message.content.strip()
            data = self._parse_json_dict(content)
            return data.get('moments', [])
            
        except Exception as e:
            logger.error(f"Failed to extract character moments (batch) with extraction model: {e}")
            raise
    
    async def extract_npcs(
        self,
        scene_content: str,
        scene_sequence: int,
        explicit_character_names: List[str],
        system_prompt: str = "You are a precise story analysis assistant. Extract NPCs and named entities from scenes. Return only valid JSON."
    ) -> Dict[str, Any]:
        """
        Extract NPCs from a scene
        
        Args:
            scene_content: Scene text to analyze
            scene_sequence: Scene sequence number
            explicit_character_names: List of characters already tracked (exclude these)
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with 'npcs' array
        """
        try:
            from litellm import acompletion
            
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
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract NPCs with extraction model: {e}")
            raise
    
    async def extract_npcs_batch(
        self,
        batch_content: str,
        explicit_character_names: List[str],
        system_prompt: str = "You are a precise story analysis assistant. Extract NPCs and named entities from scenes. Return only valid JSON."
    ) -> Dict[str, Any]:
        """
        Extract NPCs from multiple scenes in batch
        
        Args:
            batch_content: Multiple scenes text (with scene markers)
            explicit_character_names: List of characters already tracked (exclude these)
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with 'npcs' array
        """
        try:
            from litellm import acompletion
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            
            prompt = f"""Analyze the following scenes and extract ALL named entities (characters, beings, entities) 
that are NOT in the explicit character list.

{batch_content}

Explicit Characters (already tracked): {explicit_names_str}

Extract ALL named entities that:
- Are mentioned by name
- Are NOT in the explicit character list above
- Could be characters, NPCs, entities, beings, or important figures
- Have dialogue, perform actions, or have relationships in the scenes

For each NPC, identify:
- Name (exact name as mentioned)
- Mention count (how many times mentioned across scenes)
- Has dialogue (true/false)
- Has actions (true/false - performs actions)
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
            
            params = self._get_generation_params(max_tokens=self.max_tokens * 2)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total * 2
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract NPCs (batch) with extraction model: {e}")
            raise
    
    async def extract_entity_states(
        self,
        scene_content: str,
        scene_sequence: int,
        character_names: List[str],
        system_prompt: str = "You are a precise story analysis assistant. Extract entity state changes and return only valid JSON."
    ) -> Dict[str, Any]:
        """
        Extract entity state changes from a scene
        
        Args:
            scene_content: Scene text to analyze
            scene_sequence: Scene sequence number
            character_names: List of known character names
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with 'characters', 'locations', 'objects' arrays
        """
        try:
            from litellm import acompletion
            
            prompt = f"""Analyze this story scene and extract entity state changes.

Scene (Sequence #{scene_sequence}):
{scene_content}

Known Characters: {', '.join(character_names)}

Extract the following as JSON:
1. Character state changes (location, emotional state, possessions, knowledge, relationships)
2. Location information (name, condition, atmosphere, occupants)
3. Important objects (name, location, owner, condition)

CRITICAL INSTRUCTIONS FOR OBJECT EXTRACTION:
- Only extract objects that are PLOT-RELEVANT:
  * Used in actions by characters (e.g., "Rambo drew his gun")
  * Possessed/carried by characters (e.g., "Sarah's phone")
  * Mentioned 2+ times in the scene
  * Central to plot events (not trivial items like phones, keys unless central to action)
- DO NOT extract everyday items unless they are actively used or central to the scene
- For "condition": Provide ONLY factual, observable physical condition (damaged, intact, locked, open, broken, pristine, etc.)
  * BAD: "Silent confirmation of a rendezvous" (interpretive)
  * GOOD: "intact", "damaged", "locked"
- For "significance": Provide ONLY factual role in the scene (used by X, mentioned in Y, carried by Z)
  * BAD: "A symbol of active planning and intention" (interpretive/symbolic)
  * GOOD: "used by Rambo to call for backup", "carried by Sarah", "mentioned in conversation"
- NO interpretive, symbolic, or narrative importance descriptions

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
      "condition": "factual physical condition only (damaged, intact, locked, etc.) or null",
      "significance": "factual role in scene only (used by X, mentioned in Y) or null"
    }}
  ]
}}

If no changes for a category, use empty array. Return ONLY the JSON, no other text."""
            
            params = self._get_generation_params()
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract entity states with extraction model: {e}")
            raise
    
    async def extract_character_details(
        self,
        character_name: str,
        character_scenes_text: str,
        system_prompt: str = "You are a detailed character profiling assistant. Analyze all appearances of a character in a story and extract comprehensive details about them. Be thorough but accurate - only include information that is clearly supported by the text. Return ONLY valid JSON, no other text."
    ) -> Dict[str, Any]:
        """
        Extract detailed character information from scenes
        
        Args:
            character_name: Name of character to analyze
            character_scenes_text: All scenes where character appears (formatted)
            system_prompt: System prompt for the model
            
        Returns:
            Dictionary with character details
        """
        try:
            from litellm import acompletion
            
            prompt = f"""Analyze all appearances of the character "{character_name}" in the following story scenes.
Extract comprehensive details about this character:

Story scenes featuring {character_name}:
{character_scenes_text}

Extract the following information:
- Physical description and appearance (how they look, dress, distinctive features)
- Personality traits (list of adjectives describing their character)
- Background and history (their past, where they're from, important life events)
- Goals and motivations (what they want, what drives them)
- Fears and weaknesses (what they're afraid of, their vulnerabilities)
- Brief overall description (2-3 sentence summary of who they are)
- Suggested role in the story (protagonist, antagonist, ally, mentor, love_interest, comic_relief, mysterious, or other)

Return valid JSON with this exact structure:
{{
  "name": "Character Name",
  "description": "Overall 2-3 sentence description",
  "personality_traits": ["trait1", "trait2", "trait3"],
  "background": "Background and history text",
  "goals": "Goals and motivations text",
  "fears": "Fears and weaknesses text",
  "appearance": "Physical description text",
  "suggested_role": "role_name"
}}

Return ONLY the JSON object, no other text or markdown formatting."""
            
            params = self._get_generation_params(max_tokens=1500)
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                timeout=self.timeout.total * 2
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_dict(content)
            
        except Exception as e:
            logger.error(f"Failed to extract character details with extraction model: {e}")
            raise
    
    def _calculate_batch_timeout(self, num_scenes: int) -> float:
        """
        Calculate timeout for batch extraction based on number of scenes.
        Local LLMs process slower, so we use generous timeouts.
        
        Args:
            num_scenes: Number of scenes in batch
            
        Returns:
            Timeout in seconds
        """
        # Base timeout: 120 seconds (4x single extraction)
        # Scale with batch size: +10 seconds per scene
        # Max: 300 seconds (5 minutes)
        timeout = 120 + (num_scenes * 10)
        return min(timeout, 300)
    
    def _calculate_batch_max_tokens(self, num_scenes: int) -> int:
        """
        Calculate max_tokens for batch extraction based on number of scenes.
        
        Args:
            num_scenes: Number of scenes in batch
            
        Returns:
            Max tokens for response
        """
        # Base: 3000-4000 tokens (3x individual)
        # Scale with batch size
        base_tokens = 3500
        scaled_tokens = int(base_tokens * (1 + num_scenes / 5))
        # Max cap: 8000 tokens
        return min(scaled_tokens, 8000)
    
    def _parse_combined_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse combined JSON response with robust error handling.
        Handles malformed JSON, partial responses, and missing sections.
        
        Args:
            content: Raw response content
            
        Returns:
            Dictionary with 'character_moments', 'npcs', 'plot_events', 'entity_states' keys
            Missing sections will be empty arrays/objects
        """
        result = {
            'character_moments': [],
            'npcs': [],
            'plot_events': [],
            'entity_states': {
                'characters': [],
                'locations': [],
                'objects': []
            }
        }
        
        try:
            # Clean response (remove markdown code blocks if present)
            response_clean = content.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            elif response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Try to parse full JSON
            try:
                data = json.loads(response_clean)
                
                # Extract each section independently
                if 'character_moments' in data and isinstance(data['character_moments'], list):
                    result['character_moments'] = data['character_moments']
                elif 'moments' in data and isinstance(data['moments'], list):
                    # Handle alternative key name
                    result['character_moments'] = data['moments']
                
                if 'npcs' in data:
                    if isinstance(data['npcs'], list):
                        result['npcs'] = data['npcs']
                    elif isinstance(data['npcs'], dict) and 'npcs' in data['npcs']:
                        # Handle nested structure
                        result['npcs'] = data['npcs']['npcs'] if isinstance(data['npcs']['npcs'], list) else []
                
                if 'plot_events' in data and isinstance(data['plot_events'], list):
                    result['plot_events'] = data['plot_events']
                elif 'events' in data and isinstance(data['events'], list):
                    # Handle alternative key name
                    result['plot_events'] = data['events']
                
                # Parse entity_states
                if 'entity_states' in data and isinstance(data['entity_states'], dict):
                    entity_states = data['entity_states']
                    if 'characters' in entity_states and isinstance(entity_states['characters'], list):
                        result['entity_states']['characters'] = entity_states['characters']
                    if 'locations' in entity_states and isinstance(entity_states['locations'], list):
                        result['entity_states']['locations'] = entity_states['locations']
                    if 'objects' in entity_states and isinstance(entity_states['objects'], list):
                        result['entity_states']['objects'] = entity_states['objects']
                
                logger.info(f"Successfully parsed combined extraction: {len(result['character_moments'])} moments, "
                          f"{len(result['npcs'])} NPCs, {len(result['plot_events'])} events, "
                          f"{len(result['entity_states']['characters'])} character states, "
                          f"{len(result['entity_states']['locations'])} location states, "
                          f"{len(result['entity_states']['objects'])} object states")
                return result
                
            except json.JSONDecodeError:
                # Try to extract partial JSON using regex
                import re
                
                # Try to find JSON objects for each section
                moments_match = re.search(r'"character_moments"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if not moments_match:
                    moments_match = re.search(r'"moments"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if moments_match:
                    try:
                        moments_json = json.loads(f'[{moments_match.group(1)}]')
                        result['character_moments'] = moments_json if isinstance(moments_json, list) else []
                    except:
                        pass
                
                npcs_match = re.search(r'"npcs"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if npcs_match:
                    try:
                        npcs_json = json.loads(f'[{npcs_match.group(1)}]')
                        result['npcs'] = npcs_json if isinstance(npcs_json, list) else []
                    except:
                        pass
                
                events_match = re.search(r'"plot_events"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if not events_match:
                    events_match = re.search(r'"events"\s*:\s*\[(.*?)\]', response_clean, re.DOTALL)
                if events_match:
                    try:
                        events_json = json.loads(f'[{events_match.group(1)}]')
                        result['plot_events'] = events_json if isinstance(events_json, list) else []
                    except:
                        pass
                
                # Try to parse entity_states with regex (less reliable but attempt it)
                entity_states_match = re.search(r'"entity_states"\s*:\s*\{(.*?)\}', response_clean, re.DOTALL)
                if entity_states_match:
                    try:
                        entity_states_json = json.loads(f'{{{entity_states_match.group(1)}}}')
                        if isinstance(entity_states_json, dict):
                            if 'characters' in entity_states_json and isinstance(entity_states_json['characters'], list):
                                result['entity_states']['characters'] = entity_states_json['characters']
                            if 'locations' in entity_states_json and isinstance(entity_states_json['locations'], list):
                                result['entity_states']['locations'] = entity_states_json['locations']
                            if 'objects' in entity_states_json and isinstance(entity_states_json['objects'], list):
                                result['entity_states']['objects'] = entity_states_json['objects']
                    except:
                        pass
                
                if any(result.values()) or any(result['entity_states'].values()):
                    logger.warning(f"Partially parsed combined extraction using regex: {len(result['character_moments'])} moments, "
                                 f"{len(result['npcs'])} NPCs, {len(result['plot_events'])} events, "
                                 f"{len(result['entity_states']['characters'])} character states")
                    return result
                else:
                    raise
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse combined JSON response: {e}\nContent preview: {content[:500]}")
            # Return empty result instead of raising - caller can fallback
            return result
        except Exception as e:
            logger.error(f"Unexpected error parsing combined response: {e}\nContent preview: {content[:500]}")
            return result
    
    async def extract_all_batch(
        self,
        batch_content: str,
        character_names: List[str],
        explicit_character_names: List[str],
        thread_context: str = "",
        num_scenes: int = 1
    ) -> Dict[str, Any]:
        """
        Extract character moments, NPCs, plot events, and entity states from multiple scenes in a single LLM call.
        This combines four separate extractions into one for efficiency.
        
        Args:
            batch_content: Multiple scenes text (with scene markers)
            character_names: List of explicit character names (for character moments and entity states)
            explicit_character_names: List of characters already tracked (exclude from NPCs)
            thread_context: Context about existing plot threads
            num_scenes: Number of scenes in batch (for timeout/token calculation)
            
        Returns:
            Dictionary with 'character_moments', 'npcs', 'plot_events', 'entity_states' keys
        """
        try:
            from litellm import acompletion
            
            explicit_names_str = ", ".join(explicit_character_names) if explicit_character_names else "None"
            character_names_str = ", ".join(character_names) if character_names else "None"
            
            # Build thread context section
            thread_section = f"\n\nActive plot threads to consider:{thread_context}" if thread_context else ""
            
            # Calculate dynamic limits based on batch size
            max_npcs_total = 10
            max_events_total = 8
            
            # Get prompts from centralized prompts.yml
            system_prompt = prompt_manager.get_prompt("entity_state_extraction.batch", "system")
            user_prompt = prompt_manager.get_prompt(
                "entity_state_extraction.batch", "user",
                character_names=character_names_str,
                explicit_names=explicit_names_str,
                thread_section=thread_section,
                batch_content=batch_content,
                max_npcs_total=max_npcs_total,
                max_events_total=max_events_total
            )
            
            # Calculate dynamic timeout and max_tokens
            timeout_seconds = self._calculate_batch_timeout(num_scenes)
            max_tokens = self._calculate_batch_max_tokens(num_scenes)
            
            params = self._get_generation_params(max_tokens=max_tokens)
            logger.info(f"Starting combined extraction: {num_scenes} scenes, timeout={timeout_seconds}s, max_tokens={max_tokens}")
            
            response = await acompletion(
                **params,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                timeout=timeout_seconds
            )
            
            content = response.choices[0].message.content.strip()
            logger.debug(f"Combined extraction response length: {len(content)} characters")
            
            # Parse with robust error handling
            return self._parse_combined_json_response(content)
            
        except Exception as e:
            logger.error(f"Failed to extract all (combined batch) with extraction model: {e}")
            raise

