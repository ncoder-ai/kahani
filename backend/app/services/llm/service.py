"""
Unified LLM Service

Provides a clean, unified interface for all LLM operations using LiteLLM
and centralized prompt management.
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List
import litellm
from litellm import acompletion
import logging
import re

from .client import LLMClient
from .prompts import prompt_manager

logger = logging.getLogger(__name__)

class UnifiedLLMService:
    """
    Unified LLM Service using LiteLLM
    
    Features:
    - Multi-provider support through LiteLLM
    - Centralized prompt management
    - User configuration caching
    - Both streaming and non-streaming operations
    - Comprehensive error handling
    """
    
    def __init__(self):
        self._client_cache: Dict[int, LLMClient] = {}
    
    def get_user_client(self, user_id: int, user_settings: Dict[str, Any]) -> LLMClient:
        """Get or create LLM client configuration for user"""
        if user_id not in self._client_cache:
            try:
                self._client_cache[user_id] = LLMClient(user_settings)
                logger.info(f"Created LLM client for user {user_id} with provider {self._client_cache[user_id].api_type}")
            except Exception as e:
                logger.error(f"Failed to create LLM client for user {user_id}: {e}")
                raise
        
        return self._client_cache[user_id]
    
    async def validate_user_connection(self, user_id: int, user_settings: Dict[str, Any]) -> tuple[bool, str]:
        """Validate user's LLM connection and return detailed error info"""
        try:
            client = self.get_user_client(user_id, user_settings)
            return await client.test_connection()
        except Exception as e:
            return False, f"Failed to create client: {str(e)}"
    
    def invalidate_user_client(self, user_id: int):
        """Invalidate cached client when user updates settings"""
        if user_id in self._client_cache:
            del self._client_cache[user_id]
            logger.info(f"Invalidated LLM client cache for user {user_id}")
    
    async def _generate(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """Internal method for non-streaming generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Get generation parameters
        gen_params = client.get_generation_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        try:
            logger.info(f"Generating with {client.model_string} for user {user_id}")
            
            response = await acompletion(**gen_params)
            
            content = response.choices[0].message.content
            logger.info(f"Generated {len(content)} characters for user {user_id}")
            
            return content
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LiteLLM generation failed for user {user_id}: {error_msg}")
            
            # Provide helpful error messages for common connection issues
            if "404" in error_msg or "Not Found" in error_msg:
                if client.api_type == "openai_compatible":
                    raise ValueError(f"API endpoint not found. For TabbyAPI and similar services, try adding '/v1' to your URL: {client.api_url}/v1")
                else:
                    raise ValueError(f"API endpoint not found at {client.api_url}. Please check your URL.")
            elif "401" in error_msg or "Unauthorized" in error_msg:
                raise ValueError(f"Authentication failed. Please check your API key.")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise ValueError(f"Access forbidden. Please check your API key and permissions.")
            elif "Connection" in error_msg or "timeout" in error_msg.lower():
                raise ValueError(f"Cannot connect to {client.api_url}. Please check if the service is running and accessible.")
            else:
                # Fallback to direct HTTP for LM Studio and TabbyAPI
                if client.api_type in ["lm_studio", "openai_compatible"]:
                    logger.info(f"Attempting direct HTTP fallback for {client.api_type}")
                    return await self._direct_http_fallback(client, messages, max_tokens, temperature, False)
                else:
                    logger.error(f"LLM generation failed for user {user_id}: {error_msg}")
                    raise ValueError(f"LLM generation failed: {error_msg}")
    
    async def _direct_http_fallback(self, client, messages, max_tokens, temperature, stream):
        """Direct HTTP fallback for LM Studio when LiteLLM fails"""
        import httpx
        
        payload = {
            "model": client.model_name,  # Use the actual model name, not the prefixed one
            "messages": messages,
            "max_tokens": max_tokens or client.max_tokens,
            "temperature": temperature if temperature is not None else client.temperature,
            "stream": stream
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if client.api_key:
            headers["Authorization"] = f"Bearer {client.api_key}"
        
        try:
            # Determine the correct endpoint URL
            if client.api_url.endswith("/v1"):
                endpoint_url = f"{client.api_url}/chat/completions"
            else:
                endpoint_url = f"{client.api_url}/v1/chat/completions"
            
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                
                if stream:
                    # Handle streaming response
                    async def stream_generator():
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data.strip() == "[DONE]":
                                    break
                                try:
                                    import json
                                    chunk = json.loads(data)
                                    if "choices" in chunk and len(chunk["choices"]) > 0:
                                        delta = chunk["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                    return stream_generator()
                else:
                    # Handle non-streaming response
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"]
                    else:
                        raise ValueError("Invalid response format from LM Studio")
                        
        except Exception as e:
            logger.error(f"Direct HTTP fallback failed: {e}", exc_info=True)
            raise ValueError(f"LLM generation failed: {str(e)}")
    
    async def _generate_stream(
        self,
        prompt: str,
        user_id: int,
        user_settings: Dict[str, Any],
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """Internal method for streaming generation"""
        
        client = self.get_user_client(user_id, user_settings)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Get streaming parameters
        gen_params = client.get_streaming_params(max_tokens, temperature)
        gen_params["messages"] = messages
        
        try:
            logger.info(f"Streaming generation with {client.model_string} for user {user_id}")
            
            response = await acompletion(**gen_params)
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"LLM streaming failed for user {user_id}: {e}")
            raise ValueError(f"LLM streaming failed: {str(e)}")
    
    def _clean_scene_numbers(self, content: str) -> str:
        """Remove scene numbers and titles from the beginning of generated content"""
        # Remove patterns like "Scene 7:", "Scene 7: Title", etc. from the start
        content = re.sub(r'^Scene\s+\d+:.*?(\n|$)', '', content, flags=re.IGNORECASE).strip()
        # Also remove standalone scene titles that might start with numbers
        content = re.sub(r'^\d+[:.]\s*[A-Z][^.\n]*(\n|$)', '', content).strip()
        return content
    
    def _clean_scene_numbers_chunk(self, chunk: str) -> str:
        """Clean scene numbers from streaming chunks - more conservative than full cleaning"""
        if chunk.strip().startswith(('Scene ', 'SCENE ', 'scene ')):
            if re.match(r'^Scene\s+\d+[:\-\s]', chunk, re.IGNORECASE):
                cleaned = re.sub(r'^Scene\s+\d+[:\-\s]*[^\n]*\n?', '', chunk, flags=re.IGNORECASE)
                return cleaned
        return chunk
    
    # Story Generation Functions
    
    async def generate_story_title(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
        """Generate creative story titles based on story content"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "titles",
            context=self._format_context_for_titles(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("titles")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse titles from response
        titles = [title.strip() for title in response.split('\n') if title.strip()]
        
        # Clean up titles
        cleaned_titles = []
        for title in titles:
            cleaned_title = title.strip()
            # Remove common prefixes like "1.", "•", "-", etc.
            cleaned_title = re.sub(r'^[\d\.\-\*\•]\s*', '', cleaned_title)
            # Remove quotes if they wrap the entire title
            if cleaned_title.startswith('"') and cleaned_title.endswith('"'):
                cleaned_title = cleaned_title[1:-1]
            if cleaned_title.startswith("'") and cleaned_title.endswith("'"):
                cleaned_title = cleaned_title[1:-1]
            
            if cleaned_title and len(cleaned_title.split()) <= 8:  # Reasonable title length
                cleaned_titles.append(cleaned_title.strip())
        
        # Ensure we have exactly 5 titles
        if len(cleaned_titles) < 5:
            fallback_titles = [
                "The Journey Begins",
                "Shadows and Light", 
                "Destiny Calls",
                "The Final Choice",
                "Beyond the Horizon"
            ]
            cleaned_titles.extend(fallback_titles[:5-len(cleaned_titles)])
        
        return cleaned_titles[:5]
    
    async def generate_story_chapters(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], chapter_count: int = 5) -> List[str]:
        """Generate a chapter structure for a story"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "story_chapters",
            context=self._format_context_for_chapters(context),
            chapter_count=chapter_count
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_chapters")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse chapters from response
        chapters = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for numbered chapters
            if re.match(r'^[\d\.\-\*]\s*', line):
                # Clean the chapter text
                chapter_text = re.sub(r'^[\d\.\-\*]\s*', '', line).strip()
                if chapter_text and len(chapter_text) > 10:  # Ensure substantial content
                    chapters.append(chapter_text)
        
        # Ensure we have the requested number of chapters
        if len(chapters) < chapter_count:
            fallback_chapters = [
                f"Chapter {i+1}: The story begins to unfold with new challenges and opportunities."
                for i in range(len(chapters), chapter_count)
            ]
            chapters.extend(fallback_chapters)
        
        return chapters[:chapter_count]
    
    async def generate_scene(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a story scene"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene",
            context=self._format_context_for_scene(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate a story scene with streaming"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene",
            context=self._format_context_for_scene(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene")
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
    async def generate_scene_variants(self, original_scene: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate alternative versions of a scene"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "scene_variants",
            original_scene=original_scene,
            context=self._format_context_for_scene(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_variants")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_variants_streaming(self, original_scene: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate alternative versions of a scene with streaming"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "scene_variants_streaming",
            original_scene=original_scene,
            context=self._format_context_for_scene(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_variants")
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
    async def generate_scene_continuation(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate continuation content for an existing scene"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            context=self._format_context_for_continuation(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_continuation")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return self._clean_scene_numbers(response)
    
    async def generate_scene_continuation_streaming(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate continuation content for an existing scene with streaming"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scene_continuation",
            context=self._format_context_for_continuation(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scene_continuation")
        
        async for chunk in self._generate_stream(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        ):
            cleaned_chunk = self._clean_scene_numbers_chunk(chunk)
            if cleaned_chunk:  # Only yield non-empty chunks
                yield cleaned_chunk
    
    async def generate_choices(self, scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
        """Generate 4 narrative choices for the given scene"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "choices",
            scene_content=scene_content[-800:],  # Last 800 chars to avoid token limits
            context=self._format_context_for_choices(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("choices")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        # Parse choices from response
        choices = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for numbered choices
            if re.match(r'^[\d\.\-\*]\s*', line):
                # Clean the choice text
                choice_text = re.sub(r'^[\d\.\-\*]\s*', '', line).strip()
                if choice_text and len(choice_text) > 10:  # Ensure substantial content
                    choices.append(choice_text)
        
        # Ensure we have at least some choices
        if len(choices) < 2:
            choices = [
                "Continue forward cautiously",
                "Take a different approach", 
                "Investigate further",
                "Make a bold decision"
            ]
        
        return choices[:4]  # Return up to 4 choices
    
    async def generate_scenario(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a creative scenario based on user selections and characters"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "story_generation", "scenario",
            context=self._format_context_for_scenario(context),
            elements=self._format_elements_for_scenario(context)
        )
        
        max_tokens = prompt_manager.get_max_tokens("scenario")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return response
    
    async def generate_plot_points(self, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], plot_type: str = "complete") -> List[str]:
        """Generate plot points based on characters and scenario"""
        
        if plot_type == "complete":
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "plot_generation", "complete_plot",
                context=self._format_context_for_plot(context)
            )
            max_tokens = prompt_manager.get_max_tokens("complete_plot")
        else:
            system_prompt, user_prompt = prompt_manager.get_prompt_pair(
                "plot_generation", "single_plot_point",
                context=self._format_context_for_plot(context),
                point_name=self._get_plot_point_name(context.get("plot_point_index", 0))
            )
            max_tokens = prompt_manager.get_max_tokens("single_plot_point")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        if plot_type == "complete":
            return self._parse_plot_points(response)
        else:
            return [response]
    
    async def generate_summary(self, story_content: str, story_context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
        """Generate a comprehensive story summary"""
        
        system_prompt, user_prompt = prompt_manager.get_prompt_pair(
            "summary_generation", "story_summary",
            story_context=self._format_context_for_summary(story_context),
            story_content=story_content
        )
        
        max_tokens = prompt_manager.get_max_tokens("story_summary")
        
        response = await self._generate(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens
        )
        
        return response.strip()
    
    # Helper methods for context formatting
    
    def _format_context_for_titles(self, context: Dict[str, Any]) -> str:
        """Format context for title generation"""
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
        
        return "\n".join(context_parts)
    
    def _format_context_for_scene(self, context: Dict[str, Any]) -> str:
        """Format context for scene generation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            context_parts.append(f"Setting: {context['world_setting']}")
        
        if context.get("characters"):
            char_descriptions = [f"- {char.get('name', 'Unknown')}: {char.get('description', 'No description')}" 
                               for char in context["characters"]]
            context_parts.append(f"Characters present:\n{chr(10).join(char_descriptions)}")
        
        if context.get("previous_scenes"):
            context_parts.append(f"Previous events: {context['previous_scenes']}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_continuation(self, context: Dict[str, Any]) -> str:
        """Format context for scene continuation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("characters"):
            char_descriptions = [f"- {char.get('name', 'Unknown')}: {char.get('description', 'No description')}" 
                               for char in context["characters"]]
            context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
        
        if context.get("previous_content"):
            context_parts.append(f"Previous content: {context['previous_content'][-600:]}")  # Last 600 chars
        
        if context.get("choice_made"):
            context_parts.append(f"Reader's choice: {context['choice_made']}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_choices(self, context: Dict[str, Any]) -> str:
        """Format context for choice generation"""
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("characters"):
            char_list = [char.get('name', 'Unknown') for char in context.get('characters', [])]
            if char_list:
                context_parts.append(f"Characters involved: {', '.join(char_list)}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")
        
        return "\n".join(context_parts)
    
    def _format_context_for_scenario(self, context: Dict[str, Any]) -> str:
        """Format context for scenario generation"""
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
        
        return "\n".join(context_parts)
    
    def _format_elements_for_scenario(self, context: Dict[str, Any]) -> str:
        """Format story elements for scenario generation"""
        elements = []
        if context.get("opening"):
            elements.append(f"Story opening: {context['opening']}")
        if context.get("setting"):
            elements.append(f"Setting: {context['setting']}")
        if context.get("conflict"):
            elements.append(f"Driving force: {context['conflict']}")
        
        return "\n".join(elements)
    
    def _format_context_for_plot(self, context: Dict[str, Any]) -> str:
        """Format context for plot generation"""
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
        
        return "\n".join(context_parts)
    
    def _format_context_for_chapters(self, context: Dict[str, Any]) -> str:
        """Format context for chapter generation"""
        return self._format_context_for_plot(context)  # Same format as plot
    
    def _format_context_for_summary(self, context: Dict[str, Any]) -> str:
        """Format context for summary generation"""
        context_parts = []
        
        if context.get("title"):
            context_parts.append(f"Title: {context['title']}")
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("scene_count"):
            context_parts.append(f"Number of scenes: {context['scene_count']}")
        
        return "\n".join(context_parts)
    
    def _get_plot_point_name(self, index: int) -> str:
        """Get plot point name by index"""
        plot_point_names = [
            "Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"
        ]
        return plot_point_names[min(index, len(plot_point_names)-1)]
    
    def _parse_plot_points(self, response: str) -> List[str]:
        """Parse plot points from response"""
        plot_points = []
        
        # Clean up the response and look for plot points
        lines = response.split('\n')
        current_point = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for plot point markers (numbers, bullets, or keywords)
            if (re.match(r'^[\d\.\-\*\•]\s*', line) or 
                re.search(r'\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*', line, re.IGNORECASE)):
                
                # Save previous point if exists
                if current_point:
                    # Clean the point
                    clean_point = current_point.strip()
                    # Remove leading markers and formatting
                    clean_point = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_point)
                    clean_point = re.sub(r'^\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*:\s*', '', clean_point, flags=re.IGNORECASE)
                    clean_point = re.sub(r'^(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution):\s*', '', clean_point, flags=re.IGNORECASE)
                    if clean_point and len(clean_point) > 20:  # Ensure it's substantial content
                        plot_points.append(clean_point)
                
                current_point = line
            else:
                # Continuation of current point
                if current_point:
                    current_point += " " + line
        
        # Don't forget the last point
        if current_point:
            clean_point = current_point.strip()
            clean_point = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_point)
            clean_point = re.sub(r'^\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*:\s*', '', clean_point, flags=re.IGNORECASE)
            clean_point = re.sub(r'^(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution):\s*', '', clean_point, flags=re.IGNORECASE)
            if clean_point and len(clean_point) > 20:
                plot_points.append(clean_point)
        
        # Ensure we have exactly 5 plot points
        if len(plot_points) < 5:
            fallback_points = [
                "The story begins with an intriguing hook that draws readers in.",
                "A pivotal event changes everything and sets the main conflict in motion.",
                "Challenges and obstacles test the characters' resolve and growth.",
                "The climax brings all conflicts to a head in an intense confrontation.",
                "The resolution ties up loose ends and shows character transformation."
            ]
            plot_points.extend(fallback_points[len(plot_points):])
        
        return plot_points[:5]
