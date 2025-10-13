"""
Add TTS (Text-to-Speech) Support

This migration adds tables for TTS settings and audio caching.
Supports multiple TTS providers with extensible configuration.
"""

import sys
import os
from datetime import datetime

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.config import settings
from app.database import Base
from app.models import TTSSettings, SceneAudio

def run_migration():
    """Run the TTS migration"""
    print("🎙️  Running TTS Migration...")
    
    # Create engine
    engine = create_engine(settings.database_url)
    
    # Create tables
    print("Creating TTS tables...")
    
    try:
        # Check if tables already exist
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tts_settings'"
            ))
            if result.fetchone():
                print("⚠️  TTS tables already exist. Skipping creation.")
                return
        
        # Create the new tables
        TTSSettings.__table__.create(engine, checkfirst=True)
        SceneAudio.__table__.create(engine, checkfirst=True)
        
        print("✅ TTS tables created successfully!")
        print("\nCreated tables:")
        print("  - tts_settings: User TTS configuration (provider-agnostic)")
        print("  - scene_audio: Cached audio files for scenes")
        
        print("\n📋 Supported TTS Providers:")
        print("  - openai-compatible (Kokoro, ChatterboxTTS, OpenAI, LM Studio)")
        print("  - elevenlabs (can be added)")
        print("  - google (can be added)")
        print("  - azure (can be added)")
        print("  - aws-polly (can be added)")
        
        print("\n🎯 Next Steps:")
        print("  1. Restart the backend server")
        print("  2. Users can configure TTS in settings")
        print("  3. Test with Kokoro: http://172.16.23.80:4321")
        
    except Exception as e:
        print(f"❌ Error running migration: {str(e)}")
        raise

def rollback_migration():
    """Rollback the TTS migration"""
    print("🔄 Rolling back TTS migration...")
    
    engine = create_engine(settings.database_url)
    
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS scene_audio"))
            conn.execute(text("DROP TABLE IF EXISTS tts_settings"))
            conn.commit()
        
        print("✅ TTS tables dropped successfully!")
        
    except Exception as e:
        print(f"❌ Error rolling back migration: {str(e)}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TTS Migration")
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration"
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    else:
        run_migration()
