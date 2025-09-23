#!/usr/bin/env python3
"""
Database reset script for scene variants migration
Run this to reset the database with the new schema
"""

import os
import sys
from pathlib import Path

# Add the backend directory to the path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database import engine, Base
from app.models import *  # Import all models including new ones

def reset_database():
    """Drop all tables and recreate with new schema"""
    print("🗑️  Dropping all existing tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("🏗️  Creating new tables with scene variants schema...")
    Base.metadata.create_all(bind=engine)
    
    print("✅ Database reset complete!")
    print("📋 New tables created:")
    for table_name in Base.metadata.tables.keys():
        print(f"   - {table_name}")

if __name__ == "__main__":
    print("⚠️  WARNING: This will delete ALL existing data!")
    response = input("Continue? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        reset_database()
    else:
        print("❌ Operation cancelled")