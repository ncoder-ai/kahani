import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..models import Story, Scene, Character, StoryCharacter, StoryBranch
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
            # Scene batch size for LLM cache optimization
            self.scene_batch_size = ctx_settings.get("scene_batch_size", 10)
        else:
            self.max_tokens = max_tokens or settings.context_max_tokens
            self.keep_recent_scenes = settings.context_keep_recent_scenes
            self.summary_threshold = settings.context_summary_threshold
            self.summary_threshold_tokens = getattr(settings, "context_summary_threshold_tokens", 10000)
            self.enable_summarization = True
            self.scene_batch_size = 10  # Default batch size for scene caching
        
        # Ensure max_tokens has a valid default (4000 from config.yaml)
        # This can be None if user_settings.context_max_tokens is explicitly set to None
        if self.max_tokens is None:
            self.max_tokens = 4000
            logger.warning(f"max_tokens was None, using default value of 4000")
        
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
    
    def _get_active_branch_id(self, db: Session, story_id: int) -> Optional[int]:
        """Get the active branch ID for a story."""
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        return active_branch.id if active_branch else None
    
    async def build_story_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Build optimized context for story generation, managing token limits
        
        Args:
            story_id: Story ID
            db: Database session
            chapter_id: Optional chapter ID to separate active/inactive characters
            exclude_scene_id: Optional scene ID to exclude from context (for regeneration)
            branch_id: Optional branch ID (if not provided, uses active branch)
        
        Returns:
            Optimized context dict with story info, characters, and scene history
        """
        
        # Get story info
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # If exclude_scene_id is provided, get scenes from StoryFlow that come before it
        if exclude_scene_id:
            from ..models import StoryFlow
            # Get the scene being excluded to find its sequence_number
            excluded_scene = db.query(Scene).filter(Scene.id == exclude_scene_id).first()
            if excluded_scene:
                # Query StoryFlow for all active entries with sequence_number < excluded_scene.sequence_number
                flow_query = db.query(StoryFlow).filter(
                    StoryFlow.story_id == story_id,
                    StoryFlow.is_active == True,
                    StoryFlow.sequence_number < excluded_scene.sequence_number
                )
                # Filter by branch if available
                if branch_id:
                    flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
                flow_entries = flow_query.order_by(StoryFlow.sequence_number).all()
                
                # Get Scene objects from the flow entries
                scene_ids = [flow.scene_id for flow in flow_entries]
                if scene_ids:
                    scene_query = db.query(Scene).filter(Scene.id.in_(scene_ids))
                    
                    # Filter by chapter_id if provided
                    if chapter_id:
                        scene_query = scene_query.filter(Scene.chapter_id == chapter_id)
                        logger.info(f"[CONTEXT BUILD] Filtering to chapter {chapter_id} (with exclude_scene_id)")
                    
                    scenes = scene_query.order_by(Scene.sequence_number).all()
                else:
                    scenes = []
                logger.info(f"[CONTEXT BUILD] Excluding scene {exclude_scene_id} (sequence {excluded_scene.sequence_number}), using {len(scenes)} scenes from StoryFlow")
            else:
                # Scene not found, fall back to normal query
                logger.warning(f"[CONTEXT BUILD] Excluded scene {exclude_scene_id} not found, falling back to normal query")
                scene_query = db.query(Scene).filter(Scene.story_id == story_id)
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
        # Get all scenes ordered by sequence
        # When chapter_id is provided, include scenes from ALL chapters up to and including that chapter
        elif chapter_id:
            # Get the chapter to find its chapter_number
            from ..models import Chapter
            active_chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            
            if active_chapter:
                # Include scenes from all chapters with chapter_number <= active chapter's chapter_number
                # This ensures we include previous chapters but exclude future chapters
                scene_query = db.query(Scene).join(Chapter).filter(
                    Scene.story_id == story_id,
                    Chapter.chapter_number <= active_chapter.chapter_number
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.info(f"[CONTEXT BUILD] Chapter {chapter_id} (Chapter {active_chapter.chapter_number}): Including scenes from chapters 1-{active_chapter.chapter_number} ({len(scenes)} scenes)")
            else:
                # Fallback: if chapter not found, only get scenes from that chapter_id
                scene_query = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.chapter_id == chapter_id
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.warning(f"[CONTEXT BUILD] Chapter {chapter_id} not found, falling back to chapter_id filter only")
            
            # Note: continues_from_previous controls whether story_so_far and 
            # previous_chapter_summary are included (handled in base context building below)
        else:
            scene_query = db.query(Scene).filter(Scene.story_id == story_id)
            if branch_id:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scenes = scene_query.order_by(Scene.sequence_number).all()
        
        # Get story characters (filtered by branch)
        char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
        if branch_id:
            char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
        story_characters = char_query.all()
        
        # Separate into active (chapter) and inactive (story only) characters
        active_characters = []
        inactive_characters = []
        
        if chapter_id:
            # Get chapter-specific characters
            from ..models import chapter_characters
            chapter_char_ids = db.execute(
                chapter_characters.select().where(
                    chapter_characters.c.chapter_id == chapter_id
                )
            ).fetchall()
            chapter_story_char_ids = {row.story_character_id for row in chapter_char_ids}
            
            # Get chapter info for context
            from ..models import Chapter
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        else:
            chapter_story_char_ids = set()
            chapter = None
        
        for sc in story_characters:
            character = db.query(Character).filter(Character.id == sc.character_id).first()
            if not character:
                continue
            
            char_data = {
                "name": character.name,
                "role": sc.role or "",
                "description": character.description or "",
                "personality": ", ".join(character.personality_traits) if character.personality_traits else "",
                "background": character.background or "",
                "goals": character.goals or "",
                "fears": character.fears or "",
                "appearance": character.appearance or "",
                "relationships": ""
            }
            
            if chapter_id and sc.id in chapter_story_char_ids:
                # Active character - full details
                active_characters.append(char_data)
            elif chapter_id:
                # Inactive character - brief format
                inactive_characters.append({
                    "name": character.name,
                    "role": sc.role or ""
                })
            else:
                # No chapter specified - treat all as active
                active_characters.append(char_data)
        
        # Add important NPCs that crossed threshold (always as active)
        try:
            from .npc_tracking_service import NPCTrackingService
            npc_service = NPCTrackingService(user_id=self.user_id, user_settings=self.user_settings)
            npc_characters = npc_service.get_important_npcs_for_context(db, story_id, branch_id=branch_id)
            active_characters.extend(npc_characters)
            logger.warning(f"[CONTEXT BUILD] Added {len(npc_characters)} important NPCs to context (total characters now: {len(active_characters)})")
            if npc_characters:
                logger.warning(f"[CONTEXT BUILD] NPCs added: {[npc.get('name', 'Unknown') for npc in npc_characters]}")
        except Exception as e:
            logger.warning(f"Failed to include NPCs in context: {e}")
        
        # Format characters section with active/inactive distinction
        if chapter_id and inactive_characters:
            # Format with clear distinction
            characters_section = {
                "active_characters": active_characters,
                "inactive_characters": inactive_characters
            }
            logger.info(f"[CONTEXT BUILD] Chapter {chapter_id}: {len(active_characters)} active, {len(inactive_characters)} inactive characters")
        else:
            # All characters are active (or no chapter specified)
            characters_section = active_characters
        
        # Build base context
        base_context = {
            "story_id": story_id,
            "title": story.title,
            "genre": story.genre,
            "tone": story.tone,
            "world_setting": story.world_setting,
            "initial_premise": story.initial_premise,
            "scenario": story.scenario,
            "characters": characters_section
        }
        
        # Add chapter-specific context if available
        if chapter:
            base_context["chapter_location"] = chapter.location_name
            base_context["chapter_time_period"] = chapter.time_period
            base_context["chapter_scenario"] = chapter.scenario
            
            # Check if chapter continues from previous (controls summary inclusion)
            continues_from_previous = getattr(chapter, 'continues_from_previous', True)
            
            # Include story_so_far if it exists AND chapter continues from previous
            if chapter.story_so_far and continues_from_previous:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Including story_so_far ({len(chapter.story_so_far)} chars)")
                base_context["story_so_far"] = chapter.story_so_far
            elif chapter.story_so_far and not continues_from_previous:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Excluding story_so_far (continues_from_previous=False)")
            else:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: story_so_far is None")
            
            # Include previous chapter's summary if available AND chapter continues from previous
            if chapter.chapter_number > 1 and continues_from_previous:
                from ..models import Chapter as ChapterModel, ChapterStatus
                previous_chapter = db.query(ChapterModel).filter(
                    ChapterModel.story_id == story_id,
                    ChapterModel.chapter_number == chapter.chapter_number - 1,
                    ChapterModel.auto_summary.isnot(None)
                ).first()
                if previous_chapter and previous_chapter.auto_summary:
                    logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Found previous chapter {previous_chapter.chapter_number} summary ({len(previous_chapter.auto_summary)} chars)")
                    base_context["previous_chapter_summary"] = previous_chapter.auto_summary
                else:
                    logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: No previous chapter summary found (previous_chapter={previous_chapter is not None}, has_auto_summary={previous_chapter.auto_summary if previous_chapter else 'N/A'})")
            elif chapter.chapter_number > 1 and not continues_from_previous:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Excluding previous_chapter_summary (continues_from_previous=False)")
            else:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: First chapter, no previous chapter summary")
            
            # Include current chapter's auto_summary for context on this chapter's progress
            # This should only include scenes that have been summarized (up to last_summary_scene_count)
            # Recent scenes beyond last_summary_scene_count will be included separately in the scene context
            if chapter.auto_summary:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Including current_chapter_summary ({len(chapter.auto_summary)} chars, last_summary_scene_count={chapter.last_summary_scene_count})")
                base_context["current_chapter_summary"] = chapter.auto_summary
            else:
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: current_chapter_summary is None")
        
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
Scenario: {base_context.get('scenario', '')}
"""
        
        # Add character information - handle both list and dict formats
        characters = base_context.get('characters', [])
        if isinstance(characters, dict) and "active_characters" in characters:
            # New format: dict with active_characters and inactive_characters
            active_chars = characters.get("active_characters", [])
            inactive_chars = characters.get("inactive_characters", [])
            
            # Count tokens for active characters (full details)
            for char in active_chars:
                if isinstance(char, dict):
                    char_text = f"""
Character: {char.get('name', '')}
Role: {char.get('role', '')}
Description: {char.get('description', '')}
Personality: {char.get('personality', '')}
Background: {char.get('background', '')}
Goals: {char.get('goals', '')}
Fears: {char.get('fears', '')}
Appearance: {char.get('appearance', '')}
"""
                    context_text += char_text
            
            # Count tokens for inactive characters (brief format)
            for char in inactive_chars:
                if isinstance(char, dict):
                    char_text = f"""
Character: {char.get('name', '')}
Role: {char.get('role', '')}
"""
                    context_text += char_text
        else:
            # Legacy format: list of character dicts
            for char in characters:
                if isinstance(char, dict):
                    char_text = f"""
Character: {char.get('name', '')}
Role: {char.get('role', '')}
Description: {char.get('description', '')}
Personality: {char.get('personality', '')}
Background: {char.get('background', '')}
Goals: {char.get('goals', '')}
Fears: {char.get('fears', '')}
Appearance: {char.get('appearance', '')}
"""
                    context_text += char_text
        
        # Add chapter summaries to token count (these are part of base context)
        if base_context.get('story_so_far'):
            context_text += f"\nStory So Far:\n{base_context['story_so_far']}"
        if base_context.get('previous_chapter_summary'):
            context_text += f"\nPrevious Chapter Summary:\n{base_context['previous_chapter_summary']}"
        if base_context.get('current_chapter_summary'):
            context_text += f"\nCurrent Chapter Summary:\n{base_context['current_chapter_summary']}"
        
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
        Dynamically fill available tokens with scenes using batch-aligned selection.
        
        This method selects scenes in complete batch units (aligned to scene_batch_size)
        to maximize LLM cache hit rates. Working backward from the most recent scene:
        1. First, include the active batch (current incomplete batch)
        2. Then add complete batches (e.g., 51-60, 41-50) until token budget exhausted
        
        A batch is only included if ALL its scenes fit. We allow slight overage (~5%)
        to leverage the 10% buffer from token_buffer setting.
        """
        total_scenes = len(scenes)
        batch_size = self.scene_batch_size
        
        if total_scenes == 0:
            return {
                "previous_scenes": "",
                "recent_scenes": "",
                "scene_summary": "No scenes",
                "total_scenes": 0,
                "context_strategy": "empty"
            }
        
        # Build a map of scene sequence numbers to scenes and their token counts
        scene_map: Dict[int, Tuple[Scene, str, int]] = {}
        for scene in scenes:
            scene_content = await self._get_scene_content_proper(scene, db)
            scene_tokens = self.count_tokens(scene_content)
            scene_map[scene.sequence_number] = (scene, scene_content, scene_tokens)
        
        # Get the highest scene number (most recent)
        max_scene_num = max(scene_map.keys())
        
        # Calculate batch boundaries
        # Active batch: the batch containing the most recent scene
        active_batch_num = (max_scene_num - 1) // batch_size
        active_batch_start = active_batch_num * batch_size + 1
        active_batch_end = active_batch_start + batch_size - 1
        
        # Step 1: Always include the active batch (partial, changes each scene)
        included_scenes = []
        used_tokens = 0
        
        for seq_num in range(active_batch_start, max_scene_num + 1):
            if seq_num in scene_map:
                scene, content, tokens = scene_map[seq_num]
                included_scenes.append(scene)
                used_tokens += tokens
        
        logger.debug(f"[BATCH FILL] Active batch {active_batch_num} (scenes {active_batch_start}-{max_scene_num}): {len(included_scenes)} scenes, {used_tokens} tokens")
        
        # Step 2: Work backward through complete batches
        # Allow slight overage (5%) to leverage the 10% buffer from token_buffer
        overage_allowance = int(available_tokens * 0.05)
        effective_limit = available_tokens + overage_allowance
        
        current_batch_num = active_batch_num - 1
        
        while current_batch_num >= 0:
            batch_start = current_batch_num * batch_size + 1
            batch_end = batch_start + batch_size - 1
            
            # Get all scenes in this batch that exist
            batch_scenes = []
            batch_tokens = 0
            batch_complete = True
            
            for seq_num in range(batch_start, batch_end + 1):
                if seq_num in scene_map:
                    scene, content, tokens = scene_map[seq_num]
                    batch_scenes.append(scene)
                    batch_tokens += tokens
                else:
                    # Scene doesn't exist in our context - batch is incomplete
                    batch_complete = False
            
            # Only include complete batches (all scenes from batch_start to batch_end present)
            # A batch is complete if it has exactly batch_size scenes
            if not batch_complete or len(batch_scenes) != batch_size:
                logger.debug(f"[BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): incomplete ({len(batch_scenes)}/{batch_size} scenes), stopping")
                break
            
            # Check if adding this complete batch fits within our limit
            if used_tokens + batch_tokens <= effective_limit:
                # Insert at the beginning to maintain order
                included_scenes = batch_scenes + included_scenes
                used_tokens += batch_tokens
                logger.debug(f"[BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): included, {batch_tokens} tokens, total now {used_tokens}")
                current_batch_num -= 1
            else:
                logger.debug(f"[BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): would exceed limit ({used_tokens} + {batch_tokens} > {effective_limit}), stopping")
                break
        
        if not included_scenes:
            # Emergency fallback - just the last scene
            last_scene = scenes[-1]
            last_content = await self._get_scene_content_proper(last_scene, db)
            included_scenes = [last_scene]
            used_tokens = self.count_tokens(last_content)
        
        # Build content using proper scene content
        included_content_parts = []
        for scene in included_scenes:
            if scene.sequence_number in scene_map:
                _, content, _ = scene_map[scene.sequence_number]
            included_content_parts.append(content)
        
        included_content = "\n\n".join(included_content_parts)
        
        # Use batch-aligned content directly - no on-the-fly summarization
        # Pre-existing summaries (story_so_far, previous_chapter_summary, current_chapter_summary)
        # are already included in base context and should be used instead
        full_content = included_content
        strategy = "batch_aligned"
        
        # Log batch alignment info
        if included_scenes:
            first_seq = min(s.sequence_number for s in included_scenes)
            last_seq = max(s.sequence_number for s in included_scenes)
            logger.info(f"[BATCH FILL] Final: scenes {first_seq}-{last_seq} ({len(included_scenes)}/{total_scenes} scenes), {used_tokens}/{available_tokens} tokens, batch_size={batch_size}")
        
        return {
            "previous_scenes": full_content,
            "recent_scenes": included_content,
            "scene_summary": f"Batch-aligned context: {len(included_scenes)} scenes included",
            "total_scenes": total_scenes,
            "context_strategy": strategy
        }
    
    async def _get_scene_content_proper(self, scene: Scene, db: Session = None, branch_id: Optional[int] = None) -> str:
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
            flow_query = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            )
            if branch_id:
                flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
            flow = flow_query.first()
            
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
            if char.get('goals'):
                char_text += f"Goals: {char.get('goals', '')}\n"
            if char.get('fears'):
                char_text += f"Fears: {char.get('fears', '')}\n"
            if char.get('appearance'):
                char_text += f"Appearance: {char.get('appearance', '')}\n"
            text_parts.append(char_text)
        
        return "\n".join(text_parts)
    
    async def build_scene_generation_context(self, story_id: int, db: Session, custom_prompt: str = "", is_variant_generation: bool = False, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Build optimized context specifically for scene generation
        
        Args:
            story_id: Story ID
            db: Database session
            custom_prompt: Custom prompt (continue option for new scenes, enhancement guidance for variants)
            is_variant_generation: True if this is for variant generation, False for new scene generation
            chapter_id: Optional chapter ID to separate active/inactive characters
            exclude_scene_id: Optional scene ID to exclude from context (for regeneration)
            branch_id: Optional branch ID to filter scenes by branch (for branching stories)
        """
        
        # Get full context with chapter_id for character separation and branch_id for branch filtering
        full_context = await self.build_story_context(story_id, db, chapter_id=chapter_id, exclude_scene_id=exclude_scene_id, branch_id=branch_id)
        
        # Check if this is the first scene (no previous scenes)
        total_scenes = full_context.get("total_scenes", 0)
        is_first_scene = total_scenes == 0
        
        # Add custom prompt if provided (continuation option text)
        if custom_prompt and custom_prompt.strip():
            if is_variant_generation:
                # Variant generation with guided enhancement - only set enhancement_guidance
                # Don't set current_situation to avoid "IMMEDIATE SITUATION" formatting
                full_context["enhancement_guidance"] = custom_prompt.strip()
            else:
                # New scene generation with continue option - set current_situation
                # This triggers "IMMEDIATE SITUATION" formatting
                full_context["current_situation"] = custom_prompt.strip()
                logger.info(f"[CONTEXT_MANAGER] Set current_situation from custom_prompt: '{full_context['current_situation']}'")
                if is_first_scene:
                    full_context["is_first_scene"] = True
                    full_context["user_prompt_provided"] = True
        else:
            logger.warning(f"[CONTEXT_MANAGER] custom_prompt is empty or whitespace only: '{custom_prompt}'")
        
        # Optimize for scene generation (focus on recent events and character state)
        # Use "previous_scenes" which contains full context (including semantic scenes for SemanticContextManager)
        scene_context = {
            "genre": full_context.get("genre"),
            "tone": full_context.get("tone"), 
            "world_setting": full_context.get("world_setting"),
            "scenario": full_context.get("scenario"),  # Story-level scenario (from story creation)
            "initial_premise": full_context.get("initial_premise"),  # Include initial premise
            "characters": full_context.get("characters", []),
            "previous_scenes": full_context.get("previous_scenes", ""),  # Full context (includes semantic for semantic manager)
            "current_situation": full_context.get("current_situation", ""),
            "scene_summary": full_context.get("scene_summary", ""),
            "total_scenes": full_context.get("total_scenes", 0),
            "context_type": full_context.get("context_type", "linear"),  # Indicate which context manager was used
            "is_first_scene": is_first_scene,
            "user_prompt_provided": bool(custom_prompt),
            "enhancement_guidance": full_context.get("enhancement_guidance", ""),  # Signal for guided enhancement
            # Add chapter-specific metadata
            "chapter_location": full_context.get("chapter_location"),
            "chapter_time_period": full_context.get("chapter_time_period"),
            "chapter_scenario": full_context.get("chapter_scenario"),  # Chapter-specific scenario
            # Add chapter summaries
            "story_so_far": full_context.get("story_so_far"),
            "previous_chapter_summary": full_context.get("previous_chapter_summary"),
            "current_chapter_summary": full_context.get("current_chapter_summary")
        }
        
        # Log what's in the context
        logger.info(f"[CONTEXT BUILD] Scene generation context - story_so_far: {'present' if scene_context.get('story_so_far') else 'None'}, previous_chapter_summary: {'present' if scene_context.get('previous_chapter_summary') else 'None'}, current_chapter_summary: {'present' if scene_context.get('current_chapter_summary') else 'None'}")
        if scene_context.get("story_so_far"):
            logger.info(f"[CONTEXT BUILD] story_so_far length: {len(scene_context['story_so_far'])} chars")
        if scene_context.get("previous_chapter_summary"):
            logger.info(f"[CONTEXT BUILD] previous_chapter_summary length: {len(scene_context['previous_chapter_summary'])} chars")
        if scene_context.get("current_chapter_summary"):
            logger.info(f"[CONTEXT BUILD] current_chapter_summary length: {len(scene_context['current_chapter_summary'])} chars")
        
        return scene_context

    async def build_choice_generation_context(self, story_id: int, db: Session, scene_context: Optional[Dict[str, Any]] = None, chapter_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Build context optimized for choice generation
        If scene_context is provided, reuse it to preserve all context fields.
        Otherwise, build full context using build_scene_generation_context() (for "More Choices" button case)
        """
        if scene_context is not None:
            # Reuse the provided scene generation context - preserve all fields
            return scene_context.copy()
        else:
            # Build full context (for "More Choices" button case where original context isn't available)
            return await self.build_scene_generation_context(story_id, db, chapter_id=chapter_id)

    async def build_scene_continuation_context(
        self, 
        story_id: int, 
        scene_id: int, 
        current_content: str,
        db: Session, 
        custom_prompt: str = "",
        branch_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Build context for scene continuation - uses same structure as scene generation
        for maximum cache hits.
        
        The current scene is EXCLUDED from previous_scenes (via exclude_scene_id) and
        sent only in the final message. This mirrors how choice generation works.
        """
        # Get scene info for chapter_id
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        chapter_id = scene.chapter_id if scene else None
        
        # Build full context, EXCLUDING the current scene to avoid duplication
        # This uses the same context structure as scene generation for cache hits
        full_context = await self.build_scene_generation_context(
            story_id, db, 
            custom_prompt=custom_prompt,
            chapter_id=chapter_id,
            exclude_scene_id=scene_id,  # Exclude current scene - it will be in final message
            branch_id=branch_id
        )
        
        # Add continuation-specific fields
        full_context["current_scene_content"] = current_content
        full_context["current_content"] = current_content  # For POV detection
        full_context["continuation_prompt"] = custom_prompt or "Continue this scene with more details and development."
        full_context["context_type"] = "scene_continuation"
        full_context["scene_title"] = scene.title if scene else ""
        full_context["scene_number"] = scene.sequence_number if scene else 1
        
        return full_context

    async def calculate_actual_context_size(self, story_id: int, chapter_id: int, db: Session, branch_id: Optional[int] = None) -> int:
        """
        Calculate the total token count for all content in the current chapter.
        
        This method counts tokens for ALL scenes in the chapter that are in the active
        story flow, plus base context (story settings, chapter summaries, etc.).
        
        Unlike the context sent to the LLM (which is limited by token budget), this
        returns the TOTAL tokens for the chapter to show accurate progress tracking.
        
        IMPORTANT: Only counts scenes from the current chapter that are in the active story flow.
        
        Args:
            story_id: Story ID
            chapter_id: Chapter ID (ensures only current chapter context is included)
            db: Database session
            branch_id: Optional branch ID (if not provided, uses active branch)
            
        Returns:
            Total token count of all content in the chapter
        """
        try:
            from ..models import Chapter, StoryFlow
            
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                logger.error(f"Chapter {chapter_id} not found")
                return 0
            
            # Get active branch if not specified
            if branch_id is None:
                branch_id = self._get_active_branch_id(db, story_id)
            
            # Build context with chapter_id - this will include base context and chapter summaries
            context = await self.build_story_context(story_id, db, chapter_id=chapter_id, branch_id=branch_id)
            
            # Get all scenes from the current chapter that are in the ACTIVE story flow
            # This matches how get_active_scene_count works
            scene_query = db.query(Scene).join(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.is_active == True,
                Scene.chapter_id == chapter_id
            )
            if branch_id:
                scene_query = scene_query.filter(StoryFlow.branch_id == branch_id)
            current_chapter_scenes = scene_query.order_by(Scene.sequence_number).all()
            
            # Calculate base context tokens (always included)
            base_context_dict = {
                "genre": context.get("genre", ""),
                "tone": context.get("tone", ""),
                "world_setting": context.get("world_setting", ""),
                "initial_premise": context.get("initial_premise", ""),
                "scenario": context.get("scenario", ""),
                "characters": context.get("characters", [])
            }
            base_tokens = self._calculate_base_context_tokens(base_context_dict)
            
            # Add chapter summary tokens
            if context.get("story_so_far"):
                base_tokens += self.count_tokens(f"Story So Far:\n{context['story_so_far']}")
            if context.get("previous_chapter_summary"):
                base_tokens += self.count_tokens(f"Previous Chapter Summary:\n{context['previous_chapter_summary']}")
            
            # Add chapter-specific metadata tokens
            if context.get("chapter_location"):
                base_tokens += self.count_tokens(f"Chapter Location: {context['chapter_location']}")
            if context.get("chapter_time_period"):
                base_tokens += self.count_tokens(f"Chapter Time Period: {context['chapter_time_period']}")
            if context.get("chapter_scenario"):
                base_tokens += self.count_tokens(f"Chapter Scenario: {context['chapter_scenario']}")
            
            # Count tokens for ALL scenes in the chapter (not limited by available_tokens)
            # This gives accurate total chapter size for progress tracking
            total_scene_tokens = 0
            for scene in current_chapter_scenes:
                scene_content = await self._get_scene_content_proper(scene, db)
                total_scene_tokens += self.count_tokens(scene_content)
            
            # Total = base context + all scene tokens
            total_tokens = base_tokens + total_scene_tokens
            
            logger.info(f"[CONTEXT SIZE] Calculated total context size for chapter {chapter_id}: {total_tokens} tokens (base: {base_tokens}, scene_tokens: {total_scene_tokens}, scenes: {len(current_chapter_scenes)})")
            return total_tokens
            
        except Exception as e:
            logger.error(f"Failed to calculate actual context size for chapter {chapter_id}: {e}", exc_info=True)
            # Don't return 0 on error - try to calculate at least base context
            try:
                # Try to get at least base context tokens
                story = db.query(Story).filter(Story.id == story_id).first()
                if story:
                    base_context_dict = {
                        "genre": story.genre or "",
                        "tone": story.tone or "",
                        "world_setting": story.world_setting or "",
                        "initial_premise": story.initial_premise or "",
                        "scenario": story.scenario or "",
                        "characters": []
                    }
                    base_tokens = self._calculate_base_context_tokens(base_context_dict)
                    logger.warning(f"[CONTEXT SIZE] Error occurred, returning base context tokens: {base_tokens}")
                    return base_tokens
            except Exception as e2:
                logger.error(f"Failed to calculate even base context: {e2}")
            
            # Last resort: return 0 (caller should handle this)
            return 0
    
    def _format_context_for_counting(self, context: Dict[str, Any]) -> str:
        """
        Format context for token counting - matches the format used in LLM service.
        This ensures we count tokens the same way they would be sent to the LLM.
        """
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
        
        if context.get("world_setting"):
            context_parts.append(f"Setting: {context['world_setting']}")
        
        if context.get("scenario"):
            context_parts.append(f"Story Scenario: {context['scenario']}")
        
        if context.get("initial_premise"):
            context_parts.append(f"Initial Premise: {context['initial_premise']}")
        
        # Handle characters - check if we have active/inactive separation
        characters = context.get("characters")
        if characters:
            if isinstance(characters, dict) and "active_characters" in characters:
                # Format active and inactive characters separately
                active_chars = characters.get("active_characters", [])
                inactive_chars = characters.get("inactive_characters", [])
                
                char_descriptions = []
                
                # Active characters - full details
                if active_chars:
                    char_descriptions.append("Active Characters (in this chapter):")
                    for char in active_chars:
                        char_desc = f"- {char.get('name', 'Unknown')}"
                        if char.get('role'):
                            char_desc += f" ({char['role']})"
                        char_desc += f": {char.get('description', 'No description')}"
                        if char.get('personality'):
                            char_desc += f". Personality: {char['personality']}"
                        if char.get('background'):
                            char_desc += f". Background: {char['background']}"
                        if char.get('goals'):
                            char_desc += f". Goals: {char['goals']}"
                        if char.get('fears'):
                            char_desc += f". Fears & Weaknesses: {char['fears']}"
                        if char.get('appearance'):
                            char_desc += f". Appearance: {char['appearance']}"
                        char_descriptions.append(char_desc)
                
                # Inactive characters - brief format
                if inactive_chars:
                    char_descriptions.append("\nInactive Characters (available for reference):")
                    for char in inactive_chars:
                        char_desc = f"- {char.get('name', 'Unknown')}"
                        if char.get('role'):
                            char_desc += f" ({char['role']})"
                        char_descriptions.append(char_desc)
                
                if char_descriptions:
                    context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
            else:
                # Legacy format - all characters are active
                char_descriptions = []
                for char in characters:
                    char_desc = f"- {char.get('name', 'Unknown')}"
                    if char.get('role'):
                        char_desc += f" ({char['role']})"
                    char_desc += f": {char.get('description', 'No description')}"
                    if char.get('personality'):
                        char_desc += f". Personality: {char['personality']}"
                    if char.get('background'):
                        char_desc += f". Background: {char['background']}"
                    if char.get('goals'):
                        char_desc += f". Goals: {char['goals']}"
                    if char.get('fears'):
                        char_desc += f". Fears & Weaknesses: {char['fears']}"
                    if char.get('appearance'):
                        char_desc += f". Appearance: {char['appearance']}"
                    char_descriptions.append(char_desc)
                context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")
        
        # Add chapter-specific context if available
        if context.get("chapter_location"):
            context_parts.append(f"Chapter Location: {context['chapter_location']}")
        if context.get("chapter_time_period"):
            context_parts.append(f"Chapter Time Period: {context['chapter_time_period']}")
        if context.get("chapter_scenario"):
            context_parts.append(f"Chapter Scenario: {context['chapter_scenario']}")
        
        # Add story_so_far if available (summary of all previous chapters)
        story_so_far = context.get("story_so_far")
        if story_so_far:
            context_parts.append(f"Story So Far:\n{story_so_far}")
        
        # Add previous chapter summary if available
        previous_chapter_summary = context.get("previous_chapter_summary")
        if previous_chapter_summary:
            context_parts.append(f"Previous Chapter Summary:\n{previous_chapter_summary}")
        
        # Add previous_scenes (this includes recent scenes, semantic scenes, entity states, etc.)
        if context.get("previous_scenes"):
            previous_scenes_text = context['previous_scenes']
            
            # Parse and organize previous_scenes into clear sections (matching LLM service format)
            import re
            
            # Extract Current Chapter Summary (if present)
            # Support both old "IMPORTANT OBJECTS:" and new "Notable Objects:" for backward compatibility
            # Note: Sections may have leading newlines, so we match them flexibly
            current_chapter_summary_match = re.search(r'Current Chapter Summary[^:]*:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
            current_chapter_summary = current_chapter_summary_match.group(1).strip() if current_chapter_summary_match else None
            
            # Extract Recent Scenes section
            recent_scenes_match = re.search(r'Recent Scenes:\s*(.*?)(?=\n+(?:Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
            recent_scenes_content = recent_scenes_match.group(1).strip() if recent_scenes_match else None
            
            # Extract Relevant Past Events (semantic search results)
            relevant_events_match = re.search(r'Relevant Past Events:\s*(.*?)(?=\n+(?:Recent Scenes|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
            relevant_events_content = relevant_events_match.group(1).strip() if relevant_events_match else None
            
            # Extract Entity States sections (may have leading newlines)
            entity_states_match = re.search(r'\n*(CURRENT CHARACTER STATES:.*?)(?=\n+(?:CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events)|$)', previous_scenes_text, re.DOTALL)
            entity_states_content = entity_states_match.group(1).strip() if entity_states_match else None
            
            locations_match = re.search(r'\n*CURRENT LOCATIONS:\s*(.*?)(?=\n+(?:IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES)|$)', previous_scenes_text, re.DOTALL)
            locations_content = locations_match.group(1).strip() if locations_match else None
            
            # Support both old and new object header names (may have leading newlines)
            # Try new format first, then fall back to old format
            objects_match = re.search(r'\n*Notable Objects:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
            if not objects_match:
                objects_match = re.search(r'\n*IMPORTANT OBJECTS:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
            objects_content = objects_match.group(1).strip() if objects_match else None
            
            # Build organized context sections
            # NEW ORDER: Entity states come BEFORE chapter progress and scenes (reduces recency bias)
            
            # Add Current State section if we have entity states (positioned early as reference material)
            if entity_states_content or locations_content or objects_content:
                context_parts.append("Current State:")
                
                if entity_states_content:
                    context_parts.append(f"  {entity_states_content.replace(chr(10), chr(10) + '  ')}")
                
                if locations_content:
                    context_parts.append(f"\n  CURRENT LOCATIONS:\n  {locations_content.replace(chr(10), chr(10) + '  ')}")
                
                if objects_content:
                    context_parts.append(f"\n  Notable Objects:\n  {objects_content.replace(chr(10), chr(10) + '  ')}")
            
            # Add Current Chapter Progress (positioned after entity states, before scenes)
            if current_chapter_summary or recent_scenes_content or relevant_events_content:
                context_parts.append("\nCurrent Chapter Progress:")
                
                if current_chapter_summary:
                    context_parts.append(f"  Current Chapter Summary:\n  {current_chapter_summary.replace(chr(10), chr(10) + '  ')}")
                
                if relevant_events_content:
                    context_parts.append(f"\n  Relevant Past Events (from semantic search):\n  {relevant_events_content.replace(chr(10), chr(10) + '  ')}")
                
                if recent_scenes_content:
                    context_parts.append(f"\n  Recent Scenes:\n  {recent_scenes_content.replace(chr(10), chr(10) + '  ')}")
            
            # If parsing failed, fall back to original format
            if not (current_chapter_summary or recent_scenes_content or relevant_events_content or entity_states_content):
                context_parts.append(f"Previous Events:\n{previous_scenes_text}")
        
        return "\n\n".join(context_parts)

# Global instance
context_manager = ContextManager()
