# Character Assistant - How It Works

## Overview

The Character Assistant extracts characters from stories in two phases:

### Phase 1: Extraction from `characters_present` Field
- Looks at the `characters_present` JSON field in scene variants
- This is data that was manually tagged or auto-extracted during scene creation
- **Limitation**: If a character isn't in this field, they won't be found here

### Phase 2: LLM-Based Extraction
- Analyzes all scene content using LLM
- Uses prompt: "Extract all character names from this text"
- Returns JSON array: `[{"name":"Name1","context":"role"}, ...]`
- Merges results with Phase 1 data

### Phase 3: Filtering & Ranking
- Filters out characters already in the user's character library
- Calculates importance score based on mention count and context
- Returns suggestions sorted by importance

## Why "Sorren" Might Be Missed

Based on the story "Paranoia's Price in Crystalline Shadows", here are likely reasons:

### 1. **Prompt Limitation**
Current prompt: "Extract all **character names** from this text"

**Problem**: The word "character" might cause the LLM to filter out:
- Entities/forces (like "Sorren" might be an entity)
- Spirits/beings
- Non-human entities
- Abstract concepts with names

### 2. **Indirect References**
If "Sorren" is referenced as:
- "the entity" instead of "Sorren"
- "it" (pronoun)
- "Sorren's presence" (possessive)
- "the crystalline entity"

The LLM might not connect these to the name "Sorren"

### 3. **Not in `characters_present` Field**
If scene variants don't have "Sorren" in their `characters_present` JSON field, Phase 1 won't find it.

### 4. **Name Capitalization Issues**
If sometimes written as "sorren" (lowercase) vs "Sorren" (capitalized), the LLM might treat them as different entities.

## Current Detection Prompt

```yaml
character_assistant:
  detection:
    system: |
      Extract character names from story text and return as JSON array.
    
    user: |
      Extract all character names from this text:
      
      {scene_content}
      
      Return JSON: [{{"name":"Name1","context":"role"}},{{"name":"Name2","context":"role"}}]
```

**Issues:**
- Only mentions "character names" - not entities, forces, spirits
- Doesn't emphasize extracting ALL named entities
- Doesn't handle indirect references
- Doesn't mention possessive forms or pronouns

## Suggested Improvements

### 1. Enhanced Detection Prompt
Update the prompt to explicitly include:
- Entities, forces, spirits, beings
- Non-human characters
- Entities referenced indirectly
- All named entities regardless of type

### 2. Better Context Handling
- Track possessive forms ("Sorren's", "Sorren's presence")
- Track indirect references ("the entity", "it")
- Use coreference resolution

### 3. Multiple Extraction Passes
- First pass: Direct name mentions
- Second pass: Entity/force references
- Third pass: Indirect references with context

### 4. Manual Override
- Allow users to manually add characters that the system missed
- Provide "Add Character" button even if not detected

## How to Check if Extraction is Working

1. Check backend logs for:
   - `"Calling LLM for character detection"`
   - `"Raw LLM response received"`
   - `"LLM response for character detection"`

2. Check if scenes have `characters_present` field populated

3. Test the endpoint: `POST /api/character-assistant/test/character-detection`

4. Check the character suggestions endpoint: `GET /api/character-assistant/{story_id}/character-suggestions`

## Next Steps

Would you like me to:
1. **Improve the detection prompt** to catch entities like "Sorren"?
2. **Add better logging** to see what the LLM is actually extracting?
3. **Add a manual character addition feature** for missed characters?
4. **Implement multi-pass extraction** to catch indirect references?

