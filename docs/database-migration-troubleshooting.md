# Database Migration Troubleshooting

## Issue: "table user_settings already exists" Error

### Problem Description
When running `install.sh`, you may encounter this error:
```
sqlite3.OperationalError: table user_settings already exists
```

This happens when the database has tables but Alembic doesn't know about them (missing version tracking).

### **PERMANENT FIX APPLIED** ✅

The root cause has been fixed in the codebase:

**What Changed:**
1. **`init_database.py`** now uses Alembic migrations exclusively to create tables (not `Base.metadata.create_all()`)
2. **`install.sh`** properly handles both new and existing databases
3. **Single source of truth:** Alembic manages ALL schema changes

**How It Works Now:**

```bash
# New installation
install.sh
  └─> init_database.py
       └─> alembic upgrade head  # Creates all tables via migrations

# Existing installation  
install.sh
  └─> alembic upgrade head  # Only applies new migrations
```

This ensures Alembic always knows the database state and prevents conflicts.

### Manual Fix for Existing Broken Installations

If you already have a database with this issue, use one of these options:

#### Option 1: Use the Fix Script (Recommended)
```bash
cd backend
python fix_alembic_version.py
```

This script will:
- Detect if your database has tables but no Alembic tracking
- Automatically stamp it to the current version
- Verify the fix worked

#### Option 2: Manual Stamp
```bash
cd backend
source ../.venv/bin/activate
alembic stamp head
deactivate
cd ..
```

#### Option 3: Fresh Start
```bash
# Backup your database first!
cp backend/data/kahani.db backend/data/kahani.db.backup

# Remove the database
rm backend/data/kahani.db

# Pull latest code with fixes
git pull origin dev

# Run the install script again
./install.sh
```

### Root Cause Analysis

**Old (Broken) Approach:**
```python
# init_database.py - OLD CODE ❌
Base.metadata.create_all(bind=engine)  # Created tables directly
# Then install.sh ran: alembic upgrade head  # Tried to create again → ERROR
```

**New (Fixed) Approach:**
```python
# init_database.py - NEW CODE ✅
subprocess.run(["alembic", "upgrade", "head"])  # Uses Alembic for everything
```

**Why This Matters:**
- Alembic maintains a `alembic_version` table to track which migrations have run
- When you create tables manually, Alembic doesn't know they exist
- Subsequent migrations try to create the same tables → conflict
- By using Alembic from the start, tracking is always in sync

### Creating New Migrations

After the database is properly initialized, create new migrations like this:

```bash
cd backend
source ../.venv/bin/activate

# Generate a new migration
alembic revision -m "description of changes"

# Edit the generated file in backend/alembic/versions/
# Then apply it:
alembic upgrade head

deactivate
```

### Checking Migration Status

```bash
cd backend
source ../.venv/bin/activate

# Show current version
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic show head

deactivate
```

## Related Files

- `install.sh` - Main installation script (now fixed)
- `backend/init_database.py` - Creates initial database and tables
- `backend/alembic/env.py` - Alembic configuration
- `backend/alembic/versions/` - Migration files

## Prevention

The fix in `install.sh` prevents this issue by:
1. Detecting if database is new or existing
2. For new databases: stamp Alembic after table creation
3. For existing databases: only run pending migrations

This ensures Alembic and the actual database state stay synchronized.
