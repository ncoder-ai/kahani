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
from app.models.system_settings import SystemSettings
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
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_database():
    """Initialize database with all tables."""
    # Create data directory BEFORE loading settings
    data_dir = Path(backend_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"✓ Created data directory: {data_dir}")
    print(f"  - Directory exists: {data_dir.exists()}")
    print(f"  - Directory is writable: {os.access(data_dir, os.W_OK)}")
    print(f"  - Current user: {os.getuid()}")
    
    # Check if we can write to the data directory
    if not os.access(data_dir, os.W_OK):
        print(f"❌ ERROR: Cannot write to data directory: {data_dir}")
        print(f"  - Current working directory: {os.getcwd()}")
        print(f"  - Directory permissions: {oct(data_dir.stat().st_mode)[-3:]}")
        print(f"  - Try running: chmod 755 {data_dir}")
        sys.exit(1)
    
    # Now load settings
    settings = Settings()
    
    # Database file path
    db_path = data_dir / "kahani.db"
    
    print(f"\nInitializing database at: {db_path}")
    print(f"  - Database URL from settings: {settings.database_url}")
    
    # Use absolute path for database to avoid any path resolution issues
    absolute_db_url = f"sqlite:///{db_path.absolute()}"
    print(f"  - Using absolute path: {absolute_db_url}")
    
    # Test if we can create the database file
    try:
        # Try to create a test file in the same directory
        test_file = data_dir / ".test_db_write"
        test_file.touch()
        test_file.unlink()
        print(f"✓ Database directory is writable")
    except Exception as e:
        print(f"❌ ERROR: Cannot write to database directory: {e}")
        sys.exit(1)
    
    # Create engine with absolute path
    engine = create_engine(
        absolute_db_url,
        connect_args={"check_same_thread": False}
    )
    
    # Check if database already has tables
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if existing_tables:
        print(f"Warning: Database already has {len(existing_tables)} tables: {', '.join(existing_tables)}")
        print("Skipping table creation (database already initialized)")
        return
    
    # Create all tables
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    # Get list of created tables
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Created {len(tables)} tables: {', '.join(tables)}")
    
    # Create system settings (singleton)
    print("\nCreating system settings...")
    from sqlalchemy.orm import Session
    db = Session(engine)
    
    try:
        # Create system settings with safe defaults
        system_settings = SystemSettings(
            id=1,
            # Default permissions for new users
            default_allow_nsfw=False,
            default_can_change_llm_provider=True,
            default_can_change_tts_settings=True,
            default_can_use_stt=True,
            default_can_use_image_generation=True,
            default_can_export_stories=True,
            default_can_import_stories=True,
            # Default resource limits (None = unlimited)
            default_max_stories=None,
            default_max_images_per_story=None,
            default_max_stt_minutes_per_month=None,
            # Default LLM settings
            default_llm_api_url=None,
            default_llm_api_key=None,
            default_llm_model_name=None,
            default_llm_temperature=0.7,
            # Registration settings
            registration_requires_approval=True,
        )
        db.add(system_settings)
        db.commit()
        print("✓ Created system settings with safe defaults")
        
        # NOTE: We do NOT create any default users!
        # The first user to register will automatically become admin.
        # This is handled in /api/auth/register endpoint.
        print("\n✓ Database ready - first user to register will be admin")
        
        # Verify system settings
        user_count = db.query(User).count()
        print(f"\nTotal users in database: {user_count}")
        print("  First user to register will automatically:")
        print("    - Become admin (is_admin=True)")
        print("    - Be auto-approved (is_approved=True)")
        print("    - Get all permissions")
        print("\n  Subsequent users will:")
        print("    - Inherit defaults from SystemSettings")
        print("    - Require admin approval (if registration_requires_approval=True)")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    print(f"\n✅ Database initialized successfully at: {db_path}")
    print(f"Database size: {db_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    init_database()
