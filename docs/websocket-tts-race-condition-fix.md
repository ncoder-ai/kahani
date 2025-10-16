# WebSocket TTS Fix - Race Condition

## Problem Identified

When user clicked "Narrate":

1. ✅ Frontend calls `POST /api/tts/generate-ws/{scene_id}`
2. ✅ Backend creates session
3. ❌ Backend **immediately** starts background task `generate_and_stream_chunks`
4. ❌ Background task tries to send messages via WebSocket **that doesn't exist yet**
5. ⏰ Frontend receives response and connects to WebSocket
6. ⏰ WebSocket finally attaches to session

**Result:** All messages sent before WebSocket connected = lost messages!

## Solution Applied

Added wait logic in `generate_and_stream_chunks`:

```python
# Wait for WebSocket to connect (up to 10 seconds)
logger.info(f"Waiting for WebSocket connection for session {session_id}")
for i in range(20):  # 20 attempts × 0.5s = 10 seconds max
    session = tts_session_manager.get_session(session_id)
    if session and session.websocket:
        logger.info(f"WebSocket connected for session {session_id}")
        break
    await asyncio.sleep(0.5)
else:
    logger.error(f"WebSocket never connected for session {session_id}")
    return

# Now proceed with generation...
```

## What Changed

**File:** `backend/app/routers/tts.py`

**Function:** `generate_and_stream_chunks()`

**Change:** Added WebSocket connection wait loop before attempting to send any messages

## Testing Steps

1. Restart backend server (Ctrl+C and restart `./start-dev.sh`)
2. Refresh frontend
3. Click "🔊 Narrate" button
4. Watch backend logs for:
   ```
   Waiting for WebSocket connection for session abc123
   WebSocket connected for session abc123
   Generating 5 chunks for session abc123
   Sent chunk 1/5 for session abc123
   ```

5. Watch browser console for:
   ```
   [TTS WS] Connected
   [TTS WS] Chunk ready: 1/5
   [Audio] Playing chunk 1
   ```

## Expected Behavior

- ✅ WebSocket connects first
- ✅ Background task waits for connection
- ✅ Messages sent after WebSocket ready
- ✅ Audio chunks received and played

## If Still Not Working

Check:
1. Backend logs for "WebSocket connected" message
2. Browser console for chunk messages
3. TTS provider logs for generation requests
4. User TTS settings are enabled
