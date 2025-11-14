# Extraction Invalidation Plan

## Overview

When scenes are deleted or modified, we need to invalidate and regenerate extractions and entity states that depend on those scenes. This plan outlines the comprehensive approach to handle extraction invalidation.

## Current State

### What's Already Handled

1. **CharacterMemory** - Deleted via `cleanup_scene_embeddings()` → `delete_character_moments()`
2. **PlotEvent** - Deleted via `cleanup_scene_embeddings()` → `delete_plot_events()`
3. **SceneEmbedding** - Deleted via `cleanup_scene_embeddings()`
4. **ChapterSummaryBatch** - Invalidated in `delete_scenes_from_sequence()`

### What's Missing

1. **NPCMention** - Not deleted when scenes are removed
2. **NPCTracking** - Not recalculated when scenes are deleted/modified
3. **CharacterState** - Not invalidated/recalculated when scenes are deleted/modified
4. **LocationState** - Not invalidated/recalculated when scenes are deleted/modified
5. **ObjectState** - Not invalidated/recalculated when scenes are deleted/modified
6. **Scene Modification** - No invalidation when scene content changes

## Extraction Types and Dependencies

### 1. CharacterMemory (Character Moments)
- **Storage**: Scene-specific (one-to-many with scenes)
- **Dependency**: Directly tied to scene_id
- **On Delete**: ✅ Already handled - deleted via cascade/cleanup
- **On Modify**: Needs regeneration for that scene

### 2. PlotEvent
- **Storage**: Scene-specific (one-to-many with scenes)
- **Dependency**: Directly tied to scene_id
- **On Delete**: ✅ Already handled - deleted via cascade/cleanup
- **On Modify**: Needs regeneration for that scene

### 3. NPCMention
- **Storage**: Scene-specific (one-to-many with scenes)
- **Dependency**: Directly tied to scene_id
- **On Delete**: ❌ Missing - needs deletion
- **On Modify**: Needs regeneration for that scene

### 4. NPCTracking
- **Storage**: Story-level aggregated data
- **Dependency**: Aggregated from all NPCMention entries
- **On Delete**: ❌ Missing - needs recalculation from remaining mentions
- **On Modify**: Needs recalculation

### 5. CharacterState
- **Storage**: Story-level cumulative state
- **Dependency**: Built incrementally from all scenes up to `last_updated_scene`
- **On Delete**: ❌ Missing - needs recalculation from remaining scenes
- **On Modify**: Needs recalculation if scene is before `last_updated_scene`

### 6. LocationState
- **Storage**: Story-level cumulative state
- **Dependency**: Built incrementally from all scenes
- **On Delete**: ❌ Missing - needs recalculation from remaining scenes
- **On Modify**: Needs recalculation

### 7. ObjectState
- **Storage**: Story-level cumulative state
- **Dependency**: Built incrementally from all scenes
- **On Delete**: ❌ Missing - needs recalculation from remaining scenes
- **On Modify**: Needs recalculation

## Implementation Plan

### Task 1: Add NPCMention Cleanup on Scene Deletion

**Files**: 
- `backend/app/services/llm/service.py` (`delete_scenes_from_sequence`)
- `backend/app/services/semantic_integration.py` (`cleanup_scene_embeddings`)

**Changes**:
1. Add NPCMention deletion to `cleanup_scene_embeddings()`:
   ```python
   from ..models import NPCMention
   npc_mentions_deleted = db.query(NPCMention).filter(
       NPCMention.scene_id == scene_id
   ).delete()
   logger.debug(f"[CLEANUP] Deleted {npc_mentions_deleted} NPC mentions for scene {scene_id}")
   ```

### Task 2: Recalculate NPCTracking After Scene Deletion/Modification

**Files**:
- `backend/app/services/llm/service.py` (`delete_scenes_from_sequence`)
- `backend/app/api/stories.py` (scene modification endpoints)
- `backend/app/services/npc_tracking_service.py` (already has `recalculate_all_scores()`)

**Changes**:
1. After scene deletion, call `NPCTrackingService.recalculate_all_scores()` for the story
2. After scene modification, call `NPCTrackingService.recalculate_all_scores()` for the story
3. The existing `recalculate_all_scores()` method will:
   - Recalculate `total_mentions`, `scene_count`, `first_appearance_scene`, `last_appearance_scene`
   - Recalculate `importance_score`, `frequency_score`, `significance_score`
   - Update `crossed_threshold` status if needed
