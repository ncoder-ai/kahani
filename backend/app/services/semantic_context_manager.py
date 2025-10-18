"""
Semantic Context Manager

Extends the basic ContextManager with semantic search capabilities
for intelligent context retrieval in long-form narratives.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from .context_manager import ContextManager
from .semantic_memory import get_semantic_memory_service
from ..models import Scene, SceneVariant, StoryFlow, Character, StoryCharacter
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
        
        # Load semantic settings
        if user_settings and user_settings.get("semantic_settings"):
            sem_settings = user_settings["semantic_settings"]
            self.enable_semantic = sem_settings.get("enable_semantic_memory", settings.enable_semantic_memory)
            self.semantic_top_k = sem_settings.get("semantic_search_top_k", settings.semantic_search_top_k)
            self.semantic_weight = sem_settings.get("semantic_context_weight", settings.semantic_context_weight)
            self.context_strategy = sem_settings.get("context_strategy", settings.context_strategy)
        else:
            self.enable_semantic = settings.enable_semantic_memory
            self.semantic_top_k = settings.semantic_search_top_k
            self.semantic_weight = settings.semantic_context_weight
            self.context_strategy = settings.context_strategy
        
        # Get semantic memory service
        try:
            self.semantic_memory = get_semantic_memory_service()
            logger.info(f"Semantic memory service available, strategy: {self.context_strategy}")
        except RuntimeError:
            logger.warning("Semantic memory service not initialized, falling back to linear context")
            self.enable_semantic = False
            self.context_strategy = "linear"
    
    async def build_story_context(self, story_id: int, db: Session) -> Dict[str, Any]:
        """
        Build optimized context using hybrid strategy if enabled
        
        Args:
            story_id: Story ID
            db: Database session
            
        Returns:
            Optimized context dictionary
        """
        # If semantic memory is disabled, use parent class method
        if not self.enable_semantic or self.context_strategy == "linear":
            return await super().build_story_context(story_id, db)
        
        # Use hybrid strategy
        return await self._build_hybrid_context(story_id, db)
    
    async def _build_hybrid_context(self, story_id: int, db: Session) -> Dict[str, Any]:
        """
        Build hybrid context combining recent scenes with semantically relevant past
        
        Strategy:
        1. Get base context (genre, tone, characters)
        2. Get recent scenes (immediate context)
        3. Semantic search for relevant past scenes
        4. Get character-specific moments
        5. Get chapter summaries
        6. Assemble within token budget
        """
        from ..models import Story
        
        # Get story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        # Get all scenes ordered by sequence
        scenes = db.query(Scene).filter(
            Scene.story_id == story_id
        ).order_by(Scene.sequence_number).all()
        
        if not scenes:
            # No scenes yet, return base context
            return await self._get_base_context(story_id, db)
        
        # Calculate base context tokens
        base_context = await self._get_base_context(story_id, db)
        base_tokens = self._calculate_base_context_tokens(base_context)
        
        # Available tokens for scene history
        available_tokens = self.max_tokens - base_tokens - 500  # Safety buffer
        
        if available_tokens <= 0:
            logger.warning(f"Base context too large for story {story_id}")
            return base_context
        
        # Build scene context using hybrid strategy
        scene_context = await self._build_hybrid_scene_context(
            story_id, scenes, available_tokens, db
        )
        
        # Merge contexts
        return {**base_context, **scene_context}
    
    async def _build_hybrid_scene_context(
        self,
        story_id: int,
        scenes: List[Scene],
        available_tokens: int,
        db: Session
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
        recent_content = await self._get_scene_content(recent_scenes, db)
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
                "context_type": "recent_only"
            }
        
        # Allocate tokens for different context types
        semantic_tokens = int(remaining_tokens * 0.55)  # 55% for semantic scenes
        character_tokens = int(remaining_tokens * 0.25)  # 25% for character context
        summary_tokens = int(remaining_tokens * 0.20)    # 20% for summaries
        
        # Get semantically relevant scenes
        semantic_content = await self._get_semantic_scenes(
            story_id, recent_scenes, semantic_tokens, db
        )
        
        # Get character-specific context
        character_content = await self._get_character_context(
            story_id, recent_scenes, character_tokens, db
        )
        
        # Get chapter summaries
        summary_content = await self._get_chapter_summaries(
            story_id, summary_tokens, db
        )
        
        # Assemble final context
        context_parts = []
        
        if summary_content:
            context_parts.append(f"Story Summary:\n{summary_content}")
        
        if semantic_content:
            context_parts.append(f"\nRelevant Past Events:\n{semantic_content}")
        
        if character_content:
            context_parts.append(f"\nCharacter Context:\n{character_content}")
        
        context_parts.append(f"\nRecent Scenes:\n{recent_content}")
        
        full_context = "\n".join(context_parts)
        
        return {
            "previous_scenes": full_context,
            "recent_scenes": recent_content,
            "scene_summary": f"Hybrid context: {len(recent_scenes)} recent + semantic retrieval",
            "total_scenes": total_scenes,
            "context_type": "hybrid",
            "semantic_scenes_included": semantic_content is not None,
            "character_context_included": character_content is not None
        }
    
    async def _get_base_context(self, story_id: int, db: Session) -> Dict[str, Any]:
        """Get base story context (genre, tone, characters)"""
        from ..models import Story
        
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return {}
        
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
        
        return {
            "story_id": story_id,
            "title": story.title,
            "genre": story.genre,
            "tone": story.tone,
            "world_setting": story.world_setting,
            "initial_premise": story.initial_premise,
            "characters": characters
        }
    
    async def _get_scene_content(self, scenes: List[Scene], db: Session) -> str:
        """Get content for scenes using active variants"""
        content_parts = []
        
        for scene in scenes:
            # Get active variant from StoryFlow
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            ).first()
            
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
        db: Session
    ) -> Optional[str]:
        """
        Get semantically relevant scenes from the past
        
        Args:
            story_id: Story ID
            recent_scenes: Recent scenes to use as query
            token_budget: Available tokens
            db: Database session
            
        Returns:
            Formatted string of relevant scenes or None
        """
        if not recent_scenes:
            return None
        
        try:
            # Use the most recent scene as query
            last_scene = recent_scenes[-1]
            
            # Get active variant content
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == last_scene.id,
                StoryFlow.is_active == True
            ).first()
            
            query_content = flow.scene_variant.content if flow and flow.scene_variant else last_scene.content
            
            if not query_content:
                return None
            
            # Get exclude list (recent scene sequences)
            exclude_sequences = [s.sequence_number for s in recent_scenes]
            
            # Search for similar scenes
            similar_scenes = await self.semantic_memory.search_similar_scenes(
                query_text=query_content,
                story_id=story_id,
                top_k=self.semantic_top_k,
                exclude_sequences=exclude_sequences
            )
            
            if not similar_scenes:
                return None
            
            # Get scene content within token budget
            relevant_parts = []
            used_tokens = 0
            
            for result in similar_scenes:
                # Get the scene and variant
                scene = db.query(Scene).filter(Scene.id == result['scene_id']).first()
                if not scene:
                    continue
                
                variant = db.query(SceneVariant).filter(SceneVariant.id == result['variant_id']).first()
                if not variant:
                    continue
                
                scene_text = f"[Relevant from Scene {scene.sequence_number}, similarity: {result['similarity_score']:.2f}]: {variant.content[:300]}..."
                scene_tokens = self.count_tokens(scene_text)
                
                if used_tokens + scene_tokens <= token_budget:
                    relevant_parts.append(scene_text)
                    used_tokens += scene_tokens
                else:
                    break
            
            if relevant_parts:
                return "\n\n".join(relevant_parts)
            
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
        db: Session
    ) -> Optional[str]:
        """
        Get chapter summaries for compressed history
        
        Args:
            story_id: Story ID
            token_budget: Available tokens
            db: Database session
            
        Returns:
            Formatted chapter summaries or None
        """
        from ..models import Chapter
        
        if token_budget < 200:
            return None
        
        try:
            # Get completed chapters with summaries
            chapters = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.auto_summary.isnot(None)
            ).order_by(Chapter.chapter_number).all()
            
            if not chapters:
                return None
            
            summary_parts = []
            used_tokens = 0
            
            for chapter in chapters:
                summary_text = f"Chapter {chapter.chapter_number} ({chapter.title or 'Untitled'}): {chapter.auto_summary}"
                summary_tokens = self.count_tokens(summary_text)
                
                if used_tokens + summary_tokens <= token_budget:
                    summary_parts.append(summary_text)
                    used_tokens += summary_tokens
                else:
                    # Include at least part of the summary
                    remaining_budget = token_budget - used_tokens
                    if remaining_budget > 100:
                        truncated = summary_text[:remaining_budget * 4]  # Rough char estimate
                        summary_parts.append(truncated + "...")
                    break
            
            if summary_parts:
                return "\n\n".join(summary_parts)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chapter summaries: {e}")
            return None


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

