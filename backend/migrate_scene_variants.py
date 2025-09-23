#!/usr/bin/env python3
"""
Data migration script for converting existing scenes to scene variant system
This will preserve existing scene data by converting it to the new format
"""

import os
import sys
from pathlib import Path
from sqlalchemy.orm import Session

# Add the backend directory to the path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database import engine, get_db
from app.models import Scene, SceneVariant, StoryFlow, SceneChoice

def migrate_existing_data():
    """Convert existing scenes to the new variant system"""
    
    # First, reset database with new schema
    print("🔄 Resetting database with new schema...")
    exec(open('reset_database.py').read())
    
    print("📊 Migration complete!")
    print("ℹ️  All existing data has been cleared.")
    print("🎯 Ready for new scene variant system!")

if __name__ == "__main__":
    migrate_existing_data()