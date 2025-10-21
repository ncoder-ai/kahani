import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from ..models import Story, Scene, Character, StoryCharacter
from ..services.llm.service import UnifiedLLMService
from ..services.llm.prompts import prompt_manager
from ..database import get_db
from ..config import settings
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

# Initialize the unified LLM service
unified_llm_service = UnifiedLLMService()

if not TIKTOKEN_AVAILABLE:
    tiktoken = None

logger = logging.getLogger(__name__)

class ContextManager:
    """Smart context management for long stories that exceed LLM token limits"""
    
    def __init__(self, max_tokens: int = None, user_settings: dict = None, user_id: int = 1):
        """
        Initialize context manager
        
        Args:
            max_tokens: Maximum tokens to send to LLM (leaving room for response)
            user_settings: User-specific settings to override defaults
            user_id: User ID for LLM service calls
        """
        self.user_id = user_id
        self.user_settings = user_settings or {}
        if user_settings and user_settings.get("context_settings"):
            ctx_settings = user_settings["context_settings"]
            self.max_tokens = ctx_settings.get("max_tokens", settings.context_max_tokens)
            self.keep_recent_scenes = ctx_settings.get("keep_recent_scenes", settings.context_keep_recent_scenes)
            self.summary_threshold = ctx_settings.get("summary_threshold", settings.context_summary_threshold)
            # New hybrid threshold - token-based threshold for more precise control
            self.summary_threshold_tokens = ctx_settings.get("summary_threshold_tokens", 
                                                           getattr(settings, "context_summary_threshold_tokens", 10000))
            self.enable_summarization = ctx_settings.get("enable_summarization", True)
        else:
            self.max_tokens = max_tokens or settings.context_max_tokens
            self.keep_recent_scenes = settings.context_keep_recent_scenes
            self.summary_threshold = settings.context_summary_threshold
            self.summary_threshold_tokens = getattr(settings, "context_summary_threshold_tokens", 10000)
            self.enable_summarization = True
        
        # Apply token buffer for safety margin
        self.context_token_buffer = settings.context_token_buffer
        self.effective_max_tokens = int(self.max_tokens * self.context_token_buffer)
        
        # Initialize tokenizer if available
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
                self.use_tiktoken = True
                logger.info("Tiktoken initialized successfully for accurate token counting")
            except Exception as e:
                logger.warning(f"Failed to initialize tiktoken: {e}, using estimation")
                self.use_tiktoken = False
        else:
            logger.warning("Tiktoken not available, using estimation for token counting")
            self.use_tiktoken = False
        
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken or fallback estimation"""
        if self.use_tiktoken:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.warning(f"Tiktoken encoding failed: {e}, falling back to estimation")
        
        # Fallback: more accurate estimation (1 token ≈ 3.5 characters for English)
        # This is closer to the actual token count
        return int(len(text) / 3.5)
    
    async def build_story_context(self, story_id: int, db: Session) -> Dict[str, Any]:
        """
        Build optimized context for story generation, managing token limits
        
        Returns:
            Optimized context dict with story info, characters, and scene history
        """
        
        # Get story info
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        # Get all scenes ordered by sequence
        scenes = db.query(Scene).filter(
            Scene.story_id == story_id
        ).order_by(Scene.sequence_number).all()
        
        # Get story characters
        story_characters = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story_id
        ).all()
        
        characters = []
        for sc in story_characters:
            character = db.query(Character).filter(Character.id == sc.character_id).first()
            if character:
                characters.append({
                    "name": character.name,
                    "role": character.role,
                    "description": character.description,
                    "personality": character.personality,
                    "background": character.background,
                    "goals": character.goals,
                    "relationships": character.relationships
                })
        
        # Build base context
        base_context = {
            "story_id": story_id,
            "title": story.title,
            "genre": story.genre,
            "tone": story.tone,
            "world_setting": story.world_setting,
            "initial_premise": story.initial_premise,
            "characters": characters
        }
        
        # Calculate base context tokens
        base_tokens = self._calculate_base_context_tokens(base_context)
        
        # Available tokens for scene history (using effective max tokens)
        available_tokens = self.effective_max_tokens - base_tokens - 500  # Reserve 500 for safety
        
        if available_tokens <= 0:
            logger.warning(f"Base context too large for story {story_id}")
            return base_context
        
        # Build scene history with smart truncation
        scene_context = await self._build_scene_context(scenes, available_tokens, db)
        
        # Merge contexts
        return {**base_context, **scene_context}
    
    def _calculate_base_context_tokens(self, base_context: Dict[str, Any]) -> int:
        """Calculate tokens used by base story context"""
        
        # Convert context to text for token counting
        context_text = f"""
