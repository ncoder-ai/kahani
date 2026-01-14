#!/usr/bin/env python3
"""
Test the interaction extraction - shows current state of interactions in the database.
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
        print(f"\n📊 Current state for story {story_id}:")
        
        # Count interactions
        result = session.execute(text("""
            SELECT COUNT(*) FROM character_interactions WHERE story_id = :story_id
        """), {"story_id": story_id})
        count = result.scalar()
        print(f"Interactions in DB: {count}")
        
        # Count scenes
        result = session.execute(text("""
            SELECT COUNT(*) FROM scenes WHERE story_id = :story_id
        """), {"story_id": story_id})
        scene_count = result.scalar()
        print(f"Total scenes: {scene_count}")
        
        if count > 0:
            print("\n📋 Current interactions:")
            result = session.execute(text("""
                SELECT 
                    ci.interaction_type,
                    cha.name as char_a,
                    chb.name as char_b,
                    ci.first_occurrence_scene,
                    s.sequence_number,
                    CASE 
                        WHEN ci.description LIKE '%fantasy%' THEN '⚠️  FANTASY' 
                        WHEN ci.description LIKE '%imagin%' THEN '⚠️  IMAGINED'
                        WHEN ci.description LIKE '%dream%' THEN '⚠️  DREAM'
                        ELSE '✅' 
                    END as status
                FROM character_interactions ci
                JOIN characters cha ON ci.character_a_id = cha.id
                JOIN characters chb ON ci.character_b_id = chb.id
                LEFT JOIN scenes s ON ci.first_occurrence_scene = s.id
                WHERE ci.story_id = :story_id
                ORDER BY s.sequence_number ASC, ci.first_occurrence_scene ASC
            """), {"story_id": story_id})
            
            print(f"\n{'Status':<15} {'Type':<25} {'Characters':<45} {'Scene':<10}")
            print("=" * 100)
            for row in result:
                seq = f"Seq #{row[4]}" if row[4] else "No seq"
                scene_info = f"{row[3]} ({seq})"
                chars = f"{row[1]} & {row[2]}"
                print(f"{row[5]:<15} {row[0]:<25} {chars:<45} {scene_info:<10}")
        
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    main()


