# Chapter Modal UI Enhancements

## Changes Made

### 1. Added "Generate Summary" Button
- **Location**: Top of the Chapter Creation modal
- **Functionality**: 
  - Generates both `auto_summary` and `story_so_far` for the current chapter
  - Makes API call to: `POST /api/stories/{story_id}/chapters/{chapter_id}/generate-summary?regenerate_story_so_far=true`
  - Shows loading state while generating
  - Disabled if chapter has 0 scenes
  - Displays error messages if generation fails

### 2. Added Current Chapter Summary Display
- **Location**: Top section of the Chapter Creation modal
- **Shows**:
  - Current chapter's `auto_summary` if available
  - Helpful placeholder messages:
    - "Generate scenes first, then create a summary" (if 0 scenes)
    - "No summary generated yet. Click 'Generate Summary' above." (if scenes exist but no summary)
  - Scrollable box (max height 40) for long summaries

### 3. Added Story So Far Preview
- **Location**: Above the "Story Continuity" info box
- **Shows**: 
  - The `story_so_far` field from the current chapter
  - This is what will be used as context for the new chapter
  - Only displays if `story_so_far` exists
  - Scrollable box (max height 32) for long content

### 4. Updated Info Message
- Changed the info message to be more accurate:
  - Old: "The AI-generated summary from your current chapter will be used..."
  - New: "The AI will combine summaries from all previous chapters to create context..."

## UI Flow

### When Creating a New Chapter:

1. **User clicks "Create New Chapter"** button
2. **Modal opens** showing:
   - **Top Section**: Current chapter summary with "Generate Summary" button
   - **Middle Section**: Title and Description inputs
   - **Story So Far Preview**: Shows what context the new chapter will have
   - **Info Box**: Explains how continuity works
   - **Footer**: Cancel and Create buttons

3. **If Current Chapter Has No Summary:**
   - User can click "Generate Summary" button
   - System generates both `auto_summary` and `story_so_far`
   - Summary appears immediately after generation
   - This summary will then be used for the new chapter

4. **User Fills Form and Creates Chapter:**
   - New chapter is created with proper `story_so_far` context

## State Management

### New State Variables:
```typescript
const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
const [summaryError, setSummaryError] = useState<string | null>(null);
```

### New Function:
```typescript
const handleGenerateSummary = async () => {
  // Calls API endpoint with regenerate_story_so_far=true
  // Reloads chapters to get updated data
  // Shows success/error messages
}
```

## Visual Design

### Current Chapter Summary Section:
- **Header**: Label + Generate button aligned horizontally
- **Button**: Blue background, small size, shows spinner when loading
- **Summary Box**: Slate background, bordered, scrollable
- **Text**: Gray color, pre-wrapped for formatting

### Story So Far Preview:
- Similar styling to summary box
- Only shown if data exists
- Helps user understand what context the new chapter will have

### Generate Button States:
- **Normal**: Blue background, "Generate Summary" text with book icon
- **Loading**: Spinning gear icon, "Generating..." text
- **Disabled**: Gray background, not clickable (when 0 scenes)

## Testing

To test the new features:

1. **Open Maya's Last Stand, Chapter 2** (has 0 scenes)
   - Modal should show "Generate scenes first" message
   - Generate button should be disabled

2. **Open Shadow's Covenant, Chapter 1** (has 2 scenes)
   - Modal shows existing summary
   - Can click "Generate Summary" to regenerate
   - Watch loading state and success message

3. **Create a New Chapter:**
   - Should see Story So Far preview
   - Should show context from previous chapters
   - New chapter creation should work as before

## API Integration

### Endpoint Used:
```
POST /api/stories/{story_id}/chapters/{chapter_id}/generate-summary?regenerate_story_so_far=true
```

### Response Structure:
```json
{
  "message": "Chapter summary generated successfully",
  "chapter_summary": "Summary text...",
  "story_so_far": "Combined summary...",
  "scenes_summarized": 10
}
```

### Error Handling:
- Network errors are caught and displayed
- User-friendly error messages
- Doesn't break the modal if generation fails

## Files Modified

1. **`frontend/src/components/ChapterSidebar.tsx`**
   - Added state for summary generation
   - Added `handleGenerateSummary()` function
   - Enhanced modal UI with new sections
   - Added loading states and error handling

## Benefits

1. **Visibility**: Users can see current chapter summary before creating new chapter
2. **Control**: Users can manually trigger summary generation
3. **Transparency**: Users see what context will be used for new chapters
4. **Feedback**: Clear loading states and error messages
5. **Flexibility**: Can generate summary anytime, not just at threshold
