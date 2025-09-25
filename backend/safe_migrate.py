#!/usr/bin/env python3
"""
Safe database migration utilities
ALWAYS creates backups before making schema changes
"""

import sys
import os
sys.path.append('/Users/user/apps/kahani/backend')

from app.database import engine, Base
from backup_database import create_backup
import logging

logger = logging.getLogger(__name__)

def safe_recreate_database(reason="schema_migration"):
    """
    Safely recreate database with MANDATORY backup first
    """
    print("🔒 SAFE DATABASE RECREATION")
    print("=" * 50)
    
    # STEP 1: ALWAYS CREATE BACKUP FIRST
    print("1️⃣ Creating backup before any changes...")
    backup_path = create_backup(reason)
    
    if not backup_path:
        print("❌ BACKUP FAILED - ABORTING MIGRATION")
        print("🛑 Will NOT proceed without successful backup")
        return False
    
    print(f"✅ Backup created: {backup_path}")
    
    # STEP 2: Ask for confirmation
    print("\n2️⃣ About to recreate database tables...")
    print("⚠️  This will DELETE all current data")
    print(f"📁 Backup saved at: {backup_path}")
    
    confirm = input("\nDo you want to proceed? (yes/no): ").lower().strip()
    if confirm != 'yes':
        print("🛑 Migration cancelled by user")
        return False
    
    # STEP 3: Perform migration
    try:
        print("\n3️⃣ Recreating database tables...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables recreated successfully")
        
        print("\n📋 Migration Summary:")
        print(f"   ✅ Backup created: {backup_path}")
        print(f"   ✅ Database recreated")
        print(f"   📝 You can restore with: python backup_database.py restore --backup-path {backup_path}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print(f"🔄 You can restore from backup: {backup_path}")
        return False

def emergency_restore_instructions():
    """Show emergency restore instructions"""
    print("\n🚨 EMERGENCY DATA RECOVERY")
    print("=" * 40)
    print("If you lost data due to a migration:")
    print("1. cd /Users/user/apps/kahani/backend")
    print("2. python backup_database.py list")
    print("3. python backup_database.py restore --backup-path [backup_file]")
    print("")
    print("The script automatically creates backups before ANY destructive operation!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "emergency":
        emergency_restore_instructions()
    else:
        # Import models to ensure they're loaded
        from app.models.user import User
        from app.models.user_settings import UserSettings
        from app.models.story import Story
        from app.models.scene import Scene
        from app.models.prompt_template import PromptTemplate
        
        success = safe_recreate_database("manual_schema_update")
        if not success:
            print("\n🔄 Migration failed or cancelled")
            emergency_restore_instructions()