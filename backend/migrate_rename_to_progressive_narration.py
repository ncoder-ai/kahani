#!/usr/bin/env python3
"""
Database Migration: Rename auto_narrate_new_scenes to progressive_narration

This script renames the column to better reflect its actual purpose:
- OLD: auto_narrate_new_scenes (misleading name, sounded like automation)
- NEW: progressive_narration (accurate: enables chunked playback)

Purpose:
- progressive_narration: When enabled, splits scenes into chunks for progressive playback
- This is NOT about auto-generating TTS (that's a future feature)
- This is about chunking strategy for faster audio start

Usage:
    python migrate_rename_to_progressive_narration.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text, inspect
from app.database import engine, SessionLocal

def backup_database():
    """Create a backup before migration"""
    db_path = backend_dir / "data" / "kahani.db"
    if db_path.exists():
        backup_path = backend_dir / "data" / f"kahani_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_progressive_narration_rename.db"
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
        return backup_path
    return None

def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def rename_column():
    """Rename auto_narrate_new_scenes to progressive_narration"""
    db = SessionLocal()
    try:
        # Check current state
        has_old = check_column_exists('tts_settings', 'auto_narrate_new_scenes')
        has_new = check_column_exists('tts_settings', 'progressive_narration')
        
        print("\n📊 Current Schema State:")
        print(f"   - auto_narrate_new_scenes exists: {has_old}")
        print(f"   - progressive_narration exists: {has_new}")
        
        if has_new and not has_old:
            print("\n✅ Migration already complete!")
            print("   The progressive_narration column already exists.")
            return True
        
        if not has_old:
            print("\n⚠️  Warning: auto_narrate_new_scenes column not found!")
            print("   This might be a fresh database. Creating progressive_narration column...")
            
            # Just add the new column (for fresh databases)
            db.execute(text("""
                ALTER TABLE tts_settings 
                ADD COLUMN progressive_narration BOOLEAN DEFAULT 0
            """))
            db.commit()
            print("✅ Created progressive_narration column")
            return True
        
        # Both columns exist or need migration
        if has_old:
            print("\n🔄 Starting migration...")
            
            if has_new:
                print("   Both columns exist. Copying data from old to new...")
                # Copy data from old to new
                db.execute(text("""
                    UPDATE tts_settings 
                    SET progressive_narration = auto_narrate_new_scenes
                """))
                db.commit()
                print("   ✅ Data copied")
            else:
                print("   Renaming column...")
                # SQLite doesn't support direct column rename, so we need to:
                # 1. Add new column
                # 2. Copy data
                # 3. Drop old column (requires table recreation in SQLite)
                
                # Add new column
                db.execute(text("""
                    ALTER TABLE tts_settings 
                    ADD COLUMN progressive_narration BOOLEAN DEFAULT 0
                """))
                db.commit()
                print("   ✅ Created new column")
                
                # Copy data
                db.execute(text("""
                    UPDATE tts_settings 
                    SET progressive_narration = auto_narrate_new_scenes
                """))
                db.commit()
                print("   ✅ Copied data from old column")
            
            # Now we need to recreate the table without the old column
            # This is the SQLite way to drop a column
            print("   Recreating table to remove old column...")
            
            # Get all data
            result = db.execute(text("SELECT * FROM tts_settings")).fetchall()
            columns = db.execute(text("PRAGMA table_info(tts_settings)")).fetchall()
            
            # Create new table without auto_narrate_new_scenes
            db.execute(text("ALTER TABLE tts_settings RENAME TO tts_settings_old"))
            db.commit()
            print("   ✅ Renamed old table")
            
            # Get CREATE TABLE statement for new table
            # We'll build it from the model structure
            db.execute(text("""
                CREATE TABLE tts_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    tts_enabled BOOLEAN DEFAULT 0,
                    tts_provider_type VARCHAR(50) DEFAULT 'openai-compatible',
                    tts_api_url VARCHAR(500) DEFAULT '',
                    tts_api_key VARCHAR(500) DEFAULT '',
                    tts_timeout INTEGER DEFAULT 30,
                    tts_retry_attempts INTEGER DEFAULT 3,
                    tts_custom_headers JSON,
                    tts_extra_params JSON,
                    default_voice VARCHAR(100) DEFAULT 'Sara',
                    speech_speed FLOAT DEFAULT 1.0,
                    audio_format VARCHAR(10) DEFAULT 'mp3',
                    progressive_narration BOOLEAN DEFAULT 0,
                    chunk_size INTEGER DEFAULT 280,
                    stream_audio BOOLEAN DEFAULT 1,
                    pause_between_paragraphs BOOLEAN DEFAULT 1,
                    volume FLOAT DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            db.commit()
            print("   ✅ Created new table structure")
            
            # Copy data to new table
            db.execute(text("""
                INSERT INTO tts_settings 
                SELECT 
                    id, user_id, tts_enabled, tts_provider_type, tts_api_url, 
                    tts_api_key, tts_timeout, tts_retry_attempts, tts_custom_headers,
                    tts_extra_params, default_voice, speech_speed, audio_format,
                    progressive_narration, chunk_size, stream_audio,
                    pause_between_paragraphs, volume, created_at, updated_at
                FROM tts_settings_old
            """))
            db.commit()
            print("   ✅ Copied data to new table")
            
            # Drop old table
            db.execute(text("DROP TABLE tts_settings_old"))
            db.commit()
            print("   ✅ Dropped old table")
            
            print("\n✅ Migration completed successfully!")
            print(f"   Migrated {len(result)} row(s)")
            
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def verify_migration():
    """Verify the migration was successful"""
    print("\n🔍 Verifying migration...")
    db = SessionLocal()
    try:
        # Check column exists
        has_new = check_column_exists('tts_settings', 'progressive_narration')
        has_old = check_column_exists('tts_settings', 'auto_narrate_new_scenes')
        
        print(f"   - progressive_narration column exists: {has_new}")
        print(f"   - auto_narrate_new_scenes column exists: {has_old}")
        
        if has_new and not has_old:
            # Check data
            result = db.execute(text("SELECT COUNT(*) FROM tts_settings WHERE progressive_narration IS NOT NULL")).fetchone()
            count = result[0] if result else 0
            print(f"   - Rows with progressive_narration data: {count}")
            print("\n✅ Verification passed!")
            return True
        else:
            print("\n⚠️  Verification failed!")
            if not has_new:
                print("   - progressive_narration column missing!")
            if has_old:
                print("   - auto_narrate_new_scenes column still exists!")
            return False
            
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        return False
    finally:
        db.close()

def main():
    print("=" * 70)
    print("DATABASE MIGRATION: Rename to progressive_narration")
    print("=" * 70)
    
    # Create backup
    backup_path = backup_database()
    
    # Run migration
    if rename_column():
        # Verify
        if verify_migration():
            print("\n" + "=" * 70)
            print("✅ MIGRATION SUCCESSFUL!")
            print("=" * 70)
            print("\nChanges made:")
            print("  • Renamed: auto_narrate_new_scenes → progressive_narration")
            print("  • Updated field meaning:")
            print("    OLD: 'Auto-generate TTS for new scenes' (misleading)")
            print("    NEW: 'Split scenes into chunks for progressive playback' (accurate)")
            print("\nThe field now correctly represents:")
            print("  • When ON: Text is split into chunks (sentence/paragraph)")
            print("  • When OFF: Full scene text sent to TTS at once")
            print("  • chunk_size setting controls chunk size (100-500)")
            
            if backup_path:
                print(f"\nBackup saved at: {backup_path}")
            print("\n🚀 You can now restart your application!")
            return True
    
    print("\n" + "=" * 70)
    print("❌ MIGRATION FAILED!")
    print("=" * 70)
    if backup_path:
        print(f"\nRestore from backup if needed: {backup_path}")
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
