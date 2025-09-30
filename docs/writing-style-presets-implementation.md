# Writing Style Presets - Implementation Plan

## Overview
Implement a user-friendly writing style preset system that allows users to customize how the AI writes their stories, while keeping critical system prompts locked for app stability.

## Architecture

### User-Customizable
1. **Universal System Prompt** - Controls writing style, tone, voice, NSFW settings for ALL generations
2. **Story Summary Prompt** (optional override) - Custom style for story summaries

### System-Locked
- All user prompts (what to generate, format requirements)
- All structural/parsing requirements

## Database Schema

### New Table: `writing_style_presets`
```sql
CREATE TABLE writing_style_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    summary_system_prompt TEXT,  -- Optional override for summaries
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT one_active_per_user UNIQUE (user_id, is_active) WHERE is_active = TRUE
);

CREATE INDEX idx_writing_presets_user_active ON writing_style_presets(user_id, is_active);
```

### Migration Plan
1. Create new `writing_style_presets` table
2. Create default preset for existing users
3. Deprecate old `prompt_templates` table (or repurpose)

## Backend Implementation

### Phase 1: Models & Database (1-2 hours)
- [ ] Create `WritingStylePreset` model in `backend/app/models/writing_style_preset.py`
- [ ] Create migration script `backend/migrate_add_writing_presets.py`
- [ ] Run migration and test

### Phase 2: API Endpoints (2-3 hours)
Create new router: `backend/app/routers/writing_presets.py`

**Endpoints:**
```python
GET    /api/writing-presets/              # List user's presets
GET    /api/writing-presets/{id}          # Get specific preset
POST   /api/writing-presets/              # Create new preset
PUT    /api/writing-presets/{id}          # Update preset
DELETE /api/writing-presets/{id}          # Delete preset
POST   /api/writing-presets/{id}/activate # Set as active
POST   /api/writing-presets/{id}/duplicate # Clone preset
GET    /api/writing-presets/default       # Get system default
```

### Phase 3: Update PromptManager (1-2 hours)
Update `backend/app/services/llm/prompts.py`:

```python
def get_prompt(template_key, user_id, db, **vars):
    # Get user's active writing style
    style = get_active_writing_style(user_id, db)
    
    # Determine system prompt
    if template_key == "story_summary" and style and style.summary_system_prompt:
        system_prompt = style.summary_system_prompt
    elif style and style.system_prompt:
        system_prompt = style.system_prompt
    else:
        # Fall back to YAML default
        system_prompt = yaml_prompts[template_key]["system"]
    
    # User prompt is ALWAYS from YAML (locked)
    user_prompt_template = yaml_prompts[template_key]["user"]
    user_prompt = user_prompt_template.format(**vars)
    
    return system_prompt, user_prompt
```

### Phase 4: Cache Invalidation (1 hour)
- [ ] Invalidate LLM cache when preset is changed
- [ ] Invalidate when preset is activated
- [ ] Update cache key to include preset_id

## Frontend Implementation

### Phase 1: UI Components (3-4 hours)
Create new components in `frontend/src/components/writing-presets/`:

**Components:**
- `WritingPresetsManager.tsx` - Main management UI
- `PresetEditor.tsx` - Edit individual preset
- `PresetSelector.tsx` - Dropdown in settings/toolbar
- `PresetCard.tsx` - Display preset info
- `PresetPreview.tsx` - Test preset with sample generation

### Phase 2: API Integration (2 hours)
Update `frontend/src/lib/api.ts`:
```typescript
export const writingPresets = {
  list: () => api.get('/writing-presets/'),
  get: (id: number) => api.get(`/writing-presets/${id}`),
  create: (data) => api.post('/writing-presets/', data),
  update: (id: number, data) => api.put(`/writing-presets/${id}`, data),
  delete: (id: number) => api.delete(`/writing-presets/${id}`),
  activate: (id: number) => api.post(`/writing-presets/${id}/activate`),
  duplicate: (id: number) => api.post(`/writing-presets/${id}/duplicate`),
  getDefault: () => api.get('/writing-presets/default'),
};
```

### Phase 3: Settings Page Integration (2 hours)
- [ ] Add "Writing Styles" tab to settings page
- [ ] Integrate `WritingPresetsManager` component
- [ ] Add quick preset selector in app toolbar

### Phase 4: State Management (1 hour)
Update Redux store to track active preset:
```typescript
interface WritingPresetState {
  presets: WritingPreset[];
  activePreset: WritingPreset | null;
  loading: boolean;
  error: string | null;
}
```

## Testing Plan

### Backend Tests
- [ ] Test preset CRUD operations
- [ ] Test activate/deactivate logic (only one active per user)
- [ ] Test prompt resolution (custom vs default)
- [ ] Test summary override logic
- [ ] Test with multiple users

### Frontend Tests
- [ ] Test preset selection
- [ ] Test preset editing
- [ ] Test preset preview
- [ ] Test deletion confirmation
- [ ] Test validation (empty prompts, etc.)

### Integration Tests
- [ ] Test story generation with custom preset
- [ ] Test summary generation with override
- [ ] Test switching presets mid-story
- [ ] Test cache invalidation

## Default Presets

### System Default (Read-only)
```
Name: Default
Description: Balanced, engaging storytelling for all genres

System Prompt:
You are a creative storytelling assistant. Write in an engaging narrative style that:
- Uses vivid, descriptive language
- Creates immersive scenes
- Develops characters naturally through action and dialogue
- Maintains appropriate pacing
- Respects the genre and tone specified by the user

Keep content appropriate unless explicitly told otherwise. Write in second person ("you") for interactive stories.
```

### Suggested User Presets (for documentation)
1. **Cozy & Light** - Warm, comforting, wholesome
2. **Dark & Gritty** - Noir, cynical, realistic
3. **Epic Fantasy** - Grand, dramatic, magical
4. **Romance** - Emotional, sensual, relationship-focused
5. **Horror** - Atmospheric, tense, unsettling

## Migration Strategy

### For Existing Users
1. Create "Default" preset for all existing users
2. Set as active
3. Migrate any custom prompts from old system (if applicable)

### Rollout Plan
1. Deploy backend (database + API)
2. Test with admin account
3. Deploy frontend
4. Announce feature to users
5. Provide documentation/tutorial

## Future Enhancements (v2)
- [ ] Preset sharing/community library
- [ ] Import/export presets as JSON
- [ ] Preset templates for specific genres
- [ ] Version history for presets
- [ ] AI-suggested improvements to prompts
- [ ] A/B testing between presets
- [ ] Per-story preset override

## Estimated Timeline
- **Backend**: 5-8 hours
- **Frontend**: 8-10 hours
- **Testing**: 3-4 hours
- **Documentation**: 1-2 hours
- **Total**: 17-24 hours (2-3 days)

## Success Metrics
- Users create at least one custom preset
- Active preset usage > 50% of users
- Story quality ratings remain stable or improve
- No increase in app errors
- Positive user feedback on customization

## Notes
- Keep it simple initially - can add complexity later
- Ensure backwards compatibility
- Provide clear documentation
- Make default preset high quality
- Test with various LLM providers

---

**Status**: Planning Complete ✅  
**Next Step**: Phase 1 - Models & Database  
**Assigned**: Ready to implement  
**Priority**: High  

