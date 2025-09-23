"""
Migration script to add LLM API configuration columns to existing database
"""

import sqlite3
import os

def migrate_database():
    db_path = "data/kahani.db"
    
    if not os.path.exists(db_path):
        print("Database file not found. Please ensure the backend is running first.")
        return
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = [
            "llm_api_url",
            "llm_api_key", 
            "llm_api_type",
            "llm_model_name"
        ]
        
        # Add missing columns
        for column in new_columns:
            if column not in columns:
                if column == "llm_api_url":
                    cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {column} TEXT DEFAULT 'http://localhost:1234/v1'")
                elif column == "llm_api_key":
                    cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {column} TEXT")
                elif column == "llm_api_type":
                    cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {column} TEXT DEFAULT 'openai_compatible'")
                elif column == "llm_model_name":
                    cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {column} TEXT")
                
                print(f"Added column: {column}")
            else:
                print(f"Column {column} already exists")
        
        # Commit changes
        conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()