Genre: {base_context.get('genre', '')}
Tone: {base_context.get('tone', '')}
Setting: {base_context.get('world_setting', '')}
Premise: {base_context.get('initial_premise', '')}
"""
        
        # Add character information
        for char in base_context.get('characters', []):
            char_text = f"""
Character: {char.get('name', '')}
Role: {char.get('role', '')}
Description: {char.get('description', '')}
Personality: {char.get('personality', '')}
Background: {char.get('background', '')}
Goals: {char.get('goals', '')}
"""
            context_text += char_text
        
        return self.count_tokens(context_text)
    
    async def _build_scene_context(self, scenes: List[Scene], available_tokens: int, db: Session = None) -> Dict[str, Any]:
        """
        Build scene context with smart truncation and summarization
        
        Strategy:
        1. Always include the last few scenes (recency bias)
        2. Summarize middle scenes if needed
        3. Keep key plot points from early scenes
        4. Use progressive summarization for very long stories
        """
        
        if not scenes:
            return {"previous_scenes": "", "scene_summary": "", "recent_scenes": []}
        
        total_scenes = len(scenes)
        
        # Calculate total token count for hybrid threshold
        total_content = "\n\n".join([
            f"Scene {scene.sequence_number}: {scene.content}" 
            for scene in scenes
        ])
        total_tokens = self.count_tokens(total_content)
        
        # Adaptive strategy based on story length - use hybrid threshold
        # Use summarization if EITHER condition is met:
        # 1. Scene count exceeds threshold, OR
        # 2. Token count exceeds threshold
        should_summarize = (total_scenes > self.summary_threshold or 
                           total_tokens > self.summary_threshold_tokens)
        
        if not should_summarize:
            # Short story - try to include everything
            return await self._handle_short_story(scenes, available_tokens, db)
        else:
            # Long story - use progressive summarization
            return await self._handle_long_story(scenes, available_tokens, db)
    
    async def _handle_short_story(self, scenes: List[Scene], available_tokens: int, db: Session = None) -> Dict[str, Any]:
        """Handle stories with few scenes - try to include full context with dynamic filling"""
        
        # Try to include all scenes first
        all_content = "\n\n".join([
            f"Scene {scene.sequence_number}: {scene.content}" 
            for scene in scenes
        ])
        all_tokens = self.count_tokens(all_content)
        
        if all_tokens <= available_tokens:
            logger.info(f"All {len(scenes)} scenes fit in {all_tokens}/{available_tokens} tokens")
            return {
                "previous_scenes": all_content,
                "recent_scenes": all_content,
                "scene_summary": f"Complete story context ({len(scenes)} scenes)",
                "total_scenes": len(scenes),
                "context_strategy": "full_scenes"
            }
        
        # Can't fit everything - use dynamic filling strategy
        return await self._fill_scenes_dynamically(scenes, available_tokens, db)
    
    async def _fill_scenes_dynamically(self, scenes: List[Scene], available_tokens: int, db: Session = None) -> Dict[str, Any]:
        """
        Dynamically fill available tokens with as many scenes as possible.
        Prioritizes recent scenes going backwards.
        Uses actual token counts from database when available.
        """
        total_scenes = len(scenes)
        included_scenes = []
        used_tokens = 0
        
        # Start with most recent scenes and work backwards
        for i in range(len(scenes) - 1, -1, -1):
            scene = scenes[i]
            
            # Get proper scene content from active variant
            scene_content = await self._get_scene_content_proper(scene, db)
            scene_tokens = self.count_tokens(scene_content)
            
            if used_tokens + scene_tokens <= available_tokens:
                included_scenes.insert(0, scene)  # Insert at beginning to maintain order
                used_tokens += scene_tokens
            else:
                break
        
        if not included_scenes:
            # Emergency fallback - just the last scene
            last_scene = scenes[-1]
            included_scenes = [last_scene]
            last_content = await self._get_scene_content_proper(last_scene, db)
            used_tokens = self.count_tokens(last_content)
        
        # Build content using proper scene content
        included_content_parts = []
        for scene in included_scenes:
            content = await self._get_scene_content_proper(scene, db)
            included_content_parts.append(content)
        
        included_content = "\n\n".join(included_content_parts)
        
        # Check if we have excluded scenes that need summarization
        excluded_scenes = [s for s in scenes if s not in included_scenes]
        
        if excluded_scenes and used_tokens < available_tokens - 200:  # Leave room for summary
            remaining_tokens = available_tokens - used_tokens
            summary = await self._summarize_scenes(excluded_scenes)
            summary_tokens = self.count_tokens(summary)
            
            if summary_tokens <= remaining_tokens:
                full_content = f"{summary}\n\n{included_content}"
                strategy = "dynamic_with_summary"
            else:
                full_content = included_content
                strategy = "dynamic_recent_only"
        else:
            full_content = included_content
            strategy = "dynamic_recent_only"
        
        logger.info(f"Dynamic filling: {len(included_scenes)}/{total_scenes} scenes, {used_tokens}/{available_tokens} tokens")
        
        return {
            "previous_scenes": full_content,
            "recent_scenes": included_content,
            "scene_summary": f"Dynamic context: {len(included_scenes)} scenes included",
            "total_scenes": total_scenes,
            "context_strategy": strategy
        }
    
    async def _get_scene_content_proper(self, scene: Scene, db: Session = None) -> str:
        """
        Get proper scene content from active variant via StoryFlow.
        This is the correct way to get scene content.
        """
        if not db:
            # Fallback to scene.content if no db session
            return f"Scene {scene.sequence_number}: {scene.content}"
        
        try:
            from ..models import StoryFlow, SceneVariant
            
            # Get active variant from StoryFlow
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            ).first()
            
            if flow and flow.scene_variant:
                return f"Scene {scene.sequence_number}: {flow.scene_variant.content}"
            else:
                # Fallback to scene content if no flow entry
                return f"Scene {scene.sequence_number}: {scene.content}"
        except Exception as e:
            logger.warning(f"Failed to get proper scene content for scene {scene.id}: {e}")
            return f"Scene {scene.sequence_number}: {scene.content}"
    
    def _get_scene_token_count(self, scene: Scene, scene_content: str) -> int:
        """
        Get accurate token count for a scene.
        Uses database-stored token count if available, otherwise calculates.
        """
        # Debug logging to see what's happening
        logger.debug(f"Scene {scene.sequence_number} content length: {len(scene_content)} chars")
        logger.debug(f"Scene {scene.sequence_number} content preview: {scene_content[:100]}...")
        
        # Try to get token count from chapter if scene is linked to one
        if hasattr(scene, 'chapter') and scene.chapter:
            # If scene is in a chapter, use the chapter's token tracking
            # This is more accurate than real-time calculation
            token_count = self.count_tokens(scene_content)
            logger.debug(f"Scene {scene.sequence_number} token count: {token_count}")
            return token_count
        
        # Fallback to real-time calculation
        token_count = self.count_tokens(scene_content)
        logger.debug(f"Scene {scene.sequence_number} token count: {token_count}")
        return token_count
    
    async def _handle_long_story(self, scenes: List[Scene], available_tokens: int, db: Session = None) -> Dict[str, Any]:
        """Handle long stories with dynamic filling and progressive summarization"""
        
        total_scenes = len(scenes)
        
        # Use dynamic filling for long stories too
        return await self._fill_scenes_dynamically(scenes, available_tokens, db)
    
    async def _create_progressive_summary(self, scenes: List[Scene], available_tokens: int) -> str:
        """
        Create a progressive summary that captures key story beats
        """
        
        if not scenes:
            return ""
        
        try:
            # Divide scenes into narrative chunks (beginning, middle, recent-middle)
            scene_count = len(scenes)
            
            if scene_count <= 6:
                # Small enough to summarize as one chunk
                return await self._summarize_scenes(scenes)
            
            # Divide into narrative sections
            beginning_count = max(2, scene_count // 4)
            middle_count = scene_count - beginning_count
            
            beginning_scenes = scenes[:beginning_count]
            middle_scenes = scenes[beginning_count:]
            
            # Create section summaries
            summaries = []
            
            if beginning_scenes:
                beginning_summary = await self._summarize_scenes(beginning_scenes)
                summaries.append(f"Story Opening (Scenes {beginning_scenes[0].sequence_number}-{beginning_scenes[-1].sequence_number}): {beginning_summary}")
            
            if middle_scenes:
                middle_summary = await self._summarize_scenes(middle_scenes)
                summaries.append(f"Story Development (Scenes {middle_scenes[0].sequence_number}-{middle_scenes[-1].sequence_number}): {middle_summary}")
            
            combined_summary = "\n\n".join(summaries)
            
            # Check if it fits
            if self.count_tokens(combined_summary) <= available_tokens:
                return combined_summary
            else:
                # Too long, fall back to single summary
                return await self._summarize_scenes(scenes)
                
        except Exception as e:
            logger.error(f"Failed to create progressive summary: {e}")
            # Fallback to simple summary
            return await self._summarize_scenes(scenes[-6:])  # Last 6 scenes
    
    async def _include_earlier_scenes(self, scenes: List[Scene], available_tokens: int) -> str:
        """Include as many earlier scenes as possible within token limit"""
        
        content_parts = []
        used_tokens = 0
        
        # Include scenes from most recent to oldest (within the earlier scenes)
        for scene in reversed(scenes):
            scene_text = f"Scene {scene.sequence_number}: {scene.content}"
            scene_tokens = self.count_tokens(scene_text)
            
            if used_tokens + scene_tokens <= available_tokens:
                content_parts.insert(0, scene_text)  # Insert at beginning to maintain order
                used_tokens += scene_tokens
            else:
                break
        
        if content_parts:
            return "\n\n".join(content_parts)
        else:
            # If no scenes fit, create a summary
            return await self._summarize_scenes(scenes)
    
    async def _summarize_scenes(self, scenes: List[Scene]) -> str:
        """
        Create a concise summary of multiple scenes using LLM
        
        This is crucial for maintaining story continuity when context is limited
        """
        
        if not scenes:
            return ""
        
        if len(scenes) == 1:
            return f"Previous: {scenes[0].content[:200]}..."
        
        try:
            # Prepare scenes for summarization
            scenes_text = "\n\n".join([
                f"Scene {scene.sequence_number}: {scene.content}"
                for scene in scenes
            ])
            
            # Get database session for prompt lookup
            db = next(get_db())
            
            try:
                # Get dynamic prompts (user custom or default)
                system_prompt = prompt_manager.get_prompt(
                    template_key="story_summary",
                    prompt_type="system",
                    user_id=self.user_id,
                    db=db
                )
                
                # Get user prompt with template variables
                user_prompt = prompt_manager.get_prompt(
                    template_key="story_summary",
                    prompt_type="user",
                    user_id=self.user_id,
                    db=db,
                    story_content=scenes_text,
                    story_context=f"Summary of {len(scenes)} scenes from the story"
                )
                
                # Get max tokens for this template
                max_tokens = prompt_manager.get_max_tokens("story_summary")

                summary = await unified_llm_service.generate(
                    prompt=user_prompt, 
                    user_id=self.user_id, 
                    user_settings=self.user_settings, 
                    system_prompt=system_prompt, 
                    max_tokens=max_tokens
                )
            
            finally:
                db.close()
            
            # Add metadata about what was summarized
            scene_range = f"Scenes {scenes[0].sequence_number}-{scenes[-1].sequence_number}"
            return f"Summary of {scene_range}: {summary}"
            
        except Exception as e:
            logger.error(f"Failed to summarize scenes: {e}")
            
            # Fallback: simple truncation summary
            key_points = []
            for scene in scenes[-3:]:  # Last 3 scenes for fallback
                # Extract first sentence or two
                content = scene.content
                sentences = content.split('. ')
                if len(sentences) >= 2:
                    key_points.append(f"Scene {scene.sequence_number}: {sentences[0]}. {sentences[1]}.")
                else:
                    key_points.append(f"Scene {scene.sequence_number}: {content[:100]}...")
            
            return "Previous story events: " + " ".join(key_points)
    
    def optimize_character_context(self, characters: List[Dict[str, Any]], max_tokens: int) -> List[Dict[str, Any]]:
        """
        Optimize character information to fit within token limits
        """
        
        if not characters:
            return []
        
        # Calculate current character tokens
        char_text = self._characters_to_text(characters)
        current_tokens = self.count_tokens(char_text)
        
        if current_tokens <= max_tokens:
            return characters
        
        # Need to compress character information
        optimized_chars = []
        
        for char in characters:
            # Keep essential info, summarize the rest
            optimized_char = {
                "name": char.get("name", ""),
                "role": char.get("role", ""),
                "description": char.get("description", "")[:200] + "..." if len(char.get("description", "")) > 200 else char.get("description", "")
            }
            
            # Add personality if there's room
            if char.get("personality"):
                personality = char["personality"][:100] + "..." if len(char["personality"]) > 100 else char["personality"]
                optimized_char["personality"] = personality
            
            optimized_chars.append(optimized_char)
            
            # Check if we're still under limit
            opt_text = self._characters_to_text(optimized_chars)
            if self.count_tokens(opt_text) > max_tokens:
                # Remove last character and break
                optimized_chars.pop()
                break
        
        return optimized_chars
    
    def _characters_to_text(self, characters: List[Dict[str, Any]]) -> str:
        """Convert character list to text for token counting"""
        
        text_parts = []
        for char in characters:
            char_text = f"Character: {char.get('name', '')}\n"
            char_text += f"Role: {char.get('role', '')}\n"
            char_text += f"Description: {char.get('description', '')}\n"
            if char.get('personality'):
                char_text += f"Personality: {char.get('personality', '')}\n"
            if char.get('background'):
                char_text += f"Background: {char.get('background', '')}\n"
            text_parts.append(char_text)
        
        return "\n".join(text_parts)
    
    async def build_scene_generation_context(self, story_id: int, db: Session, custom_prompt: str = "") -> Dict[str, Any]:
        """
        Build optimized context specifically for scene generation
        """
        
        # Get full context
        full_context = await self.build_story_context(story_id, db)
        
        # Add custom prompt if provided
        if custom_prompt:
            full_context["current_situation"] = custom_prompt
        
        # Optimize for scene generation (focus on recent events and character state)
        scene_context = {
            "genre": full_context.get("genre"),
            "tone": full_context.get("tone"), 
            "world_setting": full_context.get("world_setting"),
            "characters": full_context.get("characters", []),
            "previous_scenes": full_context.get("recent_scenes", ""),
            "current_situation": full_context.get("current_situation", ""),
            "scene_summary": full_context.get("scene_summary", ""),
            "total_scenes": full_context.get("total_scenes", 0)
        }
        
        return scene_context

    async def build_choice_generation_context(self, story_id: int, db: Session) -> Dict[str, Any]:
        """
        Build context optimized for choice generation
        Uses similar logic to scene generation but focuses on current situation
        """
        # Reuse the scene generation context which already has the right info
        scene_context = await self.build_scene_generation_context(story_id, db)
        
        # Return a focused context for choice generation
        return {
            "story_title": scene_context.get("story_title", ""),
            "story_description": scene_context.get("story_description", ""),
            "genre": scene_context.get("genre", ""),
            "tone": scene_context.get("tone", ""),
            "characters": scene_context.get("characters", []),
            "current_situation": scene_context.get("current_situation", ""),
            "scene_summary": scene_context.get("scene_summary", "")
        }

    async def build_scene_continuation_context(
        self, 
        story_id: int, 
        scene_id: int, 
        current_content: str,
        db: Session, 
        custom_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        Build context for continuing a scene by adding more content to existing content
        """
        # Get the base story context
        story_context = await self.build_story_context(story_id, db)
        
        # Get scene specific info
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        
        context = {
            "story_title": story_context.get("story_title", ""),
            "story_description": story_context.get("story_description", ""),
            "genre": story_context.get("genre", ""),
            "tone": story_context.get("tone", ""),
            "characters": story_context.get("characters", []),
            "world_setting": story_context.get("world_setting", ""),
            "current_scene_content": current_content,
            "scene_title": scene.title if scene else "",
            "scene_number": scene.sequence_number if scene else 1,
            "continuation_prompt": custom_prompt,
            "context_type": "scene_continuation"
        }
        
        return context

# Global instance
context_manager = ContextManager()