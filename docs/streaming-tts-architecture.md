# Streaming TTS Architecture - Real-time Audio During Scene Generation

## Overview

This document outlines the architecture for two advanced TTS features:

1. **Auto-play TTS for Complete Scenes**: Automatically generate and play audio for completed scenes using chunked approach
2. **Real-time TTS During Scene Generation**: Stream audio playback while LLM is still generating text (synchronized streaming)

## Feature 1: Auto-play TTS for Complete Scenes

### Current State
- ✅ Scene generation completes
- ✅ User manually clicks narrate button
- ✅ Backend chunks text, generates audio per chunk
- ✅ Frontend plays chunks sequentially

### Proposed Enhancement
- ✅ Scene generation completes
- ✅ **AUTO-TRIGGER** TTS generation (if setting enabled)
- ✅ Backend chunks text, generates audio per chunk
- ✅ Frontend automatically starts playback

### Architecture

#### 1.1 Database Schema Changes

```python
# backend/app/models/tts_settings.py
class TTSSettings(Base):
    # ... existing fields ...
    
    # NEW FIELD
    auto_play_last_scene = Column(Boolean, default=False)  # Auto-play after scene generation
```

**Migration needed:**
```python
# backend/migrate_add_auto_play.py
ALTER TABLE tts_settings ADD COLUMN auto_play_last_scene BOOLEAN DEFAULT FALSE;
```

#### 1.2 Backend Flow

```
Scene Generation Complete
    ↓
Check: user_settings.auto_play_last_scene == True?
    ↓ YES
Trigger TTS generation in background
    ↓
Chunk text (using existing TextChunker)
    ↓
Generate audio for each chunk (async)
    ↓
Store chunks in SceneAudioChunk table
    ↓
Emit WebSocket event: "tts_ready" { scene_id, chunk_count }
```

**Code Location:** `backend/app/api/stories.py`

```python
@router.post("/{story_id}/scenes")
async def generate_scene(...):
    # ... existing scene generation ...
    
    # After scene is created
    scene_id = scene.id
    
    # Check if auto-play is enabled
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    if tts_settings and tts_settings.tts_enabled and tts_settings.auto_play_last_scene:
        # Trigger TTS generation in background (don't block response)
        background_tasks.add_task(
            auto_generate_scene_audio,
            scene_id=scene_id,
            user_id=current_user.id,
            db=db
        )
    
    return scene_response
```

**Background Task:**
```python
async def auto_generate_scene_audio(scene_id: int, user_id: int, db: Session):
    """Generate TTS audio in background and notify via WebSocket"""
    try:
        tts_service = TTSService(db)
        
        # Generate audio (this will chunk and create SceneAudioChunk entries)
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        await tts_service.get_or_generate_scene_audio(
            scene=scene,
            user_id=user_id,
            force_regenerate=True
        )
        
        # Get chunk count
        chunk_count = db.query(SceneAudioChunk).filter(
            SceneAudioChunk.scene_audio_id == scene.scene_audio.id
        ).count()
        
        # Notify frontend via WebSocket
        await websocket_manager.send_personal_message(
            user_id=user_id,
            message={
                "type": "tts_ready",
                "scene_id": scene_id,
                "chunk_count": chunk_count,
                "auto_play": True
            }
        )
        
    except Exception as e:
        logger.error(f"Auto TTS generation failed: {e}")
```

#### 1.3 Frontend Flow

**Settings UI** (`TTSSettingsModal.tsx`):
```tsx
<div className="flex items-center justify-between">
  <div className="flex-1">
    <label className="text-sm font-medium text-gray-300">
      Auto-play Last Scene
    </label>
    <p className="text-xs text-gray-500 mt-1">
      Automatically narrate new scenes after generation completes
    </p>
  </div>
  <button
    type="button"
    onClick={() => setSettings(prev => ({ 
      ...prev, 
      auto_play_last_scene: !prev.auto_play_last_scene 
    }))}
    disabled={!settings.tts_enabled}
    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
      settings.auto_play_last_scene ? 'bg-purple-600' : 'bg-gray-700'
    } disabled:opacity-50`}
  >
    {/* Toggle UI */}
  </button>
