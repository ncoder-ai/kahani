#!/usr/bin/env python3
"""
Fix duplicate chapters in the database - Standalone version.

This script directly connects to the database without importing the full app.

Usage:
    python fix_duplicate_chapters_standalone.py
"""

import sys
import os
from sqlalchemy import create_engine, func, Column, Integer, String, Text, DateTime, ForeignKey, Table, Enum as SQLEnum
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase
import enum
from datetime import datetime

class Base(DeclarativeBase):
    pass

# Define minimal models needed for this script
class ChapterStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"

# Association table for chapter-character many-to-many relationship
chapter_characters = Table(
    'chapter_characters',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('chapter_id', Integer, ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False),
    Column('story_character_id', Integer, ForeignKey('story_characters.id', ondelete='CASCADE'), nullable=False),
)

class Story(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True)
    title = Column(String(200))

class StoryBranch(Base):
    __tablename__ = "story_branches"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    story_id = Column(Integer, ForeignKey("stories.id"))

class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(ChapterStatus), default=ChapterStatus.DRAFT, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Scene(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)  # NO CASCADE - this is the problem!
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    parent_scene_id = Column(Integer, ForeignKey("scenes.id"))  # Self-reference for branching

class SceneVariant(Base):
    __tablename__ = "scene_variants"
    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # NO CASCADE

class SceneChoice(Base):
    __tablename__ = "scene_choices"
    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # NO CASCADE
    scene_variant_id = Column(Integer, ForeignKey("scene_variants.id"))  # NO CASCADE
    leads_to_scene_id = Column(Integer, ForeignKey("scenes.id"))  # Self-reference, NO CASCADE

class StoryFlow(Base):
    __tablename__ = "story_flows"
    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # NO CASCADE
    scene_variant_id = Column(Integer, ForeignKey("scene_variants.id"), nullable=False)  # NO CASCADE
    from_choice_id = Column(Integer, ForeignKey("scene_choices.id"))  # NO CASCADE

class SceneAudio(Base):
    __tablename__ = "scene_audio"
    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # NO CASCADE

class ChapterSummaryBatch(Base):
    __tablename__ = "chapter_summary_batches"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=False)  # Has CASCADE in real model

def get_database_url():
    """Get database URL from environment or use default"""
    # First, try to get from environment variable (works in Docker)
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        print(f"Using DATABASE_URL from environment")
        return db_url
    
    # Try to read from .env file
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        print(f"Reading from .env file: {env_path}")
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    
    # Default to SQLite in backend directory
    db_path = os.path.join(os.path.dirname(__file__), 'backend', 'kahani.db')
    print(f"Using default SQLite path: {db_path}")
    return f"sqlite:///{db_path}"

def get_db_session():
    """Create database session"""
    database_url = get_database_url()
    print(f"Connecting to database: {database_url}")
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def find_duplicate_chapters(db):
    """Find all stories with duplicate chapter numbers"""
    # Query for duplicate chapter numbers within same story and branch
    duplicates = db.query(
        Chapter.story_id,
        Chapter.branch_id,
        Chapter.chapter_number,
        func.count(Chapter.id).label('count')
    ).group_by(
        Chapter.story_id,
        Chapter.branch_id,
        Chapter.chapter_number
    ).having(
        func.count(Chapter.id) > 1
    ).all()
    
    return duplicates

def get_chapter_details(db, story_id, branch_id, chapter_number):
    """Get all chapters with the same number"""
    query = db.query(Chapter).filter(
        Chapter.story_id == story_id,
        Chapter.chapter_number == chapter_number
    )
    
    if branch_id:
        query = query.filter(Chapter.branch_id == branch_id)
    
    chapters = query.order_by(Chapter.created_at).all()
    
    details = []
    for chapter in chapters:
        # Count scenes
        scene_count = db.query(Scene).filter(Scene.chapter_id == chapter.id).count()
        
        details.append({
            'chapter': chapter,
            'scene_count': scene_count
        })
    
    return details

