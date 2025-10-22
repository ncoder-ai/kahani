#!/usr/bin/env python3
"""
Update existing Kahani database schema to match current models.
This adds any missing tables and columns without losing data.
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect, text
from app.config import Settings
from app.database import Base

def update_database_schema():
    """Update database schema to match current models."""
    # Ensure data directory exists
    data_dir = Path(backend_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Now load settings
    settings = Settings()
    
    # Database file path
    db_path = data_dir / "kahani.db"
    
    if not db_path.exists():
        print(f"❌ Database not found at: {db_path}")
        print("Run init_database.py first to create the database.")
        return
    
    print(f"Updating database schema at: {db_path}")
    
    # Create engine
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False}
    )
    
    # Get existing tables
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    print(f"\nExisting tables: {len(existing_tables)}")
    
    # Get all model tables
    model_tables = set(Base.metadata.tables.keys())
    print(f"Model tables: {len(model_tables)}")
    
    # Find missing tables
    missing_tables = model_tables - existing_tables
    if missing_tables:
        print(f"\n📋 Missing tables to create: {', '.join(missing_tables)}")
        # Create missing tables only
        for table_name in missing_tables:
            table = Base.metadata.tables[table_name]
            table.create(engine)
            print(f"  ✅ Created table: {table_name}")
    else:
        print("\n✅ All tables exist")
    
    # Check for missing columns in existing tables
    print("\n🔍 Checking for missing columns...")
    with engine.connect() as conn:
        for table_name in existing_tables:
            if table_name not in Base.metadata.tables:
                continue
                
            # Get existing columns
            existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
            
            # Get model columns
            model_table = Base.metadata.tables[table_name]
            model_cols = {col.name for col in model_table.columns}
            
            # Find missing columns
            missing_cols = model_cols - existing_cols
            
            if missing_cols:
                print(f"\n  Table '{table_name}' missing columns: {', '.join(missing_cols)}")
                for col_name in missing_cols:
                    col = model_table.columns[col_name]
                    
                    # Determine column type
                    col_type = str(col.type)
                    
                    # Determine if nullable
                    nullable = "NULL" if col.nullable else "NOT NULL"
                    
                    # Determine default value
                    default = ""
                    if col.default is not None:
                        if hasattr(col.default, 'arg'):
                            if callable(col.default.arg):
                                # Skip callable defaults (like datetime.utcnow)
                                default = ""
                            else:
                                default = f" DEFAULT {col.default.arg}"
                    
                    # Build ALTER TABLE statement
                    # SQLite doesn't support NOT NULL on ALTER TABLE ADD COLUMN
                    # So we add as nullable first
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{default}"
                    
                    try:
                        conn.execute(text(alter_sql))
                        conn.commit()
                        print(f"    ✅ Added column: {col_name} {col_type}")
                    except Exception as e:
                        print(f"    ❌ Failed to add column {col_name}: {e}")
                        conn.rollback()
    
    print(f"\n✅ Database schema update complete!")
    print(f"Database size: {db_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    update_database_schema()