</div>
```

**WebSocket Handler** (`Story.tsx` or global context):
```tsx
useEffect(() => {
  // Connect to WebSocket
  const ws = new WebSocket(`ws://localhost:9876/ws/${userId}`);
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'tts_ready' && data.auto_play) {
      // Auto-play the newly generated audio
      handleAutoPlayTTS(data.scene_id, data.chunk_count);
    }
  };
  
  return () => ws.close();
}, [userId]);

const handleAutoPlayTTS = async (sceneId: number, chunkCount: number) => {
  // Use existing TTS hook
  const { play } = useTTS({
    sceneId,
    onPlaybackStart: () => console.log('Auto-playing TTS'),
    onError: (err) => console.error('Auto-play failed:', err)
  });
  
  // Start playback
  await play();
};
```

#### 1.4 Benefits
- ✅ Uses existing chunking system
- ✅ No blocking during scene generation
- ✅ User setting for control
- ✅ WebSocket for instant notification

---

## Feature 2: Real-time TTS During Scene Generation

### Current State
```
LLM generates text → Complete → User clicks narrate → TTS generates → Play
```

### Proposed Enhancement
```
LLM generates text chunk → TTS generates audio → Play audio → Loop
(All happening simultaneously in real-time)
```

### Architecture

#### 2.1 Key Challenge: Synchronization
- **Problem**: LLM streams text tokens, TTS needs sentences/phrases
- **Solution**: Buffer LLM output until complete sentence, then send to TTS

#### 2.2 Streaming Flow

```
Frontend initiates scene generation with TTS streaming
    ↓
Backend receives request
    ↓
WebSocket connection established
    ↓
┌─────────────────────────────────────────┐
│  PARALLEL STREAMING PIPELINE            │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │ LLM Stream                       │  │
│  │ (Character-by-character tokens)  │  │
│  └──────────┬───────────────────────┘  │
│             ↓                           │
│  ┌──────────────────────────────────┐  │
│  │ Text Buffer                      │  │
│  │ (Accumulate until sentence end)  │  │
│  └──────────┬───────────────────────┘  │
│             ↓                           │
│  ┌──────────────────────────────────┐  │
│  │ Sentence Complete?               │  │
│  │ (. ! ? delimiter)                │  │
│  └──────────┬───────────────────────┘  │
│             ↓ YES                       │
│  ┌──────────────────────────────────┐  │
│  │ TTS Stream                       │  │
│  │ (Chatterbox streaming)           │  │
│  └──────────┬───────────────────────┘  │
│             ↓                           │
│  ┌──────────────────────────────────┐  │
│  │ Audio Chunk                      │  │
│  │ (Base64 encoded)                 │  │
│  └──────────┬───────────────────────┘  │
│             ↓                           │
│  ┌──────────────────────────────────┐  │
│  │ WebSocket Send                   │  │
│  │ → Frontend                       │  │
│  └──────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
    ↓
Frontend receives audio chunks
    ↓
Queue audio chunks
    ↓
Play sequentially
```

#### 2.3 Backend Implementation

**New Endpoint** (`backend/app/api/stories.py`):
```python
@router.post("/{story_id}/scenes/generate-with-tts-stream")
async def generate_scene_with_tts_stream(
    story_id: int,
    custom_prompt: str = Form(""),
    enable_tts_stream: bool = Form(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate scene with real-time TTS streaming.
    Requires WebSocket connection for bidirectional streaming.
    
    Returns:
        WebSocket URL for client to connect to
    """
    # Create unique session ID
    session_id = f"{user_id}_{story_id}_{int(time.time())}"
    
    # Store session info
    await streaming_sessions.create_session(
        session_id=session_id,
        user_id=current_user.id,
        story_id=story_id,
        custom_prompt=custom_prompt,
        enable_tts=enable_tts_stream
    )
    
    return {
        "session_id": session_id,
        "websocket_url": f"ws://localhost:9876/ws/scene-generation/{session_id}"
    }
```

**WebSocket Endpoint** (`backend/app/api/websocket.py`):
```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import AsyncIterator
import asyncio

class StreamingSessionManager:
    """Manages active streaming sessions"""
    
    def __init__(self):
        self.active_sessions: Dict[str, WebSocket] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_sessions[session_id] = websocket
    
    async def disconnect(self, session_id: str):
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
    
    async def send_message(self, session_id: str, message: dict):
        if session_id in self.active_sessions:
            ws = self.active_sessions[session_id]
            await ws.send_json(message)

streaming_manager = StreamingSessionManager()

@app.websocket("/ws/scene-generation/{session_id}")
async def websocket_scene_generation(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for synchronized LLM + TTS streaming
    """
    await streaming_manager.connect(session_id, websocket)
    
    try:
        # Get session info
        session = await streaming_sessions.get_session(session_id)
        
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id
        })
        
        # Start the streaming pipeline
        await run_streaming_pipeline(
            session=session,
            websocket=websocket,
            db=db
        )
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    finally:
        await streaming_manager.disconnect(session_id)


