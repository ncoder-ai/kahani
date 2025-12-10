# Entity Extraction Improvements - Implementation Summary

## Date: December 9, 2025

## Overview
Implemented comprehensive improvements to entity state extraction to address issues with:
- Body parts being extracted as objects (hands, eyes, face, etc.)
- Over-granular locations (e.g., "headboard of the bed" instead of "bedroom")
- Interpretive/symbolic descriptions instead of factual states
- Trivial everyday items being tracked

## Changes Made

### 1. Updated `/Users/user/apps/kahani/backend/prompts.yml`

#### A. `entity_state_extraction.single` (lines 700-781)
**Key Improvements:**
- Added explicit exclusion lists for objects (body parts, furniture, everyday items)
- Added location scope rules (rooms/buildings only, not furniture/positions)
- Added factual-only description requirements with clear examples
- Added concise state requirements (1-5 words for states)
- Added validation examples showing correct vs. incorrect extractions

**New Rules Added:**
- **Character States**: Must be factual, concise (1-5 words), and objective
- **Locations**: Only rooms, buildings, outdoor areas, or named places
- **Objects**: Only weapons, magical items, plot devices, or items explicitly exchanged
- **Descriptions**: All must be factual physical observations, not interpretations

**Explicit Exclusions:**
- Body parts (hands, eyes, face, arms, legs, head, fingers, etc.)
- Furniture (unless central to plot)
- Everyday items (phones, keys, cups, pens)
- Parts of objects (door handles, table legs)
- Spatial references (next to X, by the Y, near Z)
- Natural features (trees, rocks, grass unless named/magical)

#### B. `entity_state_extraction.batch` (lines 784-922)
**Key Improvements:**
- Reduced extraction limits for higher quality:
  - NPCs: 10 → 5 (only most significant)
  - Plot events: 8 → 5 (stricter thresholds: importance >= 70, confidence >= 80)
  - Entity states: 15 → 8 (prioritize most plot-critical)
  - Objects: 3-5 total (highly selective)
- Added same exclusion rules and factual requirements as single extraction
- Added comprehensive validation examples
- Emphasized "quality over quantity" throughout

### 2. Updated `/Users/user/apps/kahani/backend/app/services/llm/extraction_service.py`

#### `extract_entity_states()` method (lines 627-726)
**Key Improvements:**
- Updated default system prompt to emphasize precision and quality
- Replaced entire user prompt with improved version matching prompts.yml
- Added all new exclusion rules and factual requirements
- Added location scope rules (rooms/buildings only)
- Added concise state requirements (1-3 words)

**New System Prompt:**
```python
system_prompt: str = "You are a precise story analysis assistant. Extract entity state changes and return only valid JSON. Focus on quality over quantity - extract only truly significant entities and states."
```

## Expected Improvements

### Objects
**Before:**
- "hands", "eyes", "face" (body parts)
- "coffee cup", "phone" (trivial items)
- "door", "table" (furniture)
- Condition: "Silent confirmation of a rendezvous" (interpretive)

**After:**
- Only: weapons, magical items, plot devices, explicitly exchanged items
- Condition: "damaged", "intact", "locked" (factual only)
- Significance: "used by X to do Y" (factual role only)

### Locations
**Before:**
- "headboard of the bed" (too specific)
- "next to the door" (spatial reference)
- "table", "chair" (furniture)
- Inconsistent naming ("Sarah's bedroom" → "the bedroom" → "her room")

**After:**
- "bedroom", "kitchen", "forest clearing" (room/building level)
- Consistent naming across scenes
- No furniture or spatial references

### Entity States
**Before:**
- Emotional state: "Feeling a complex mix of determination and uncertainty about the future"
- Physical condition: "Appears to be in good health based on his actions"
- Current attire: "dressed in standard field gear" (inferred)

**After:**
- Emotional state: "determined", "anxious", "angry" (1-3 words)
- Physical condition: "wounded", "exhausted", "healthy" (1-3 words)
- Current attire: Only if explicitly mentioned in text, otherwise null

## Validation Examples Added

### Correct Extraction Example:
```json
{
  "entity_states": {
    "characters": [
      {
        "name": "Sarah",
        "location": "bedroom",
        "emotional_state": "nervous",
        "possessions_gained": ["pistol"]
      }
    ],
    "locations": [
      {
        "name": "bedroom",
        "occupants": ["Sarah"]
      }
    ],
    "objects": [
      {
        "name": "pistol",
        "owner": "Sarah",
        "condition": null,
        "significance": "drawn and aimed at door"
      }
    ]
  }
}
```

### Incorrect Extraction Example (What NOT to do):
```json
{
  "entity_states": {
    "characters": [
      {
        "location": "next to the door",  // ❌ Spatial reference
        "emotional_state": "feeling complex mix of fear and determination"  // ❌ Too verbose
      }
    ],
    "locations": [
      {"name": "door"},  // ❌ Part of room
      {"name": "next to the door"}  // ❌ Spatial reference
    ],
    "objects": [
      {"name": "hands"},  // ❌ Body part - NEVER extract
      {"name": "door"},  // ❌ Part of room
      {"condition": "trembling with fear"}  // ❌ Interpretive
    ]
  }
}
```

## Testing Recommendations

1. **Test with problematic scenes** that previously extracted body parts
2. **Verify location granularity** - should be room/building level only
3. **Check object filtering** - should only see weapons, artifacts, plot devices
4. **Validate state conciseness** - emotional/physical states should be 1-3 words
5. **Ensure consistency** - same entities should have consistent names across scenes

## Files Modified

1. `/Users/user/apps/kahani/backend/prompts.yml`
   - Lines 700-781: `entity_state_extraction.single`
   - Lines 784-922: `entity_state_extraction.batch`

2. `/Users/user/apps/kahani/backend/app/services/llm/extraction_service.py`
   - Lines 627-726: `extract_entity_states()` method

## Backward Compatibility

These changes are backward compatible:
- The JSON structure remains the same
- Database schema unchanged
- Only the quality and precision of extractions improve
- Existing entity states are not affected (only new extractions)

## Next Steps

1. Monitor extraction quality in production
2. Collect examples of any remaining issues
3. Fine-tune thresholds if needed (currently: 3+ mentions for objects, 5 max NPCs, etc.)
4. Consider adding post-processing validation to filter common mistakes

## Notes

- The `extract_all_batch()` method in extraction_service.py uses centralized prompts from prompts.yml, so batch improvements automatically apply
- Hardcoded limits in extraction_service.py (max_npcs_total=10, max_events_total=8) are overridden by stricter prompt instructions (5 and 5)
- All prompts emphasize "quality over quantity" and "be highly selective"

