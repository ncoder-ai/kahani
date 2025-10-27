#!/usr/bin/env python3
"""
Fix Alembic version tracking when database has tables but no alembic_version.

This script is useful when:
1. Database was created with Base.metadata.create_all() instead of Alembic
2. Alembic migrations fail with "table already exists" errors
3. You need to sync Alembic's tracking with the actual database state

Usage:
    python fix_alembic_version.py
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect, text
from app.config import Settings

def fix_alembic_version():
    """Stamp the database with the current Alembic head version."""
    settings = Settings()
    
    # Create data directory if needed
    data_dir = Path(backend_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = data_dir / "kahani.db"
    
    print(f"Checking database at: {db_path}")
    
    if not db_path.exists():
        print("❌ Database does not exist. Run init_database.py first.")
        return False
    
    # Create engine
    absolute_db_url = f"sqlite:///{db_path.absolute()}"
    engine = create_engine(
        absolute_db_url,
        connect_args={"check_same_thread": False}
    )
    
    # Check existing tables
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    print(f"\n✓ Database has {len(existing_tables)} tables")
    
    # Check if alembic_version table exists
    has_alembic_version = 'alembic_version' in existing_tables
    
    if has_alembic_version:
        # Check current version
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            if result:
                current_version = result[0]
                print(f"✓ Alembic version table exists with version: {current_version}")
                print("\nDatabase is already tracked by Alembic.")
                print("If you're having migration issues, try:")
                print("  cd backend && alembic current")
                print("  cd backend && alembic upgrade head")
                return True
            else:
                print("⚠️  Alembic version table exists but is empty")
    else:
        print("⚠️  No alembic_version table found")
    
    # If we have tables but no Alembic tracking, stamp it
    if existing_tables and not has_alembic_version:
        print("\n🔧 Fixing: Database has tables but no Alembic tracking")
        print("Creating alembic_version table and stamping to 'head'...")
        
        import subprocess
        result = subprocess.run(
            ["alembic", "stamp", "head"],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Successfully stamped database to head")
            print(result.stdout)
            
            # Verify
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
                if result:
                    print(f"✓ Verified: Database is now at version {result[0]}")
            return True
        else:
            print("❌ Failed to stamp database:")
            print(result.stderr)
            return False
    
    elif not existing_tables:
        print("\n⚠️  Database has no tables. Run init_database.py to create schema.")
        return False
    
    return True

if __name__ == "__main__":
    print("🔧 Kahani Database Alembic Version Fixer")
    print("=" * 50)
    print()
    
    success = fix_alembic_version()
    
    if success:
        print("\n" + "=" * 50)
        print("✅ Database is ready!")
        print("\nYou can now run:")
        print("  cd backend && alembic upgrade head")
    else:
        print("\n" + "=" * 50)
        print("❌ Manual intervention may be required")
        print("\nOptions:")
        print("  1. Delete backend/data/kahani.db and run install.sh")
        print("  2. Manually inspect the database")
        print("  3. Contact support")
    
    sys.exit(0 if success else 1)
