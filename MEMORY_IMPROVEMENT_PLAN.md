# Memory System Improvement Plan

## Branch: `better_memory`

This document outlines a phased implementation plan for improving Kahani's memory system based on analysis of the current architecture and recent advancements in agentic memory.

---

## Executive Summary

**Goal:** Improve story continuity and reduce "the story forgot X" errors by:
1. Making extractions more reliable (foundation)
2. Adding a working memory scratchpad (quick win, cache-friendly)
3. Detecting contradictions before they compound (quality gate)

**Non-Goals (for this phase):**
- Graph-based memory (high effort, needs better extraction first)
- HyDE retrieval (breaks cache, defer to later)
- Temporal reasoning (needs new extraction fields)

---

## Current Architecture Summary

### What Works Well
- Batch-aligned context assembly for LLM cache hits
- Three-tier memory (short/medium/long-term)
- Fallback chains in extraction (extraction model → main LLM → retry)
- Branch-aware models throughout

### Key Pain Points
1. **Extractions return empty states** - validation passes but data is meaningless
2. **No persistent working memory** - context rebuilt from scratch each request
3. **No contradiction detection** - errors compound silently across scenes
4. **Relationship extraction underutilized** - field exists but poorly populated

---

## Phase 1: Extraction Quality Improvements

**Goal:** Ensure extractions produce meaningful data before building on top of them.

### 1.1 Add Extraction Quality Metrics

**Files to modify:**
- `backend/app/services/entity_state_service.py`
- `backend/app/models/story.py` (add metrics fields)

**Changes:**
```
Story model additions:
- extraction_success_rate: Float (0.0-1.0)
- extraction_empty_rate: Float (0.0-1.0)
- last_extraction_quality_check: DateTime
```

**Logic:**
- After each extraction, calculate quality score:
  - Characters extracted with ≥3 non-empty fields = "good"
  - Characters extracted with 1-2 fields = "partial"
  - Characters extracted with 0 fields = "empty"
- Track rolling average in Story model
- Log warning if quality drops below threshold (e.g., 70%)

**Why high certainty:** Simple counter logic, no complex dependencies.

---

### 1.2 Improve Extraction Validation

**Files to modify:**
- `backend/app/services/entity_state_service.py` (lines 516-588)

**Current behavior:**
```python
# Returns True even if all fields are empty strings
if isinstance(char_data, dict):
    return True  # Too permissive
```

**New behavior:**
```python
REQUIRED_FIELDS = ['location', 'emotional_state', 'physical_condition']
MEANINGFUL_THRESHOLD = 2  # At least 2 of 3 must be non-empty

def _has_meaningful_data(char_data: dict) -> bool:
    non_empty = sum(1 for f in REQUIRED_FIELDS
                    if char_data.get(f) and str(char_data[f]).strip())
    return non_empty >= MEANINGFUL_THRESHOLD
```

**Why high certainty:** Small change to existing validation, no new dependencies.

---

### 1.3 Improve Relationship Extraction Prompts

**Files to modify:**
- `backend/prompts.yml` (entity_state_extraction sections)

**Current issue:** `relationship_changes` field in prompt has minimal examples.

**Improvement:**
```yaml
# Add to entity_state_extraction prompts
relationship_changes:
  description: "Changes in how this character relates to others"
  format: |
    {
      "character_name": {
        "relationship_type": "friend|enemy|romantic|family|professional|rival",
        "change": "what changed this scene",
        "current_status": "current relationship state"
      }
    }
  examples:
    - {"Radhika": {"relationship_type": "romantic", "change": "first kiss", "current_status": "dating"}}
    - {"Ali": {"relationship_type": "friend", "change": "revealed secret", "current_status": "trusted confidant"}}
```

**Why high certainty:** Prompt-only change, no code changes needed.

---

## Phase 2: Working Memory Scratchpad

**Goal:** Add persistent working memory that tracks focus across generation calls.

### 2.1 Add Scratchpad Model

