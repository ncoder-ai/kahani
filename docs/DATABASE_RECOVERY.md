# Database Recovery Guide

## Emergency Recovery from Deleted Database

If you accidentally deleted `kahani.db` and/or the `chromadb` directory, follow these steps:

### Quick Recovery (Ubuntu Server)

1. **SSH into your Ubuntu server**

2. **Navigate to the Kahani directory**
   ```bash
   cd /path/to/kahani
   ```

3. **Check for backups first**
   ```bash
   ls -lh backend/backups/
   ```
   
   If you see `.db` files, you have backups! Skip to step 5.

4. **If no backups exist, recreate the database:**
   ```bash
   cd backend
   source ../.venv/bin/activate  # Activate virtual environment
   python3 recover_database.py
   ```
   
   Or manually:
   ```bash
   # Recreate database schema
   python3 init_database.py
   alembic upgrade head
   
   # Recreate ChromaDB directory (will be auto-initialized on startup)
   rm -rf data/chromadb
   mkdir -p data/chromadb
   ```

5. **If backups exist, restore from backup:**
   ```bash
   cd backend
   source ../.venv/bin/activate
   python3 recover_database.py
   ```
   
   Select option 1 to restore from backup.

6. **Restart the application**
   ```bash
   # For development
   ./start-dev.sh
   
   # For production
   ./start-prod.sh
   ```

### What Gets Lost

- **kahani.db**: All SQLite data (users, stories, scenes, characters, settings)
- **chromadb/**: All semantic memory (embeddings, character moments, plot events)

### What Gets Recreated

- **Database schema**: Automatically recreated via Alembic migrations
- **ChromaDB**: Automatically recreated when the app starts (empty, will rebuild over time)

### After Recovery

1. **Register a new admin user** (first user becomes admin automatically)
2. **Recreate your stories** (data is lost, but you can start fresh)
3. **Semantic memory will rebuild** as you create new stories

### Prevention: Set Up Automatic Backups

Create a cron job to backup your database regularly:

```bash
# Edit crontab
crontab -e

# Add this line to backup daily at 2 AM
0 2 * * * cd /path/to/kahani/backend && /path/to/.venv/bin/python backup_database.py create --reason "daily_backup" >> /var/log/kahani_backup.log 2>&1
```

Or create a simple backup script:

```bash
#!/bin/bash
# /path/to/kahani/backend/backup_daily.sh
cd /path/to/kahani/backend
source ../.venv/bin/activate
python3 backup_database.py create --reason "daily_backup"
# Keep only last 7 days of backups
find backups/ -name "*.db" -mtime +7 -delete
```

Make it executable:
```bash
chmod +x /path/to/kahani/backend/backup_daily.sh
```

### Manual Backup

To create a backup manually:

```bash
cd backend
source ../.venv/bin/activate
python3 backup_database.py create --reason "before_important_change"
```

### File Locations

- **Database**: `backend/data/kahani.db`
- **ChromaDB**: `backend/data/chromadb/`
- **Backups**: `backend/backups/`
- **Recovery script**: `backend/recover_database.py`

---

**Remember**: Regular backups are essential! Set up automated backups to prevent data loss.


