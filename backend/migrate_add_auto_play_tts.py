#!/usr/bin/env python3
"""
Migration: Add auto_play_last_scene to tts_settings

Adds a boolean column to enable/disable automatic TTS playback
after scene generation completes.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Add auto_play_last_scene column to tts_settings table"""
    
    logger.info("Starting migration: Add auto_play_last_scene to tts_settings")
    
    with engine.connect() as conn:
        try:
            # Check if column already exists
            result = conn.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('tts_settings') "
                "WHERE name='auto_play_last_scene'"
            ))
            
            if result.scalar() > 0:
                logger.info("Column 'auto_play_last_scene' already exists. Skipping migration.")
                return
            
            # Add the column
            logger.info("Adding column 'auto_play_last_scene' to tts_settings table...")
            conn.execute(text(
                "ALTER TABLE tts_settings "
                "ADD COLUMN auto_play_last_scene BOOLEAN DEFAULT 0"
            ))
            conn.commit()
            
            logger.info("✅ Migration completed successfully!")
            logger.info("Column 'auto_play_last_scene' added to tts_settings")
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            conn.rollback()
            raise


def rollback():
    """Remove auto_play_last_scene column (rollback)"""
    
    logger.info("Rolling back migration: Remove auto_play_last_scene")
    
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly
            # Would need to recreate table, but for dev we can skip
            logger.warning("SQLite doesn't support DROP COLUMN easily.")
            logger.warning("For rollback, restore from backup or recreate table.")
            
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")
            raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate TTS settings for auto-play")
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    
    args = parser.parse_args()
    
    if args.rollback:
        rollback()
    else:
        migrate()
