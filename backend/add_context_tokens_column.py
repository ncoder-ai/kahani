#!/usr/bin/env python3
"""
Add context_summary_threshold_tokens column to user_settings table
"""

import sqlite3
import os
import sys

# Add the backend directory to Python path
sys.path.append('/Users/nishant/apps/kahani/backend')

from app.config import settings

def add_context_summary_threshold_tokens_column():
    """Add the context_summary_threshold_tokens column to user_settings table"""
    
    # Extract database path from database URL
    if settings.database_url.startswith('sqlite:///'):
        db_path = settings.database_url.replace('sqlite:///', '')
    else:
        print("This script only works with SQLite databases")
        return False
    
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'context_summary_threshold_tokens' in columns:
            print("Column 'context_summary_threshold_tokens' already exists")
            return True
        
        # Add the new column with default value
        print("Adding context_summary_threshold_tokens column...")
        cursor.execute("""
            ALTER TABLE user_settings 
            ADD COLUMN context_summary_threshold_tokens INTEGER DEFAULT 10000
        """)
        
        conn.commit()
        print("Successfully added context_summary_threshold_tokens column")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'context_summary_threshold_tokens' in columns:
            print("Column verified successfully")
            return True
        else:
            print("Column verification failed")
            return False
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("Adding context_summary_threshold_tokens column to user_settings table...")
    success = add_context_summary_threshold_tokens_column()
    
    if success:
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed!")
        sys.exit(1)