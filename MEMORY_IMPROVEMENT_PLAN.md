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

### Phase 1 Testing

**Files to create:**
- `backend/tests/test_extraction_quality.py`

**Test cases:**

```python
# 1. Test extraction validation rejects empty states
async def test_validation_rejects_empty_character_state():
    """Characters with all empty fields should fail validation."""
    empty_state = {"name": "John", "location": "", "emotional_state": "", "physical_condition": ""}
    assert not _has_meaningful_data(empty_state)

async def test_validation_accepts_partial_state():
    """Characters with 2+ fields should pass validation."""
    partial_state = {"name": "John", "location": "kitchen", "emotional_state": "angry", "physical_condition": ""}
    assert _has_meaningful_data(partial_state)

# 2. Test extraction metrics tracking
async def test_extraction_metrics_updated():
    """Extraction should update story quality metrics."""
    story = create_test_story()
    await extract_and_update_states(scene_id=1)
    story.refresh()
    assert story.extraction_success_rate is not None
    assert 0.0 <= story.extraction_success_rate <= 1.0

# 3. Test relationship extraction format
async def test_relationship_extraction_format():
    """Relationships should include type, change, and status."""
    scene_content = "John kissed Mary for the first time."
    result = await extract_entity_states(scene_content, ["John", "Mary"])
    john_state = next(c for c in result['characters'] if c['name'] == 'John')
    assert 'relationship_changes' in john_state
    # Check structure if populated
    if john_state['relationship_changes']:
        for char, rel in john_state['relationship_changes'].items():
            assert 'relationship_type' in rel or isinstance(rel, str)
```

**Manual testing:**
1. Generate 10 scenes in a test story
2. Check logs for `[EXTRACTION]` entries
3. Verify `extraction_success_rate` in database
4. Compare before/after empty extraction rates

---

## Phase 2: Working Memory Scratchpad

**Goal:** Add persistent working memory that tracks scene-to-scene focus (micro-level continuity).

### Relationship to Existing PlotEvent System

**PlotEvent already tracks:**
- `thread_id` + `is_resolved` → Major story threads spanning scenes/chapters
- `description` + `involved_characters` → What happened

**What's different about Working Memory:**
| PlotEvent | Working Memory |
|-----------|----------------|
| Major story beats | Scene-to-scene details |
| "Will John discover Mary's secret?" | "John picked up a letter but didn't read it" |
| Spans chapters | Needs follow-up next scene |
| Extracted from content | Tracks narrative attention |

**Integration approach:** Derive `active_threads` FROM unresolved PlotEvents rather than duplicating.

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

    # NOTE: active_threads derived from PlotEvent.is_resolved=False, not stored here

    # Recent focus (what was important in last few scenes) - NEW
    recent_focus = Column(JSON)  # ["Character A's inner conflict", "The confrontation"]

    # Pending micro-items (mentioned but not acted on) - NEW
    pending_items = Column(JSON)  # ["The letter was picked up but not read", "Phone rang but wasn't answered"]

    # Character spotlight (who needs narrative attention) - NEW
    character_spotlight = Column(JSON)  # {"Nishant": "hasn't spoken in 2 scenes", "Radhika": "just had revelation"}

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
    You track scene-to-scene story continuity.
    Extract micro-level items that need follow-up.
    Be concise - this is metadata, not prose.
    DO NOT track major plot threads (those are tracked separately).

  user: |
    Scene just written:
    {scene_content}

    Current focus: {current_focus}

    Extract micro-continuity items:

    RECENT_FOCUS: [what was emotionally/narratively important in THIS scene - max 3 items]
    PENDING_ITEMS: [specific things MENTIONED but not ACTED ON - objects picked up, questions asked but not answered, interruptions - max 3 items]
    CHARACTER_SPOTLIGHT: {character_name: "reason they need narrative attention next"}

    Only include PENDING_ITEMS for concrete unfinished actions, not general plot threads.

    Return as JSON: {"recent_focus": [], "pending_items": [], "character_spotlight": {}}
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

    # Get active threads from PlotEvent (not duplicated in working memory)
    active_threads = self.db.query(PlotEvent).filter(
        PlotEvent.story_id == story_id,
        PlotEvent.branch_id == branch_id,
        PlotEvent.is_resolved == False
    ).order_by(PlotEvent.importance_score.desc()).limit(5).all()

    # Get working memory for micro-level tracking
    working_memory = self.db.query(WorkingMemory).filter(
        WorkingMemory.story_id == story_id,
        WorkingMemory.branch_id == branch_id
    ).first()

    context['story_focus'] = {
        'active_threads': [pe.description for pe in active_threads],  # FROM PlotEvent
        'recent_focus': working_memory.recent_focus if working_memory else [],
        'pending_items': working_memory.pending_items if working_memory else [],
        'character_spotlight': working_memory.character_spotlight if working_memory else {}
    }

    return context
