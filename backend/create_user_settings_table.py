#!/usr/bin/env python3
"""
Simple script to create UserSettings table if it doesn't exist.
This is useful for development when Alembic isn't set up.
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from app.database import engine
from app.models.user_settings import UserSettings

def create_user_settings_table():
    """Create the UserSettings table if it doesn't exist."""
    try:
        # Import all models to ensure they're registered
        from app.models import user, story, character, user_settings
        
        # Create all tables (will only create missing ones)
        from app.database import Base
        Base.metadata.create_all(bind=engine)
        
        print("✅ UserSettings table created successfully!")
        print("Users can now configure their LLM and context management preferences.")
        
    except Exception as e:
        print(f"❌ Error creating UserSettings table: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("Creating UserSettings table...")
    success = create_user_settings_table()
    
    if success:
        print("\n🎉 User settings system is ready!")
        print("Users can access settings at: http://localhost:3000/settings")
    else:
        print("\n💥 Failed to create UserSettings table")
        sys.exit(1)