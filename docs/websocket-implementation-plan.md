# WebSocket TTS Implementation Plan

## Phase 1: Backend WebSocket Infrastructure ✅

### 1.1 Session Manager
- [x] Create `TTSSessionManager` class
- [x] Handle session lifecycle
- [x] Track WebSocket connections

### 1.2 WebSocket Endpoint
- [x] Add `/ws/tts/{session_id}` endpoint
- [x] Handle connection/disconnection
- [x] Message routing

### 1.3 Streaming Generation
- [x] Modify TTS service to stream chunks
- [x] Send chunks via WebSocket as generated
- [x] Progress notifications

## Phase 2: Backend Integration ✅

### 2.1 Update Generate Endpoint
- [x] Create session instead of blocking
- [x] Return session_id
- [x] Trigger background generation

### 2.2 Background Task
- [x] Generate chunks asynchronously
- [x] Push to WebSocket
- [x] Error handling

## Phase 3: Frontend WebSocket Hook ✅

### 3.1 Create useTTSWebSocket Hook
- [x] WebSocket connection management
- [x] Message handling
- [x] Audio queue management
- [x] Automatic playback

### 3.2 Replace Polling Logic
- [x] Remove retry logic
- [x] Event-driven architecture
- [x] Error handling

## Phase 4: UI Integration ✅

### 4.1 Update SceneCard Component
- [x] Replace useTTS with useTTSWebSocket
- [x] Update UI feedback
- [x] Progress indicators

### 4.2 Testing
- [x] Manual TTS generation
- [x] Error scenarios
- [x] Connection issues

## Phase 5: Cleanup (Future)

### 5.1 Remove Old Code
- [ ] Delete useTTS hook (with polling)
- [ ] Remove REST chunk endpoint
- [ ] Clean up backend polling support

### 5.2 Documentation
- [x] Update API docs
- [x] Frontend integration guide
- [x] Migration notes

---

## Implementation Order

### Day 1: Backend Foundation
1. ✅ Create session manager
2. ✅ Add WebSocket endpoint
3. ✅ Implement streaming generation

### Day 2: Frontend Hook
4. ✅ Create useTTSWebSocket
5. ✅ Audio queue management
6. ✅ Testing

### Day 3: Integration & Polish
7. ✅ Update UI components
8. ✅ Error handling
9. ✅ Testing & refinement

---

## File Changes Required

### Backend
- [x] `backend/app/api/websocket.py` (NEW)
- [x] `backend/app/services/tts_session_manager.py` (NEW)
- [x] `backend/app/routers/tts.py` (MODIFY)
- [x] `backend/app/main.py` (MODIFY - add WebSocket route)

### Frontend
- [x] `frontend/src/hooks/useTTSWebSocket.ts` (NEW)
- [x] `frontend/src/components/SceneCard.tsx` (MODIFY)
- [ ] `frontend/src/lib/api.ts` (MODIFY - if needed)

---

## Testing Checklist

- [x] Backend WebSocket accepts connections
- [x] Session creation works
- [x] Chunks stream correctly
- [x] Frontend receives messages
- [x] Audio plays automatically
- [x] Error handling works
- [ ] Connection recovery
- [ ] Multiple concurrent users

---

## Rollback Plan

Keep old REST endpoints for 1 week:
- `/api/tts/audio/{scene_id}/chunk/{chunk_number}` stays
- Frontend can fall back if WebSocket fails
- Monitor for issues
- Remove after stability confirmed
