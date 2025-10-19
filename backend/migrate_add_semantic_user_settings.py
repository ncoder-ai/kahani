"""
Migration: Add Semantic Memory Settings to UserSettings

Adds semantic memory configuration fields to user_settings table,
allowing per-user customization of semantic context strategy.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text, inspect
from app.config import settings

def run_migration():
    print("🔧 Migrating UserSettings: Adding Semantic Memory Fields...")
    
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    
    # Check if user_settings table exists
    if 'user_settings' not in inspector.get_table_names():
        print("❌ Error: user_settings table not found!")
        return 1
    
    # Get existing columns
    existing_columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    # Define new columns to add
    new_columns = {
        'enable_semantic_memory': 'BOOLEAN DEFAULT 1',  # True by default
        'context_strategy': "VARCHAR(20) DEFAULT 'hybrid'",  # 'linear' or 'hybrid'
        'semantic_search_top_k': 'INTEGER DEFAULT 5',
        'semantic_scenes_in_context': 'INTEGER DEFAULT 5',
        'semantic_context_weight': 'REAL DEFAULT 0.4',
        'character_moments_in_context': 'INTEGER DEFAULT 3',
        'auto_extract_character_moments': 'BOOLEAN DEFAULT 1',
        'auto_extract_plot_events': 'BOOLEAN DEFAULT 1',
        'extraction_confidence_threshold': 'INTEGER DEFAULT 70',
    }
    
    with engine.connect() as conn:
        columns_added = 0
        columns_skipped = 0
        
        for column_name, column_def in new_columns.items():
            if column_name in existing_columns:
                print(f"   ⏭️  Column '{column_name}' already exists, skipping")
                columns_skipped += 1
                continue
            
            try:
                # SQLite ALTER TABLE ADD COLUMN syntax
                sql = f"ALTER TABLE user_settings ADD COLUMN {column_name} {column_def}"
                conn.execute(text(sql))
                conn.commit()
                print(f"   ✅ Added column: {column_name}")
                columns_added += 1
            except Exception as e:
                print(f"   ❌ Error adding column {column_name}: {e}")
                return 1
        
        print(f"\n📊 Migration Summary:")
        print(f"   - Columns added: {columns_added}")
        print(f"   - Columns skipped: {columns_skipped}")
        print(f"   - Total semantic fields: {len(new_columns)}")
        
        if columns_added > 0:
            print(f"\n✅ Migration completed successfully!")
            print(f"\n📋 New Fields:")
            print(f"   - enable_semantic_memory: Per-user toggle")
            print(f"   - context_strategy: 'linear' or 'hybrid'")
            print(f"   - semantic_search_top_k: Number of similar scenes to retrieve")
            print(f"   - semantic_scenes_in_context: Max semantic scenes in context")
            print(f"   - semantic_context_weight: Balance between recent vs semantic")
            print(f"   - character_moments_in_context: Max character moments")
            print(f"   - auto_extract_character_moments: Toggle extraction")
            print(f"   - auto_extract_plot_events: Toggle extraction")
            print(f"   - extraction_confidence_threshold: Quality threshold (0-100)")
        else:
            print(f"\n⏭️  No changes needed - all columns already exist")
    
    return 0


def rollback_migration():
    print("🔄 Rolling back Semantic User Settings migration...")
    
    engine = create_engine(settings.database_url)
    
    columns_to_remove = [
        'enable_semantic_memory',
        'context_strategy',
        'semantic_search_top_k',
        'semantic_scenes_in_context',
        'semantic_context_weight',
        'character_moments_in_context',
        'auto_extract_character_moments',
        'auto_extract_plot_events',
        'extraction_confidence_threshold',
    ]
    
    print("⚠️  WARNING: SQLite doesn't support DROP COLUMN directly.")
    print("   You would need to:")
    print("   1. Create new table without these columns")
    print("   2. Copy data")
    print("   3. Drop old table")
    print("   4. Rename new table")
    print("\n   Or restore from backup.")
    
    return 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Semantic User Settings Migration")
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration"
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        sys.exit(rollback_migration())
    else:
        sys.exit(run_migration())

