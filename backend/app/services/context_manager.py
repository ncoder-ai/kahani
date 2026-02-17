"""
Unified Context Manager

Single context manager that supports both linear and semantic (hybrid) context strategies.
The strategy is determined by user settings - no need for separate classes.
"""

import json
import logging
import re
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from ..models import Story, Scene, Character, StoryCharacter, StoryBranch, Chapter
from ..models import StoryFlow, SceneVariant, ChapterStatus
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

# Comprehensive stop word list for keyword search and temporal anchoring.
# Shared constant so both code paths filter the same words.
_SEARCH_STOP_WORDS = frozenset({
    # Articles, conjunctions, prepositions
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'into', 'about', 'over', 'after',
    'before', 'between', 'through', 'against', 'around', 'upon', 'without',
    # Pronouns, determiners
    'her', 'his', 'she', 'he', 'it', 'its', 'they', 'them', 'their',
    'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
    # Quantifiers
    'all', 'any', 'each', 'every', 'both', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'not', 'only', 'much', 'many',
    # Auxiliaries, modals
    'is', 'was', 'are', 'were', 'been', 'be', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
    'can', 'need',
    # Adverbs, filler words
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now',
    'then', 'here', 'there', 'when', 'where', 'why', 'how',
    'back', 'during', 'while', 'still', 'already', 'again',
    # Generic verbs (no discriminative power in keyword search)
    'like', 'looks', 'goes', 'gets', 'makes', 'takes', 'comes',
    'tells', 'asks', 'says', 'wants', 'acts', 'doing', 'done',
    'actions', 'things', 'stuff',
})


