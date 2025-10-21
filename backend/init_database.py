#!/usr/bin/env python3
"""
Initialize the Kahani database with all tables and create default users.
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect
from app.database import Base, get_db
from app.models.user import User
from app.models.user_settings import UserSettings
from app.models.story import Story
from app.models.chapter import Chapter
from app.models.scene import Scene, SceneChoice
from app.models.scene_variant import SceneVariant
from app.models.character import Character, StoryCharacter
from app.models.prompt_template import PromptTemplate
from app.models.writing_style_preset import WritingStylePreset
from app.models.story_flow import StoryFlow
from app.models.tts_settings import TTSSettings, SceneAudio
from app.models.tts_provider_config import TTSProviderConfig
from app.models.semantic_memory import CharacterMemory, PlotEvent, SceneEmbedding
from app.models.entity_state import CharacterState, LocationState, ObjectState
from app.config import Settings
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_database():
    """Initialize database with all tables."""
    settings = Settings()
    
    # Create data directory if it doesn't exist
    data_dir = Path(backend_dir) / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Database file path
    db_path = data_dir / "kahani.db"
    
    print(f"Initializing database at: {db_path}")
    
    # Create engine
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False}
    )
    
    # Check if database already has tables
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if existing_tables:
        print(f"Warning: Database already has {len(existing_tables)} tables: {', '.join(existing_tables)}")
        response = input("Drop all tables and recreate? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return
        
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
    
    # Create all tables
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    # Get list of created tables
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Created {len(tables)} tables: {', '.join(tables)}")
    
    # Create default users
    print("\nCreating default users...")
    from sqlalchemy.orm import Session
    db = Session(engine)
    
    try:
        # Create test user
        test_user = User(
            email="test@test.com",
            username="test",
            display_name="Test User",
            hashed_password=pwd_context.hash("test"),
            is_active=True,
            is_admin=False
        )
        db.add(test_user)
        
        # Create admin user
        admin_user = User(
            email=settings.admin_email,
            username="admin",
            display_name="Administrator",
            hashed_password=pwd_context.hash(settings.admin_password),
            is_active=True,
            is_admin=True
        )
        db.add(admin_user)
        
        db.commit()
        
        print(f"✓ Created test user: test@test.com / test")
        print(f"✓ Created admin user: {settings.admin_email} / {settings.admin_password}")
        
        # Verify users were created
        user_count = db.query(User).count()
        print(f"\nTotal users in database: {user_count}")
        
    except Exception as e:
        print(f"Error creating users: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    print(f"\n✅ Database initialized successfully at: {db_path}")
    print(f"Database size: {db_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    init_database()
