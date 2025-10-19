"""
Add Semantic Memory Support - Simple Migration

This migration adds tables for semantic memory without importing heavy dependencies.
"""

import sqlite3
import sys
import os

# Get database path
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "kahani.db")

def run_migration():
    """Run the Semantic Memory migration"""
    print("🧠 Running Semantic Memory Migration...")
    print(f"Database: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='character_memories'")
        if cursor.fetchone():
            print("⚠️  Semantic Memory tables already exist. Skipping creation.")
            conn.close()
            return
        
        print("Creating character_memories table...")
        cursor.execute("""
            CREATE TABLE character_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                summary TEXT,
                moment_type VARCHAR(50) DEFAULT 'OTHER',
                relevance_score REAL DEFAULT 0.0,
                metadata_ TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX ix_character_memories_id ON character_memories(id)")
        cursor.execute("CREATE INDEX ix_character_memories_story_id ON character_memories(story_id)")
        cursor.execute("CREATE INDEX ix_character_memories_character_id ON character_memories(character_id)")
        cursor.execute("CREATE INDEX ix_character_memories_scene_id ON character_memories(scene_id)")
        
        print("Creating plot_events table...")
        cursor.execute("""
            CREATE TABLE plot_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                event_type VARCHAR(50) DEFAULT 'OTHER',
                description TEXT NOT NULL,
                importance_score REAL DEFAULT 0.0,
                metadata_ TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX ix_plot_events_id ON plot_events(id)")
        cursor.execute("CREATE INDEX ix_plot_events_story_id ON plot_events(story_id)")
        cursor.execute("CREATE INDEX ix_plot_events_scene_id ON plot_events(scene_id)")
        
        print("Creating scene_embeddings table...")
        cursor.execute("""
            CREATE TABLE scene_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                variant_id INTEGER NOT NULL,
                embedding_id VARCHAR(200) NOT NULL UNIQUE,
                content_hash VARCHAR(64) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
                FOREIGN KEY (variant_id) REFERENCES scene_variants(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX ix_scene_embeddings_id ON scene_embeddings(id)")
        cursor.execute("CREATE INDEX ix_scene_embeddings_story_id ON scene_embeddings(story_id)")
        cursor.execute("CREATE INDEX ix_scene_embeddings_scene_id ON scene_embeddings(scene_id)")
        cursor.execute("CREATE INDEX ix_scene_embeddings_variant_id ON scene_embeddings(variant_id)")
        cursor.execute("CREATE UNIQUE INDEX ix_scene_embeddings_embedding_id ON scene_embeddings(embedding_id)")
        
        conn.commit()
        
        print("✅ Semantic Memory tables created successfully!")
        print("\nCreated tables:")
        print("  - character_memories: Character-specific moments and memories")
        print("  - plot_events: Significant plot events and threads")
        print("  - scene_embeddings: Vector embeddings for semantic search")
        
        print("\n📋 Features:")
        print("  - Semantic search for relevant story moments")
        print("  - Character arc tracking and retrieval")
        print("  - Plot thread identification")
        print("  - Hybrid context assembly (traditional + semantic)")
        
        print("\n🎯 Next Steps:")
        print("  1. Start the backend server")
        print("  2. New scenes will automatically generate embeddings")
        print("  3. Optionally run migrate_existing_stories_to_semantic.py for existing stories")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error running migration: {str(e)}")
        raise
    finally:
        conn.close()

def rollback_migration():
    """Rollback the Semantic Memory migration"""
    print("🔄 Rolling back Semantic Memory migration...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("DROP TABLE IF EXISTS character_memories")
        cursor.execute("DROP TABLE IF EXISTS plot_events")
        cursor.execute("DROP TABLE IF EXISTS scene_embeddings")
        conn.commit()
        
        print("✅ Semantic Memory tables dropped successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error rolling back migration: {str(e)}")
        raise
    finally:
        conn.close()

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

