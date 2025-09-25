#!/usr/bin/env python3
"""
Database backup utility for Kahani
Creates timestamped backups and manages backup retention
"""

import os
import shutil
import sqlite3
from datetime import datetime, timedelta
import argparse
import json

def get_db_path():
    """Get the database file path"""
    return os.path.join(os.path.dirname(__file__), 'data', 'kahani.db')

def get_backup_dir():
    """Get the backup directory"""
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def create_backup(reason="manual"):
    """Create a timestamped backup of the database"""
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return None
    
    backup_dir = get_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"kahani_backup_{timestamp}_{reason}.db"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # Create backup using SQLite backup API (safer than file copy)
    try:
        # Connect to source database
        source_conn = sqlite3.connect(db_path)
        
        # Connect to backup database  
        backup_conn = sqlite3.connect(backup_path)
        
        # Perform the backup
        source_conn.backup(backup_conn)
        
        # Close connections
        source_conn.close()
        backup_conn.close()
        
        # Create metadata file
        metadata = {
            "created_at": datetime.now().isoformat(),
            "reason": reason,
            "source_file": db_path,
            "file_size": os.path.getsize(backup_path)
        }
        
        metadata_path = backup_path.replace('.db', '_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Database backup created: {backup_path}")
        print(f"📊 Size: {metadata['file_size']} bytes")
        return backup_path
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return None

def list_backups():
    """List all available backups"""
    backup_dir = get_backup_dir()
    
    if not os.path.exists(backup_dir):
        print("📁 No backup directory found")
        return []
    
    backups = []
    for file in os.listdir(backup_dir):
        if file.endswith('.db'):
            backup_path = os.path.join(backup_dir, file)
            metadata_path = backup_path.replace('.db', '_metadata.json')
            
            metadata = {}
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except:
                    pass
            
            backup_info = {
                'path': backup_path,
                'filename': file,
                'size': os.path.getsize(backup_path),
                'created_at': metadata.get('created_at', 'unknown'),
                'reason': metadata.get('reason', 'unknown')
            }
            backups.append(backup_info)
    
    # Sort by creation time (newest first)
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    
    if backups:
        print(f"📋 Found {len(backups)} database backups:")
        for i, backup in enumerate(backups, 1):
            print(f"  {i}. {backup['filename']}")
            print(f"     Created: {backup['created_at']}")
            print(f"     Reason: {backup['reason']}")
            print(f"     Size: {backup['size']} bytes")
            print()
    else:
        print("📂 No backups found")
    
    return backups

def restore_backup(backup_path):
    """Restore database from backup"""
    db_path = get_db_path()
    
    if not os.path.exists(backup_path):
        print(f"❌ Backup file not found: {backup_path}")
        return False
    
    # Create a backup of current database before restoring
    print("🔄 Creating backup of current database before restore...")
    current_backup = create_backup("pre_restore")
    
    try:
        # Replace current database with backup
        shutil.copy2(backup_path, db_path)
        print(f"✅ Database restored from: {backup_path}")
        return True
        
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        # Try to restore the pre-restore backup
        if current_backup and os.path.exists(current_backup):
            try:
                shutil.copy2(current_backup, db_path)
                print("🔄 Restored original database")
            except:
                print("❌ Failed to restore original database")
        return False

def cleanup_old_backups(days_to_keep=30):
    """Remove backups older than specified days"""
    backup_dir = get_backup_dir()
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    removed_count = 0
    for file in os.listdir(backup_dir):
        if file.endswith('.db'):
            file_path = os.path.join(backup_dir, file)
            file_date = datetime.fromtimestamp(os.path.getctime(file_path))
            
            if file_date < cutoff_date:
                try:
                    os.remove(file_path)
                    # Also remove metadata file
                    metadata_path = file_path.replace('.db', '_metadata.json')
                    if os.path.exists(metadata_path):
                        os.remove(metadata_path)
                    removed_count += 1
                    print(f"🗑️  Removed old backup: {file}")
                except Exception as e:
                    print(f"❌ Failed to remove {file}: {e}")
    
    if removed_count > 0:
        print(f"🧹 Cleaned up {removed_count} old backups")
    else:
        print("✨ No old backups to clean up")

def main():
    parser = argparse.ArgumentParser(description='Kahani Database Backup Utility')
    parser.add_argument('action', choices=['create', 'list', 'restore', 'cleanup'], 
                       help='Action to perform')
    parser.add_argument('--reason', default='manual', 
                       help='Reason for backup (default: manual)')
    parser.add_argument('--backup-path', 
                       help='Path to backup file for restore')
    parser.add_argument('--days', type=int, default=30,
                       help='Days to keep backups for cleanup (default: 30)')
    
    args = parser.parse_args()
    
    if args.action == 'create':
        create_backup(args.reason)
    elif args.action == 'list':
        list_backups()
    elif args.action == 'restore':
        if not args.backup_path:
            print("❌ --backup-path is required for restore")
            return 1
        restore_backup(args.backup_path)
    elif args.action == 'cleanup':
        cleanup_old_backups(args.days)
    
    return 0

if __name__ == '__main__':
    exit(main())