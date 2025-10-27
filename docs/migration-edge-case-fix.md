# Migration Edge Case Fix - Missing Column Handling

## Problem Encountered

After implementing the initial Alembic repair fix, a new edge case was discovered:

```
sqlite3.OperationalError: no such column: "scene_container_style"
[SQL: ALTER TABLE user_settings DROP COLUMN scene_container_style]
```

### Root Cause

The database had an inconsistent migration state:
1. **Migration 008** adds `scene_container_style` column
2. **Migration ec1f4e1c996a** adds engine-specific settings (e.g., `llm_koboldcpp_api_url`)
3. **Migration bbf4e254a824** removes `scene_container_style` column

**The Issue:**
- Database had migration `ec1f4e1c996a` applied (has engine settings)
- Migration `008` was **never applied** (no `scene_container_style` column)
- Repair utility detected schema as `ec1f4e1c996a`
- When running `alembic upgrade head`, it tried to apply `bbf4e254a824`
- Migration failed trying to DROP a column that never existed

### Why This Happened

This is a classic migration chain problem where:
- Migration `008` and `ec1f4e1c996a` are independent (both modify `user_settings`)
- If `ec1f4e1c996a` was applied but `008` was skipped, the column never existed
- The removal migration `bbf4e254a824` assumes the column exists

## Solution: Two-Pronged Fix

### 1. Make Migration Idempotent

**File:** `backend/alembic/versions/bbf4e254a824_remove_scene_container_style.py`

**Change:** Added column existence check before dropping:

```python
def upgrade():
    # Remove scene_container_style column from user_settings table
    # Check if column exists before trying to drop it (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    if 'scene_container_style' in columns:
        op.drop_column('user_settings', 'scene_container_style')
    # If column doesn't exist, the migration effect is already applied
```

**Benefits:**
- ✅ Migration succeeds whether column exists or not
- ✅ Idempotent - safe to run multiple times
- ✅ Handles databases in any state
- ✅ No manual intervention needed

### 2. Improved Schema Detection

**File:** `backend/repair_alembic_version.py`

**Enhancement:** Better logic to detect edge cases:

```python
# Check for engine-specific settings (added in ec1f4e1c996a)
has_engine_settings = 'llm_koboldcpp_api_url' in user_settings_columns
has_scene_container = 'scene_container_style' in user_settings_columns

# If has engine settings but NOT scene_container_style:
# - Either at bbf4e254a824 (which removes it) or later
# - OR migration 008 was never applied (column never existed)
if has_engine_settings and not has_scene_container:
    # This is the state after bbf4e254a824 or if 008 was skipped
    return 'bbf4e254a824'

# If has engine settings AND scene_container_style:
# - At ec1f4e1c996a, before bbf4e254a824 removes it
if has_engine_settings and has_scene_container:
    return 'ec1f4e1c996a'
```

**Detection Logic:**

| Engine Settings | scene_container_style | Detected Version | Reasoning |
|----------------|----------------------|------------------|-----------|
| ✅ Yes | ✅ Yes | `ec1f4e1c996a` | Has engine settings, column not yet removed |
| ✅ Yes | ❌ No | `bbf4e254a824` | Either removed OR never added (008 skipped) |
| ❌ No | ✅ Yes | `008` | Has column but not engine settings yet |
| ❌ No | ❌ No | Earlier | Neither feature present |

## Why Both Fixes Are Essential

### Fix 1: Idempotent Migration
- **Prevents failure** when column doesn't exist
- **Future-proof** - handles any migration order
- **Safe** - can be run multiple times

### Fix 2: Better Detection
- **Correctly identifies** edge case states
- **Stamps appropriate version** to minimize migrations needed
- **Handles skipped migrations** gracefully

## Testing the Fix

### Test Case 1: Database with Engine Settings, No scene_container_style

**Initial State:**
```sql
-- Has llm_koboldcpp_api_url (from ec1f4e1c996a)
-- Does NOT have scene_container_style (008 never applied)
```

**Expected Behavior:**
1. Repair utility detects as `bbf4e254a824`
2. Stamps with `bbf4e254a824`
3. Only `c7923c6e866e` migration needs to run
4. Success! ✅

### Test Case 2: Database with Both Columns

**Initial State:**
```sql
-- Has llm_koboldcpp_api_url (from ec1f4e1c996a)
-- Has scene_container_style (from 008)
```

**Expected Behavior:**
1. Repair utility detects as `ec1f4e1c996a`
2. Stamps with `ec1f4e1c996a`
3. Runs `bbf4e254a824` (removes column - succeeds because it exists)
4. Runs `c7923c6e866e`
5. Success! ✅

### Test Case 3: Fresh Installation

**Initial State:**
```sql
-- No database exists
```

**Expected Behavior:**
1. `init_database.py` creates all tables
2. Stamps with HEAD (`c7923c6e866e`)
3. No migrations needed
4. Success! ✅

## For Your Test Server

Now you can run:

```bash
git pull origin dev
./install.sh
```

**What Will Happen:**
1. ✅ Repair utility detects your database state
2. ✅ Stamps with `bbf4e254a824` (recognizing 008 was skipped)
3. ✅ Migration `bbf4e254a824` runs but finds no column to drop (idempotent)
4. ✅ Migration `c7923c6e866e` applies character assistant settings
5. ✅ Installation completes successfully!

## Migration Chain Reference

```
001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → ec1f4e1c996a → bbf4e254a824 → c7923c6e866e (HEAD)
                                              ↑                        ↑
                                    Adds scene_container_style    Removes it
                                    
Your database was here: ec1f4e1c996a (but without 008's column)
Now stamps as: bbf4e254a824 (to skip the problematic removal)
```

## Key Takeaways

1. **Idempotent Migrations:** Always check for existence before dropping/adding
2. **Schema Detection:** Must account for skipped or out-of-order migrations
3. **Edge Cases:** Real-world databases may not follow clean migration paths
4. **Defensive Coding:** Assume migrations can run in any order or be skipped

## Files Changed

1. ✅ `backend/alembic/versions/bbf4e254a824_remove_scene_container_style.py`
   - Added column existence check
   
2. ✅ `backend/repair_alembic_version.py`
   - Improved detection logic for edge cases

## Commit

**Commit:** `0291542` - "Fix migration edge case: handle missing scene_container_style column"

This fix ensures that databases in **any state** can successfully upgrade to HEAD, regardless of which migrations were applied or skipped.

