# Cascading Summary System

## Overview

The app now uses a **two-tier summary system** for chapters:

1. **`auto_summary`** - Summary of ONLY this chapter's scenes
2. **`story_so_far`** - Cascading summary combining ALL previous chapters + current chapter

## How It Works

### Tier 1: Chapter Auto-Summary (`auto_summary`)
- **What**: Summarizes ONLY the scenes within a specific chapter
- **When Generated**:
  - Automatically after every N scenes (user-configurable, default: 5)
  - When a chapter is marked as completed
  - Manually via API endpoint
- **Stored In**: `chapter.auto_summary`
- **Purpose**: Provides a concise summary of this chapter's content that can be reused

### Tier 2: Story So Far (`story_so_far`)
- **What**: Combines summaries from ALL previous chapters + recent scenes from current chapter
- **When Generated**:
  - When creating a new chapter (automatically summarizes all previous chapters)
  - After every N scenes (updates with new current chapter content)
  - Manually via API endpoint
- **Stored In**: `chapter.story_so_far`
- **Purpose**: Provides complete context of the entire story up to this point

## Example Flow

### Story with 3 Chapters

**Chapter 1** (10 scenes):
- `auto_summary`: "Maya discovers ancient ruins and meets the Guardian..."
- `story_so_far`: "Maya discovers ancient ruins and meets the Guardian..."

**Chapter 2** (8 scenes):
- `auto_summary`: "Maya and the Guardian journey to the Shadow Realm..."
- `story_so_far`: "Previously: Maya discovered ancient ruins and met the Guardian. Now: Maya and the Guardian journey to the Shadow Realm..."

**Chapter 3** (5 scenes so far):
- `auto_summary`: Not yet generated (will be at scene 5)
- `story_so_far`: "Previously: Maya discovered ancient ruins, met the Guardian, and journeyed to the Shadow Realm. Currently: Maya faces the Shadow Lord..."

## Auto-Update Triggers

### During Scene Generation
After every `N` scenes (user setting: `context_settings.summary_threshold`, default: 5):

1. Generate/update `chapter.auto_summary` (summarize all scenes in this chapter)
2. Generate/update `chapter.story_so_far` (combine previous chapter summaries + current)
3. Update `chapter.last_summary_scene_count` to track when last updated

### During Chapter Creation
When creating a new chapter:

1. Complete the previous chapter
2. Generate `auto_summary` for previous chapter if missing
3. Generate `story_so_far` for previous chapter
4. Create new chapter
5. Generate `story_so_far` for new chapter (combining all previous)

## API Endpoints

### Generate Chapter Summary
```
POST /api/stories/{story_id}/chapters/{chapter_id}/generate-summary?regenerate_story_so_far=true
```

Parameters:
- `regenerate_story_so_far`: `false` (default) = only generate `auto_summary`, `true` = also regenerate `story_so_far`

Returns:
```json
{
  "message": "Chapter summary generated successfully",
  "chapter_summary": "Summary of this chapter...",
  "story_so_far": "Combined story summary..." | null,
  "scenes_summarized": 10
}
```

## User Settings

- **Summary Threshold**: `context_settings.summary_threshold` (default: 5 scenes)
- **Range**: 3-20 scenes
- **Enable/Disable**: `context_settings.enable_summarization`

## Database Fields

### Chapter Model
- `auto_summary` (Text): Summary of THIS chapter's scenes only
- `story_so_far` (Text): Cascading summary of all previous + current
- `last_summary_scene_count` (Integer): Tracks when last auto-summary was generated
- `scenes_count` (Integer): Total scenes in this chapter

## Frontend Display

The Chapter Sidebar shows:
- **"Story So Far"** section displays `chapter.story_so_far`
- Falls back to `chapter.auto_summary` if `story_so_far` is empty
- Editable by user if they want to customize

## Benefits

1. **Efficient Context Management**: Previous chapters are summarized, not included verbatim
2. **Scalable**: Can handle stories with 100+ chapters without context overflow
3. **Layered Detail**: 
   - Recent chapter = full detail (via recent scenes)
   - Previous chapters = concise summaries
4. **User Control**: Configurable threshold for when summaries are generated
5. **Retroactive**: Can generate summaries for existing chapters

## Migration Notes

### For Existing Chapters
Chapters created before this system:
- May have `story_so_far = "The story begins..."` (default)
- May be missing `auto_summary` even with many scenes

**Solution**: Use the retroactive fix script to generate missing summaries

## Implementation Files

- `backend/app/api/chapters.py`:
  - `generate_chapter_summary()` - Generates `auto_summary`
  - `generate_story_so_far()` - Generates `story_so_far`
  - API endpoint for manual regeneration

- `backend/app/api/stories.py`:
  - Scene generation triggers both summaries after threshold

## Future Enhancements

1. **Configurable Summary Depth**: How many previous chapters to include in detail
2. **Summary Caching**: Cache combined summaries for performance
3. **Summary Versioning**: Track summary changes over time
4. **Smart Summarization**: Use different prompts for action vs. dialogue heavy chapters