class ContextManager:
    """
    Unified context management for long stories that exceed LLM token limits.

    Supports two strategies:
    - "linear": Traditional recency-based context (recent scenes only)
    - "hybrid": Combines recent scenes with semantically relevant past scenes

    The strategy is determined by user settings (context_strategy).
    """

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

        # Load base context settings
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
            self.scene_batch_size = ctx_settings.get("scene_batch_size", 5)
            # Fill remaining context with older scenes (default True for backwards compatibility)
            self.fill_remaining_context = ctx_settings.get("fill_remaining_context", True)

            # Semantic memory settings (merged from SemanticContextManager)
            self.enable_semantic = ctx_settings.get("enable_semantic_memory", settings.enable_semantic_memory)
            self.semantic_top_k = ctx_settings.get("semantic_search_top_k", settings.semantic_search_top_k)
            self.semantic_scenes_in_context = ctx_settings.get("semantic_scenes_in_context", settings.semantic_scenes_in_context)
            self.semantic_weight = ctx_settings.get("semantic_context_weight", settings.semantic_context_weight)
            self.character_moments_in_context = ctx_settings.get("character_moments_in_context", settings.character_moments_in_context)
            self.context_strategy = ctx_settings.get("context_strategy", settings.context_strategy)
            self.auto_extract_character_moments = ctx_settings.get("auto_extract_character_moments", settings.auto_extract_character_moments)
            self.auto_extract_plot_events = ctx_settings.get("auto_extract_plot_events", settings.auto_extract_plot_events)
            self.extraction_confidence_threshold = ctx_settings.get("extraction_confidence_threshold", settings.extraction_confidence_threshold)
            # Settings for filtering
            self.semantic_min_similarity = ctx_settings.get("semantic_min_similarity", getattr(settings, "semantic_min_similarity", 0.3))
            self.location_recency_window = ctx_settings.get("location_recency_window", getattr(settings, "location_recency_window", 10))
        else:
            self.max_tokens = max_tokens or settings.context_max_tokens
            self.keep_recent_scenes = settings.context_keep_recent_scenes
            self.summary_threshold = settings.context_summary_threshold
            self.summary_threshold_tokens = getattr(settings, "context_summary_threshold_tokens", 10000)
            self.enable_summarization = True
            self.scene_batch_size = 5  # Default batch size for scene caching
            self.fill_remaining_context = True  # Default to filling remaining context

            # Semantic memory settings - defaults from global settings
            self.enable_semantic = settings.enable_semantic_memory
            self.semantic_top_k = settings.semantic_search_top_k
            self.semantic_scenes_in_context = settings.semantic_scenes_in_context
            self.semantic_weight = settings.semantic_context_weight
            self.character_moments_in_context = settings.character_moments_in_context
            self.context_strategy = settings.context_strategy
            self.auto_extract_character_moments = settings.auto_extract_character_moments
            self.auto_extract_plot_events = settings.auto_extract_plot_events
            self.extraction_confidence_threshold = settings.extraction_confidence_threshold
            self.semantic_min_similarity = getattr(settings, "semantic_min_similarity", 0.3)
            self.location_recency_window = getattr(settings, "location_recency_window", 10)

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

        # Initialize semantic memory service (graceful fallback if not available)
        self.semantic_memory = None
        if self.enable_semantic and self.context_strategy != "linear":
            try:
                from .semantic_memory import get_semantic_memory_service
                self.semantic_memory = get_semantic_memory_service()
                logger.info(f"Semantic memory available, strategy: {self.context_strategy}")
            except RuntimeError:
                logger.warning("Semantic memory not available, using linear context")
                self.enable_semantic = False
                self.context_strategy = "linear"
        
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
    
    async def build_story_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None, user_intent: Optional[str] = None, use_entity_states_snapshot: bool = False) -> Dict[str, Any]:
        """
        Build optimized context for story generation, managing token limits.

        Routes to either linear or hybrid context strategy based on settings.

        Args:
            story_id: Story ID
            db: Database session
            chapter_id: Optional chapter ID to separate active/inactive characters
            exclude_scene_id: Optional scene ID to exclude from context (for regeneration)
            branch_id: Optional branch ID (if not provided, uses active branch)
            user_intent: Optional user intent for semantic search query building
            use_entity_states_snapshot: If True and exclude_scene_id is provided, use saved
                entity_states_snapshot from the variant instead of current entity states.
                This ensures cache consistency when regenerating variants.

        Returns:
            Optimized context dict with story info, characters, and scene history
        """
        # Route based on strategy setting
        if not self.enable_semantic or self.context_strategy == "linear":
            return await self._build_linear_context(
                story_id, db, chapter_id, exclude_scene_id, branch_id,
                user_intent, use_entity_states_snapshot
            )
        return await self._build_hybrid_context(
            story_id, db, chapter_id, exclude_scene_id, branch_id,
            user_intent, use_entity_states_snapshot
        )

    async def _build_linear_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None, user_intent: Optional[str] = None, use_entity_states_snapshot: bool = False) -> Dict[str, Any]:
        """
        Build context using linear (recency-based) strategy.

        This is the original build_story_context implementation.
        Keeps the most recent scenes without semantic search.
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

            # Use snapshot as background if available, else fall back to static background
            background = self._get_snapshot_background(
                db, character.id, story.world_id,
                getattr(story, 'timeline_order', None),
                branch_id=branch_id,
            ) or character.background or ""

            char_data = {
                "name": character.name,
                "gender": character.gender or "",
                "role": sc.role or "",
                "description": character.description or "",
                "personality": ", ".join(character.personality_traits) if character.personality_traits else "",
                "background": background,
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
                    "gender": character.gender or "",
                    "role": sc.role or ""
                })
            else:
                # No chapter specified - treat all as active
                active_characters.append(char_data)
        
        # Add important NPCs with tiered recency-based inclusion
        try:
            from .npc_tracking_service import NPCTrackingService
            npc_service = NPCTrackingService(user_id=self.user_id, user_settings=self.user_settings)

            # Get current scene sequence for recency calculation
            current_scene_sequence = None
            if scenes:
                current_scene_sequence = max(s.sequence_number for s in scenes)

            # Collect explicit character names for cross-story dedup
            explicit_names = {c["name"].lower() for c in active_characters + inactive_characters}

            # Get tiered NPCs (active with full details, inactive with brief mention)
            tiered_npcs = npc_service.get_tiered_npcs_for_context(
                db=db,
                story_id=story_id,
                current_scene_sequence=current_scene_sequence,
                chapter_id=chapter_id,
                branch_id=branch_id,
                world_id=story.world_id,
                explicit_character_names=explicit_names
            )

            active_npc_characters = tiered_npcs.get("active_npcs", [])
            inactive_npc_characters = tiered_npcs.get("inactive_npcs", [])

            # Add active NPCs to active characters
            active_characters.extend(active_npc_characters)

            # Add inactive NPCs to inactive characters
            inactive_characters.extend(inactive_npc_characters)

            logger.info(f"[CONTEXT BUILD] Added {len(active_npc_characters)} active NPCs and {len(inactive_npc_characters)} inactive NPCs to context")
            if active_npc_characters:
                logger.info(f"[CONTEXT BUILD] Active NPCs: {[npc.get('name', 'Unknown') for npc in active_npc_characters]}")
            if inactive_npc_characters:
                logger.info(f"[CONTEXT BUILD] Inactive NPCs: {[npc.get('name', 'Unknown') for npc in inactive_npc_characters]}")
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
            
            # Add chapter plot guidance if available (from brainstorming)
            if hasattr(chapter, 'chapter_plot') and chapter.chapter_plot:
                base_context["chapter_plot"] = chapter.chapter_plot
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Including chapter_plot guidance")

            # Add plot progress (completed events) if available
            if hasattr(chapter, 'plot_progress') and chapter.plot_progress:
                base_context["plot_progress"] = chapter.plot_progress
                completed_count = len(chapter.plot_progress.get("completed_events", []))
                logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Including plot_progress ({completed_count} completed events)")

            # Add arc phase details if available
            if hasattr(chapter, 'arc_phase_id') and chapter.arc_phase_id:
                # Get the arc phase from the story
                if story.story_arc:
                    arc_phase = story.get_arc_phase(chapter.arc_phase_id)
                    if arc_phase:
                        base_context["arc_phase"] = arc_phase
                        logger.info(f"[CONTEXT BUILD] Chapter {chapter.chapter_number}: Including arc phase '{arc_phase.get('name', 'Unknown')}'")
            
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

        # For variant regeneration with snapshot, load ALL snapshotted context first
        # This ensures cache consistency by using the exact same context as the original generation
        context_snapshot = None
        if use_entity_states_snapshot and exclude_scene_id:
            context_snapshot = await self._load_entity_states_snapshot(db, exclude_scene_id)
            if context_snapshot:
                logger.info(f"[LINEAR CONTEXT] Using context snapshot from scene {exclude_scene_id} for cache consistency")
                # Apply snapshotted values
                if context_snapshot.get("entity_states_text"):
                    base_context["entity_states_text"] = context_snapshot["entity_states_text"]
                if context_snapshot.get("story_focus"):
                    base_context["story_focus"] = context_snapshot["story_focus"]
                    logger.info(f"[LINEAR CONTEXT] Applied snapshotted story_focus")
        # If no snapshot available, build dynamic context
        if not context_snapshot:
            # Add story focus (working memory + active plot threads)
            try:
                story_focus = self._build_story_focus(db, story_id, branch_id)
                if story_focus:
                    base_context["story_focus"] = story_focus
            except Exception as e:
                logger.warning(f"[CONTEXT BUILD] Failed to build story focus: {e}")

        # Add contradiction context (unresolved continuity warnings) - always fresh
        try:
            current_scene_sequence = max(s.sequence_number for s in scenes if s.sequence_number) if scenes else None
            contradiction_context = self._build_contradiction_context(db, story_id, branch_id, current_scene_sequence)
            if contradiction_context:
                base_context["contradiction_context"] = contradiction_context
        except Exception as e:
            logger.warning(f"[CONTEXT BUILD] Failed to build contradiction context: {e}")

        # Add chronicle context (character developments + location history)
        try:
            chronicle_context = self._build_chronicle_context(db, story_id, branch_id)
            if chronicle_context:
                base_context["chronicle_context"] = chronicle_context
        except Exception as e:
            logger.warning(f"[CONTEXT BUILD] Failed to build chronicle context: {e}")

        # Entity states removed from prompt — no longer building entity_states_text

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

    def _build_story_focus(self, db: Session, story_id: int, branch_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Build story focus context from working memory and plot events.

        Returns a dict with:
        - active_threads: From unresolved PlotEvents (major story threads)
        - recent_focus: From WorkingMemory (what was important recently)
        - pending_items: From WorkingMemory (things needing follow-up)
        - character_spotlight: From WorkingMemory (who needs attention)
        """
        try:
            from ..models import PlotEvent, WorkingMemory

            story_focus = {}

            # Get active threads from unresolved PlotEvents
            plot_events = db.query(PlotEvent).filter(
                PlotEvent.story_id == story_id,
                PlotEvent.is_resolved == False
            )
            if branch_id:
                plot_events = plot_events.filter(PlotEvent.branch_id == branch_id)

            # Add secondary sort by id for deterministic ordering (cache stability)
            plot_events = plot_events.order_by(
                PlotEvent.importance_score.desc().nullsfirst(),
                PlotEvent.id.asc()
            ).limit(5).all()

            if plot_events:
                story_focus["active_threads"] = [pe.description for pe in plot_events if pe.description]

            # Get working memory for micro-level tracking (if enabled)
            ctx_settings = self.user_settings.get('context_settings', {})
            if ctx_settings.get('enable_working_memory', True):
                wm_query = db.query(WorkingMemory).filter(
                    WorkingMemory.story_id == story_id
                )
                if branch_id:
                    wm_query = wm_query.filter(WorkingMemory.branch_id == branch_id)

                working_memory = wm_query.first()

                if working_memory:
                    if working_memory.recent_focus:
                        story_focus["recent_focus"] = working_memory.recent_focus[:3]
                    if working_memory.character_spotlight:
                        story_focus["character_spotlight"] = working_memory.character_spotlight

            # Only return if we have something useful
            if story_focus:
                logger.info(f"[CONTEXT BUILD] Story focus: threads={len(story_focus.get('active_threads', []))}, "
                           f"focus={len(story_focus.get('recent_focus', []))}, "
                           f"spotlight={len(story_focus.get('character_spotlight', {}))}")
                return story_focus

            return None

        except Exception as e:
            logger.warning(f"[CONTEXT BUILD] Error building story focus: {e}")
            return None

    def _build_contradiction_context(self, db: Session, story_id: int, branch_id: Optional[int], current_scene_sequence: Optional[int] = None) -> Optional[List[str]]:
        """
        Build contradiction context from unresolved contradictions.

        Only includes contradictions from recent scenes (within the visible context window)
        so the LLM only sees warnings it can actually address.

        Returns a list of concise warning strings for the LLM to naturally address.
        """
        try:
            from ..models import Contradiction

            ctx_settings = self.user_settings.get('context_settings', {})
            if not ctx_settings.get('enable_contradiction_injection', True):
                return None

            severity_threshold = ctx_settings.get('contradiction_severity_threshold', 'info')
            severity_order = {'info': 0, 'warning': 1, 'error': 2}
            threshold_level = severity_order.get(severity_threshold, 0)

            query = db.query(Contradiction).filter(
                Contradiction.story_id == story_id,
                Contradiction.resolved == False
            )
            if branch_id:
                query = query.filter(Contradiction.branch_id == branch_id)

            # Recency filter: only show contradictions from scenes within the recent
            # context window (keep_recent_scenes * batch_size). Older contradictions
            # are stale — characters naturally move between rooms over many scenes.
            if current_scene_sequence:
                recent_window = self.keep_recent_scenes * self.scene_batch_size
                min_scene = current_scene_sequence - recent_window
                query = query.filter(Contradiction.scene_sequence >= min_scene)

            contradictions = query.order_by(Contradiction.detected_at.desc()).limit(10).all()

            # Filter by severity, take up to 5
            filtered = [c for c in contradictions if severity_order.get(c.severity, 0) >= threshold_level][:5]
            if not filtered:
                return None

            # Format as concise warning strings
            warnings = []
            for c in filtered:
                type_label = c.contradiction_type.replace('_', ' ').title()
                char_part = f" {c.character_name}:" if c.character_name else ""
                if c.previous_value and c.current_value:
                    issue = f'was "{c.previous_value}" but now "{c.current_value}"'
                else:
                    issue = c.current_value or c.previous_value or "unknown"
                warnings.append(f"- [{type_label}]{char_part} {issue} (scene {c.scene_sequence})")

            logger.info(f"[CONTEXT BUILD] Contradiction context: {len(warnings)} warnings for story {story_id}")
            return warnings

        except Exception as e:
            logger.warning(f"[CONTEXT BUILD] Error building contradiction context: {e}")
            return None

    def _get_snapshot_background(self, db: Session, character_id: int, world_id: Optional[int], story_timeline_order: Optional[int], branch_id: Optional[int] = None) -> Optional[str]:
        """
        Get character snapshot text to use as background, if a valid snapshot exists.

        A snapshot is valid when its timeline_order <= the current story's timeline_order,
        meaning it covers events up to or before the current story's position.
        Prefers branch-specific snapshot over NULL branch snapshot.
        """
        if not world_id:
            return None
        try:
            from ..models import CharacterSnapshot
            from sqlalchemy import or_
            query = db.query(CharacterSnapshot).filter(
                CharacterSnapshot.world_id == world_id,
                CharacterSnapshot.character_id == character_id,
                or_(CharacterSnapshot.branch_id == branch_id, CharacterSnapshot.branch_id.is_(None)),
            ).order_by(CharacterSnapshot.branch_id.desc().nullslast())
            snapshot = query.first()
            if not snapshot:
                return None
            # If neither has a timeline order, use the snapshot
            if snapshot.timeline_order is None or story_timeline_order is None:
                return snapshot.snapshot_text
            # Snapshot must cover at or before the current story's timeline position
            if snapshot.timeline_order <= story_timeline_order:
                return snapshot.snapshot_text
            return None
        except Exception as e:
            logger.warning(f"[CONTEXT] Failed to get snapshot for character {character_id}: {e}")
            return None

    def _build_chronicle_context(self, db: Session, story_id: int, branch_id: Optional[int]) -> Optional[str]:
        """
        Build chronicle context from character snapshots (preferred) or individual entries (fallback),
        plus location lorebook events.

        If a CharacterSnapshot exists for a character, uses the snapshot paragraph.
        Otherwise falls back to individual chronicle entries for that character.
        Location lorebook entries are always individual bullets (no snapshot equivalent).

        Returns formatted text or None if no entries exist.
        """
        try:
            from ..models import CharacterChronicle, LocationLorebook, Character, CharacterSnapshot

            # Get story to check world_id
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story or not story.world_id:
                return None

            world_id = story.world_id

            # Query character snapshots for this world/story/branch
            snapshot_query = db.query(CharacterSnapshot, Character.name).join(
                Character, CharacterSnapshot.character_id == Character.id
            ).filter(
                CharacterSnapshot.world_id == world_id,
            )
            if branch_id:
                snapshot_query = snapshot_query.filter(
                    or_(CharacterSnapshot.branch_id == branch_id, CharacterSnapshot.branch_id.is_(None))
                )
            else:
                snapshot_query = snapshot_query.filter(CharacterSnapshot.branch_id.is_(None))
            snapshots = snapshot_query.all()
            snapshot_by_char_id = {snap.character_id: (snap, char_name) for snap, char_name in snapshots}

            # Query character chronicle entries (for fallback characters without snapshots)
            char_query = db.query(CharacterChronicle, Character.name).join(
                Character, CharacterChronicle.character_id == Character.id
            ).filter(
                CharacterChronicle.world_id == world_id,
                CharacterChronicle.story_id == story_id,
            )
            if branch_id:
                char_query = char_query.filter(
                    or_(CharacterChronicle.branch_id == branch_id, CharacterChronicle.branch_id.is_(None))
                )
            char_entries = char_query.order_by(CharacterChronicle.sequence_order.asc()).all()

            # Query location lorebook entries
            loc_query = db.query(LocationLorebook).filter(
                LocationLorebook.world_id == world_id,
                LocationLorebook.story_id == story_id,
            )
            if branch_id:
                loc_query = loc_query.filter(
                    or_(LocationLorebook.branch_id == branch_id, LocationLorebook.branch_id.is_(None))
                )
            loc_entries = loc_query.order_by(LocationLorebook.sequence_order.asc()).all()

            if not char_entries and not loc_entries and not snapshots:
                return None

            # Group character entries by character_id and name (for fallback)
            char_groups = {}  # char_id -> (name, [entries])
            for chronicle, char_name in char_entries:
                if chronicle.character_id not in char_groups:
                    char_groups[chronicle.character_id] = (char_name, [])
                char_groups[chronicle.character_id][1].append(chronicle)

            # Group location entries by name
            loc_groups = {}
            for entry in loc_entries:
                if entry.location_name not in loc_groups:
                    loc_groups[entry.location_name] = []
                loc_groups[entry.location_name].append(entry)

            # Format output — snapshots for characters that have them, entries for others
            MAX_CHARS = 6000
            parts = []
            total_chars = 0
            snapshot_count = 0
            fallback_count = 0

            # Collect all character IDs that have either snapshots or entries
            all_char_ids = set(snapshot_by_char_id.keys()) | set(char_groups.keys())

            if all_char_ids:
                parts.append("Characters:")
                total_chars += 12

                for char_id in all_char_ids:
                    if char_id in snapshot_by_char_id:
                        # Use snapshot paragraph
                        snap, char_name = snapshot_by_char_id[char_id]
                        snap_text = f"\n{char_name}:\n{snap.snapshot_text}"
                        snap_len = len(snap_text)
                        if total_chars + snap_len > MAX_CHARS:
                            continue
                        parts.append(snap_text)
                        total_chars += snap_len
                        snapshot_count += 1
                    elif char_id in char_groups:
                        # Fallback: individual entries
                        name, entries = char_groups[char_id]
                        entries.sort(key=lambda e: (not e.is_defining, -e.sequence_order))

                        char_lines = [f"\n{name}:"]
                        for entry in entries:
                            line = f"- [{entry.entry_type.value.replace('_', ' ')}] {entry.description}"
                            line_len = len(line) + 1
                            if total_chars + line_len > MAX_CHARS:
                                if not entry.is_defining:
                                    continue
                            char_lines.append(line)
                            total_chars += line_len

                        if len(char_lines) > 1:
                            parts.append("\n".join(char_lines))
                            fallback_count += 1

            if loc_groups and total_chars < MAX_CHARS:
                parts.append("\nLocations:")
                total_chars += 12

                for name, entries in loc_groups.items():
                    entries.sort(key=lambda e: -e.sequence_order)

                    loc_lines = [f"\n{name}:"]
                    for entry in entries:
                        line = f"- {entry.event_description}"
                        line_len = len(line) + 1
                        if total_chars + line_len > MAX_CHARS:
                            continue
                        loc_lines.append(line)
                        total_chars += line_len

                    if len(loc_lines) > 1:
                        parts.append("\n".join(loc_lines))

            result = "\n".join(parts).strip()
            if not result:
                return None

            logger.info(f"[CONTEXT BUILD] Chronicle context: {snapshot_count} snapshots, {fallback_count} fallback characters, {len(loc_entries)} location entries ({total_chars} chars)")
            return result

        except Exception as e:
            logger.warning(f"[CONTEXT BUILD] Error building chronicle context: {e}")
            return None

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
                "included_scenes": len(scenes),
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
                "included_scenes": 0,
                "context_strategy": "empty"
            }

        # If fill_remaining_context is disabled, only include keep_recent_scenes
        # This helps weaker LLMs focus on recent context without dilution
        if not self.fill_remaining_context:
            recent_scenes = scenes[-self.keep_recent_scenes:]
            scene_contents = []
            for scene in recent_scenes:
                scene_content = await self._get_scene_content_proper(scene, db)
                scene_contents.append(scene_content)
            combined_content = "\n\n".join(scene_contents)
            logger.info(f"[LINEAR CONTEXT] Fill remaining context disabled: using only {len(recent_scenes)} recent scenes")
            return {
                "previous_scenes": combined_content,
                "recent_scenes": combined_content,
                "scene_summary": f"Recent {len(recent_scenes)} scenes (fill disabled)",
                "total_scenes": len(recent_scenes),
                "included_scenes": len(recent_scenes),
                "context_strategy": "recent_only"
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
            "included_scenes": len(included_scenes),
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
                
                # Get max tokens for this template - use user's setting
                max_tokens = prompt_manager.get_max_tokens("story_summary", self.user_settings)

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

    async def build_scene_generation_context(self, story_id: int, db: Session, custom_prompt: str = "", is_variant_generation: bool = False, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None, use_entity_states_snapshot: bool = False) -> Dict[str, Any]:
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
            use_entity_states_snapshot: If True and exclude_scene_id is provided, use saved
                entity_states_snapshot from the variant for cache consistency
        """
        # DEBUG: Log custom_prompt at entry point
        if custom_prompt is None:
            logger.warning(f"[CONTEXT_MANAGER] build_scene_generation_context: custom_prompt=None, is_variant={is_variant_generation}")
        elif not custom_prompt.strip():
            logger.warning(f"[CONTEXT_MANAGER] build_scene_generation_context: custom_prompt=EMPTY, is_variant={is_variant_generation}")
        else:
            logger.info(f"[CONTEXT_MANAGER] build_scene_generation_context: custom_prompt='{custom_prompt[:80]}', is_variant={is_variant_generation}")

        # Get full context with chapter_id for character separation and branch_id for branch filtering
        # Pass custom_prompt as user_intent so semantic search can find scenes relevant to the user's choice
        full_context = await self.build_story_context(story_id, db, chapter_id=chapter_id, exclude_scene_id=exclude_scene_id, branch_id=branch_id, user_intent=custom_prompt, use_entity_states_snapshot=use_entity_states_snapshot)
        
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
        # Use "previous_scenes" which contains full context (including semantic scenes for hybrid strategy)
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
            "current_chapter_summary": full_context.get("current_chapter_summary"),
            # Add chapter plot guidance (from brainstorming)
            "chapter_plot": full_context.get("chapter_plot"),
            "plot_progress": full_context.get("plot_progress"),  # Track completed events for choice generation
            "arc_phase": full_context.get("arc_phase"),
            # Pacing guidance will be added below if enabled
            "pacing_guidance": None,
            # Working memory & active plot threads
            "story_focus": full_context.get("story_focus"),
            # Contradiction context (unresolved continuity warnings)
            "contradiction_context": full_context.get("contradiction_context"),
            # Chronicle context (character developments + location history)
            "chronicle_context": full_context.get("chronicle_context"),
            # Entity states (character states, locations, objects) - passed separately for independent message positioning
            "entity_states_text": full_context.get("entity_states_text"),
            # Semantic scenes - passed separately for dedicated message positioning (LAST before task)
            "semantic_scenes_text": full_context.get("semantic_scenes_text"),
            # Internal refs for multi-query decomposition in service.py
            "_semantic_search_state": full_context.get("_semantic_search_state"),
            "_context_manager_ref": full_context.get("_context_manager_ref"),
            "_context_snapshot": full_context.get("_context_snapshot"),
        }
        
        # Add pacing guidance if chapter plot tracking is enabled
        gen_prefs = self.user_settings.get("generation_preferences", {})
        enable_plot_tracking = gen_prefs.get("enable_chapter_plot_tracking", True)
        
        if enable_plot_tracking and chapter_id and scene_context.get("chapter_plot"):
            try:
                from .chapter_progress_service import ChapterProgressService
                chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
                if chapter:
                    # Get plot_check_mode from story (defaults to user preference or "all")
                    story = db.query(Story).filter(Story.id == chapter.story_id).first()
                    plot_check_mode = "all"
                    if story and story.plot_check_mode:
                        plot_check_mode = story.plot_check_mode
                    elif gen_prefs.get("default_plot_check_mode"):
                        plot_check_mode = gen_prefs.get("default_plot_check_mode")

                    progress_service = ChapterProgressService(db)
                    pacing_guidance = progress_service.generate_pacing_guidance(chapter, plot_check_mode=plot_check_mode)
                    if pacing_guidance:
                        scene_context["pacing_guidance"] = pacing_guidance
                        logger.info(f"[CONTEXT BUILD] Added pacing guidance for chapter {chapter_id} (plot_check_mode={plot_check_mode})")
            except Exception as e:
                logger.warning(f"[CONTEXT BUILD] Failed to generate pacing guidance: {e}")

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
        
        # Add story_so_far if available (cumulative summary of all previous chapters)
        # Note: previous_chapter_summary removed as redundant with story_so_far
        story_so_far = context.get("story_so_far")
        if story_so_far:
            context_parts.append(f"Story So Far:\n{story_so_far}")

        # Add previous_scenes (this includes recent scenes, semantic scenes, entity states, etc.)
        if context.get("previous_scenes"):
            previous_scenes_text = context['previous_scenes']
            
            # Parse and organize previous_scenes into clear sections (matching LLM service format)
            import re
            
            # Try NEW format first: "Relevant Context:" combined section
            relevant_context_match = re.search(r'Relevant Context:\n(.*?)(?=\n\nRecent Scenes:|$)', previous_scenes_text, re.DOTALL)
            recent_scenes_match = re.search(r'Recent Scenes:(.*?)$', previous_scenes_text, re.DOTALL)
            
            # Extract Current Chapter Summary (if present) - works with both old and new format
            current_chapter_summary_match = re.search(r'Current Chapter Summary[^:]*:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Context|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Active Objects)|$)', previous_scenes_text, re.DOTALL)
            current_chapter_summary = current_chapter_summary_match.group(1).strip() if current_chapter_summary_match else None
            
            if relevant_context_match:
                # NEW FORMAT: Combined "Relevant Context" section
                relevant_context_content = relevant_context_match.group(1).strip()
                recent_scenes_content = recent_scenes_match.group(1).strip() if recent_scenes_match else None
                
                # Add Current Chapter Progress (positioned before relevant context)
                if current_chapter_summary:
                    context_parts.append("Current Chapter Progress:")
                    context_parts.append(f"  Current Chapter Summary:\n  {current_chapter_summary.replace(chr(10), chr(10) + '  ')}")
                
                # Add Relevant Context (combined semantic events + entity states)
                if relevant_context_content:
                    context_parts.append(f"\nRelevant Context:\n{relevant_context_content}")
                
                # Add Recent Scenes
                if recent_scenes_content:
                    context_parts.append(f"\nRecent Scenes:\n{recent_scenes_content}")
            else:
                # OLD FORMAT (backward compatibility): Separate sections
                recent_scenes_content = re.search(r'Recent Scenes:\s*(.*?)(?=\n+(?:Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
                recent_scenes_content = recent_scenes_content.group(1).strip() if recent_scenes_content else None
                
                # Extract Relevant Past Events (semantic search results)
                relevant_events_match = re.search(r'Relevant Past Events:\s*(.*?)(?=\n+(?:Recent Scenes|CURRENT CHARACTER STATES|CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects)|$)', previous_scenes_text, re.DOTALL)
                relevant_events_content = relevant_events_match.group(1).strip() if relevant_events_match else None
                
                # Extract Entity States sections (may have leading newlines)
                entity_states_match = re.search(r'\n*(CURRENT CHARACTER STATES:.*?)(?=\n+(?:CURRENT LOCATIONS|IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events)|$)', previous_scenes_text, re.DOTALL)
                entity_states_content = entity_states_match.group(1).strip() if entity_states_match else None
                
                locations_match = re.search(r'\n*CURRENT LOCATIONS:\s*(.*?)(?=\n+(?:IMPORTANT OBJECTS|Notable Objects|Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES)|$)', previous_scenes_text, re.DOTALL)
                locations_content = locations_match.group(1).strip() if locations_match else None
                
                # Support both old and new object header names (may have leading newlines)
                objects_match = re.search(r'\n*(?:Notable Objects|Active Objects):\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
                if not objects_match:
                    objects_match = re.search(r'\n*IMPORTANT OBJECTS:\s*(.*?)(?=\n+(?:Recent Scenes|Relevant Past Events|CURRENT CHARACTER STATES|CURRENT LOCATIONS)|$)', previous_scenes_text, re.DOTALL)
                objects_content = objects_match.group(1).strip() if objects_match else None
                
                # Build organized context sections
                # Add Current State section if we have entity states
                if entity_states_content or locations_content or objects_content:
                    context_parts.append("Current State:")
                    
                    if entity_states_content:
                        context_parts.append(f"  {entity_states_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if locations_content:
                        context_parts.append(f"\n  CURRENT LOCATIONS:\n  {locations_content.replace(chr(10), chr(10) + '  ')}")
                    
                    if objects_content:
                        context_parts.append(f"\n  Active Objects:\n  {objects_content.replace(chr(10), chr(10) + '  ')}")
                
                # Add Current Chapter Progress
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

    # ========================================================================
    # HYBRID/SEMANTIC CONTEXT METHODS (merged from SemanticContextManager)
    # ========================================================================

    def _get_batch_aligned_recent_scenes(self, scenes: List) -> List:
        """
        Select scenes aligned to batch boundaries for optimal LLM cache hits.

        Instead of a rolling window (last N scenes), this selects:
        1. N complete batches (stable across consecutive scene generations)
        2. All scenes in the active/incomplete batch (changes each scene)

        For example, with batch_size=5 and current scene 237:
        - Active batch = 47 (scenes 236-240), currently has 236-237
        - If keep_recent_scenes=10 (2 batches worth):
          - Include batch 46 (scenes 231-235) - COMPLETE, stable
          - Include batch 45 (scenes 226-230) - COMPLETE, stable
          - Include active batch scenes 236-237

        This ensures cache hits on complete batches between consecutive generations.

        Args:
            scenes: List of Scene objects, ordered by sequence number

        Returns:
            List of Scene objects to include in context
        """
        if not scenes:
            return []

        batch_size = self.scene_batch_size

        # Get the highest sequence number (current scene position)
        max_seq = max(s.sequence_number for s in scenes if s.sequence_number)

        # Calculate active batch number (0-indexed)
        # Scene 1-5 = batch 0, 6-10 = batch 1, etc.
        active_batch_num = (max_seq - 1) // batch_size

        # Use keep_recent_scenes as the number of complete batches to include
        # (frontend now shows this as "Recent Scene Batches")
        # Cap at 5 batches max to prevent old settings (which meant "scenes") from exploding context
        num_complete_batches = min(5, max(1, self.keep_recent_scenes))

        # Calculate the range of batches to include
        # Start from (active_batch - num_complete_batches) up to active_batch
        start_batch = max(0, active_batch_num - num_complete_batches)

        # Calculate scene sequence range
        # start_batch's first scene: start_batch * batch_size + 1
        min_seq = start_batch * batch_size + 1

        # Include all scenes from min_seq to max_seq
        selected_scenes = [s for s in scenes if s.sequence_number and min_seq <= s.sequence_number <= max_seq]

        # Sort by sequence number
        selected_scenes.sort(key=lambda s: s.sequence_number)

        logger.debug(f"[BATCH ALIGN] max_seq={max_seq}, active_batch={active_batch_num}, "
                    f"start_batch={start_batch}, min_seq={min_seq}, selected={len(selected_scenes)}")

        return selected_scenes

    async def _build_hybrid_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None, user_intent: Optional[str] = None, use_entity_states_snapshot: bool = False) -> Dict[str, Any]:
        """
        Build hybrid context combining recent scenes with semantically relevant past.

        Args:
            story_id: Story ID
            db: Database session
            chapter_id: Optional chapter ID to separate active/inactive characters
            exclude_scene_id: Optional scene ID to exclude from context (for regeneration)
            branch_id: Optional branch ID (if not provided, uses active branch)
            user_intent: User's continue option - influences which past scenes are retrieved
            use_entity_states_snapshot: If True and exclude_scene_id is provided, use saved
                entity_states_snapshot from the variant for cache consistency

        Strategy:
        1. Get base context (genre, tone, characters)
        2. Get recent scenes (immediate context)
        3. Semantic search for relevant past scenes
        4. Get character-specific moments
        5. Get chapter summaries
        6. Assemble within token budget
        """
        # Get story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise ValueError(f"Story {story_id} not found")

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)

        # If exclude_scene_id is provided, use same logic as new scene generation
        # Get all scenes BEFORE the excluded scene (by sequence_number) for cache consistency
        # This ensures variant regeneration sees the SAME context as when the original was generated
        excluded_scene_sequence = None  # Track for entity state filtering
        if exclude_scene_id:
            # Get the scene being excluded
            excluded_scene = db.query(Scene).filter(Scene.id == exclude_scene_id).first()
            if excluded_scene:
                excluded_scene_sequence = excluded_scene.sequence_number  # Store for entity state filtering
            if excluded_scene and excluded_scene.chapter_id:
                # Use the EXCLUDED SCENE's sequence_number to determine context range
                # This ensures we include only scenes that existed BEFORE this scene was generated,
                # maximizing cache hits for variant regeneration
                scene_chapter = db.query(Chapter).filter(Chapter.id == excluded_scene.chapter_id).first()

                if scene_chapter:
                    # Include ONLY scenes with sequence_number < excluded scene's sequence_number
                    # This matches what the LLM saw when the original scene was generated
                    scene_query = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.is_deleted == False,
                        Scene.sequence_number < excluded_scene.sequence_number  # Only scenes BEFORE this one
                    )
                    if branch_id:
                        scene_query = scene_query.filter(Scene.branch_id == branch_id)
                    scenes = scene_query.order_by(Scene.sequence_number).all()
                    logger.info(f"[HYBRID CONTEXT BUILD] Variant regeneration for scene {exclude_scene_id} (seq {excluded_scene.sequence_number}): Including {len(scenes)} scenes (seq 1 to {excluded_scene.sequence_number - 1})")
                else:
                    # Fallback: if chapter not found, still use sequence_number filter
                    scene_query = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.is_deleted == False,
                        Scene.sequence_number < excluded_scene.sequence_number
                    )
                    if branch_id:
                        scene_query = scene_query.filter(Scene.branch_id == branch_id)
                    scenes = scene_query.order_by(Scene.sequence_number).all()
                    logger.warning(f"[HYBRID CONTEXT BUILD] Scene {exclude_scene_id}'s chapter not found, using {len(scenes)} scenes before seq {excluded_scene.sequence_number}")
            else:
                # Scene not found - fall back to all scenes (shouldn't happen)
                scene_query = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.warning(f"[HYBRID CONTEXT BUILD] Excluded scene {exclude_scene_id} not found, using all {len(scenes)} scenes")
        # Get all scenes ordered by sequence
        # When chapter_id is provided, include scenes from ALL chapters up to and including that chapter
        elif chapter_id:
            # Get the chapter to find its chapter_number
            active_chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

            if active_chapter:
                # Include scenes from all chapters with chapter_number <= active chapter's chapter_number
                # This ensures we include previous chapters but exclude future chapters
                scene_query = db.query(Scene).join(Chapter).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False,
                    Chapter.chapter_number <= active_chapter.chapter_number
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter_id} (Chapter {active_chapter.chapter_number}): Including scenes from chapters 1-{active_chapter.chapter_number} ({len(scenes)} scenes)")
            else:
                # Fallback: if chapter not found, only get scenes from that chapter_id
                scene_query = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False,
                    Scene.chapter_id == chapter_id
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.warning(f"[HYBRID CONTEXT BUILD] Chapter {chapter_id} not found, falling back to chapter_id filter only")

            # Note: continues_from_previous is handled in base context building
            # Semantic search still searches across all chapters (limit_to_chapter_id controls this separately)
        else:
            scene_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            )
            if branch_id:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scenes = scene_query.order_by(Scene.sequence_number).all()

        if not scenes:
            # No scenes yet — but if this story is in a multi-story world,
            # still set up world scope so cross-story recall can fire via service.py
            base_context = await self._get_base_context(story_id, db, chapter_id=chapter_id, branch_id=branch_id)
            world_scope = self._resolve_world_search_scope(story_id, branch_id, db)
            if world_scope:
                base_tokens = self._calculate_base_context_tokens(base_context)
                available_tokens = self.effective_max_tokens - base_tokens - 500
                semantic_tokens = min(int(available_tokens * 0.5), 4000)  # Conservative budget for first scene
                base_context["_semantic_search_state"] = {
                    "user_intent": user_intent,
                    "story_id": story_id,
                    "exclude_sequences": [],
                    "branch_id": branch_id,
                    "chapter_id": chapter_id,
                    "dominant_chapter_id": chapter_id,
                    "token_budget": semantic_tokens,
                    "single_query_results": [],
                    "intent_result": None,
                    "world_scope": world_scope,
                    "exclude_scene_ids": set(),
                }
                base_context["_context_manager_ref"] = self
                logger.info(f"[HYBRID CONTEXT] No scenes yet but world scope available — enabling cross-story recall")
            return base_context

        # Calculate base context tokens
        base_context = await self._get_base_context(story_id, db, chapter_id=chapter_id, branch_id=branch_id)
        base_tokens = self._calculate_base_context_tokens(base_context)

        # Available tokens for scene history (using effective max tokens)
        available_tokens = self.effective_max_tokens - base_tokens - 500  # Safety buffer

        if available_tokens <= 0:
            logger.warning(f"Base context too large for story {story_id}")
            return base_context

        # Build scene context using hybrid strategy
        scene_context = await self._build_hybrid_scene_context(
            story_id, scenes, available_tokens, db, chapter_id=chapter_id, branch_id=branch_id, user_intent=user_intent,
            excluded_scene_sequence=excluded_scene_sequence,
            use_entity_states_snapshot=use_entity_states_snapshot,
            exclude_scene_id=exclude_scene_id
        )

        # Check if we have a context snapshot from variant regeneration
        # If so, use snapshotted story_focus and relationship_context for cache consistency
        context_snapshot = scene_context.pop("_context_snapshot", None)

        if context_snapshot:
            # Use snapshotted values for cache consistency
            if context_snapshot.get("story_focus"):
                base_context["story_focus"] = context_snapshot["story_focus"]
                logger.info(f"[HYBRID CONTEXT] Applied snapshotted story_focus for cache consistency")
        # Only build dynamic context if no snapshot was available
        if not context_snapshot:
            # Add story focus (working memory + active plot threads)
            try:
                story_focus = self._build_story_focus(db, story_id, branch_id)
                if story_focus:
                    base_context["story_focus"] = story_focus
            except Exception as e:
                logger.warning(f"[HYBRID CONTEXT BUILD] Failed to build story focus: {e}")

        # Add contradiction context (unresolved continuity warnings)
        try:
            current_seq_for_contradictions = None
            if scenes:
                current_seq_for_contradictions = max(s.sequence_number for s in scenes if s.sequence_number) if scenes else None
            contradiction_context = self._build_contradiction_context(db, story_id, branch_id, current_seq_for_contradictions)
            if contradiction_context:
                base_context["contradiction_context"] = contradiction_context
        except Exception as e:
            logger.warning(f"[HYBRID CONTEXT BUILD] Failed to build contradiction context: {e}")

        # Add chronicle context (character developments + location history)
        try:
            chronicle_context = self._build_chronicle_context(db, story_id, branch_id)
            if chronicle_context:
                base_context["chronicle_context"] = chronicle_context
        except Exception as e:
            logger.warning(f"[HYBRID CONTEXT BUILD] Failed to build chronicle context: {e}")

        # Merge contexts
        return {**base_context, **scene_context}

    _VALID_INTENTS = {"direct", "recall", "react"}
    _VALID_TEMPORALS = {"earliest", "latest", "any"}

    async def _classify_intent(self, user_intent: str) -> Optional[dict]:
        """
        Classify user intent via extraction LLM before semantic search.

        Returns dict with {intent, temporal, queries, keywords} or None if
        classification is unavailable (extraction LLM down, not configured, etc.).
        On failure, caller should fall back to running semantic search as usual.
        """
        ext_settings = self.user_settings.get('extraction_model_settings', {})
        if not ext_settings.get('enabled', False):
            return None

        try:
            from .llm.extraction_service import ExtractionLLMService
            from .llm.prompts import prompt_manager

            ext_defaults = settings._yaml_config.get('extraction_model', {})
            url = ext_settings.get('url', ext_defaults.get('url'))
            model = ext_settings.get('model_name', ext_defaults.get('model_name'))
            if not url or not model:
                return None

            api_key = ext_settings.get('api_key', ext_defaults.get('api_key', ''))
            temperature = ext_settings.get('temperature', ext_defaults.get('temperature', 0.3))
            max_tokens = ext_settings.get('max_tokens', ext_defaults.get('max_tokens', 2000))
            top_p = ext_settings.get('top_p', ext_defaults.get('top_p', 1.0))
            repetition_penalty = ext_settings.get('repetition_penalty', ext_defaults.get('repetition_penalty', 1.0))
            min_p = ext_settings.get('min_p', ext_defaults.get('min_p', 0.0))
            thinking_disable_method = ext_settings.get('thinking_disable_method', ext_defaults.get('thinking_disable_method', 'none'))
            thinking_disable_custom = ext_settings.get('thinking_disable_custom', ext_defaults.get('thinking_disable_custom', ''))
            llm_settings = self.user_settings.get('llm_settings', {})
            timeout_total = llm_settings.get('timeout_total', 240)

            extraction_service = ExtractionLLMService(
                url=url, model=model, api_key=api_key,
                temperature=temperature, max_tokens=max_tokens,
                timeout_total=timeout_total, top_p=top_p,
                repetition_penalty=repetition_penalty, min_p=min_p,
                thinking_disable_method=thinking_disable_method,
                thinking_disable_custom=thinking_disable_custom,
            )

            decompose_task = prompt_manager.get_prompt("semantic_decompose", "user", user_intent=user_intent)
            if not decompose_task:
                return None

            allow_thinking = ext_settings.get('thinking_enabled_memory', True)
            messages = [{"role": "user", "content": decompose_task}]
            response = await extraction_service.generate_with_messages(
                messages=messages, max_tokens=300, allow_thinking=allow_thinking
            )

            if not response or not response.strip():
                return None

            return self._parse_decomposition_response(response)
        except Exception as e:
            logger.warning(f"[INTENT CLASSIFY] Failed ({e}), falling back to semantic search")
            return None

    def _parse_decomposition_response(self, response: str) -> Optional[dict]:
        """Parse intent-aware JSON from decomposition LLM. Returns dict or None."""
        def _extract(result: dict) -> Optional[dict]:
            queries = result.get("queries")
            if not isinstance(queries, list) or not all(isinstance(s, str) for s in queries):
                return None
            intent = (result.get("intent") or "").lower().strip()
            intent = intent if intent in self._VALID_INTENTS else None
            temporal = (result.get("temporal") or "").lower().strip()
            temporal = temporal if temporal in self._VALID_TEMPORALS else None
            parsed = [s.strip() for s in queries[:6] if s.strip()]
            kw_raw = result.get("keywords", [])
            keywords = [k.strip().lower() for k in kw_raw if isinstance(k, str) and k.strip()] if isinstance(kw_raw, list) else []
            if not parsed:
                return None
            return {"intent": intent, "temporal": temporal, "queries": parsed, "keywords": keywords}

        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            result = json.loads(cleaned)
            if isinstance(result, dict) and "queries" in result:
                return _extract(result)
            if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
                return _extract(result[0])
            if isinstance(result, list) and all(isinstance(s, str) for s in result):
                parsed = [s.strip() for s in result[:6] if s.strip()]
                return {"intent": None, "temporal": None, "queries": parsed, "keywords": []} if parsed else None

            obj_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if obj_match:
                result = json.loads(obj_match.group())
                if isinstance(result, dict) and "queries" in result:
                    return _extract(result)
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"[INTENT CLASSIFY] JSON parse failed: {e}, response: {response[:200]}")

        return None

    async def _build_hybrid_scene_context(
        self,
        story_id: int,
        scenes: List[Scene],
        available_tokens: int,
        db: Session,
        chapter_id: Optional[int] = None,
        limit_semantic_to_chapter: bool = False,
        branch_id: Optional[int] = None,
        user_intent: Optional[str] = None,
        excluded_scene_sequence: Optional[int] = None,
        use_entity_states_snapshot: bool = False,
        exclude_scene_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Build scene context using hybrid retrieval strategy.

        Token allocation:
        - Recent scenes: 40% of available tokens
        - Semantically relevant scenes: 35% of available tokens
        - Character moments: 15% of available tokens
        - Chapter summaries: 10% of available tokens
        """
        # DEBUG: Log user_intent at entry point with explicit None vs empty check
        if user_intent is None:
            logger.warning(f"[HYBRID CONTEXT] _build_hybrid_scene_context received user_intent: None (Python None)")
        elif not user_intent.strip():
            logger.warning(f"[HYBRID CONTEXT] _build_hybrid_scene_context received user_intent: EMPTY STRING")
        else:
            logger.info(f"[HYBRID CONTEXT] _build_hybrid_scene_context received user_intent: '{user_intent[:80]}'")

        total_scenes = len(scenes)

        # Get recent scenes using BATCH-ALIGNED selection for cache stability
        # Instead of rolling window (last N scenes), select:
        # 1. Complete batches (stable, maximizes cache hits)
        # 2. Active batch (all scenes in the current incomplete batch)
        recent_scenes = self._get_batch_aligned_recent_scenes(scenes)
        logger.info(f"[HYBRID CONTEXT] Batch-aligned selection: {len(recent_scenes)} scenes "
                   f"(batch_size={self.scene_batch_size}, requested={self.keep_recent_scenes})")

        recent_content = await self._get_scene_content(recent_scenes, db, branch_id=branch_id)
        recent_tokens = self.count_tokens(recent_content)

        # Allocate remaining tokens
        remaining_tokens = available_tokens - recent_tokens
        if remaining_tokens < 500:
            # Not enough space for semantic retrieval
            logger.info(f"Limited tokens, using only recent scenes for story {story_id}")
            return {
                "previous_scenes": recent_content,
                "recent_scenes": recent_content,
                "scene_summary": f"Recent context only ({len(recent_scenes)} scenes)",
                "total_scenes": total_scenes,
                "included_scenes": len(recent_scenes),
                "context_type": "recent_only"
            }

        # Dynamic allocation: prioritize semantic, character, entity, summary first
        # Then fill remaining budget with recent scenes (if fill_remaining_context is enabled)

        # Collect scene sequence numbers that will be in Recent Scenes (for exclusion from semantic search)
        all_recent_scene_sequences = [s.sequence_number for s in recent_scenes]

        # Only estimate additional scenes for exclusion if fill_remaining_context is enabled
        # When disabled, we only exclude the keep_recent_scenes, allowing semantic search to find
        # older scenes that might be relevant
        if self.fill_remaining_context:
            # Estimate remaining tokens after semantic/character/entity/summary (use average allocation ~50%)
            estimated_other_tokens = int(remaining_tokens * 0.5)
            estimated_remaining_for_recent = remaining_tokens - estimated_other_tokens

            # Get preliminary list of additional scenes that will be included (for exclusion purposes only)
            # Note: We'll recalculate this later with actual token usage, but this gives us a good estimate
            _, estimated_additional_scenes = await self._add_recent_scenes_dynamically(
                scenes, len(recent_scenes), estimated_remaining_for_recent, db
            )
            all_recent_scene_sequences.extend([s.sequence_number for s in estimated_additional_scenes])
            logger.info(f"[HYBRID CONTEXT] Excluding {len(all_recent_scene_sequences)} scenes from semantic search (recent: {len(recent_scenes)}, additional: {len(estimated_additional_scenes)})")
        else:
            logger.info(f"[HYBRID CONTEXT] Fill remaining context disabled - excluding only {len(recent_scenes)} recent scenes from semantic search")

        # Remove duplicates and sort for clarity
        all_recent_scene_sequences = sorted(set(all_recent_scene_sequences))

        semantic_tokens = int(remaining_tokens * 0.50)
        character_tokens = int(remaining_tokens * 0.15)
        entity_tokens = int(remaining_tokens * 0.05)
        summary_tokens = int(remaining_tokens * 0.05)

        logger.info(f"[HYBRID CONTEXT] Token budget - remaining: {remaining_tokens}, semantic: {semantic_tokens}, character: {character_tokens}")

        # Load context snapshot early — needed for semantic_scenes_text override below
        entity_states_content = None
        context_snapshot = None
        if use_entity_states_snapshot and exclude_scene_id:
            context_snapshot = await self._load_entity_states_snapshot(db, exclude_scene_id)

        # --- Intent classification: skip semantic search for direct intents ---
        intent_result = None
        skip_semantic = False
        if user_intent and user_intent.strip() and self.enable_semantic:
            intent_result = await self._classify_intent(user_intent)
            if intent_result:
                intent_type = intent_result.get("intent")
                logger.info(f"[INTENT CLASSIFY] Result: {intent_type or 'direct (default)'}, "
                           f"queries={intent_result.get('queries', [])}"
                           + (f", keywords={intent_result.get('keywords')}" if intent_result.get('keywords') else ""))
                if intent_type == "direct" or (not intent_type and not intent_result.get("queries")):
                    skip_semantic = True
                    logger.info(f"[INTENT CLASSIFY] Direct intent — skipping semantic search")

        # Get semantically relevant scenes (skip for direct intents)
        semantic_content, single_query_results = "", []
        if not skip_semantic:
            semantic_content, single_query_results = await self._get_semantic_scenes(
                story_id, recent_scenes, semantic_tokens, db,
                exclude_all_recent_sequences=all_recent_scene_sequences,
                limit_to_chapter_id=chapter_id if limit_semantic_to_chapter else None,
                branch_id=branch_id,
                user_intent=user_intent
            )
        semantic_used_tokens = self.count_tokens(semantic_content) if semantic_content else 0

        # Store search state for potential multi-query improvement in service.py
        current_chapter_id = recent_scenes[-1].chapter_id if recent_scenes else None
        # Dominant chapter = most frequent chapter among recent scenes (not just the last scene's chapter)
        chapter_counts = Counter(s.chapter_id for s in recent_scenes if s.chapter_id)
        dominant_chapter_id = chapter_counts.most_common(1)[0][0] if chapter_counts else current_chapter_id
        # Resolve world scope for cross-story recall
        world_scope = self._resolve_world_search_scope(story_id, branch_id, db)
        exclude_scene_ids = set(s.id for s in recent_scenes)

        context_state = {
            "user_intent": user_intent,
            "story_id": story_id,
            "exclude_sequences": all_recent_scene_sequences,
            "branch_id": branch_id,
            "chapter_id": current_chapter_id,
            "dominant_chapter_id": dominant_chapter_id,
            "token_budget": semantic_tokens,
            "single_query_results": single_query_results,
            "intent_result": intent_result,  # cached for service.py to reuse
            "world_scope": world_scope,  # None for single-story worlds
            "exclude_scene_ids": exclude_scene_ids,  # For world-scope exclusion by scene ID
        }

        # Get character-specific context
        character_content = await self._get_character_context(
            story_id, recent_scenes, character_tokens, db
        )
        character_used_tokens = self.count_tokens(character_content) if character_content else 0

        entity_used_tokens = 0

        # Get character interaction history (stable, updates only on entity extraction)
        interaction_history_content = await self._get_interaction_history(
            story_id, db, branch_id=branch_id
        )
        interaction_used_tokens = self.count_tokens(interaction_history_content) if interaction_history_content else 0
        logger.info(f"[HYBRID CONTEXT] Interaction history: {interaction_used_tokens} tokens, included={interaction_history_content is not None}")

        # Get chapter summaries (only current chapter summary - story_so_far and previous_chapter_summary
        # are handled as direct fields in base_context to avoid duplication)
        summary_content = await self._get_chapter_summaries(
            story_id, summary_tokens, db, chapter_id=chapter_id
        )
        summary_used_tokens = self.count_tokens(summary_content) if summary_content else 0

        # Calculate remaining tokens after semantic/character/entity/summary
        used_tokens_so_far = semantic_used_tokens + character_used_tokens + entity_used_tokens + summary_used_tokens
        remaining_for_recent = remaining_tokens - used_tokens_so_far

        # Only fill remaining context with additional scenes if enabled (default: True)
        # When disabled, only keep_recent_scenes are included - better for weaker LLMs
        # that benefit from focused context with less dilution of state information
        additional_recent_content = None
        additional_recent_scenes = []
        if self.fill_remaining_context:
            # Fill ALL remaining tokens with additional recent scenes (going backwards)
            # This ensures we use the full token budget
            additional_recent_content, additional_recent_scenes = await self._add_recent_scenes_dynamically(
                scenes, len(recent_scenes), remaining_for_recent, db
            )
            logger.info(f"[HYBRID CONTEXT] Fill remaining context enabled: added {len(additional_recent_scenes)} additional scenes")
        else:
            logger.info(f"[HYBRID CONTEXT] Fill remaining context disabled: using only {len(recent_scenes)} recent scenes")

        # Combine initial recent scenes with additional scenes for the Recent Scenes section
        # Exclude duplicates (additional_recent_scenes already excludes scenes in recent_scenes)
        # Order: older scenes (additional) come first, then recent scenes (chronological order)
        if additional_recent_content:
            # Combine additional_recent_content (older) + recent_content (newer)
            # Both are now in chronological order, so combine oldest → newest
            if recent_content:
                combined_recent_content = f"{additional_recent_content}\n\n{recent_content}"
            else:
                combined_recent_content = additional_recent_content
        else:
            combined_recent_content = recent_content

        # Log what we got from _get_chapter_summaries
        if summary_content:
            logger.info(f"[HYBRID CONTEXT] _get_chapter_summaries returned content ({len(summary_content)} chars): {summary_content[:200]}...")
        else:
            logger.info("[HYBRID CONTEXT] _get_chapter_summaries returned None")

        # Assemble final context
        context_parts = []

        if summary_content:
            # Defensive check: Remove any "Story So Far:" or "Previous Chapter Summary" that might
            # have accidentally been included (they should be in base_context as direct fields)
            filtered_content = summary_content
            import re

            # Remove "Story So Far:" section (header + all content until next section or end)
            if "Story So Far:" in filtered_content:
                logger.error("[HYBRID CONTEXT] ERROR: Found 'Story So Far:' in summary_content! Filtering it out.")
                # Match "Story So Far:" and everything until "Previous Chapter Summary" or "Current Chapter Summary" or end
                pattern = r'Story So Far:.*?(?=(?:Previous Chapter Summary|Current Chapter Summary|$))'
                filtered_content = re.sub(pattern, '', filtered_content, flags=re.DOTALL)
                filtered_content = filtered_content.strip()

            # Remove "Previous Chapter Summary" section (header + all content until next section or end)
            if "Previous Chapter Summary" in filtered_content:
                logger.error("[HYBRID CONTEXT] ERROR: Found 'Previous Chapter Summary' in summary_content! Filtering it out.")
                # Match "Previous Chapter Summary" and everything until "Current Chapter Summary" or end
                pattern = r'Previous Chapter Summary.*?(?=(?:Current Chapter Summary|$))'
                filtered_content = re.sub(pattern, '', filtered_content, flags=re.DOTALL)
                filtered_content = filtered_content.strip()

            if filtered_content.strip():
                context_parts.append(f"Story Summary:\n{filtered_content}")
            else:
                logger.info("[HYBRID CONTEXT] summary_content was filtered to empty, not adding to context")

        # Add interaction history BEFORE Relevant Context for cache optimization
        # (Interaction history is stable - only updates on entity extraction)
        if interaction_history_content:
            context_parts.append(f"\n{interaction_history_content}")

        # Build "Relevant Context" section (character context only now)
        # Semantic scenes are passed separately via "semantic_scenes_text" for dedicated message positioning
        # Entity states are passed separately via "entity_states_text" key for independent message positioning
        relevant_context_parts = []

        # NOTE: semantic_content is NO LONGER included here - it's passed as separate key
        # to be positioned as dedicated message right before task instruction

        if character_content:
            relevant_context_parts.append(f"Character Context:\n{character_content}")

        # entity_states_content is NOT included here — passed as separate return key
        # so _format_context_as_messages() can position it independently

        if relevant_context_parts:
            context_parts.append(f"\nRelevant Context:\n" + "\n\n".join(relevant_context_parts))

        context_parts.append(f"\nRecent Scenes:\n{combined_recent_content}")

        full_context = "\n".join(context_parts)

        return {
            "previous_scenes": full_context,
            "entity_states_text": entity_states_content,  # Passed separately for independent message positioning
            "semantic_scenes_text": semantic_content,  # Passed separately - positioned as LAST message before task
            "recent_scenes": combined_recent_content,  # Include both initial and additional recent scenes
            "scene_summary": "",  # Don't include metadata in prompt - it's debug info only
            "total_scenes": total_scenes,
            "included_scenes": len(recent_scenes) + len(additional_recent_scenes),  # Actual scenes in context
            "context_type": "hybrid",
            "semantic_scenes_included": semantic_content is not None,
            "character_context_included": character_content is not None,
            "entity_states_included": entity_states_content is not None,
            "interaction_history_included": interaction_history_content is not None,
            "_context_snapshot": context_snapshot,  # Return snapshot for story_focus/relationship_context override
            "_semantic_search_state": context_state,  # For multi-query decomposition in service.py
            "_context_manager_ref": self,  # For service.py to call search_and_format_multi_query()
        }

    async def _get_base_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, branch_id: Optional[int] = None) -> Dict[str, Any]:
        """Get base story context (genre, tone, characters) with chapter-specific character separation.

        Used by hybrid context strategy. Enhanced version with NPC tracking and voice styles.
        """
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return {}

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)

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
            from ..models.chapter import chapter_characters
            chapter_char_ids = db.execute(
                chapter_characters.select().where(
                    chapter_characters.c.chapter_id == chapter_id
                )
            ).fetchall()
            chapter_story_char_ids = {row.story_character_id for row in chapter_char_ids}

            # Get chapter info for context
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        else:
            chapter_story_char_ids = set()
            chapter = None

        for sc in story_characters:
            character = db.query(Character).filter(Character.id == sc.character_id).first()
            if not character:
                continue

            # Determine effective voice style (story-specific override or character default)
            effective_voice_style = sc.voice_style_override if sc.voice_style_override else character.voice_style

            # Use snapshot as background if available, else fall back to static background
            background = self._get_snapshot_background(
                db, character.id, story.world_id,
                getattr(story, 'timeline_order', None),
                branch_id=branch_id,
            ) or character.background or ""

            char_data = {
                "name": character.name,
                "gender": character.gender or "",
                "role": sc.role or "",
                "description": character.description or "",
                "personality": ", ".join(character.personality_traits) if character.personality_traits else "",
                "background": background,
                "goals": character.goals or "",
                "fears": character.fears or "",
                "appearance": character.appearance or "",
                "relationships": "",
                "voice_style": effective_voice_style  # Character's speaking style
            }

            if chapter_id and sc.id in chapter_story_char_ids:
                # Active character - full details
                active_characters.append(char_data)
            elif chapter_id:
                # Inactive character - brief format
                inactive_characters.append({
                    "name": character.name,
                    "gender": character.gender or "",
                    "role": sc.role or ""
                })
            else:
                # No chapter specified - treat all as active
                active_characters.append(char_data)

        # Add important NPCs with tiered recency-based inclusion
        try:
            from .npc_tracking_service import NPCTrackingService
            npc_service = NPCTrackingService(user_id=self.user_id, user_settings=self.user_settings)

            # Get current scene sequence for recency calculation
            # Query the latest scene for this story
            latest_scene = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            ).order_by(desc(Scene.sequence_number)).first()
            current_scene_sequence = latest_scene.sequence_number if latest_scene else 0

            # Collect explicit character names for cross-story dedup
            explicit_names = {c["name"].lower() for c in active_characters + inactive_characters}

            # Get tiered NPCs (active with full details, inactive with brief mention)
            tiered_npcs = npc_service.get_tiered_npcs_for_context(
                db=db,
                story_id=story_id,
                current_scene_sequence=current_scene_sequence,
                chapter_id=chapter_id,
                branch_id=branch_id,
                world_id=story.world_id,
                explicit_character_names=explicit_names
            )

            active_npc_characters = tiered_npcs.get("active_npcs", [])
            inactive_npc_characters = tiered_npcs.get("inactive_npcs", [])

            # Add active NPCs to active characters
            active_characters.extend(active_npc_characters)

            # Add inactive NPCs to inactive characters
            inactive_characters.extend(inactive_npc_characters)

            logger.info(f"[HYBRID CONTEXT BUILD] Added {len(active_npc_characters)} active NPCs and {len(inactive_npc_characters)} inactive NPCs to context")
            if active_npc_characters:
                logger.info(f"[HYBRID CONTEXT BUILD] Active NPCs: {[npc.get('name', 'Unknown') for npc in active_npc_characters]}")
            if inactive_npc_characters:
                logger.info(f"[HYBRID CONTEXT BUILD] Inactive NPCs: {[npc.get('name', 'Unknown') for npc in inactive_npc_characters]}")
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

            # Add chapter plot guidance if available (from brainstorming)
            if hasattr(chapter, 'chapter_plot') and chapter.chapter_plot:
                base_context["chapter_plot"] = chapter.chapter_plot
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Including chapter_plot guidance")

            # Add plot progress (completed events) if available
            if hasattr(chapter, 'plot_progress') and chapter.plot_progress:
                base_context["plot_progress"] = chapter.plot_progress
                completed_count = len(chapter.plot_progress.get("completed_events", []))
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Including plot_progress ({completed_count} completed events)")

            # Add arc phase details if available
            if hasattr(chapter, 'arc_phase_id') and chapter.arc_phase_id:
                # Get the arc phase from the story
                if story.story_arc:
                    arc_phase = story.get_arc_phase(chapter.arc_phase_id)
                    if arc_phase:
                        base_context["arc_phase"] = arc_phase
                        logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Including arc phase '{arc_phase.get('name', 'Unknown')}'")

            # Check if chapter continues from previous (controls summary inclusion)
            continues_from_previous = getattr(chapter, 'continues_from_previous', True)

            # Include story_so_far if it exists AND chapter continues from previous
            if chapter.story_so_far and continues_from_previous:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Including story_so_far ({len(chapter.story_so_far)} chars)")
                base_context["story_so_far"] = chapter.story_so_far
            elif chapter.story_so_far and not continues_from_previous:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Excluding story_so_far (continues_from_previous=False)")
            else:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: story_so_far is None")

            # Include previous chapter's summary if available AND chapter continues from previous
            if chapter.chapter_number > 1 and continues_from_previous:
                from ..models import Chapter as ChapterModel
                previous_chapter = db.query(ChapterModel).filter(
                    ChapterModel.story_id == story_id,
                    ChapterModel.chapter_number == chapter.chapter_number - 1,
                    ChapterModel.auto_summary.isnot(None)
                ).first()
                if previous_chapter and previous_chapter.auto_summary:
                    logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Found previous chapter {previous_chapter.chapter_number} summary ({len(previous_chapter.auto_summary)} chars)")
                    base_context["previous_chapter_summary"] = previous_chapter.auto_summary
                else:
                    logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: No previous chapter summary found (previous_chapter={previous_chapter is not None}, has_auto_summary={previous_chapter.auto_summary if previous_chapter else 'N/A'})")
            elif chapter.chapter_number > 1 and not continues_from_previous:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Excluding previous_chapter_summary (continues_from_previous=False)")
            else:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: First chapter, no previous chapter summary")

            # Include current chapter's auto_summary for context on this chapter's progress
            if chapter.auto_summary:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: Including current_chapter_summary ({len(chapter.auto_summary)} chars)")
                base_context["current_chapter_summary"] = chapter.auto_summary
            else:
                logger.info(f"[HYBRID CONTEXT BUILD] Chapter {chapter.chapter_number}: current_chapter_summary is None")

        return base_context

    async def _get_scene_content(self, scenes: List[Scene], db: Session, branch_id: Optional[int] = None) -> str:
        """Get content for scenes using active variants.

        Scenes are expected to be in chronological order (oldest → newest).
        The scenes list from database query is already chronological, and slicing (scenes[-N:])
        maintains that order, so we use scenes as-is.
        """
        content_parts = []

        # Scenes are already in chronological order (oldest → newest)
        # No need to reverse - this ensures narrative flow and maximizes recency bias (most recent scenes at end)
        for scene in scenes:
            # Get active variant from StoryFlow
            flow_query = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            )
            if branch_id:
                flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
            flow = flow_query.first()

            if flow and flow.scene_variant:
                content_parts.append(
                    f"Scene {scene.sequence_number}: {flow.scene_variant.content}"
                )
            else:
                # Fallback to scene content if no flow entry
                if scene.content:
                    content_parts.append(
                        f"Scene {scene.sequence_number}: {scene.content}"
                    )

        return "\n\n".join(content_parts)

    async def _get_semantic_scenes(
        self,
        story_id: int,
        recent_scenes: List[Scene],
        token_budget: int,
        db: Session,
        exclude_all_recent_sequences: Optional[List[int]] = None,
        limit_to_chapter_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        user_intent: Optional[str] = None
    ) -> Tuple[Optional[str], List[Dict]]:
        """
        Get semantically relevant scenes from the past.

        Args:
            story_id: Story ID
            recent_scenes: Recent scenes to use as query
            token_budget: Available tokens
            db: Database session
            exclude_all_recent_sequences: Scene sequences to exclude
            limit_to_chapter_id: Optional chapter ID to limit search
            branch_id: Optional branch ID to filter results (only return scenes from this branch)
            user_intent: User's continue option - prioritized in semantic search query

        Returns:
            Tuple of (formatted scenes text or None, list of scored result dicts)
        """
        if not recent_scenes:
            return None, []

        if not self.semantic_memory:
            return None, []

        try:
            # Build query from: user intent (highest priority) + recent scene content
            query_parts = []

            # DEBUG: Log user_intent value
            logger.info(f"[SEMANTIC SEARCH] user_intent received: '{user_intent[:100] if user_intent else 'None'}...'")

            # Add user intent FIRST (highest priority) - this is what the user wants to happen next
            if user_intent and user_intent.strip():
                query_parts.append(user_intent.strip())
                logger.info(f"[SEMANTIC SEARCH] Including user intent in query: '{user_intent[:100]}...'")

            # Add last 2-3 scenes for context
            query_scenes = recent_scenes[-3:] if len(recent_scenes) >= 3 else recent_scenes
            for i, scene in enumerate(query_scenes):
                # Get active variant content
                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()

                scene_content = flow.scene_variant.content if flow and flow.scene_variant else scene.content
                if scene_content:
                    # Truncate to 200 chars — full scenes (~1500 chars each) drown out
                    # user_intent (~200 chars), making the bi-encoder embed generic scene
                    # content instead of the specific recall cues in user_intent.
                    query_parts.append(scene_content[:200])

            if not query_parts:
                return None, []

            # Combine: user intent first, then recent scenes (most recent first)
            # User intent is already first, now add scenes in reverse order
            if user_intent and user_intent.strip():
                # Skip first element (user intent), reverse the rest (scenes)
                scene_parts = query_parts[1:]
                query_content = query_parts[0] + "\n\n" + "\n\n".join(reversed(scene_parts)) if scene_parts else query_parts[0]
            else:
                query_content = "\n\n".join(reversed(query_parts))

            # Get exclude list (all scenes that will be in Recent Scenes section)
            # Use provided complete exclusion list if available, otherwise fall back to just recent_scenes
            if exclude_all_recent_sequences:
                exclude_sequences = exclude_all_recent_sequences
                logger.debug(f"[SEMANTIC SEARCH] Using complete exclusion list: {len(exclude_sequences)} scenes")
            else:
                # Fallback: only exclude initial recent scenes (for backward compatibility)
                exclude_sequences = [s.sequence_number for s in recent_scenes]
                logger.debug(f"[SEMANTIC SEARCH] Using fallback exclusion list: {len(exclude_sequences)} scenes")

            # Search for similar scenes
            # If limit_to_chapter_id is provided, only search within that chapter (for context size calculation)
            # Otherwise, search across entire story (normal behavior)
            # Request more results than needed so we can filter by similarity threshold and branch
            # Use 10x to ensure we get enough candidates after branch filtering (legacy data has no branch_id)
            search_top_k = self.semantic_top_k * 10  # Get 10x results to filter by branch

            similar_scenes = await self.semantic_memory.search_similar_scenes(
                query_text=query_content,
                story_id=story_id,
                top_k=search_top_k,
                exclude_sequences=exclude_sequences,
                chapter_id=limit_to_chapter_id,  # Limit to chapter if specified, otherwise None (entire story)
                use_reranking=False  # Single-query path uses keyword boosting; cross-encoder only in multi-query path
            )

            if not similar_scenes:
                logger.info(f"[SEMANTIC SEARCH] No similar scenes found for story {story_id}")
                return None, []

            # === KEYWORD BOOSTING ===
            # Dynamically extract keywords from user_intent to boost scenes with matching terms
            # No hardcoded story-specific patterns - extract from the actual prompt
            keyword_boost = 0.20  # Base boost for scenes containing extracted keywords
            extracted_keywords = []  # List of (search_terms, display_name, boost_amount) tuples

            if user_intent:
                import re
                user_intent_lower = user_intent.lower()

                # 1. Extract multi-word phrases (2-3 word combinations that appear meaningful)
                # Look for adjective+noun or noun+noun patterns
                # Extract all 2-3 word sequences and filter for meaningful ones
                words = re.findall(r'\b[a-z]+\b', user_intent_lower)
                stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                             'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
                             'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                             'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
                             'her', 'his', 'she', 'he', 'it', 'its', 'they', 'them', 'their',
                             'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
                             'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
                             'few', 'more', 'most', 'other', 'some', 'such', 'no', 'not', 'only',
                             'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now',
                             'then', 'here', 'there', 'about', 'into', 'over', 'after', 'before'}

                # Extract significant words (non-stop words, 3+ chars)
                significant_words = [w for w in words if w not in stop_words and len(w) >= 3]

                # Add individual significant words as keywords
                for word in significant_words:
                    extracted_keywords.append(([word], word, keyword_boost))

                # Extract 2-word phrases from significant words
                for i in range(len(words) - 1):
                    if words[i] not in stop_words and words[i+1] not in stop_words:
                        phrase = f"{words[i]} {words[i+1]}"
                        if len(phrase) >= 5:  # Minimum phrase length
                            extracted_keywords.append(([phrase, words[i], words[i+1]], phrase, keyword_boost * 1.5))

                # NOTE: Character name boosting removed — common character names appear
                # in ~95% of scenes, providing zero discriminative signal and causing
                # keyword boost saturation (every scene hits the cap).

                if extracted_keywords:
                    # Deduplicate and show unique keywords
                    unique_keywords = list(set(name for _, name, _ in extracted_keywords))[:15]
                    logger.info(f"[SEMANTIC SEARCH] Extracted keywords for boosting: {unique_keywords}")

            # Apply keyword boosting with IDF weighting to similar_scenes
            if extracted_keywords:
                # Batch-load scene content for top 50 candidates (not per-scene queries)
                candidate_ids = [r['scene_id'] for r in similar_scenes[:50]]
                candidate_flows = db.query(StoryFlow).filter(
                    StoryFlow.scene_id.in_(candidate_ids),
                    StoryFlow.is_active == True
                ).all()
                flow_by_scene = {f.scene_id: f for f in candidate_flows}

                # Build content map for top 50
                content_by_scene_id = {}
                for sid in candidate_ids:
                    flow = flow_by_scene.get(sid)
                    content = (flow.scene_variant.content if flow and flow.scene_variant else "").lower()
                    if content:
                        content_by_scene_id[sid] = content

                # Compute IDF weight per keyword: base_boost / max(1, doc_freq)
                # Keywords appearing in many scenes get negligible boost
                num_docs = len(content_by_scene_id)
                keyword_idf = {}  # display_name -> idf-adjusted boost
                for search_terms, display_name, base_boost in extracted_keywords:
                    doc_freq = 0
                    for content_lower in content_by_scene_id.values():
                        for term in search_terms:
                            if term in content_lower:
                                doc_freq += 1
                                break
                    idf_boost = base_boost / max(1, doc_freq)
                    keyword_idf[display_name] = idf_boost
                    if doc_freq > 0:
                        logger.debug(f"[SEMANTIC SEARCH] IDF: '{display_name}' in {doc_freq}/{num_docs} scenes, boost: {base_boost:.2f} -> {idf_boost:.4f}")

                # Apply IDF-weighted boosts
                for result in similar_scenes[:50]:
                    scene_id = result.get('scene_id')
                    content_lower = content_by_scene_id.get(scene_id)
                    if not content_lower:
                        continue

                    matches = []
                    total_boost = 0.0
                    for search_terms, display_name, _base in extracted_keywords:
                        for term in search_terms:
                            if term in content_lower:
                                matches.append(display_name)
                                total_boost += keyword_idf.get(display_name, 0.0)
                                break  # Only count each keyword category once

                    if matches:
                        original_score = result.get('similarity_score', 0.0)
                        # IDF naturally prevents saturation; cap at 0.80 as safety net
                        capped_boost = min(total_boost, 0.80)
                        result['similarity_score'] = original_score + capped_boost
                        result['keyword_matches'] = matches
                        result['keyword_boost'] = capped_boost
                        logger.debug(f"[SEMANTIC SEARCH] Boosted scene {result.get('sequence', '?')}: {original_score:.3f} -> {result['similarity_score']:.3f} (boost: {capped_boost:.4f}, matches: {matches})")

                # Re-sort by boosted similarity score
                similar_scenes.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)

                # Log top candidates after boosting
                boosted_scenes = [(r.get('similarity_score', 0), r.get('sequence', 0), r.get('keyword_matches', [])) for r in similar_scenes[:10]]
                logger.info(f"[SEMANTIC SEARCH] After keyword boost, top 10: {boosted_scenes}")

            # === CHAPTER AFFINITY BOOST ===
            # Scenes from the same chapter as recent scenes get a boost.
            # This helps when users reference "events from today" or want recap of chapter events,
            # ensuring same-chapter scenes outrank thematically-similar scenes from other chapters.
            chapter_affinity_boost = 0.15
            current_chapter_id = recent_scenes[-1].chapter_id if recent_scenes else None

            if current_chapter_id is not None:
                chapter_boosted_count = 0
                for result in similar_scenes:
                    result_chapter_id = result.get('chapter_id')
                    if result_chapter_id is not None and result_chapter_id == current_chapter_id:
                        original_score = result.get('similarity_score', 0.0)
                        result['similarity_score'] = original_score + chapter_affinity_boost
                        result['chapter_boost'] = chapter_affinity_boost
                        chapter_boosted_count += 1
                        logger.debug(
                            f"[SEMANTIC SEARCH] Chapter boost scene seq {result.get('sequence', '?')}: "
                            f"{original_score:.3f} -> {result['similarity_score']:.3f}"
                        )

                if chapter_boosted_count > 0:
                    similar_scenes.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
                    logger.info(
                        f"[SEMANTIC SEARCH] Chapter affinity boost: {chapter_boosted_count} scenes "
                        f"from chapter {current_chapter_id} boosted by +{chapter_affinity_boost}"
                    )

            # Filter by minimum similarity threshold and age
            current_scene_sequence = recent_scenes[-1].sequence_number if recent_scenes else None
            filtered_results = []

            # Log how many scenes we're starting with
            logger.info(f"[SEMANTIC SEARCH] Processing {len(similar_scenes)} candidates for story {story_id}, branch_id filter: {branch_id}")

            filtered_by_similarity = 0
            filtered_by_branch = 0
            filtered_by_age = 0
            filtered_by_missing = 0

            for result in similar_scenes:
                similarity_score = result.get('similarity_score', 0.0)

                # Filter out low similarity results
                if similarity_score < self.semantic_min_similarity:
                    logger.debug(f"[SEMANTIC SEARCH] Filtered out scene {result.get('scene_id')} - similarity {similarity_score:.2f} < threshold {self.semantic_min_similarity}")
                    filtered_by_similarity += 1
                    continue

                # Get scene sequence for age filtering
                scene = db.query(Scene).filter(Scene.id == result['scene_id']).first()
                if not scene:
                    filtered_by_missing += 1
                    continue

                # Filter by branch_id if specified (prevents cross-branch contamination)
                if branch_id is not None and scene.branch_id != branch_id:
                    logger.debug(f"[SEMANTIC SEARCH] Filtered out scene {scene.sequence_number} - wrong branch (scene branch: {scene.branch_id}, current branch: {branch_id})")
                    filtered_by_branch += 1
                    continue

                # Optional: Filter out very old scenes unless similarity is very high
                if current_scene_sequence is not None:
                    scene_age = current_scene_sequence - scene.sequence_number
                    # If scene is >50 scenes old, require higher similarity (>0.6)
                    if scene_age > 50 and similarity_score < 0.6:
                        logger.debug(f"[SEMANTIC SEARCH] Filtered out old scene {scene.sequence_number} (age {scene_age}) - similarity {similarity_score:.2f} < 0.6")
                        filtered_by_age += 1
                        continue

                filtered_results.append(result)

            # Log filter statistics
            logger.info(f"[SEMANTIC SEARCH] Filter stats for story {story_id}: similarity={filtered_by_similarity}, branch={filtered_by_branch}, age={filtered_by_age}, missing={filtered_by_missing}, passed={len(filtered_results)}")

            if not filtered_results:
                logger.info(f"[SEMANTIC SEARCH] No scenes passed filters for story {story_id} (branch_id={branch_id})")
                return None, []

            # Sort filtered results by sequence_number (chronological order) before processing
            # This ensures "Relevant Past Events" appear in narrative order
            # Use semantic_scenes_in_context to limit how many semantic scenes are included
            filtered_results_with_scenes = []
            for result in filtered_results[:self.semantic_scenes_in_context]:  # Limit to semantic_scenes_in_context
                scene = db.query(Scene).filter(Scene.id == result['scene_id']).first()
                if scene:
                    filtered_results_with_scenes.append((result, scene))

            # Sort by sequence_number ascending (oldest → newest)
            filtered_results_with_scenes.sort(key=lambda x: x[1].sequence_number)

            # Log which scenes were selected with similarity scores
            if filtered_results_with_scenes:
                selected_info = [(r['similarity_score'], s.sequence_number) for r, s in filtered_results_with_scenes]
                logger.info(f"[SEMANTIC SEARCH] Top {len(selected_info)} candidates (score, seq#): {selected_info}")

            # Get scene content within token budget (now using chronologically sorted results)
            # No per-scene truncation — include full scene content; token budget controls total inclusion
            relevant_parts = []
            used_tokens = 0

            for result, scene in filtered_results_with_scenes:
                variant = db.query(SceneVariant).filter(SceneVariant.id == result['variant_id']).first()
                if not variant:
                    continue

                keyword_matches = result.get('keyword_matches', [])

                # Include keyword match info to help LLM understand relevance
                match_info = f" [matched: {', '.join(keyword_matches)}]" if keyword_matches else ""
                scene_text = f"[Relevant from Scene {scene.sequence_number}{match_info}]:\n{variant.content}"
                scene_tokens = self.count_tokens(scene_text)

                if used_tokens + scene_tokens <= token_budget:
                    relevant_parts.append(scene_text)
                    used_tokens += scene_tokens
                else:
                    break

            if relevant_parts:
                logger.info(f"[SEMANTIC SEARCH] Selected {len(relevant_parts)}/{self.semantic_scenes_in_context} semantic scenes (similarity >= {self.semantic_min_similarity}) for story {story_id}, total chars: {sum(len(p) for p in relevant_parts)}")
                # Log first 200 chars of each semantic scene for debugging
                for i, part in enumerate(relevant_parts):
                    logger.info(f"[SEMANTIC SEARCH] Scene {i+1} preview: {part[:200]}...")
                # Only pass the top selected results (not all 200 candidates) to multi-query merge.
                # Passing all candidates causes the merge to upgrade ~130 multi-query scores with
                # keyword-boosted single-query scores, effectively bypassing content verification.
                selected_results = [r for r, _s in filtered_results_with_scenes]
                return "\n\n".join(relevant_parts), selected_results

            logger.info(f"[SEMANTIC SEARCH] No scenes fit within token budget after filtering")
            return None, []

        except Exception as e:
            logger.error(f"Failed to get semantic scenes: {e}")
            return None, []

    @staticmethod
    def _reciprocal_rank_fusion(
        batch_results: "List[List[Dict[str, Any]]]",
        k: int = 60
    ) -> "List[Dict[str, Any]]":
        """
        Merge multiple ranked result lists using Reciprocal Rank Fusion.

        Args:
            batch_results: List of result lists (one per query) from batch search
            k: RRF constant (default 60, standard value)

        Returns:
            Merged + deduplicated results with normalized RRF scores in similarity_score
        """
        rrf_scores: Dict[str, float] = {}  # embedding_id -> accumulated RRF score
        best_result: Dict[str, Dict] = {}  # embedding_id -> best result dict

        for result_list in batch_results:
            for rank, result in enumerate(result_list):
                eid = result.get('embedding_id', f"{result.get('scene_id')}_{result.get('variant_id')}")
                score = 1.0 / (k + rank + 1)  # rank is 0-indexed, so +1
                rrf_scores[eid] = rrf_scores.get(eid, 0.0) + score

                # Keep the result dict with highest original similarity
                if eid not in best_result or result.get('bi_encoder_score', 0) > best_result[eid].get('bi_encoder_score', 0):
                    best_result[eid] = result

        if not rrf_scores:
            return []

        # Normalize to [0, 1]
        max_score = max(rrf_scores.values())
        if max_score == 0:
            return []

        merged = []
        for eid, rrf_score in rrf_scores.items():
            result = dict(best_result[eid])
            result['similarity_score'] = rrf_score / max_score
            result['rrf_raw_score'] = rrf_score
            merged.append(result)

        # Sort descending by normalized RRF score
        merged.sort(key=lambda x: x['similarity_score'], reverse=True)
        return merged

    async def _lookup_interaction_scenes(
        self,
        sub_queries: "List[str]",
        story_id: int,
        branch_id: "Optional[int]",
        db: Session,
    ) -> "List[Dict[str, Any]]":
        """
        Check if decomposed sub-queries match any tracked interaction types.
        Returns exact scene numbers from CharacterInteraction records.

        Matching logic (keyword overlap, no LLM):
        - Extract significant words from each interaction type
        - Check overlap with combined sub-query text
        - Require >=50% keyword overlap AND at least one character name match

        Returns:
            List of {"scene_sequence": int, "interaction_type": str} dicts
        """
        try:
            from ..models import CharacterInteraction, Character

            interactions = db.query(CharacterInteraction).filter(
                CharacterInteraction.story_id == story_id
            )
            if branch_id is not None:
                interactions = interactions.filter(
                    (CharacterInteraction.branch_id == branch_id) |
                    (CharacterInteraction.branch_id.is_(None))
                )
            interactions = interactions.all()

            if not interactions:
                return []

            # Build combined sub-query text for matching
            combined_text = " ".join(sq.lower() for sq in sub_queries)

            # Words to strip from interaction types before matching
            type_stop_words = frozenset({
                'first', 'the', 'a', 'an', 'on', 'in', 'of', 'to', 'by', 'with',
                'and', 'or', 'is', 'was', 'their', 'her', 'his', 'its',
            })

            # Cache character names by ID
            char_cache = {}

            matches = []
            for interaction in interactions:
                # Extract significant words from interaction type
                type_words = [
                    w for w in interaction.interaction_type.lower().replace('_', ' ').split()
                    if w not in type_stop_words and len(w) >= 3
                ]
                if not type_words:
                    continue

                # Check keyword overlap
                matched_words = sum(1 for w in type_words if w in combined_text)
                overlap = matched_words / len(type_words)
                if overlap < 0.5:
                    continue

                # Check character name match
                for char_id in (interaction.character_a_id, interaction.character_b_id):
                    if char_id not in char_cache:
                        char = db.query(Character.name).filter(Character.id == char_id).first()
                        char_cache[char_id] = char.name.lower() if char else ""
                char_a_name = char_cache.get(interaction.character_a_id, "")
                char_b_name = char_cache.get(interaction.character_b_id, "")

                name_match = False
                for name in (char_a_name, char_b_name):
                    if name:
                        # Check any part of the name (first name, last name)
                        for part in name.split():
                            if len(part) >= 3 and part in combined_text:
                                name_match = True
                                break
                    if name_match:
                        break

                if not name_match:
                    continue

                matches.append({
                    "scene_sequence": interaction.first_occurrence_scene,
                    "interaction_type": interaction.interaction_type,
                })
                logger.info(f"[INTERACTION SHORTCUT] Matched '{interaction.interaction_type}' "
                           f"at scene {interaction.first_occurrence_scene} "
                           f"(overlap={overlap:.0%}, chars={char_a_name}/{char_b_name})")

            return matches

        except Exception as e:
            logger.warning(f"[INTERACTION SHORTCUT] Lookup failed: {e}")
            return []

    def _resolve_world_search_scope(
        self,
        story_id: int,
        branch_id: int,
        db: Session
    ) -> "Optional[Dict[str, Any]]":
        """
        Resolve world-scope search parameters for cross-story recall.

        Returns None if single-story world (no other stories to search).
        Otherwise returns a dict with story IDs, branch mappings, timeline offsets, etc.
        """
        try:
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story or not story.world_id:
                return None

            from ..models.world import World
            from sqlalchemy import func as sa_func

            # Find all stories in this world with timeline_order <= current story
            current_timeline = story.timeline_order or 0
            world_stories = (
                db.query(Story)
                .filter(
                    Story.world_id == story.world_id,
                    Story.id != story_id,
                    or_(
                        Story.timeline_order.is_(None),
                        Story.timeline_order <= current_timeline
                    )
                )
                .order_by(Story.timeline_order.asc().nullslast(), Story.id.asc())
                .all()
            )

            if not world_stories:
                return None  # Single-story world

            # Build story+branch pairs: current story uses active branch_id,
            # other stories use their current_branch_id
            story_branch_pairs = []
            branch_map = {}
            story_titles = {}
            timeline_ordered = []

            for ws in world_stories:
                ws_branch = ws.current_branch_id
                if ws_branch is None:
                    # Fallback: find any active branch
                    active = db.query(StoryBranch).filter(
                        StoryBranch.story_id == ws.id,
                        StoryBranch.is_active == True
                    ).first()
                    ws_branch = active.id if active else None
                story_branch_pairs.append((ws.id, ws_branch))
                branch_map[ws.id] = ws_branch
                story_titles[ws.id] = ws.title
                timeline_ordered.append(ws)

            # Add current story last (highest timeline position)
            story_branch_pairs.append((story_id, branch_id))
            branch_map[story_id] = branch_id
            story_titles[story_id] = story.title
            timeline_ordered.append(story)

            story_ids = [sid for sid, _ in story_branch_pairs]

            # Compute global offsets: cumulative scene count per story in timeline order
            global_offsets = {}
            cumulative = 0
            for ws in timeline_ordered:
                global_offsets[ws.id] = cumulative
                ws_bid = branch_map[ws.id]
                if ws_bid:
                    count = db.query(sa_func.count(Scene.id)).filter(
                        Scene.story_id == ws.id,
                        Scene.branch_id == ws_bid
                    ).scalar() or 0
                else:
                    count = db.query(sa_func.count(Scene.id)).filter(
                        Scene.story_id == ws.id
                    ).scalar() or 0
                cumulative += count

            logger.info(f"[WORLD SCOPE] world_id={story.world_id}, stories={story_ids}, "
                       f"offsets={global_offsets}, branch_map={branch_map}")

            return {
                "world_id": story.world_id,
                "story_branch_pairs": story_branch_pairs,
                "story_ids": story_ids,
                "branch_map": branch_map,
                "story_titles": story_titles,
                "global_offsets": global_offsets,
            }

        except Exception as e:
            logger.warning(f"[WORLD SCOPE] Failed to resolve: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    # Module-level cache for event embeddings: {story_id: (max_event_id, event_data, embeddings)}
    _event_embedding_cache: "Dict[int, tuple]" = {}

    def _keyword_score_events(
        self,
        sub_queries: "List[str]",
        all_events: list,
        llm_keywords: "Optional[List[str]]" = None,
    ) -> "Dict[int, Dict[str, Any]]":
        """
        Keyword-based scoring of events against sub-queries.
        Direct word/phrase matches — strongest signal when they exist.
        Character names are excluded from keyword matching (they appear in
        nearly every event and have zero discriminative power).
        When llm_keywords are provided (LLM-generated synonym expansions),
        they supplement the sub-query words for broader coverage.
        Returns {event_index: {scene_sequence, event_text, score}}.
        """
        # Build character name exclusion set from events' characters_involved
        char_name_words = set()
        for event in all_events:
            for name in (event.characters_involved or []):
                for part in name.lower().split():
                    if len(part) >= 3:
                        char_name_words.add(part)

        query_words = set()
        query_phrases = set()
        for sq in sub_queries:
            words = sq.lower().split()
            for w in words:
                if len(w) >= 4 and w not in _SEARCH_STOP_WORDS and w not in char_name_words:
                    query_words.add(w)
            for i in range(len(words) - 1):
                if len(words[i]) >= 3 and len(words[i + 1]) >= 3:
                    phrase = f"{words[i]} {words[i + 1]}"
                    # Keep phrases even if they contain character names
                    query_phrases.add(phrase)

        if not query_words and not llm_keywords:
            return {}

        results = {}

        # --- Pass A: Standard keyword scoring from sub-queries ---
        if query_words:
            total_terms = len(query_words)
            for idx, event in enumerate(all_events):
                event_lower = event.event_text.lower()
                event_words = set(event_lower.split())

                word_hits = sum(1 for w in query_words if w in event_words or w in event_lower)
                if word_hits == 0:
                    continue

                score = word_hits / total_terms
                for phrase in query_phrases:
                    if phrase in event_lower:
                        score += 0.15

                if score >= 0.3:
                    results[idx] = {
                        "scene_sequence": event.scene_sequence,
                        "event_text": event.event_text,
                        "score": min(score, 1.0),
                    }

        # --- Pass B: LLM keyword scoring (separate, not diluted by sub-query words) ---
        # Each LLM keyword is a synonym/variant. If ANY matches, the event is relevant.
        # Substring matching — "stolen car" matches "drove the stolen car away".
        # Track distinct keywords matched PER SCENE (across all events in that scene)
        # so scenes matching 2+ different keywords rank higher than single-keyword scenes.
        scene_kw_matches = {}  # scene_sequence -> set of matched keywords
        if llm_keywords:
            # Filter keywords: lowercase, exclude character names, min 3 chars
            filtered_kw = []
            for kw in llm_keywords:
                kw_lower = kw.strip().lower()
                if len(kw_lower) < 3:
                    continue
                if kw_lower in char_name_words:
                    continue
                filtered_kw.append(kw_lower)

            if filtered_kw:
                for idx, event in enumerate(all_events):
                    event_lower = event.event_text.lower()
                    matched = {kw for kw in filtered_kw if kw in event_lower}
                    if not matched:
                        continue
                    seq = event.scene_sequence
                    if seq not in scene_kw_matches:
                        scene_kw_matches[seq] = set()
                    scene_kw_matches[seq].update(matched)
                    # Per-event score based on hits in THIS event
                    hits = len(matched)
                    llm_score = min(0.35 + 0.15 * hits, 1.0)
                    if idx in results:
                        results[idx]["score"] = max(results[idx]["score"], llm_score)
                        results[idx]["has_keyword_match"] = True
                    else:
                        results[idx] = {
                            "scene_sequence": seq,
                            "event_text": event.event_text,
                            "score": llm_score,
                            "has_keyword_match": True,
                        }

        # Apply scene-level keyword diversity bonus:
        # Scenes where multiple DIFFERENT keywords matched across events get a boost.
        # This helps when a scene matches multiple keywords across its events
        # rank higher than scenes matching only 1 keyword.
        if scene_kw_matches:
            for idx in list(results.keys()):
                seq = results[idx]["scene_sequence"]
                distinct_kws = scene_kw_matches.get(seq)
                if distinct_kws and len(distinct_kws) > 1:
                    diversity_bonus = 0.10 * (len(distinct_kws) - 1)
                    results[idx]["score"] = min(results[idx]["score"] + diversity_bonus, 1.0)

        return results

    async def _lookup_scene_events(
        self,
        sub_queries: "List[str]",
        story_id: int,
        branch_id: "Optional[int]",
        db: Session,
        llm_keywords: "Optional[List[str]]" = None,
    ) -> "List[Dict[str, Any]]":
        """
        Hybrid event lookup: keyword matching + bi-encoder semantic similarity.

        Keyword matches are the strongest signal (direct word overlap).
        Semantic similarity fills vocabulary gaps (e.g. "stole" matches "theft").
        Final score = max(keyword_score, semantic_score) per event.
        Event embeddings are cached in memory per story for fast subsequent lookups.
        """
        try:
            from ..models.scene_event import SceneEvent

            # Load all events for this story/branch
            query = db.query(SceneEvent).filter(SceneEvent.story_id == story_id)
            if branch_id is not None:
                query = query.filter(
                    (SceneEvent.branch_id == branch_id) |
                    (SceneEvent.branch_id.is_(None))
                )
            all_events = query.order_by(SceneEvent.id).all()

            if not all_events:
                return []

            # --- Pass 1: Keyword scoring (instant, strongest signal) ---
            keyword_scores = self._keyword_score_events(sub_queries, all_events, llm_keywords=llm_keywords)
            kw_count = len(keyword_scores)

            # --- Pass 2: Semantic similarity (handles vocabulary gaps) ---
            # Per-sub-query top-K ensures each aspect of the query gets representation
            # (prevents one dominant sub-query from consuming all slots)
            per_query_top = {}  # {event_idx: score}
            if self.semantic_memory:
                try:
                    import numpy as np

                    max_event_id = all_events[-1].id
                    cache_key = story_id
                    cached = ContextManager._event_embedding_cache.get(cache_key)

                    if cached and cached[0] == max_event_id:
                        event_embeddings = cached[1]
                    else:
                        event_texts = [e.event_text for e in all_events]
                        event_embeddings = await self.semantic_memory.encode_texts(event_texts)
                        ContextManager._event_embedding_cache[cache_key] = (max_event_id, event_embeddings)
                        logger.info(f"[EVENT INDEX] Cached {len(all_events)} event embeddings for story {story_id}")

                    query_embeddings = await self.semantic_memory.encode_texts(sub_queries)

                    # Cosine similarity: (num_queries, num_events)
                    e_norms = np.linalg.norm(event_embeddings, axis=1, keepdims=True)
                    q_norms = np.linalg.norm(query_embeddings, axis=1, keepdims=True)
                    sim_matrix = (query_embeddings / (q_norms + 1e-8)) @ (event_embeddings / (e_norms + 1e-8)).T

                    # Take top 5 per sub-query, merge with max score per event
                    SIM_THRESHOLD = 0.45
                    PER_QUERY_K = 5
                    for q_idx in range(len(sub_queries)):
                        q_sims = sim_matrix[q_idx]
                        top_indices = np.argsort(q_sims)[::-1][:PER_QUERY_K * 3]  # oversample for dedup
                        count = 0
                        for idx in top_indices:
                            score = float(q_sims[idx])
                            if score < SIM_THRESHOLD:
                                break
                            if idx not in per_query_top or score > per_query_top[idx]:
                                per_query_top[idx] = score
                            count += 1
                            if count >= PER_QUERY_K:
                                break

                except Exception as e:
                    logger.warning(f"[EVENT INDEX] Semantic scoring failed, using keyword-only: {e}")

            # --- Character relevance: extract queried character names from sub-queries ---
            queried_chars = set()
            try:
                from ..models.character import Character as CharModel, StoryCharacter
                story_chars = (
                    db.query(CharModel.name)
                    .join(StoryCharacter, StoryCharacter.character_id == CharModel.id)
                    .filter(StoryCharacter.story_id == story_id)
                    .all()
                )
                # Build name variant mapping: any name form → canonical first name
                # "Elena Marco" → {"elena": "elena", "marco": "elena", "elena marco": "elena"}
                # This handles events stored as "Elena", "Mrs. Marco", or "Elena Marco"
                name_to_canonical = {}  # any variant → canonical first name
                all_first_names = set()
                for (cname,) in story_chars:
                    parts = cname.lower().split()
                    first = parts[0]
                    all_first_names.add(first)
                    name_to_canonical[cname.lower()] = first  # full name
                    for part in parts:
                        if part not in name_to_canonical:
                            name_to_canonical[part] = first  # first/last name

                # Extract ACTOR characters: the first character name in each sub-query,
                # then keep only those appearing as actor in majority of sub-queries.
                # "Matt pushed Claire aside" → Matt is actor (first name, position 0)
                # Majority vote filters out noise from passive-voice sub-queries.
                from collections import Counter
                actor_counts = Counter()
                for sq in sub_queries:
                    sq_lower = sq.lower()
                    earliest_pos = len(sq_lower)
                    earliest_canonical = None
                    for variant, canonical in name_to_canonical.items():
                        pos = sq_lower.find(variant)
                        if pos != -1 and pos < earliest_pos:
                            earliest_pos = pos
                            earliest_canonical = canonical
                    if earliest_canonical:
                        actor_counts[earliest_canonical] += 1
                # Keep characters that are actor in >1 sub-query (or sole sub-query)
                threshold = 2 if len(sub_queries) > 2 else 1
                for name, count in actor_counts.items():
                    if count >= threshold:
                        queried_chars.add(name)
                if queried_chars:
                    logger.info(f"[EVENT INDEX] Queried characters: {queried_chars}")
            except Exception:
                pass

            # --- Merge: max(keyword, semantic) per event, with character relevance ---
            all_indices = set(keyword_scores.keys()) | set(per_query_top.keys())
            matches = []
            for idx in all_indices:
                kw = keyword_scores.get(idx)
                sem = per_query_top.get(idx)
                kw_score = kw["score"] if kw else 0.0
                sem_score = sem if sem else 0.0
                best_score = max(kw_score, sem_score)
                has_kw = bool(kw and kw.get("has_keyword_match"))

                event = all_events[idx]

                # Demote events attributed to different characters than queried
                # Resolve event names through variant mapping (handles "Marco" → "elena")
                if queried_chars and event.characters_involved:
                    event_canonicals = set()
                    for c in event.characters_involved:
                        c_lower = c.lower()
                        canonical = name_to_canonical.get(c_lower) or name_to_canonical.get(c_lower.split()[0])
                        if canonical:
                            event_canonicals.add(canonical)
                        else:
                            event_canonicals.add(c_lower)  # NPC or unknown — use as-is
                    if event_canonicals & queried_chars:
                        pass  # Correct character — keep score
                    else:
                        best_score *= 0.5  # Wrong character — demote

                matches.append({
                    "scene_sequence": event.scene_sequence,
                    "event_text": event.event_text,
                    "score": best_score,
                    "has_keyword_match": has_kw,
                })

            # Deduplicate by scene_sequence (keep best score, propagate keyword flag)
            best_by_seq = {}
            for m in matches:
                seq = m["scene_sequence"]
                if seq not in best_by_seq or m["score"] > best_by_seq[seq]["score"]:
                    best_by_seq[seq] = m
                # Propagate keyword flag from ANY event in the scene
                if m.get("has_keyword_match"):
                    best_by_seq[seq]["has_keyword_match"] = True

            # Debug: check specific scenes of interest
            for dbg_seq in [52, 53, 54]:
                if dbg_seq in best_by_seq:
                    m = best_by_seq[dbg_seq]
                    logger.info(f"[EVENT INDEX DBG] seq={dbg_seq} score={m['score']:.3f} "
                               f"kw={m.get('has_keyword_match', False)} '{m['event_text'][:80]}'")
                else:
                    logger.info(f"[EVENT INDEX DBG] seq={dbg_seq} NOT in matches")

            # Sort: keyword matches first (more precise), then by score
            # This ensures scenes matching LLM synonyms get reserved slots over
            # semantic-only matches that may be thematically similar but factually wrong.
            all_scene_matches = sorted(
                best_by_seq.values(),
                key=lambda x: (x.get("has_keyword_match", False), x["score"]),
                reverse=True
            )
            top_matches = all_scene_matches[:12]

            if top_matches:
                sem_count = len(per_query_top) - kw_count
                logger.info(f"[EVENT INDEX] Found {len(top_matches)} matches "
                           f"(keyword={kw_count}, semantic={len(per_query_top)}, "
                           f"top={top_matches[0]['score']:.2f}: '{top_matches[0]['event_text'][:60]}')")
                # Debug: log top 8 event matches with scene sequence, score, and event snippet
                for rank, m in enumerate(top_matches[:8]):
                    logger.info(f"[EVENT INDEX] #{rank+1} seq={m['scene_sequence']} "
                               f"score={m['score']:.3f} kw={m.get('has_keyword_match', False)} "
                               f"'{m['event_text'][:80]}'...")

            return top_matches

        except Exception as e:
            logger.warning(f"[EVENT INDEX] Lookup failed: {e}")
            return []

    async def search_and_format_multi_query(
        self,
        sub_queries: "List[str]",
        context: "Dict[str, Any]",
        db: Session,
        intent_type: "Optional[str]" = None,
        temporal_type: "Optional[str]" = None,
        user_intent: "Optional[str]" = None,
        keywords: "Optional[List[str]]" = None
    ) -> "Optional[str]":
        """
        Run multi-query semantic search with RRF fusion, then apply boosts and format.

        Called from service.py after query decomposition succeeds.
        Reads search parameters from context["_semantic_search_state"].

        Args:
            sub_queries: Decomposed sub-queries from LLM
            context: The scene context dict containing _semantic_search_state
            db: Database session
            intent_type: Classified intent ("direct", "recall", "react") or None
            temporal_type: Temporal position ("earliest", "latest", "any") or None
            user_intent: Original user intent text for content verification keywords

        Returns:
            Formatted semantic scenes text, or None if search fails
        """
        state = context.get("_semantic_search_state")
        if not state:
            logger.warning("[SEMANTIC MULTI-QUERY] No _semantic_search_state in context")
            return None, 0.0

        if not self.semantic_memory:
            return None, 0.0

        try:
            user_intent = state["user_intent"]
            story_id = state["story_id"]
            exclude_sequences = state["exclude_sequences"]
            branch_id = state["branch_id"]
            chapter_id = state["chapter_id"]
            token_budget = state["token_budget"]
            world_scope = state.get("world_scope")  # None for single-story worlds
            exclude_scene_ids = state.get("exclude_scene_ids", set())

            # === SCENE EVENT INDEX ===
            # Event index provides precise factual matching via keyword + semantic scoring.
            # For recall: top matches get reserved slots (guaranteed in output, high floor scores).
            # For direct/react: matches contribute as pinned scenes (compete normally).
            # NOTE: Interaction shortcut removed — it matched interaction TYPE but not
            # direction/specifics (e.g., matched A→B when query was about B→A).
            # The event index provides precise per-event matching.
            pinned_scene_scores = {}  # {scene_id: score} — keyed by scene_id (globally unique)
            pinned_scene_ids = set()
            reserved_event_scene_ids = {}  # scene_id -> score (recall only, guaranteed slots)

            # Search event index across all world stories (or just current story)
            event_matches = []
            if world_scope:
                for ws_id, ws_branch in world_scope["story_branch_pairs"]:
                    matches = await self._lookup_scene_events(
                        sub_queries, ws_id, ws_branch, db, llm_keywords=keywords
                    )
                    # Attach story_id to each match for cross-story identification
                    for m in matches:
                        m["story_id"] = ws_id
                    event_matches.extend(matches)
                # Re-sort merged matches by score
                event_matches.sort(key=lambda x: (x.get("has_keyword_match", False), x["score"]), reverse=True)
                event_matches = event_matches[:12]
            else:
                event_matches = await self._lookup_scene_events(
                    sub_queries, story_id, branch_id, db, llm_keywords=keywords
                )
                for m in event_matches:
                    m["story_id"] = story_id

            # Resolve scene_ids for event matches (needed for scene_id-based pinning)
            # Build a map of (story_id, sequence) -> scene_id for surrounding scenes
            if event_matches:
                _em_lookup_pairs = set()
                for em in event_matches:
                    em_sid = em.get("story_id", story_id)
                    center_seq = em["scene_sequence"]
                    for offset in range(-2, 3):
                        seq = center_seq + offset
                        if seq > 0:
                            _em_lookup_pairs.add((em_sid, seq))
                # Batch query: find scene IDs for all (story_id, sequence) pairs
                _em_scene_map = {}  # (story_id, seq) -> scene_id
                if _em_lookup_pairs:
                    _em_story_ids = set(p[0] for p in _em_lookup_pairs)
                    _em_seqs = set(p[1] for p in _em_lookup_pairs)
                    _em_scenes = db.query(Scene.id, Scene.story_id, Scene.sequence_number, Scene.branch_id).filter(
                        Scene.story_id.in_(_em_story_ids),
                        Scene.sequence_number.in_(_em_seqs)
                    ).all()
                    for s in _em_scenes:
                        # Only include scenes on the correct branch
                        if world_scope:
                            expected_branch = world_scope["branch_map"].get(s.story_id)
                        else:
                            expected_branch = branch_id
                        if expected_branch is None or s.branch_id == expected_branch:
                            _em_scene_map[(s.story_id, s.sequence_number)] = s.id

            if intent_type == "recall" and event_matches:
                # RECALL: Pin all event matches + surroundings. Reserved slot
                # selection deferred until after RRF, when we can combine
                # event scores with RRF scores for better ranking.
                for em in event_matches:
                    em_sid = em.get("story_id", story_id)
                    center_seq = em['scene_sequence']
                    match_score = em.get('score', 0.5)
                    center_scene_id = _em_scene_map.get((em_sid, center_seq))
                    if center_scene_id:
                        if center_scene_id not in pinned_scene_scores or match_score > pinned_scene_scores[center_scene_id]:
                            pinned_scene_scores[center_scene_id] = match_score
                        pinned_scene_ids.add(center_scene_id)
                    for offset in [-2, -1, 1, 2]:
                        seq = center_seq + offset
                        if seq > 0:
                            neighbor_id = _em_scene_map.get((em_sid, seq))
                            if neighbor_id:
                                decay_score = match_score * max(0.4, 1.0 - 0.3 * abs(offset))
                                if neighbor_id not in pinned_scene_scores or decay_score > pinned_scene_scores[neighbor_id]:
                                    pinned_scene_scores[neighbor_id] = decay_score
                                pinned_scene_ids.add(neighbor_id)
                logger.info(f"[EVENT INDEX] Pinned {len(pinned_scene_ids)} total "
                           f"from {len(event_matches)} matches (reserved deferred to post-RRF)")
            elif event_matches:
                # DIRECT/REACT: Event matches are pinned but not reserved
                for em in event_matches:
                    em_sid = em.get("story_id", story_id)
                    center_seq = em['scene_sequence']
                    match_score = em.get('score', 0.5)
                    for offset in range(-2, 3):
                        seq = center_seq + offset
                        if seq > 0:
                            neighbor_id = _em_scene_map.get((em_sid, seq))
                            if neighbor_id:
                                pin_score = match_score * max(0.4, 1.0 - 0.3 * abs(offset))
                                if neighbor_id not in pinned_scene_scores or pin_score > pinned_scene_scores[neighbor_id]:
                                    pinned_scene_scores[neighbor_id] = pin_score
                                pinned_scene_ids.add(neighbor_id)
                logger.info(f"[EVENT INDEX] Pinned {len(pinned_scene_ids)} scene IDs "
                           f"from {len(event_matches)} event matches")

            # Use only decomposed sub-queries (not user_intent).
            # user_intent is a long narrative sentence that pulls in generic scenes;
            # sub-queries are more focused and produce better RRF fusion.
            all_queries = sub_queries

            logger.info(f"[SEMANTIC MULTI-QUERY] Running {len(all_queries)} sub-queries "
                       f"(intent: {intent_type or 'direct'})")

            # Request more results per query for post-filtering
            search_top_k = self.semantic_top_k * 5

            # Batch search — single batch encode + single pgvector call
            if world_scope:
                batch_results = await self.semantic_memory.search_similar_scenes_batch(
                    query_texts=all_queries,
                    story_ids=world_scope["story_ids"],
                    branch_map=world_scope["branch_map"],
                    top_k=search_top_k,
                    exclude_sequences=exclude_sequences,
                    exclude_story_id=story_id,
                    chapter_id=None
                )
            else:
                batch_results = await self.semantic_memory.search_similar_scenes_batch(
                    query_texts=all_queries,
                    story_id=story_id,
                    top_k=search_top_k,
                    exclude_sequences=exclude_sequences,
                    chapter_id=None
                )

            if not batch_results or all(len(r) == 0 for r in batch_results):
                logger.info("[SEMANTIC MULTI-QUERY] No results from batch search")
                return None, 0.0

            # RRF merge of bi-encoder results
            be_results = self._reciprocal_rank_fusion(batch_results)
            logger.info(f"[SEMANTIC MULTI-QUERY] Bi-encoder RRF: {sum(len(r) for r in batch_results)} results "
                       f"into {len(be_results)} unique scenes")

            if not be_results:
                return None, 0.0

            import re as _re

            # Extract character names for filtering (used by both keyword search and temporal anchoring)
            characters = context.get("characters", [])
            if isinstance(characters, dict) and "active_characters" in characters:
                char_names = [c.get("name", "").lower() for c in characters.get("active_characters", [])]
                char_names += [c.get("name", "").lower() for c in characters.get("inactive_characters", [])]
            else:
                char_names = [c.get("name", "").lower() for c in (characters if isinstance(characters, list) else [])]
            char_names = set(n for n in char_names if n)

            # Frequency-aware character name split:
            # Only filter high-frequency names (protagonists appearing in >30% of scenes).
            # Rare character names are valuable search keywords — keep them.
            from sqlalchemy import func as sa_func

            all_char_words = set()
            for name in char_names:
                for word in name.split():
                    if word and len(word) >= 3:
                        all_char_words.add(word)

            total_branch_scenes = db.query(sa_func.count(Scene.id)).filter(
                Scene.story_id == story_id, Scene.branch_id == branch_id
            ).scalar() or 1
            char_freq_threshold = int(total_branch_scenes * 0.30)

            char_name_words = set()   # high-freq → FILTER (protagonist noise)
            rare_char_words = set()   # low-freq → KEEP as keywords

            for word in all_char_words:
                count = db.query(sa_func.count(Scene.id)).join(
                    SceneVariant, and_(SceneVariant.scene_id == Scene.id, SceneVariant.is_original == True)
                ).filter(
                    sa_func.lower(SceneVariant.content).like(f'%{word}%'),
                    Scene.story_id == story_id, Scene.branch_id == branch_id
                ).scalar() or 0
                if count > char_freq_threshold:
                    char_name_words.add(word)
                else:
                    rare_char_words.add(word)

            logger.info(f"[CHAR FREQ] filter={char_name_words}, keep(rare)={rare_char_words} "
                        f"(threshold={char_freq_threshold}/{total_branch_scenes})")

            # === KEYWORD SEARCH ===
            # The bi-encoder misses scenes that contain exact query terms but embed
            # differently. Keyword search catches these (e.g. "kitchen counter" scenes
            # invisible to bi-encoder). Results are RRF-merged with bi-encoder pool.
            try:

                # Extract keywords: 2+ word phrases and distinctive single words
                # Comprehensive stop word list shared with temporal anchoring
                kw_stop_words = _SEARCH_STOP_WORDS
                kw_phrases = set()
                kw_words = set()
                for sq in sub_queries:
                    words = _re.findall(r'\b[a-z]+\b', sq.lower())
                    # 2-word phrases (no stop words, no char names)
                    for i in range(len(words) - 1):
                        w1, w2 = words[i], words[i + 1]
                        if (w1 not in kw_stop_words and w2 not in kw_stop_words
                                and w1 not in char_name_words and w2 not in char_name_words
                                and len(w1) >= 3 and len(w2) >= 3):
                            kw_phrases.add(f"{w1} {w2}")
                    # Single words (≥5 chars, not stop words, not char names)
                    for w in words:
                        if len(w) >= 5 and w not in kw_stop_words and w not in char_name_words:
                            kw_words.add(w)

                # Prefer phrases — skip single words contained in qualifying phrases
                for phrase in list(kw_phrases):
                    for w in phrase.split():
                        kw_words.discard(w)

                search_keywords = list(kw_phrases) + list(kw_words)
                logger.info(f"[KEYWORD SEARCH] Keywords: {search_keywords}")

                if search_keywords:
                    # Find scenes matching each keyword via DB LIKE query
                    kw_scene_seqs = {}  # keyword → {scene_id: info}
                    # Build list of (story_id, branch_id) pairs to search
                    _kw_search_pairs = (
                        world_scope["story_branch_pairs"] if world_scope
                        else [(story_id, branch_id)]
                    )
                    for keyword in search_keywords:
                        pattern = f"%{keyword}%"
                        for _kw_sid, _kw_bid in _kw_search_pairs:
                            query = db.query(
                                Scene.id, Scene.story_id, Scene.sequence_number, Scene.chapter_id,
                                SceneVariant.id.label('variant_id')
                            ).join(
                                SceneVariant, and_(
                                    SceneVariant.scene_id == Scene.id,
                                    SceneVariant.is_original == True
                                )
                            ).filter(
                                sa_func.lower(SceneVariant.content).like(sa_func.lower(pattern)),
                                Scene.story_id == _kw_sid,
                            )
                            if _kw_bid is not None:
                                query = query.filter(Scene.branch_id == _kw_bid)
                            # Exclude sequences only from current story
                            if exclude_sequences and _kw_sid == story_id:
                                query = query.filter(~Scene.sequence_number.in_(exclude_sequences))
                            rows = query.all()
                            if rows:
                                if keyword not in kw_scene_seqs:
                                    kw_scene_seqs[keyword] = {}
                                kw_scene_seqs[keyword].update({
                                    r.id: {'seq': r.sequence_number, 'chapter_id': r.chapter_id,
                                           'variant_id': r.variant_id, 'story_id': r.story_id}
                                    for r in rows
                                })

                    # IDF filter: drop keywords that match too many scenes (no discriminative power).
                    # Words like "any", "without", character names all match 50%+ of scenes.
                    # Specific keywords ("kitchen counter", "sundress") match <15%.
                    # total_branch_scenes reused from character frequency check above.
                    max_kw_matches = max(20, int(total_branch_scenes * 0.15))
                    dropped = []
                    for keyword in list(kw_scene_seqs.keys()):
                        n_matches = len(kw_scene_seqs[keyword])
                        if n_matches > max_kw_matches:
                            # Exempt keywords containing rare character names
                            if rare_char_words and set(keyword.split()) & rare_char_words:
                                logger.info(f"[KEYWORD SEARCH] IDF exempt '{keyword}'({n_matches}) — rare char name")
                                continue
                            dropped.append(f"'{keyword}'({n_matches})")
                            del kw_scene_seqs[keyword]
                    if dropped:
                        logger.info(f"[KEYWORD SEARCH] IDF filter dropped (>{max_kw_matches} matches): {', '.join(dropped)}")

                    # Score each scene by how many keywords it matches
                    scene_kw_count = {}  # scene_id → match count
                    scene_info = {}  # scene_id → {seq, chapter_id, variant_id}
                    for keyword, scene_map in kw_scene_seqs.items():
                        for sid, info in scene_map.items():
                            scene_kw_count[sid] = scene_kw_count.get(sid, 0) + 1
                            scene_info[sid] = info

                    total_kw = max(1, len(kw_scene_seqs))  # Only count surviving keywords
                    keyword_results = []
                    for sid, count in scene_kw_count.items():
                        info = scene_info[sid]
                        keyword_results.append({
                            'scene_id': sid,
                            'story_id': info.get('story_id', story_id),
                            'variant_id': info['variant_id'],
                            'sequence': info['seq'],
                            'chapter_id': info['chapter_id'],
                            'embedding_id': f"scene_{sid}_v{info['variant_id']}",
                            'similarity_score': count / total_kw,
                            'keyword_matches': count,
                        })
                    keyword_results.sort(key=lambda x: x['similarity_score'], reverse=True)

                    if keyword_results:
                        # RRF merge bi-encoder + keyword pools
                        similar_scenes = self._reciprocal_rank_fusion([be_results, keyword_results])
                        logger.info(f"[KEYWORD SEARCH] Hybrid RRF: {len(be_results)} bi-encoder + "
                                   f"{len(keyword_results)} keyword → {len(similar_scenes)} unique")
                    else:
                        similar_scenes = be_results
                        logger.info("[KEYWORD SEARCH] No keyword matches, using bi-encoder only")
                else:
                    similar_scenes = be_results
                    logger.info("[KEYWORD SEARCH] No keywords extracted, using bi-encoder only")
            except Exception as e:
                similar_scenes = be_results
                logger.warning(f"[KEYWORD SEARCH] Failed (non-fatal), using bi-encoder only: {e}")

            # char_names and char_name_words already extracted above (before keyword search)

            stop_words = _SEARCH_STOP_WORDS

            # === TEMPORAL ANCHORING ===
            # Use keywords from sub-queries to find WHEN recalled events happened,
            # then boost semantic results near that timeframe.
            try:
                # Step 3a: Extract anchor keywords — 2-word phrases + distinctive single words
                anchor_phrases = set()
                anchor_words = set()
                for sq in sub_queries:
                    words = _re.findall(r'\b[a-z]+\b', sq.lower())
                    # 2-word phrases (excluding char names)
                    for i in range(len(words) - 1):
                        w1, w2 = words[i], words[i + 1]
                        if w1 not in char_name_words and w2 not in char_name_words:
                            bigram = f"{w1} {w2}"
                            if len(bigram) >= 7:
                                anchor_phrases.add(bigram)
                    # Distinctive single words (≥4 chars, not stop/name words)
                    for w in words:
                        if len(w) >= 4 and w not in stop_words and w not in char_name_words:
                            anchor_words.add(w)

                # Combine all candidate keywords (phrases first — more specific)
                anchor_candidates = [(p, True) for p in anchor_phrases] + [(w, False) for w in anchor_words]
                logger.info(f"[TEMPORAL ANCHOR] Candidates: {len(anchor_phrases)} phrases, {len(anchor_words)} words")

                # Step 3b: Filter by specificity — query DB for scene count per keyword
                # Ceiling raised to 40 (was 15): words like "sundress" (38 scenes) are
                # strong signals when combined with recency weighting. The recency-weighted
                # average naturally handles words with many old occurrences.
                # For world scope, use global positions (offset + sequence) for cross-story distance.
                _global_offsets = world_scope["global_offsets"] if world_scope else {story_id: 0}
                _anchor_search_pairs = (
                    world_scope["story_branch_pairs"] if world_scope
                    else [(story_id, branch_id)]
                )

                qualifying_sequences = []  # Global positions from qualifying keywords
                qualifying_keywords = []

                for keyword, is_phrase in anchor_candidates:
                    pattern = f"%{keyword}%"
                    all_global_positions = []
                    for _a_sid, _a_bid in _anchor_search_pairs:
                        query = db.query(Scene.sequence_number).join(
                            SceneVariant, and_(
                                SceneVariant.scene_id == Scene.id,
                                SceneVariant.is_original == True
                            )
                        ).filter(
                            sa_func.lower(SceneVariant.content).like(sa_func.lower(pattern)),
                            Scene.story_id == _a_sid,
                        )
                        if _a_bid is not None:
                            query = query.filter(Scene.branch_id == _a_bid)
                        rows = query.order_by(Scene.sequence_number).all()
                        offset = _global_offsets.get(_a_sid, 0)
                        all_global_positions.extend([offset + r[0] for r in rows])
                    count = len(all_global_positions)
                    if 2 <= count <= 40:
                        qualifying_sequences.extend(all_global_positions)
                        qualifying_keywords.append((keyword, count, all_global_positions))
                        logger.debug(f"[TEMPORAL ANCHOR] Kept '{keyword}' ({count} scenes): {all_global_positions[:10]}...")
                    else:
                        logger.debug(f"[TEMPORAL ANCHOR] Discarded '{keyword}' ({count} scenes)")

                # Step 3b2: Prefer phrases over constituent words
                # If "kitchen counter" qualified, skip "kitchen" and "counter" as separate words
                qualified_phrase_set = set(kw for kw, cnt, sq in qualifying_keywords if ' ' in kw)
                if qualified_phrase_set:
                    before_count = len(qualifying_keywords)
                    filtered_kw = []
                    for kw, cnt, seqs in qualifying_keywords:
                        if ' ' not in kw:  # single word
                            if any(kw in phrase for phrase in qualified_phrase_set):
                                logger.debug(f"[TEMPORAL ANCHOR] Skipping '{kw}' — contained in qualifying phrase")
                                # Remove this word's sequences from qualifying_sequences
                                for s in seqs:
                                    try:
                                        qualifying_sequences.remove(s)
                                    except ValueError:
                                        pass
                                continue
                        filtered_kw.append((kw, cnt, seqs))
                    qualifying_keywords = filtered_kw
                    if len(qualifying_keywords) < before_count:
                        logger.info(f"[TEMPORAL ANCHOR] Phrase dedup: {before_count} -> {len(qualifying_keywords)} keywords")

                # Step 3c: Compute temporal anchors with confidence weights.
                # Each anchor gets a confidence proportional to the total keyword occurrences
                # that contributed to it. "sundress" (37 occ) → high confidence anchor.
                # "underwear" (3 occ) → low confidence anchor (weaker boost).
                ANCHOR_RECENT_LIMIT = 5
                anchor_data = []  # list of (anchor_value, confidence)
                if qualifying_sequences:
                    all_seqs_sorted = sorted(qualifying_sequences)
                    spread = all_seqs_sorted[-1] - all_seqs_sorted[0]
                    latest_seq = all_seqs_sorted[-1]

                    def _recency_weighted_anchor(seqs):
                        """Compute recency-weighted average of last N sequence numbers."""
                        if not seqs:
                            return 0
                        recent = sorted(seqs)[-ANCHOR_RECENT_LIMIT:]
                        seq_min = min(recent)
                        decay_range = max(1, latest_seq - seq_min)
                        weights = [1.0 + 3.0 * ((s - seq_min) / decay_range) for s in recent]
                        total_weight = sum(weights)
                        return int(sum(s * w for s, w in zip(recent, weights)) / total_weight) if total_weight > 0 else int(sum(recent) / len(recent))

                    if spread > 100 and len(qualifying_keywords) >= 2:
                        # Wide spread — per-sub-query anchors with confidence
                        for sq in sub_queries:
                            sq_lower = sq.lower()
                            sq_seqs = []
                            sq_total_occ = 0
                            for keyword, count, seqs in qualifying_keywords:
                                if keyword in sq_lower:
                                    sq_seqs.extend(seqs)
                                    sq_total_occ += count
                            if sq_seqs:
                                anchor_val = _recency_weighted_anchor(sq_seqs)
                                # Confidence saturates at 15 occurrences (min 0.15 for any qualifying keyword)
                                confidence = min(1.0, max(0.15, sq_total_occ / 15.0))
                                anchor_data.append((anchor_val, confidence))
                        # Deduplicate by anchor value (keep highest confidence)
                        seen = {}
                        for val, conf in anchor_data:
                            if val not in seen or conf > seen[val]:
                                seen[val] = conf
                        anchor_data = sorted(seen.items())
                    if not anchor_data:
                        total_occ = sum(c for _, c, _ in qualifying_keywords)
                        anchor_data = [(_recency_weighted_anchor(qualifying_sequences),
                                       min(1.0, max(0.15, total_occ / 15.0)))]

                    anchors = [a for a, _ in anchor_data]
                    logger.info(f"[TEMPORAL ANCHOR] Keywords: {[(k, c) for k, c, _ in qualifying_keywords]}, "
                               f"anchors: {[(a, f'{c:.2f}') for a, c in anchor_data]}, spread: {spread}")

                    # Step 3d: Apply confidence-weighted proximity boost
                    # Skip for recall intents — sub-queries already target early events;
                    # recency-weighted boosting would fight that by inflating recent scenes.
                    if intent_type == "recall":
                        logger.info(f"[TEMPORAL ANCHOR] Computed anchors {[(a, f'{c:.2f}') for a, c in anchor_data]} "
                                   f"but SKIPPING boost — recall intent")
                    else:
                        result_scene_ids = [r['scene_id'] for r in similar_scenes]
                        result_scenes = db.query(Scene.id, Scene.story_id, Scene.sequence_number).filter(
                            Scene.id.in_(result_scene_ids)
                        ).all()
                        # Map scene_id → global position for distance calculations
                        global_pos_by_id = {}
                        for sid, s_story_id, seq in result_scenes:
                            offset = _global_offsets.get(s_story_id, 0)
                            global_pos_by_id[sid] = offset + seq

                        boosted_count = 0
                        for result in similar_scenes:
                            global_pos = global_pos_by_id.get(result['scene_id'])
                            if global_pos is None:
                                continue
                            # Best boost across all anchors (each weighted by confidence)
                            best_boost = 0.0
                            for anchor_val, confidence in anchor_data:
                                distance = abs(global_pos - anchor_val)
                                raw_boost = max(0.0, 0.50 - 0.005 * distance)
                                best_boost = max(best_boost, raw_boost * confidence)
                            if best_boost > 0:
                                result['similarity_score'] += best_boost
                                result['temporal_boost'] = best_boost
                                boosted_count += 1

                        if boosted_count > 0:
                            similar_scenes.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
                            logger.info(f"[TEMPORAL ANCHOR] Boosted {boosted_count} scenes "
                                       f"(global offsets: {_global_offsets}). "
                                       f"Top 5 after: {[(r.get('similarity_score', 0), global_pos_by_id.get(r['scene_id'], '?')) for r in similar_scenes[:5]]}")
                else:
                    logger.info("[TEMPORAL ANCHOR] No qualifying keywords found — skipping")

            except Exception as e:
                logger.warning(f"[TEMPORAL ANCHOR] Failed (non-fatal): {e}")
                import traceback
                logger.debug(traceback.format_exc())

            # Batch-load content for top candidates (used by reranking / phrase boost / content verification)
            candidate_ids = [r['scene_id'] for r in similar_scenes[:50]]
            candidate_scenes_db = db.query(Scene).filter(Scene.id.in_(candidate_ids)).all()
            scenes_by_id = {s.id: s for s in candidate_scenes_db}

            flows = db.query(StoryFlow).filter(
                StoryFlow.scene_id.in_(candidate_ids),
                StoryFlow.is_active == True
            ).all()
            flow_by_scene = {f.scene_id: f for f in flows}

            # Cache content strings for reuse
            content_by_scene_id = {}
            for sid in candidate_ids:
                flow = flow_by_scene.get(sid)
                content_by_scene_id[sid] = (flow.scene_variant.content if flow and flow.scene_variant else "").lower()

            # Cross-encoder reranking disabled — adds ~23s latency for marginal quality gain.
            # Event index + keyword scoring + content verification handle recall well enough.
            rerank_applied = False

            if not rerank_applied:
                # Fallback: phrase boost + content verification (when reranker unavailable)
                # === PHRASE-LEVEL KEYWORD BOOST ===
                phrases = set()
                for sq in sub_queries:
                    words = _re.findall(r'\b[a-z]+\b', sq.lower())
                    for i in range(len(words) - 1):
                        w1, w2 = words[i], words[i + 1]
                        if w1 not in char_name_words and w2 not in char_name_words:
                            bigram = f"{w1} {w2}"
                            if len(bigram) >= 7:
                                phrases.add(bigram)
                phrases = list(phrases)

                if phrases:
                    for result in similar_scenes[:50]:
                        content = content_by_scene_id.get(result['scene_id'], "")
                        if not content:
                            continue
                        total_boost = 0.0
                        matched = []
                        for phrase in phrases:
                            if phrase in content:
                                total_boost += 0.15
                                matched.append(phrase)
                        if matched:
                            capped = min(total_boost, 0.30)
                            result['similarity_score'] += capped
                            result['phrase_boost'] = capped
                            result['phrase_matches'] = matched

                    similar_scenes.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
                    logger.info(f"[SEMANTIC MULTI-QUERY] Phrase boost applied with phrases: {phrases}")

                # === CONTENT VERIFICATION RE-SCORING ===
                verify_words = set()
                verify_source = "sub-queries"
                if user_intent:
                    intent_words = set()
                    for w in _re.findall(r'\b[a-z]+\b', user_intent.lower()):
                        if len(w) >= 4 and w not in _SEARCH_STOP_WORDS and w not in char_name_words:
                            intent_words.add(w)
                    if len(intent_words) >= 2:
                        verify_words = intent_words
                        verify_source = "user_intent"
                if not verify_words:
                    for sq in sub_queries:
                        for w in _re.findall(r'\b[a-z]+\b', sq.lower()):
                            if len(w) >= 4 and w not in _SEARCH_STOP_WORDS and w not in char_name_words:
                                verify_words.add(w)

                if verify_words:
                    for result in similar_scenes[:50]:
                        content = content_by_scene_id.get(result['scene_id'], "")
                        if not content:
                            result['content_match'] = 0.0
                            result['similarity_score'] *= 0.4
                            continue
                        matches = sum(1 for w in verify_words if w in content)
                        ratio = matches / len(verify_words)
                        result['content_match'] = ratio
                        result['similarity_score'] *= (0.4 + 0.6 * ratio)

                    similar_scenes.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
                    logger.info(f"[CONTENT VERIFY] {len(verify_words)} keywords from {verify_source}: {sorted(verify_words)}, "
                               f"Top 5: {[(round(r.get('similarity_score', 0), 3), round(r.get('content_match', 0), 2), content_by_scene_id.get(r['scene_id'], '')[:30]) for r in similar_scenes[:5]]}")

            # No merge with single-query results. Multi-query runs independently with
            # content verification to ensure scenes match actual query content. Merging
            # single-query keyword-boosted scores would bypass content verification and
            # promote scenes that match common words but not the specific query intent.

            # === FILTER + FORMAT ===
            # No chapter affinity boost: multi-query targets cross-chapter retrieval.
            # No age filter: past events ARE the target; min_similarity threshold suffices.
            # Cross-encoder scores are sigmoid-normalized [0,1] — use stricter threshold
            # to avoid padding budget with weakly relevant scenes.
            min_sim = 0.5 if rerank_applied else self.semantic_min_similarity
            filtered_results = []
            for result in similar_scenes:
                similarity_score = result.get('similarity_score', 0.0)
                if result.get('pinned'):
                    pass  # Pinned scenes bypass threshold
                elif similarity_score < min_sim:
                    continue

                scene = db.query(Scene).filter(Scene.id == result['scene_id']).first()
                if not scene:
                    continue

                # Branch filtering: for world scope, use per-story branch_map
                if world_scope:
                    expected_branch = world_scope["branch_map"].get(scene.story_id)
                    if expected_branch is not None and scene.branch_id != expected_branch:
                        continue
                elif branch_id is not None and scene.branch_id != branch_id:
                    continue

                filtered_results.append(result)

            if not filtered_results:
                logger.info("[SEMANTIC MULTI-QUERY] No scenes passed filters")
                return None, 0.0

            # === SELECTION ===
            scene_limit = 15

            # Get sequence numbers for all filtered results
            result_ids = [r['scene_id'] for r in filtered_results]
            result_scenes_db = db.query(Scene.id, Scene.sequence_number).filter(
                Scene.id.in_(result_ids)
            ).all()
            seq_by_id_sel = {sid: seq for sid, seq in result_scenes_db}

            # Deduplicate by scene_id (keep highest score)
            seen_scene_ids = {}
            for r in filtered_results:
                sid = r['scene_id']
                if sid not in seen_scene_ids or r.get('similarity_score', 0) > seen_scene_ids[sid].get('similarity_score', 0):
                    seen_scene_ids[sid] = r
            filtered_results = list(seen_scene_ids.values())

            # Remove scenes already in RECENT SCENES (they waste a slot)
            # For world scope, use scene_id-based exclusion (sequences are story-specific)
            if exclude_scene_ids:
                before_count = len(filtered_results)
                filtered_results = [r for r in filtered_results if r['scene_id'] not in exclude_scene_ids]
                removed = before_count - len(filtered_results)
                if removed:
                    logger.info(f"[SEMANTIC MULTI-QUERY] Removed {removed} scenes by scene_id exclusion")
            elif exclude_sequences:
                exclude_set = set(exclude_sequences)
                before_count = len(filtered_results)
                filtered_results = [r for r in filtered_results if seq_by_id_sel.get(r['scene_id']) not in exclude_set]
                removed = before_count - len(filtered_results)
                if removed:
                    logger.info(f"[SEMANTIC MULTI-QUERY] Removed {removed} scenes already in recent context")

            # === TEMPORAL POSITION BOOST ===
            # When the LLM classifies temporal intent, bias selection toward the
            # right part of the timeline. Uses multiplicative boost so relevant
            # scenes get amplified while irrelevant ones stay low.
            # "earliest" boosts low sequence numbers, "latest" boosts high.
            # Applied to all intents including recall — helps disambiguate when
            # the same characters had similar interactions at different points.
            if temporal_type in ("earliest", "latest") and filtered_results:
                # Build global positions for temporal position boost
                _tp_scene_ids = [r['scene_id'] for r in filtered_results]
                _tp_scenes = db.query(Scene.id, Scene.story_id, Scene.sequence_number).filter(
                    Scene.id.in_(_tp_scene_ids)
                ).all()
                _tp_global = {sid: _global_offsets.get(s_sid, 0) + seq for sid, s_sid, seq in _tp_scenes}

                positions = [_tp_global.get(r['scene_id'], 0) for r in filtered_results]
                min_pos, max_pos = min(positions), max(positions)
                pos_range = max(1, max_pos - min_pos)

                boosted = 0
                for r in filtered_results:
                    pos = _tp_global.get(r['scene_id'], 0)
                    if temporal_type == "earliest":
                        position_ratio = 1.0 - ((pos - min_pos) / pos_range)
                    else:
                        position_ratio = (pos - min_pos) / pos_range
                    multiplier = 0.8 + 0.2 * position_ratio
                    r['temporal_position_boost'] = multiplier
                    r['similarity_score'] *= multiplier
                    boosted += 1

                filtered_results.sort(key=lambda r: r.get('similarity_score', 0), reverse=True)
                top5 = [(round(r.get('similarity_score', 0), 3), _tp_global.get(r['scene_id'], '?'))
                         for r in filtered_results[:5]]
                logger.info(f"[TEMPORAL POSITION] Applied {temporal_type} penalty (×0.8–1.0) to {boosted} scenes. "
                           f"Top 5: {top5}")

            # Don't pad with noise — remove low-relevance scenes before selection
            MIN_RELEVANCE = 0.40
            pre_filter_count = len(filtered_results)
            filtered_results = [r for r in filtered_results if r.get('similarity_score', 0) >= MIN_RELEVANCE]
            if len(filtered_results) < pre_filter_count:
                logger.info(f"[RELEVANCE FILTER] Removed {pre_filter_count - len(filtered_results)} "
                           f"scenes below {MIN_RELEVANCE} threshold")

            # === RESERVED SLOT SELECTION ===
            # Select top 3 event matches by event_score only (not RRF).
            # The event index exists to find scenes the bi-encoder MISSES —
            # penalizing zero-RRF scenes defeats that purpose.
            if intent_type == "recall" and event_matches:
                event_matches.sort(key=lambda em: em.get('score', 0.5), reverse=True)

                reserved_event_scene_ids.clear()
                for em in event_matches[:3]:
                    em_sid = em.get("story_id", story_id)
                    center_seq = em['scene_sequence']
                    center_scene_id = _em_scene_map.get((em_sid, center_seq))
                    if center_scene_id:
                        score = em.get('score', 0.5) + 0.15
                        reserved_event_scene_ids[center_scene_id] = score
                        pinned_scene_scores[center_scene_id] = score

                top5_info = [(em['scene_sequence'], em.get('story_id', story_id), f"ev={em.get('score', 0):.3f}")
                             for em in event_matches[:5]]
                logger.info(f"[EVENT RESERVED] Top 5 by event score: {top5_info}")
                logger.info(f"[EVENT RESERVED] Reserved 3 clusters at scene_ids: {list(reserved_event_scene_ids.keys())}")

            # Select top-N, guaranteeing pinned scenes are included (budget-limited by pin score)
            filtered_results.sort(key=lambda r: r.get('similarity_score', 0), reverse=True)

            if pinned_scene_ids:
                # Apply reserved additive bonus to event-matched scenes
                if reserved_event_scene_ids:
                    for r in filtered_results:
                        if r['scene_id'] in reserved_event_scene_ids:
                            r['similarity_score'] += 0.15

                # Load pinned scenes not already in the candidate pool
                existing_ids = {r['scene_id'] for r in filtered_results}
                missing_ids = pinned_scene_ids - existing_ids
                loaded_count = 0
                if missing_ids:
                    missing_scenes = db.query(Scene).filter(
                        Scene.id.in_(missing_ids),
                    ).all()
                    for ms in missing_scenes:
                        flow = db.query(StoryFlow).filter(
                            StoryFlow.scene_id == ms.id,
                            StoryFlow.is_active == True
                        ).first()
                        if flow and flow.scene_variant:
                            score = pinned_scene_scores.get(ms.id, 0.5)
                            # Reserved scenes from DB also get additive bonus
                            if ms.id in reserved_event_scene_ids:
                                score += 0.15
                            r = {
                                'scene_id': ms.id,
                                'story_id': ms.story_id,
                                'variant_id': flow.scene_variant.id,
                                'sequence': ms.sequence_number,
                                'chapter_id': ms.chapter_id,
                                'similarity_score': score,
                                'pinned': True,
                            }
                            filtered_results.append(r)
                            seq_by_id_sel[ms.id] = ms.sequence_number
                            loaded_count += 1
                    if loaded_count:
                        logger.info(f"[EVENT INDEX] Loaded {loaded_count} additional pinned scenes from DB")

                # Guarantee reserved event clusters (-1, center, +1) for top event matches.
                # Find neighboring scene_ids for each reserved center scene.
                reserved_cluster_ids = set()
                if reserved_event_scene_ids:
                    for center_id in reserved_event_scene_ids:
                        reserved_cluster_ids.add(center_id)
                        # Find neighbor scenes by sequence ±1 in the same story/branch
                        center_scene = db.query(Scene).filter(Scene.id == center_id).first()
                        if center_scene:
                            neighbors = db.query(Scene.id).filter(
                                Scene.story_id == center_scene.story_id,
                                Scene.branch_id == center_scene.branch_id,
                                Scene.sequence_number.in_([
                                    center_scene.sequence_number - 1,
                                    center_scene.sequence_number + 1
                                ]),
                            ).all()
                            for (nid,) in neighbors:
                                reserved_cluster_ids.add(nid)

                reserved_ids = set()
                reserved_selected = []
                if reserved_cluster_ids:
                    for r in filtered_results:
                        if r['scene_id'] in reserved_cluster_ids:
                            reserved_selected.append(r)
                            reserved_ids.add(r['scene_id'])

                remaining_budget = scene_limit - len(reserved_selected)
                rest = [r for r in filtered_results if r['scene_id'] not in reserved_ids]
                rest.sort(key=lambda r: r.get('similarity_score', 0), reverse=True)
                selected = reserved_selected + rest[:max(0, remaining_budget)]

                pinned_in = sum(1 for r in selected if r['scene_id'] in pinned_scene_ids)
                ranked_in = len(selected) - pinned_in
                logger.info(f"[SCENE SELECTION] {len(reserved_selected)} reserved (clusters) + "
                           f"{pinned_in - len(reserved_selected)} pinned + {ranked_in} ranked "
                           f"= {len(selected)} total")
            else:
                selected = filtered_results[:scene_limit]

            # Build final list with Scene objects, sorted chronologically for output
            # For world scope, use global position for cross-story ordering
            selected_ids = {r['scene_id'] for r in selected}
            all_selected_scenes = db.query(Scene).filter(Scene.id.in_(selected_ids)).all()
            scene_obj_by_id = {s.id: s for s in all_selected_scenes}
            filtered_with_scenes = []
            for r in selected:
                scene = scene_obj_by_id.get(r['scene_id'])
                if scene:
                    filtered_with_scenes.append((r, scene))

            # Sort by global position (cross-story chronological order)
            _fmt_offsets = world_scope["global_offsets"] if world_scope else {story_id: 0}
            filtered_with_scenes.sort(
                key=lambda x: _fmt_offsets.get(x[1].story_id, 0) + x[1].sequence_number
            )

            if filtered_with_scenes:
                selected_info = [
                    (round(r['similarity_score'], 3), s.sequence_number,
                     f"s{s.story_id}" if world_scope and s.story_id != story_id else "")
                    for r, s in filtered_with_scenes
                ]
                logger.info(f"[SEMANTIC MULTI-QUERY] Selected {len(filtered_with_scenes)} scenes (score, seq#, story): {selected_info}")

            # Format within token budget — select by SCORE, present chronologically
            # No per-scene truncation — include full scene content; token budget controls total inclusion
            _story_titles = world_scope["story_titles"] if world_scope else {}
            scene_entries = []
            for result, scene in filtered_with_scenes:
                variant = db.query(SceneVariant).filter(SceneVariant.id == result['variant_id']).first()
                if not variant:
                    continue
                # Cross-story scenes get story title label
                if world_scope and scene.story_id != story_id:
                    title = _story_titles.get(scene.story_id, f"Story {scene.story_id}")
                    label = f"[From '{title}', Scene {scene.sequence_number}]"
                else:
                    label = f"[Relevant from Scene {scene.sequence_number}]"
                scene_text = f"{label}:\n{variant.content}"
                global_pos = _fmt_offsets.get(scene.story_id, 0) + scene.sequence_number
                scene_entries.append({
                    'result': result,
                    'scene': scene,
                    'full_text': scene_text,
                    'full_tokens': self.count_tokens(scene_text),
                    'score': result.get('similarity_score', 0),
                    'seq': scene.sequence_number,
                    'global_pos': global_pos,
                })

            # Greedily select scenes by score (highest first) within token budget
            scene_entries.sort(key=lambda e: e['score'], reverse=True)
            total_tokens_used = 0
            selected_entries = []
            for entry in scene_entries:
                if total_tokens_used + entry['full_tokens'] <= token_budget:
                    entry['use_text'] = entry['full_text']
                    total_tokens_used += entry['full_tokens']
                    selected_entries.append(entry)

            # Step 3: Sort selected scenes chronologically for presentation (global order)
            selected_entries.sort(key=lambda e: e['global_pos'])
            relevant_parts = [e['use_text'] for e in selected_entries]

            if relevant_parts:
                top_score = max(r.get('similarity_score', 0) for r, _s in filtered_with_scenes)
                logger.info(f"[SEMANTIC MULTI-QUERY] Formatted {len(relevant_parts)} scenes, "
                           f"total chars: {sum(len(p) for p in relevant_parts)}, top_score: {top_score:.3f}")
                return "\n\n".join(relevant_parts), top_score

            return None, 0.0

        except Exception as e:
            logger.error(f"[SEMANTIC MULTI-QUERY] Failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, 0.0

    async def _get_character_context(
        self,
        story_id: int,
        recent_scenes: List[Scene],
        token_budget: int,
        db: Session
    ) -> Optional[str]:
        """
        Get character-specific context.

        Args:
            story_id: Story ID
            recent_scenes: Recent scenes to identify active characters
            token_budget: Available tokens
            db: Database session

        Returns:
            Formatted character context or None
        """
        if not recent_scenes or token_budget < 100:
            return None

        try:
            # TODO: Extract characters from recent scenes
            # For now, return None - will be implemented with CharacterMemoryService
            return None

        except Exception as e:
            logger.error(f"Failed to get character context: {e}")
            return None

    async def _get_chapter_summaries(
        self,
        story_id: int,
        token_budget: int,
        db: Session,
        chapter_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Get chapter summaries for compressed history.

        NOTE: story_so_far and previous_chapter_summary are NOT included here because
        they are already included as direct fields in base_context to avoid duplication.

        Only includes:
        - Summary of the current chapter (auto_summary if it has scenes and has been processed)

        Args:
            story_id: Story ID
            token_budget: Available tokens
            db: Database session
            chapter_id: Optional current chapter ID

        Returns:
            Formatted chapter summaries or None
        """
        if token_budget < 200:
            return None

        try:
            summary_parts = []
            used_tokens = 0

            # Get current chapter's auto_summary (if it has scenes and has been processed)
            # NOTE: We do NOT include story_so_far or previous_chapter_summary here - they are
            # handled as direct fields in base_context to avoid duplication
            if chapter_id:
                current_chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
                if current_chapter and current_chapter.auto_summary and current_chapter.scenes_count > 0:
                    logger.info(f"[HYBRID CONTEXT] Adding current chapter {current_chapter.chapter_number} summary to _get_chapter_summaries")
                    current_summary_text = f"Current Chapter Summary (Chapter {current_chapter.chapter_number}):\n{current_chapter.auto_summary}"
                    current_summary_tokens = self.count_tokens(current_summary_text)
                    if used_tokens + current_summary_tokens <= token_budget:
                        summary_parts.append(current_summary_text)
                        used_tokens += current_summary_tokens
                else:
                    logger.info(f"[HYBRID CONTEXT] Not adding current chapter summary (chapter_id={chapter_id}, has_auto_summary={current_chapter.auto_summary if current_chapter else False}, scenes_count={current_chapter.scenes_count if current_chapter else 0})")

            # No fallback - if no current chapter summary exists, return None
            # Historical context is already provided by "Story So Far" and "Previous Chapter Summary" direct fields
            if summary_parts:
                result = "\n\n".join(summary_parts)
                logger.info(f"[HYBRID CONTEXT] _get_chapter_summaries returning {len(summary_parts)} parts: {[part[:50] + '...' if len(part) > 50 else part for part in summary_parts]}")
                # Verify we're not accidentally including story_so_far or previous_chapter_summary
                if "Story So Far:" in result:
                    logger.error("[HYBRID CONTEXT] ERROR: story_so_far found in _get_chapter_summaries result! This should not happen.")
                if "Previous Chapter Summary" in result:
                    logger.error("[HYBRID CONTEXT] ERROR: previous_chapter_summary found in _get_chapter_summaries result! This should not happen.")
                return result

            logger.info("[HYBRID CONTEXT] _get_chapter_summaries returning None (no summaries)")
            return None

        except Exception as e:
            logger.error(f"Failed to get chapter summaries: {e}")
            return None

    async def _get_entity_states(
        self,
        story_id: int,
        token_budget: int,
        db: Session,
        current_scene_sequence: Optional[int] = None,
        branch_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Get formatted entity states for context.

        Args:
            story_id: Story ID
            token_budget: Available tokens
            db: Database session
            current_scene_sequence: Current scene sequence for filtering
            branch_id: Optional branch ID for filtering

        Returns:
            Formatted entity states or None
        """
        try:
            from ..models import CharacterState, LocationState, ObjectState

            # Get all entity states for this story (filtered by branch)
            # Order by updated_at DESC to ensure we get the latest states
            # (though typically there's one state per entity, ordering ensures we get most recent if duplicates exist)

            # First try to get states for specific branch
            char_state_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            if branch_id:
                char_state_query = char_state_query.filter(CharacterState.branch_id == branch_id)
            # Add secondary sort by id for deterministic ordering (cache stability)
            character_states = char_state_query.order_by(CharacterState.updated_at.desc(), CharacterState.id.asc()).all()

            loc_state_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            if branch_id:
                loc_state_query = loc_state_query.filter(LocationState.branch_id == branch_id)
            location_states = loc_state_query.order_by(LocationState.updated_at.desc(), LocationState.id.asc()).all()

            obj_state_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id:
                obj_state_query = obj_state_query.filter(ObjectState.branch_id == branch_id)
            object_states = obj_state_query.order_by(ObjectState.updated_at.desc(), ObjectState.id.asc()).all()

            if not character_states and not location_states and not object_states:
                return None

            # Deduplicate: keep only most recent state per entity (ordered by updated_at DESC)
            if character_states:
                seen_chars = set()
                deduped = []
                for cs in character_states:
                    if cs.character_id not in seen_chars:
                        seen_chars.add(cs.character_id)
                        deduped.append(cs)
                character_states = deduped

            if location_states:
                seen_locs = set()
                deduped = []
                for ls in location_states:
                    if ls.location_name not in seen_locs:
                        seen_locs.add(ls.location_name)
                        deduped.append(ls)
                location_states = deduped

            if object_states:
                seen_objs = set()
                deduped = []
                for os_item in object_states:
                    if os_item.object_name not in seen_objs:
                        seen_objs.add(os_item.object_name)
                        deduped.append(os_item)
                object_states = deduped

            # Format entity states
            entity_parts = []
            used_tokens = 0

            # Character States
            # Filter to only show characters with recent state updates
            if character_states:
                # Filter character states by recency (only show if updated recently)
                filtered_char_states = []
                for char_state in character_states:
                    # Include if updated recently OR if it's a main character (always show main characters)
                    include = True
                    if current_scene_sequence is not None and char_state.last_updated_scene is not None:
                        # Skip entity states that reference scenes beyond current branch's range
                        if char_state.last_updated_scene > current_scene_sequence:
                            include = False  # Scene doesn't exist in current branch context
                        else:
                            scene_age = current_scene_sequence - char_state.last_updated_scene
                            # Only include if updated within recency window (or if main character)
                            if scene_age > self.location_recency_window:
                                # Still include if it's likely a main character (has significant state)
                                # Include appearance to prevent filtering out clothing/attire
                                if not (char_state.current_goal or char_state.possessions or
                                       char_state.appearance or
                                       (char_state.knowledge and len(char_state.knowledge) > 0)):
                                    include = False

                    if include:
                        filtered_char_states.append(char_state)

                if filtered_char_states:
                    entity_parts.append("CURRENT CHARACTER STATES:")
                    for char_state in filtered_char_states:
                        # Get character name
                        character = db.query(Character).filter(
                            Character.id == char_state.character_id
                        ).first()

                        if not character:
                            continue

                        char_text = f"\n{character.name}:"

                        # Only show location if it's recent (within recency window)
                        show_location = True
                        if current_scene_sequence is not None and char_state.last_updated_scene is not None:
                            scene_age = current_scene_sequence - char_state.last_updated_scene
                            if scene_age > self.location_recency_window:
                                show_location = False  # Location is outdated

                        # Helper: treat literal "null" strings as None
                        def _val(v):
                            return v if v and not (isinstance(v, str) and v.lower() == "null") else None

                        loc = _val(char_state.current_location)
                        if loc and show_location:
                            char_text += f"\n  Location: {loc}"
                        elif loc:
                            logger.debug(f"[ENTITY STATES] Skipping outdated location for {character.name} (last updated scene {char_state.last_updated_scene}, current {current_scene_sequence})")

                        # Current position (sub-room arrangement)
                        pos = _val(char_state.current_position)
                        if pos and show_location:
                            char_text += f"\n  Position: {pos}"

                        # Items in hand
                        if char_state.items_in_hand and len(char_state.items_in_hand) > 0:
                            items_str = ", ".join(char_state.items_in_hand)
                            char_text += f"\n  Holding: {items_str}"

                        if _val(char_state.emotional_state):
                            # Sort emotional state attributes for deterministic cache-friendly ordering
                            emo_attrs = [a.strip() for a in char_state.emotional_state.split(',')]
                            emo_sorted = ', '.join(sorted(emo_attrs))
                            char_text += f"\n  Emotional State: {emo_sorted}"

                        if _val(char_state.physical_condition):
                            # Sort physical condition attributes for deterministic cache-friendly ordering
                            phys_attrs = [a.strip() for a in char_state.physical_condition.split(',')]
                            phys_sorted = ', '.join(sorted(phys_attrs))
                            char_text += f"\n  Physical Condition: {phys_sorted}"

                        if _val(char_state.appearance):
                            char_text += f"\n  Current Attire: {char_state.appearance}"

                        if char_state.current_goal:
                            char_text += f"\n  Current Goal: {char_state.current_goal}"

                        if char_state.possessions:
                            possessions_str = ", ".join(char_state.possessions[:5])  # Limit to 5
                            char_text += f"\n  Possessions: {possessions_str}"

                        if char_state.knowledge and len(char_state.knowledge) > 0:
                            # Show most recent 3 knowledge items
                            recent_knowledge = char_state.knowledge[-3:]
                            char_text += f"\n  Recent Knowledge: {'; '.join(recent_knowledge)}"

                        # Relationships (show top 3 most relevant)
                        if char_state.relationships:
                            char_text += f"\n  Key Relationships:"
                            count = 0
                            for rel_char, rel_data in char_state.relationships.items():
                                if count >= 3:
                                    break
                                if isinstance(rel_data, dict):
                                    status = rel_data.get('status', 'unknown')
                                    trust = rel_data.get('trust', 'unknown')
                                    char_text += f"\n    - {rel_char}: {status} (trust: {trust}/10)"
                                count += 1

                        # Check token budget
                        char_tokens = self.count_tokens(char_text)
                        if used_tokens + char_tokens > token_budget:
                            break

                        entity_parts.append(char_text)
                        used_tokens += char_tokens

            # Location States (if tokens available)
            # Filter to only show CURRENT locations (recently updated or with current occupants)
            if location_states and used_tokens < token_budget * 0.8:
                # Filter locations by recency and current occupants
                current_locations = []
                recent_locations = []

                for loc_state in location_states:
                    is_current = False

                    # Skip entity states that reference scenes beyond current branch's range
                    if current_scene_sequence is not None and loc_state.last_updated_scene is not None:
                        if loc_state.last_updated_scene > current_scene_sequence:
                            continue  # Scene doesn't exist in current branch context

                    # Check if location was updated recently (within recency window)
                    if current_scene_sequence is not None and loc_state.last_updated_scene is not None:
                        scene_age = current_scene_sequence - loc_state.last_updated_scene
                        if scene_age <= self.location_recency_window:
                            is_current = True

                    # Check if location has current occupants (active location)
                    if loc_state.current_occupants and len(loc_state.current_occupants) > 0:
                        is_current = True

                    if is_current:
                        current_locations.append(loc_state)
                    else:
                        recent_locations.append(loc_state)

                # Prioritize current locations, then recent ones
                filtered_locations = current_locations + recent_locations[:2]  # Max 2 recent for context

                if filtered_locations:
                    # Separate current vs recent for clarity
                    if current_locations:
                        entity_parts.append("\n\nCURRENT LOCATIONS:")
                        for loc_state in current_locations[:1]:  # Show only the PRIMARY current location
                            loc_text = f"\n{loc_state.location_name}:"

                            if loc_state.condition:
                                loc_text += f"\n  Condition: {loc_state.condition}"

                            if loc_state.atmosphere:
                                loc_text += f"\n  Atmosphere: {loc_state.atmosphere}"

                            if loc_state.current_occupants:
                                occupants_str = ", ".join(loc_state.current_occupants[:5])
                                loc_text += f"\n  Present: {occupants_str}"

                            loc_tokens = self.count_tokens(loc_text)
                            if used_tokens + loc_tokens > token_budget:
                                break

                            entity_parts.append(loc_text)
                            used_tokens += loc_tokens

                    # Show additional recent locations if space and they're relevant
                    if recent_locations and used_tokens < token_budget * 0.9:
                        entity_parts.append("\n\nRECENT LOCATIONS (for context):")
                        for loc_state in recent_locations[:2]:  # Max 2 recent locations
                            loc_text = f"\n{loc_state.location_name}:"

                            if loc_state.condition:
                                loc_text += f"\n  Condition: {loc_state.condition}"

                            if loc_state.atmosphere:
                                loc_text += f"\n  Atmosphere: {loc_state.atmosphere}"

                            if loc_state.current_occupants:
                                occupants_str = ", ".join(loc_state.current_occupants[:5])
                                loc_text += f"\n  Present: {occupants_str}"

                            loc_tokens = self.count_tokens(loc_text)
                            if used_tokens + loc_tokens > token_budget:
                                break

                            entity_parts.append(loc_text)
                            used_tokens += loc_tokens

            # Object States (if tokens available)
            # STRICT FILTERING: Only include objects that are highly relevant to current scene
            # This prevents LLM fixation on objects mentioned long ago
            if object_states and used_tokens < token_budget * 0.9:
                # Collect current character locations for location-based object matching
                current_character_locations = set()

                # Get locations from character states
                for char_state in character_states:
                    if char_state.current_location:
                        current_character_locations.add(char_state.current_location.lower())

                # Also add current locations from location states (those with occupants)
                for loc_state in location_states:
                    if loc_state.current_occupants and len(loc_state.current_occupants) > 0:
                        if loc_state.location_name:
                            current_character_locations.add(loc_state.location_name.lower())

                # Apply STRICT object filtering - must meet at least one criterion:
                # 1. Currently owned/held by a character
                # 2. Updated in the last 3 scenes (very recent interaction)
                # 3. In the same location where characters are currently present
                OBJECT_RECENCY_WINDOW = 3  # Much tighter than general recency window
                filtered_objects = []

                for obj_state in object_states:
                    include = False
                    include_reason = None

                    # Skip entity states that reference scenes beyond current branch's range
                    if current_scene_sequence is not None and obj_state.last_updated_scene is not None:
                        if obj_state.last_updated_scene > current_scene_sequence:
                            continue  # Scene doesn't exist in current branch context

                    # Criterion 1: Currently owned/held by a character (highest priority)
                    if obj_state.current_owner_id:
                        include = True
                        include_reason = "owned"

                    # Criterion 2: Updated very recently (within 3 scenes)
                    elif current_scene_sequence is not None and obj_state.last_updated_scene is not None:
                        scene_age = current_scene_sequence - obj_state.last_updated_scene
                        if scene_age <= OBJECT_RECENCY_WINDOW:
                            include = True
                            include_reason = f"recent (age={scene_age})"

                    # Criterion 3: In the same location as current characters
                    if not include and obj_state.current_location:
                        obj_location_lower = obj_state.current_location.lower()
                        if obj_location_lower in current_character_locations:
                            include = True
                            include_reason = "same_location"

                    if include:
                        filtered_objects.append((obj_state, include_reason))
                        logger.debug(f"[ENTITY STATES] Including object '{obj_state.object_name}': {include_reason}")

                # Limit to 3 most relevant objects
                filtered_objects = filtered_objects[:3]

                if filtered_objects:
                    entity_parts.append("\n\nActive Objects:")
                    for obj_state, reason in filtered_objects:
                        # Minimal format to reduce object prominence
                        # Just name + owner OR location, no condition/significance
                        if obj_state.current_owner_id and db:
                            try:
                                owner = db.query(Character).filter(Character.id == obj_state.current_owner_id).first()
                                if owner:
                                    obj_text = f"\n- {obj_state.object_name} (held by {owner.name})"
                                else:
                                    obj_text = f"\n- {obj_state.object_name}"
                            except Exception as e:
                                logger.warning(f"Failed to fetch owner for object {obj_state.object_name}: {e}")
                                obj_text = f"\n- {obj_state.object_name}"
                        elif obj_state.current_location:
                            obj_text = f"\n- {obj_state.object_name} (in {obj_state.current_location})"
                        else:
                            obj_text = f"\n- {obj_state.object_name}"

                        obj_tokens = self.count_tokens(obj_text)
                        if used_tokens + obj_tokens > token_budget:
                            break

                        entity_parts.append(obj_text)
                        used_tokens += obj_tokens

                logger.info(f"[ENTITY STATES] Object filtering: {len(object_states)} total -> {len(filtered_objects)} included (char locations: {current_character_locations})")

            if len(entity_parts) > 0:
                return "\n".join(entity_parts)

            return None

        except Exception as e:
            logger.error(f"Failed to get entity states: {e}")
            return None

    async def _load_entity_states_snapshot(
        self,
        db: Session,
        scene_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Load context snapshot from the scene's active variant.

        Used during variant regeneration to ensure cache consistency by using
        the exact same context (entity states, story_focus)
        that was present when the scene was generated.

        Args:
            db: Database session
            scene_id: Scene ID to load snapshot for

        Returns:
            Dict with snapshot fields (entity_states_text, story_focus)
            or None if no snapshot available. Falls back to legacy entity_states_snapshot
            if full context_snapshot is not available.
        """
        try:
            import json as json_lib

            # Get the active variant for this scene from StoryFlow
            flow_entry = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene_id,
                StoryFlow.is_active == True
            ).first()

            if not flow_entry:
                logger.debug(f"[CACHE] No active StoryFlow found for scene {scene_id}")
                return None

            # Get the variant
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == flow_entry.scene_variant_id
            ).first()

            if not variant:
                logger.debug(f"[CACHE] No variant found for scene_variant_id {flow_entry.scene_variant_id}")
                return None

            # Try to load full context_snapshot first (includes story_focus, relationship_context)
            # context_snapshot may be a prompt snapshot ({"v": 2, ...}) or entity states dict — skip the former
            if variant.context_snapshot:
                try:
                    snapshot = json_lib.loads(variant.context_snapshot)
                    if isinstance(snapshot, dict) and "v" not in snapshot:
                        # Entity states dict (no version key)
                        logger.info(f"[CACHE] Loaded full context_snapshot from variant {variant.id}: "
                                   f"entity_states={len(snapshot.get('entity_states_text', '') or '')} chars, "
                                   f"story_focus={'yes' if snapshot.get('story_focus') else 'no'}, "
                                   f"relationship_context={'yes' if snapshot.get('relationship_context') else 'no'}")
                        return snapshot
                    # else: prompt snapshot — skip, not entity states
                except json_lib.JSONDecodeError as e:
                    logger.warning(f"[CACHE] Failed to parse context_snapshot JSON for variant {variant.id}: {e}")

            # Fall back to legacy entity_states_snapshot
            if variant.entity_states_snapshot:
                logger.info(f"[CACHE] Using legacy entity_states_snapshot from variant {variant.id} ({len(variant.entity_states_snapshot)} chars)")
                return {"entity_states_text": variant.entity_states_snapshot}

            logger.debug(f"[CACHE] Variant {variant.id} has no snapshot (scene {scene_id})")
            return None

        except Exception as e:
            logger.warning(f"[CACHE] Failed to load snapshot for scene {scene_id}: {e}")
            return None

    async def _get_interaction_history(
        self,
        story_id: int,
        db: Session,
        branch_id: int = None
    ) -> Optional[str]:
        """
        Get character interaction history for the story.

        This provides a factual record of what interactions have occurred between characters,
        helping the LLM maintain accurate continuity.

        Args:
            story_id: Story ID
            db: Database session
            branch_id: Optional branch ID for filtering

        Returns:
            Formatted interaction history or None
        """
        try:
            from ..models import CharacterInteraction

            # Get story's interaction types configuration
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story or not story.interaction_types:
                logger.info(f"[INTERACTION HISTORY] No interaction_types configured for story {story_id}")
                return None

            logger.info(f"[INTERACTION HISTORY] Story {story_id} has {len(story.interaction_types)} interaction types configured")

            # Get all interactions for this story
            query = db.query(CharacterInteraction).filter(
                CharacterInteraction.story_id == story_id
            )
            if branch_id:
                query = query.filter(CharacterInteraction.branch_id == branch_id)

            # Add secondary sort by id for deterministic ordering (cache stability)
            interactions = query.order_by(
                CharacterInteraction.first_occurrence_scene,
                CharacterInteraction.id.asc()
            ).all()

            logger.info(f"[INTERACTION HISTORY] Found {len(interactions)} interactions for story {story_id} (branch_id={branch_id})")

            if not interactions:
                return None

            # Build character ID to name mapping
            char_ids = set()
            for interaction in interactions:
                char_ids.add(interaction.character_a_id)
                char_ids.add(interaction.character_b_id)

            characters = db.query(Character).filter(Character.id.in_(char_ids)).all()
            char_id_to_name = {c.id: c.name for c in characters}

            # Group interactions by character pair
            pair_interactions = {}
            for interaction in interactions:
                # Create consistent pair key (alphabetically sorted names)
                name_a = char_id_to_name.get(interaction.character_a_id, "Unknown")
                name_b = char_id_to_name.get(interaction.character_b_id, "Unknown")
                pair_key = tuple(sorted([name_a, name_b]))

                if pair_key not in pair_interactions:
                    pair_interactions[pair_key] = []
                pair_interactions[pair_key].append({
                    "type": interaction.interaction_type,
                    "scene": interaction.first_occurrence_scene,
                    "description": interaction.description
                })

            # Format output — compact: type + scene number only, no descriptions
            parts = ["CHARACTER INTERACTION HISTORY:"]
            parts.append("")

            for (name_a, name_b), interactions_list in pair_interactions.items():
                parts.append(f"{name_a} & {name_b}:")
                for interaction in interactions_list:
                    parts.append(f"  - {interaction['type']} (scene {interaction['scene']})")
                parts.append("")

            # Add note about what hasn't happened
            configured_types = set(story.interaction_types)
            occurred_types = {i.interaction_type for i in interactions}
            not_occurred = configured_types - occurred_types

            if not_occurred:
                parts.append("INTERACTIONS NOT YET OCCURRED:")
                parts.append(f"  {', '.join(sorted(not_occurred))}")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"Failed to get interaction history: {e}")
            return None

    async def _add_recent_scenes_dynamically(
        self,
        scenes: List[Scene],
        min_recent_count: int,
        available_tokens: int,
        db: Session
    ) -> Tuple[str, List[Scene]]:
        """
        Add recent scenes using batch-aligned selection for LLM cache optimization.

        Selects scenes in complete batch units (aligned to scene_batch_size) to maximize
        LLM cache hit rates. Working backward from the most recent scene:
        1. First, include the active batch (current incomplete batch)
        2. Then add complete batches until token budget exhausted

        A batch is only included if ALL its scenes fit. We allow slight overage (~5%)
        to leverage the 10% buffer from token_buffer setting.

        Args:
            scenes: All scenes in chronological order
            min_recent_count: Number of most recent scenes already included (to avoid duplicates)
            available_tokens: Token budget for additional scenes
            db: Database session

        Returns:
            Tuple of (formatted content string, list of included Scene objects)
        """
        if not scenes or available_tokens <= 0:
            return "", []

        batch_size = self.scene_batch_size

        # Build a map of scene sequence numbers to (scene, content, tokens)
        # Only include scenes BEFORE the min_recent_count most recent ones
        # (to avoid duplicating scenes already in recent_scenes)
        scene_map: Dict[int, Tuple[Scene, str, int]] = {}

        # scenes list is chronological (oldest → newest)
        # Exclude the last min_recent_count scenes
        scenes_to_consider = scenes[:-min_recent_count] if min_recent_count > 0 else scenes

        if not scenes_to_consider:
            return "", []

        for scene in scenes_to_consider:
            scene_content = await self._get_scene_content_proper(scene, db)
            scene_tokens = self.count_tokens(scene_content)
            scene_map[scene.sequence_number] = (scene, scene_content, scene_tokens)

        if not scene_map:
            return "", []

        # Get the highest scene number we're considering (most recent, excluding min_recent_count)
        max_scene_num = max(scene_map.keys())

        # Calculate batch boundaries
        # Active batch: the batch containing the most recent scene we're considering
        active_batch_num = (max_scene_num - 1) // batch_size
        active_batch_start = active_batch_num * batch_size + 1

        # Step 1: Include scenes from the active batch (partial, changes each scene)
        included_scenes = []
        scene_contents = []
        used_tokens = 0

        for seq_num in range(active_batch_start, max_scene_num + 1):
            if seq_num in scene_map:
                scene, content, tokens = scene_map[seq_num]
                included_scenes.append(scene)
                scene_contents.append(content)
                used_tokens += tokens

        logger.debug(f"[HYBRID BATCH FILL] Active batch {active_batch_num} (scenes {active_batch_start}-{max_scene_num}): {len(included_scenes)} scenes, {used_tokens} tokens")

        # Step 2: Work backward through complete batches
        # Allow slight overage (5%) to leverage the 10% buffer from token_buffer
        overage_allowance = int(available_tokens * 0.05)
        effective_limit = available_tokens + overage_allowance

        current_batch_num = active_batch_num - 1

        while current_batch_num >= 0:
            batch_start = current_batch_num * batch_size + 1
            batch_end = batch_start + batch_size - 1

            # Get all scenes in this batch that exist in our map
            batch_scenes = []
            batch_contents = []
            batch_tokens = 0
            batch_complete = True

            for seq_num in range(batch_start, batch_end + 1):
                if seq_num in scene_map:
                    scene, content, tokens = scene_map[seq_num]
                    batch_scenes.append(scene)
                    batch_contents.append(content)
                    batch_tokens += tokens
                else:
                    # Scene doesn't exist in our map - batch is incomplete
                    batch_complete = False

            # Only include complete batches (all scenes from batch_start to batch_end present)
            if not batch_complete or len(batch_scenes) != batch_size:
                logger.debug(f"[HYBRID BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): incomplete ({len(batch_scenes)}/{batch_size} scenes), stopping")
                break

            # Check if adding this complete batch fits within our limit
            if used_tokens + batch_tokens <= effective_limit:
                # Insert at the beginning to maintain chronological order
                included_scenes = batch_scenes + included_scenes
                scene_contents = batch_contents + scene_contents
                used_tokens += batch_tokens
                logger.debug(f"[HYBRID BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): included, {batch_tokens} tokens, total now {used_tokens}")
                current_batch_num -= 1
            else:
                logger.debug(f"[HYBRID BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): would exceed limit ({used_tokens} + {batch_tokens} > {effective_limit}), stopping")
                break

        # Build content from scene_contents (already in chronological order)
        content = "\n\n".join(scene_contents)

        # Log batch alignment info
        if included_scenes:
            first_seq = min(s.sequence_number for s in included_scenes)
            last_seq = max(s.sequence_number for s in included_scenes)
            logger.info(f"[HYBRID BATCH FILL] Final: scenes {first_seq}-{last_seq} ({len(included_scenes)} scenes), {used_tokens}/{available_tokens} tokens, batch_size={batch_size}")
        else:
            logger.info(f"[HYBRID BATCH FILL] No additional scenes included (available_tokens={available_tokens})")

        return content, included_scenes


# Global instance
context_manager = ContextManager()
