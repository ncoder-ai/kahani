#!/usr/bin/env python3
"""
Migration script to add chapters system to existing stories.

This migration:
1. Adds story_mode column to stories table
2. Creates chapters table
3. Adds chapter_id column to scenes table
4. Creates default "Chapter 1" for all existing stories
5. Links all existing scenes to Chapter 1
"""

import sys
import os
from pathlib import Path
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum, inspect
from sqlalchemy.orm import Session
from datetime import datetime
from app.config import settings
from app.models import Base, Story, Scene, Chapter, StoryMode, ChapterStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add chapters system to database"""
    try:
        # Create engine
        engine = create_engine(settings.database_url)
        inspector = inspect(engine)
        
        logger.info("=" * 60)
        logger.info("Starting Chapters System Migration")
        logger.info("=" * 60)
        
        # Step 1: Add story_mode column to stories table
        logger.info("\n[1/5] Adding story_mode column to stories table...")
        stories_columns = [col['name'] for col in inspector.get_columns('stories')]
        
        if 'story_mode' not in stories_columns:
            with engine.begin() as conn:
                # For SQLite, need to set proper enum value
                conn.execute(text("""
                    ALTER TABLE stories 
                    ADD COLUMN story_mode VARCHAR(50) DEFAULT 'DYNAMIC'
                """))
            logger.info("✓ Added story_mode column")
        else:
            # Update any lowercase values to uppercase
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE stories 
                    SET story_mode = 'DYNAMIC' 
                    WHERE story_mode = 'dynamic' OR story_mode IS NULL
                """))
            logger.info("✓ story_mode column already exists (updated values)")
        
        # Step 2: Create chapters table
        logger.info("\n[2/5] Creating chapters table...")
        if 'chapters' not in inspector.get_table_names():
            Base.metadata.tables['chapters'].create(engine)
            logger.info("✓ Created chapters table")
        else:
            logger.info("✓ chapters table already exists")
        
        # Step 3: Add chapter_id column to scenes table
        logger.info("\n[3/5] Adding chapter_id column to scenes table...")
        scenes_columns = [col['name'] for col in inspector.get_columns('scenes')]
        
        if 'chapter_id' not in scenes_columns:
            with engine.begin() as conn:
                conn.execute(text("""
                    ALTER TABLE scenes 
                    ADD COLUMN chapter_id INTEGER
                """))
            logger.info("✓ Added chapter_id column to scenes")
        else:
            logger.info("✓ chapter_id column already exists")
        
        # Step 4: Create Chapter 1 for all existing stories
        logger.info("\n[4/5] Creating default Chapter 1 for existing stories...")
        with Session(engine) as session:
            # Get all stories that don't have chapters yet
            stories = session.query(Story).all()
            chapters_created = 0
            
            for story in stories:
                # Check if story already has chapters
                existing_chapter = session.query(Chapter).filter(
                    Chapter.story_id == story.id,
                    Chapter.chapter_number == 1
                ).first()
                
                if not existing_chapter:
                    # Create Chapter 1
                    chapter = Chapter(
                        story_id=story.id,
                        chapter_number=1,
                        title="Chapter 1",
                        description="The beginning of your story",
                        story_so_far="The story begins...",
                        status=ChapterStatus.ACTIVE,
                        created_at=story.created_at or datetime.utcnow()
                    )
                    session.add(chapter)
                    session.flush()  # Get the chapter ID
                    
                    # Count scenes for this story
                    scene_count = session.query(Scene).filter(
                        Scene.story_id == story.id
                    ).count()
                    
                    chapter.scenes_count = scene_count
                    chapters_created += 1
                    
                    logger.info(f"  Created Chapter 1 for story {story.id} ({story.title}) - {scene_count} scenes")
            
            session.commit()
            logger.info(f"✓ Created {chapters_created} default chapters")
        
        # Step 5: Link all existing scenes to their story's Chapter 1
        logger.info("\n[5/5] Linking scenes to Chapter 1...")
        with Session(engine) as session:
            scenes_updated = 0
            
            # Get all stories with their Chapter 1
            stories = session.query(Story).all()
            
            for story in stories:
                chapter_1 = session.query(Chapter).filter(
                    Chapter.story_id == story.id,
                    Chapter.chapter_number == 1
                ).first()
                
                if chapter_1:
                    # Update all scenes for this story to link to Chapter 1
                    result = session.execute(
                        text("""
                            UPDATE scenes 
                            SET chapter_id = :chapter_id 
                            WHERE story_id = :story_id AND chapter_id IS NULL
                        """),
                        {"chapter_id": chapter_1.id, "story_id": story.id}
                    )
                    scenes_updated += result.rowcount
            
            session.commit()
            logger.info(f"✓ Linked {scenes_updated} scenes to their chapters")
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ Migration completed successfully!")
        logger.info("=" * 60)
        logger.info("\nSummary:")
        logger.info(f"  - Added story_mode column to stories")
        logger.info(f"  - Created chapters table")
        logger.info(f"  - Added chapter_id column to scenes")
        logger.info(f"  - Created {chapters_created} default chapters")
        logger.info(f"  - Linked {scenes_updated} scenes to chapters")
        
        return True
        
    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
