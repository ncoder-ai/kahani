# Summary System Analysis & Fix Plan

## Current Issues

### Issue 1: Chapter Summary Missing Context
**Problem:** `generate_chapter_summary()` only sends current chapter's scenes to LLM
**Impact:** LLM has no context about characters, events from previous chapters
**Required:** Should send summaries of ALL previous chapters for context

### Issue 2: No Automatic Summary Generation
**Problem:** Summaries only generate when:
- User manually clicks button
- New chapter is created
**Required:** Should auto-generate every N scenes (user setting: `context_summary_threshold`)

### Issue 3: Confusion Between Summary Types
**Current:**
- `chapter.auto_summary` = summary of current chapter scenes
- `chapter.story_so_far` = previous chapters' summaries + current scenes
- `story.summary` = story-level summary (rarely used)

**Should Be:**
- `chapter.auto_summary` = summary of THIS chapter's scenes (generated with context from previous chapters)
- `chapter.story_so_far` = summary of ALL previous chapters + current chapter summary
- `story.summary` = comprehensive story summary (all chapters)

## Correct Implementation

### What Should Happen

#### When Generating Chapter Summary:
```
Input to LLM:
1. Summaries of ALL previous chapters (for context)
2. All scenes from CURRENT chapter (to summarize)

Output:
- Updates chapter.auto_summary
```

#### When Generating Story So Far:
```
Input to LLM:
1. Summaries of ALL previous chapters
2. Summary of CURRENT chapter (auto_summary)

Output:
- Updates chapter.story_so_far
- This becomes context for new scene generation
```

#### Auto-Generation Triggers:
1. **Every N scenes** (user setting: context_summary_threshold)
   - Check: current_scenes_count - last_summary_scene_count >= threshold
   - Generate: chapter.auto_summary
   - Update: last_summary_scene_count

2. **When chapter starts** (creating new chapter)
   - Generate: story_so_far for new chapter

3. **Manual click** "Generate Chapter Summary"
   - Generate: chapter.auto_summary
   - Optional: regenerate story_so_far

4. **Manual click** "Generate Story Summary"  
   - Generate: story.summary (comprehensive)
   - Uses all chapter summaries

## Implementation Plan

### 1. Fix `generate_chapter_summary()` to include context
```python
async def generate_chapter_summary(chapter_id: int, db: Session, user_id: int) -> str:
    # Get chapter
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    
    # Get ALL PREVIOUS chapters' summaries for context
    previous_chapters = db.query(Chapter).filter(
        Chapter.story_id == chapter.story_id,
        Chapter.chapter_number < chapter.chapter_number
    ).order_by(Chapter.chapter_number).all()
    
    previous_summaries = [f"Chapter {ch.chapter_number}: {ch.auto_summary}" 
                         for ch in previous_chapters if ch.auto_summary]
    
    # Get current chapter's scenes
    current_scenes = [...]  # existing logic
    
    # Combine for prompt
    prompt = f"""
    Previous Chapters (for context):
    {previous_summaries}
    
    Current Chapter {chapter.chapter_number} Scenes (to summarize):
    {current_scenes}
    
    Summarize ONLY Chapter {chapter.chapter_number}, but use the context 
    from previous chapters to maintain character consistency and continuity.
    """
```

### 2. Add auto-generation check after scene creation
```python
# In scene creation endpoint, after creating scene:
if user_settings.auto_generate_summaries:
    scenes_since_summary = chapter.scenes_count - chapter.last_summary_scene_count
    if scenes_since_summary >= user_settings.context_summary_threshold:
        await generate_chapter_summary(chapter.id, db, user_id)
        # Also update story_so_far
        await generate_story_so_far(chapter.id, db, user_id)
```

### 3. Update `generate_story_so_far()` logic
```python
async def generate_story_so_far(chapter_id: int, db: Session, user_id: int) -> str:
    # Get ALL previous chapters' summaries
    previous_summaries = [...]
    
    # Get CURRENT chapter's summary (not individual scenes)
    current_summary = chapter.auto_summary
    
    # Combine
    prompt = f"""
    Previous Chapters:
    {previous_summaries}
    
    Current Chapter {chapter.chapter_number}:
    {current_summary}
    
    Create a cohesive "Story So Far" that flows naturally...
    """
```

### 4. Add story-level summary generation
```python
async def generate_story_summary(story_id: int, db: Session, user_id: int) -> str:
    # Get ALL chapters' summaries
    all_chapters = db.query(Chapter).filter(
        Chapter.story_id == story_id
    ).order_by(Chapter.chapter_number).all()
    
    all_summaries = [f"Chapter {ch.chapter_number}: {ch.auto_summary}"
                    for ch in all_chapters if ch.auto_summary]
    
    # Generate comprehensive story summary
    prompt = f"""
    All Chapters:
    {all_summaries}
    
    Create a comprehensive story summary that captures the entire narrative...
    """
    
    # Save to story.summary
    story.summary = await llm_service.generate(...)
```

## Migration Needed

Add column to user_settings:
```sql
ALTER TABLE user_settings ADD COLUMN auto_generate_summaries BOOLEAN DEFAULT TRUE;
```

## Testing Plan

1. Create story with 10 scenes, threshold=5
   - After scene 5: auto_summary should generate
   - After scene 10: auto_summary should regenerate
   
2. Create multi-chapter story
   - Chapter 1 summary should have no context
   - Chapter 2 summary should reference Chapter 1 characters/events
   
3. Manual generation
   - Click "Generate Chapter Summary" → updates auto_summary
   - Click "Generate Story Summary" → updates story.summary
