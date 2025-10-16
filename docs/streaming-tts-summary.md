# Streaming TTS - Implementation Summary

## Overview
Two features to enhance TTS experience in Kahani:

1. **Auto-play Complete Scenes** (Simple) - Auto-narrate after scene generation completes
2. **Real-time Streaming TTS** (Advanced) - Narrate while scene is being generated

---

## Feature 1: Auto-play Complete Scenes ⭐ RECOMMENDED FIRST

### What It Does
When scene generation completes → Automatically generate TTS → Auto-play audio

### Why This First?
✅ **Quick to implement** (2-3 days)  
✅ **Uses existing infrastructure** (chunking, TTS service)  
✅ **Works with all TTS providers**  
✅ **Low risk**, high value  
✅ **Clean separation of concerns**  

### How It Works
```
User generates scene
    ↓
Scene complete → saved to DB
    ↓
Background task: Generate TTS chunks
    ↓
WebSocket notification: "TTS ready"
    ↓
Frontend auto-plays audio
```

### Key Components

**Backend**:
- New field: `TTSSettings.auto_play_last_scene`
- Background task in `generate_scene()` endpoint
- WebSocket notification on TTS ready

**Frontend**:
- WebSocket listener for "tts_ready" event
- Auto-trigger existing `useTTS()` hook
- Toggle in TTSSettingsModal

### Code Changes
1. Migration: Add `auto_play_last_scene` column
2. `stories.py`: Add background task after scene creation
3. `websocket.py`: Send notification when TTS ready
4. `TTSSettingsModal.tsx`: Add toggle
5. `Story.tsx`: WebSocket listener + auto-play

---

## Feature 2: Real-time Streaming TTS 🚀 ADVANCED

### What It Does
Stream audio **WHILE** scene is being generated (synchronized LLM + TTS)

### Why This Is Advanced?
⚠️ **Complex** (1-2 weeks)  
⚠️ **New WebSocket architecture**  
⚠️ **Requires streaming TTS provider** (Chatterbox)  
⚠️ **Sophisticated error handling**  
✅ **Revolutionary UX** - hear narration immediately  
✅ **Competitive advantage**  

### How It Works
```
User clicks "Generate with TTS"
    ↓
WebSocket connection established
    ↓
┌─────────────────────────────────┐
│  LLM streams tokens             │
│    ↓                            │
│  Buffer until sentence complete │
│    ↓                            │
│  TTS streams audio              │
│    ↓                            │
│  WebSocket sends audio chunk    │
│    ↓                            │
│  Frontend plays immediately     │
└─────────────────────────────────┘
    ↓
Next sentence → repeat
```

### Key Innovation: Sentence Boundary Detection
```python
LLM: "The hero entered" → Buffer
LLM: " the dark" → Buffer  
LLM: " castle." → Sentence complete! → Send to TTS
TTS: [audio] → Send to frontend → Play
LLM: " She looked" → Start new buffer...
```

### Key Components

**Backend**:
- New endpoint: `/scenes/generate-with-tts-stream`
- WebSocket endpoint: `/ws/scene-generation/{session_id}`
- Streaming pipeline: LLM → Buffer → TTS → Audio
- Sentence boundary detector
- Session manager

**Frontend**:
- New hook: `useStreamingTTS()`
- Audio queue manager
- Real-time text display
- WebSocket client

### Technical Challenges

1. **Synchronization**: LLM fast, TTS slower
   - Solution: Audio queue with sequential playback

2. **Sentence Detection**: When to trigger TTS?
   - Solution: Regex for `.!?` followed by space

3. **Error Recovery**: What if TTS fails mid-stream?
   - Solution: Skip failed sentence, continue stream

4. **Network**: High data volume
   - Solution: MP3 compression, Base64 encoding

---

## Comparison

| Aspect | Feature 1: Auto-play | Feature 2: Streaming |
|--------|---------------------|---------------------|
| **Implementation** | 2-3 days | 1-2 weeks |
| **Complexity** | Low | High |
| **Risk** | Low | Medium |
| **TTS Providers** | Any | Streaming only |
| **User Experience** | Good (2-5s delay) | Excellent (instant) |
| **Network Usage** | Moderate | High |
| **Error Handling** | Simple | Complex |
| **Dependencies** | Existing code | New WebSocket infra |

---

## Recommendation: Phased Approach

### Phase 1: Auto-play (Week 1) ⭐
Implement Feature 1 first because:
- ✅ Quick win for users
- ✅ Validates TTS workflow
- ✅ Tests WebSocket infrastructure
- ✅ Provides immediate value
- ✅ Low risk to production

### Phase 2: Real-time Streaming (Weeks 2-3) 🚀
Build Feature 2 after Feature 1 stabilizes:
- ✅ Can reuse WebSocket code from Feature 1
- ✅ Users already familiar with auto-play
- ✅ Clear upgrade path
- ✅ Time to test Chatterbox streaming
- ✅ Can iterate based on Feature 1 feedback

---

## User Settings

Both features controlled via TTS Settings Modal:

```
┌─────────────────────────────────────────┐
│ TTS Global Settings                     │
├─────────────────────────────────────────┤
│                                         │
│ [✓] Enable Text-to-Speech              │
│                                         │
│ [✓] Auto-play Last Scene       ← NEW   │
│     Start narration automatically       │
│     after scene generation completes    │
│                                         │
│ [ ] Real-time TTS (Experimental) ← NEW │
│     Hear narration while scene is       │
│     being written (requires Chatterbox) │
│                                         │
│ [✓] Progressive Narration               │
│     Chunk Size: 280 characters          │
│                                         │
└─────────────────────────────────────────┘
```

---

## Database Schema

