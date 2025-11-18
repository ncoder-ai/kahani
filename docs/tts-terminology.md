# TTS Terminology Reference

## Clear Definitions

This document clarifies the difference between **Progressive Playback** and **Streaming** in our TTS implementation.

---

## 🎯 Progressive Playback (Client-Side Chunking)

### What It Is
Text is **split into chunks** on our backend, each chunk is sent to the TTS provider **separately**, and audio plays as each chunk completes.

### Why We Do It
- ⚡ **Faster time-to-first-audio** - User hears narration sooner
- 🎵 **Seamless playback** - Next chunk plays as current finishes
- 📊 **Better UX** - Progress indication, don't wait for entire scene

### How It Works
```
Scene Text (2000 chars)
    ↓
Split into chunks (chunk_size = 280)
    ↓
Chunk 1 (280 chars) → TTS Provider → Audio 1 → Play ▶️
Chunk 2 (280 chars) → TTS Provider → Audio 2 → Play ▶️  
Chunk 3 (280 chars) → TTS Provider → Audio 3 → Play ▶️
...
Chunk 7 (160 chars) → TTS Provider → Audio 7 → Play ▶️
```

### Settings Control
- **Field:** `chunk_size`
- **Range:** 100-500 characters
- **Impact:**
  - 100 chars = ~1 sentence = Faster start, more API calls
  - 280 chars = ~1-2 sentences = Balanced (default)
  - 500 chars = ~1 paragraph = Slower start, fewer API calls

### Current Status
✅ **IMPLEMENTED** - Our backend already does this via `TextChunker` and `TTSService._generate_chunked_audio()`

### Code Location
- Backend: `backend/app/services/tts/tts_service.py`
- Text chunking: `backend/app/services/tts/text_chunker.py`

---

## 🌊 Streaming (Provider-Side Feature)

### What It Is
The TTS provider **streams audio bytes** in real-time as it generates them (SSE/WebSocket), before synthesis is complete.

### Why We Want It
- ⚡⚡ **Even faster start** - Audio plays during synthesis
- 🎵 **Single request** - No need to chunk on our side
- 🔄 **Real-time** - Bytes arrive as they're generated

### How It Would Work
```
Send Full Text (2000 chars) → TTS Provider
                                   ↓
                         Starts generating audio
                                   ↓
                         Bytes stream back via SSE/WebSocket
                                   ↓
                         Play bytes as they arrive ▶️
                                   ↓
                         Continue playing while generating...
```

### Provider Support
Different providers have different streaming capabilities:

| Provider | Streaming Support | API Type |
|----------|------------------|----------|
| OpenAI TTS | ✅ Yes | Chunked transfer |
| ElevenLabs | ✅ Yes | WebSocket |
| Chatterbox | ❓ Unknown | Check docs |
| Kokoro | ❓ Unknown | Check docs |

### Settings Control
- **Field:** `stream_audio` (reserved)
- **Current:** Toggle exists in UI but not functional
- **Purpose:** Enable streaming when we implement provider-specific handlers

### Current Status
❌ **NOT YET IMPLEMENTED** - Future enhancement requiring:
1. Provider-specific streaming handlers
2. SSE/WebSocket client implementation
3. Audio chunk buffering/playback logic

### Code Location (Future)
- Backend: Will add to provider implementations
- Frontend: Will add to audio playback component

---

## 📊 Comparison Table

| Aspect | Progressive Playback | Streaming |
|--------|---------------------|-----------|
| **Where** | Our backend chunks | Provider streams |
| **How** | Multiple API calls | Single streaming call |
| **Speed** | Fast | Faster |
| **Control** | We control chunk size | Provider controls |
| **Status** | ✅ Implemented | ❌ Future |
| **Setting** | `chunk_size` | `stream_audio` |
| **Complexity** | Medium | High |

---

## 🎨 Visual Comparison

### Progressive Playback (Current)
```
Backend                    TTS Provider              Frontend
  |                             |                        |
  |-- Chunk 1 (280 chars) ---->|                        |
  |                             |<---- Audio 1 --------->| ▶️ Play
  |-- Chunk 2 (280 chars) ---->|                        |
  |                             |<---- Audio 2 --------->| ▶️ Play
  |-- Chunk 3 (280 chars) ---->|                        |
  |                             |<---- Audio 3 --------->| ▶️ Play
  
  Time to First Audio: ~1-2 seconds (one chunk processing)
  Total Time: Sum of all chunks
```

