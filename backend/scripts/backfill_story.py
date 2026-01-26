#!/usr/bin/env python3
"""
Comprehensive Story Backfill Script

Re-processes existing stories to update:
- Relationship graph (character relationships)
- Chapter summaries
- Entity state extractions
- Working memory

Usage:
    # Full backfill for a story:
    python scripts/backfill_story.py --story-id 5

    # Specific features only:
    python scripts/backfill_story.py --story-id 5 --relationships --summaries

    # Dry run:
    python scripts/backfill_story.py --story-id 5 --dry-run
"""

import sys
import os
import argparse
import asyncio
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import SessionLocal
from app.models import (
    Story, Scene, StoryCharacter, Character, SceneVariant,
    Chapter, ChapterSummaryBatch, UserSettings
)
from app.models.relationship import CharacterRelationship, RelationshipSummary
from app.models.working_memory import WorkingMemory
from app.services.entity_state_service import EntityStateService
from app.services.chapter_summary_service import ChapterSummaryService


def get_user_settings(db: Session, user_id: int = 1) -> dict:
    """Get user settings from database."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings:
        return settings.to_dict()
    return {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_story_characters(db: Session, story_id: int, branch_id: int = None) -> list[str]:
    """Get character names for a story."""
    query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)

    if branch_id:
        query = query.filter(
            or_(
                StoryCharacter.branch_id == branch_id,
                StoryCharacter.branch_id.is_(None)
            )
        )

    story_characters = query.all()

    characters = []
    for sc in story_characters:
        char = db.query(Character).filter(Character.id == sc.character_id).first()
        if char and char.name:
            characters.append(char.name)

    return characters


def get_scenes_for_story(db: Session, story_id: int, branch_id: int = None) -> list[tuple]:
    """Get all scenes for a story in order.

    Returns list of (scene_id, sequence_number, content, branch_id, chapter_id)
    """
    query = db.query(Scene).filter(
        Scene.story_id == story_id,
        Scene.is_deleted == False
    )

    if branch_id:
        query = query.filter(
            or_(
                Scene.branch_id == branch_id,
                Scene.branch_id.is_(None)
            )
        )

    scenes = query.order_by(Scene.sequence_number).all()

    if not scenes:
        logger.warning(f"No scenes found for story {story_id}")
        return []

    result = []
    for scene in scenes:
        # Get the first variant (original) or any variant with content
        variant = db.query(SceneVariant).filter(
            SceneVariant.scene_id == scene.id
        ).order_by(SceneVariant.variant_number).first()

        if variant and variant.content:
            result.append((
                scene.id,
                scene.sequence_number,
                variant.content,
                scene.branch_id,
                scene.chapter_id
            ))

    return result


def get_chapters_for_story(db: Session, story_id: int, branch_id: int = None) -> list:
    """Get all chapters for a story."""
    query = db.query(Chapter).filter(Chapter.story_id == story_id)

    if branch_id:
        query = query.filter(
            or_(
                Chapter.branch_id == branch_id,
                Chapter.branch_id.is_(None)
            )
        )

    return query.order_by(Chapter.chapter_number).all()


# =============================================================================
# RELATIONSHIP BACKFILL
# =============================================================================

def clear_relationships(db: Session, story_id: int, branch_id: int = None):
    """Clear existing relationship data for a story."""
    query = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id
    )
    if branch_id:
        query = query.filter(CharacterRelationship.branch_id == branch_id)
    deleted_events = query.delete()

    query = db.query(RelationshipSummary).filter(
        RelationshipSummary.story_id == story_id
    )
    if branch_id:
        query = query.filter(RelationshipSummary.branch_id == branch_id)
    deleted_summaries = query.delete()

    db.commit()
    logger.info(f"  Cleared {deleted_events} relationship events and {deleted_summaries} summaries")


async def backfill_relationships(
    db: Session,
    story_id: int,
    branch_id: int,
    scenes: list,
    characters: list[str],
    user_settings: dict,
    dry_run: bool = False
) -> int:
    """Backfill relationship graph for all scenes."""
    logger.info("=== BACKFILL RELATIONSHIPS ===")

    if len(characters) < 2:
        logger.warning(f"  Less than 2 characters ({len(characters)}), skipping")
        return 0

    if not dry_run:
        # Clear ALL branches for this story (don't filter by branch_id)
        clear_relationships(db, story_id)

    entity_service = EntityStateService(user_id=1, user_settings=user_settings)
    total = 0

    for scene_id, sequence, content, scene_branch_id, chapter_id in scenes:
        if dry_run:
            logger.info(f"  [DRY RUN] Would process scene {sequence}")
            continue

        try:
            result = await entity_service.update_relationship_graph(
                db=db,
                story_id=story_id,
                branch_id=scene_branch_id or branch_id,
                scene_id=scene_id,
                scene_sequence=sequence,
                scene_content=content,
                characters=characters
            )
            count = len(result) if result else 0
            if count > 0:
                logger.info(f"  Scene {sequence}: {count} relationships")
                total += count
        except Exception as e:
            logger.error(f"  Scene {sequence}: error - {e}")

        await asyncio.sleep(0.3)

    logger.info(f"  Total: {total} relationships extracted")
    return total


# =============================================================================
# CHAPTER SUMMARY BACKFILL
# =============================================================================

def clear_chapter_summaries(db: Session, story_id: int):
    """Clear existing chapter summaries."""
    chapters = db.query(Chapter).filter(Chapter.story_id == story_id).all()
    for chapter in chapters:
        chapter.auto_summary = None
        chapter.last_summary_scene_count = 0

    # Also clear summary batches
    db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id.in_([c.id for c in chapters])
    ).delete(synchronize_session=False)

    db.commit()
    logger.info(f"  Cleared summaries for {len(chapters)} chapters")


async def backfill_chapter_summaries(
    db: Session,
    story_id: int,
    branch_id: int,
    chapters: list,
    scenes: list,
    user_settings: dict,
    user_id: int = 2,
    dry_run: bool = False,
    batch_size: int = 10
) -> int:
    """Regenerate chapter summaries using batched incremental processing.

    Processes each chapter's scenes in batches of `batch_size` to avoid
    exceeding the LLM context window. Uses the incremental summary service
    which builds upon the previous batch's summary.
    """
    logger.info("=== BACKFILL CHAPTER SUMMARIES ===")

    if not chapters:
        logger.warning("  No chapters found")
        return 0

    if not dry_run:
        clear_chapter_summaries(db, story_id)

    summary_service = ChapterSummaryService(db=db, user_id=user_id)
    total = 0

    for chapter in chapters:
        # Get scenes for this chapter
        chapter_scenes = [s for s in scenes if s[4] == chapter.id]

        if not chapter_scenes:
            logger.info(f"  Chapter {chapter.chapter_number}: no scenes, skipping")
            continue

        num_batches = (len(chapter_scenes) + batch_size - 1) // batch_size

        if dry_run:
            logger.info(f"  [DRY RUN] Would regenerate summary for chapter {chapter.chapter_number} "
                        f"({len(chapter_scenes)} scenes, {num_batches} batches)")
            continue

        try:
            # Reset watermark so incremental starts from the beginning
            chapter.last_summary_scene_count = 0
            chapter.auto_summary = None
            db.flush()

            # Process scenes in batches using the incremental method
            # The service fetches scenes with sequence_number > last_summary_scene_count
            # and max_new_scenes limits how many it picks up per call
            for batch_idx in range(num_batches):
                result = await summary_service.generate_chapter_summary_incremental(
                    chapter_id=chapter.id,
                    max_new_scenes=batch_size
                )

                # The service updates chapter.last_summary_scene_count after each batch
                # so the next call picks up where this one left off

                if result:
                    logger.info(f"  Chapter {chapter.chapter_number} batch {batch_idx + 1}/{num_batches}: "
                                f"summarized (watermark now at {chapter.last_summary_scene_count})")
                else:
                    logger.warning(f"  Chapter {chapter.chapter_number} batch {batch_idx + 1}/{num_batches}: "
                                   f"summary generation failed")
                    break  # Stop if a batch fails

                await asyncio.sleep(0.5)

            # Also generate story_so_far for this chapter
            await summary_service.generate_story_so_far(chapter_id=chapter.id)

            total += 1
            logger.info(f"  Chapter {chapter.chapter_number}: complete ({len(chapter_scenes)} scenes, {num_batches} batches)")

        except Exception as e:
            logger.error(f"  Chapter {chapter.chapter_number}: error - {e}")

    logger.info(f"  Total: {total} chapters summarized")
    return total


# =============================================================================
# ENTITY STATE BACKFILL
# =============================================================================

async def backfill_entity_states(
    db: Session,
    story_id: int,
    branch_id: int,
    scenes: list,
    characters: list[str],
    user_settings: dict,
    dry_run: bool = False
) -> int:
    """Re-extract entity states from scenes."""
    logger.info("=== BACKFILL ENTITY STATES ===")

    if not characters:
        logger.warning("  No characters found, skipping")
        return 0

    entity_service = EntityStateService(user_id=1, user_settings=user_settings)
    total = 0

    # Process scenes in batches of 5 (matching the extraction threshold)
    batch_size = 5
    for i in range(0, len(scenes), batch_size):
        batch = scenes[i:i + batch_size]
        batch_start = batch[0][1]
        batch_end = batch[-1][1]

        if dry_run:
            logger.info(f"  [DRY RUN] Would extract entities for scenes {batch_start}-{batch_end}")
            continue

        try:
            # Combine batch content
            batch_content = "\n\n---\n\n".join([s[2] for s in batch])
            last_scene = batch[-1]

            result = await entity_service.extract_and_update_entity_states(
                db=db,
                story_id=story_id,
                branch_id=last_scene[3] or branch_id,
                chapter_id=last_scene[4],
                scene_sequence=last_scene[1],
                scene_content=batch_content,
                characters=characters
            )

            if result:
                logger.info(f"  Scenes {batch_start}-{batch_end}: extracted")
                total += 1
            else:
                logger.warning(f"  Scenes {batch_start}-{batch_end}: extraction failed")

        except Exception as e:
            logger.error(f"  Scenes {batch_start}-{batch_end}: error - {e}")

        await asyncio.sleep(0.5)

    logger.info(f"  Total: {total} extraction batches processed")
    return total


# =============================================================================
# WORKING MEMORY BACKFILL
# =============================================================================

def clear_working_memory(db: Session, story_id: int, branch_id: int = None):
    """Clear existing working memory."""
    query = db.query(WorkingMemory).filter(WorkingMemory.story_id == story_id)
    if branch_id:
        query = query.filter(WorkingMemory.branch_id == branch_id)
    deleted = query.delete()
    db.commit()
    logger.info(f"  Cleared {deleted} working memory entries")


async def backfill_working_memory(
    db: Session,
    story_id: int,
    branch_id: int,
    scenes: list,
    user_settings: dict,
    dry_run: bool = False
) -> int:
    """Update working memory from scenes."""
    logger.info("=== BACKFILL WORKING MEMORY ===")

    if not scenes:
        logger.warning("  No scenes found")
        return 0

    if not dry_run:
        # Clear ALL branches for this story
        clear_working_memory(db, story_id)

    entity_service = EntityStateService(user_id=1, user_settings=user_settings)

    # Only process last few scenes for working memory (it's meant to be recent)
    recent_scenes = scenes[-5:]
    logger.info(f"  Processing last {len(recent_scenes)} scenes for working memory")

    for scene_id, sequence, content, scene_branch_id, chapter_id in recent_scenes:
        if dry_run:
            logger.info(f"  [DRY RUN] Would update working memory for scene {sequence}")
            continue

        try:
            await entity_service.update_working_memory(
                db=db,
                story_id=story_id,
                branch_id=scene_branch_id or branch_id,
                chapter_id=chapter_id,
                scene_sequence=sequence,
                scene_content=content
            )
            logger.info(f"  Scene {sequence}: working memory updated")
        except Exception as e:
            logger.error(f"  Scene {sequence}: error - {e}")

        await asyncio.sleep(0.3)

    logger.info("  Working memory backfill complete")
    return 1


# =============================================================================
# MAIN BACKFILL
# =============================================================================

async def backfill_story(
    story_id: int,
    branch_id: int = None,
    user_id: int = 1,
    dry_run: bool = False,
    do_relationships: bool = True,
    do_summaries: bool = True,
    do_entities: bool = True,
    do_memory: bool = True
):
    """Full backfill for a story."""
    db = SessionLocal()

    try:
        # Get story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.error(f"Story {story_id} not found")
            return

        logger.info(f"\n{'='*60}")
        logger.info(f"BACKFILLING STORY {story_id}: {story.title}")
        logger.info(f"{'='*60}\n")

        # Get characters
        characters = get_story_characters(db, story_id, branch_id)
        logger.info(f"Characters: {', '.join(characters)}")

        # Get scenes
        scenes = get_scenes_for_story(db, story_id, branch_id)
        logger.info(f"Scenes: {len(scenes)}")

        # Get chapters
        chapters = get_chapters_for_story(db, story_id, branch_id)
        logger.info(f"Chapters: {len(chapters)}")

        # Use branch from first scene if not specified
        if branch_id is None and scenes:
            branch_id = scenes[0][3]

        # Get user settings from database
        user_settings = get_user_settings(db, user_id=user_id)
        # Ensure required settings are enabled
        if 'context_settings' not in user_settings:
            user_settings['context_settings'] = {}
        user_settings['context_settings']['enable_relationship_graph'] = True
        user_settings['context_settings']['enable_working_memory'] = True
        logger.info(f"Using extraction model: {user_settings.get('extraction_model_settings', {}).get('url', 'default')}")

        print()

        # Run backfills
        if do_relationships:
            await backfill_relationships(
                db, story_id, branch_id, scenes, characters, user_settings, dry_run
            )
            print()

        if do_summaries:
            await backfill_chapter_summaries(
                db, story_id, branch_id, chapters, scenes, user_settings,
                user_id=user_id, dry_run=dry_run
            )
            print()

        if do_entities:
            await backfill_entity_states(
                db, story_id, branch_id, scenes, characters, user_settings, dry_run
            )
            print()

        if do_memory:
            await backfill_working_memory(
                db, story_id, branch_id, scenes, user_settings, dry_run
            )
            print()

        # Final summary
        logger.info(f"{'='*60}")
        logger.info(f"BACKFILL COMPLETE FOR STORY {story_id}")
        logger.info(f"{'='*60}")

        if not dry_run:
            # Show relationship summaries
            summaries = db.query(RelationshipSummary).filter(
                RelationshipSummary.story_id == story_id
            ).all()
            if summaries:
                logger.info("\nRelationship Summaries:")
                for s in summaries:
                    logger.info(f"  {s.character_a} <-> {s.character_b}: {s.current_type} "
                               f"[{s.current_strength:.1f}] ({s.total_interactions} interactions)")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description='Comprehensive story backfill script'
    )
    parser.add_argument(
        '--story-id', '-s',
        type=int,
        required=True,
        help='Story ID to process'
    )
    parser.add_argument(
        '--branch-id', '-b',
        type=int,
        help='Branch ID to process (optional)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Dry run - do not make changes'
    )
    parser.add_argument(
        '--relationships', '-r',
        action='store_true',
        help='Only backfill relationships'
    )
    parser.add_argument(
        '--summaries', '-u',
        action='store_true',
        help='Only backfill chapter summaries'
    )
    parser.add_argument(
        '--entities', '-e',
        action='store_true',
        help='Only backfill entity states'
    )
    parser.add_argument(
        '--memory', '-m',
        action='store_true',
        help='Only backfill working memory'
    )
    parser.add_argument(
        '--user-id', '-U',
        type=int,
        default=2,
        help='User ID for LLM settings (default: 2)'
    )

    args = parser.parse_args()

    # If no specific flags, do all
    do_all = not any([args.relationships, args.summaries, args.entities, args.memory])

    asyncio.run(backfill_story(
        story_id=args.story_id,
        branch_id=args.branch_id,
        user_id=args.user_id,
        dry_run=args.dry_run,
        do_relationships=args.relationships or do_all,
        do_summaries=args.summaries or do_all,
        do_entities=args.entities or do_all,
        do_memory=args.memory or do_all
    ))


if __name__ == "__main__":
    main()
