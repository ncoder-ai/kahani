# Implementation Plan: Configurable Plot Event Check Mode

## Overview

Add a configurable setting that controls how many plot events are sent to the LLM for checking after each scene generation. Currently, ALL remaining events are sent. This change allows users to choose between strict linear checking (next 1 event), slight flexibility (next 3 events), or full flexibility (all remaining events).

Additionally, unify the event tracking by combining `key_events`, `climax`, and `resolution` into a single ordered list for detection purposes, while keeping the brainstorm output structure unchanged.

## Design Decisions

1. **Per-story setting** with **user default that pre-fills new stories**
   - Story setting is the source of truth
   - User default just initializes new stories

2. **Unified event list for tracking**
   - Brainstorm output stays as-is: `{"key_events": [...], "climax": "...", "resolution": "..."}`
   - At tracking time, flatten into: `[...key_events, climax, resolution]`
   - All events go through LLM detection (no more text-match hacks)
   - `climax_reached` / `resolution_reached` derived from completion status

3. **Keep pacing guidance**
   - Still highlight "approaching climax" etc. based on progress
   - Special messaging for final events preserved

## Setting Values

| Value | Label | Description | Default |
|-------|-------|-------------|---------|
| `1` | Next event only | Strict linear - only check if the immediate next event occurred | **Default** |
| `3` | Next few events | Slight flexibility - check next 3 events | |
| `all` | All remaining | Full flexibility - check all remaining events (current behavior) | |

---

## Implementation Tasks

### 1. Backend: Story Model
**File:** `backend/app/models/story.py`

Add new column to Story model:
```python
# Plot event checking mode - how many events to send for LLM detection
# "1" = next event only (strict), "3" = next 3 events, "all" = all remaining
plot_check_mode = Column(String(10), default="1")
```

### 2. Backend: User Settings Model
**File:** `backend/app/models/user_settings.py`

Add new column to UserSettings model:
```python
# Default plot check mode for new stories
default_plot_check_mode = Column(String(10), nullable=True)  # "1", "3", or "all"
```

Update `to_dict()` method to include in `generation_preferences`:
```python
"default_plot_check_mode": self.default_plot_check_mode if self.default_plot_check_mode is not None else gen_defaults.get("default_plot_check_mode", "1")
```

Update `populate_from_defaults()` method.

### 3. Backend: Config Defaults
**File:** `backend/config.yaml`

Add default under `user_defaults.generation_preferences`:
```yaml
default_plot_check_mode: "1"  # "1" (strict), "3" (flexible), or "all"
```

### 4. Backend: Database Migration
**File:** `backend/alembic/versions/XXX_add_plot_check_mode.py`

Create migration to add:
- `plot_check_mode` column to `stories` table
- `default_plot_check_mode` column to `user_settings` table

### 5. Backend: Settings API Schema
**File:** `backend/app/api/settings.py`

Update `GenerationPreferencesUpdate` schema:
```python
default_plot_check_mode: Optional[str] = Field(None, pattern="^(1|3|all)$")
```

Update the settings update endpoint to handle this field.

### 6. Backend: Story API Schema
**File:** `backend/app/api/stories.py`

Update story schemas to include `plot_check_mode`:
- `StoryCreate` - optional, defaults from user settings
- `StoryUpdate` - optional
- `StoryResponse` - include the field

When creating a story, initialize `plot_check_mode` from user's `default_plot_check_mode`.

### 7. Backend: ChapterProgressService (Core Logic Changes)
**File:** `backend/app/services/chapter_progress_service.py`

#### 7a. Add helper to flatten events
```python
def get_all_chapter_events(self, chapter_plot: dict) -> list:
    """
    Combine key_events + climax + resolution into one ordered list.
    Brainstorm output stays unchanged, we just flatten at tracking time.
    """
    events = list(chapter_plot.get("key_events", []))
    if chapter_plot.get("climax"):
        events.append(chapter_plot["climax"])
    if chapter_plot.get("resolution"):
        events.append(chapter_plot["resolution"])
    return events
```

#### 7b. Modify `extract_and_update_progress()`