def delete_chapter(db, chapter_id):
    """Delete a chapter and all its related data in the correct order"""
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    
    if not chapter:
        print(f"Chapter {chapter_id} not found")
        return False
    
    print(f"\nDeleting chapter {chapter_id}...")
    
    # Get all scenes in this chapter first
    scenes = db.query(Scene).filter(Scene.chapter_id == chapter_id).all()
    scene_ids = [scene.id for scene in scenes]
    
    if not scene_ids:
        # No scenes, safe to delete chapter and its direct associations
        print(f"  - No scenes found in chapter")
        db.execute(chapter_characters.delete().where(chapter_characters.c.chapter_id == chapter_id))
        batch_count = db.query(ChapterSummaryBatch).filter(
            ChapterSummaryBatch.chapter_id == chapter_id
        ).delete(synchronize_session=False)
        db.delete(chapter)
        db.commit()
        print(f"  ✓ Chapter {chapter_id} deleted successfully")
        return True
    
    # Get all scene variant IDs for these scenes
    variant_ids = []
    variants = db.query(SceneVariant).filter(SceneVariant.scene_id.in_(scene_ids)).all()
    variant_ids = [v.id for v in variants]
    
    print(f"  - Found {len(scenes)} scene(s) and {len(variants)} variant(s)")
    
    # CRITICAL: Delete in this exact order to avoid foreign key violations
    # The order respects the dependency chain from the database schema
    
    # 1. Delete chapter-character associations (has CASCADE but delete explicitly)
    assoc_result = db.execute(chapter_characters.delete().where(chapter_characters.c.chapter_id == chapter_id))
    print(f"  - Deleted {assoc_result.rowcount} chapter-character association(s)")
    
    # 2. Delete summary batches (has CASCADE but delete explicitly)
    batch_count = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).delete(synchronize_session=False)
    print(f"  - Deleted {batch_count} summary batch(es)")
    
    # 3. Delete scene_audio entries (references scenes, NO CASCADE)
    audio_count = db.query(SceneAudio).filter(
        SceneAudio.scene_id.in_(scene_ids)
    ).delete(synchronize_session=False)
    print(f"  - Deleted {audio_count} scene audio record(s)")
    
    # 4. Delete story_flows (references scene_choices, scene_variants, and scenes - NO CASCADE)
    flow_count = db.query(StoryFlow).filter(
        StoryFlow.scene_id.in_(scene_ids)
    ).delete(synchronize_session=False)
    print(f"  - Deleted {flow_count} story flow entrie(s)")
    
    # 5. Delete scene_choices (references scene_variants and scenes, NO CASCADE)
    # IMPORTANT: Must handle self-reference via leads_to_scene_id
    # First, set leads_to_scene_id to NULL for any choices that point to our scenes
    nullify_count = db.query(SceneChoice).filter(
        SceneChoice.leads_to_scene_id.in_(scene_ids)
    ).update({SceneChoice.leads_to_scene_id: None}, synchronize_session=False)
    if nullify_count > 0:
        print(f"  - Nullified {nullify_count} scene_choice.leads_to_scene_id reference(s)")
    
    # Now safe to delete scene_choices belonging to our scenes
    choice_count = db.query(SceneChoice).filter(
        SceneChoice.scene_id.in_(scene_ids)
    ).delete(synchronize_session=False)
    print(f"  - Deleted {choice_count} scene choice(s)")
    
    # 6. Delete scene_variants (references scenes, NO CASCADE)
    variant_count = db.query(SceneVariant).filter(
        SceneVariant.scene_id.in_(scene_ids)
    ).delete(synchronize_session=False)
    print(f"  - Deleted {variant_count} scene variant(s)")
    
    # 7. Delete scenes (references chapters, NO CASCADE - this is the root cause!)
    # IMPORTANT: Must handle self-reference via parent_scene_id
    # First, set parent_scene_id to NULL for any scenes that point to our scenes
    parent_nullify_count = db.query(Scene).filter(
        Scene.parent_scene_id.in_(scene_ids)
    ).update({Scene.parent_scene_id: None}, synchronize_session=False)
    if parent_nullify_count > 0:
        print(f"  - Nullified {parent_nullify_count} scene.parent_scene_id reference(s)")
    
    # Now safe to delete our scenes - MUST use query delete, not ORM delete!
    scene_count = db.query(Scene).filter(
        Scene.chapter_id == chapter_id
    ).delete(synchronize_session=False)
    print(f"  - Deleted {scene_count} scene(s)")
    
    # 8. Finally, delete the chapter itself (now nothing references it)
    chapter_delete_count = db.query(Chapter).filter(
        Chapter.id == chapter_id
    ).delete(synchronize_session=False)
    print(f"  - Deleted chapter {chapter_id}")
    
    db.commit()
    print(f"  ✓ Chapter {chapter_id} deleted successfully")
    
    return True

