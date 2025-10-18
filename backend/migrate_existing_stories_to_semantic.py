"""
Migration Script: Embed Existing Stories into Semantic Memory

This script processes existing stories and creates embeddings for:
- Scene content
- Character moments (auto-extracted)
- Plot events (auto-extracted)

Usage:
    python migrate_existing_stories_to_semantic.py [--story-id STORY_ID] [--dry-run]

Options:
    --story-id: Process only specific story (default: all stories)
    --dry-run: Show what would be done without making changes
    --skip-extraction: Only create scene embeddings, skip character/plot extraction
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Story, Scene, StoryFlow, SceneVariant, Chapter, User, UserSettings
from app.services.semantic_memory import initialize_semantic_memory_service, get_semantic_memory_service
from app.services.character_memory_service import get_character_memory_service
from app.services.plot_thread_service import get_plot_thread_service
from app.services.semantic_integration import process_scene_embeddings
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationStats:
    """Track migration statistics"""
    def __init__(self):
        self.stories_processed = 0
        self.scenes_embedded = 0
        self.character_moments = 0
        self.plot_events = 0
        self.errors = 0
        self.skipped = 0


async def migrate_scene(
    scene: Scene,
    variant: SceneVariant,
    story_id: int,
    chapter_id: int,
    user_id: int,
    user_settings: dict,
    skip_extraction: bool,
    db,
    stats: MigrationStats
):
    """Migrate a single scene"""
    try:
        logger.info(f"  Processing scene {scene.sequence_number} (ID: {scene.id})")
        
        # Check if already embedded
        from app.models import SceneEmbedding
        existing = db.query(SceneEmbedding).filter(
            SceneEmbedding.scene_id == scene.id,
            SceneEmbedding.variant_id == variant.id
        ).first()
        
        if existing:
            logger.info(f"    Scene {scene.id} already embedded, skipping")
            stats.skipped += 1
            return
        
        # Process embeddings
        results = await process_scene_embeddings(
            scene_id=scene.id,
            variant_id=variant.id,
            story_id=story_id,
            scene_content=variant.content,
            sequence_number=scene.sequence_number,
            chapter_id=chapter_id,
            user_id=user_id,
            user_settings=user_settings if not skip_extraction else {**user_settings, 'auto_extract_character_moments': False, 'auto_extract_plot_events': False},
            db=db
        )
        
        if results['scene_embedding']:
            stats.scenes_embedded += 1
            logger.info(f"    ✓ Scene embedding created")
        
        if results.get('character_moments', False):
            stats.character_moments += 1
            logger.info(f"    ✓ Character moments extracted")
        
        if results.get('plot_events', False):
            stats.plot_events += 1
            logger.info(f"    ✓ Plot events extracted")
        
    except Exception as e:
        logger.error(f"    ✗ Failed to migrate scene {scene.id}: {e}")
        stats.errors += 1


async def migrate_story(
    story_id: int,
    skip_extraction: bool,
    dry_run: bool,
    stats: MigrationStats
):
    """Migrate a single story"""
    db = SessionLocal()
    
    try:
        # Get story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.error(f"Story {story_id} not found")
            return
        
        logger.info(f"\nMigrating story {story_id}: '{story.title}'")
        logger.info(f"  Owner ID: {story.owner_id}")
        
        if dry_run:
            logger.info("  [DRY RUN - No changes will be made]")
        
        # Get user settings
        user_settings_db = db.query(UserSettings).filter(
            UserSettings.user_id == story.owner_id
        ).first()
        user_settings = user_settings_db.to_dict() if user_settings_db else {}
        
        # Get all scenes with active variants
        scenes = db.query(Scene).filter(
            Scene.story_id == story_id
        ).order_by(Scene.sequence_number).all()
        
        if not scenes:
            logger.info("  No scenes to migrate")
            return
        
        logger.info(f"  Found {len(scenes)} scenes to process")
        
        if dry_run:
            logger.info(f"  [DRY RUN] Would process {len(scenes)} scenes")
            stats.stories_processed += 1
            return
        
        # Process each scene
        for scene in scenes:
            # Get active variant
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            ).first()
            
            if not flow or not flow.scene_variant:
                logger.warning(f"  Scene {scene.id} has no active variant, skipping")
                stats.skipped += 1
                continue
            
            # Get chapter ID
            chapter_id = scene.chapter_id
            
            # Migrate scene
            await migrate_scene(
                scene=scene,
                variant=flow.scene_variant,
                story_id=story_id,
                chapter_id=chapter_id,
                user_id=story.owner_id,
                user_settings=user_settings,
                skip_extraction=skip_extraction,
                db=db,
                stats=stats
            )
        
        stats.stories_processed += 1
        logger.info(f"✓ Story {story_id} migration complete")
        
    except Exception as e:
        logger.error(f"Failed to migrate story {story_id}: {e}")
        stats.errors += 1
    finally:
        db.close()


async def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(description='Migrate existing stories to semantic memory')
    parser.add_argument('--story-id', type=int, help='Migrate specific story only')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--skip-extraction', action='store_true', help='Only create scene embeddings, skip character/plot extraction')
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("SEMANTIC MEMORY MIGRATION SCRIPT")
    logger.info("=" * 80)
    
    # Initialize semantic memory service
    if not settings.enable_semantic_memory:
        logger.error("Semantic memory is disabled in configuration!")
        logger.error("Set enable_semantic_memory=True in config.py to continue")
        return
    
    logger.info("\nInitializing semantic memory service...")
    try:
        initialize_semantic_memory_service(
            persist_directory=settings.semantic_db_path,
            embedding_model=settings.semantic_embedding_model
        )
        logger.info("✓ Semantic memory service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize semantic memory service: {e}")
        return
    
    # Get collection stats
    semantic_memory = get_semantic_memory_service()
    initial_stats = semantic_memory.get_collection_stats()
    logger.info(f"\nInitial collection stats:")
    logger.info(f"  Scenes: {initial_stats['scenes']}")
    logger.info(f"  Character moments: {initial_stats['character_moments']}")
    logger.info(f"  Plot events: {initial_stats['plot_events']}")
    
    # Get stories to migrate
    db = SessionLocal()
    try:
        if args.story_id:
            stories = db.query(Story).filter(Story.id == args.story_id).all()
            if not stories:
                logger.error(f"Story {args.story_id} not found")
                return
        else:
            stories = db.query(Story).all()
        
        logger.info(f"\nFound {len(stories)} stories to migrate")
        
        if args.dry_run:
            logger.info("\n⚠️  DRY RUN MODE - No changes will be made")
        
        if args.skip_extraction:
            logger.info("⚠️  SKIP EXTRACTION MODE - Only scene embeddings will be created")
        
    finally:
        db.close()
    
    # Migrate each story
    stats = MigrationStats()
    
    for story in stories:
        await migrate_story(
            story_id=story.id,
            skip_extraction=args.skip_extraction,
            dry_run=args.dry_run,
            stats=stats
        )
    
    # Final stats
    logger.info("\n" + "=" * 80)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"\nStories processed: {stats.stories_processed}")
    logger.info(f"Scenes embedded: {stats.scenes_embedded}")
    logger.info(f"Character moments extracted: {stats.character_moments}")
    logger.info(f"Plot events extracted: {stats.plot_events}")
    logger.info(f"Skipped (already embedded): {stats.skipped}")
    logger.info(f"Errors: {stats.errors}")
    
    # Get final collection stats
    final_stats = semantic_memory.get_collection_stats()
    logger.info(f"\nFinal collection stats:")
    logger.info(f"  Scenes: {final_stats['scenes']} (+{final_stats['scenes'] - initial_stats['scenes']})")
    logger.info(f"  Character moments: {final_stats['character_moments']} (+{final_stats['character_moments'] - initial_stats['character_moments']})")
    logger.info(f"  Plot events: {final_stats['plot_events']} (+{final_stats['plot_events'] - initial_stats['plot_events']})")
    
    logger.info("\n✓ Migration script completed")


if __name__ == "__main__":
    asyncio.run(main())

