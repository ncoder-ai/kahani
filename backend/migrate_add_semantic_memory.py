"""
Add Semantic Memory Support

This migration adds tables for semantic memory, character moments, and plot events.
Enables vector embeddings and semantic search for improved story continuity.
"""

import sys
import os
from datetime import datetime

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.config import settings
from app.database import Base
from app.models import CharacterMemory, PlotEvent, SceneEmbedding

def run_migration():
    """Run the Semantic Memory migration"""
    print("🧠 Running Semantic Memory Migration...")
    
    # Create engine
    engine = create_engine(settings.database_url)
    
    # Create tables
    print("Creating Semantic Memory tables...")
    
    try:
        # Check if tables already exist
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='character_memories'"
            ))
            if result.fetchone():
                print("⚠️  Semantic Memory tables already exist. Skipping creation.")
                return
        
        # Create the new tables
        CharacterMemory.__table__.create(engine, checkfirst=True)
        PlotEvent.__table__.create(engine, checkfirst=True)
        SceneEmbedding.__table__.create(engine, checkfirst=True)
        
        print("✅ Semantic Memory tables created successfully!")
        print("\nCreated tables:")
        print("  - character_memories: Character-specific moments and memories")
        print("  - plot_events: Significant plot events and threads")
        print("  - scene_embeddings: Vector embeddings for semantic search")
        
        print("\n📋 Features:")
        print("  - Semantic search for relevant story moments")
        print("  - Character arc tracking and retrieval")
        print("  - Plot thread identification and resolution tracking")
        print("  - Hybrid context assembly (traditional + semantic)")
        
        print("\n🎯 Next Steps:")
        print("  1. Restart the backend server")
        print("  2. New scenes will automatically generate embeddings")
        print("  3. Optionally run migrate_existing_stories_to_semantic.py for existing stories")
        print("  4. Configure semantic settings in user settings if needed")
        
    except Exception as e:
        print(f"❌ Error running migration: {str(e)}")
        raise

def rollback_migration():
    """Rollback the Semantic Memory migration"""
    print("🔄 Rolling back Semantic Memory migration...")
    
    engine = create_engine(settings.database_url)
    
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS character_memories"))
            conn.execute(text("DROP TABLE IF EXISTS plot_events"))
            conn.execute(text("DROP TABLE IF EXISTS scene_embeddings"))
            conn.commit()
        
        print("✅ Semantic Memory tables dropped successfully!")
        
    except Exception as e:
        print(f"❌ Error rolling back migration: {str(e)}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Semantic Memory Migration")
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration"
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    else:
        run_migration()

