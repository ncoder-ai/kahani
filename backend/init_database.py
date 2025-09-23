#!/usr/bin/env python3
"""
Initialize the database with all tables
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base
from app.models import User, UserSettings, Story

def init_database():
    """Create all database tables"""
    print("Creating database tables...")
    
    # Import all models to ensure they're registered with Base
    from app.models.user import User
    from app.models.user_settings import UserSettings
    from app.models.story import Story
    from app.models.scene import Scene
    from app.models.character import Character
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    # Verify tables were created
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables created: {tables}")
    
    if 'user_settings' in tables:
        print("\nChecking user_settings table structure:")
        columns = inspector.get_columns('user_settings')
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")

if __name__ == "__main__":
    init_database()