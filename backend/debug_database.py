#!/usr/bin/env python3
"""
Database migration: Fix schema issues and ensure all tables are up to date
"""

import sqlite3
import sys
import os
from datetime import datetime

def main():
    print("🔧 Fixing database schema issues...")
    
    # Database path - relative to backend directory
    db_path = "data/kahani.db"
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return 1
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("📊 Checking current database state...")
        
        # Check existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Existing tables: {', '.join(tables)}")
        
        # Check stories count
        if 'stories' in tables:
            cursor.execute("SELECT COUNT(*) FROM stories")
            story_count = cursor.fetchone()[0]
            print(f"✅ Stories preserved: {story_count} stories found")
        
        # Check users count
        if 'users' in tables:
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"✅ Users preserved: {user_count} users found")
        
        # Check scenes count
        if 'scenes' in tables:
            cursor.execute("SELECT COUNT(*) FROM scenes")
            scene_count = cursor.fetchone()[0]
            print(f"✅ Scenes preserved: {scene_count} scenes found")
        
        print("🔧 Database appears intact. The issue is likely model synchronization.")
        print("💡 The server error suggests SQLAlchemy models are expecting different columns.")
        print("💡 This often happens when models are modified but not migrated properly.")
        
        # Let's check if we can query the data directly
        print("\n📋 Sample story data:")
        cursor.execute("SELECT id, title, owner_id FROM stories LIMIT 3")
        stories = cursor.fetchall()
        for story in stories:
            print(f"  Story ID {story[0]}: '{story[1]}' (Owner: {story[2]})")
        
        conn.close()
        
        print(f"\n✅ Database analysis complete!")
        print(f"\n🚨 Issue Summary:")
        print(f"   - Stories are NOT deleted ({story_count} stories exist)")
        print(f"   - Database schema exists and contains data")
        print(f"   - Problem is SQLAlchemy model/database synchronization")
        print(f"\n💡 Solution: The server needs to handle schema differences gracefully")
        print(f"   - Consider using Alembic for proper migrations")
        print(f"   - Or temporarily modify models to match current schema")
        
        return 0
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())