```

**Message assembly (service.py) - insert AFTER pacing, BEFORE final task:**
```python
# After pacing message, before task instruction
if context.get('story_focus'):
    sf = context['story_focus']
    focus_parts = []

    if sf['active_threads']:
        focus_parts.append(f"Unresolved threads: {'; '.join(sf['active_threads'][:3])}")
    if sf['recent_focus']:
        focus_parts.append(f"Recent focus: {', '.join(sf['recent_focus'][:2])}")
    if sf['pending_items']:
        focus_parts.append(f"Pending: {', '.join(sf['pending_items'][:2])}")
    if sf['character_spotlight']:
        spotlight = [f"{k} ({v})" for k, v in list(sf['character_spotlight'].items())[:2]]
        focus_parts.append(f"Character attention: {', '.join(spotlight)}")

    if focus_parts:
        messages.append({"role": "user", "content": "=== STORY FOCUS ===\n" + "\n".join(focus_parts)})
```

**Why high certainty:**
- Active threads from existing PlotEvent (no duplication)
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

### Phase 2 Testing

**Files to create:**
- `backend/tests/test_working_memory.py`

**Test cases:**

```python
# 1. Test working memory model CRUD
async def test_working_memory_creation():
    """Should create working memory for a story."""
    story = create_test_story()
    wm = WorkingMemory(
        story_id=story.id,
        branch_id=story.current_branch_id,
        recent_focus=["test focus"],
        pending_items=["test pending"],
        character_spotlight={"John": "needs attention"}
    )
    db.add(wm)
    db.commit()
    assert wm.id is not None

# 2. Test active threads derived from PlotEvent
async def test_active_threads_from_plot_events():
    """Active threads should come from unresolved PlotEvents."""
    story = create_test_story()
    # Create unresolved plot event
    pe = PlotEvent(story_id=story.id, is_resolved=False, description="Will John find the key?")
    db.add(pe)
    db.commit()

    context = context_manager.build_story_context(story_id=story.id)
    assert "Will John find the key?" in context['story_focus']['active_threads']

# 3. Test working memory update extraction
async def test_working_memory_update():
    """Should extract focus items from scene content."""
    scene_content = "John picked up the mysterious letter but was interrupted before he could read it."
    updates = await _extract_memory_updates(scene_content, existing_memory=None)
    # Should identify pending item
    assert any("letter" in item.lower() for item in updates.get('pending_items', []))

# 4. Test context integration preserves cache prefix
async def test_story_focus_at_end_of_context():
    """Story focus should be in suffix, not prefix."""
    context = context_manager.build_story_context(story_id=1)
    messages = format_context_as_messages(context)
    # Story focus should be near the end
    focus_idx = next(i for i, m in enumerate(messages) if 'STORY FOCUS' in m.get('content', ''))
    assert focus_idx >= len(messages) - 3  # In last 3 messages

# 5. Test graceful fallback when no working memory
async def test_context_without_working_memory():
    """Should not fail if working memory doesn't exist."""
    story = create_test_story()  # No working memory created
    context = context_manager.build_story_context(story_id=story.id)
    # Should have empty defaults, not error
    assert context['story_focus']['recent_focus'] == []
    assert context['story_focus']['pending_items'] == []
