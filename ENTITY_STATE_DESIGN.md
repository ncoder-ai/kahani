# Entity State Tracking Design

## Overview

Entity state tracking maintains a **living, evolving snapshot** of characters, locations, and objects throughout the story. Unlike semantic search (which finds similar past scenes), entity states provide **current, authoritative truth** about the story world.

## Why Entity States?

### Problem 1: Character Inconsistency
```
Scene 50: "Sarah wore the silver necklace from her mother"
Scene 100: "Sarah reached for the necklace, but it wasn't there"
Scene 101: "Sarah's necklace glinted in the moonlight" ❌ INCONSISTENT!
```

**With Entity State:**
```json
{
  "character": "Sarah",
  "possessions": ["ancient_sword", "mother's_ring"],
  "missing_items": ["silver_necklace (lost in Scene 78)"]
}
```

### Problem 2: Relationship Tracking
```
Scene 30: "Sarah and Marcus grew closer"
Scene 60: "Marcus betrayed Sarah"
Scene 90: "Sarah smiled warmly at Marcus" ❌ WRONG!
```

**With Entity State:**
```json
{
  "relationships": {
    "Marcus": {
      "status": "enemy",
      "last_interaction": "Scene 60: betrayal",
      "trust_level": -5,
      "unresolved_conflict": "betrayal and lies"
    }
  }
}
```

### Problem 3: Location State
```
Scene 40: "The castle throne room was destroyed in the battle"
Scene 70: "Sarah entered the pristine throne room" ❌ WRONG!
```

**With Entity State:**
```json
{
  "location": "Castle Throne Room",
  "condition": "destroyed",
  "notable_features": ["collapsed ceiling", "broken throne"],
  "last_event": "Scene 40: dragon battle"
}
```

---

## Entity Types

### 1. Character States

```json
{
  "character_id": 1,
  "character_name": "Sarah Thornwood",
  "story_id": 1,
  "last_updated_scene": 89,
  "state": {
    // PHYSICAL STATE
    "current_location": "Castle Throne Room",
    "physical_condition": "wounded but determined",
    "appearance": "blood-stained armor, disheveled hair",
    "possessions": ["Glowing Sword of Aether", "Mother's Silver Ring"],
    "missing_items": ["Royal Crown (stolen by Marcus)"],
    
    // EMOTIONAL/MENTAL STATE
    "emotional_state": "vengeful, heartbroken",
    "current_goal": "confront Marcus about his betrayal",
    "active_conflicts": [
      "revenge vs. mercy",
      "duty to kingdom vs. personal pain"
    ],
    "knowledge": [
      "Marcus's betrayal",
      "Sword's true power",
      "Father's murder by Marcus"
    ],
    "secrets": ["Carries Marcus's child"],
    
    // RELATIONSHIPS (dynamic)
    "relationships": {
      "Marcus": {
        "status": "enemy_former_lover",
        "trust": -8,
        "last_interaction_scene": 60,
        "last_interaction_summary": "Marcus revealed his betrayal",
        "unresolved_tension": "betrayal, lies, murder of father",
        "emotional_complexity": "still loves him despite everything"
      },
      "Elena": {
        "status": "ally_confidant",
        "trust": 9,
        "last_interaction_scene": 85,
        "last_interaction_summary": "Elena helped Sarah prepare for confrontation",
        "bond_type": "sisterhood"
      }
    },
    
    // CHARACTER ARC
    "arc_stage": "confrontation_climax",
    "arc_progress": 0.75,
    "key_decisions": [
      "Scene 45: Spared the dragon",
      "Scene 67: Chose revenge over mercy",
      "Scene 78: Lost mother's necklace saving villagers"
    ],
    
    // SKILLS/ABILITIES
    "skills": ["master swordsman", "limited magic from sword"],
    "recent_growth": "learned to channel sword's power",
    
    // RECENT ACTIONS (last 3 scenes)
    "recent_actions": [
      "Scene 87: Gathered allies",
      "Scene 88: Confronted castle guards",
      "Scene 89: Entered throne room"
    ]
  },
  
  "updated_at": "2024-01-15T14:30:00Z"
}
```

### 2. Location States

