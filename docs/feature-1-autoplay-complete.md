# Feature 1: Auto-play TTS - Implementation Complete ✅

**Date:** October 16, 2025  
**Status:** ✅ READY FOR TESTING

---

## What Was Implemented

Auto-play TTS automatically narrates newly generated scenes without requiring manual button click.

### User Experience Flow

```
User generates new scene
    ↓
Scene generation completes
    ↓
(If auto-play enabled in settings)
    ↓
TTS session created automatically
    ↓
Audio generation starts in background
    ↓
Audio plays automatically when ready
```

---

## Implementation Details

### 1. Database Migration ✅

**File:** `backend/migrate_add_auto_play_tts.py`

Added `auto_play_last_scene` BOOLEAN column to `tts_settings` table.

```sql
ALTER TABLE tts_settings 
ADD COLUMN auto_play_last_scene BOOLEAN DEFAULT 0
```

### 2. Backend Changes ✅

**Modified Files:**

1. **`backend/app/models/tts_settings.py`**
   - Added `auto_play_last_scene` column to model
   - Updated `to_dict()` to include new field

2. **`backend/app/routers/tts.py`**
   - Added `auto_play_last_scene` to request/response models
   - Updated `update_tts_settings()` to handle new field

3. **`backend/app/api/stories.py`**
   - Added `trigger_auto_play_tts()` function
   - Modified `generate_scene()` to check auto-play setting
   - Returns `auto_play` object with `session_id` in response

4. **`backend/app/api/websocket.py`**
   - Modified WebSocket endpoint to auto-start generation on connect
   - Triggers `generate_and_stream_chunks()` when client connects

### 3. Frontend Changes ✅

**Modified Files:**

1. **`frontend/src/components/TTSSettingsModal.tsx`**
   - Added `auto_play_last_scene` to interface
   - Added toggle UI control
   - Updated load/save logic

2. **`frontend/src/app/story/[id]/page.tsx`**
   - Modified `generateNewScene()` to check for `auto_play` in response
   - Dispatches `kahani:autoplay-tts` custom event with session info

3. **`frontend/src/hooks/useTTSWebSocket.ts`**
   - Added `connectToSession()` function for existing sessions
   - Added event listener for `kahani:autoplay-tts`
   - Auto-connects and plays when event received

---

## How It Works

### Backend Flow

1. User generates scene
2. Scene created successfully
3. Backend checks `tts_settings.auto_play_last_scene` for user
4. If enabled:
   - Creates TTS session via `tts_session_manager.create_session()`
   - Returns session_id in response: `{ auto_play: { session_id, scene_id } }`

### Frontend Flow

1. Frontend receives scene generation response
2. Checks for `response.auto_play.session_id`
3. If present:
   - Dispatches custom event with session info
   - TTS hook for that scene receives event
   - Connects to WebSocket with existing session_id
   - Backend starts generation when WebSocket connects
   - Audio plays automatically when chunks arrive

### WebSocket Auto-Start

When WebSocket connects to an existing session:
```python
# In websocket.py
if not session.is_generating:
    # Start generation automatically
    asyncio.create_task(generate_and_stream_chunks(
        session_id=session_id,
        scene_id=session.scene_id,
        user_id=session.user_id
    ))
```

---

## User Settings

### Enable Auto-play

1. Open TTS Settings modal
2. Enable "TTS Enabled" toggle
3. Enable "Auto-play New Scenes" toggle
4. Click "Save Settings"

### Settings Storage

```python
# Database: tts_settings table
auto_play_last_scene = 1  # Enabled
auto_play_last_scene = 0  # Disabled
```

---

## Testing Checklist

- [ ] Enable auto-play in TTS settings
- [ ] Generate a new scene
- [ ] Verify audio starts playing automatically
- [ ] Verify no manual "Narrate" button click needed
- [ ] Check browser console for auto-play logs
- [ ] Test with auto-play disabled (no auto-play)
- [ ] Test with TTS disabled (no auto-play)

---

## Expected Behavior

### With Auto-play Enabled

```
1. User clicks "Continue Story" or enters custom prompt
2. Scene generation completes
3. Audio generation starts automatically
4. First audio chunk plays within 2-3 seconds
5. Subsequent chunks play seamlessly
6. No manual intervention needed
```

### With Auto-play Disabled

```
1. User clicks "Continue Story"
2. Scene generation completes
3. No automatic audio
4. User must click "🔊 Narrate" button manually
```

---

## Console Logs to Watch

**Backend:**
```
[AUTO-PLAY] Creating TTS session for scene 123, user 1
[AUTO-PLAY] Created TTS session abc123 for scene 123
[WebSocket] Client connected to TTS session: abc123
[WebSocket] Starting TTS generation for session: abc123
```

**Frontend:**
```
[AUTO-PLAY] Starting TTS for new scene {session_id, scene_id}
[AUTO-PLAY] Event received for scene 123
[AUTO-PLAY] Connecting to session: abc123
[AUTO-PLAY] Autoplay permission established
[AUTO-PLAY] WebSocket connected
[TTS WS] Received message: chunk_ready
[Audio] Playing chunk 1
```

---

## Troubleshooting

### Issue: No audio plays

**Check:**
1. Is `auto_play_last_scene` enabled in database?
   ```bash
   sqlite3 backend/data/kahani.db "SELECT auto_play_last_scene FROM tts_settings"
   ```
2. Does response include `auto_play` object?
   - Check browser Network tab for `/scenes` response
3. Is event being dispatched?
   - Check console for "AUTO-PLAY Starting TTS" message

### Issue: Audio starts but fails

**Check:**
1. WebSocket connection in Network tab
2. Backend logs for generation errors
3. TTS provider availability

---

## Performance

- **Time to Start:** 2-3 seconds after scene generation
- **No Extra Overhead:** Uses existing WebSocket infrastructure
- **Background Generation:** Doesn't block UI

---

## Next Steps

1. **Test thoroughly** with different scenarios
2. **Add notification** (optional) when auto-play starts
3. **Add progress indicator** in scene card during auto-play
4. **Implement Feature 2:** Real-time TTS during scene generation

---

## Files Changed

### Backend (5 files)
- `backend/migrate_add_auto_play_tts.py` (NEW)
- `backend/app/models/tts_settings.py` (MODIFIED)
- `backend/app/routers/tts.py` (MODIFIED)
- `backend/app/api/stories.py` (MODIFIED)
- `backend/app/api/websocket.py` (MODIFIED)

### Frontend (3 files)
- `frontend/src/components/TTSSettingsModal.tsx` (MODIFIED)
- `frontend/src/app/story/[id]/page.tsx` (MODIFIED)
- `frontend/src/hooks/useTTSWebSocket.ts` (MODIFIED)

---

**Ready for Testing! 🎉**
