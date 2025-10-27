#!/usr/bin/env python3
"""
Repair Alembic version table for existing databases.

This utility detects the current database schema state and properly stamps
the alembic_version table with the correct migration version.

Use this when:
- Database has tables but alembic_version is missing or incorrect
- Migration errors occur due to version mismatch
- After manual schema changes
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect, text
from alembic.script import ScriptDirectory
from alembic.config import Config as AlembicConfig
from app.config import Settings

def get_database_engine():
    """Get database engine from settings."""
    settings = Settings()
    data_dir = backend_dir / "data"
    db_path = data_dir / "kahani.db"
    
    if not db_path.exists():
        print(f"❌ Database not found at: {db_path}")
        print("   Nothing to repair. Run init_database.py to create a new database.")
        sys.exit(0)
    
    absolute_db_url = f"sqlite:///{db_path.absolute()}"
    engine = create_engine(
        absolute_db_url,
        connect_args={"check_same_thread": False}
    )
    return engine, db_path

def get_current_alembic_version(engine):
    """Get the current Alembic version from the database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if 'alembic_version' not in tables:
        return None
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        return row[0] if row else None

def get_head_revision():
    """Get the HEAD revision from Alembic migrations."""
    try:
        alembic_ini_path = backend_dir / "alembic.ini"
        alembic_cfg = AlembicConfig(str(alembic_ini_path))
        script = ScriptDirectory.from_config(alembic_cfg)
        return script.get_current_head()
    except Exception as e:
        print(f"❌ Error reading Alembic configuration: {e}")
        sys.exit(1)

def detect_schema_version(engine):
    """
    Detect which migration version matches the current database schema.
    
    This checks for presence of key tables and columns added in each migration.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if not tables:
        return None  # Empty database
    
    # Check for tables that should exist
    required_base_tables = ['users', 'stories', 'chapters', 'scenes', 'characters']
    if not all(table in tables for table in required_base_tables):
        print("⚠️  Database is missing core tables. Schema may be corrupted.")
        return None
    
    # Check for user_settings table (added in migration 001)
    if 'user_settings' not in tables:
        print("⚠️  Database predates migration 001 (user_settings table missing)")
        return None
    
    # Get columns in user_settings to determine version
    user_settings_columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    # Check for character assistant settings (added in c7923c6e866e)
    if 'character_assistant_enabled' in user_settings_columns:
        # This is the latest migration
        return get_head_revision()
    
    # Check for engine-specific settings (added in ec1f4e1c996a)
    if 'llm_koboldcpp_api_url' in user_settings_columns:
        return 'bbf4e254a824'  # Before character assistant settings
    
    # Check for scene_container_style removal (bbf4e254a824)
    if 'scene_container_style' not in user_settings_columns:
        # Check if we have the columns from ec1f4e1c996a
        if 'llm_koboldcpp_api_url' not in user_settings_columns:
            return 'ec1f4e1c996a'  # Has removal but not engine settings yet
    
    # Check for scene_container_style (added in 008, removed in bbf4e254a824)
    if 'scene_container_style' in user_settings_columns:
        return '008'
    
    # Check for color theme settings (added in 007)
    if 'color_theme_primary' in user_settings_columns:
        return '007'
    
    # Check for role in story_characters (added in 006)
    if 'story_characters' in tables:
        story_char_columns = [col['name'] for col in inspector.get_columns('story_characters')]
        if 'role' in story_char_columns:
            return '006'
    
    # Check for scenario field in stories (added in 004/005)
    if 'stories' in tables:
        story_columns = [col['name'] for col in inspector.get_columns('stories')]
        if 'scenario' in story_columns:
            return '005'  # or '004', they're similar
    
    # Check for admin system tables (added in 003)
    if 'system_settings' in tables:
        return '003'
    
    # Check for semantic memory tables (added in 002)
    if 'character_memories' in tables or 'plot_events' in tables:
        return '002'
    
    # Has user_settings but nothing else we can detect
    return '001'

def stamp_version(engine, version):
    """Stamp the database with the specified Alembic version."""
    with engine.connect() as conn:
        # Create alembic_version table if it doesn't exist
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """))
        
        # Delete any existing version
        conn.execute(text("DELETE FROM alembic_version"))
        
        # Insert the new version
        conn.execute(text("""
            INSERT INTO alembic_version (version_num) VALUES (:version)
        """), {"version": version})
        
        conn.commit()

def repair_alembic_version():
    """Main repair function."""
    print("🔧 Alembic Version Repair Utility")
    print("=" * 50)
    
    # Get database engine
    engine, db_path = get_database_engine()
    print(f"\n📁 Database: {db_path}")
    
    # Check current version
    current_version = get_current_alembic_version(engine)
    head_revision = get_head_revision()
    
    print(f"📊 Current Alembic version: {current_version or 'NOT SET'}")
    print(f"🎯 Latest migration (HEAD): {head_revision}")
    
    # If version is already correct, nothing to do
    if current_version == head_revision:
        print("\n✅ Database is already at HEAD revision. No repair needed.")
        return
    
    # Detect what version the schema actually matches
    print("\n🔍 Analyzing database schema...")
    detected_version = detect_schema_version(engine)
    
    if detected_version is None:
        print("\n⚠️  Could not reliably detect schema version.")
        print("   The database may be empty, corrupted, or use a custom schema.")
        
        # Check if database is empty
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if not tables:
            print("   Database is empty - no tables found.")
            print("   Run init_database.py to initialize it.")
            return
        
        print("\n❓ What would you like to do?")
        print("   1. Stamp with HEAD revision (if schema is up to date)")
        print("   2. Exit and fix manually")
        return
    
    print(f"✓ Detected schema matches migration: {detected_version}")
    
    # Determine action
    if detected_version == head_revision:
        print(f"\n✅ Schema is up to date with HEAD revision")
        print(f"   Stamping database with: {head_revision}")
        stamp_version(engine, head_revision)
        print("✓ Alembic version repaired successfully!")
    else:
        print(f"\n⚠️  Schema appears to be at: {detected_version}")
        print(f"   HEAD revision is: {head_revision}")
        print(f"   Stamping database with detected version: {detected_version}")
        stamp_version(engine, detected_version)
        print("✓ Alembic version stamped!")
        print("\n💡 You can now run 'alembic upgrade head' to apply remaining migrations.")

if __name__ == "__main__":
    try:
        repair_alembic_version()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

