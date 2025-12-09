#!/usr/bin/env python3
"""
Fix duplicate chapters in the database.

This script will:
1. Find all stories with duplicate chapter numbers on the same branch
2. Show you the duplicates
3. Let you choose which one to keep
4. Delete the unwanted chapter and all its related data

Usage:
    python fix_duplicate_chapters.py
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from app.models import Chapter, Scene, ChapterSummaryBatch, Story, StoryBranch
from app.models.chapter import chapter_characters
from app.config import settings

def get_db_session():
    """Create database session"""
    engine = create_engine(settings.database_url)
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
    """Delete a chapter and all its related data"""
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    
    if not chapter:
        print(f"Chapter {chapter_id} not found")
        return False
    
    print(f"\nDeleting chapter {chapter_id}...")
    
    # Delete chapter-character associations
    db.execute(chapter_characters.delete().where(chapter_characters.c.chapter_id == chapter_id))
    print(f"  - Deleted chapter-character associations")
    
    # Delete summary batches
    batch_count = db.query(ChapterSummaryBatch).filter(
        ChapterSummaryBatch.chapter_id == chapter_id
    ).delete()
    print(f"  - Deleted {batch_count} summary batch(es)")
    
    # Delete scenes (CASCADE should handle scene variants, story flow, etc.)
    scene_count = db.query(Scene).filter(Scene.chapter_id == chapter_id).delete()
    print(f"  - Deleted {scene_count} scene(s)")
    
    # Delete the chapter itself
    db.delete(chapter)
    
    db.commit()
    print(f"  ✓ Chapter {chapter_id} deleted successfully")
    
    return True

def main():
    print("=" * 80)
    print("DUPLICATE CHAPTER FIXER")
    print("=" * 80)
    print()
    
    db = get_db_session()
    
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
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
