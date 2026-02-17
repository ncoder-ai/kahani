#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for Kahani

This script migrates all data from a SQLite database to PostgreSQL.
It handles foreign key relationships and preserves data integrity.

Usage:
    python migrate_sqlite_to_postgres.py [options]

Options:
    --sqlite-url    SQLite database URL (default: from config or sqlite:///./data/kahani.db)
    --postgres-url  PostgreSQL database URL (default: from DATABASE_URL env var)
    --verify-only   Only verify data counts, don't migrate
    --dry-run       Show what would be migrated without actually migrating
    --skip-backup   Skip creating a backup of SQLite database
"""

import os
import sys
import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Add the backend directory to the path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_table_order() -> List[str]:
    """
    Return tables in order that respects foreign key dependencies.
    Tables with no dependencies come first, then tables that depend on them.
    """
    return [
        # Base tables (no foreign keys)
        'users',
        'system_settings',
        'writing_style_presets',
        
        # User-dependent tables
        'user_settings',
        'tts_settings',
        'prompt_templates',
        'stories',
        'characters',
        
        # Story-dependent tables
        'story_branches',
        'story_characters',
        'chapters',
        
        # Chapter-dependent tables
        'chapter_characters',  # Association table
        'chapter_summary_batches',
        'scenes',
        
        # Scene-dependent tables
        'scene_variants',
        'scene_choices',
        'scene_audio',
        'scene_embeddings',
        
        # Character-dependent tables
        'character_memories',
        'character_states',
        
        # Story flow and other tables
        'story_flows',
        'plot_events',
        'location_states',
        'object_states',
        'entity_state_batches',
        
        # NPC tracking tables
        'npc_mentions',
        'npc_tracking',
        'npc_tracking_snapshots',
    ]


def create_backup(sqlite_path: str) -> str:
    """Create a backup of the SQLite database."""
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{sqlite_path}.backup_{timestamp}"
    
    logger.info(f"Creating backup: {backup_path}")
    shutil.copy2(sqlite_path, backup_path)
    logger.info(f"Backup created successfully")
    
    return backup_path


def get_sqlite_path_from_url(url: str) -> str:
    """Extract file path from SQLite URL."""
    if url.startswith('sqlite:///'):
        path = url.replace('sqlite:///', '')
        if not path.startswith('/'):
            # Relative path
            return str(backend_dir / path)
        return path
    raise ValueError(f"Invalid SQLite URL: {url}")


def run_alembic_migrations(postgres_url: str) -> bool:
    """Run Alembic migrations on the PostgreSQL database."""
    logger.info("Running Alembic migrations on PostgreSQL...")
    
    # Set the DATABASE_URL environment variable for Alembic
    os.environ['DATABASE_URL'] = postgres_url
    
    try:
        import subprocess
        result = subprocess.run(
            ['alembic', 'upgrade', 'head'],
            cwd=str(backend_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Alembic migration failed: {result.stderr}")
            return False
        
        logger.info("Alembic migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error running Alembic migrations: {e}")
        return False


def get_table_data(engine, table_name: str) -> List[Dict[str, Any]]:
    """Fetch all data from a table."""
    with engine.connect() as conn:
        result = conn.execute(text(f'SELECT * FROM "{table_name}"'))
        columns = result.keys()
        rows = []
        for row in result:
            rows.append(dict(zip(columns, row)))
        return rows


def get_table_count(engine, table_name: str) -> int:
    """Get the count of rows in a table."""
    with engine.connect() as conn:
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        return result.scalar()


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def get_boolean_columns(engine, table_name: str) -> set:
    """Get a set of column names that are boolean type in PostgreSQL."""
    boolean_cols = set()
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            AND table_schema = 'public'
            AND data_type = 'boolean'
        """))
        for row in result:
            boolean_cols.add(row[0])
    return boolean_cols


def insert_data(engine, table_name: str, data: List[Dict[str, Any]], batch_size: int = 100) -> int:
    """Insert data into a table in batches."""
    if not data:
        return 0
    
    inserted = 0
    columns = data[0].keys()
    
    # Get boolean columns for this table
    boolean_columns = get_boolean_columns(engine, table_name)
    
    with engine.connect() as conn:
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            
            for row in batch:
                # Build INSERT statement
                cols = ', '.join([f'"{c}"' for c in row.keys()])
                placeholders = ', '.join([f':{c}' for c in row.keys()])
                
                # Handle NULL values and special types
                # Convert SQLite boolean integers (0/1) to PostgreSQL booleans (True/False)
                clean_row = {}
                for k, v in row.items():
                    if v is None:
                        clean_row[k] = None
                    elif k in boolean_columns and isinstance(v, int) and v in (0, 1):
                        # This column is a boolean in PostgreSQL, convert integer to boolean
                        clean_row[k] = bool(v)
                    else:
                        clean_row[k] = v
                
                try:
                    conn.execute(
                        text(f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})'),
                        clean_row
                    )
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Error inserting row into {table_name}: {e}")
                    logger.debug(f"Row data: {clean_row}")
            
            conn.commit()
    
    return inserted


def reset_sequences(pg_engine, table_name: str):
    """Reset PostgreSQL sequences for auto-increment columns."""
    with pg_engine.connect() as conn:
        # Find sequences for this table
        result = conn.execute(text(f"""
            SELECT column_name, column_default
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            AND column_default LIKE 'nextval%'
        """))
        
        for row in result:
            column_name = row[0]
            # Get max value and reset sequence
            max_result = conn.execute(text(f'SELECT MAX("{column_name}") FROM "{table_name}"'))
            max_val = max_result.scalar() or 0
            
            # Extract sequence name from column_default
            seq_result = conn.execute(text(f"""
                SELECT pg_get_serial_sequence('{table_name}', '{column_name}')
            """))
            seq_name = seq_result.scalar()
            
            if seq_name:
                conn.execute(text(f"SELECT setval('{seq_name}', {max_val + 1}, false)"))
                logger.debug(f"Reset sequence {seq_name} to {max_val + 1}")
        
        conn.commit()


