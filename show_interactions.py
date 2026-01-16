#!/usr/bin/env python3
"""
Simple script to display extracted character interactions from the database.
Shows interaction type, characters, scene ID, and description only (no scene content).
"""
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_db_url():
    """Get database URL from environment or config."""
    return os.environ.get('DATABASE_URL', 'postgresql://kahani_user:kahani_pass@postgres:5432/kahani_db')

def main():
    story_id = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    
    engine = create_engine(get_db_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Query to get interactions WITHOUT scene content
        query = text("""
            SELECT 
                ci.id,
                ci.interaction_type,
                ci.first_occurrence_scene,
                ci.description,
                cha.name as character_a,
                chb.name as character_b,
                s.sequence_number,
                ci.created_at
            FROM character_interactions ci
            JOIN characters cha ON ci.character_a_id = cha.id
            JOIN characters chb ON ci.character_b_id = chb.id
            LEFT JOIN scenes s ON ci.first_occurrence_scene = s.id
            WHERE ci.story_id = :story_id
            ORDER BY s.sequence_number ASC, ci.created_at ASC
        """)
        
        results = session.execute(query, {"story_id": story_id}).fetchall()
        
        if not results:
            print(f"\n❌ No interactions found for story {story_id}")
            print("\nThis could mean:")
            print("1. The extraction hasn't run yet")
            print("2. No interactions were detected in the scenes")
            print("3. The story has no scenes yet")
            return
        
        print(f"\n✅ Found {len(results)} interactions for story {story_id}\n")
        print("=" * 120)
        print(f"{'#':<4} {'Type':<25} {'Characters':<40} {'Scene':<12} {'Description':<50}")
        print("=" * 120)
        
        for idx, row in enumerate(results, 1):
            interaction_type = row[1]
            scene_id = row[2]
            description = row[3]
            char_a = row[4]
            char_b = row[5]
            sequence_number = row[6]
            
            # Truncate description for table display
            desc_short = (description[:47] + '...') if len(description) > 50 else description
            characters = f"{char_a} ↔ {char_b}"
            seq = f"Seq #{sequence_number}" if sequence_number else "No seq"
            scene_info = f"{scene_id} ({seq})"
            
            print(f"{idx:<4} {interaction_type:<25} {characters:<40} {scene_info:<12} {desc_short:<50}")
        
        print("=" * 120)
        print(f"\nTotal: {len(results)} interactions\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    main()



