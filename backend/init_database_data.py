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
from app.config import settings

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
        
        # Create system settings from config.yaml defaults
        system_defaults = settings.system_defaults
        
        system_settings = SystemSettings(
            id=1,
            # Default permissions for new users
            default_allow_nsfw=system_defaults.get('permissions', {}).get('default_allow_nsfw'),
            default_can_change_llm_provider=system_defaults.get('permissions', {}).get('default_can_change_llm_provider'),
            default_can_change_tts_settings=system_defaults.get('permissions', {}).get('default_can_change_tts_settings'),
            default_can_use_stt=system_defaults.get('permissions', {}).get('default_can_use_stt'),
            default_can_use_image_generation=system_defaults.get('permissions', {}).get('default_can_use_image_generation'),
            default_can_export_stories=system_defaults.get('permissions', {}).get('default_can_export_stories'),
            default_can_import_stories=system_defaults.get('permissions', {}).get('default_can_import_stories'),
            # Default resource limits (None = unlimited)
            default_max_stories=system_defaults.get('resource_limits', {}).get('default_max_stories'),
            default_max_images_per_story=system_defaults.get('resource_limits', {}).get('default_max_images_per_story'),
            default_max_stt_minutes_per_month=system_defaults.get('resource_limits', {}).get('default_max_stt_minutes_per_month'),
            # Default LLM settings
            default_llm_api_url=system_defaults.get('llm_defaults', {}).get('default_llm_api_url'),
            default_llm_api_key=system_defaults.get('llm_defaults', {}).get('default_llm_api_key'),
            default_llm_model_name=system_defaults.get('llm_defaults', {}).get('default_llm_model_name'),
            default_llm_temperature=system_defaults.get('llm_defaults', {}).get('default_llm_temperature'),
            # Registration settings
            registration_requires_approval=system_defaults.get('registration', {}).get('registration_requires_approval'),
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
