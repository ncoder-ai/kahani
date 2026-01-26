#!/usr/bin/env python3
"""
Backfill Relationship Graph for Existing Stories

This script processes existing scenes and extracts character relationships
to populate the relationship graph tables (character_relationships, relationship_summaries).

Usage:
    # From backend directory:
    python scripts/backfill_relationships.py --story-id 5

    # Process all stories:
    python scripts/backfill_relationships.py --all

    # Dry run (no database changes):
    python scripts/backfill_relationships.py --story-id 5 --dry-run
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
from app.models import Story, Scene, StoryFlow, StoryCharacter, Character, SceneVariant
from app.models.relationship import CharacterRelationship, RelationshipSummary
from app.services.entity_state_service import EntityStateService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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

    Returns list of (scene_id, sequence_number, content, branch_id)
    """
    # Get active flow
    flow_query = db.query(StoryFlow).filter(
        StoryFlow.story_id == story_id,
        StoryFlow.is_active == True
    )

    if branch_id:
        flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)

    flow = flow_query.first()

    if not flow:
        logger.warning(f"No active flow found for story {story_id}")
        return []

    # Get scenes
    scenes = db.query(Scene).filter(
        Scene.flow_id == flow.id
    ).order_by(Scene.sequence_number).all()

    result = []
    for scene in scenes:
        # Get the active variant's content
        variant = db.query(SceneVariant).filter(
            SceneVariant.scene_id == scene.id,
            SceneVariant.is_active == True
        ).first()

        if variant and variant.content:
            result.append((
                scene.id,
                scene.sequence_number,
                variant.content,
                flow.branch_id
            ))

    return result


def clear_existing_relationships(db: Session, story_id: int, branch_id: int = None):
    """Clear existing relationship data for a story."""
    # Delete events
    query = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id
    )
    if branch_id:
        query = query.filter(CharacterRelationship.branch_id == branch_id)
    deleted_events = query.delete()

    # Delete summaries
    query = db.query(RelationshipSummary).filter(
        RelationshipSummary.story_id == story_id
    )
    if branch_id:
        query = query.filter(RelationshipSummary.branch_id == branch_id)
    deleted_summaries = query.delete()

    db.commit()
    logger.info(f"Cleared {deleted_events} events and {deleted_summaries} summaries for story {story_id}")


async def process_scene(
    db: Session,
    entity_service: EntityStateService,
    story_id: int,
    branch_id: int,
    scene_id: int,
    scene_sequence: int,
    scene_content: str,
    characters: list[str],
    dry_run: bool = False
) -> int:
    """Process a single scene and extract relationships.

    Returns number of relationships extracted.
    """
    if dry_run:
        logger.info(f"  [DRY RUN] Would process scene {scene_sequence}")
        return 0

    try:
        result = await entity_service.update_relationship_graph(
            db=db,
            story_id=story_id,
            branch_id=branch_id,
            scene_id=scene_id,
            scene_sequence=scene_sequence,
            scene_content=scene_content,
            characters=characters
        )

        count = len(result) if result else 0
        if count > 0:
            logger.info(f"  Scene {scene_sequence}: extracted {count} relationships")
        else:
            logger.debug(f"  Scene {scene_sequence}: no relationships")

        return count

    except Exception as e:
        logger.error(f"  Scene {scene_sequence}: error - {e}")
        return 0


async def backfill_story(
    story_id: int,
    branch_id: int = None,
    dry_run: bool = False,
    clear_existing: bool = True
):
    """Backfill relationship graph for a single story."""
    db = SessionLocal()

    try:
        # Get story
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.error(f"Story {story_id} not found")
            return

        logger.info(f"Processing story {story_id}: {story.title}")

        # Get characters
        characters = get_story_characters(db, story_id, branch_id)
        if len(characters) < 2:
            logger.warning(f"Story {story_id} has less than 2 characters ({len(characters)}), skipping")
            return

        logger.info(f"  Characters: {', '.join(characters)}")

        # Get scenes
        scenes = get_scenes_for_story(db, story_id, branch_id)
        if not scenes:
            logger.warning(f"Story {story_id} has no scenes")
            return

        logger.info(f"  Found {len(scenes)} scenes to process")

        # Use branch from first scene if not specified
        if branch_id is None and scenes:
            branch_id = scenes[0][3]

        # Clear existing relationships
        if clear_existing and not dry_run:
            clear_existing_relationships(db, story_id, branch_id)

        # Create entity service with default settings
        user_settings = {
            'context_settings': {
                'enable_relationship_graph': True
            }
        }
        entity_service = EntityStateService(user_id=1, user_settings=user_settings)

        # Process each scene
        total_relationships = 0
        for scene_id, sequence, content, scene_branch_id in scenes:
            count = await process_scene(
                db=db,
                entity_service=entity_service,
                story_id=story_id,
                branch_id=scene_branch_id or branch_id,
                scene_id=scene_id,
                scene_sequence=sequence,
                scene_content=content,
                characters=characters,
                dry_run=dry_run
            )
            total_relationships += count

            # Small delay to avoid overwhelming the extraction LLM
            if not dry_run:
                await asyncio.sleep(0.5)

        logger.info(f"  Total: {total_relationships} relationships extracted from {len(scenes)} scenes")

        # Show final summary
        if not dry_run:
            summaries = db.query(RelationshipSummary).filter(
                RelationshipSummary.story_id == story_id
            ).all()

            logger.info(f"\n  Relationship Summaries:")
            for s in summaries:
                logger.info(f"    {s.character_a} <-> {s.character_b}: {s.current_type} "
                           f"[{s.current_strength:.1f}] ({s.trajectory}, {s.total_interactions} interactions)")

    finally:
        db.close()


async def backfill_all_stories(dry_run: bool = False):
    """Backfill relationship graph for all stories."""
    db = SessionLocal()

    try:
        stories = db.query(Story).all()
        logger.info(f"Found {len(stories)} stories to process")

        for story in stories:
            await backfill_story(story.id, dry_run=dry_run)
            print()  # Blank line between stories

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description='Backfill relationship graph for existing stories'
    )
    parser.add_argument(
        '--story-id', '-s',
        type=int,
        help='Story ID to process'
    )
    parser.add_argument(
        '--branch-id', '-b',
        type=int,
        help='Branch ID to process (optional)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Process all stories'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Dry run - do not make changes'
    )
    parser.add_argument(
        '--no-clear',
        action='store_true',
        help='Do not clear existing relationships before processing'
    )

    args = parser.parse_args()

    if not args.story_id and not args.all:
        parser.error("Either --story-id or --all is required")

    if args.all:
        asyncio.run(backfill_all_stories(dry_run=args.dry_run))
    else:
        asyncio.run(backfill_story(
            story_id=args.story_id,
            branch_id=args.branch_id,
            dry_run=args.dry_run,
            clear_existing=not args.no_clear
        ))


if __name__ == "__main__":
    main()
