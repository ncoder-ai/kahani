#!/usr/bin/env python3
"""
Re-index scene embeddings with contextual prefixes.

For each scene in the specified story:
1. Generates a 1-sentence summary via extraction LLM
2. Builds a contextual prefix (chapter, scene#, location, characters, summary)
3. Upserts the enriched content to ChromaDB (existing embedding IDs get overwritten)

Usage:
    python scripts/reindex_contextual_embeddings.py --story-id 5
    python scripts/reindex_contextual_embeddings.py --story-id 5 --dry-run
    python scripts/reindex_contextual_embeddings.py --story-id 5 --chapter-id 8
"""

import sys
import os
import argparse
import asyncio
import logging
import hashlib

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import (
    Story, Scene, SceneVariant, Chapter, StoryCharacter, Character,
    SceneEmbedding, UserSettings
)
from app.models.story_flow import StoryFlow
from app.services.semantic_memory import get_semantic_memory_service, initialize_semantic_memory_service
from app.services.llm.service import UnifiedLLMService
from app.services.llm.extraction_service import ExtractionLLMService

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def get_user_settings(db: Session, user_id: int = 1) -> dict:
    """Get user settings from database."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings:
        return settings.to_dict()
    return {}


def get_story_characters(db: Session, story_id: int) -> str:
    """Get comma-separated character names for a story."""
    story_chars = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id).all()
    seen = set()
    names = []
    for sc in story_chars:
        char = db.query(Character).filter(Character.id == sc.character_id).first()
        if char and char.name not in seen:
            seen.add(char.name)
            names.append(char.name)
    return ", ".join(names)


async def generate_summary_simple(extraction_service: ExtractionLLMService, scene_content: str) -> dict:
    """Generate a 1-sentence summary + specific location using the extraction model directly.

    Returns:
        Dict with 'location' and 'summary', or empty dict on failure.
    """
    system_prompt = (
        "Return TWO lines:\n"
        "1. Location: just the room or area name, 1-4 words max (e.g. \"kitchen\", \"back patio\", \"master bedroom\"). No descriptions or adjectives.\n"
        "2. Summary: ONE factual sentence of what happens. Include character names and key action. No opinions or adjectives."
    )
    user_prompt = f"Scene:\n{scene_content[:3000]}\n\nLocation:"

    try:
        response = await extraction_service.generate_with_messages(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=150
        )
        if response:
            import re
            text = response.strip()
            # Strip markdown formatting
            text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
            text = re.sub(r'#{1,6}\s*', '', text)
            text = re.sub(r'`(.+?)`', r'\1', text)

            location = ""
            summary = ""

            # The user_prompt ends with "Location:" so LLM continues with value directly
            # Response format: "Kitchen\nSummary: ..." (first line = location, no prefix)
            loc_match = re.search(r'(?i)^location:\s*(.+)', text, re.MULTILINE)
            sum_match = re.search(r'(?i)^summary:\s*(.+)', text, re.MULTILINE)

            if loc_match:
                location = loc_match.group(1).strip().rstrip('.')
            if sum_match:
                summary = sum_match.group(1).strip()

            # If no "Location:" prefix found, first non-empty line is the location
            if not location:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if lines:
                    first = lines[0]
                    # First line is location if it's short (< 60 chars) and not the summary
                    if len(first) < 60 and not re.match(r'(?i)^summary:', first):
                        location = first.rstrip('.')

            # If no "Summary:" prefix found, grab text after location line
            if not summary:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                non_loc_lines = [l for l in lines if l.rstrip('.') != location and not re.match(r'(?i)^location:', l)]
                summary = ' '.join(non_loc_lines) if non_loc_lines else ""

            if '. ' in summary:
                summary = summary[:summary.index('. ') + 1]
            return {"location": location, "summary": summary}
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
    return {}


async def reindex_story(story_id: int, chapter_id: int = None, dry_run: bool = False,
                        extraction_url_override: str = None, extraction_model_override: str = None):
    """Re-index all scene embeddings for a story with contextual prefixes."""
    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            logger.error(f"Story {story_id} not found")
            return

        logger.info(f"Re-indexing story {story_id}: '{story.title}'")

        # Get user settings and extraction service
        user_settings = get_user_settings(db, user_id=story.owner_id)
        ext_settings = user_settings.get('extraction_model_settings', {})

        extraction_service = None
        if ext_settings.get('enabled', False):
            ext_url = extraction_url_override or ext_settings.get('url', '')
            ext_model = extraction_model_override or ext_settings.get('model_name', '')
            extraction_service = ExtractionLLMService(
                url=ext_url,
                model=ext_model,
                api_key=ext_settings.get('api_key', 'not-needed'),
                temperature=ext_settings.get('temperature', 0.3)
            )
            logger.info(f"Using extraction model: {ext_model} at {ext_url}")
        else:
            logger.warning("No extraction model configured, summaries will be skipped")

        # Get active branch
        from app.models import StoryBranch
        active_branch = db.query(StoryBranch).filter(
            and_(StoryBranch.story_id == story_id, StoryBranch.is_active == True)
        ).first()
        branch_id = active_branch.id if active_branch else None

        # Get character names
        character_names = get_story_characters(db, story_id)

        # Get chapters
        chapter_query = db.query(Chapter).filter(Chapter.story_id == story_id)
        if chapter_id:
            chapter_query = chapter_query.filter(Chapter.id == chapter_id)
        chapters = chapter_query.order_by(Chapter.chapter_number).all()

        # Initialize semantic memory service (not auto-initialized in script context)
        from app.config import settings as app_settings
        try:
            semantic_memory = get_semantic_memory_service()
        except RuntimeError:
            logger.info("Initializing semantic memory service...")
            semantic_memory = initialize_semantic_memory_service(
                persist_directory=app_settings.semantic_db_path,
                embedding_model=app_settings.semantic_embedding_model
            )

        total_processed = 0
        total_errors = 0

        for chapter in chapters:
            logger.info(f"\n--- Chapter {chapter.chapter_number}: '{chapter.title}' ---")

            # Get scenes for this chapter via StoryFlow
            flow_query = db.query(Scene).join(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.is_active == True,
                Scene.chapter_id == chapter.id,
                Scene.is_deleted == False
            )
            if branch_id:
                flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
            scenes = flow_query.order_by(Scene.sequence_number).all()

            logger.info(f"  Found {len(scenes)} scenes")

            for scene in scenes:
                try:
                    # Get active variant
                    flow_entry = db.query(StoryFlow).filter(
                        StoryFlow.scene_id == scene.id,
                        StoryFlow.is_active == True
                    )
                    if branch_id:
                        flow_entry = flow_entry.filter(StoryFlow.branch_id == branch_id)
                    flow_entry = flow_entry.first()

                    if not flow_entry or not flow_entry.scene_variant_id:
                        continue

                    variant = db.query(SceneVariant).filter(
                        SceneVariant.id == flow_entry.scene_variant_id
                    ).first()

                    if not variant or not variant.content:
                        continue

                    scene_content = variant.content

                    # Generate summary + location
                    summary_result = {}
                    if extraction_service:
                        summary_result = await generate_summary_simple(extraction_service, scene_content)
                        if summary_result.get("summary"):
                            logger.info(f"  Scene {scene.sequence_number}: {summary_result['summary'][:80]}...")

                    # Build prefix — use LLM scene location, fall back to chapter location
                    prefix_parts = []
                    scene_location = summary_result.get("location", "") if summary_result else ""
                    location_str = scene_location or chapter.location_name or "unknown"
                    prefix_parts.append(
                        f"Chapter {chapter.chapter_number} '{chapter.title}', "
                        f"Scene {scene.sequence_number}. "
                        f"Location: {location_str}."
                    )
                    if character_names:
                        prefix_parts.append(f"Characters: {character_names}.")
                    if summary_result.get("summary"):
                        prefix_parts.append(summary_result["summary"])

                    context_prefix = "\n".join(prefix_parts)
                    enriched_content = f"{context_prefix}\n{scene_content}"

                    if dry_run:
                        logger.info(f"  [DRY RUN] Scene {scene.sequence_number}: prefix={len(context_prefix)} chars")
                        logger.info(f"    Prefix: {context_prefix[:150]}...")
                        # Print one full example for inspection
                        if total_processed == 0:
                            print("\n" + "=" * 80)
                            print("FULL EXAMPLE — What gets embedded in ChromaDB:")
                            print("=" * 80)
                            print(enriched_content[:2000])
                            if len(enriched_content) > 2000:
                                print(f"\n... ({len(enriched_content) - 2000} more chars)")
                            print("=" * 80 + "\n")
                        total_processed += 1
                        continue

                    # Upsert to ChromaDB
                    embedding_id = await semantic_memory.add_scene_embedding(
                        scene_id=scene.id,
                        variant_id=variant.id,
                        story_id=story_id,
                        content=enriched_content,
                        metadata={
                            'sequence': scene.sequence_number,
                            'chapter_id': chapter.id,
                            'branch_id': branch_id or 0,
                            'characters': [],
                            'has_contextual_prefix': True
                        }
                    )

                    # Update SceneEmbedding record
                    content_hash = hashlib.sha256(enriched_content.encode('utf-8')).hexdigest()
                    existing = db.query(SceneEmbedding).filter(
                        SceneEmbedding.embedding_id == embedding_id
                    ).first()

                    if existing:
                        existing.content_hash = content_hash
                        existing.content_length = len(enriched_content)
                    else:
                        db.add(SceneEmbedding(
                            story_id=story_id,
                            branch_id=branch_id,
                            scene_id=scene.id,
                            variant_id=variant.id,
                            embedding_id=embedding_id,
                            content_hash=content_hash,
                            sequence_order=scene.sequence_number,
                            chapter_id=chapter.id,
                            content_length=len(enriched_content)
                        ))

                    db.commit()
                    total_processed += 1

                    if total_processed % 10 == 0:
                        logger.info(f"  Progress: {total_processed} scenes processed")

                except Exception as e:
                    logger.error(f"  Error processing scene {scene.id}: {e}")
                    db.rollback()
                    total_errors += 1

        logger.info(f"\nDone! Processed: {total_processed}, Errors: {total_errors}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Re-index scene embeddings with contextual prefixes")
    parser.add_argument("--story-id", type=int, default=5, help="Story ID to re-index (default: 5)")
    parser.add_argument("--chapter-id", type=int, default=None, help="Optional: only re-index a specific chapter")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be done without writing")
    parser.add_argument("--extraction-url", type=str, default=None, help="Override extraction model URL (e.g. http://172.16.23.80:5001)")
    parser.add_argument("--extraction-model", type=str, default=None, help="Override extraction model name")
    args = parser.parse_args()

    asyncio.run(reindex_story(
        args.story_id,
        chapter_id=args.chapter_id,
        dry_run=args.dry_run,
        extraction_url_override=args.extraction_url,
        extraction_model_override=args.extraction_model
    ))


if __name__ == "__main__":
    main()