async def run_streaming_pipeline(
    session: StreamingSession,
    websocket: WebSocket,
    db: Session
):
    """
    Main pipeline: LLM → Text Buffer → TTS → Audio Stream
    """
    # Get user settings
    user_settings = get_or_create_user_settings(session.user_id, db)
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == session.user_id
    ).first()
    
    # Build context for LLM
    context_manager = ContextManager(user_settings=user_settings, user_id=session.user_id)
    context = await context_manager.build_scene_generation_context(
        session.story_id, db, session.custom_prompt
    )
    
    # Initialize TTS provider
    from app.services.tts.factory import TTSProviderFactory
    tts_provider = TTSProviderFactory.create_provider(
        provider_type=tts_settings.tts_provider_type,
        api_url=tts_settings.tts_api_url,
        api_key=tts_settings.tts_api_key or "",
        timeout=30,
        extra_params=tts_settings.tts_extra_params or {}
    )
    
    # Text buffer for accumulating LLM output
    text_buffer = ""
    full_scene_text = ""
    sentence_count = 0
    
    # Send status update
    await websocket.send_json({
        "type": "generation_started",
        "message": "Starting scene generation with real-time narration"
    })
    
    try:
        # Stream from LLM
        async for text_chunk in llm_service.generate_scene_streaming(
            context, session.user_id, user_settings
        ):
            # Accumulate in buffer
            text_buffer += text_chunk
            full_scene_text += text_chunk
            
            # Send text to frontend immediately
            await websocket.send_json({
                "type": "text_chunk",
                "text": text_chunk
            })
            
            # Check if we have a complete sentence
            if has_sentence_boundary(text_buffer):
                sentence = extract_complete_sentence(text_buffer)
                text_buffer = text_buffer[len(sentence):].lstrip()
                
                # Generate TTS for this sentence
                logger.info(f"Generating TTS for sentence #{sentence_count}: {sentence[:50]}...")
                
                # Stream TTS audio
                try:
                    tts_request = TTSRequest(
                        text=sentence,
                        voice_id=tts_settings.default_voice,
                        speed=tts_settings.speech_speed,
                        format=AudioFormat.MP3
                    )
                    
                    # Collect audio stream into chunks
                    audio_data = b""
                    async for audio_chunk in tts_provider.synthesize_stream(tts_request):
                        audio_data += audio_chunk
                    
                    # Send complete audio for this sentence
                    import base64
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    
                    await websocket.send_json({
                        "type": "audio_chunk",
                        "audio": audio_base64,
                        "sentence_number": sentence_count,
                        "sentence_text": sentence,
                        "format": "mp3"
                    })
                    
                    sentence_count += 1
                    
                except Exception as tts_error:
                    logger.error(f"TTS generation failed for sentence: {tts_error}")
                    # Continue with text generation even if TTS fails
        
        # Handle any remaining text in buffer
        if text_buffer.strip():
            # Generate TTS for remaining text
            try:
                tts_request = TTSRequest(
                    text=text_buffer.strip(),
                    voice_id=tts_settings.default_voice,
                    speed=tts_settings.speech_speed,
                    format=AudioFormat.MP3
                )
                
                audio_data = b""
                async for audio_chunk in tts_provider.synthesize_stream(tts_request):
                    audio_data += audio_chunk
                
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                
                await websocket.send_json({
                    "type": "audio_chunk",
                    "audio": audio_base64,
                    "sentence_number": sentence_count,
                    "sentence_text": text_buffer.strip(),
                    "format": "mp3"
                })
            except Exception as e:
                logger.error(f"Final TTS generation failed: {e}")
        
        # Save the scene to database
        scene = await save_scene_to_db(
            story_id=session.story_id,
            content=full_scene_text,
            db=db
        )
        
        # Send completion message
        await websocket.send_json({
            "type": "generation_complete",
            "scene_id": scene.id,
            "total_sentences": sentence_count,
            "total_length": len(full_scene_text)
        })
        
    except Exception as e:
        logger.error(f"Streaming pipeline error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


def has_sentence_boundary(text: str) -> bool:
    """Check if text contains complete sentence"""
    # Look for sentence-ending punctuation followed by space or newline
    import re
    return bool(re.search(r'[.!?]["\']?\s', text))


def extract_complete_sentence(text: str) -> str:
    """Extract first complete sentence from text"""
    import re
    match = re.search(r'^.*?[.!?]["\']?(?:\s|$)', text, re.DOTALL)
    if match:
        return match.group(0).rstrip()
    return text
```

#### 2.4 Frontend Implementation

**New Hook** (`frontend/src/hooks/useStreamingTTS.ts`):
```typescript
import { useCallback, useEffect, useRef, useState } from 'react';

interface UseStreamingTTSOptions {
  storyId: number;
  customPrompt?: string;
  onTextChunk?: (text: string) => void;
  onAudioChunk?: (audio: string, sentenceNumber: number) => void;
  onComplete?: (sceneId: number) => void;
  onError?: (error: string) => void;
}

interface AudioQueueItem {
  audio: string; // Base64
  sentenceNumber: number;
  sentenceText: string;
}

export function useStreamingTTS({
  storyId,
  customPrompt = '',
  onTextChunk,
  onAudioChunk,
  onComplete,
  onError
}: UseStreamingTTSOptions) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [accumulatedText, setAccumulatedText] = useState('');
  const [isPlaying, setIsPlaying] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const audioQueueRef = useRef<AudioQueueItem[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  
  // Audio playback queue processor
  const processAudioQueue = useCallback(async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) {
      return;
    }
    
    const audioItem = audioQueueRef.current.shift();
    if (!audioItem) return;
    
    isPlayingRef.current = true;
    setIsPlaying(true);
    
    try {
      // Create audio element
      const audio = new Audio();
      audioRef.current = audio;
      
      // Convert base64 to blob URL
      const binaryString = atob(audioItem.audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);
      
      audio.src = url;
      
      // Play audio
      await audio.play();
      
      // Wait for audio to finish
      await new Promise<void>((resolve) => {
        audio.onended = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
      });
      
    } catch (error) {
      console.error('Audio playback error:', error);
    } finally {
      isPlayingRef.current = false;
      audioRef.current = null;
      
      // Process next audio in queue
      if (audioQueueRef.current.length > 0) {
        setTimeout(() => processAudioQueue(), 100);
      } else {
        setIsPlaying(false);
      }
    }
  }, []);
  
  const startGeneration = useCallback(async () => {
    setIsGenerating(true);
    setAccumulatedText('');
    audioQueueRef.current = [];
    
    try {
      // Get WebSocket URL from backend
      const response = await fetch(
        `${API_BASE_URL}/api/stories/${storyId}/scenes/generate-with-tts-stream`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
            'Content-Type': 'application/x-www-form-urlencoded'
          },
          body: new URLSearchParams({
            custom_prompt: customPrompt,
            enable_tts_stream: 'true'
          })
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to start generation');
      }
      
      const { session_id, websocket_url } = await response.json();
      
      // Connect to WebSocket
      const ws = new WebSocket(websocket_url);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('WebSocket connected');
      };
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        switch (data.type) {
          case 'connected':
            console.log('Streaming session connected:', data.session_id);
            break;
          
          case 'generation_started':
            console.log('Generation started');
            break;
          
          case 'text_chunk':
            // Accumulate text
            setAccumulatedText(prev => prev + data.text);
            onTextChunk?.(data.text);
            break;
          
          case 'audio_chunk':
            // Add audio to queue
            audioQueueRef.current.push({
              audio: data.audio,
              sentenceNumber: data.sentence_number,
              sentenceText: data.sentence_text
            });
            
            onAudioChunk?.(data.audio, data.sentence_number);
            
            // Start playback if not already playing
            if (!isPlayingRef.current) {
              processAudioQueue();
            }
            break;
          
          case 'generation_complete':
            console.log('Generation complete:', data);
            setIsGenerating(false);
            onComplete?.(data.scene_id);
            break;
          
          case 'error':
            console.error('Generation error:', data.message);
            onError?.(data.message);
            setIsGenerating(false);
            break;
        }
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        onError?.('WebSocket connection error');
        setIsGenerating(false);
      };
      
      ws.onclose = () => {
        console.log('WebSocket closed');
        wsRef.current = null;
      };
      
    } catch (error) {
      console.error('Failed to start generation:', error);
      onError?.(error instanceof Error ? error.message : 'Failed to start generation');
      setIsGenerating(false);
    }
  }, [storyId, customPrompt, onTextChunk, onAudioChunk, onComplete, onError, processAudioQueue]);
  
  const stopGeneration = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    // Stop current audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    setIsGenerating(false);
    setIsPlaying(false);
  }, []);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopGeneration();
    };
  }, [stopGeneration]);
  
  return {
    startGeneration,
    stopGeneration,
    isGenerating,
    isPlaying,
    accumulatedText
  };
}
```

**Usage in Story Component**:
```tsx
// Story.tsx or similar
const {
  startGeneration,
  stopGeneration,
  isGenerating,
  isPlaying,
  accumulatedText
} = useStreamingTTS({
  storyId: story.id,
  onTextChunk: (text) => {
    // Update UI with new text chunk
    setStreamingText(prev => prev + text);
  },
  onAudioChunk: (audio, sentenceNumber) => {
    console.log(`Audio chunk ${sentenceNumber} received`);
  },
  onComplete: (sceneId) => {
    // Scene complete, refresh story
    loadStory();
  },
  onError: (error) => {
    alert(`Generation failed: ${error}`);
  }
});

