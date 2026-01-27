"""
Semantic Context Manager

Extends the basic ContextManager with semantic search capabilities
for intelligent context retrieval in long-form narratives.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from sqlalchemy import and_, or_
from .context_manager import ContextManager
from .semantic_memory import get_semantic_memory_service
from ..models import Scene, SceneVariant, StoryFlow, Character, StoryCharacter, ChapterStatus, StoryBranch
from ..config import settings

logger = logging.getLogger(__name__)


class SemanticContextManager(ContextManager):
    """
    Enhanced context manager with semantic search capabilities
    
    Features:
    - Hybrid context assembly (recent + semantically relevant)
    - Character-aware context retrieval
    - Plot thread continuity
    - Token-efficient context selection
    """
    
    def __init__(self, max_tokens: int = None, user_settings: dict = None, user_id: int = 1):
        """
        Initialize semantic context manager
        
        Args:
            max_tokens: Maximum tokens for context
            user_settings: User-specific settings
            user_id: User ID for LLM calls
        """
        super().__init__(max_tokens, user_settings, user_id)
        
        # Load semantic settings from user context_settings (now includes semantic options)
        if user_settings and user_settings.get("context_settings"):
            ctx_settings = user_settings["context_settings"]
            self.enable_semantic = ctx_settings.get("enable_semantic_memory", settings.enable_semantic_memory)
            self.semantic_top_k = ctx_settings.get("semantic_search_top_k", settings.semantic_search_top_k)
            self.semantic_scenes_in_context = ctx_settings.get("semantic_scenes_in_context", settings.semantic_scenes_in_context)
            self.semantic_weight = ctx_settings.get("semantic_context_weight", settings.semantic_context_weight)
            self.character_moments_in_context = ctx_settings.get("character_moments_in_context", settings.character_moments_in_context)
            self.context_strategy = ctx_settings.get("context_strategy", settings.context_strategy)
            self.auto_extract_character_moments = ctx_settings.get("auto_extract_character_moments", settings.auto_extract_character_moments)
            self.auto_extract_plot_events = ctx_settings.get("auto_extract_plot_events", settings.auto_extract_plot_events)
            self.extraction_confidence_threshold = ctx_settings.get("extraction_confidence_threshold", settings.extraction_confidence_threshold)
            # New settings for filtering
            self.semantic_min_similarity = ctx_settings.get("semantic_min_similarity", getattr(settings, "semantic_min_similarity", 0.3))
            self.location_recency_window = ctx_settings.get("location_recency_window", getattr(settings, "location_recency_window", 10))
            # Fill remaining context setting (default True for backwards compatibility)
            self.fill_remaining_context = ctx_settings.get("fill_remaining_context", True)
        else:
            # Fallback to global settings
            self.enable_semantic = settings.enable_semantic_memory
            self.semantic_top_k = settings.semantic_search_top_k
            self.semantic_scenes_in_context = settings.semantic_scenes_in_context
            self.semantic_weight = settings.semantic_context_weight
            self.character_moments_in_context = settings.character_moments_in_context
            self.context_strategy = settings.context_strategy
            self.auto_extract_character_moments = settings.auto_extract_character_moments
            self.auto_extract_plot_events = settings.auto_extract_plot_events
            self.extraction_confidence_threshold = settings.extraction_confidence_threshold
            # New settings for filtering
            self.semantic_min_similarity = getattr(settings, "semantic_min_similarity", 0.3)
            self.location_recency_window = getattr(settings, "location_recency_window", 10)
            # Fill remaining context setting (default True for backwards compatibility)
            self.fill_remaining_context = True
        
        # Get semantic memory service
        try:
            self.semantic_memory = get_semantic_memory_service()
            logger.info(f"Semantic memory service available, strategy: {self.context_strategy}")
        except RuntimeError:
            logger.warning("Semantic memory service not initialized, falling back to linear context")
            self.enable_semantic = False
            self.context_strategy = "linear"
    
    async def build_story_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None, user_intent: Optional[str] = None) -> Dict[str, Any]:
        """
        Build optimized context using hybrid strategy if enabled

        Args:
            story_id: Story ID
            db: Database session
            chapter_id: Optional chapter ID to separate active/inactive characters
            exclude_scene_id: Optional scene ID to exclude from context (for regeneration)
            branch_id: Optional branch ID (if not provided, uses active branch)
            user_intent: Optional user's continue option/custom prompt to influence semantic search

        Returns:
            Optimized context dictionary
        """
        # If semantic memory is disabled, use parent class method
        if not self.enable_semantic or self.context_strategy == "linear":
            return await super().build_story_context(story_id, db, chapter_id=chapter_id, exclude_scene_id=exclude_scene_id, branch_id=branch_id)

        # Use hybrid strategy
        return await self._build_hybrid_context(story_id, db, chapter_id=chapter_id, exclude_scene_id=exclude_scene_id, branch_id=branch_id, user_intent=user_intent)

    async def _build_hybrid_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, exclude_scene_id: Optional[int] = None, branch_id: Optional[int] = None, user_intent: Optional[str] = None) -> Dict[str, Any]:
        """
        Build hybrid context combining recent scenes with semantically relevant past

        Args:
            user_intent: User's continue option - influences which past scenes are retrieved

        Strategy:
        1. Get base context (genre, tone, characters)
        2. Get recent scenes (immediate context)
        3. Semantic search for relevant past scenes
        4. Get character-specific moments
        5. Get chapter summaries
        6. Assemble within token budget
        
        Args:
            story_id: Story ID
            db: Database session
            chapter_id: Optional chapter ID to separate active/inactive characters
            exclude_scene_id: Optional scene ID to exclude from context (for regeneration)
            branch_id: Optional branch ID (if not provided, uses active branch)
        """
        from ..models import Story
        
        # Get story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # If exclude_scene_id is provided, use same logic as new scene generation
        # Get all scenes from chapters 1 through the EXCLUDED SCENE's chapter, then exclude that scene
        if exclude_scene_id:
            # Get the scene being excluded
            excluded_scene = db.query(Scene).filter(Scene.id == exclude_scene_id).first()
            if excluded_scene and excluded_scene.chapter_id:
                # Use the EXCLUDED SCENE's chapter to determine context range
                # This ensures we include all chapters up to and including the scene's actual chapter,
                # regardless of which chapter is marked as "active"
                from ..models import Chapter
                scene_chapter = db.query(Chapter).filter(Chapter.id == excluded_scene.chapter_id).first()
                
                if scene_chapter:
                    # Include scenes from all chapters with chapter_number <= scene's chapter number
                    scene_query = db.query(Scene).join(Chapter).filter(
                        Scene.story_id == story_id,
                        Scene.is_deleted == False,
                        Chapter.chapter_number <= scene_chapter.chapter_number,
                        Scene.id != exclude_scene_id  # Exclude the specific scene
                    )
                    if branch_id:
                        scene_query = scene_query.filter(Scene.branch_id == branch_id)
                    scenes = scene_query.order_by(Scene.sequence_number).all()
                    logger.info(f"[SEMANTIC CONTEXT BUILD] Scene {exclude_scene_id} is in Chapter {scene_chapter.chapter_number}: Including scenes from chapters 1-{scene_chapter.chapter_number}, excluding scene {exclude_scene_id} ({len(scenes)} scenes)")
                else:
                    # Fallback: if chapter not found, get all scenes except excluded one
                    scene_query = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.is_deleted == False,
                        Scene.id != exclude_scene_id
                    )
                    if branch_id:
                        scene_query = scene_query.filter(Scene.branch_id == branch_id)
                    scenes = scene_query.order_by(Scene.sequence_number).all()
                    logger.warning(f"[SEMANTIC CONTEXT BUILD] Scene {exclude_scene_id}'s chapter not found, using all scenes except it ({len(scenes)} scenes)")
            else:
                # Scene not found or has no chapter - fall back to simple exclusion
                scene_query = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False,
                    Scene.id != exclude_scene_id
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.info(f"[SEMANTIC CONTEXT BUILD] Excluding scene {exclude_scene_id}, using {len(scenes)} scenes")
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
                    Scene.is_deleted == False,
                    Chapter.chapter_number <= active_chapter.chapter_number
                )
                if branch_id:
                    scene_query = scene_query.filter(Scene.branch_id == branch_id)
                scenes = scene_query.order_by(Scene.sequence_number).all()
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter_id} (Chapter {active_chapter.chapter_number}): Including scenes from chapters 1-{active_chapter.chapter_number} ({len(scenes)} scenes)")
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
                logger.warning(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter_id} not found, falling back to chapter_id filter only")
            
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
            # No scenes yet, return base context
            return await self._get_base_context(story_id, db, chapter_id=chapter_id, branch_id=branch_id)
        
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
            story_id, scenes, available_tokens, db, chapter_id=chapter_id, branch_id=branch_id, user_intent=user_intent
        )

        # Add story focus (working memory + active plot threads)
        try:
            story_focus = self._build_story_focus(db, story_id, branch_id)
            if story_focus:
                base_context["story_focus"] = story_focus
        except Exception as e:
            logger.warning(f"[SEMANTIC CONTEXT BUILD] Failed to build story focus: {e}")

        # Add relationship context (character relationship arcs)
        try:
            current_seq = None
            if scenes:
                current_seq = max(s.sequence_number for s in scenes if s.sequence_number) if scenes else None

            relationship_context = self._build_relationship_context(db, story_id, branch_id, current_seq)
            if relationship_context:
                base_context["relationship_context"] = relationship_context
        except Exception as e:
            logger.warning(f"[SEMANTIC CONTEXT BUILD] Failed to build relationship context: {e}")

        # Add contradiction context (unresolved continuity warnings)
        try:
            contradiction_context = self._build_contradiction_context(db, story_id, branch_id)
            if contradiction_context:
                base_context["contradiction_context"] = contradiction_context
        except Exception as e:
            logger.warning(f"[SEMANTIC CONTEXT BUILD] Failed to build contradiction context: {e}")

        # Merge contexts
        return {**base_context, **scene_context}

    async def _build_hybrid_scene_context(
        self,
        story_id: int,
        scenes: List[Scene],
        available_tokens: int,
        db: Session,
        chapter_id: Optional[int] = None,
        limit_semantic_to_chapter: bool = False,
        branch_id: Optional[int] = None,
        user_intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build scene context using hybrid retrieval strategy
        
        Token allocation:
        - Recent scenes: 40% of available tokens
        - Semantically relevant scenes: 35% of available tokens
        - Character moments: 15% of available tokens
        - Chapter summaries: 10% of available tokens
        """
        total_scenes = len(scenes)
        
        # Get recent scenes (last N scenes)
        recent_scenes = scenes[-self.keep_recent_scenes:]
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
            logger.info(f"[SEMANTIC CONTEXT] Excluding {len(all_recent_scene_sequences)} scenes from semantic search (recent: {len(recent_scenes)}, additional: {len(estimated_additional_scenes)})")
        else:
            logger.info(f"[SEMANTIC CONTEXT] Fill remaining context disabled - excluding only {len(recent_scenes)} recent scenes from semantic search")

        # Remove duplicates and sort for clarity
        all_recent_scene_sequences = sorted(set(all_recent_scene_sequences))
        
        semantic_tokens = int(remaining_tokens * 0.25)
        character_tokens = int(remaining_tokens * 0.15)
        entity_tokens = int(remaining_tokens * 0.05)
        summary_tokens = int(remaining_tokens * 0.05)
        
        # Get semantically relevant scenes first (top N from user settings)
        # Pass complete exclusion list so we don't duplicate scenes already in Recent Scenes
        # If limit_semantic_to_chapter is True, only search within current chapter (for context size calculation)
        semantic_content = await self._get_semantic_scenes(
            story_id, recent_scenes, semantic_tokens, db,
            exclude_all_recent_sequences=all_recent_scene_sequences,
            limit_to_chapter_id=chapter_id if limit_semantic_to_chapter else None,
            branch_id=branch_id,
            user_intent=user_intent
        )
        semantic_used_tokens = self.count_tokens(semantic_content) if semantic_content else 0
        
        # Get character-specific context
        character_content = await self._get_character_context(
            story_id, recent_scenes, character_tokens, db
        )
        character_used_tokens = self.count_tokens(character_content) if character_content else 0
        
        # Get entity states - pass current scene sequence for filtering
        current_scene_sequence = scenes[-1].sequence_number if scenes else None
        entity_states_content = await self._get_entity_states(
            story_id, entity_tokens, db, current_scene_sequence=current_scene_sequence, branch_id=branch_id
        )
        entity_used_tokens = self.count_tokens(entity_states_content) if entity_states_content else 0
        
        # Get character interaction history (stable, updates only on entity extraction)
        interaction_history_content = await self._get_interaction_history(
            story_id, db, branch_id=branch_id
        )
        interaction_used_tokens = self.count_tokens(interaction_history_content) if interaction_history_content else 0
        logger.info(f"[SEMANTIC CONTEXT] Interaction history: {interaction_used_tokens} tokens, included={interaction_history_content is not None}")
        
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
            logger.info(f"[SEMANTIC CONTEXT] Fill remaining context enabled: added {len(additional_recent_scenes)} additional scenes")
        else:
            logger.info(f"[SEMANTIC CONTEXT] Fill remaining context disabled: using only {len(recent_scenes)} recent scenes")

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
            logger.info(f"[SEMANTIC CONTEXT] _get_chapter_summaries returned content ({len(summary_content)} chars): {summary_content[:200]}...")
        else:
            logger.info("[SEMANTIC CONTEXT] _get_chapter_summaries returned None")
        
        # Assemble final context
        context_parts = []
        
        if summary_content:
            # Defensive check: Remove any "Story So Far:" or "Previous Chapter Summary" that might
            # have accidentally been included (they should be in base_context as direct fields)
            filtered_content = summary_content
            
            # Remove "Story So Far:" section (header + all content until next section or end)
            if "Story So Far:" in filtered_content:
                logger.error("[SEMANTIC CONTEXT] ERROR: Found 'Story So Far:' in summary_content! Filtering it out.")
                import re
                # Match "Story So Far:" and everything until "Previous Chapter Summary" or "Current Chapter Summary" or end
                pattern = r'Story So Far:.*?(?=(?:Previous Chapter Summary|Current Chapter Summary|$))'
                filtered_content = re.sub(pattern, '', filtered_content, flags=re.DOTALL)
                filtered_content = filtered_content.strip()
            
            # Remove "Previous Chapter Summary" section (header + all content until next section or end)
            if "Previous Chapter Summary" in filtered_content:
                logger.error("[SEMANTIC CONTEXT] ERROR: Found 'Previous Chapter Summary' in summary_content! Filtering it out.")
                import re
                # Match "Previous Chapter Summary" and everything until "Current Chapter Summary" or end
                pattern = r'Previous Chapter Summary.*?(?=(?:Current Chapter Summary|$))'
                filtered_content = re.sub(pattern, '', filtered_content, flags=re.DOTALL)
                filtered_content = filtered_content.strip()
            
            if filtered_content.strip():
                context_parts.append(f"Story Summary:\n{filtered_content}")
            else:
                logger.info("[SEMANTIC CONTEXT] summary_content was filtered to empty, not adding to context")
        
        # Add interaction history BEFORE Relevant Context for cache optimization
        # (Interaction history is stable - only updates on entity extraction)
        if interaction_history_content:
            context_parts.append(f"\n{interaction_history_content}")
        
        # Build combined "Relevant Context" section (semantic events + entity states)
        # This section is placed immediately before Recent Scenes for maximum recency emphasis
        relevant_context_parts = []
        
        if semantic_content:
            relevant_context_parts.append(f"Relevant Past Events:\n{semantic_content}")
        
        if character_content:
            relevant_context_parts.append(f"Character Context:\n{character_content}")
        
        if entity_states_content:
            relevant_context_parts.append(entity_states_content)
        
        if relevant_context_parts:
            context_parts.append(f"\nRelevant Context:\n" + "\n\n".join(relevant_context_parts))
        
        context_parts.append(f"\nRecent Scenes:\n{combined_recent_content}")
        
        full_context = "\n".join(context_parts)
        
        return {
            "previous_scenes": full_context,
            "recent_scenes": combined_recent_content,  # Include both initial and additional recent scenes
            "scene_summary": "",  # Don't include metadata in prompt - it's debug info only
            "total_scenes": total_scenes,
            "included_scenes": len(recent_scenes) + len(additional_recent_scenes),  # Actual scenes in context
            "context_type": "hybrid",
            "semantic_scenes_included": semantic_content is not None,
            "character_context_included": character_content is not None,
            "entity_states_included": entity_states_content is not None,
            "interaction_history_included": interaction_history_content is not None
        }
    
    async def _get_base_context(self, story_id: int, db: Session, chapter_id: Optional[int] = None, branch_id: Optional[int] = None) -> Dict[str, Any]:
        """Get base story context (genre, tone, characters) with chapter-specific character separation"""
        from ..models import Story
        
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return {}
        
        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        
        # Get story characters (filtered by branch, including NULL branch_id for shared characters)
        char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
        if branch_id:
            char_query = char_query.filter(or_(
                StoryCharacter.branch_id == branch_id,
                StoryCharacter.branch_id.is_(None)
            ))
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
            from ..models import Chapter
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
            
            char_data = {
                "name": character.name,
                "role": sc.role or "",
                "description": character.description or "",
                "personality": ", ".join(character.personality_traits) if character.personality_traits else "",
                "background": character.background or "",
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
            from sqlalchemy import desc
            latest_scene = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.is_deleted == False
            ).order_by(desc(Scene.sequence_number)).first()
            current_scene_sequence = latest_scene.sequence_number if latest_scene else 0
            
            # Get tiered NPCs (active with full details, inactive with brief mention)
            tiered_npcs = npc_service.get_tiered_npcs_for_context(
                db=db,
                story_id=story_id,
                current_scene_sequence=current_scene_sequence,
                chapter_id=chapter_id,
                branch_id=branch_id
            )
            
            active_npc_characters = tiered_npcs.get("active_npcs", [])
            inactive_npc_characters = tiered_npcs.get("inactive_npcs", [])
            
            # Add active NPCs to active characters
            active_characters.extend(active_npc_characters)
            
            # Add inactive NPCs to inactive characters
            inactive_characters.extend(inactive_npc_characters)
            
            logger.info(f"[SEMANTIC CONTEXT BUILD] Added {len(active_npc_characters)} active NPCs and {len(inactive_npc_characters)} inactive NPCs to context")
            if active_npc_characters:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Active NPCs: {[npc.get('name', 'Unknown') for npc in active_npc_characters]}")
            if inactive_npc_characters:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Inactive NPCs: {[npc.get('name', 'Unknown') for npc in inactive_npc_characters]}")
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
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Including chapter_plot guidance")
            
            # Add arc phase details if available
            if hasattr(chapter, 'arc_phase_id') and chapter.arc_phase_id:
                # Get the arc phase from the story
                if story.story_arc:
                    arc_phase = story.get_arc_phase(chapter.arc_phase_id)
                    if arc_phase:
                        base_context["arc_phase"] = arc_phase
                        logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Including arc phase '{arc_phase.get('name', 'Unknown')}'")
            
            # Check if chapter continues from previous (controls summary inclusion)
            continues_from_previous = getattr(chapter, 'continues_from_previous', True)
            
            # Include story_so_far if it exists AND chapter continues from previous
            if chapter.story_so_far and continues_from_previous:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Including story_so_far ({len(chapter.story_so_far)} chars)")
                base_context["story_so_far"] = chapter.story_so_far
            elif chapter.story_so_far and not continues_from_previous:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Excluding story_so_far (continues_from_previous=False)")
            else:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: story_so_far is None")
            
            # Include previous chapter's summary if available AND chapter continues from previous
            if chapter.chapter_number > 1 and continues_from_previous:
                from ..models import Chapter as ChapterModel, ChapterStatus
                previous_chapter = db.query(ChapterModel).filter(
                    ChapterModel.story_id == story_id,
                    ChapterModel.chapter_number == chapter.chapter_number - 1,
                    ChapterModel.auto_summary.isnot(None)
                ).first()
                if previous_chapter and previous_chapter.auto_summary:
                    logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Found previous chapter {previous_chapter.chapter_number} summary ({len(previous_chapter.auto_summary)} chars)")
                    base_context["previous_chapter_summary"] = previous_chapter.auto_summary
                else:
                    logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: No previous chapter summary found (previous_chapter={previous_chapter is not None}, has_auto_summary={previous_chapter.auto_summary if previous_chapter else 'N/A'})")
            elif chapter.chapter_number > 1 and not continues_from_previous:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Excluding previous_chapter_summary (continues_from_previous=False)")
            else:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: First chapter, no previous chapter summary")
            
            # Include current chapter's auto_summary for context on this chapter's progress
            if chapter.auto_summary:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: Including current_chapter_summary ({len(chapter.auto_summary)} chars)")
                base_context["current_chapter_summary"] = chapter.auto_summary
            else:
                logger.info(f"[SEMANTIC CONTEXT BUILD] Chapter {chapter.chapter_number}: current_chapter_summary is None")
        
        return base_context
    
    async def _get_scene_content(self, scenes: List[Scene], db: Session, branch_id: Optional[int] = None) -> str:
        """Get content for scenes using active variants
        
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
    ) -> Optional[str]:
        """
        Get semantically relevant scenes from the past

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
            Formatted string of relevant scenes or None
        """
        if not recent_scenes:
            return None

        try:
            # Build query from: user intent (highest priority) + recent scene content
            query_parts = []

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
                    query_parts.append(scene_content)

            if not query_parts:
                return None

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
                chapter_id=limit_to_chapter_id  # Limit to chapter if specified, otherwise None (entire story)
            )
            
            if not similar_scenes:
                logger.info(f"[SEMANTIC SEARCH] No similar scenes found for story {story_id}")
                return None
            
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
                return None
            
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
            
            # Get scene content within token budget (now using chronologically sorted results)
            relevant_parts = []
            used_tokens = 0
            
            for result, scene in filtered_results_with_scenes:
                variant = db.query(SceneVariant).filter(SceneVariant.id == result['variant_id']).first()
                if not variant:
                    continue
                
                similarity_score = result.get('similarity_score', 0.0)
                scene_text = f"[Relevant from Scene {scene.sequence_number}, similarity: {similarity_score:.2f}]: {variant.content[:300]}..."
                scene_tokens = self.count_tokens(scene_text)
                
                if used_tokens + scene_tokens <= token_budget:
                    relevant_parts.append(scene_text)
                    used_tokens += scene_tokens
                else:
                    break
            
            if relevant_parts:
                logger.info(f"[SEMANTIC SEARCH] Selected {len(relevant_parts)}/{self.semantic_scenes_in_context} semantic scenes (similarity >= {self.semantic_min_similarity}) for story {story_id}")
                return "\n\n".join(relevant_parts)
            
            logger.info(f"[SEMANTIC SEARCH] No scenes fit within token budget after filtering")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get semantic scenes: {e}")
            return None
    
    async def _get_character_context(
        self,
        story_id: int,
        recent_scenes: List[Scene],
        token_budget: int,
        db: Session
    ) -> Optional[str]:
        """
        Get character-specific context
        
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
        Get chapter summaries for compressed history
        
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
        from ..models import Chapter
        
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
                    logger.info(f"[SEMANTIC CONTEXT] Adding current chapter {current_chapter.chapter_number} summary to _get_chapter_summaries")
                    current_summary_text = f"Current Chapter Summary (Chapter {current_chapter.chapter_number}):\n{current_chapter.auto_summary}"
                    current_summary_tokens = self.count_tokens(current_summary_text)
                    if used_tokens + current_summary_tokens <= token_budget:
                        summary_parts.append(current_summary_text)
                        used_tokens += current_summary_tokens
                else:
                    logger.info(f"[SEMANTIC CONTEXT] Not adding current chapter summary (chapter_id={chapter_id}, has_auto_summary={current_chapter.auto_summary if current_chapter else False}, scenes_count={current_chapter.scenes_count if current_chapter else 0})")
            
            # No fallback - if no current chapter summary exists, return None
            # Historical context is already provided by "Story So Far" and "Previous Chapter Summary" direct fields
            if summary_parts:
                result = "\n\n".join(summary_parts)
                logger.info(f"[SEMANTIC CONTEXT] _get_chapter_summaries returning {len(summary_parts)} parts: {[part[:50] + '...' if len(part) > 50 else part for part in summary_parts]}")
                # Verify we're not accidentally including story_so_far or previous_chapter_summary
                if "Story So Far:" in result:
                    logger.error("[SEMANTIC CONTEXT] ERROR: story_so_far found in _get_chapter_summaries result! This should not happen.")
                if "Previous Chapter Summary" in result:
                    logger.error("[SEMANTIC CONTEXT] ERROR: previous_chapter_summary found in _get_chapter_summaries result! This should not happen.")
                return result
            
            logger.info("[SEMANTIC CONTEXT] _get_chapter_summaries returning None (no summaries)")
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
        Get formatted entity states for context
        
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
            from ..models import CharacterState, LocationState, ObjectState, Character
            
            # Get all entity states for this story (filtered by branch)
            # Order by updated_at DESC to ensure we get the latest states
            # (though typically there's one state per entity, ordering ensures we get most recent if duplicates exist)
            
            # First try to get states for specific branch
            char_state_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            if branch_id:
                char_state_query = char_state_query.filter(CharacterState.branch_id == branch_id)
            character_states = char_state_query.order_by(CharacterState.updated_at.desc()).all()
            
            # If no branch-specific states found, fall back to NULL branch_id states (legacy data)
            if branch_id and not character_states:
                logger.info(f"[ENTITY STATES] No character states for branch {branch_id}, falling back to NULL branch_id states")
                character_states = db.query(CharacterState).filter(
                    CharacterState.story_id == story_id,
                    CharacterState.branch_id.is_(None)
                ).order_by(CharacterState.updated_at.desc()).all()
            
            loc_state_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            if branch_id:
                loc_state_query = loc_state_query.filter(LocationState.branch_id == branch_id)
            location_states = loc_state_query.order_by(LocationState.updated_at.desc()).all()
            
            # If no branch-specific states found, fall back to NULL branch_id states (legacy data)
            if branch_id and not location_states:
                logger.info(f"[ENTITY STATES] No location states for branch {branch_id}, falling back to NULL branch_id states")
                location_states = db.query(LocationState).filter(
                    LocationState.story_id == story_id,
                    LocationState.branch_id.is_(None)
                ).order_by(LocationState.updated_at.desc()).all()
            
            obj_state_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id:
                obj_state_query = obj_state_query.filter(ObjectState.branch_id == branch_id)
            object_states = obj_state_query.order_by(ObjectState.updated_at.desc()).all()
            
            # If no branch-specific states found, fall back to NULL branch_id states (legacy data)
            if branch_id and not object_states:
                logger.info(f"[ENTITY STATES] No object states for branch {branch_id}, falling back to NULL branch_id states")
                object_states = db.query(ObjectState).filter(
                    ObjectState.story_id == story_id,
                    ObjectState.branch_id.is_(None)
                ).order_by(ObjectState.updated_at.desc()).all()
            
            if not character_states and not location_states and not object_states:
                return None
            
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
                        
                        if char_state.current_location and show_location:
                            char_text += f"\n  Location: {char_state.current_location}"
                        elif char_state.current_location:
                            # Location exists but is outdated - don't show it to avoid confusion
                            logger.debug(f"[ENTITY STATES] Skipping outdated location for {character.name} (last updated scene {char_state.last_updated_scene}, current {current_scene_sequence})")
                        
                        if char_state.emotional_state:
                            char_text += f"\n  Emotional State: {char_state.emotional_state}"
                        
                        if char_state.physical_condition:
                            char_text += f"\n  Physical Condition: {char_state.physical_condition}"
                        
                        if char_state.appearance:
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
            from ..models import CharacterInteraction, Character, Story
            
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
            
            interactions = query.order_by(
                CharacterInteraction.first_occurrence_scene
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
            
            # Format output
            parts = ["CHARACTER INTERACTION HISTORY:"]
            parts.append("(Factual record of what has occurred between characters)")
            parts.append("")
            
            for (name_a, name_b), interactions_list in pair_interactions.items():
                parts.append(f"{name_a} & {name_b}:")
                for interaction in interactions_list:
                    desc = f" - {interaction['description']}" if interaction['description'] else ""
                    parts.append(f"  - {interaction['type']} (scene {interaction['scene']}){desc}")
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

    async def calculate_actual_context_size(self, story_id: int, chapter_id: int, db: Session) -> int:
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
            
        Returns:
            Total token count of all content in the chapter
        """
        try:
            from ..models import Chapter
            
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                logger.error(f"Chapter {chapter_id} not found")
                return 0
            
            # Build base context (includes chapter summaries)
            base_context = await self._get_base_context(story_id, db, chapter_id=chapter_id)
            base_tokens = self._calculate_base_context_tokens(base_context)
            
            # Add chapter summary tokens
            if base_context.get("story_so_far"):
                base_tokens += self.count_tokens(f"Story So Far:\n{base_context['story_so_far']}")
            if base_context.get("previous_chapter_summary"):
                base_tokens += self.count_tokens(f"Previous Chapter Summary:\n{base_context['previous_chapter_summary']}")
            
            # Add chapter-specific metadata tokens
            if base_context.get("chapter_location"):
                base_tokens += self.count_tokens(f"Chapter Location: {base_context['chapter_location']}")
            if base_context.get("chapter_time_period"):
                base_tokens += self.count_tokens(f"Chapter Time Period: {base_context['chapter_time_period']}")
            if base_context.get("chapter_scenario"):
                base_tokens += self.count_tokens(f"Chapter Scenario: {base_context['chapter_scenario']}")
            
            # Get all scenes from the current chapter that are in the ACTIVE story flow
            # This matches how get_active_scene_count works
            current_chapter_scenes = db.query(Scene).join(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.is_active == True,
                Scene.chapter_id == chapter_id
            ).order_by(Scene.sequence_number).all()
            
            if not current_chapter_scenes:
                # No scenes in current chapter yet - still count base context
                logger.info(f"[CONTEXT SIZE] Calculated total context size for chapter {chapter_id} (semantic, no scenes): {base_tokens} tokens")
                return base_tokens
            
            # Count tokens for ALL scenes in the chapter (not limited by available_tokens)
            # This gives accurate total chapter size for progress tracking
            total_scene_tokens = 0
            for scene in current_chapter_scenes:
                scene_content = await self._get_scene_content_proper(scene, db)
                total_scene_tokens += self.count_tokens(scene_content)
            
            # Total = base context + all scene tokens
            total_tokens = base_tokens + total_scene_tokens
            
            logger.info(f"[CONTEXT SIZE] Calculated total context size for chapter {chapter_id} (semantic): {total_tokens} tokens (base: {base_tokens}, scene_tokens: {total_scene_tokens}, scenes: {len(current_chapter_scenes)})")
            return total_tokens
            
        except Exception as e:
            logger.error(f"Failed to calculate actual context size for chapter {chapter_id}: {e}", exc_info=True)
            # Fallback to parent method
            try:
                return await super().calculate_actual_context_size(story_id, chapter_id, db)
            except Exception as e2:
                logger.error(f"Parent method also failed: {e2}")
                return 0
    
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
        
        logger.debug(f"[SEMANTIC BATCH FILL] Active batch {active_batch_num} (scenes {active_batch_start}-{max_scene_num}): {len(included_scenes)} scenes, {used_tokens} tokens")
        
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
                logger.debug(f"[SEMANTIC BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): incomplete ({len(batch_scenes)}/{batch_size} scenes), stopping")
                break
        
            # Check if adding this complete batch fits within our limit
            if used_tokens + batch_tokens <= effective_limit:
                # Insert at the beginning to maintain chronological order
                included_scenes = batch_scenes + included_scenes
                scene_contents = batch_contents + scene_contents
                used_tokens += batch_tokens
                logger.debug(f"[SEMANTIC BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): included, {batch_tokens} tokens, total now {used_tokens}")
                current_batch_num -= 1
            else:
                logger.debug(f"[SEMANTIC BATCH FILL] Batch {current_batch_num} (scenes {batch_start}-{batch_end}): would exceed limit ({used_tokens} + {batch_tokens} > {effective_limit}), stopping")
                break
        
        # Build content from scene_contents (already in chronological order)
        content = "\n\n".join(scene_contents)
        
        # Log batch alignment info
        if included_scenes:
            first_seq = min(s.sequence_number for s in included_scenes)
            last_seq = max(s.sequence_number for s in included_scenes)
            logger.info(f"[SEMANTIC BATCH FILL] Final: scenes {first_seq}-{last_seq} ({len(included_scenes)} scenes), {used_tokens}/{available_tokens} tokens, batch_size={batch_size}")
        else:
            logger.info(f"[SEMANTIC BATCH FILL] No additional scenes included (available_tokens={available_tokens})")
        
        return content, included_scenes


# Global instance factory
def create_semantic_context_manager(max_tokens: int = None, user_settings: dict = None, user_id: int = 1) -> SemanticContextManager:
    """
    Factory function to create SemanticContextManager instance
    
    Args:
        max_tokens: Maximum tokens for context
        user_settings: User-specific settings
        user_id: User ID
        
    Returns:
        SemanticContextManager instance
    """
    return SemanticContextManager(max_tokens, user_settings, user_id)