```json
{
  "location_id": 1,
  "location_name": "Castle Throne Room",
  "story_id": 1,
  "last_updated_scene": 89,
  "state": {
    // PHYSICAL STATE
    "condition": "damaged from battle",
    "atmosphere": "tense, dark, echoing",
    "lighting": "torchlit, shadows dancing",
    "temperature": "cold",
    "notable_features": [
      "Cracked marble throne",
      "Shattered stained glass windows",
      "Blood stains on floor from previous battle"
    ],
    
    // OCCUPANCY
    "current_occupants": ["Marcus", "Royal Guards (4)"],
    "previous_occupants": ["Sarah's father (Scene 10)", "Dragon (Scene 40)"],
    
    // HISTORY
    "significant_events": [
      "Scene 10: Sarah's coronation",
      "Scene 23: Marcus's betrayal revealed here",
      "Scene 40: Dragon attack",
      "Scene 60: Marcus claimed the throne"
    ],
    
    // OBJECTS PRESENT
    "objects": [
      "The Iron Throne (damaged)",
      "Ancient Tapestries (torn)",
      "Father's Portrait (slashed by Marcus)"
    ],
    
    // TIME/WEATHER
    "time_of_day": "midnight",
    "weather_visible": "storm outside, thunder rumbling"
  },
  
  "updated_at": "2024-01-15T14:30:00Z"
}
```

### 3. Object States

```json
{
  "object_id": 1,
  "object_name": "Sword of Aether",
  "story_id": 1,
  "last_updated_scene": 89,
  "state": {
    // PHYSICAL STATE
    "condition": "glowing with power",
    "appearance": "ethereal blue light, ancient runes visible",
    "current_location": "in Sarah's hand",
    "current_owner": "Sarah Thornwood",
    
    // HISTORY
    "origin": "Scene 15: discovered in throne room vault",
    "previous_owners": ["Sarah's father", "Ancient King Aldric"],
    "significance": "key to defeating Marcus",
    
    // CAPABILITIES
    "powers": [
      "amplifies wielder's emotions",
      "can cut through magic",
      "grows stronger near the throne"
    ],
    "limitations": [
      "drains wielder's energy",
      "unstable when used in anger"
    ],
    
    // RECENT HISTORY
    "recent_events": [
      "Scene 67: Power surge near castle",
      "Scene 78: Used to save villagers",
      "Scene 89: Glowing intensely in throne room"
    ]
  },
  
  "updated_at": "2024-01-15T14:30:00Z"
}
```

---

## Database Schema

### Character States Table
```sql
CREATE TABLE character_states (
    id INTEGER PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    story_id INTEGER REFERENCES stories(id) ON DELETE CASCADE,
    last_updated_scene INTEGER,
    
    -- Physical State
    current_location TEXT,
    physical_condition TEXT,
    appearance TEXT,
    possessions JSON,  -- Array of items
    
    -- Emotional/Mental State
    emotional_state TEXT,
    current_goal TEXT,
    active_conflicts JSON,  -- Array of conflicts
    knowledge JSON,  -- Array of known facts
    secrets JSON,  -- Array of secrets
    
    -- Relationships
    relationships JSON,  -- Object mapping character_name -> relationship_state
    
    -- Character Arc
    arc_stage TEXT,
    arc_progress FLOAT,  -- 0.0 to 1.0
    recent_decisions JSON,  -- Array of key decisions
    
    -- Recent Activity
    recent_actions JSON,  -- Last N actions
    
    -- Full State Snapshot (JSON)
    full_state JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(character_id, story_id)
);
```

### Location States Table
```sql
CREATE TABLE location_states (
    id INTEGER PRIMARY KEY,
    story_id INTEGER REFERENCES stories(id) ON DELETE CASCADE,
    location_name TEXT NOT NULL,
    last_updated_scene INTEGER,
    
    -- Physical State
    condition TEXT,
    atmosphere TEXT,
    notable_features JSON,
    
    -- Occupancy
    current_occupants JSON,
    
    -- History
    significant_events JSON,
    
    -- Full State Snapshot (JSON)
    full_state JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(story_id, location_name)
);
```

