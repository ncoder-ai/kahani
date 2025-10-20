"""
Database Migration: Add Entity State Tables

Creates tables for tracking character, location, and object states.
These tables maintain authoritative current state for story continuity.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect
from app.config import settings
from app.models import Base, CharacterState, LocationState, ObjectState

def run_migration():
    """Create entity state tables"""
    print("🏗️  Running Entity States Migration...")
    print("=" * 60)
    
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    
    # Check existing tables
    existing_tables = inspector.get_table_names()
    
    tables_to_create = []
    
    if 'character_states' not in existing_tables:
        tables_to_create.append('character_states')
    else:
        print("⏩ Table 'character_states' already exists, skipping")
    
    if 'location_states' not in existing_tables:
        tables_to_create.append('location_states')
    else:
        print("⏩ Table 'location_states' already exists, skipping")
    
    if 'object_states' not in existing_tables:
        tables_to_create.append('object_states')
    else:
        print("⏩ Table 'object_states' already exists, skipping")
    
    if not tables_to_create:
        print("\n✅ All entity state tables already exist!")
        print("=" * 60)
        return 0
    
    print(f"\n📋 Creating {len(tables_to_create)} table(s)...")
    
    try:
        # Create tables
        if 'character_states' in tables_to_create:
            print("  Creating character_states table...")
            CharacterState.__table__.create(engine, checkfirst=True)
            print("  ✅ character_states created")
        
        if 'location_states' in tables_to_create:
            print("  Creating location_states table...")
            LocationState.__table__.create(engine, checkfirst=True)
            print("  ✅ location_states created")
        
        if 'object_states' in tables_to_create:
            print("  Creating object_states table...")
            ObjectState.__table__.create(engine, checkfirst=True)
            print("  ✅ object_states created")
        
        print("\n" + "=" * 60)
        print("✅ Entity States Migration Complete!")
        print("=" * 60)
        
        print("\n📊 Tables Created:")
        print("  • character_states - Character state tracking")
        print("  • location_states - Location state tracking")
        print("  • object_states - Object state tracking")
        
        print("\n🎯 Features Enabled:")
        print("  • Authoritative character state (location, emotions, possessions)")
        print("  • Relationship tracking with trust levels")
        print("  • Knowledge and goal tracking")
        print("  • Location continuity (condition, occupants)")
        print("  • Object tracking (location, owner, state)")
        
        print("\n🚀 Next Steps:")
        print("  1. Entity states will automatically extract from new scenes")
        print("  2. States will be included in LLM context")
        print("  3. Character consistency will improve dramatically!")
        print("  4. Optionally run migrate_existing_stories_to_semantic.py")
        print("     to populate states for existing stories")
        
        print("\n💡 How It Works:")
        print("  • After each scene generation, LLM extracts state changes")
        print("  • Character locations, emotions, possessions are tracked")
        print("  • Relationships evolve with trust levels")
        print("  • States are included in context for next scene")
        print("  • Result: Perfect character and world consistency!")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("=" * 60)
        return 1


def rollback_migration():
    """Drop entity state tables"""
    print("🔄 Rolling Back Entity States Migration...")
    print("=" * 60)
    
    engine = create_engine(settings.database_url)
    
    try:
        from sqlalchemy import text
        
        with engine.connect() as conn:
            print("  Dropping object_states table...")
            conn.execute(text("DROP TABLE IF EXISTS object_states"))
            
            print("  Dropping location_states table...")
            conn.execute(text("DROP TABLE IF EXISTS location_states"))
            
            print("  Dropping character_states table...")
            conn.execute(text("DROP TABLE IF EXISTS character_states"))
            
            conn.commit()
        
        print("\n✅ Entity States tables dropped successfully!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n❌ Rollback failed: {e}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Entity States Migration")
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration (drop tables)"
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        sys.exit(rollback_migration())
    else:
        sys.exit(run_migration())

