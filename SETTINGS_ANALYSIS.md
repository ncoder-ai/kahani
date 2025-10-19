# Settings Architecture Analysis & Recommendations

## Current State Overview

### 1. User Settings (Database-backed)
**Location**: `backend/app/models/user_settings.py`

**Current Categories:**
- **LLM Settings**: Temperature, top_p, top_k, repetition_penalty, max_tokens, API config
- **Context Settings**: max_tokens, keep_recent_scenes, summary_threshold, summary_threshold_tokens, enable_summarization
- **Generation Preferences**: default_genre, default_tone, scene_length, auto_choices, choices_count
- **UI Preferences**: Theme, font size, display options, notifications
- **Export Settings**: Format, metadata, choices inclusion
- **Advanced**: custom_system_prompt, experimental_features

**Missing from UserSettings:**
- ❌ Semantic memory configuration
- ❌ Context strategy selection (linear vs hybrid)
- ❌ Semantic search parameters
- ❌ Auto-extraction settings

---

### 2. Writing Style Presets (Database-backed)
**Location**: `backend/app/models/writing_style_preset.py`

**Current Functionality:**
- ✅ User-customizable system prompts (controls AI writing style, tone, NSFW)
- ✅ Optional summary-specific system prompts
- ✅ Per-user multiple presets with active preset selection
- ✅ Full CRUD operations via API
- ✅ **Actually being used** in LLM service

**How They're Used:**
```python
# In backend/app/services/llm/prompts.py (lines 90-110)
# SYSTEM prompts use writing style presets:
active_preset = db.query(WritingStylePreset).filter(
    WritingStylePreset.user_id == user_id,
    WritingStylePreset.is_active == True
).first()

if active_preset:
    # For story summaries - use specific override if exists
    if template_key == "story_summary" and active_preset.summary_system_prompt:
        prompt_text = active_preset.summary_system_prompt
    else:
        # For all other generation (scenes, choices, etc.)
        prompt_text = active_preset.system_prompt
```

**Current Features:**
- Name and description for organization
- Universal system prompt for all generations
- Optional override for story summaries
- Preset activation/deactivation
- Preset duplication
- Default template provided

**What They Control:**
- ✅ Writing style, tone, voice
- ✅ NSFW/content policies
- ✅ Narrative perspective
- ✅ Descriptiveness level
- ✅ Pacing preferences
- ✅ Character development approach

---

### 3. Prompt Templates (Database + YAML)
**Location**: `backend/app/models/prompt_template.py`, `backend/prompts.yml`

**Current Architecture:**
- **SYSTEM Prompts**: User-customizable via Writing Style Presets (universal)
- **USER Prompts**: LOCKED in YAML file (not user-editable)

**Available in YAML:**
```yaml
story_generation:
  scenario:      # Initial story scenario
  titles:        # Story title generation
  scene:         # Main scene generation
  scene_continuation: # Scene continuation after choice
  choices:       # Choice generation

choice_generation: # Direct choice generation

story_summary:     # Chapter/story summarization

character_generation:
  initial:       # Create new character
  brainstorm:    # Character ideas
  expand:        # Expand character details
```

**Two-Tier System:**
1. **System Prompts** (User-customizable)
   - Controlled by Writing Style Presets
   - Universal across all generation types
   - Or specific override for summaries
   
2. **User Prompts** (Locked in YAML)
   - Defines WHAT to do, not HOW
   - Contains template structure
   - Not user-editable for app stability

**Frontend "AI Prompts" Tab:**
**Location**: `frontend/src/app/settings/page.tsx` (lines 84-102, 154-198)

**Current Implementation:**
- Shows prompt templates list
- Allows viewing template details
- Has "edit" functionality
- **BUT**: Unclear if editing actually works or if it's for viewing only
- Loads from `/api/prompt-templates/` endpoint

---

## 🎯 Key Findings

### Writing Style Presets: ✅ WORKING & INTEGRATED

