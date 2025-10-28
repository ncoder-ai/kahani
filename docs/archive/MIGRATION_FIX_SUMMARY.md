# Database Migration Error Fix

## The Problem
When running `install.sh`, users encountered:
```
sqlite3.OperationalError: table user_settings already exists
```

## Root Cause
The issue was in `backend/app/main.py` at line 52:
```python
Base.metadata.create_all(bind=engine)
```

This line was creating ALL database tables every time the FastAPI app started, including:
- When running the web server
- When running Alembic migrations (because migrations import the app)
- During tests

### The Conflict
1. **`init_database.py`** creates all base tables using `Base.metadata.create_all()`
2. **`install.sh`** then runs `alembic upgrade head`
3. **Alembic imports `app.main`** which triggers `Base.metadata.create_all()` AGAIN
4. This creates tables that Alembic was supposed to create → **ERROR**

## The Fix

### ✅ Removed Auto-Creation from main.py

**File: `backend/app/main.py`**
```python
# REMOVED THIS LINE:
# Base.metadata.create_all(bind=engine)

# REPLACED WITH COMMENT:
# NOTE: We do NOT create tables here anymore! 
# Database schema is managed by:
# 1. init_database.py for fresh installations
# 2. Alembic migrations for schema updates
```

### ✅ Updated install.sh Logic

**File: `install.sh`**
```bash
if [[ -f backend/data/kahani.db ]]; then
    # Existing database: just run new migrations
    alembic upgrade head
else
    # New database: 
    # 1. Create all tables with init_database.py
    python init_database.py
    # 2. Stamp alembic so it knows base schema exists
    alembic stamp head
fi
```

## How It Works Now

### Fresh Installation
```
1. init_database.py
   └─> Base.metadata.create_all()  # Creates ALL tables
   
2. alembic stamp head
   └─> Marks database as "at latest version"
   
3. Server starts
   └─> main.py loads but does NOT create tables
```

### Existing Installation  
```
1. alembic upgrade head
   └─> Only applies NEW migrations
   
2. Server starts
   └─> main.py loads but does NOT create tables
```

### Adding New Fields (Dev Workflow)
```
1. Update model in backend/app/models/
2. Create migration: alembic revision -m "add new field"
3. Edit migration file
4. Apply: alembic upgrade head
5. Server restart picks up new schema (no table creation)
```

## Why This Fix is Permanent

1. **Single Responsibility**: 
   - `init_database.py` = initial schema
   - `alembic` = schema changes
   - `main.py` = web server (no schema management)

2. **No Import Side Effects**: 
   - Importing `app.main` no longer modifies the database
   - Safe for tests, migrations, and utilities

3. **Alembic is Source of Truth**:
   - After initial creation, Alembic tracks all changes
   - No conflicts between manual and automatic table creation

## Files Changed

- ✅ `backend/app/main.py` - Removed `Base.metadata.create_all()`
- ✅ `install.sh` - Added `alembic stamp head` after init_database
- ✅ `docs/database-migration-troubleshooting.md` - Updated documentation
- ✅ `backend/fix_alembic_version.py` - Helper script for fixing broken databases

## For Users with Existing Error

If you already encountered the error:

```bash
# Option 1: Use the fix script
cd backend
python fix_alembic_version.py

# Option 2: Manual fix
cd backend
source ../.venv/bin/activate
alembic stamp head
deactivate

# Option 3: Fresh start
rm backend/data/kahani.db
./install.sh
```

## Testing the Fix

The fix has been tested and verified to:
- ✅ Work on fresh installations
- ✅ Work on existing databases
- ✅ Not interfere with running server
- ✅ Allow Alembic migrations to run cleanly
- ✅ Prevent table already exists errors

---

**Status**: ✅ FIXED - Ready to deploy
**Date**: October 27, 2025