### Object States Table
```sql
CREATE TABLE object_states (
    id INTEGER PRIMARY KEY,
    story_id INTEGER REFERENCES stories(id) ON DELETE CASCADE,
    object_name TEXT NOT NULL,
    last_updated_scene INTEGER,
    
    -- Physical State
    condition TEXT,
    current_location TEXT,
    current_owner_id INTEGER REFERENCES characters(id),
    
    -- Metadata
    significance TEXT,
    object_type TEXT,  -- 'weapon', 'item', 'artifact', 'document'
    
    -- Full State Snapshot (JSON)
    full_state JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(story_id, object_name)
);
```

---

## Update Strategy

### After Each Scene Generation:

1. **Extract Entities**
   - Parse scene content for character mentions, locations, objects
   - Use LLM to identify state changes

2. **Update Character States**
   ```python
   # LLM Prompt
   "Analyze this scene and extract character state updates:
   Scene: [SCENE CONTENT]
   
   For each character, identify:
   - Location changes
   - Emotional changes
   - New knowledge acquired
   - Relationship changes
   - Physical state changes
   - Possessions gained/lost
   
   Return as JSON."
   ```

3. **Update Location States**
   - Track who entered/left
   - Note condition changes (battle damage, etc.)
   - Update atmosphere

4. **Update Object States**
   - Track location changes
   - Track ownership changes
   - Note condition changes

---

## Context Assembly

### Before Generating Next Scene:

```python
# Get entity states for context
character_states = get_active_character_states(story_id)
location_state = get_current_location_state(story_id)
object_states = get_relevant_object_states(story_id)

# Build entity context
entity_context = f"""
CURRENT CHARACTER STATES:

Sarah Thornwood:
- Location: {character_states['Sarah']['current_location']}
- Emotional State: {character_states['Sarah']['emotional_state']}
- Current Goal: {character_states['Sarah']['current_goal']}
- Possessions: {', '.join(character_states['Sarah']['possessions'])}
- Relationship with Marcus: {character_states['Sarah']['relationships']['Marcus']['status']}
  - Trust Level: {character_states['Sarah']['relationships']['Marcus']['trust']}/10
  - Last Interaction: {character_states['Sarah']['relationships']['Marcus']['last_interaction_summary']}

CURRENT LOCATION:

{location_state['location_name']}:
- Condition: {location_state['condition']}
- Atmosphere: {location_state['atmosphere']}
- Present: {', '.join(location_state['current_occupants'])}

IMPORTANT OBJECTS:

Sword of Aether:
- Location: {object_states['Sword of Aether']['current_location']}
- Condition: {object_states['Sword of Aether']['condition']}
- Current State: {object_states['Sword of Aether']['appearance']}
"""

# Send to LLM with scene generation prompt
```

---

## Benefits

### ✅ Character Consistency
- Always know character's current emotional state
- Track relationships dynamically
- Remember possessions, knowledge, goals

### ✅ World Continuity
- Locations maintain state (damaged, occupied, etc.)
- Objects don't teleport or disappear
- Time progression tracked

### ✅ Relationship Tracking
- Trust levels evolve
- Conflicts tracked
- Last interaction remembered

### ✅ Character Arc Progression
- Track where character is in their journey
- Remember key decisions
- Guide future development

---

## Example: Before & After

### Without Entity States
```
LLM Context: [Recent 5 scenes + semantic retrieval]

Generated Scene:
"Sarah smiled at Marcus warmly. 'It's good to see you again, my love.'"
❌ Forgot about the betrayal!
```

### With Entity States
```
LLM Context: 
- Recent 5 scenes
- Semantic retrieval
- Entity States:
  - Sarah: emotional_state="vengeful", relationships.Marcus.trust=-8
  - Sarah knows: Marcus betrayed her, murdered her father

Generated Scene:
"Sarah's eyes hardened as she faced Marcus. 'You took everything from me,' 
she whispered, her hand tightening on the sword. 'My father. My trust. My love.'"
✅ Perfect consistency!
```

---

## Implementation Plan

1. ✅ Design schema (this document)
2. Create database models
3. Create EntityStateService
4. Add LLM-based state extraction
5. Integrate into scene generation
6. Update context manager
7. Test with existing stories

---

## Next Steps

Ready to implement this? The payoff will be **massive** for your story quality!

