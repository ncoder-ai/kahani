# Complete Summary System Documentation

## 📊 Three-Tier Summary Architecture

### Tier 1: Chapter Summary (`chapter.auto_summary`)
**Purpose:** Summarize ONLY the scenes within a specific chapter

**Generation Process:**
1. Collects ALL scenes from the chapter
2. Combines scene content into one text
3. Sends to LLM with prompt: "Summarize this chapter's content..."
4. **Does NOT** consider previous chapters or story context
5. Result: Standalone chapter summary

**When Generated:**
- Automatically after N scenes (user-configurable, default: 5)
- When chapter is marked as completed
- Manually via "Generate Chapter Summary" button

**Stored In:** `Chapter.auto_summary`

**Example:**
```
Chapter 1 Summary:
"Maya discovers ancient ruins in the desert and meets the Guardian, 
a mysterious being who warns her about the Shadow Realm..."
```

---

### Tier 2: Story So Far (`chapter.story_so_far`)
**Purpose:** Provide context for generating scenes in this chapter

**Generation Process - Summary of Summaries Approach:**
```python
# Step 1: Collect previous chapter summaries
previous_summaries = [
    "Chapter 1: Maya discovers ruins...",
    "Chapter 2: Maya journeys to Shadow Realm...",
    "Chapter 3: Maya battles Shadow Lord..."
]

# Step 2: Get recent 3 scenes from CURRENT chapter (truncated to 200 chars)
recent_scenes = [
    "Scene 8: Maya finds the artifact...",
    "Scene 9: Guardian reveals truth..."
]

# Step 3: Combine into structured format
combined = """
=== Previous Chapters ===
Chapter 1: [summary]
Chapter 2: [summary]
Chapter 3: [summary]

=== Chapter 4 (Current) - Recent Scenes ===
Scene 8: [preview]
Scene 9: [preview]
"""

# Step 4: Send to LLM with prompt:
# "Create a cohesive Story So Far from these summaries and recent events"

# Result: Narrative that flows naturally
story_so_far = "The journey began when Maya discovered ancient ruins...
                 [continued narrative combining all previous chapters]...
                 Recently, Maya found the artifact and learned the truth..."
```

**Key Points:**
- ✅ **Summary of Summaries** - NOT concatenation
- ✅ **LLM creates cohesive narrative** from condensed inputs
- ✅ **Maintains continuity** across all chapters
- ✅ **Efficient** - Doesn't send all scenes to LLM

**When Generated:**
- After every N scenes (along with chapter summary)
- When creating a new chapter
- Manually via "Generate Chapter Summary" button (with `regenerate_story_so_far=true`)

**Stored In:** `Chapter.story_so_far`

**Example:**
```
Story So Far (Chapter 4):
"Maya's journey began with the discovery of ancient ruins where she met 
the Guardian. Together they ventured into the dangerous Shadow Realm, 
facing numerous challenges and uncovering dark secrets about her lineage. 
After a fierce battle with the Shadow Lord, Maya emerged victorious but 
wounded. Recently, she discovered a powerful artifact that may hold the 
key to her destiny, and the Guardian finally revealed the truth about 
her connection to the ancient prophecy..."
```

---

### Tier 3: Story Summary (`story.summary`)
**Purpose:** Overall summary of the entire story for display in dashboard

**Generation Process - Two Approaches:**

#### Approach 1: Summary of Summaries (NEW - Efficient)
```python
# Collect chapter summaries
chapter_summaries = [
    "Chapter 1: Maya discovers ruins and meets Guardian...",
    "Chapter 2: Journey to Shadow Realm...",
    "Chapter 3: Battle with Shadow Lord...",
    "Chapter 4: Discovery of artifact..."
]

# Combine with metadata
prompt = """Create a comprehensive story summary from these chapter summaries:

Story Title: Maya's Last Stand
Genre: Fantasy Adventure
Total Chapters: 4
Total Scenes: 35

Chapter Summaries:
[chapter summaries here]

Provide a cohesive overview (3-5 paragraphs)"""

# Send to LLM
story_summary = await llm_service._generate(...)
```

