# Improved Scrolling Behavior Test Plan

## What Changed

### Before (Issues)
- Multiple aggressive scroll effects running simultaneously
- 3 different `useEffect` hooks all triggering scrolls with different timings (50ms, 100ms, 200ms, 300ms)
- Jarring automatic scrolls even when users manually scrolled away
- No respect for user's current scroll position
- Constant scrolling during streaming updates

### After (Improvements)
- **Single consolidated scroll effect** with intelligent timing
- **Smart scroll detection** - only scrolls if user is near bottom already
- **Manual scroll tracking** - detects when user scrolls away and respects that choice
- **Visual indicator** - shows "New content added" notification instead of forcing scroll
- **Gentler scroll behavior** - uses `block: 'nearest'` instead of aggressive `block: 'end'`
- **Longer delays** - 400-600ms instead of 50-300ms for less jarring experience

## Test Cases

### 1. Normal Content Generation (User at Bottom)
- **Expected**: Gentle scroll to new content with visual indicator
- **Test**: Generate a new scene while scrolled to bottom
- **Behavior**: Should smoothly scroll to show new content

### 2. User Manually Scrolled Away
- **Expected**: No automatic scroll, only visual indicator shown
- **Test**: Scroll up to middle of story, then generate new scene
- **Behavior**: Should show "New content added" indicator but not force scroll

### 3. Streaming Content
- **Expected**: Minimal scrolling during stream, final gentle scroll when complete
- **Test**: Use streaming mode to generate content
- **Behavior**: Should not constantly scroll during typing, only at completion

### 4. User Returns to Bottom
- **Expected**: Auto-scroll behavior resumes
- **Test**: Scroll away, generate content (no scroll), then scroll back to bottom
- **Behavior**: Next generation should resume auto-scrolling

## Key Features

1. **User Intent Respect**: System detects and respects when user has intentionally scrolled away
2. **Visual Feedback**: Clear indicator shows when new content is available without forced movement
3. **Performance**: Single scroll effect instead of multiple competing effects
4. **Smooth UX**: Longer delays and gentler scroll animations

## Code Changes Summary

- Replaced 3 scroll `useEffect` hooks with 1 intelligent one
- Added scroll position tracking to detect user intent
- Implemented visual "New content added" indicator with fade-in animation
- Changed scroll timing from 50-300ms to 400-600ms
- Used `block: 'nearest'` instead of `block: 'end'` for gentler scrolling