### Streaming (Future)
```
Backend                    TTS Provider              Frontend
  |                             |                        |
  |---- Full Text (2000) ------>|                        |
  |                             |-- bytes chunk 1 ------>| ▶️ Start
  |                             |-- bytes chunk 2 ------>| ▶️ Playing
  |                             |-- bytes chunk 3 ------>| ▶️ Playing
  |                             |-- bytes chunk 4 ------>| ▶️ Playing
  |                             |-- bytes chunk N ------>| ▶️ Playing
  
  Time to First Audio: ~0.5-1 second (instant streaming)
  Total Time: Similar to full generation
```

---

## 🔧 Implementation Status

### ✅ What We Have (Progressive Playback)
```python
# backend/app/services/tts/tts_service.py
async def _generate_chunked_audio(self, text: str, ...):
    """Split text into chunks and generate audio for each"""
    chunker = TextChunker(max_chunk_size=max_length)
    chunks = chunker.chunk_text(text)
    
    for chunk in chunks:
        response = await provider.synthesize(chunk)
        audio_chunks.append(response.audio_data)
    
    return audio_chunks
```

### ❌ What We Don't Have (Streaming)
```python
# Future implementation idea
async def stream_scene_audio_realtime(self, scene: Scene, ...):
    """Stream audio bytes from provider in real-time"""
    async with provider.synthesize_stream(scene.content) as stream:
        async for audio_bytes in stream:
            yield audio_bytes  # Send to frontend immediately
```

---

## 🎯 User Settings

### UI in TTSSettingsModal

**Current Implementation:**
```tsx
{/* Chunk Size - Controls Progressive Playback */}
<div className="space-y-2">
  <label>TTS Chunk Size: {chunk_size} characters</label>
  <input 
    type="range" 
    min="100" 
    max="500" 
    value={chunk_size}
  />
  <p className="text-xs text-gray-500">
    <strong>Progressive Playback:</strong> Smaller chunks = faster audio start.
    Text is split into chunks, each processed separately for quicker playback.
  </p>
</div>
```

**Reserved for Future:**
```tsx
{/* Stream Audio - Will enable provider streaming */}
<div>
  <label>Stream Audio (Coming Soon)</label>
  <Toggle value={stream_audio} disabled />
  <p className="text-xs text-gray-500">
    Future: Use provider streaming capabilities for instant playback
  </p>
</div>
```

---

## 💡 When to Use What

### Use Progressive Playback (Current) When:
- ✅ Scene text is long (>500 chars)
- ✅ Want faster time-to-first-audio
- ✅ Provider doesn't support streaming
- ✅ Need fine control over chunk boundaries

### Use Streaming (Future) When:
- ⏳ Provider supports SSE/WebSocket streaming
- ⏳ Want absolute fastest start
- ⏳ Can handle real-time audio buffering
- ⏳ Want simplest backend logic (no chunking)

### Use Neither (Complete Generation) When:
- Short text (<100 chars)
- User prefers complete audio before playback
- Testing/debugging
- Network is unreliable

---

## 📝 Code Comments

We've updated code comments to reflect correct terminology:

**Backend Model:**
```python
# backend/app/models/tts_settings.py
chunk_size = Column(Integer, default=280)  
# Progressive playback: chunk size for faster audio start

stream_audio = Column(Boolean, default=True)  
# Future: Use provider streaming capabilities (SSE)
```

**API Documentation:**
```python
# backend/app/routers/tts.py
chunk_size: Optional[int] = Field(
    280, ge=100, le=500,
    description="Progressive playback: Text chunk size (smaller = faster start)"
)

stream_audio: Optional[bool] = Field(
    True,
    description="Future: Use provider streaming (SSE) when available"
)
```

---

## 🎓 Summary

**Remember:**
- **Progressive Playback** = We chunk → Multiple calls → Fast start ✅
- **Streaming** = Provider streams → Single call → Faster start ❌ (future)

Both aim to reduce time-to-first-audio, but use different approaches!