**Benefits:**
- ✅ Much more efficient (only summaries, not all scenes)
- ✅ Scalable to stories with 100+ chapters
- ✅ Maintains high-level narrative arc
- ✅ Fast generation

#### Approach 2: Full Scene Summarization (OLD - Less Efficient)
```python
# Combine ALL scene content from ALL chapters
combined_text = "\n\n".join([
    f"Scene {scene.sequence_number}: {scene.content}"
    for scene in all_scenes
])

# Send entire story to LLM
story_summary = await llm_service.generate(...)
```

**Drawbacks:**
- ❌ Very slow for long stories
- ❌ May hit token limits
- ❌ Expensive LLM calls
- ❌ Not scalable

**When Generated:**
- Manually via "Generate Story Summary" button (uses Approach 1)
- Via old endpoint `/regenerate-summary` (uses Approach 2)

**Stored In:** `Story.summary`

**Displayed:** Dashboard summary box for each story

**Example:**
```
Maya's Last Stand - Story Summary:
"Maya's Last Stand is an epic fantasy adventure following Maya, a young woman 
who discovers ancient ruins in the desert and meets a mysterious Guardian. 
Her discovery sets her on a perilous journey to the Shadow Realm, where she 
must confront dark forces and uncover the truth about her heritage.

Throughout her quest, Maya faces numerous challenges including fierce battles 
with shadow creatures, treacherous landscapes, and moral dilemmas that test 
her resolve. The Guardian serves as both mentor and mystery, gradually 
revealing secrets about an ancient prophecy that Maya is destined to fulfill.

The story reaches its climax with an intense confrontation against the Shadow 
Lord, where Maya must use both her newfound powers and her unwavering 
determination. Though victorious, the battle leaves her changed. The 
discovery of a powerful artifact in the aftermath hints at even greater 
challenges ahead, while the Guardian's final revelation about Maya's 
connection to the ancient prophecy sets the stage for her ultimate destiny..."
```

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Scene Generated                       │
└───────────────────────────────┬─────────────────────────────┘
                                │
                    Every N scenes? (threshold = 5)
                                │
                ┌───────────────┴───────────────┐
                │                               │
               NO                              YES
                │                               │
         Continue writing              ┌────────┴────────┐
                                       │  Auto-Generate:  │
                                       │  1. Chapter      │
                                       │     Summary      │
                                       │  2. Story So Far │
                                       └────────┬────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                           Chapter.auto_summary    Chapter.story_so_far
                           (This chapter only)     (All previous + current)
                                    │                       │
                                    │                       │
                    Used for viewing chapter    Used for generating
                      in Chapter modal         new scenes in context
                                    │                       │
                                    └───────────┬───────────┘
                                                │
                                    When "Create New Chapter" clicked
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        │                                               │
        Mark previous chapter COMPLETED              Create new chapter with
            Generate its summary if missing        story_so_far from combined
                                                      previous chapters
                                                           │
┌─────────────────────────────────────────────────────────┴─────────────┐
│                                                                         │
│                  Manual Triggers (UI Buttons):                         │
│  1. "Generate Chapter Summary" → Updates current chapter               │
│  2. "Generate Story Summary" → Creates Story.summary from all chapters │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
                        Story.summary displayed in Dashboard
