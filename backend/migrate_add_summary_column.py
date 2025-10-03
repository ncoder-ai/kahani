#!/usr/bin/env python3
"""
Migration script to add summary column to stories table.
This allows storing AI-generated summaries directly in the story model.
"""

import sys
import os
from pathlib import Path
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text, Column, Text, inspect
from app.config import settings
from app.models import Base, Story

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add summary column to stories table if it doesn't exist"""
    try:
        # Create engine
        engine = create_engine(settings.database_url)
        
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('stories')]
        
        if 'summary' in columns:
            logger.info("✓ Column 'summary' already exists in stories table")
            return True
        
        logger.info("Adding 'summary' column to stories table...")
        
        # Add the column
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE stories 
                ADD COLUMN summary TEXT
            """))
        
        logger.info("✓ Successfully added 'summary' column to stories table")
        
        # Verify the column was added
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('stories')]
        
        if 'summary' in columns:
            logger.info("✓ Verified 'summary' column exists in stories table")
            return True
        else:
            logger.error("✗ Failed to verify 'summary' column")
            return False
            
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Running migration: Add summary column to stories table")
    logger.info("=" * 60)
    
    success = run_migration()
    
    if success:
        logger.info("\n✓ Migration completed successfully")
        sys.exit(0)
    else:
        logger.error("\n✗ Migration failed")
        sys.exit(1)
