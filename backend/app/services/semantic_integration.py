"""
Semantic Integration Helper

Provides integration functions for semantic memory features
during scene generation and story management.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from .semantic_context_manager import SemanticContextManager, create_semantic_context_manager
from .context_manager import ContextManager
from .semantic_memory import get_semantic_memory_service
from .character_memory_service import get_character_memory_service
from .plot_thread_service import get_plot_thread_service
from ..config import settings
from ..models import Scene, SceneVariant, Story, Chapter

logger = logging.getLogger(__name__)


def get_context_manager_for_user(user_settings: Dict[str, Any], user_id: int) -> ContextManager:
    """
    Get appropriate context manager based on configuration
    
    Args:
        user_settings: User settings dictionary
        user_id: User ID
        
    Returns:
        ContextManager (or SemanticContextManager if enabled)
    """
    # Check if semantic memory is enabled globally
    if not settings.enable_semantic_memory:
        logger.debug("Semantic memory disabled globally, using standard ContextManager")
        return ContextManager(user_settings=user_settings, user_id=user_id)
    
    # Check user-specific settings
    if user_settings and user_settings.get("context_strategy") == "linear":
        logger.debug("User prefers linear context, using standard ContextManager")
        return ContextManager(user_settings=user_settings, user_id=user_id)
    
    # Use semantic context manager
    try:
        logger.debug("Using SemanticContextManager for hybrid context")
        return create_semantic_context_manager(user_settings=user_settings, user_id=user_id)
    except Exception as e:
        logger.warning(f"Failed to create SemanticContextManager, falling back to standard: {e}")
        return ContextManager(user_settings=user_settings, user_id=user_id)


async def process_scene_embeddings(
    scene_id: int,
    variant_id: int,
    story_id: int,
    scene_content: str,
    sequence_number: int,
    chapter_id: Optional[int],
    user_id: int,
    user_settings: Dict[str, Any],
    db: Session
) -> Dict[str, bool]:
    """
    Process semantic embeddings and extractions for a new scene
    
    This function:
    1. Creates scene embedding in vector database
    2. Extracts character moments (if enabled)
    3. Extracts plot events (if enabled)
    4. Updates entity states (characters, locations, objects)
    
    Args:
        scene_id: Scene ID
        variant_id: Variant ID
        story_id: Story ID
        scene_content: Scene content text
        sequence_number: Scene sequence number
        chapter_id: Optional chapter ID
        user_id: User ID
        user_settings: User settings
        db: Database session
        
    Returns:
        Dictionary with success status for each operation
    """
    results = {
        'scene_embedding': False,
        'character_moments': False,
        'plot_events': False,
        'entity_states': False
    }
    
    # Skip if semantic memory is disabled
    if not settings.enable_semantic_memory:
        logger.info("Semantic memory disabled, skipping embeddings")
        return results
    
    try:
        logger.info(f"Starting semantic processing for scene {scene_id}")
        semantic_memory = get_semantic_memory_service()
        logger.info(f"Semantic memory service obtained successfully")
        
        # 1. Create scene embedding
        try:
            logger.info(f"Creating scene embedding for scene {scene_id}")
            embedding_id = await semantic_memory.add_scene_embedding(
                scene_id=scene_id,
                variant_id=variant_id,
                story_id=story_id,
                content=scene_content,
                metadata={
                    'sequence': sequence_number,
                    'chapter_id': chapter_id or 0,
                    'characters': []  # Could be enhanced later
                }
            )
            
            # Store embedding reference in database
            from ..models import SceneEmbedding
            import hashlib
            
            # Generate content hash for change detection
            content_hash = hashlib.sha256(scene_content.encode('utf-8')).hexdigest()
            
            scene_embedding = SceneEmbedding(
                story_id=story_id,
                scene_id=scene_id,
                variant_id=variant_id,
                embedding_id=embedding_id,
                content_hash=content_hash,
                sequence_order=sequence_number,
                chapter_id=chapter_id,
                content_length=len(scene_content)
            )
            db.add(scene_embedding)
            db.commit()
            
            results['scene_embedding'] = True
            logger.info(f"Created scene embedding for scene {scene_id}")
            
        except Exception as e:
            logger.error(f"Failed to create scene embedding: {e}")
            import traceback
            logger.error(f"Scene embedding traceback: {traceback.format_exc()}")
            db.rollback()
        
        # 2. Extract character moments (if enabled in user settings)
        auto_extract_chars = True
        if user_settings and user_settings.get("context_settings"):
            auto_extract_chars = user_settings["context_settings"].get(
                "auto_extract_character_moments", 
                settings.auto_extract_character_moments
            )
        else:
            auto_extract_chars = settings.auto_extract_character_moments
            
        if auto_extract_chars:
            try:
                char_service = get_character_memory_service()
                moments = await char_service.extract_character_moments(
                    scene_id=scene_id,
                    scene_content=scene_content,
                    story_id=story_id,
                    sequence_number=sequence_number,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                
                results['character_moments'] = len(moments) > 0
                logger.info(f"Extracted {len(moments)} character moments for scene {scene_id}")
                
            except Exception as e:
                logger.error(f"Failed to extract character moments: {e}")
        
        # 3. Extract plot events (if enabled in user settings)
        auto_extract_plot = True
        if user_settings and user_settings.get("context_settings"):
            auto_extract_plot = user_settings["context_settings"].get(
                "auto_extract_plot_events", 
                settings.auto_extract_plot_events
            )
        else:
            auto_extract_plot = settings.auto_extract_plot_events
            
        if auto_extract_plot:
            try:
                plot_service = get_plot_thread_service()
                events = await plot_service.extract_plot_events(
                    scene_id=scene_id,
                    scene_content=scene_content,
                    story_id=story_id,
                    sequence_number=sequence_number,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                
                results['plot_events'] = len(events) > 0
                logger.info(f"Extracted {len(events)} plot events for scene {scene_id}")
                
            except Exception as e:
                logger.error(f"Failed to extract plot events: {e}")
        
        # 4. Extract and update entity states (characters, locations, objects)
        try:
            from .entity_state_service import EntityStateService
            entity_service = EntityStateService(user_id=user_id, user_settings=user_settings)
            
            entity_results = await entity_service.extract_and_update_states(
                db=db,
                story_id=story_id,
                scene_id=scene_id,
                scene_sequence=sequence_number,
                scene_content=scene_content
            )
            
            results['entity_states'] = entity_results.get('extraction_successful', False)
            logger.info(f"Entity states updated for scene {scene_id}: {entity_results}")
            
        except Exception as e:
            logger.error(f"Failed to update entity states: {e}")
        
        return results
        
    except RuntimeError as e:
        logger.warning(f"Semantic memory service not available: {e}")
        return results
    except Exception as e:
        logger.error(f"Unexpected error in semantic processing: {e}")
        import traceback
        logger.error(f"Semantic processing traceback: {traceback.format_exc()}")
        return results


async def cleanup_scene_embeddings(scene_id: int, db: Session):
    """
    Clean up all semantic data for a deleted scene
    
    Args:
        scene_id: Scene ID to clean up
        db: Database session
    """
    try:
        # Get semantic services
        char_service = get_character_memory_service()
        plot_service = get_plot_thread_service()
        semantic_memory = get_semantic_memory_service()
        
        # Delete character moments
        char_service.delete_character_moments(scene_id, db)
        
        # Delete plot events
        plot_service.delete_plot_events(scene_id, db)
        
        # Delete scene embeddings from database
        from ..models import SceneEmbedding
        scene_embeddings = db.query(SceneEmbedding).filter(
            SceneEmbedding.scene_id == scene_id
        ).all()
        
        # Delete from vector database
        for embedding in scene_embeddings:
            try:
                # Get variant ID from embedding
                parts = embedding.embedding_id.split('_')
                if len(parts) >= 3:
                    variant_id = int(parts[-1].replace('v', ''))
                    semantic_memory.delete_scene_embedding(scene_id, variant_id)
            except Exception as e:
                logger.warning(f"Failed to delete vector embedding {embedding.embedding_id}: {e}")
        
        # Delete database records
        db.query(SceneEmbedding).filter(
            SceneEmbedding.scene_id == scene_id
        ).delete()
        
        db.commit()
        logger.info(f"Cleaned up semantic data for scene {scene_id}")
        
    except Exception as e:
        logger.error(f"Failed to cleanup scene embeddings: {e}")
        db.rollback()


def get_semantic_stats(story_id: int, db: Session) -> Dict[str, Any]:
    """
    Get statistics about semantic data for a story
    
    Args:
        story_id: Story ID
        db: Database session
        
    Returns:
        Dictionary with semantic memory statistics
    """
    try:
        from ..models import SceneEmbedding, CharacterMemory, PlotEvent
        
        stats = {
            'enabled': settings.enable_semantic_memory,
            'scene_embeddings': 0,
            'character_moments': 0,
            'plot_events': 0,
            'unresolved_threads': 0
        }
        
        if not settings.enable_semantic_memory:
            return stats
        
        # Count scene embeddings
        stats['scene_embeddings'] = db.query(SceneEmbedding).filter(
            SceneEmbedding.story_id == story_id
        ).count()
        
        # Count character moments
        stats['character_moments'] = db.query(CharacterMemory).filter(
            CharacterMemory.story_id == story_id
        ).count()
        
        # Count plot events
        stats['plot_events'] = db.query(PlotEvent).filter(
            PlotEvent.story_id == story_id
        ).count()
        
        # Count unresolved threads
        stats['unresolved_threads'] = db.query(PlotEvent).filter(
            PlotEvent.story_id == story_id,
            PlotEvent.is_resolved == False
        ).count()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get semantic stats: {e}")
        return {'enabled': False, 'error': str(e)}