// Button to trigger streaming generation
<button
  onClick={startGeneration}
  disabled={isGenerating}
  className="px-4 py-2 bg-purple-600 rounded"
>
  {isGenerating ? (
    <>
      <Loader2 className="w-4 h-4 animate-spin" />
      Generating with audio...
    </>
  ) : (
    'Generate Scene with TTS'
  )}
</button>

// Display streaming text
{accumulatedText && (
  <div className="mt-4 p-4 bg-slate-800 rounded">
    <p className="text-gray-300">{accumulatedText}</p>
    {isPlaying && (
      <div className="mt-2 flex items-center text-sm text-purple-400">
        <Volume2 className="w-4 h-4 mr-2" />
        Playing narration...
      </div>
    )}
  </div>
)}
```

#### 2.5 Settings UI

Add toggle in TTS Settings Modal:
```tsx
<div className="flex items-center justify-between">
  <div className="flex-1">
    <label className="text-sm font-medium text-gray-300">
      Real-time TTS During Generation
    </label>
    <p className="text-xs text-gray-500 mt-1">
      Hear narration while scene is being written (experimental)
    </p>
  </div>
  <button
    type="button"
    onClick={() => setSettings(prev => ({ 
      ...prev, 
      realtime_tts: !prev.realtime_tts 
    }))}
    disabled={!settings.tts_enabled}
    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
      settings.realtime_tts ? 'bg-purple-600' : 'bg-gray-700'
    } disabled:opacity-50`}
  >
    {/* Toggle UI */}
  </button>
</div>
```

