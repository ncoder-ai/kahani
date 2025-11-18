# TTS Global Settings Documentation

## Overview

The TTS Settings Modal now includes global behavior settings that control how TTS works across your entire story experience. These settings are located at the top of the modal in a purple-highlighted section.

## Important Terminology

**Progressive Narration vs. Auto-Narration:**
- **Progressive Narration** (CURRENT FEATURE): When you click the narrate button, should we split the scene into chunks (sentences/paragraphs) for faster audio start, or send the entire scene at once?
- **Auto-Narrate New Scenes** (FUTURE FEATURE): Automatically start TTS generation when a new scene is created, without user clicking the narrate button. Not implemented yet.

## Global Settings

### 1. Enable Text-to-Speech (Master Switch)
- **Type**: Toggle (On/Off)
- **Default**: On
- **Description**: Master control for the entire TTS feature
- **Effect**:
  - When OFF: TTS is completely disabled, no audio controls shown
  - When ON: TTS features are available

**Use Cases:**
- Disable TTS if you prefer reading without audio
- Temporarily turn off TTS to save API calls/bandwidth
- Disable during content creation, enable for final review

### 2. Progressive Narration
- **Type**: Toggle (On/Off)
- **Default**: Off
- **Description**: When you press the narrate button, split the scene text into chunks for progressive playback
- **Effect**:
  - When OFF: Entire scene text is sent to TTS as one piece
  - When ON: Scene is split into chunks based on chunk_size setting
  - Only applies when user clicks narrate button (not automatic)

**How It Works:**
- Scene text is split on backend using TextChunker
- Each chunk is processed by TTS separately
- Audio chunks are played sequentially
- Provides faster time-to-first-audio (user hears something sooner)

**Benefits:**
- ✅ **Faster Start**: User hears audio sooner (first chunk plays while others generate)
- ✅ **Better UX**: No long wait for full scene audio
- ✅ **Progress Feedback**: Can show generation progress per chunk

**Trade-offs:**
- ⚠️ **More API Calls**: Each chunk = separate TTS request
- ⚠️ **Potential Gaps**: Brief pauses between chunks (usually imperceptible)

**When to Use:**
- Enable for long scenes where users would wait too long for audio
- Disable for short scenes or if your provider has slow cold-start time
- Consider API costs - more chunks = more requests

### 3. Chunk Size (When Progressive Narration is ON)
- **Type**: Slider
- **Range**: 100 - 500 characters
- **Default**: 280 characters
- **Description**: Size of each text chunk when progressive narration is enabled
- **Only visible/active when Progressive Narration is ON**

**Presets:**
- **100 characters**: Sentence-level chunks
  - Very fast audio start
  - More API calls
  - Good for: Real-time narration feel, impatient users
  
- **280 characters**: Balanced (Default)
  - Good compromise between speed and efficiency
  - ~1-2 sentences per chunk
  - Good for: Most use cases
  
- **500 characters**: Paragraph-level chunks
  - Slower audio start
  - Fewer API calls
  - Good for: Cost optimization, smooth provider execution

**Factors to Consider:**
- **Provider Speed**: Fast providers can handle smaller chunks efficiently
- **Network Latency**: High latency = larger chunks better (fewer round trips)
- **API Costs**: Pay per request? Use larger chunks
- **User Patience**: Impatient users? Use smaller chunks

## Settings Interaction

### Enable TTS = OFF
- All other TTS controls are disabled
- No audio controls shown in story UI
- No TTS API calls made

### Enable TTS = ON, Progressive Narration = OFF
- User can click narrate button on scenes
- Entire scene text sent to TTS at once
- chunk_size setting is hidden (not applicable)
- One API call per scene narration

### Enable TTS = ON, Progressive Narration = ON
- User can click narrate button on scenes
- Scene text split into chunks based on chunk_size
- Each chunk generates separate TTS audio
- Audio chunks play sequentially
- chunk_size slider becomes visible
- Multiple API calls per scene narration

## Backend Implementation