```python
async def extract_and_update_progress(
    self,
    chapter: Chapter,
    scene_content: str,
    llm_service,
    user_id: int,
    user_settings: Dict[str, Any],
    plot_check_mode: str = "1"  # New parameter - default to strict
) -> Dict[str, Any]:
    if not chapter.chapter_plot:
        return {}

    self.db.refresh(chapter)

    # Get ALL events as unified list (key_events + climax + resolution)
    all_events = self.get_all_chapter_events(chapter.chapter_plot)

    # Get already completed events
    progress = chapter.plot_progress or {}
    already_completed = set(progress.get("completed_events", []))

    # Only check for events that haven't been completed yet
    remaining_events = [e for e in all_events if e not in already_completed]

    if not remaining_events:
        return self.update_progress(chapter, [])

    # Apply plot_check_mode filter
    if plot_check_mode == "1":
        events_to_check = remaining_events[:1]
    elif plot_check_mode == "3":
        events_to_check = remaining_events[:3]
    else:  # "all"
        events_to_check = remaining_events

    # Extract newly completed events via LLM
    new_completed = await self.extract_completed_events(
        scene_content=scene_content,
        key_events=events_to_check,
        llm_service=llm_service,
        user_id=user_id,
        user_settings=user_settings
    )

    # Derive climax_reached and resolution_reached from completed events
    climax = chapter.chapter_plot.get("climax", "")
    resolution = chapter.chapter_plot.get("resolution", "")

    all_completed = already_completed.union(new_completed)
    climax_reached = climax in all_completed if climax else False
    resolution_reached = resolution in all_completed if resolution else False

    # Update progress
    return self.update_progress(
        chapter=chapter,
        new_completed_events=new_completed,
        climax_reached=climax_reached,
        resolution_reached=resolution_reached
    )
```

#### 7c. Update `update_progress()` to accept resolution_reached
```python
def update_progress(
    self,
    chapter: Chapter,
    new_completed_events: List[str],
    scene_count: Optional[int] = None,
    climax_reached: bool = False,
    resolution_reached: bool = False  # Add this parameter
) -> Dict[str, Any]:
    # ... existing code ...

    # Update resolution status (once True, stays True)
    if resolution_reached or progress_data.get("resolution_reached", False):
        progress_data["resolution_reached"] = True
```

#### 7d. Update `get_chapter_progress()` to use unified events
```python
def get_chapter_progress(self, chapter: Chapter) -> Dict[str, Any]:
    if not chapter.chapter_plot:
        return { ... }

    # Use unified event list
    all_events = self.get_all_chapter_events(chapter.chapter_plot)
    total_events = len(all_events)

    # ... rest of the logic uses all_events instead of key_events ...

    return {
        "has_plot": True,
        "completed_events": completed_events,
        "total_events": total_events,
        "progress_percentage": round(progress_percentage, 1),
        "remaining_events": remaining_events,
        "climax_reached": progress_data.get("climax_reached", False),
        "resolution_reached": progress_data.get("resolution_reached", False),
        "scene_count": actual_scene_count,
        "climax": chapter.chapter_plot.get("climax"),
        "resolution": chapter.chapter_plot.get("resolution"),
        "all_events": all_events  # Return unified list for UI
    }
```

#### 7e. Keep `generate_pacing_guidance()` as-is
The existing pacing guidance already handles:
- Progress percentage messaging
- "Approaching climax" when progress is high
- "Guide toward climax/resolution" when events complete

No changes needed - it naturally works with the unified approach.

### 8. Backend: Scene Generation Endpoint
**File:** `backend/app/api/scene_endpoints.py`

Update the scene generation flow to pass `plot_check_mode` from the story:

```python
# Around line 1296
# Get story's plot_check_mode (default to "1" for strict linear)
plot_check_mode = story.plot_check_mode or "1"

# Pass to extract_and_update_progress
await chapter_progress_service.extract_and_update_progress(
    chapter=chapter,
    scene_content=final_content,
    llm_service=llm_service,
    user_id=current_user.id,
    user_settings=user_settings_dict,
    plot_check_mode=plot_check_mode
)
```

### 9. Frontend: Types
**File:** `frontend/src/types/settings.ts`

Update `GenerationPreferences` interface:
```typescript
default_plot_check_mode?: '1' | '3' | 'all';
```

**File:** `frontend/src/types/story.ts` (or equivalent)
```typescript
plot_check_mode?: '1' | '3' | 'all';
```

### 10. Frontend: User Settings UI (Default for New Stories)
**File:** `frontend/src/components/settings/tabs/ContextSettingsTab.tsx`

