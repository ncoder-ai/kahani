#!/usr/bin/env python3
"""
Database Recovery Script for Kahani

This script helps recover from accidental database deletion.
It checks for backups and provides recovery options.
"""
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def check_backups():
    """Check for available database backups"""
    backups_dir = backend_dir / "backups"
    backups_dir.mkdir(exist_ok=True)
    
    backups = []
    if backups_dir.exists():
        for file in backups_dir.glob("*.db"):
            stat = file.stat()
            backups.append({
                "path": file,
                "name": file.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime)
            })
    
    # Sort by modification time (newest first)
    backups.sort(key=lambda x: x["modified"], reverse=True)
    return backups

def restore_from_backup(backup_path: Path, db_path: Path):
    """Restore database from backup"""
    print(f"\n🔄 Restoring database from backup...")
    print(f"   Backup: {backup_path}")
    print(f"   Target: {db_path}")
    
    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy backup to database location
    shutil.copy2(backup_path, db_path)
    
    print(f"✅ Database restored successfully!")
    print(f"   Database size: {db_path.stat().st_size / 1024:.1f} KB")
    
    # Run Alembic migrations to ensure schema is up to date
    print(f"\n🔄 Running Alembic migrations to ensure schema is current...")
    os.chdir(backend_dir)
    os.system("alembic upgrade head")
    print(f"✅ Migrations complete!")

def recreate_database():
    """Recreate database from scratch using Alembic"""
    print(f"\n🔄 Recreating database from scratch...")
    
    # Initialize database
    print("   Step 1: Initializing database schema...")
    os.chdir(backend_dir)
    os.system("python3 init_database.py")
    
    # Run migrations
    print("   Step 2: Running Alembic migrations...")
    os.system("alembic upgrade head")
    
    print(f"✅ Database recreated successfully!")
    print(f"   ⚠️  Note: All data is lost. You'll need to:")
    print(f"      - Register a new admin user")
    print(f"      - Recreate your stories and content")

def recreate_chromadb():
    """Recreate ChromaDB directory"""
    chromadb_dir = backend_dir / "data" / "chromadb"
    
    print(f"\n🔄 Recreating ChromaDB...")
    
    # Remove existing directory if it exists
    if chromadb_dir.exists():
        print(f"   Removing existing ChromaDB directory...")
        shutil.rmtree(chromadb_dir)
    
    # Create new directory
    chromadb_dir.mkdir(parents=True, exist_ok=True)
    print(f"✅ ChromaDB directory created at: {chromadb_dir}")
    print(f"   ⚠️  Note: All semantic memory (embeddings) will be lost.")
    print(f"      ChromaDB will be automatically recreated when the app starts.")

def main():
    print("=" * 60)
    print("🔧 Kahani Database Recovery Tool")
    print("=" * 60)
    
    db_path = backend_dir / "data" / "kahani.db"
    chromadb_dir = backend_dir / "data" / "chromadb"
    
    # Check current state
    print(f"\n📊 Current State:")
    print(f"   Database exists: {db_path.exists()}")
    print(f"   ChromaDB exists: {chromadb_dir.exists()}")
    
    # Check for backups
    print(f"\n🔍 Checking for backups...")
    backups = check_backups()
    
    if backups:
        print(f"   Found {len(backups)} backup(s):")
        for i, backup in enumerate(backups, 1):
            size_kb = backup["size"] / 1024
            print(f"   {i}. {backup['name']}")
            print(f"      Size: {size_kb:.1f} KB")
            print(f"      Modified: {backup['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"   ⚠️  No backups found in {backend_dir / 'backups'}")
    
    # Recovery options
    print(f"\n📋 Recovery Options:")
    
    if backups:
        print(f"\n1. Restore from backup (recommended)")
        print(f"2. Recreate database from scratch (loses all data)")
        print(f"3. Recreate ChromaDB only")
        print(f"4. Exit")
        
        choice = input(f"\nSelect option (1-4): ").strip()
        
        if choice == "1":
            if len(backups) == 1:
                backup_path = backups[0]["path"]
            else:
                print(f"\nAvailable backups:")
                for i, backup in enumerate(backups, 1):
                    print(f"  {i}. {backup['name']} ({backup['size']/1024:.1f} KB)")
                backup_num = int(input(f"Select backup (1-{len(backups)}): ")) - 1
                backup_path = backups[backup_num]["path"]
            
            restore_from_backup(backup_path, db_path)
            recreate_chromadb()
            
        elif choice == "2":
            confirm = input(f"⚠️  This will DELETE all data. Type 'yes' to confirm: ")
            if confirm.lower() == "yes":
                recreate_database()
                recreate_chromadb()
            else:
                print("Cancelled.")
                
        elif choice == "3":
            recreate_chromadb()
            
        elif choice == "4":
            print("Exiting.")
            return
        else:
            print("Invalid option.")
    else:
        print(f"\n⚠️  No backups available. Options:")
        print(f"1. Recreate database from scratch (loses all data)")
        print(f"2. Recreate ChromaDB only")
        print(f"3. Exit")
        
        choice = input(f"\nSelect option (1-3): ").strip()
        
        if choice == "1":
            confirm = input(f"⚠️  This will DELETE all data. Type 'yes' to confirm: ")
            if confirm.lower() == "yes":
                recreate_database()
                recreate_chromadb()
            else:
                print("Cancelled.")
        elif choice == "2":
            recreate_chromadb()
        elif choice == "3":
            print("Exiting.")
            return
        else:
            print("Invalid option.")
    
    print(f"\n✅ Recovery complete!")
    print(f"\n📝 Next Steps:")
    print(f"   1. Start the application: ./start-dev.sh or ./start-prod.sh")
    print(f"   2. Register a new admin user (first user becomes admin)")
    print(f"   3. ChromaDB will be automatically recreated on startup")

if __name__ == "__main__":
    main()

