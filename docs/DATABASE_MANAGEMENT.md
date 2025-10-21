# Database Management Guide

## ⚠️ CRITICAL: Always Backup Before Schema Changes

**NEVER** make database schema changes without a backup. Use these tools:

## Backup Management

### Create a backup
```bash
cd backend
python backup_database.py create --reason "before_feature_x"
```

### List all backups
```bash
python backup_database.py list
```

### Restore from backup
```bash
python backup_database.py restore --backup-path backups/kahani_backup_YYYYMMDD_HHMMSS_reason.db
```

### Cleanup old backups
```bash
python backup_database.py cleanup --days 30
```

## Safe Database Migration

If you need to recreate the database (schema changes):

```bash
cd backend
python safe_migrate.py
```

This script will:
1. **Automatically create a backup first**
2. Ask for confirmation
3. Perform the migration
4. Provide restore instructions if anything goes wrong

## Emergency Recovery

If data was accidentally lost:

```bash
cd backend
python safe_migrate.py emergency
```

This shows recovery instructions and lists available backups.

## Development Workflow

### Before making schema changes:
1. `python backup_database.py create --reason "before_schema_change"`
2. Make your changes
3. Test thoroughly
4. Keep backup until changes are confirmed working

### Regular maintenance:
- Create backups before major features
- Clean up old backups monthly: `python backup_database.py cleanup`
- Test restore process occasionally

## File Locations

- **Database**: `backend/data/kahani.db`
- **Backups**: `backend/backups/`
- **Scripts**: `backend/backup_database.py`, `backend/safe_migrate.py`

## Recovery Examples

```bash
# List available backups
python backup_database.py list

# Restore from a specific backup
python backup_database.py restore --backup-path backups/kahani_backup_20240925_143022_before_schema_change.db

# Create backup before risky operation
python backup_database.py create --reason "before_llm_config_change"
```

---

**Remember**: A backup that doesn't exist can't save your data! 🔒