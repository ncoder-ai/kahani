"""
Migration: Add TTS Provider Configs Table

Creates the tts_provider_configs table to store per-provider settings for users.
This allows users to maintain separate configurations for different TTS providers
(e.g., Chatterbox, Kokoro, OpenAI-compatible).

Run this script to add the table to your database:
    python migrate_add_provider_configs.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.config import settings
from app.database import Base
from app.models.tts_provider_config import TTSProviderConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Add tts_provider_configs table"""
    
    # Create engine
    engine = create_engine(settings.database_url)
    
    logger.info("Starting migration: Add TTS Provider Configs table")
    
    try:
        # Create the new table
        logger.info("Creating tts_provider_configs table...")
        TTSProviderConfig.__table__.create(engine, checkfirst=True)
        
        logger.info("✓ Migration completed successfully!")
        logger.info("")
        logger.info("The tts_provider_configs table has been created.")
        logger.info("Users can now save separate settings for each TTS provider.")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