### Feature 1
```python
# Add to TTSSettings model
auto_play_last_scene = Column(Boolean, default=False)
```

### Feature 2
```python
# Add to TTSSettings model
realtime_tts_enabled = Column(Boolean, default=False)
min_sentence_length = Column(Integer, default=20)
```

Migration:
```sql
ALTER TABLE tts_settings 
ADD COLUMN auto_play_last_scene BOOLEAN DEFAULT FALSE;

ALTER TABLE tts_settings 
ADD COLUMN realtime_tts_enabled BOOLEAN DEFAULT FALSE;

ALTER TABLE tts_settings 
ADD COLUMN min_sentence_length INTEGER DEFAULT 20;
```

---

## API Endpoints

### Feature 1 (Uses Existing)
- `POST /api/stories/{story_id}/scenes` - Add background task
- `ws://localhost:9876/ws/{user_id}` - Existing WebSocket

### Feature 2 (New)
- `POST /api/stories/{story_id}/scenes/generate-with-tts-stream` - Initialize
- `ws://localhost:9876/ws/scene-generation/{session_id}` - Stream data

---

## Testing Strategy

### Feature 1 Tests
```
✓ Enable auto-play setting
✓ Generate scene → Verify auto-play starts
✓ TTS disabled → No auto-play
✓ TTS generation fails → Graceful fallback
✓ Multiple scenes in sequence
✓ WebSocket reconnection
```

### Feature 2 Tests
```
✓ Text streams progressively
✓ Audio plays as sentences complete
✓ Sentence boundary detection (various punctuation)
✓ Audio queue manages fast LLM / slow TTS
✓ Stop generation mid-stream
✓ WebSocket disconnect/reconnect
✓ TTS fails for one sentence → Continue
✓ Concurrent users don't interfere
```

---

## Success Criteria

### Feature 1
- [ ] Users can toggle auto-play in settings
- [ ] New scenes auto-narrate when setting enabled
- [ ] Works with all TTS providers
- [ ] <5 second delay after scene complete
- [ ] Graceful handling when TTS unavailable

### Feature 2
- [ ] Users can enable real-time TTS
- [ ] First audio plays within 3-5 seconds
- [ ] Text and audio stay synchronized
- [ ] Smooth playback (no gaps/overlaps)
- [ ] Works reliably with Chatterbox
- [ ] Proper error recovery

---

## Next Actions

### To Start Feature 1:
1. Create migration for `auto_play_last_scene`
2. Modify `generate_scene()` endpoint
3. Add WebSocket notification
4. Update TTSSettingsModal
5. Add WebSocket listener to Story component
6. Test end-to-end

### To Start Feature 2:
1. Design WebSocket protocol (message types)
2. Implement streaming session manager
3. Build sentence buffer with boundary detection
4. Create WebSocket endpoint for streaming
5. Build `useStreamingTTS()` hook
6. Add UI for real-time generation
7. Extensive testing

---

## Questions Needing Decisions

1. **Priority**: Start with Feature 1 or jump to Feature 2?
   - **Recommendation**: Feature 1 first

2. **Provider Compatibility**: Should Feature 2 fallback to Feature 1 if provider doesn't support streaming?
   - **Recommendation**: Yes, show warning + use regular generation

3. **User Control**: For Feature 2, allow pause/skip sentence during playback?
   - **Recommendation**: Add in Phase 2.1 (after initial release)

4. **Buffer Size**: Min characters before triggering TTS in Feature 2?
   - **Recommendation**: Start with 20 chars, make configurable

5. **Error Display**: How to show TTS errors during streaming?
   - **Recommendation**: Small toast notification, continue generation

---

## File Structure

New/Modified files for both features:

```
backend/
  app/
    api/
      stories.py                     # Add background task (F1)
      websocket.py                   # Add streaming endpoint (F2)
    services/
      tts/
        streaming_buffer.py          # NEW: Sentence buffer (F2)
        streaming_session.py         # NEW: Session manager (F2)
  migrations/
    add_auto_play_setting.py         # NEW: F1 migration
    add_realtime_tts_settings.py     # NEW: F2 migration

frontend/
  src/
    hooks/
      useStreamingTTS.ts             # NEW: Streaming hook (F2)
    components/
      TTSSettingsModal.tsx           # Update: Add toggles
      Story.tsx                      # Update: WebSocket listeners

docs/
  streaming-tts-architecture.md      # THIS FILE (detailed)
  streaming-tts-summary.md           # CURRENT FILE (overview)
```

---

## Timeline Estimate

### Feature 1: Auto-play Complete Scenes
- **Day 1**: Backend (migration, background task, WebSocket)
- **Day 2**: Frontend (settings UI, WebSocket listener, auto-play)
- **Day 3**: Testing, bug fixes, documentation

**Total: 3 days**

### Feature 2: Real-time Streaming TTS  
- **Week 1**: Backend infrastructure
  - Days 1-2: WebSocket endpoint, session manager
  - Days 3-4: Streaming pipeline, sentence buffer
  - Day 5: Testing, refinement
  
- **Week 2**: Frontend + Integration
  - Days 1-2: `useStreamingTTS()` hook, audio queue
  - Days 3-4: UI integration, status indicators
  - Day 5: End-to-end testing
  
- **Week 3**: Polish + Production
  - Days 1-2: Error handling, edge cases
  - Days 3-4: Performance optimization
  - Day 5: Documentation, deployment

**Total: 2-3 weeks**

---

## Ready to Proceed?

I'm ready to start implementing either feature. Just let me know:

1. Which feature should we build first?
2. Any modifications to the proposed architecture?
3. Any specific requirements or constraints?

Let's build something amazing! 🎙️✨
