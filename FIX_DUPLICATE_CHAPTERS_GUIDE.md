# Fix Duplicate Chapters Guide

## Problem
You have duplicate Chapter 1s in your database due to the bug that was just fixed.

## Solution Options

### Option 1: Use the Python Script (Recommended)

I've created a script that will help you fix the database interactively.

**Steps:**

1. **Stop your backend server** (if running)

2. **Run the fix script:**
   ```bash
   cd /Users/nishant/apps/kahani
   python fix_duplicate_chapters.py
   ```

3. **Follow the prompts:**
   - The script will show you all duplicate chapters
   - For each duplicate, it will show:
     - Chapter ID
     - Title
     - Status (ACTIVE/COMPLETED/DRAFT)
     - Number of scenes
     - Creation date
   - Choose which chapter to KEEP (usually the one with more scenes or the correct one)
   - The script will delete the others

4. **Restart your backend server**

**Example Output:**
```
================================================================================
Story: My Story (ID: 1)
Branch: Main (ID: 1)
Chapter Number: 1
Duplicate Count: 2
================================================================================

Found these duplicate chapters:

1. Chapter ID: 5
   Title: Chapter 1
   Status: active
   Scenes: 0
   Created: 2025-12-09 01:23:45

2. Chapter ID: 2
   Title: Chapter 1
   Status: completed
   Scenes: 15
   Created: 2025-12-08 10:30:00

Which chapter do you want to KEEP? (1-2)
> 2

Deleting chapter 5...
  - Deleted chapter-character associations
  - Deleted 0 summary batch(es)
  - Deleted 0 scene(s)
  ✓ Chapter 5 deleted successfully

✓ Kept chapter 2
```

### Option 2: Use the API Endpoint (If Backend is Running)

If you prefer to use the API:

1. **Find the duplicate chapter ID** you want to delete
   - Go to your story in the UI
   - Note the chapter ID from the URL or developer tools

2. **Call the delete endpoint:**
   ```bash
   # Replace with your actual values
   STORY_ID=1
   CHAPTER_ID=5  # The duplicate you want to delete
   
   curl -X DELETE "http://localhost:9876/api/stories/${STORY_ID}/chapters/${CHAPTER_ID}" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

3. **Refresh your UI**

### Option 3: Direct Database Access (Advanced)

If you're comfortable with SQL:

```sql
-- First, find the duplicates
SELECT story_id, branch_id, chapter_number, COUNT(*) as count
FROM chapters
GROUP BY story_id, branch_id, chapter_number
HAVING COUNT(*) > 1;

-- Then delete the unwanted chapter (replace 5 with the chapter ID to delete)
DELETE FROM chapters WHERE id = 5;
```

**Note:** The database has CASCADE deletes, so this will automatically clean up:
- Chapter-character associations
- Summary batches
- Scenes and their variants
- Story flow entries

## Prevention

The bug that caused this has been fixed in the latest code. The fixes include:

1. **Proper transaction management** - Previous chapter completion and new chapter creation are now in separate transactions
2. **Duplicate detection** - System checks for duplicate chapter numbers before creating
3. **Better error handling** - Clear error messages if something goes wrong
4. **Trace logging** - All operations are logged with trace IDs for debugging

## New Feature: Delete Chapter from UI

I've also added a DELETE chapter API endpoint, so you can add a delete button in your UI:

**Backend Endpoint:**
```
DELETE /api/stories/{story_id}/chapters/{chapter_id}
```

**Frontend API Method:**
```typescript
await api.deleteChapter(storyId, chapterId);
```

**Safety Features:**
- Cannot delete the only chapter in a story
- Cannot delete chapters from inactive branches
- Automatically activates another chapter if you delete the active one
- Cleans up all related data (scenes, summaries, associations)

## Need Help?

If you encounter any issues:

1. Check the logs at `/Users/nishant/apps/kahani/backend/logs/kahani.log`
2. Look for entries with `[CHAPTER:CREATE]` or `[CHAPTER]` tags
3. The trace_id will help you follow the flow of a specific operation

## Verification

After fixing, verify:

1. Each chapter number appears only once per story/branch
2. You have the correct chapters with their scenes
3. The active chapter is set correctly
4. No orphaned data remains

You can check with:
```bash
python fix_duplicate_chapters.py
```

If it says "No duplicate chapters found!" you're all set! ✓
