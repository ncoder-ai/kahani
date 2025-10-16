#!/usr/bin/env python3
"""
Migration script to add auto_generate_summaries column to user_settings table
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text, inspect
from app.config import settings

def migrate():
    """Add auto_generate_summaries column to user_settings table"""
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
    )
    
    with engine.connect() as conn:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('user_settings')]
        
        if 'auto_generate_summaries' in columns:
            print("✓ Column 'auto_generate_summaries' already exists")
            return
        
        print("Adding auto_generate_summaries column...")
        
        # Add the column with default value
        conn.execute(text("""
            ALTER TABLE user_settings 
            ADD COLUMN auto_generate_summaries BOOLEAN DEFAULT TRUE
        """))
        conn.commit()
        
        print("✓ Successfully added auto_generate_summaries column")
        print("  Default value: TRUE (auto-generation enabled)")

if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Add auto_generate_summaries to user_settings")
    print("=" * 60)
    
    try:
        migrate()
        print("\n✓ Migration completed successfully!")
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)
