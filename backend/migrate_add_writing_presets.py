#!/usr/bin/env python3
"""
Migration: Add Writing Style Presets

Creates the writing_style_presets table and initializes default presets for existing users.
This replaces the old prompt_templates approach with a simpler, more user-friendly system.

Usage:
    python migrate_add_writing_presets.py [--db-path PATH]
"""

import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import argparse

# Default system prompt for new presets
DEFAULT_SYSTEM_PROMPT = """You are a creative storytelling assistant. Write in an engaging narrative style that:
- Uses vivid, descriptive language to paint clear mental images
- Creates immersive scenes that draw readers into the story world
- Develops characters naturally through their actions, dialogue, and decisions
- Maintains appropriate pacing to keep the story moving forward
- Respects the genre, tone, and themes specified by the user

Keep content appropriate for general audiences unless explicitly told otherwise by the user. Write in second person ("you") for interactive stories to create an immersive experience."""

DEFAULT_PRESET_NAME = "Default"
DEFAULT_PRESET_DESCRIPTION = "Balanced, engaging storytelling suitable for all genres"


def get_db_path():
    """Determine the database path"""
    parser = argparse.ArgumentParser(description='Migrate database to add writing style presets')
    parser.add_argument('--db-path', type=str, help='Path to the database file')
    args = parser.parse_args()
    
    if args.db_path:
        return args.db_path
    
    # Try common locations
    possible_paths = [
        'data/kahani.db',
        'backend/data/kahani.db',
        '../data/kahani.db',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    print("Error: Could not find database file. Please specify with --db-path")
    sys.exit(1)


def create_backup(db_path):
    """Create a backup of the database before migration"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(db_path).parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    backup_path = backup_dir / f"kahani_backup_{timestamp}_writing_presets.db"
    
    print(f"Creating backup at {backup_path}...")
    
    # Copy the database
    import shutil
    shutil.copy2(db_path, backup_path)
    
    print(f"Backup created successfully!")
    return backup_path


def table_exists(cursor, table_name):
    """Check if a table exists in the database"""
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    return cursor.fetchone() is not None


def create_writing_style_presets_table(cursor):
    """Create the writing_style_presets table"""
    print("Creating writing_style_presets table...")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS writing_style_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            system_prompt TEXT NOT NULL,
            summary_system_prompt TEXT,
            is_active BOOLEAN DEFAULT 0 NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Create index for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_writing_presets_user_active 
        ON writing_style_presets(user_id, is_active)
    """)
    
    print("✓ Table created successfully")


def get_all_users(cursor):
    """Get all users from the database"""
    cursor.execute("SELECT id FROM users")
    return [row[0] for row in cursor.fetchall()]


def create_default_preset_for_user(cursor, user_id):
    """Create a default preset for a user"""
    now = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT INTO writing_style_presets 
        (user_id, name, description, system_prompt, summary_system_prompt, is_active, created_at)
        VALUES (?, ?, ?, ?, NULL, 1, ?)
    """, (user_id, DEFAULT_PRESET_NAME, DEFAULT_PRESET_DESCRIPTION, DEFAULT_SYSTEM_PROMPT, now))


def migrate_database(db_path):
    """Run the migration"""
    print(f"\n{'='*60}")
    print(f"Writing Style Presets Migration")
    print(f"Database: {db_path}")
    print(f"{'='*60}\n")
    
    # Create backup first
    backup_path = create_backup(db_path)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        if table_exists(cursor, 'writing_style_presets'):
            print("⚠️  Table 'writing_style_presets' already exists!")
            response = input("Do you want to continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Migration cancelled.")
                return
        
        # Create the table
        create_writing_style_presets_table(cursor)
        
        # Get all users
        users = get_all_users(cursor)
        print(f"\nFound {len(users)} users")
        
        if users:
            print("Creating default presets for existing users...")
            for user_id in users:
                create_default_preset_for_user(cursor, user_id)
                print(f"  ✓ Created default preset for user {user_id}")
        
        # Commit changes
        conn.commit()
        
        # Verify migration
        cursor.execute("SELECT COUNT(*) FROM writing_style_presets")
        preset_count = cursor.fetchone()[0]
        
        print(f"\n{'='*60}")
        print(f"Migration completed successfully! ✅")
        print(f"{'='*60}")
        print(f"  - Created writing_style_presets table")
        print(f"  - Created {preset_count} default presets")
        print(f"  - Backup saved to: {backup_path}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print(f"Rolling back changes...")
        conn.rollback()
        print(f"Database restored from backup: {backup_path}")
        raise
    
    finally:
        conn.close()


def verify_migration(db_path):
    """Verify the migration was successful"""
    print("\nVerifying migration...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check table exists
        if not table_exists(cursor, 'writing_style_presets'):
            print("❌ Table not found!")
            return False
        
        # Check structure
        cursor.execute("PRAGMA table_info(writing_style_presets)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {
            'id', 'user_id', 'name', 'description', 'system_prompt',
            'summary_system_prompt', 'is_active', 'created_at', 'updated_at'
        }
        
        if not required_columns.issubset(columns):
            print(f"❌ Missing columns: {required_columns - columns}")
            return False
        
        # Check data
        cursor.execute("SELECT COUNT(*) FROM writing_style_presets")
        preset_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        print(f"✓ Table structure is correct")
        print(f"✓ Found {preset_count} presets for {user_count} users")
        
        # Show sample
        cursor.execute("""
            SELECT id, user_id, name, is_active 
            FROM writing_style_presets 
            LIMIT 3
        """)
        
        print("\nSample presets:")
        for row in cursor.fetchall():
            print(f"  - ID: {row[0]}, User: {row[1]}, Name: '{row[2]}', Active: {bool(row[3])}")
        
        return True
        
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        db_path = get_db_path()
        migrate_database(db_path)
        
        if verify_migration(db_path):
            print("\n✅ Migration verified successfully!\n")
            sys.exit(0)
        else:
            print("\n❌ Migration verification failed!\n")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