### Database Fields
```python
class TTSSettings:
    tts_enabled = Column(Boolean, default=False)           # Master switch
    progressive_narration = Column(Boolean, default=False) # Enable chunking
    chunk_size = Column(Integer, default=280)              # Chunk size (100-500)
```

### API Endpoints

**GET /api/tts/settings**
```json
{
  "tts_enabled": true,
  "progressive_narration": true,
  "chunk_size": 280
}
```

**PUT /api/tts/settings**
```json
{
  "tts_enabled": true,
  "progressive_narration": true,
  "chunk_size": 280
}
```

### Audio Generation Logic
```python
# When progressive_narration is True:
if settings.progressive_narration:
    chunks = TextChunker.split_text(scene_text, settings.chunk_size)
    audio_files = [generate_tts(chunk) for chunk in chunks]
    return concatenate_audio(audio_files)
else:
    # Generate full scene at once
    return generate_tts(scene_text)
```

## Frontend Implementation

### Settings State
```typescript
interface TTSSettings {
  tts_enabled: boolean;
  progressive_narration: boolean;
  chunk_size: number;  // 100-500
}
```

### Conditional UI
- chunk_size slider only shown when progressive_narration = true
- All settings disabled when tts_enabled = false

## Usage Scenarios

### Scenario 1: Fast, Responsive Narration
```
Enable TTS: ON
Progressive Narration: ON
Chunk Size: 100 (Sentence)
```
**Result:** Near-instant audio feedback, user hears first sentence within ~500ms
**Trade-off:** More API calls, higher costs if provider charges per request

### Scenario 2: Cost-Optimized Narration
```
Enable TTS: ON
Progressive Narration: ON
Chunk Size: 500 (Paragraph)
```
**Result:** Fewer API calls, lower cost, but slower audio start (1-2s)

### Scenario 3: Single-Shot Narration
```
Enable TTS: ON
Progressive Narration: OFF
```
**Result:** One API call per scene, simplest approach, but longest wait time (3-5s+ for long scenes)

### Scenario 4: No Audio
```
Enable TTS: OFF
```
**Result:** No TTS features available, reading-only mode

## Testing Checklist

- [ ] Toggle Enable TTS on/off
- [ ] Verify all TTS controls disabled when TTS off
- [ ] Toggle Progressive Narration on/off
- [ ] Verify chunk_size slider appears/disappears with Progressive Narration
- [ ] Adjust chunk_size and verify it saves
- [ ] Test narration with Progressive ON vs OFF
- [ ] Verify chunked audio plays smoothly
- [ ] Check that settings persist across sessions
- [ ] Test with different providers
- [ ] Measure time-to-first-audio with different chunk sizes

## Integration with Phase 3 (Scene Audio Controls)

When implementing Scene Audio Controls, respect these settings:

1. **Check tts_enabled**: Don't show audio controls if TTS is disabled
2. **Use progressive_narration**: Pass to backend to control chunking
3. **Apply chunk_size**: Use user's preferred chunk size
4. **Show loading state**: Display per-chunk progress if progressive is ON

## Future: Auto-Narrate New Scenes

**Not implemented yet** - This will be a separate feature (Phase 4) that automatically triggers TTS generation when a scene is created, without the user clicking narrate. It will work in conjunction with progressive narration:

```
Future Feature Combinations:

Auto-Narrate: ON + Progressive Narration: ON
→ New scenes automatically split into chunks and generate audio in background
→ Audio starts playing as soon as first chunk is ready

Auto-Narrate: ON + Progressive Narration: OFF
→ New scenes automatically generate full audio in background
→ Audio starts playing when complete scene audio is ready

Auto-Narrate: OFF + Progressive Narration: ON/OFF
→ Current behavior - user clicks narrate button
```

## Migration Notes

**Database Column Renamed:**
- OLD: `auto_narrate_new_scenes` (was misleading)
- NEW: `progressive_narration` (accurate description)

A migration script has been run to rename the column: `migrate_rename_to_progressive_narration.py`