Add dropdown under the "Enable Plot Progress Tracking" section:
```tsx
<div className="mt-4">
  <label className="text-sm text-gray-300">Default Plot Check Mode (for new stories)</label>
  <select
    value={generationPrefs.default_plot_check_mode || '1'}
    onChange={(e) => setGenerationPrefs({
      ...generationPrefs,
      default_plot_check_mode: e.target.value
    })}
    className="w-full bg-gray-700 text-white rounded px-3 py-2 mt-1"
  >
    <option value="1">Next event only (strict linear) - Recommended</option>
    <option value="3">Next 3 events (slight flexibility)</option>
    <option value="all">All remaining events (full flexibility)</option>
  </select>
  <p className="text-xs text-gray-400 mt-1">
    Controls how many plot events are checked after each scene.
    Strict = events must happen in order. Flexible = events can trigger out of order.
  </p>
</div>
```

### 11. Frontend: Story Settings UI (Per-Story Override)
**File:** `frontend/src/components/StorySettingsModal.tsx` (or equivalent)

Add dropdown for per-story `plot_check_mode` setting in the Story Settings section:
```tsx
{/* Plot Check Mode - only show if plot tracking is available */}
<div className="mt-4">
  <label className="text-sm text-gray-300">Plot Check Mode</label>
  <select
    value={story.plot_check_mode || '1'}
    onChange={(e) => updateStory({ plot_check_mode: e.target.value })}
    className="w-full bg-gray-700 text-white rounded px-3 py-2 mt-1"
  >
    <option value="1">Next event only (strict linear)</option>
    <option value="3">Next 3 events (slight flexibility)</option>
    <option value="all">All remaining events (full flexibility)</option>
  </select>
  <p className="text-xs text-gray-400 mt-1">
    Strict: Events must happen in exact order.
    Flexible: Events can be detected out of order.
  </p>
</div>
```

### 12. Frontend: Settings Modal State
**File:** `frontend/src/components/SettingsModal.tsx`

Update default state and save logic to include `default_plot_check_mode`.

---

## File Change Summary

| File | Change Type |
|------|-------------|
| `backend/app/models/story.py` | Add `plot_check_mode` column |
| `backend/app/models/user_settings.py` | Add `default_plot_check_mode` column + update methods |
| `backend/config.yaml` | Add default value |
| `backend/alembic/versions/XXX_*.py` | New migration |
| `backend/app/api/settings.py` | Update schema + endpoint |
| `backend/app/api/stories.py` | Update schemas + create logic |
| `backend/app/services/chapter_progress_service.py` | Unified events + mode filtering |
| `backend/app/api/scene_endpoints.py` | Pass `plot_check_mode` to service |
| `frontend/src/types/settings.ts` | Update types |
| `frontend/src/types/story.ts` | Update types |
| `frontend/src/components/settings/tabs/ContextSettingsTab.tsx` | Add UI |
| `frontend/src/components/StorySettingsModal.tsx` | Add UI |
| `frontend/src/components/SettingsModal.tsx` | Update state |

---

## Key Behavior Changes

### Before (Current)
- `key_events` sent to LLM for detection
- `climax` detected via text matching (`climax.lower() in scene_content.lower()`)
- `resolution` only via manual toggle
- All remaining events always sent

### After (New)
- All events (`key_events` + `climax` + `resolution`) sent to LLM
- Unified detection - no more text matching hacks
- `plot_check_mode` controls how many events are sent
- `climax_reached` / `resolution_reached` derived from event completion
- Pacing guidance unchanged - still highlights approaching climax

---

## Testing Considerations

1. **Mode "1" (strict linear)**
   - Only first remaining event sent to LLM
   - Events must complete in order
   - Climax only checked after all key_events done

2. **Mode "3" (slight flexibility)**
   - First 3 remaining events sent
   - Can detect up to 3 events in any order

3. **Mode "all" (full flexibility)**
   - All remaining events sent (current behavior)
   - Backwards compatible

4. **Unified events**
   - Climax detected via LLM (not text match)
   - Resolution detected via LLM (not manual only)
   - Progress percentage includes climax/resolution in total

5. **User default → story initialization**
   - New stories inherit user's `default_plot_check_mode`
   - Existing stories default to "1" (strict)

---

## Migration Path

1. Deploy migration (adds columns with NULL/default values)
2. Existing stories get `plot_check_mode = NULL` → treated as "1" (strict - new default)
3. Existing `completed_events` preserved - climax/resolution just get added when detected
4. No data migration needed for `chapter_plot` structure (brainstorm unchanged)