**Status**: **Fully functional and actively used**

**Evidence:**
1. Used directly in `PromptManager.get_prompt()` for all system prompts
2. Active preset is queried from database for each generation
3. LLM cache is invalidated when presets are updated
4. Frontend has full management UI via `WritingPresetsManager` component
5. API endpoints provide CRUD operations

**User Experience:**
- Users can create custom writing styles
- Switch between presets for different story types
- "Epic Fantasy", "Cozy Romance", "Gritty Noir", etc.
- Each preset controls how the AI writes

**Conclusion**: This system is **well-designed and working perfectly**. No issues.

---

### Prompt Templates Tab: ⚠️ CONFUSING

**Issues:**
1. **Unclear Purpose**: Shows prompts but unclear what's editable
2. **Redundancy with Writing Styles**: System prompts are controlled by Writing Style Presets, not this tab
3. **User Prompts are Locked**: YAML-based prompts shouldn't be user-editable
4. **Confusing UI**: Users might think they can edit prompts here, but they actually edit writing styles elsewhere

**What Users Actually Want Here:**
- View the prompt structure being used
- Understand how prompts are assembled
- Maybe see example outputs
- **NOT**: Edit the core prompt templates (that's for writing styles)

**Recommendation**: 
- **Rename to "Prompt Inspector"** or "Prompt Viewer"
- Make it read-only with clear explanation
- Show how user's active Writing Style Preset is being used
- Show the final assembled prompt (system + user combined)
- Link to Writing Style Presets for actual customization

---

### Semantic Memory Settings: ❌ MISSING FROM USER SETTINGS

**Currently in Global Config Only:**
```python
# backend/app/config.py (lines 37-51)
enable_semantic_memory: bool = True
semantic_db_path: str = "./data/chromadb"
semantic_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
semantic_search_top_k: int = 5
semantic_context_weight: float = 0.4
context_strategy: str = "hybrid"  # "linear" or "hybrid"
semantic_scenes_in_context: int = 5
character_moments_in_context: int = 3
auto_extract_character_moments: bool = True
auto_extract_plot_events: bool = True
extraction_confidence_threshold: int = 70
```

**Problem**: These are **global settings**, not per-user!

**User Impact:**
- All users share the same semantic memory configuration
- Users can't customize their context strategy
- Power users can't tune semantic search parameters
- No way to disable semantic memory if it causes issues

---

## 📋 Recommendations

### 1. Add Semantic Memory to User Settings ✨

**New Fields for `UserSettings` Model:**

```python
# Context Management Settings (existing - keep)
context_max_tokens: int = 4000
context_keep_recent_scenes: int = 3
context_summary_threshold: int = 5
context_summary_threshold_tokens: int = 8000
enable_context_summarization: bool = True
auto_generate_summaries: bool = True

# NEW: Semantic Memory Settings
enable_semantic_memory: bool = True  # Per-user toggle
context_strategy: str = "hybrid"     # "linear" or "hybrid"

# NEW: Semantic Search Configuration
semantic_search_top_k: int = 5       # How many similar scenes to retrieve
semantic_scenes_in_context: int = 5  # Max semantic scenes in context
semantic_context_weight: float = 0.4 # Balance between recent vs semantic (0-1)

# NEW: Character & Plot Tracking
character_moments_in_context: int = 3  # Max character moments in context
auto_extract_character_moments: bool = True
auto_extract_plot_events: bool = True

# NEW: Advanced Semantic Options (could be in advanced settings)
extraction_confidence_threshold: int = 70  # 0-100
```

**Benefits:**
- Users can choose linear vs hybrid context
- Power users can tune semantic search
- Users experiencing issues can disable semantic memory
- Different preferences for different use cases

**UI Organization:**
```
Settings Tabs:
├── Writing Styles (existing, working perfectly)
├── LLM Settings (existing)
├── Context Management ⭐ (enhanced with semantic options)
│   ├── Basic Settings
│   │   ├── Max context tokens
│   │   ├── Keep recent scenes
│   │   └── Auto-summarization
│   ├── Semantic Memory ✨ (NEW)
│   │   ├── Enable semantic memory (toggle)
│   │   ├── Context strategy (linear/hybrid)
│   │   ├── Semantic scenes to include (slider)
│   │   ├── Character moments to include (slider)
│   │   └── Auto-extract settings (toggles)
│   └── Advanced
│       └── Extraction confidence threshold
├── Generation Preferences (existing)
├── UI Preferences (existing)
└── Prompt Viewer 👁️ (renamed from AI Prompts)
```

---

### 2. Reorganize/Clarify Prompt Templates Tab

**Current Confusion:**
- Tab is called "AI Prompts"
- Shows prompt templates
- But system prompts are controlled by Writing Styles
- User prompts are locked in YAML

**Proposed Changes:**

**Option A: Rename to "Prompt Inspector" (Read-Only)**
```
Prompt Inspector Tab:
├── Active Writing Style: [Preset Name]
│   └── [Link to edit Writing Style Presets]
├── System Prompt Preview
│   └── Shows active preset's system prompt
├── Available Prompt Templates
│   ├── Scene Generation
│   │   ├── System Prompt: [from active preset]
│   │   └── User Prompt: [from YAML, read-only]
│   ├── Choice Generation
│   ├── Story Summary
│   └── Character Generation
└── Example Output (optional)
    └── Show how prompts combine
```

**Option B: Merge into Writing Styles**
- Remove separate "AI Prompts" tab
- Add "Preview Prompts" button in Writing Style Presets
- Shows how the preset will be used across different generation types

**Option C: Advanced Debug View** (For power users)
- Rename to "Advanced: Prompt Debug"
- Show full prompt assembly process
- Include context strategy details
- Show semantic search results
- Display token usage breakdown

**Recommendation**: **Option A** (Prompt Inspector) with clear read-only indication

---

### 3. What's Missing vs What Exists

#### Writing Style Presets (Existing) ✅
**What they control:**
- HOW the AI writes (style, tone, voice)
- NSFW/content policies
- Narrative approach
- Descriptiveness

**What they DON'T control:**
- WHAT information is sent (context assembly) ← This is Context Management
- Template structure (locked in YAML) ← This ensures app stability

#### Context Management (Needs Enhancement) ⭐
**What it controls:**
- WHAT information is included in context
- HOW context is assembled (linear vs semantic)
- Token budgets and allocation
- Summarization strategies

**Currently has:**
- Basic token limits
- Scene retention counts
- Summarization toggles

**Missing:**
- Semantic memory controls ← **Need to add**
- Context strategy selection ← **Need to add**
- Semantic search tuning ← **Need to add**

---

## 🚀 Implementation Plan

### Phase 1: Database Migration
1. Add new columns to `user_settings` table:
   - `enable_semantic_memory`
   - `context_strategy`
   - `semantic_search_top_k`
   - `semantic_scenes_in_context`
   - `semantic_context_weight`
   - `character_moments_in_context`
   - `auto_extract_character_moments`
   - `auto_extract_plot_events`
   - `extraction_confidence_threshold`

2. Set defaults from current global config

3. Create migration script

### Phase 2: Backend Updates
1. Update `UserSettings.to_dict()` to include new semantic settings

2. Update `SemanticContextManager.__init__()` to read from user settings:
```python
# Currently reads from global settings
self.enable_semantic = settings.enable_semantic_memory

# Should read from user settings
if user_settings and user_settings.get("semantic_settings"):
    sem_settings = user_settings["semantic_settings"]
    self.enable_semantic = sem_settings.get("enable_semantic_memory", settings.enable_semantic_memory)
    # etc...
```

3. Update API endpoints to save/load semantic settings

4. Fallback to global settings if user hasn't configured

### Phase 3: Frontend Updates
1. Add "Semantic Memory" section to Context Management tab

2. Create UI components:
   - Toggle for enable/disable
   - Radio buttons for linear/hybrid strategy
   - Sliders for scene/moment counts
   - Advanced settings accordion

3. Add helpful tooltips explaining each setting

4. Show "Experimental" badge if enabled

### Phase 4: Prompt Tab Cleanup
1. Rename "AI Prompts" to "Prompt Inspector"

2. Make it clear it's read-only

3. Show active Writing Style Preset at top

4. Link to Writing Styles tab for customization

5. Show how prompts are assembled

---

## 📊 Summary Table

| Feature | Current State | User Configurable? | Location | Recommendation |
|---------|--------------|-------------------|----------|----------------|
| **Writing Style** | ✅ Working | ✅ Yes (Per Writing Preset) | Writing Styles Tab | Keep as-is, working perfectly |
| **LLM Parameters** | ✅ Working | ✅ Yes (Per User) | LLM Settings Tab | Keep as-is |
| **Context Strategy** | ⚠️ Global only | ❌ No | config.py | **Add to UserSettings** |
| **Semantic Search** | ⚠️ Global only | ❌ No | config.py | **Add to UserSettings** |
| **Auto-extraction** | ⚠️ Global only | ❌ No | config.py | **Add to UserSettings** |
| **System Prompts** | ✅ Working | ✅ Yes (Via Writing Styles) | Writing Styles Tab | Keep as-is |
| **User Prompts** | ✅ Working | ❌ No (Locked in YAML) | prompts.yml | Keep locked, clarify in UI |
| **Prompt Templates** | ⚠️ Confusing | ❓ Unclear | AI Prompts Tab | **Rename to Prompt Inspector** |

---

## 🎯 Quick Wins

1. **Add semantic settings to Context Management tab** (High impact, medium effort)
2. **Rename "AI Prompts" to "Prompt Inspector"** (Low effort, high clarity)
3. **Add tooltips explaining semantic memory** (Low effort, high UX improvement)
4. **Link Writing Styles from Prompt Inspector** (Low effort, reduces confusion)

---

## 🔮 Future Enhancements

### Per-Story Settings Override
Allow users to override settings for specific stories:
```python
class Story(Base):
    # Existing fields...
    
    # NEW: Optional overrides
    override_context_strategy: str = None  # If set, overrides user default
    override_semantic_enabled: bool = None
    # etc...
```

**Use case**: 
- Short story → Force linear context
- Epic saga → Force hybrid with max semantic retrieval
- Experimental story → Custom extraction thresholds

### Semantic Search Quality Metrics
Show users how well semantic search is working:
- Relevance scores of retrieved scenes
- Token usage breakdown (recent vs semantic)
- Character moment extraction confidence
- Option to manually tag scenes as "important"

### Preset Templates for Context Management
Just like Writing Style Presets, create Context Presets:
- "Short Story" (linear, minimal semantic)
- "Long-form Epic" (hybrid, aggressive semantic)
- "Character-focused" (high character moments)
- "Plot-driven" (high plot events)

---

## Final Recommendation Priority

**High Priority:**
1. ✅ Add semantic memory settings to UserSettings model
2. ✅ Create UI in Context Management tab
3. ✅ Update SemanticContextManager to read user settings
4. ✅ Rename "AI Prompts" to "Prompt Inspector"

**Medium Priority:**
5. Add helpful tooltips and explanations
6. Create "preset" templates for common scenarios
7. Show semantic search metrics in debug view

**Low Priority:**
8. Per-story setting overrides
9. Advanced semantic tuning options
10. Semantic search quality analytics

---

**Conclusion**: The Writing Style Presets system is **excellent and working perfectly**. The main gap is **semantic memory configuration being global instead of per-user**. Adding these settings to Context Management will give users the power they need without disrupting the existing well-designed architecture.

