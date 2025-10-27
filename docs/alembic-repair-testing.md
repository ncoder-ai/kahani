# Alembic Version Repair - Testing Guide

This document describes how to test the Alembic version repair functionality across different database states.

## Overview

The fix consists of three components:
1. **init_database.py** - Uses Alembic API to correctly stamp new databases with HEAD revision
2. **repair_alembic_version.py** - Detects and repairs existing databases with version mismatches
3. **install.sh** - Orchestrates both utilities during installation

## Test Scenarios

### Scenario 1: Fresh Installation (No Database)

**Setup:**
```bash
# Ensure no database exists
rm -f backend/data/kahani.db
```

**Test:**
```bash
./install.sh
```

**Expected Result:**
- ✅ `init_database.py` creates new database
- ✅ Database stamped with HEAD revision (currently: `c7923c6e866e`)
- ✅ No migrations run (already at HEAD)
- ✅ Verification passes

**Verify:**
```bash
sqlite3 backend/data/kahani.db "SELECT version_num FROM alembic_version;"
# Should output: c7923c6e866e
```

---

### Scenario 2: Existing Database with Correct Version

**Setup:**
```bash
# Database already exists with correct alembic_version
sqlite3 backend/data/kahani.db "SELECT version_num FROM alembic_version;"
# Shows: c7923c6e866e
```

**Test:**
```bash
./install.sh
```

**Expected Result:**
- ✅ `repair_alembic_version.py` detects correct version
- ✅ Reports "No repair needed"
- ✅ `alembic upgrade head` runs but finds no migrations to apply
- ✅ Installation completes successfully

---

### Scenario 3: Existing Database with Missing alembic_version (Original Bug)

**Setup:**
```bash
# Simulate the user's issue: database exists but alembic_version is missing
sqlite3 backend/data/kahani.db "DROP TABLE IF EXISTS alembic_version;"
```

**Test:**
```bash
./install.sh
```

**Expected Result:**
- ✅ `repair_alembic_version.py` detects schema version by inspecting tables/columns
- ✅ Stamps database with detected version
- ✅ `alembic upgrade head` applies any remaining migrations
- ✅ Database brought up to HEAD revision
- ✅ Installation completes successfully

**Verify:**
```bash
sqlite3 backend/data/kahani.db "SELECT version_num FROM alembic_version;"
# Should output: c7923c6e866e (or latest HEAD)
```

---

### Scenario 4: Existing Database with Wrong Version

**Setup:**
```bash
# Set wrong version (e.g., 001 when schema is actually at 008)
sqlite3 backend/data/kahani.db "DELETE FROM alembic_version;"
sqlite3 backend/data/kahani.db "INSERT INTO alembic_version VALUES ('001');"
```

**Test:**
```bash
./install.sh
```

**Expected Result:**
- ✅ `repair_alembic_version.py` detects actual schema version
- ✅ Updates alembic_version to match actual schema
- ✅ `alembic upgrade head` applies remaining migrations
- ✅ Database brought up to HEAD revision

---

### Scenario 5: Manual Repair Utility Usage

**Setup:**
```bash
# Broken database state
sqlite3 backend/data/kahani.db "DROP TABLE IF EXISTS alembic_version;"
```

**Test:**
```bash
cd backend
python repair_alembic_version.py
```

**Expected Result:**
```
🔧 Alembic Version Repair Utility
==================================================

📁 Database: /path/to/backend/data/kahani.db
📊 Current Alembic version: NOT SET
🎯 Latest migration (HEAD): c7923c6e866e

🔍 Analyzing database schema...
✓ Detected schema matches migration: c7923c6e866e

✅ Schema is up to date with HEAD revision
   Stamping database with: c7923c6e866e
✓ Alembic version repaired successfully!
```

---

## Testing on Your Test Server

### Quick Fix for Current Issue

If you want to fix your test server immediately without waiting for the full installation:

```bash
cd backend
python3 repair_alembic_version.py
cd ..
```

Then run migrations:
```bash
cd backend
source ../.venv/bin/activate
alembic upgrade head
deactivate
cd ..
```

### Full Test with Updated Code

1. **Pull the latest changes** (with the fixes)
2. **Run install.sh:**
   ```bash
   ./install.sh
   ```
3. **Verify the fix worked:**
   ```bash
   sqlite3 backend/data/kahani.db "SELECT version_num FROM alembic_version;"
   ```

---

## Schema Detection Logic

The repair utility detects schema version by checking for:

| Migration | Detection Criteria |
|-----------|-------------------|
| `001` | `user_settings` table exists |
| `002` | `character_memories` or `plot_events` tables exist |
| `003` | `system_settings` table exists |
| `004/005` | `scenario` column in `stories` table |
| `006` | `role` column in `story_characters` table |
| `007` | `color_theme_primary` column in `user_settings` |
| `008` | `scene_container_style` column in `user_settings` |
| `ec1f4e1c996a` | `llm_koboldcpp_api_url` column in `user_settings` |
| `bbf4e254a824` | `scene_container_style` removed from `user_settings` |
| `c7923c6e866e` (HEAD) | `character_assistant_enabled` column in `user_settings` |

---

## Troubleshooting

### If repair_alembic_version.py fails

1. **Check database file exists:**
   ```bash
   ls -la backend/data/kahani.db
   ```

2. **Check database is readable:**
   ```bash
   sqlite3 backend/data/kahani.db ".tables"
   ```

3. **Check Alembic configuration:**
   ```bash
   cd backend
   alembic current
   ```

### If migrations still fail after repair

1. **Check current version:**
   ```bash
   cd backend
   alembic current
   ```

2. **Check pending migrations:**
   ```bash
   alembic history
   ```

3. **Manually stamp to HEAD (last resort):**
   ```bash
   alembic stamp head
   ```

---

## Validation Commands

After any fix, validate the database state:

```bash
# Check Alembic version
sqlite3 backend/data/kahani.db "SELECT version_num FROM alembic_version;"

# Check all tables exist
sqlite3 backend/data/kahani.db ".tables"

# Check user_settings columns (should have all latest columns)
sqlite3 backend/data/kahani.db ".schema user_settings"

# Verify Alembic sees no pending migrations
cd backend && alembic current && cd ..
```

---

## Success Criteria

✅ Fresh installations create database with correct HEAD revision  
✅ Existing databases with correct version are left unchanged  
✅ Existing databases with missing/wrong version are automatically repaired  
✅ Migrations run successfully after repair  
✅ No manual intervention required during `install.sh`  
✅ Repair utility can be run standalone for manual fixes  

---

## Notes

- The repair utility is **idempotent** - safe to run multiple times
- Schema detection is **conservative** - if uncertain, it prompts rather than guessing
- The fix is **permanent** - future fresh installs will always work correctly
- Existing databases are **automatically repaired** during installation