```

---

## 🎯 API Endpoints

### 1. Generate Chapter Summary
```
POST /api/stories/{story_id}/chapters/{chapter_id}/generate-summary?regenerate_story_so_far=true
```

**What it does:**
- Generates `chapter.auto_summary` (this chapter's scenes)
- If `regenerate_story_so_far=true`: Also generates `chapter.story_so_far`

**Response:**
```json
{
  "message": "Chapter summary generated successfully",
  "chapter_summary": "Summary text...",
  "story_so_far": "Combined narrative...",
  "scenes_summarized": 10
}
```

---

### 2. Generate Story Summary (Summary of Summaries)
```
POST /api/summaries/stories/{story_id}/generate-story-summary
```

**What it does:**
- Collects `auto_summary` from ALL chapters
- Creates comprehensive story summary
- Saves to `story.summary`
- Uses summary of summaries approach (efficient!)

**Response:**
```json
{
  "message": "Story summary generated successfully",
  "summary": "Comprehensive story summary...",
  "chapters_summarized": 4,
  "total_scenes": 35,
  "approach": "summary_of_summaries"
}
```

---

### 3. Regenerate Story Summary (Old Method)
```
POST /api/summaries/stories/{story_id}/regenerate-summary
```

**What it does:**
- Combines ALL scene content (not summaries)
- Generates summary from full text
- Less efficient but more detailed

---

## 🖥️ UI Implementation

### Chapter Modal Buttons

```
┌─────────────────────────────────────────────────────────────┐
│  Create New Chapter                                    [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Story Summary (All Chapters)   [Generate Story Summary]    │
│  Creates a comprehensive summary from all chapter summaries  │
│                                                              │
│  Current Chapter Summary        [Generate Chapter Summary]  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Chapter 1 summary appears here...                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  [Title and Description inputs...]                           │
│                                                              │
│  Story So Far (will be used for new chapter)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Combined summary from all previous chapters...         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Button Colors:**
- **Green** = Story Summary (affects entire story)
- **Blue** = Chapter Summary (affects current chapter)

---

## 🎨 Dashboard Display

The `story.summary` field should be displayed in the dashboard:

### Current Dashboard
Shows: Title, genre, scenes count, last updated

### Enhanced Dashboard (TO DO)
Should show: **Story Summary** in summary box
- Display `story.summary` if it exists
- Show "Generate Summary" button if missing
- Allow users to see story overview without opening it

---

## 🔑 Key Design Decisions

### Why Not Include Story Context in Chapter Summary?
- Chapter summaries should be **reusable** and **standalone**
- They get combined later in `story_so_far`
- Cleaner separation of concerns

### Why Summary of Summaries for Story So Far?
- **Efficiency**: Only send condensed summaries to LLM
- **Scalability**: Works with 100+ chapters
- **Cost**: Much cheaper than sending all scenes
- **Quality**: LLM creates cohesive narrative from summaries

### Why Both Approaches for Story Summary?
- **New approach** (summary of summaries): For regular use, efficient
- **Old approach** (full scenes): For detailed analysis when needed

---

## 📈 Performance Comparison

### Story with 10 Chapters, 100 Scenes

**Old Approach (Full Scenes):**
- Input tokens: ~50,000 tokens
- Generation time: ~30 seconds
- Cost: High
- Max story size: Limited by context window

**New Approach (Summary of Summaries):**
- Input tokens: ~5,000 tokens (10x less!)
- Generation time: ~5 seconds (6x faster!)
- Cost: 10x cheaper
- Max story size: Unlimited (summaries are fixed size)

---

## ✅ Implementation Checklist

- [x] `Chapter.auto_summary` generation
- [x] `Chapter.story_so_far` generation (summary of summaries)
- [x] Auto-trigger after N scenes
- [x] Auto-trigger on chapter creation
- [x] Manual chapter summary button
- [x] Manual story summary button
- [x] New efficient story summary endpoint
- [ ] Display `story.summary` in dashboard
- [ ] Add "Generate Summary" button to dashboard cards

---

## 🧪 Testing

### Test Chapter Summary:
1. Open Shadow's Covenant (Chapter 1, 2 scenes)
2. Click "Generate Chapter Summary"
3. Verify `auto_summary` appears in box

### Test Story So Far:
1. Same chapter, click "Generate Chapter Summary"
2. Verify `story_so_far` combines all previous chapters

### Test Story Summary:
1. Click "Generate Story Summary" (green button)
2. Verify success message shows approach: "summary_of_summaries"
3. Check dashboard for story summary display

---

## 🎯 Summary

**Three distinct summary types:**
1. **Chapter Summary** = Standalone chapter content
2. **Story So Far** = Cascading narrative for context (summary of summaries)
3. **Story Summary** = Overall story overview for dashboard

**All use efficient summary of summaries approach where appropriate!**