4. Note: Need to ensure `recalculate_all_scores()` properly handles deleted scenes (it queries NPCMention, so should work correctly)

### Task 3: Invalidate and Recalculate Entity States After Scene Deletion

**Files**:
- `backend/app/services/llm/service.py` (`delete_scenes_from_sequence`)
- `backend/app/services/entity_state_service.py` (new method)

**Changes**:
1. Create new method `recalculate_entity_states_from_scenes()`:
   - Takes story_id, db, user_id, user_settings, and optional `up_to_sequence` parameter
   - Gets all scenes up to that sequence (or all remaining scenes) ordered by sequence_number
   - Deletes existing CharacterState, LocationState, ObjectState records for the story
   - Re-extracts entity states from scratch by processing all remaining scenes in order
   - Uses existing `extract_and_update_states()` method for each scene
   - Updates CharacterState.last_updated_scene to the last processed scene

2. Call this method after scene deletion:
   ```python
   from ...services.entity_state_service import EntityStateService
   entity_service = EntityStateService(user_id, user_settings)
   await entity_service.recalculate_entity_states_from_scenes(
       db, story_id, user_id, user_settings, up_to_sequence=max_remaining_sequence
   )
   ```

**Considerations**:
- This is expensive (requires re-processing all remaining scenes)
- Could be optimized by only recalculating if deleted scenes were before any `last_updated_scene`
- For now, full recalculation ensures correctness
- Consider running in background task for large stories

### Task 4: Handle Scene Modification

**Files**:
- `backend/app/api/stories.py` (`_update_story_flow`, `continue_scene`)

**Changes**:
1. When scene content is modified, invalidate extractions for that scene:
   - Delete CharacterMemory for the scene
   - Delete PlotEvent for the scene
   - Delete NPCMention for the scene
   - Delete SceneEmbedding for the scene

2. Regenerate extractions for the modified scene:
   - Call `process_scene_embeddings()` with the new content
   - This will regenerate CharacterMemory, PlotEvent, NPCMention, SceneEmbedding

3. Recalculate aggregated data:
   - Recalculate NPCTracking (via `recalculate_all_scores()`)
   - Recalculate EntityStates if the modified scene affects them:
     - If scene sequence <= any CharacterState.last_updated_scene, recalculate
     - Similar for LocationState and ObjectState

### Task 5: Batch-Based Extraction Storage (Future Optimization)

**Note**: This is a potential optimization similar to ChapterSummaryBatch, but more complex.

**Concept**:
- Store extractions in batches (e.g., scenes 1-5, 6-10, etc.)
- When scenes are deleted, only regenerate affected batches
- Reduces token costs for long stories

**Challenges**:
- Entity states are cumulative, not batch-based
- CharacterMemory and PlotEvent are scene-specific, so batching doesn't help much
- NPCTracking is aggregated, so batching doesn't help

**Recommendation**: 
- Defer this optimization for now
- Focus on correct invalidation first
- Consider batching only for entity state recalculation if performance becomes an issue

## Implementation Order

1. **Task 1** - Add NPCMention cleanup (simple, low risk)
2. **Task 2** - Recalculate NPCTracking (moderate complexity)
3. **Task 3** - Recalculate Entity States (complex, expensive)
4. **Task 4** - Handle scene modification (moderate complexity)

## Error Handling

- All invalidation operations should be wrapped in try/except
- Log errors but don't fail scene deletion if invalidation fails
- Use background tasks for expensive operations (entity state recalculation)
- Provide user feedback for long-running operations

## Testing Considerations

1. Test scene deletion with:
   - Scenes that have CharacterMemory entries
   - Scenes that have PlotEvent entries
   - Scenes that have NPCMention entries
   - Scenes that affect CharacterState, LocationState, ObjectState
   - Scenes that affect NPCTracking thresholds

2. Test scene modification with:
   - Scenes that have existing extractions
   - Scenes that affect entity states
   - Scenes that affect NPC tracking

3. Verify:
   - No orphaned extraction records
   - Entity states reflect only remaining scenes
   - NPC tracking scores are accurate
   - No stale data in vector database (ChromaDB)

## Performance Considerations

- Entity state recalculation is expensive - consider:
  - Only recalculating if deleted scenes affect state
  - Using background tasks for recalculation
  - Caching intermediate results
  - Batch processing for multiple scenes

- NPC tracking recalculation is moderate cost - acceptable to run synchronously

- CharacterMemory/PlotEvent deletion is fast - can run synchronously

