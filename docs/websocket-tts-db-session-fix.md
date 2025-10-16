# WebSocket TTS Fix - Database Session Issue

## Problem #2 Identified

After fixing the race condition, a new issue appeared:

**Error:** "The network connection was lost" when calling `POST /api/tts/generate-ws/30`

**Root Cause:** Database session was being passed to background task, but the session was closed by the time the background task tried to use it!

### Why This Happens

FastAPI's `Depends(get_db)` creates a database session that's tied to the request lifecycle:

```python
# In the endpoint
async def generate_scene_audio_websocket(..., db: Session = Depends(get_db)):
    # db session is valid here
    
    background_tasks.add_task(
        generate_and_stream_chunks,
        db=db  # ❌ Passing db session to background task
    )
    
    return response  # ✅ Request ends, db session closes!

# Later, in background task
async def generate_and_stream_chunks(..., db: Session):
    # ❌ db session is already closed - CRASH!
    scene = db.query(Scene).filter(...)  # ❌ Error: connection lost
```

## Solution Applied

Background tasks must create their own database sessions:

```python
async def generate_and_stream_chunks(
    session_id: str,
    scene_id: int,  # ✅ Pass ID instead of object
    user_id: int
    # ✅ No db parameter
):
    # ✅ Create own DB session
    db = next(get_db())
    
    try:
        # ✅ Query with our own session
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        
        # ... generate audio ...
        
    finally:
        # ✅ Clean up our session
        db.close()
```

## What Changed

**File:** `backend/app/routers/tts.py`

### Change 1: Endpoint (line ~750)
```python
# Before
background_tasks.add_task(
    generate_and_stream_chunks,
    session_id=session_id,
    scene=scene,  # ❌ Passing ORM object with closed session
    user_id=current_user.id,
    db=db  # ❌ Passing closed session
)

# After
background_tasks.add_task(
    generate_and_stream_chunks,
    session_id=session_id,
    scene_id=scene_id,  # ✅ Just pass the ID
    user_id=current_user.id
    # ✅ No db parameter
)
```

### Change 2: Background Task Function (line ~773)
```python
# Before
async def generate_and_stream_chunks(
    session_id: str,
    scene: Scene,  # ❌ ORM object from closed session
    user_id: int,
    db: Session  # ❌ Closed session
):

# After
async def generate_and_stream_chunks(
    session_id: str,
    scene_id: int,  # ✅ Just the ID
    user_id: int
    # ✅ No db parameter
):
    # ✅ Create fresh DB session
    db = next(get_db())
    
    try:
        # ✅ Query with fresh session
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        # ... rest of the code ...
    finally:
        db.close()  # ✅ Clean up
```

## Testing Steps

1. **Restart backend server** (it must reload with the fix):
   ```bash
   # Stop current backend (Ctrl+C in backend terminal)
   # Or if using ./start-dev.sh, restart it
   ```

2. **Refresh frontend**

3. **Click "🔊 Narrate" button**

4. **Expected behavior:**
   - ✅ No "network connection lost" error
   - ✅ Backend logs show:
     ```
     Waiting for WebSocket connection for session abc123
     WebSocket connected for session abc123
     Generating 5 chunks for session abc123
     Sent chunk 1/5 for session abc123
     ```
   - ✅ Browser console shows:
     ```
     [TTS WS] Connected
     [TTS WS] Chunk ready: 1/5
     [Audio] Playing chunk 1
     ```

## Why This Pattern?

**Background tasks in FastAPI must be self-contained:**

✅ **Good:** Pass IDs, create own resources
```python
background_tasks.add_task(my_task, user_id=123, scene_id=456)

async def my_task(user_id: int, scene_id: int):
    db = next(get_db())  # Own session
    try:
        # Do work
    finally:
        db.close()
```

❌ **Bad:** Pass request-scoped resources
```python
background_tasks.add_task(my_task, db=db, user=current_user)  # ❌

async def my_task(db: Session, user: User):
    # db is closed, user object is detached - CRASH!
```

## Related Issues Fixed

- ✅ Race condition (background task vs WebSocket connect)
- ✅ Database session lifecycle (this fix)

Both issues have been resolved!
