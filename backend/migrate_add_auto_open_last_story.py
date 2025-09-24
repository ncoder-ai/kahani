#!/usr/bin/env python3
"""
Migration script to add auto_open_last_story and last_accessed_story_id columns to user_settings table.
"""

import sqlite3
import os
from pathlib import Path

def add_auto_open_last_story_columns():
    """Add auto_open_last_story and last_accessed_story_id columns to user_settings table"""
    
    # Database path
    db_path = Path(__file__).parent / "data" / "kahani.db"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Check if columns already exist
            cursor.execute("PRAGMA table_info(user_settings)")
            columns = [column[1] for column in cursor.fetchall()]
            
            print(f"Existing columns in user_settings: {columns}")
            
            # Add auto_open_last_story column if it doesn't exist
            if 'auto_open_last_story' not in columns:
                print("Adding auto_open_last_story column...")
                cursor.execute(
                    "ALTER TABLE user_settings ADD COLUMN auto_open_last_story BOOLEAN DEFAULT 0"
                )
                print("✅ Added auto_open_last_story column")
            else:
                print("auto_open_last_story column already exists")
            
            # Add last_accessed_story_id column if it doesn't exist
            if 'last_accessed_story_id' not in columns:
                print("Adding last_accessed_story_id column...")
                cursor.execute(
                    "ALTER TABLE user_settings ADD COLUMN last_accessed_story_id INTEGER DEFAULT NULL"
                )
                print("✅ Added last_accessed_story_id column")
            else:
                print("last_accessed_story_id column already exists")
            
            conn.commit()
            
            # Verify the changes
            cursor.execute("PRAGMA table_info(user_settings)")
            updated_columns = [column[1] for column in cursor.fetchall()]
            print(f"Updated columns in user_settings: {updated_columns}")
            
            return True
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Adding auto_open_last_story settings to user_settings table...")
    success = add_auto_open_last_story_columns()
    
    if success:
        print("✅ Migration completed successfully!")
        print("\nNew settings added:")
        print("- auto_open_last_story: Boolean flag to enable auto-redirect to last story")
        print("- last_accessed_story_id: ID of the last story the user worked on")
    else:
        print("❌ Migration failed!")