**Files to create:**
- `backend/app/models/working_memory.py`

**Model definition:**
```python
class WorkingMemory(Base):
    __tablename__ = "working_memory"

    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id"), nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)

    # Current focus items (what the story is tracking)
    active_threads = Column(JSON)  # ["Will X reveal the secret?", "The mysterious letter"]

    # Recent focus (what was important in last few scenes)
    recent_focus = Column(JSON)  # ["Character A's inner conflict", "The confrontation"]

    # Unresolved from last scene
    pending_items = Column(JSON)  # ["The letter was mentioned but not opened"]

    # Character focus (who needs attention)
    character_spotlight = Column(JSON)  # {"Nishant": "needs development", "Radhika": "just had major moment"}

    # Last updated
    last_scene_sequence = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    story = relationship("Story", back_populates="working_memory")
```

**Why high certainty:** Simple model, follows existing patterns (see EntityStateBatch).

---

### 2.2 Add Scratchpad Update Logic

**Files to modify:**
- `backend/app/services/entity_state_service.py` (add method)
- `backend/prompts.yml` (add scratchpad extraction prompt)

**New method in entity_state_service.py:**
```python
async def update_working_memory(
    self,
    story_id: int,
    branch_id: int,
    chapter_id: int,
    scene_sequence: int,
    scene_content: str
) -> WorkingMemory:
    """Update working memory after scene generation."""

    # Get current working memory or create new
    memory = self.db.query(WorkingMemory).filter(
        WorkingMemory.story_id == story_id,
        WorkingMemory.branch_id == branch_id
    ).first()

    if not memory:
        memory = WorkingMemory(story_id=story_id, branch_id=branch_id)
        self.db.add(memory)

    # Extract updates from scene (small LLM call)
    updates = await self._extract_memory_updates(scene_content, memory)

    # Apply updates
    memory.active_threads = updates.get('active_threads', memory.active_threads)
    memory.recent_focus = updates.get('recent_focus', memory.recent_focus)
    memory.pending_items = updates.get('pending_items', [])
    memory.character_spotlight = updates.get('character_spotlight', {})
    memory.last_scene_sequence = scene_sequence
    memory.chapter_id = chapter_id

    self.db.commit()
    return memory
```

**Extraction prompt (prompts.yml):**
```yaml
working_memory_update:
  system: |
    You update a story's working memory after each scene.
    Extract what the story should remember and track.
    Be concise - this is metadata, not prose.

  user: |
    Scene just written:
    {scene_content}

    Current working memory:
    Active threads: {current_threads}
    Recent focus: {current_focus}

    Update the working memory:

    ACTIVE_THREADS: [questions/tensions the story is building toward - max 5]
    RECENT_FOCUS: [what was important in this scene - max 3]
    PENDING_ITEMS: [things mentioned but not resolved in this scene - max 3]
    CHARACTER_SPOTLIGHT: {character: reason they need attention}

    Return as JSON.
```

**Why high certainty:** Follows existing extraction patterns, small focused prompt.

---

### 2.3 Integrate Scratchpad into Context

**Files to modify:**
- `backend/app/services/context_manager.py` (add to context dict)
- `backend/app/services/llm/service.py` (add to message assembly)

**Context manager addition:**
```python
def build_story_context(self, ...):
    context = {...}  # existing

    # Add working memory if exists
    working_memory = self.db.query(WorkingMemory).filter(
        WorkingMemory.story_id == story_id,
        WorkingMemory.branch_id == branch_id
    ).first()

    if working_memory:
        context['working_memory'] = {
            'active_threads': working_memory.active_threads or [],
            'recent_focus': working_memory.recent_focus or [],
            'pending_items': working_memory.pending_items or [],
            'character_spotlight': working_memory.character_spotlight or {}
        }

    return context
```

