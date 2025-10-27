# Alembic Migration State Fix - Summary

## Problem

When running `install.sh` on a test server with an existing database, the installation failed with:

```
sqlite3.OperationalError: table user_settings already exists
```

This occurred because:
1. The database had tables created via `Base.metadata.create_all()`
2. The `alembic_version` table was either missing, empty, or had the wrong version
3. Alembic tried to run migration `001` from scratch, attempting to create tables that already existed

## Root Cause

The `init_database.py` script had flawed logic for determining the latest migration version:
- It sorted migration files **alphabetically** to find the "latest" migration
- Alphabetical sort: `001, 002, ..., 008, bbf4e254a824, c7923c6e866e, ec1f4e1c996a`
- Actual migration chain: `001 → 002 → ... → 008 → ec1f4e1c996a → bbf4e254a824 → c7923c6e866e`
- Result: New databases were stamped with the wrong version

## Solution

### 1. Fixed `init_database.py` (Permanent Fix)

**File:** `backend/init_database.py` (lines 85-125)

**Change:** Replaced alphabetical file sorting with Alembic's built-in API:

```python
from alembic.script import ScriptDirectory
from alembic.config import Config as AlembicConfig

alembic_cfg = AlembicConfig(str(alembic_ini_path))
script = ScriptDirectory.from_config(alembic_cfg)
head_revision = script.get_current_head()
```

**Benefits:**
- ✅ Always gets the correct HEAD revision
- ✅ Follows Alembic's dependency chain
- ✅ Works regardless of migration file naming
- ✅ All future fresh installs will work correctly

### 2. Created `repair_alembic_version.py` (Repair Utility)

**File:** `backend/repair_alembic_version.py` (new)

**Purpose:** Detects and repairs existing databases with version mismatches

**Features:**
- Inspects database schema (tables, columns)
- Determines which migration version matches the current schema
- Stamps `alembic_version` table with correct version
- Provides clear output about actions taken
- Idempotent (safe to run multiple times)

**Schema Detection Logic:**
- Checks for presence of specific tables and columns added in each migration
- Works backwards from latest to earliest migration
- Conservative approach - prompts if uncertain

### 3. Updated `install.sh` (Orchestration)

**File:** `install.sh` (lines 183-203)

**Change:** Added repair step before running migrations on existing databases:

```bash
if [[ -f backend/data/kahani.db ]]; then
    log_warning "Database already exists, checking Alembic state..."
    # Repair any Alembic version mismatches before running migrations
    cd backend && $python_cmd repair_alembic_version.py && cd ..
    log_info "Running migrations..."
    source .venv/bin/activate
    cd backend && alembic upgrade head && cd ..
    deactivate
else
    log_info "Initializing new database..."
    cd backend && $python_cmd init_database.py && cd ..
fi
```

**Flow:**
- **New database:** `init_database.py` creates with correct HEAD stamp
- **Existing database:** `repair_alembic_version.py` fixes version, then migrations run

## Why This Is a Permanent Fix

1. **Root Cause Addressed:** `init_database.py` now uses proper Alembic API
2. **Future-Proof:** All new installations will create correctly stamped databases
3. **Backward Compatible:** Existing broken databases are automatically repaired
4. **No Manual Intervention:** The fix is transparent during `install.sh`
5. **Standalone Utility:** Can manually run `repair_alembic_version.py` if needed

## Quick Fix for Your Test Server

### Option 1: Run the Repair Utility

```bash
cd backend
python3 repair_alembic_version.py
cd ..
./install.sh
```

### Option 2: Manual SQL Fix

```bash
cd backend
sqlite3 data/kahani.db "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY);"
sqlite3 data/kahani.db "INSERT OR REPLACE INTO alembic_version VALUES ('c7923c6e866e');"
cd ..
./install.sh
```

### Option 3: Fresh Installation

```bash
# Backup existing database if needed
mv backend/data/kahani.db backend/data/kahani.db.backup

# Run fresh install
./install.sh
```

## Testing

See `docs/alembic-repair-testing.md` for comprehensive testing scenarios including:
- Fresh installation (no database)
- Existing database with correct version
- Existing database with missing `alembic_version` (your case)
- Existing database with wrong version
- Manual repair utility usage

## Files Changed

1. ✅ `backend/init_database.py` - Fixed HEAD revision detection
2. ✅ `backend/repair_alembic_version.py` - New repair utility
3. ✅ `install.sh` - Added repair step for existing databases
4. ✅ `docs/alembic-repair-testing.md` - Testing documentation

## Verification

After applying the fix, verify with:

```bash
# Check Alembic version
sqlite3 backend/data/kahani.db "SELECT version_num FROM alembic_version;"
# Should output: c7923c6e866e

# Check no pending migrations
cd backend && alembic current && cd ..
# Should show: c7923c6e866e (head)
```

## Migration Chain Reference

Current migration chain (for reference):
```
001 (Add user settings)
  ↓
002 (Add semantic memory models)
  ↓
003 (Add admin system)
  ↓
004 (Add scenario field to stories)
  ↓
005 (Add scenario field to stories - duplicate)
  ↓
006 (Add role to story characters)
  ↓
007 (Add color themes)
  ↓
008 (Add scene container style)
  ↓
ec1f4e1c996a (Add engine specific settings)
  ↓
bbf4e254a824 (Remove scene container style)
  ↓
c7923c6e866e (Add character assistant settings) ← HEAD
```

## Summary

This fix ensures that:
- ✅ New databases are always created with the correct Alembic version
- ✅ Existing databases are automatically repaired during installation
- ✅ No manual intervention is required
- ✅ The solution is permanent and future-proof
- ✅ A standalone repair utility is available for edge cases

The error you encountered on your test server will no longer occur with these changes.

