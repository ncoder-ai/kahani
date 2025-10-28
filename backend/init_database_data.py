#!/usr/bin/env python3
"""
Initialize database with default data (NOT schema).
Schema is managed exclusively by Alembic migrations.

This script only creates:
- System settings (default configuration)
- Any other default data needed for the application

It does NOT create tables - that's handled by Alembic.
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from app.database import engine
from app.models.system_settings import SystemSettings
from app.models.user import User

def init_default_data():
    """Initialize database with default data only."""
    print("🗄️  Initializing default data...")
    
    # Create data directory if it doesn't exist
    data_dir = backend_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if database exists
    db_path = data_dir / "kahani.db"
    if not db_path.exists():
        print("❌ Database does not exist. Run 'alembic upgrade head' first.")
        return False
    
    # Create database session
    db = Session(engine)
    
    try:
        # Check if system settings already exist
        existing_settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
        
        if existing_settings:
            print("✅ System settings already exist, skipping data initialization")
            return True
        
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
        
        print("✅ Created system settings with safe defaults")
        
        # Verify system settings
        user_count = db.query(User).count()
        print(f"📊 Total users in database: {user_count}")
        print("🔐 First user to register will automatically:")
        print("   - Become admin (is_admin=True)")
        print("   - Be auto-approved (is_approved=True)")
        print("   - Get all permissions")
        print("\n📝 Subsequent users will:")
        print("   - Inherit defaults from SystemSettings")
        print("   - Require admin approval (if registration_requires_approval=True)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing default data: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = init_default_data()
    if success:
        print("\n✅ Default data initialization complete")
    else:
        print("\n❌ Default data initialization failed")
        sys.exit(1)