**Message assembly (service.py) - insert AFTER pacing, BEFORE final task:**
```python
# After pacing message, before task instruction
if context.get('working_memory'):
    wm = context['working_memory']
    memory_text = f"""=== STORY FOCUS ===
Active threads to develop: {', '.join(wm['active_threads'][:3])}
Recent focus: {', '.join(wm['recent_focus'][:2])}
Pending from last scene: {', '.join(wm['pending_items'][:2])}
"""
    if wm['character_spotlight']:
        spotlight = [f"{k}: {v}" for k, v in list(wm['character_spotlight'].items())[:2]]
        memory_text += f"Character attention needed: {'; '.join(spotlight)}\n"

    messages.append({"role": "user", "content": memory_text})
```

**Why high certainty:**
- Scratchpad is small (100-200 tokens)
- Placed at end, doesn't break cache prefix
- Optional - graceful fallback if missing

---

### 2.4 Trigger Scratchpad Update

**Files to modify:**
- `backend/app/api/scene_endpoints.py` (after scene generation)

**Add to background tasks after scene generation:**
```python
# Existing background tasks
background_tasks.add_task(run_extractions, ...)
background_tasks.add_task(update_semantic_memory, ...)

# New: Update working memory
background_tasks.add_task(
    update_working_memory,
    story_id=story_id,
    branch_id=branch_id,
    chapter_id=chapter_id,
    scene_sequence=scene.sequence_number,
    scene_content=generated_content
)
```

**Why high certainty:** Follows existing background task pattern exactly.

---

## Phase 3: Contradiction Detection

**Goal:** Detect and flag continuity errors before they compound.

### 3.1 Add Contradiction Detection Service

**Files to create:**
- `backend/app/services/contradiction_service.py`

**Service definition:**
```python
class ContradictionService:
    """Detects continuity errors between extractions."""

    CONTRADICTION_TYPES = [
        'location_jump',      # Character moved without travel scene
        'knowledge_leak',     # Character knows something they shouldn't
        'state_regression',   # State reverted without explanation
        'timeline_error',     # Event order inconsistency
    ]

    async def check_extraction(
        self,
        story_id: int,
        branch_id: int,
        scene_sequence: int,
        new_states: dict,
        db: Session
    ) -> List[Contradiction]:
        """Check new extraction against previous state."""

        contradictions = []

        # Get previous character states
        prev_states = db.query(CharacterState).filter(
            CharacterState.story_id == story_id,
            CharacterState.branch_id == branch_id
        ).all()

        for char_state in new_states.get('characters', []):
            char_name = char_state.get('name')
            prev = next((s for s in prev_states if s.character.name == char_name), None)

            if not prev:
                continue

            # Check location jump
            if (char_state.get('location') and prev.current_location and
                char_state['location'] != prev.current_location):
                # Flag if no travel mentioned
                contradictions.append(Contradiction(
                    type='location_jump',
                    character=char_name,
                    previous=prev.current_location,
                    current=char_state['location'],
                    scene_sequence=scene_sequence,
                    severity='warning'
                ))

            # Check knowledge leak
            new_knowledge = set(char_state.get('knowledge_gained', []))
            # Would need scene content to verify knowledge source
            # For now, just log new knowledge for review

        return contradictions
```

**Why high certainty:**
- Simple comparison logic
- Uses existing CharacterState model
- Can start with just location_jump detection, expand later

---

### 3.2 Add Contradiction Model

**Files to create:**
- `backend/app/models/contradiction.py`

**Model definition:**
```python
class Contradiction(Base):
    __tablename__ = "contradictions"

    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id"), nullable=True)
    scene_sequence = Column(Integer, nullable=False)

    contradiction_type = Column(String(50))  # location_jump, knowledge_leak, etc.
    character_name = Column(String(255), nullable=True)

    previous_value = Column(Text)
    current_value = Column(Text)

    severity = Column(String(20))  # info, warning, error
    resolved = Column(Boolean, default=False)
    resolution_note = Column(Text, nullable=True)

    detected_at = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="contradictions")
```

**Why high certainty:** Simple logging model, no complex relationships.

---

### 3.3 Integrate Contradiction Detection

