"""
Migration: Add auto_play_last_scene column to tts_settings table

This enables automatic TTS playback after scene generation completes.
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str):
    """Add auto_play_last_scene column to tts_settings table."""
    
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(tts_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'auto_play_last_scene' in columns:
            print("✓ Column 'auto_play_last_scene' already exists")
            return
        
        # Add the column
        print("Adding 'auto_play_last_scene' column...")
        cursor.execute("""
            ALTER TABLE tts_settings 
            ADD COLUMN auto_play_last_scene BOOLEAN DEFAULT 0
        """)
        
        conn.commit()
        print("✓ Successfully added 'auto_play_last_scene' column")
        
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Default database paths
    db_paths = [
        "data/kahani.db",
        "backend/data/kahani.db"
    ]
    
    # Use provided path or try defaults
    if len(sys.argv) > 1:
        db_paths = [sys.argv[1]]
    
    for db_path in db_paths:
        if Path(db_path).exists():
            print(f"\n{'='*60}")
            print(f"Migrating: {db_path}")
            print('='*60)
            migrate_database(db_path)
            break
    else:
        print("✗ Database not found. Please provide path as argument.")
        print("Usage: python migrate_add_auto_play.py [path/to/kahani.db]")
        sys.exit(1)
    
    print("\n✓ Migration completed successfully!")
