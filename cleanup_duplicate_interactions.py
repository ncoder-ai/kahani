#!/usr/bin/env python3
"""
Clean up duplicate character interactions, keeping only the first occurrence
of each interaction type per character pair.
"""
import sys
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

def get_db_url():
    """Get database URL from environment."""
    return os.environ.get('DATABASE_URL', 'postgresql://kahani_user:kahani_pass@postgres:5432/kahani_db')

def main():
    story_id = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    
    engine = create_engine(get_db_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # First, show what we have
        result = session.execute(text("""
            SELECT 
                ci.interaction_type,
                cha.name as char_a,
                chb.name as char_b,
                COUNT(*) as count
            FROM character_interactions ci
            JOIN characters cha ON ci.character_a_id = cha.id
            JOIN characters chb ON ci.character_b_id = chb.id
            WHERE ci.story_id = :story_id
            GROUP BY ci.interaction_type, cha.name, chb.name
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        """), {"story_id": story_id})
        
        duplicates = result.fetchall()
        
        if not duplicates:
            print(f"✅ No duplicates found for story {story_id}")
            return
        
        print(f"\n📊 Found {len(duplicates)} duplicate interaction types:\n")
        for row in duplicates:
            print(f"  - {row[0]}: {row[1]} & {row[2]} ({row[3]} occurrences)")
        
        # Delete duplicates, keeping only the one with the lowest scene number
        # (which represents the true first occurrence)
        delete_query = text("""
            DELETE FROM character_interactions ci1
            WHERE ci1.story_id = :story_id
            AND EXISTS (
                SELECT 1 FROM character_interactions ci2
                WHERE ci1.story_id = ci2.story_id
                AND ci1.character_a_id = ci2.character_a_id
                AND ci1.character_b_id = ci2.character_b_id
                AND ci1.interaction_type = ci2.interaction_type
                AND (
                    ci1.first_occurrence_scene > ci2.first_occurrence_scene
                    OR (ci1.first_occurrence_scene = ci2.first_occurrence_scene AND ci1.id > ci2.id)
                )
            )
        """)
        
        result = session.execute(delete_query, {"story_id": story_id})
        deleted_count = result.rowcount
        session.commit()
        
        print(f"\n✅ Deleted {deleted_count} duplicate interactions")
        
        # Show what remains
        result = session.execute(text("""
            SELECT COUNT(*) FROM character_interactions WHERE story_id = :story_id
        """), {"story_id": story_id})
        remaining = result.scalar()
        
        print(f"📊 {remaining} unique interactions remaining")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()