---

## Comparison Matrix

| Feature | Feature 1: Auto-play Complete | Feature 2: Real-time Streaming |
|---------|------------------------------|-------------------------------|
| **Complexity** | Low (uses existing system) | High (new WebSocket pipeline) |
| **Latency** | Scene complete → 2-5s → Play | Text appears → instant audio |
| **User Control** | Setting toggle only | Setting + manual trigger |
| **Backend Changes** | Add background task | New WebSocket endpoints |
| **Frontend Changes** | WebSocket listener | New hook + components |
| **TTS Provider** | Any provider works | **Requires streaming support (Chatterbox)** |
| **Error Handling** | Simple (task fails) | Complex (streaming recovery) |
| **Network Usage** | Moderate (chunked) | High (continuous stream) |
| **Use Case** | Hands-free experience | Immersive real-time |

---

## Implementation Priority

### Phase 1: Feature 1 (Auto-play Complete Scenes) - RECOMMENDED FIRST
**Estimated Time**: 2-3 days

1. ✅ Add `auto_play_last_scene` to TTSSettings model
2. ✅ Create migration script
3. ✅ Add background task after scene generation
4. ✅ WebSocket notification system
5. ✅ Frontend WebSocket listener
6. ✅ Update TTSSettingsModal UI
7. ✅ Test end-to-end flow

