import httpx
import json
import re
from typing import List, Dict, Any, Optional
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class LMStudioService:
    """Service for interacting with LM Studio's OpenAI-compatible API"""
    
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens
        self.temperature = settings.llm_temperature
    
    def _clean_scene_numbers(self, content: str) -> str:
        """Remove scene numbers and titles from the beginning of generated content"""
        # Remove patterns like "Scene 7:", "Scene 7: Title", etc. from the start
        # This captures the entire first line if it starts with scene numbering
        content = re.sub(r'^Scene\s+\d+:.*?(\n|$)', '', content, flags=re.IGNORECASE).strip()
        # Also remove standalone scene titles that might start with numbers
        content = re.sub(r'^\d+[:.]\s*[A-Z][^.\n]*(\n|$)', '', content).strip()
        return content
        
    async def _make_request(self, prompt: str, system_prompt: str = "", max_tokens: int = None, user_settings: dict = None, stream: bool = False) -> str:
        """Make a request to LM Studio API with optional user settings"""
        
        headers = {
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Use user settings if provided, otherwise use defaults
        if user_settings and user_settings.get("llm_settings"):
            llm_config = user_settings["llm_settings"]
            temperature = llm_config.get("temperature", self.temperature)
            top_p = llm_config.get("top_p", 1.0)
            top_k = llm_config.get("top_k", 50)
            repetition_penalty = llm_config.get("repetition_penalty", 1.1)
            max_tokens_setting = llm_config.get("max_tokens", self.max_tokens)
            model_name = llm_config.get("model_name", self.model)
            base_url = llm_config.get("api_url", self.base_url)
            api_key = llm_config.get("api_key", self.api_key)
            api_type = llm_config.get("api_type", "openai_compatible")
        else:
            temperature = self.temperature
            top_p = 1.0
            top_k = 50
            repetition_penalty = 1.1
            max_tokens_setting = self.max_tokens
            model_name = self.model
            base_url = self.base_url
            api_key = self.api_key
            api_type = "openai_compatible"
        
        # Update headers with user's API key if provided
        if api_key and api_key != "not-needed-for-local":
            headers["Authorization"] = f"Bearer {api_key}"
        
        # Configure endpoint based on API type
        if api_type == "ollama":
            endpoint = f"{base_url}/api/chat"
        elif api_type == "koboldcpp":
            endpoint = f"{base_url}/api/v1/chat/completions"
        else:  # openai, openai_compatible
            # Handle URLs that might or might not have /v1 already
            if base_url.endswith("/v1"):
                endpoint = f"{base_url}/chat/completions"
            else:
                endpoint = f"{base_url}/v1/chat/completions"
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens or max_tokens_setting,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "stream": stream
        }
        
        logger.info(f"Making LLM request to: {endpoint}")
        logger.info(f"Using model: {model_name}")
        logger.info(f"Payload keys: {list(payload.keys())}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=60.0
                )
                response.raise_for_status()
                
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                logger.info(f"LLM response received, length: {len(content)} characters")
                return content
                
        except httpx.RequestError as e:
            logger.error(f"HTTP request failed: {e}")
            raise Exception(f"Failed to connect to LLM service: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise Exception(f"LLM service error: {e.response.status_code}")
        except KeyError as e:
            logger.error(f"Unexpected response format: {e}")
            raise Exception("Invalid response from LLM service")
    
    async def _make_streaming_request(self, prompt: str, system_prompt: str = "", max_tokens: int = None, user_settings: dict = None):
        """Make a streaming request to LM Studio API"""
        
        headers = {
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Use user settings if provided, otherwise use defaults
        if user_settings and user_settings.get("llm_settings"):
            llm_config = user_settings["llm_settings"]
            temperature = llm_config.get("temperature", self.temperature)
            top_p = llm_config.get("top_p", 1.0)
            top_k = llm_config.get("top_k", 50)
            repetition_penalty = llm_config.get("repetition_penalty", 1.1)
            max_tokens_setting = llm_config.get("max_tokens", self.max_tokens)
            model_name = llm_config.get("model_name", self.model)
            base_url = llm_config.get("api_url", self.base_url)
            api_key = llm_config.get("api_key", self.api_key)
            api_type = llm_config.get("api_type", "openai_compatible")
        else:
            temperature = self.temperature
            top_p = 1.0
            top_k = 50
            repetition_penalty = 1.1
            max_tokens_setting = self.max_tokens
            model_name = self.model
            base_url = self.base_url
            api_key = self.api_key
            api_type = "openai_compatible"
        
        # Update headers with user's API key if provided
        if api_key and api_key != "not-needed-for-local":
            headers["Authorization"] = f"Bearer {api_key}"
        
        # Configure endpoint based on API type
        if api_type == "ollama":
            endpoint = f"{base_url}/api/chat"
        elif api_type == "koboldcpp":
            endpoint = f"{base_url}/api/v1/chat/completions"
        else:  # openai, openai_compatible
            # Handle URLs that might or might not have /v1 already
            if base_url.endswith("/v1"):
                endpoint = f"{base_url}/chat/completions"
            else:
                endpoint = f"{base_url}/v1/chat/completions"
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens or max_tokens_setting,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "stream": True
        }
        
        logger.info(f"Making streaming LLM request to: {endpoint}")
        logger.info(f"Using model: {model_name}")
        
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=60.0
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            if line.startswith("data: "):
                                line = line[6:]  # Remove "data: " prefix
                            
                            if line.strip() == "[DONE]":
                                break
                                
                            try:
                                data = json.loads(line)
                                
                                # Check for errors first
                                if "error" in data:
                                    error_msg = data["error"].get("message", "Unknown error")
                                    logger.error(f"LLM streaming error: {error_msg}")
                                    raise Exception(f"LLM streaming error: {error_msg}")
                                
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse JSON: {line} - Error: {e}")
                                continue
                
        except httpx.RequestError as e:
            logger.error(f"HTTP request failed: {e}")
            raise Exception(f"Failed to connect to LLM service: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise Exception(f"LLM service error: {e.response.status_code}")
    
    def _truncate_context_for_streaming(self, story_context: Dict[str, Any]) -> List[str]:
        """
        Truncate story context to fit within model limits for streaming
        """
        context_parts = []
        
        # Core story information (always include)
        if story_context.get("genre"):
            context_parts.append(f"Genre: {story_context['genre']}")
        
        if story_context.get("tone"):
            context_parts.append(f"Tone: {story_context['tone']}")
            
        if story_context.get("world_setting"):
            # Truncate if too long
            setting = story_context["world_setting"]
            if len(setting) > 200:
                setting = setting[:200] + "..."
            context_parts.append(f"Setting: {setting}")
            
        # Character information (limit to key characters)
        if story_context.get("characters"):
            char_info = []
            for i, char in enumerate(story_context["characters"][:3]):  # Limit to 3 characters
                char_desc = f"- {char.get('name', 'Unknown')}: {char.get('description', 'No description')}"
                if len(char_desc) > 100:
                    char_desc = char_desc[:100] + "..."
                char_info.append(char_desc)
            if char_info:
                context_parts.append(f"Main Characters:\n" + "\n".join(char_info))
        
        # Scene summary (truncated)
        if story_context.get("scene_summary"):
            summary = story_context["scene_summary"]
            if len(summary) > 300:
                summary = summary[:300] + "..."
            context_parts.append(f"Story Context: {summary}")
        
        # Previous scenes (truncated to most recent)
        if story_context.get("previous_scenes"):
            prev = story_context["previous_scenes"]
            if len(prev) > 500:
                # Take the last 500 characters to keep most recent content
                prev = "..." + prev[-500:]
            context_parts.append(f"Recent Events:\n{prev}")
            
        # Current situation
        if story_context.get("current_situation"):
            current = story_context["current_situation"]
            if len(current) > 200:
                current = current[:200] + "..."
            context_parts.append(f"Current Situation: {current}")
        
        return context_parts

    async def generate_scene_with_context_management(self, story_context: Dict[str, Any], user_settings: dict = None) -> str:
        """
        Generate a scene with smart context management for long stories
        
        This method uses the provided context which should already be optimized
        by the ContextManager for token limits.
        """
        
        system_prompt = """You are a creative storytelling assistant. Generate engaging narrative scenes that:
1. Continue the story naturally from the previous context
2. Include vivid descriptions and character development
3. Maintain consistency with established characters and world
4. Create dramatic tension and forward momentum
5. End at a natural decision point for the reader
6. Reference important previous events when relevant
7. Show character growth and relationship development

Write in a rich, engaging narrative style appropriate for the genre.

FORMATTING REQUIREMENTS:
- Use standard quotation marks for dialogue: "Hello," she said.
- Wrap internal thoughts/monologue in asterisks: *I can't believe this is happening*
- Use clear paragraph breaks between different speakers or actions
- DO NOT include scene numbers or titles like "Scene 7:" at the beginning
- Start directly with the narrative content

Important: If you see a scene summary, treat it as established story history.
Pay attention to the total scene count to understand story progression."""

        # Use truncated context to avoid token limits
        context_parts = self._truncate_context_for_streaming(story_context)
        
        # Simple prompt for better reliability
        prompt = f"""Story Context:
{chr(10).join(context_parts)}

Generate the next scene in this story. Make it engaging and immersive, approximately 200-300 words.
Ensure the scene flows naturally from the previous events."""

        result = await self._make_request(prompt, system_prompt, user_settings=user_settings)
        return self._clean_scene_numbers(result)

    async def generate_scene_with_context_management_streaming(self, story_context: Dict[str, Any], user_settings: dict = None):
        """
        Generate a scene with smart context management for long stories (streaming version)
        
        This method uses the provided context which should already be optimized
        by the ContextManager for token limits.
        """
        
        system_prompt = """You are a creative storytelling assistant. Generate engaging narrative scenes that:
1. Continue the story naturally from the previous context
2. Include vivid descriptions and character development
3. Maintain consistency with established characters and world
4. Create dramatic tension and forward momentum
5. End at a natural decision point for the reader
6. Reference important previous events when relevant
7. Show character growth and relationship development

Write in a rich, engaging narrative style appropriate for the genre.

FORMATTING REQUIREMENTS:
- Use standard quotation marks for dialogue: "Hello," she said.
- Wrap internal thoughts/monologue in asterisks: *I can't believe this is happening*
- Use clear paragraph breaks between different speakers or actions
- DO NOT include scene numbers or titles like "Scene 7:" at the beginning
- Start directly with the narrative content

Important: If you see a scene summary, treat it as established story history.
Pay attention to the total scene count to understand story progression."""

        # Use truncated context to avoid token limits (same as non-streaming)
        context_parts = self._truncate_context_for_streaming(story_context)
        
        # Simple prompt for streaming (to avoid token limits)
        prompt = f"""Story Context:
{chr(10).join(context_parts)}

Generate the next scene in this story. Make it engaging and immersive, approximately 200-300 words.
Ensure the scene flows naturally from the previous events."""

        logger.info(f"Built prompt with {len(prompt)} characters for streaming request")
        
        full_content = ""
        async for chunk in self._make_streaming_request(prompt, system_prompt, user_settings=user_settings):
            full_content += chunk
            yield chunk
        
        # Clean scene numbers from the final content if needed
        cleaned_content = self._clean_scene_numbers(full_content)
        # If cleaning changed the content, yield the difference
        if cleaned_content != full_content:
            yield cleaned_content[len(full_content):]

    async def generate_scene(self, story_context: Dict[str, Any]) -> str:
        """Generate a scene based on story context"""
        
        system_prompt = """You are a creative storytelling assistant. Generate engaging narrative scenes that:
1. Continue the story naturally from the previous context
2. Include vivid descriptions and character development
3. Maintain consistency with established characters and world
4. Create dramatic tension and forward momentum
5. End at a natural decision point for the reader

FORMATTING REQUIREMENTS:
- Use standard quotation marks for dialogue: "Hello," she said.
- Wrap internal thoughts/monologue in asterisks: *I can't believe this is happening*
- Use clear paragraph breaks between different speakers or actions
- DO NOT include scene numbers or titles like "Scene 7:" at the beginning
- Start directly with the narrative content

Write in a rich, engaging narrative style appropriate for the genre."""

        # Build context prompt
        context_parts = []
        
        if story_context.get("genre"):
            context_parts.append(f"Genre: {story_context['genre']}")
        
        if story_context.get("tone"):
            context_parts.append(f"Tone: {story_context['tone']}")
            
        if story_context.get("world_setting"):
            context_parts.append(f"Setting: {story_context['world_setting']}")
            
        if story_context.get("characters"):
            char_info = []
            for char in story_context["characters"]:
                char_info.append(f"- {char.get('name', 'Unknown')}: {char.get('description', 'No description')}")
            if char_info:
                context_parts.append(f"Characters present:\n" + "\n".join(char_info))
        
        if story_context.get("previous_scenes"):
            context_parts.append(f"Previous events: {story_context['previous_scenes']}")
            
        if story_context.get("current_situation"):
            context_parts.append(f"Current situation: {story_context['current_situation']}")
        
        prompt = f"""Story Context:
{chr(10).join(context_parts)}

Generate the next scene in this story. Make it engaging and immersive, approximately 200-400 words."""

        result = await self._make_request(prompt, system_prompt)
        return self._clean_scene_numbers(result)
    
    async def generate_choices(self, scene_content: str, story_context: Dict[str, Any], user_settings: dict = None) -> List[str]:
        """Generate 4 narrative choices for the given scene"""
        
        system_prompt = """You are a creative storytelling assistant. Generate exactly 4 compelling narrative choices that:
1. Offer meaningfully different story directions
2. Stay true to character motivations and world rules
3. Create interesting dramatic possibilities
4. Vary in risk/reward and emotional tone
5. Are concise but evocative (1-2 sentences each)

Format your response as a JSON array of exactly 4 strings."""

        context_parts = []
        
        if story_context.get("characters"):
            char_names = [char.get('name', 'Unknown') for char in story_context["characters"]]
            context_parts.append(f"Available characters: {', '.join(char_names)}")
        
        if story_context.get("genre"):
            context_parts.append(f"Genre: {story_context['genre']}")
            
        if story_context.get("current_location"):
            context_parts.append(f"Location: {story_context['current_location']}")

        context_str = "\n".join(context_parts) if context_parts else "No additional context provided."

        prompt = f"""Story Context:
{context_str}

Scene that just occurred:
{scene_content}

Generate exactly 4 different choices for what could happen next. Return them as a JSON array of strings, like:
["Choice 1 text here", "Choice 2 text here", "Choice 3 text here", "Choice 4 text here"]"""

        response = await self._make_request(prompt, system_prompt, max_tokens=500, user_settings=user_settings)
        
        logger.info(f"LLM Response for choices: {response[:500]}...")
        
        try:
            # Clean the response to extract JSON
            cleaned_response = response.strip()
            
            # Remove markdown code blocks if present
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # Find JSON array in the response
            start_idx = cleaned_response.find('[')
            end_idx = cleaned_response.rfind(']')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = cleaned_response[start_idx:end_idx + 1]
                logger.info(f"Extracted JSON string: {json_str}")
                choices = json.loads(json_str)
                if isinstance(choices, list) and len(choices) >= 4:
                    logger.info(f"Successfully parsed {len(choices)} choices from LLM")
                    return choices[:4]
                elif isinstance(choices, list) and len(choices) > 0:
                    # If we got fewer than 4, pad with generic choices
                    logger.warning(f"Got only {len(choices)} choices, padding with generic ones")
                    while len(choices) < 4:
                        choices.append(f"Alternative approach {len(choices)}")
                    return choices[:4]
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"JSON parsing failed: {e}. Response was: {response[:200]}...")
        
        # Fallback: parse line by line if JSON parsing fails
        lines = []
        for line in response.split('\n'):
            line = line.strip().strip('"\'.,').strip()
            if line and not line.startswith('[') and not line.startswith(']') and len(line) > 10:
                lines.append(line)
        
        if len(lines) >= 4:
            return lines[:4]
        elif len(lines) > 0:
            # Pad with generic choices if we have some but not enough
            while len(lines) < 4:
                lines.append(f"Consider alternative options")
            return lines[:4]
        
        # Final fallback: generate generic choices
        logger.error("Could not parse LLM response for choices, using fallback")
        logger.error(f"Full LLM response was: {response}")
        return [
            "Continue with the current course of action",
            "Try a different approach to the situation", 
            "Seek help or advice from others",
            "Take a moment to carefully consider options"
        ]
    
    async def expand_choice(self, choice_text: str, story_context: Dict[str, Any]) -> str:
        """Generate additional context or consequences for a choice"""
        
        system_prompt = """You are a storytelling assistant. Provide a brief description of what might happen if this choice is selected. Focus on immediate consequences and character reactions. Keep it to 1-2 sentences."""
        
        prompt = f"""Choice: {choice_text}

Story context: {story_context.get('current_situation', 'No context provided')}

What might happen if this choice is selected?"""

        return await self._make_request(prompt, system_prompt, max_tokens=100)

    async def generate_scenario(self, context: Dict[str, Any]) -> str:
        """Generate a creative scenario based on user selections and characters"""
        
        system_prompt = """You are a creative storytelling assistant. Generate an engaging story scenario that:
1. Incorporates the provided characters as central figures
2. Creates meaningful personal stakes for each character
3. Establishes relationships and conflicts between characters
4. Matches the specified genre and tone
5. Weaves together the story elements into a cohesive setup
6. Is 3-5 sentences long and creates a compelling hook
7. Sets up dramatic tension that involves the characters' goals and relationships

Write in an engaging narrative style that makes readers care about what happens to these specific characters."""

        # Build context prompt
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story elements
        elements = []
        if context.get("opening"):
            elements.append(f"Story opening: {context['opening']}")
        if context.get("setting"):
            elements.append(f"Setting: {context['setting']}")
        if context.get("conflict"):
            elements.append(f"Driving force: {context['conflict']}")
            
        prompt = f"""Please create a scenario based on these elements:

{chr(10).join(context_parts)}

Story elements to incorporate:
{chr(10).join(elements)}

Generate a creative scenario that:
- Places these specific characters at the center of the story
- Creates personal stakes and meaningful relationships between them
- Incorporates the story elements naturally
- Sets up compelling dramatic tension that makes readers invested in these characters' journey

Scenario:"""

        return await self._make_request(prompt, system_prompt, max_tokens=400)

    async def generate_titles(self, context: Dict[str, Any]) -> List[str]:
        """Generate creative story titles based on story content"""
        
        system_prompt = """You are a creative title generator for interactive stories. Generate 5 compelling story titles that:
1. Capture the essence of the story scenario and characters
2. Match the specified genre and tone perfectly
3. Are memorable and intriguing
4. Reflect the key themes, conflicts, or character relationships
5. Range from 2-6 words each
6. Avoid clichés and generic phrases
7. Create emotional hooks that make readers want to explore the story

Provide ONLY the 5 titles, one per line, without numbers or additional text."""

        # Build context prompt
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        # Story elements
        story_elements = context.get("story_elements", {})
        if story_elements:
            elements = []
            for key, value in story_elements.items():
                if value:
                    elements.append(f"{key.title()}: {value}")
            if elements:
                context_parts.append(f"Story Elements:\n{chr(10).join(elements)}")

        prompt = f"""Based on these story details:

{chr(10).join(context_parts)}

Generate 5 compelling titles that capture the heart of this specific story. Focus on the unique characters, their relationships, and the central conflict. Make each title distinctive and emotionally engaging.

Titles:"""

        response = await self._make_request(prompt, system_prompt, max_tokens=150)
        
        # Parse titles from response
        titles = [title.strip() for title in response.split('\n') if title.strip()]
        
        # Ensure we have exactly 5 titles
        if len(titles) < 5:
            # Add fallback titles if needed
            fallback_titles = [
                "The Journey Begins",
                "Shadows and Light", 
                "Destiny Calls",
                "The Final Choice",
                "Beyond Tomorrow"
            ]
            titles.extend(fallback_titles[:5-len(titles)])
        
        return titles[:5]

    async def generate_complete_plot(self, context: Dict[str, Any]) -> List[str]:
        """Generate a complete 5-point plot structure based on characters and scenario"""
        
        system_prompt = """You are a master storyteller and plot architect. Generate a complete 5-point plot structure that:
1. Is perfectly tailored to the specific characters and their relationships
2. Builds naturally from the established scenario
3. Creates meaningful character arcs and development
4. Escalates tension and stakes progressively
5. Delivers satisfying character-driven resolutions
6. Incorporates the genre and tone seamlessly
7. Creates opportunities for character growth and conflict

Provide exactly 5 plot points in this order:
1. Opening Hook - How the story begins with character-specific elements
2. Inciting Incident - The event that sets everything in motion for THESE characters
3. Rising Action - Character-specific challenges and conflicts
4. Climax - The ultimate confrontation involving these characters' arcs
5. Resolution - How these specific characters' journeys conclude

Write each plot point as 2-3 sentences. Focus on how the plot serves these specific characters' growth and relationships."""

        # Build context prompt
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        # World setting
        if context.get("world_setting"):
            context_parts.append(f"World Setting:\n{context['world_setting']}")

        prompt = f"""Based on these story elements:

{chr(10).join(context_parts)}

Generate a complete 5-point plot structure that weaves these characters' personal journeys into a compelling narrative arc. Each plot point should advance both the external story and the internal character development.

Focus on:
- How each character's goals, fears, and relationships drive the plot
- Meaningful conflicts that test character bonds and growth
- Plot developments that arise naturally from character choices
- A climax that resolves both external threats and internal character arcs

Plot Structure:

1. Opening Hook:

2. Inciting Incident:

3. Rising Action:

4. Climax:

5. Resolution:"""

        response = await self._make_request(prompt, system_prompt, max_tokens=600)
        
        # Clean and parse plot points from response
        plot_points = []
        
        # Remove markdown formatting and clean up
        cleaned_response = response.replace('**', '').replace('*', '')
        
        # Split by numbered sections
        sections = []
        current_section = ""
        
        for line in cleaned_response.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # Check if line starts with a number (1., 2., etc.) or plot point name
            if (any(line.startswith(f"{i}.") for i in range(1, 6)) or 
                any(name in line.lower() for name in ['opening hook', 'inciting incident', 'rising action', 'climax', 'resolution'])):
                
                # Save previous section
                if current_section.strip():
                    sections.append(current_section.strip())
                current_section = line
            else:
                # Continue building current section
                if current_section:
                    current_section += " " + line
        
        # Add the last section
        if current_section.strip():
            sections.append(current_section.strip())
        
        # Extract actual plot content (remove numbering and headers)
        for section in sections:
            # Remove numbering and common headers
            content = section
            for i in range(1, 6):
                content = content.replace(f"{i}. ", "")
            
            # Remove plot point headers
            headers_to_remove = [
                'opening hook:', 'inciting incident:', 'rising action:', 'climax:', 'resolution:',
                'opening hook', 'inciting incident', 'rising action', 'climax', 'resolution'
            ]
            
            for header in headers_to_remove:
                content = content.lower().replace(header, "").strip()
                
            # Capitalize first letter
            if content:
                content = content[0].upper() + content[1:] if len(content) > 1 else content.upper()
                plot_points.append(content)
        
        # Ensure we have exactly 5 meaningful plot points
        if len(plot_points) < 5:
            # Add fallback points based on characters
            character_names = [char.get('name', 'the protagonist') for char in context.get('characters', [])]
            main_char = character_names[0] if character_names else 'the protagonist'
            
            fallback_points = [
                f"The story opens as {main_char} encounters the first signs of the conflict that will define their journey.",
                f"A crucial discovery forces {main_char} to step fully into the adventure, changing everything they thought they knew.",
                f"As challenges mount, {main_char} and their allies face escalating obstacles that test their bonds and resolve.",
                f"The climax brings all conflicts to a head as {main_char} confronts their greatest fear and makes their ultimate choice.",
                f"The resolution shows how {main_char} and their world have been transformed by the journey they've undertaken."
            ]
            
            # Fill in missing points
            while len(plot_points) < 5:
                plot_points.append(fallback_points[len(plot_points)])
        
        return plot_points[:5]

    async def generate_single_plot_point(self, context: Dict[str, Any]) -> str:
        """Generate a single plot point based on characters and scenario"""
        
        plot_point_names = [
            "Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"
        ]
        
        index = context.get("plot_point_index", 0)
        point_name = plot_point_names[min(index, len(plot_point_names)-1)]
        
        system_prompt = f"""You are a master storyteller. Generate a compelling {point_name} that:
1. Is specifically tailored to the provided characters and their relationships
2. Builds naturally from the established scenario and world
3. Creates meaningful stakes for these specific characters
4. Advances character development and relationships
5. Matches the genre and tone perfectly
6. Sets up future plot developments organically

Write 2-3 sentences that feel like a natural part of this specific story with these specific characters."""

        # Build context prompt
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        # World setting
        if context.get("world_setting"):
            context_parts.append(f"World Setting:\n{context['world_setting']}")

        prompt = f"""Based on these story elements:

{chr(10).join(context_parts)}

Generate a compelling {point_name} that naturally incorporates these characters' personalities, relationships, and the established scenario. Focus on how this plot point specifically serves these characters' journeys and the unique aspects of this story.

{point_name}:"""

        return await self._make_request(prompt, system_prompt, max_tokens=200)

    async def test_connection(self) -> bool:
        """Test if the LLM service is available"""
        try:
            response = await self._make_request(
                "Hello, please respond with 'Connection successful'",
                max_tokens=10
            )
            return "successful" in response.lower()
        except Exception as e:
            logger.error(f"LLM connection test failed: {e}")
            return False

# Create global instance
llm_service = LMStudioService()