def main():
    print("=" * 80)
    print("DUPLICATE CHAPTER FIXER - Standalone Version")
    print("=" * 80)
    print()
    
    try:
        db = get_db_session()
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        print("\nMake sure:")
        print("1. Your database file exists at: backend/kahani.db")
        print("2. Or set DATABASE_URL in your .env file")
        return
    
    try:
        # Find duplicates
        duplicates = find_duplicate_chapters(db)
        
        if not duplicates:
            print("✓ No duplicate chapters found!")
            return
        
        print(f"Found {len(duplicates)} story/branch combinations with duplicate chapters:\n")
        
        for dup in duplicates:
            story_id, branch_id, chapter_number, count = dup
            
            # Get story name
            story = db.query(Story).filter(Story.id == story_id).first()
            story_name = story.title if story else f"Story {story_id}"
            
            # Get branch name
            if branch_id:
                branch = db.query(StoryBranch).filter(StoryBranch.id == branch_id).first()
                branch_name = branch.name if branch else f"Branch {branch_id}"
            else:
                branch_name = "Main"
            
            print(f"\n{'=' * 80}")
            print(f"Story: {story_name} (ID: {story_id})")
            print(f"Branch: {branch_name} (ID: {branch_id})")
            print(f"Chapter Number: {chapter_number}")
            print(f"Duplicate Count: {count}")
            print(f"{'=' * 80}\n")
            
            # Get chapter details
            chapter_details = get_chapter_details(db, story_id, branch_id, chapter_number)
            
            print("Found these duplicate chapters:\n")
            for i, detail in enumerate(chapter_details, 1):
                chapter = detail['chapter']
                scene_count = detail['scene_count']
                
                print(f"{i}. Chapter ID: {chapter.id}")
                print(f"   Title: {chapter.title or '(No title)'}")
                print(f"   Status: {chapter.status.value}")
                print(f"   Scenes: {scene_count}")
                print(f"   Created: {chapter.created_at}")
                print(f"   Description: {chapter.description[:100] if chapter.description else '(No description)'}...")
                print()
            
            # Ask user which to keep
            while True:
                print(f"Which chapter do you want to KEEP? (1-{len(chapter_details)})")
                print("Enter the number, or 's' to skip this story, or 'q' to quit:")
                choice = input("> ").strip().lower()
                
                if choice == 'q':
                    print("\nExiting...")
                    return
                
                if choice == 's':
                    print("\nSkipping this story...")
                    break
                
                try:
                    keep_index = int(choice) - 1
                    if 0 <= keep_index < len(chapter_details):
                        # Delete all others
                        for i, detail in enumerate(chapter_details):
                            if i != keep_index:
                                delete_chapter(db, detail['chapter'].id)
                        
                        print(f"\n✓ Kept chapter {chapter_details[keep_index]['chapter'].id}")
                        break
                    else:
                        print(f"Invalid choice. Please enter 1-{len(chapter_details)}")
                except ValueError:
                    print("Invalid input. Please enter a number, 's', or 'q'")
        
        print("\n" + "=" * 80)
        print("✓ All duplicates processed!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
