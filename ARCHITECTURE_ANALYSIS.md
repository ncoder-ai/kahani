# TTS Auto-Play Architecture Analysis

## Current Problems

### 1. **Duplicate TTS Trigger Logic**
- `trigger_auto_play_tts()` in stories.py (variant regeneration)
- Inline auto-play code in `generate_scene_streaming_endpoint()` (new scenes)
- **Result**: Two code paths that need to be kept in sync

### 2. **Inconsistent Event Sending**
- Variant creation: Sends `auto_play_ready` event in `create_scene_variant_streaming()`
- New scene: Sends `auto_play_ready` event in `generate_scene_streaming_endpoint()`
- **Result**: Fixes in one place don't apply to the other

### 3. **Complex Frontend Handling**
- Different callbacks for different generation types
- `generateSceneStreaming()` vs `createSceneVariantStreaming()`
- Each has different parameter signatures and event handling
- **Result**: Brittle, hard to maintain

### 4. **Race Conditions**
- Multiple places that can start TTS generation
- `trigger_auto_play_tts()` + WebSocket endpoint both try to start generation
- Complex `is_generating` flag management
- **Result**: Duplicate generation, chunks playing multiple times

## Root Cause

The system treats "new scene" and "variant regeneration" as completely separate operations, even though they're functionally identical from a TTS perspective:
1. Scene content is generated/exists
2. Check if auto-play is enabled
3. Create TTS session
4. Start generating audio
5. Send `auto_play_ready` event
6. Frontend connects and plays

## Proposed Solution

### Backend: Single Unified Auto-Play Function

```python
async def setup_auto_play_if_enabled(
    scene_id: int,
    user_id: int,
    send_event_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Unified auto-play setup for ANY scene operation.
    
    Args:
        scene_id: The scene to setup TTS for
        user_id: The user requesting auto-play
        send_event_callback: Optional callback to send SSE event immediately
        
    Returns:
        session_id if auto-play was setup, None otherwise
    """
    # Check if enabled
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == user_id
    ).first()
    
    if not (tts_settings and tts_settings.tts_enabled and tts_settings.auto_play_last_scene):
        return None
    
    # Create session
    session_id = tts_session_manager.create_session(
        scene_id=scene_id,
        user_id=user_id,
        auto_play=True
    )
    
    # Start generation immediately
    asyncio.create_task(generate_and_stream_chunks(
        session_id=session_id,
        scene_id=scene_id,
        user_id=user_id
    ))
    
    # Send event if callback provided (for streaming endpoints)
    if send_event_callback:
        event = {
            'type': 'auto_play_ready',
            'auto_play_session_id': session_id,
            'scene_id': scene_id
        }
        send_event_callback(event)
    
    return session_id
```

### Usage:

**For Streaming Endpoints (new scene, variant):**
```python
async def some_streaming_endpoint():
    # ... scene generation ...
    
    # Inline event sender
    async def send_event(event):
        yield f"data: {json.dumps(event)}\n\n"
    
    session_id = await setup_auto_play_if_enabled(
        scene_id=scene.id,
        user_id=current_user.id,
        send_event_callback=send_event
    )
    
    # Include in completion event
    if session_id:
        completion_data['auto_play_session_id'] = session_id
```

**For Non-Streaming Endpoints:**
```python
async def some_regular_endpoint():
    # ... scene generation ...
    
    session_id = await setup_auto_play_if_enabled(
        scene_id=scene.id,
        user_id=current_user.id
    )
    
    # Include in response
    if session_id:
        response['auto_play_session_id'] = session_id
```

### Frontend: Single Unified Handler

```typescript
// Single callback for ANY streaming operation
interface StreamingCallbacks {
  onChunk?: (chunk: string) => void;
  onComplete?: (data: any) => void;
  onError?: (error: string) => void;
  onAutoPlayReady?: (sessionId: string) => void; // SAME for all
}

// Parse SSE events uniformly
const parsed = JSON.parse(data);
if (parsed.type === 'content' && onChunk) {
  onChunk(parsed.chunk);
} else if (parsed.type === 'auto_play_ready' && onAutoPlayReady) {
  // SAME handling for new scene AND variant
  onAutoPlayReady(parsed.auto_play_session_id);
} else if (parsed.type === 'complete' && onComplete) {
  onComplete(parsed);
}
```

## Benefits

1. ✅ **Single Source of Truth**: One function for all auto-play logic
2. ✅ **Consistent Behavior**: Fix once, works everywhere
3. ✅ **Less Code**: Remove ~100 lines of duplicate logic
4. ✅ **Easier Testing**: Test one function instead of multiple paths
5. ✅ **Fewer Bugs**: No more "works for X but breaks Y"

## Migration Steps

1. Create `setup_auto_play_if_enabled()` in stories.py
2. Replace all auto-play code in new scene endpoint
3. Replace all auto-play code in variant endpoint
4. Remove `trigger_auto_play_tts()` function
5. Test both new scene and variant generation
6. Remove debug logging once stable

## Estimated Impact

- **Lines Removed**: ~150
- **Lines Added**: ~50
- **Net Reduction**: ~100 lines
- **Complexity**: Significantly reduced
- **Maintainability**: Much improved