def migrate_table(sqlite_engine, pg_engine, table_name: str, dry_run: bool = False) -> tuple:
    """Migrate a single table from SQLite to PostgreSQL."""
    if not table_exists(sqlite_engine, table_name):
        logger.debug(f"Table {table_name} does not exist in SQLite, skipping")
        return (0, 0)
    
    if not table_exists(pg_engine, table_name):
        logger.warning(f"Table {table_name} does not exist in PostgreSQL, skipping")
        return (0, 0)
    
    # Get data from SQLite
    data = get_table_data(sqlite_engine, table_name)
    source_count = len(data)
    
    if source_count == 0:
        logger.info(f"  {table_name}: 0 rows (empty)")
        return (0, 0)
    
    if dry_run:
        logger.info(f"  {table_name}: {source_count} rows (dry run)")
        return (source_count, 0)
    
    # Clear existing data in PostgreSQL
    with pg_engine.connect() as conn:
        conn.execute(text(f'DELETE FROM "{table_name}"'))
        conn.commit()
    
    # Insert data
    inserted = insert_data(pg_engine, table_name, data)
    
    # Reset sequences
    reset_sequences(pg_engine, table_name)
    
    logger.info(f"  {table_name}: {inserted}/{source_count} rows migrated")
    
    return (source_count, inserted)


def verify_migration(sqlite_engine, pg_engine) -> bool:
    """Verify that migration was successful by comparing row counts."""
    logger.info("\nVerifying migration...")
    
    all_match = True
    table_order = get_table_order()
    
    for table_name in table_order:
        if not table_exists(sqlite_engine, table_name):
            continue
        if not table_exists(pg_engine, table_name):
            continue
        
        sqlite_count = get_table_count(sqlite_engine, table_name)
        pg_count = get_table_count(pg_engine, table_name)
        
        if sqlite_count == pg_count:
            status = "✓"
        else:
            status = "✗"
            all_match = False
        
        logger.info(f"  {status} {table_name}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
    
    return all_match


def main():
    parser = argparse.ArgumentParser(
        description='Migrate Kahani database from SQLite to PostgreSQL'
    )
    parser.add_argument(
        '--sqlite-url',
        default=None,
        help='SQLite database URL (default: sqlite:///./data/kahani.db)'
    )
    parser.add_argument(
        '--postgres-url',
        default=None,
        help='PostgreSQL database URL (default: from DATABASE_URL env var)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify data counts, do not migrate'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually migrating'
    )
    parser.add_argument(
        '--skip-backup',
        action='store_true',
        help='Skip creating a backup of SQLite database'
    )
    
    args = parser.parse_args()
    
    # Determine database URLs
    sqlite_url = args.sqlite_url or 'sqlite:///./data/kahani.db'
    postgres_url = args.postgres_url or os.environ.get('DATABASE_URL')
    
    if not postgres_url:
        logger.error("PostgreSQL URL not provided. Set DATABASE_URL environment variable or use --postgres-url")
        sys.exit(1)
    
    if not postgres_url.startswith('postgresql'):
        logger.error(f"Invalid PostgreSQL URL: {postgres_url}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Kahani SQLite to PostgreSQL Migration")
    logger.info("=" * 60)
    logger.info(f"SQLite URL: {sqlite_url}")
    logger.info(f"PostgreSQL URL: {postgres_url.split('@')[0]}@...")  # Hide password
    
    # Create engines
    sqlite_engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=NullPool
    )
    
    pg_engine = create_engine(postgres_url, poolclass=NullPool)
    
    # Verify connections
    try:
        with sqlite_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✓ SQLite connection successful")
    except Exception as e:
        logger.error(f"✗ SQLite connection failed: {e}")
        sys.exit(1)
    
    try:
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✓ PostgreSQL connection successful")
    except Exception as e:
        logger.error(f"✗ PostgreSQL connection failed: {e}")
        sys.exit(1)
    
    # Verify only mode
    if args.verify_only:
        success = verify_migration(sqlite_engine, pg_engine)
        sys.exit(0 if success else 1)
    
    # Create backup
    if not args.skip_backup and not args.dry_run:
        try:
            sqlite_path = get_sqlite_path_from_url(sqlite_url)
            backup_path = create_backup(sqlite_path)
            logger.info(f"Backup created: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            sys.exit(1)
    
    # Run Alembic migrations on PostgreSQL
    if not args.dry_run:
        if not run_alembic_migrations(postgres_url):
            logger.error("Alembic migrations failed. Aborting migration.")
            sys.exit(1)
    
    # Migrate tables
    logger.info("\nMigrating tables...")
    
    table_order = get_table_order()
    total_source = 0
    total_migrated = 0
    
    for table_name in table_order:
        source, migrated = migrate_table(
            sqlite_engine, pg_engine, table_name, dry_run=args.dry_run
        )
        total_source += source
        total_migrated += migrated
    
    # Summary
    logger.info("\n" + "=" * 60)
    if args.dry_run:
        logger.info(f"DRY RUN: Would migrate {total_source} total rows")
    else:
        logger.info(f"Migration complete: {total_migrated}/{total_source} rows migrated")
    
    # Verify migration
    if not args.dry_run:
        success = verify_migration(sqlite_engine, pg_engine)
        if success:
            logger.info("\n✓ Migration verified successfully!")
        else:
            logger.warning("\n⚠ Some tables have mismatched counts. Please investigate.")
    
    logger.info("=" * 60)


if __name__ == '__main__':
    main()

