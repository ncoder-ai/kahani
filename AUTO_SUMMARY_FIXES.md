# Auto-Summary Feature Fixes

## Issues Identified

### Issue 1: Auto-Summary Not Triggering During Scene Generation
**Problem**: When generating scenes within a chapter, the auto-summary feature was not being triggered even after reaching the threshold number of scenes.

**Root Cause**: In `backend/app/api/stories.py` line 541, the code was trying to access `user_settings.context_summary_threshold` as if `user_settings` was an object, but it's actually a dictionary returned from `UserSettings.to_dict()`.

**Fix**: Changed from:
```python
summary_threshold = user_settings.context_summary_threshold if user_settings else 5
```

To:
```python
summary_threshold = user_settings.get('context_settings', {}).get('summary_threshold', 5) if user_settings else 5
```

**Impact**: Auto-summary will now trigger correctly after the configured number of scenes (default: 5 scenes).

---

### Issue 2: New Chapter Creation Shows Empty "Story So Far"
**Problem**: When creating a new chapter, the "Story So Far" field in the Chapter modal was empty or showed default text instead of an AI-generated summary.

**Root Cause**: The previous chapter didn't have an `auto_summary` generated when the new chapter was being created.

**Fix**: Modified `backend/app/api/chapters.py` in the `create_chapter` function to:
1. Automatically generate a summary for the previous chapter when marking it as completed (if it doesn't already have one)
2. Use the generated `auto_summary` as the default `story_so_far` for the new chapter
3. Added proper database refresh after summary generation to ensure latest data is available

**Code Changes**:
```python
# Mark current chapter as completed if exists
if active_chapter:
    active_chapter.status = ChapterStatus.COMPLETED
    active_chapter.completed_at = datetime.utcnow()
    
    # Generate summary for the completed chapter if it doesn't have one yet
    if not active_chapter.auto_summary and active_chapter.scenes_count > 0:
        logger.info(f"[CHAPTER] Generating summary for completed chapter {active_chapter.id}")
        try:
            await generate_chapter_summary(active_chapter.id, db, current_user.id)
            db.refresh(active_chapter)  # Refresh to get the auto_summary
            logger.info(f"[CHAPTER] Summary generated for completed chapter {active_chapter.id}")
        except Exception as e:
            logger.error(f"[CHAPTER] Failed to generate summary: {e}")

# Use auto_summary from previous chapter if available
default_story_so_far = "Continuing the story..."
if active_chapter and active_chapter.auto_summary:
    default_story_so_far = active_chapter.auto_summary
```

**Impact**: New chapters will now automatically show an AI-generated summary of the previous chapter's events in the "Story So Far" field.

---

## How Auto-Summary Works Now

### During Scene Generation
1. Every time a scene is generated, it's linked to the active chapter
2. The chapter's `scenes_count` is incremented
3. The system checks: `scenes_since_last_summary >= summary_threshold`
4. If threshold is reached (default: 5 scenes), an auto-summary is generated in the background
5. The summary is stored in `chapter.auto_summary`
6. `last_summary_scene_count` is updated to track when the last summary was made

### During Chapter Creation
1. When creating a new chapter, the current active chapter is marked as COMPLETED
2. If the completed chapter doesn't have an `auto_summary` yet (and has scenes), one is generated immediately
3. The new chapter's `story_so_far` field is populated with:
   - Frontend-provided value (if any), OR
   - Previous chapter's `auto_summary` (if available), OR
   - Default text: "Continuing the story..."

### User Settings
- Users can configure the auto-summary threshold in Settings
- Default: 5 scenes
- Range: 3-20 scenes
- Setting path: `context_settings.summary_threshold`

---

## Testing the Fixes

### Test 1: Auto-Summary During Scene Generation
1. Open an existing story with an active chapter
2. Generate 5 scenes (or your configured threshold)
3. Check the logs for: `[CHAPTER] Auto-summary check: X scenes since last summary`
4. After reaching threshold, you should see: `[CHAPTER] Auto-summary generated for chapter X`
5. Open the Chapter sidebar - the "Story So Far" should show the AI-generated summary

### Test 2: New Chapter Creation
1. Open a story with at least one chapter containing scenes
2. Click "Create New Chapter" in the Chapter sidebar
3. The Chapter Creation modal should show:
   - The "Story So Far" field pre-populated with a summary
   - Not empty or showing "Continuing the story..." (unless Chapter 1 had no scenes)
4. Create the chapter and verify the summary is saved

### Test 3: Summary Generation Logs
Check logs with:
```bash
tail -f logs/kahani.log | grep "CHAPTER"
```

You should see:
- `[CHAPTER] Auto-summary check: X scenes since last summary (threshold: Y)`
- `[CHAPTER] Chapter X reached Y scenes since last summary, triggering auto-summary`
- `[CHAPTER] Auto-summary generated for chapter X`
- `[CHAPTER] Generating summary for completed chapter X`

---

## Configuration

### User Settings (Settings Page)
- **Context Summary Threshold**: Number of scenes before auto-summary is triggered
- **Enable Context Summarization**: Toggle auto-summary feature on/off

### Technical Details
- Default threshold: 5 scenes
- Summary max tokens: 400
- Summary is stored in `Chapter.auto_summary` field
- Tracking field: `Chapter.last_summary_scene_count`

---

## Files Modified

1. **backend/app/api/stories.py**
   - Fixed `summary_threshold` access to use dictionary syntax
   - Added logging for auto-summary checks

2. **backend/app/api/chapters.py**
   - Added automatic summary generation when completing a chapter
   - Improved `story_so_far` default value logic for new chapters
   - Added database refresh after summary generation

---

## Notes

- Auto-summary generation happens asynchronously and won't block scene generation
- If summary generation fails, it logs an error but doesn't break the scene/chapter creation
- The frontend already correctly handles displaying `auto_summary` when `story_so_far` is empty
- Summary generation uses the LLM configured in user settings
