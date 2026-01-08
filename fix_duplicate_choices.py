#!/usr/bin/env python3
"""
Fix duplicate choices in the database.

This script removes duplicate SceneChoice records that were created when a user
selected an existing AI-generated choice to continue the story. The bug caused
a duplicate choice record to be created with is_user_created=True, even though
the original AI-generated choice already existed.

Usage:
    # Preview what would be deleted (dry run)
    python fix_duplicate_choices.py --dry-run
    
    # Actually delete the duplicates
    python fix_duplicate_choices.py
    
    # Delete duplicates for a specific story
    python fix_duplicate_choices.py --story-id 5
"""

import os
import sys
import argparse

# Add the backend directory to the path so we can import the models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def get_database_url():
    """Get database URL from environment or .env file"""
    # Try environment variable first
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return db_url
    
    # Try loading from .env file
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    return line.split('=', 1)[1].strip('"\'')
    
    # Default PostgreSQL connection for Docker setup
    return 'postgresql://kahani:kahani@localhost:5432/kahani'


def find_duplicate_choices(session, story_id=None):
    """
    Find duplicate choices where the same text exists twice for the same variant,
    once as AI-generated (is_user_created=False) and once as user-created (is_user_created=True).
    """
    from sqlalchemy import text
    
    # Query to find duplicates
    query = """
    SELECT 
        sc2.id as duplicate_id,
        sc2.scene_variant_id,
        sc2.choice_text,
        sc2.is_user_created as duplicate_is_user_created,
        sc1.id as original_id,
        sc1.is_user_created as original_is_user_created,
        sv.scene_id,
        s.story_id
    FROM scene_choices sc1
    JOIN scene_choices sc2 ON sc1.scene_variant_id = sc2.scene_variant_id 
        AND sc1.choice_text = sc2.choice_text 
        AND sc1.id < sc2.id
    JOIN scene_variants sv ON sc1.scene_variant_id = sv.id
    JOIN scenes s ON sv.scene_id = s.id
    WHERE sc2.is_user_created = true 
        AND sc1.is_user_created = false
    """
    
    if story_id:
        query += f" AND s.story_id = {story_id}"
    
    query += " ORDER BY s.story_id, sv.scene_id, sc1.id"
    
    result = session.execute(text(query))
    return result.fetchall()


def delete_duplicate_choices(session, duplicate_ids, dry_run=False):
    """Delete the duplicate choice records."""
    from sqlalchemy import text
    
    if not duplicate_ids:
        print("No duplicates to delete.")
        return 0
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete {len(duplicate_ids)} duplicate choice(s)")
        return len(duplicate_ids)
    
    # Delete the duplicates
    ids_str = ','.join(str(id) for id in duplicate_ids)
    delete_query = f"DELETE FROM scene_choices WHERE id IN ({ids_str})"
    session.execute(text(delete_query))
    session.commit()
    
    print(f"\nDeleted {len(duplicate_ids)} duplicate choice(s)")
    return len(duplicate_ids)


def main():
    parser = argparse.ArgumentParser(description='Fix duplicate choices in the database')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Preview what would be deleted without actually deleting')
    parser.add_argument('--story-id', type=int, 
                        help='Only fix duplicates for a specific story ID')
    args = parser.parse_args()
    
    # Get database connection
    db_url = get_database_url()
    print(f"Connecting to database...")
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Find duplicates
        print(f"\nSearching for duplicate choices" + 
              (f" in story {args.story_id}" if args.story_id else "") + "...")
        
        duplicates = find_duplicate_choices(session, args.story_id)
        
        if not duplicates:
            print("No duplicate choices found!")
            return
        
        print(f"\nFound {len(duplicates)} duplicate choice(s):\n")
        print(f"{'Story':<8} {'Scene':<8} {'Variant':<10} {'Original ID':<12} {'Duplicate ID':<14} Choice Text")
        print("-" * 100)
        
        duplicate_ids = []
        for row in duplicates:
            duplicate_id = row[0]
            variant_id = row[1]
            choice_text = row[2][:50] + "..." if len(row[2]) > 50 else row[2]
            original_id = row[4]
            scene_id = row[6]
            story_id = row[7]
            
            print(f"{story_id:<8} {scene_id:<8} {variant_id:<10} {original_id:<12} {duplicate_id:<14} {choice_text}")
            duplicate_ids.append(duplicate_id)
        
        # Delete duplicates
        print()
        if args.dry_run:
            print("=" * 50)
            print("DRY RUN MODE - No changes will be made")
            print("=" * 50)
        
        delete_duplicate_choices(session, duplicate_ids, args.dry_run)
        
        if not args.dry_run:
            print("\nDuplicates have been removed successfully!")
        else:
            print("\nRun without --dry-run to actually delete the duplicates.")
            
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    main()