```

**Manual testing:**
1. Generate 5 scenes in sequence
2. After each scene, check `working_memory` table for updates
3. Verify `recent_focus` and `pending_items` make sense
4. Check generation logs for "STORY FOCUS" inclusion
5. Compare generation quality with/without working memory (A/B)

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

### Phase 3 Testing

**Files to create:**
- `backend/tests/test_contradiction_detection.py`

**Test cases:**

```python
# 1. Test location jump detection
async def test_detects_location_jump():
    """Should detect when character moves without travel scene."""
    story = create_test_story()
    # Set previous state
    char_state = CharacterState(story_id=story.id, character_id=1, current_location="kitchen")
    db.add(char_state)
    db.commit()

    # New extraction has different location
    new_states = {"characters": [{"name": "John", "location": "beach"}]}

    contradictions = await contradiction_service.check_extraction(
        story_id=story.id,
        new_states=new_states,
        scene_sequence=5
    )

    assert len(contradictions) == 1
    assert contradictions[0].contradiction_type == "location_jump"
    assert contradictions[0].previous_value == "kitchen"
    assert contradictions[0].current_value == "beach"

# 2. Test no false positive for same location
async def test_no_false_positive_same_location():
    """Should not flag when character stays in same location."""
    # Previous: kitchen, New: kitchen
    new_states = {"characters": [{"name": "John", "location": "kitchen"}]}
    contradictions = await contradiction_service.check_extraction(...)
    assert len(contradictions) == 0

# 3. Test contradiction model persistence
async def test_contradiction_persisted():
    """Detected contradictions should be saved to database."""
    # Trigger location jump
    await entity_state_service.extract_and_update_states(scene_id=1)

    contradictions = db.query(Contradiction).filter(
        Contradiction.story_id == story.id
    ).all()
    # Should have logged the contradiction
    assert len(contradictions) >= 0  # May or may not detect based on extraction

# 4. Test contradiction resolution
async def test_contradiction_resolution():
    """Should be able to mark contradictions as resolved."""
    contradiction = Contradiction(
        story_id=1, contradiction_type="location_jump",
        previous_value="kitchen", current_value="beach"
    )
    db.add(contradiction)
    db.commit()

    # Resolve it
    contradiction.resolved = True
    contradiction.resolution_note = "Travel happened off-screen"
    db.commit()

    assert contradiction.resolved == True

# 5. Test API endpoint
async def test_get_contradictions_api():
    """API should return unresolved contradictions."""
    response = await client.get(f"/api/stories/{story_id}/contradictions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
```

**Manual testing:**
1. Create a story and generate several scenes
2. Manually edit a character's location in `character_states` table
3. Generate next scene
4. Check `contradictions` table for logged entries
5. Check logs for `[CONTRADICTION]` warnings
6. Test API endpoint to list contradictions

**Integration testing:**
1. Generate a 10-scene story end-to-end
2. Review all logged contradictions
3. Verify severity levels make sense
4. Check that contradictions don't block generation (non-blocking)

---

## Implementation Order

```
Phase 1: Extraction Quality
├── 1.1 Add extraction metrics to Story model
├── 1.2 Improve validation in entity_state_service
├── 1.3 Update extraction prompts for relationships
├── 1.4 Write tests (test_extraction_quality.py)
└── 1.5 Manual testing: generate 10 scenes, verify metrics

Phase 2: Working Memory
├── 2.1 Create WorkingMemory model + migration
├── 2.2 Add scratchpad update service method
├── 2.3 Integrate into context assembly (with PlotEvent for active_threads)
├── 2.4 Add background task trigger
├── 2.5 Write tests (test_working_memory.py)
└── 2.6 Manual testing: verify context includes STORY FOCUS section

Phase 3: Contradiction Detection
├── 3.1 Create ContradictionService
├── 3.2 Create Contradiction model + migration
├── 3.3 Integrate into extraction flow (non-blocking)
├── 3.4 Add API endpoints
├── 3.5 Write tests (test_contradiction_detection.py)
└── 3.6 Manual testing: trigger location jump, verify logging

Final: Integration Testing
├── Generate 20-scene story end-to-end
├── Review extraction quality metrics
├── Review working memory updates
├── Review contradiction logs
└── A/B compare generation quality
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