**Files to modify:**
- `backend/app/services/entity_state_service.py`

**Add after extraction, before state update:**
```python
async def extract_and_update_states(self, ...):
    # ... existing extraction code ...

    # NEW: Check for contradictions
    contradiction_service = ContradictionService()
    contradictions = await contradiction_service.check_extraction(
        story_id=story_id,
        branch_id=branch_id,
        scene_sequence=scene_sequence,
        new_states=extracted_states,
        db=self.db
    )

    # Log contradictions (don't block generation)
    for c in contradictions:
        logger.warning(f"[CONTRADICTION] {c.type}: {c.character} "
                      f"was at '{c.previous}', now at '{c.current}' "
                      f"(scene {c.scene_sequence})")
        self.db.add(c)

    # ... continue with existing state update ...
```

**Why high certainty:**
- Non-blocking (just logging)
- Can be disabled via config if needed
- Uses existing extraction flow

---

### 3.4 Add Contradiction API (Optional)

**Files to create:**
- `backend/app/api/contradictions.py`

**Endpoints:**
```python
@router.get("/stories/{story_id}/contradictions")
async def get_contradictions(story_id: int, resolved: bool = False):
    """Get unresolved contradictions for a story."""

@router.patch("/contradictions/{id}/resolve")
async def resolve_contradiction(id: int, note: str):
    """Mark contradiction as resolved with explanation."""
```

**Why high certainty:** Simple CRUD, follows existing API patterns.

---

## Implementation Order

```
Week 1: Phase 1 (Extraction Quality)
├── 1.1 Add extraction metrics to Story model
├── 1.2 Improve validation in entity_state_service
└── 1.3 Update extraction prompts for relationships

Week 2: Phase 2 (Working Memory)
├── 2.1 Create WorkingMemory model + migration
├── 2.2 Add scratchpad update service method
├── 2.3 Integrate into context assembly
└── 2.4 Add background task trigger

Week 3: Phase 3 (Contradiction Detection)
├── 3.1 Create ContradictionService
├── 3.2 Create Contradiction model + migration
├── 3.3 Integrate into extraction flow
└── 3.4 Add API endpoints (optional)

Week 4: Testing & Refinement
├── Test with existing stories
├── Tune extraction quality thresholds
├── Refine contradiction severity levels
└── Gather feedback on scratchpad usefulness
```

---

## Database Migrations Required

1. **Phase 1:** Alter `stories` table - add `extraction_success_rate`, `extraction_empty_rate`
2. **Phase 2:** Create `working_memory` table
3. **Phase 3:** Create `contradictions` table

All migrations are additive (no destructive changes).

---

## Configuration Additions

```yaml
# config.yaml additions

memory:
  # Extraction quality
  extraction_quality_threshold: 0.7  # Warn if below
  extraction_required_fields: ["location", "emotional_state"]

  # Working memory
  enable_working_memory: true
  working_memory_max_threads: 5
  working_memory_max_tokens: 200

  # Contradiction detection
  enable_contradiction_detection: true
  contradiction_severity_threshold: "warning"  # info, warning, error
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Working memory extraction adds latency | Run as background task, not blocking |
| Scratchpad breaks cache | Placed at end of context, after stable prefix |
| Contradiction detection false positives | Start with logging only, no blocking |
| Migration failures | All additive, can rollback easily |

---

## Success Metrics

1. **Extraction Quality:** Empty extraction rate drops from ~30% to <10%
2. **Continuity:** Contradiction detection catches >80% of location jumps
3. **User Experience:** "Story forgot X" complaints decrease
4. **Performance:** No measurable increase in generation latency (background tasks)

---

## Future Phases (Not in Scope)

After these phases succeed:

- **Phase 4:** Relationship graph from enriched extraction data
- **Phase 5:** HyDE retrieval for semantic search (with cache-aware hybrid)
- **Phase 6:** Temporal reasoning with timeline extraction
- **Phase 7:** Reflection cycles for character arc synthesis