**Benefits**:
- Quick win
- Uses existing infrastructure
- Works with all TTS providers
- Low risk

### Phase 2: Feature 2 (Real-time Streaming) - ADVANCED FEATURE
**Estimated Time**: 1-2 weeks

1. ✅ Design WebSocket protocol
2. ✅ Implement streaming session manager
3. ✅ Create streaming pipeline (LLM → Buffer → TTS)
4. ✅ Implement sentence boundary detection
5. ✅ Build frontend hook and audio queue
6. ✅ Add UI controls and status indicators
7. ✅ Extensive testing and optimization
8. ✅ Error handling and recovery

**Benefits**:
- Revolutionary UX
- True real-time experience
- Competitive advantage

**Challenges**:
- Complex synchronization
- Requires Chatterbox streaming
- Error recovery more complex
- Higher network/CPU usage

---

## Technical Considerations

### 1. TTS Provider Requirements

**Feature 1**: ✅ Any provider with chunking support (current system)

**Feature 2**: Requires streaming support
- ✅ **Chatterbox**: Has streaming endpoint
- ⚠️ **OpenAI-compatible**: May not support streaming
- 🔄 Need to verify each provider's streaming capabilities

### 2. Performance

**Feature 1**:
- Scene generation: 5-15s
- TTS generation: 2-5s (background)
- Total delay: ~2-5s after scene complete
- Acceptable UX

**Feature 2**:
- LLM token: ~50ms
- Sentence complete: ~1-3s
- TTS for sentence: ~500ms-1s
- First audio: ~2-4s after generation starts
- Excellent UX

### 3. Error Handling

**Feature 1**:
- Scene generates successfully ✅
- TTS fails → User can manually retry ✅
- Simple fallback

**Feature 2**:
- LLM fails → Abort, show error ⚠️
- TTS fails mid-stream → Skip sentence, continue ⚠️
- WebSocket drops → Reconnect or fallback ⚠️
- Complex recovery needed

### 4. User Settings

Add to `TTSSettings` model:
```python
# Feature 1
auto_play_last_scene = Column(Boolean, default=False)

# Feature 2  
realtime_tts_enabled = Column(Boolean, default=False)
min_sentence_length = Column(Integer, default=20)  # Min chars before TTS
```

---

## API Endpoints Summary

### Feature 1
- ✅ Use existing: `POST /api/stories/{story_id}/scenes`
- ✅ Add WebSocket: `ws://localhost:9876/ws/{user_id}` (global)
- ✅ Background task integration

### Feature 2
- 🆕 `POST /api/stories/{story_id}/scenes/generate-with-tts-stream`
- 🆕 `ws://localhost:9876/ws/scene-generation/{session_id}`
- 🆕 Session management endpoints

---

## Testing Plan

### Feature 1 Testing
1. Enable auto-play setting
2. Generate new scene
3. Verify TTS starts automatically after scene complete
4. Test with TTS disabled
5. Test with different chunk sizes
6. Test error scenarios (TTS provider down)
7. Test WebSocket reconnection

### Feature 2 Testing
1. Enable real-time TTS
2. Trigger scene generation
3. Verify text appears progressively
4. Verify audio plays as sentences complete
5. Test sentence boundary detection (various punctuation)
6. Test with long/short sentences
7. Test audio queue management (fast LLM, slow TTS)
8. Test WebSocket disconnect/reconnect
9. Test stop generation mid-stream
10. Stress test with multiple concurrent users

---

## Next Steps

1. **Decide**: Which feature to implement first?
   - Recommendation: Start with Feature 1 (auto-play complete)
   
2. **Review**: Does this architecture align with your vision?

3. **Clarify**: Any specific requirements or constraints?

4. **Proceed**: I can start implementing either feature based on your preference

---

## Questions for You

1. Should we implement Feature 1 first (simpler, working) or jump to Feature 2 (advanced, riskier)?

2. For Feature 2: Are you okay with requiring Chatterbox or should we add fallback?

3. Do you want manual controls (pause, skip sentence) for Feature 2?

4. Should real-time TTS be opt-in (setting) or replace normal generation?

5. Any preferences on the sentence boundary detection logic?
