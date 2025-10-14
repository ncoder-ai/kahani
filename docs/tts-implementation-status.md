# TTS Implementation Status & Next Steps

## 📊 Current Status Overview

### ✅ Completed Phases

#### Phase 1: Backend Foundation - **100% COMPLETE**
- ✅ Database models (TTSSettings, SceneAudio, TTSProviderConfig)
- ✅ Migration scripts executed
- ✅ Provider architecture (OpenAI-compatible, Chatterbox, Kokoro)
- ✅ TTSService with text chunking
- ✅ TTS settings endpoints
- ✅ Provider registration system
- ✅ Health check endpoints
- ✅ Voice listing endpoints

#### Phase 2: Settings UI & Configuration - **100% COMPLETE** 
- ✅ TTSSettingsModal component
- ✅ Provider selection dropdown
- ✅ API URL and key configuration
- ✅ Voice selection with "See All Voices" modal
- ✅ VoiceBrowserModal with voice preview
- ✅ Test connection functionality
- ✅ Auto health check on provider switch
- ✅ **Per-provider configuration persistence**
- ✅ Provider-specific settings (Chatterbox: exaggeration, pace, temperature)
- ✅ Voice persistence per provider
- ✅ Speed slider (0.5x - 2.0x)
- ✅ Timeout configuration

#### Backend Audio Generation - **COMPLETE**
- ✅ Audio file storage system
- ✅ SceneAudio caching layer
- ✅ generate_scene_audio endpoint
- ✅ Audio file serving endpoint
- ✅ Chunk concatenation for long scenes
- ✅ Streaming audio chunks endpoint
- ✅ Provider-agnostic audio generation

### 🚧 Not Yet Started

#### Phase 3: Frontend TTS Player (NEXT)
**Goal**: Basic playback UI for scenes

**What needs to be built:**
1. **TTSPlayer Component**
   - Play/pause/stop controls
   - Progress bar with time display
   - Loading states
   - Error handling UI
   - Volume control
   - Speed control (0.5x - 2.0x)

2. **useTTS Hook**
   - Audio playback management using Web Audio API
   - State management (isPlaying, isPaused, isLoading)
   - Progress tracking
   - Error handling
   - Audio caching

3. **Audio State Management**
   - Add TTS state to Zustand store (or Context)
   - Track currently playing scene
   - Manage playback queue
   - Handle auto-play settings

**Files to create:**
- `frontend/src/components/TTSPlayer.tsx`
- `frontend/src/hooks/useTTS.ts`
- `frontend/src/store/ttsStore.ts` (or add to existing store)

#### Phase 4: Scene Integration
**Goal**: TTS controls in scene display

**What needs to be built:**
1. **Scene Narration Button**
   - Speaker icon button on each scene
   - Shows playing state
   - Integrates with TTSPlayer

2. **Scene Display Integration**
   - Embed TTSPlayer in scene view
   - Show audio controls when playing
   - Handle scene switching
   - Auto-narration for new scenes

3. **Narration Queue**
   - Queue multiple scenes
   - Auto-advance to next scene
   - Skip/previous controls

**Files to modify:**
- `frontend/src/components/SceneDisplay.tsx` (or equivalent)
- `frontend/src/app/story/[id]/page.tsx`

#### Phase 5: Advanced Controls
**Goal**: Enhanced playback features

**Features:**
- ✅ Speed control (already in settings)
- ✅ Volume control (need in player)
- Seek functionality (scrub timeline)
- Keyboard shortcuts (Space, Arrow keys)
- Download audio button
- Regenerate audio option
- Waveform visualization

#### Phase 6: Streaming & Performance
**Goal**: Real-time audio streaming during generation

**Features:**
- Progressive audio playback during generation
- SSE (Server-Sent Events) for streaming
- Audio prefetching for next scenes
- Optimized chunk processing
- Background generation

#### Phase 7: Polish & Testing
**Goal**: Production-ready

**Features:**
- Comprehensive error handling
- Retry logic for failures
- Loading skeletons
- User documentation
- Cross-browser testing
- Mobile optimization
- Performance monitoring

---

## 🎯 Recommended Next Steps

### Immediate Next: Phase 3 - Frontend TTS Player

This is the logical next step because:
1. Backend audio generation is complete
2. Settings UI is complete
3. Users can configure TTS providers
4. **Missing piece**: Actually playing the audio in the UI

### Phase 3 Implementation Plan

#### Step 1: Create useTTS Hook (2-3 hours)
**Priority: HIGH**

Create `frontend/src/hooks/useTTS.ts`:

```typescript
export const useTTS = () => {
  const [audioState, setAudioState] = useState({
    isPlaying: false,
    isPaused: false,
    isLoading: false,
    progress: 0,
    duration: 0,
    currentTime: 0,
    error: null,
  });
  
  const play = async (sceneId: number) => {
    // Fetch audio from /api/tts/audio/{scene_id}
    // Create Audio element
    // Handle playback
  };
  
  const pause = () => { /* ... */ };
  const resume = () => { /* ... */ };
  const stop = () => { /* ... */ };
  const seek = (time: number) => { /* ... */ };
  
  return { ...audioState, play, pause, resume, stop, seek };
};
```

**Key features:**
- Fetch audio from backend
- HTML5 Audio or Web Audio API
- Progress tracking
- Error handling
- State management

#### Step 2: Create TTSPlayer Component (3-4 hours)
**Priority: HIGH**

Create `frontend/src/components/TTSPlayer.tsx`:

```typescript
interface TTSPlayerProps {
  sceneId: number;
  autoPlay?: boolean;
  compact?: boolean;
}

export default function TTSPlayer({ sceneId, autoPlay, compact }: TTSPlayerProps) {
  const { isPlaying, progress, duration, play, pause, stop } = useTTS();
  
  return (
    <div className="tts-player">
      {/* Play/Pause button */}
      {/* Progress bar */}
      {/* Time display */}
      {/* Volume control */}
      {/* Speed control */}
    </div>
  );
}
```

**UI Elements:**
- Play/Pause/Stop buttons
- Progress bar (seekable)
- Time display (current/total)
- Volume slider
- Speed selector (0.5x, 1x, 1.5x, 2x)
- Loading spinner
- Error messages

#### Step 3: Add Speaker Button to Scenes (1-2 hours)
**Priority: MEDIUM**

Modify scene display to add speaker icon:

```typescript
// In SceneDisplay or similar component
<div className="scene-header">
  <h3>Scene {scene.number}</h3>
  <button onClick={() => playScene(scene.id)}>
    🔊 {isPlaying ? 'Pause' : 'Play'}
  </button>
</div>

{isPlaying && <TTSPlayer sceneId={scene.id} />}
```

#### Step 4: Add TTS State Management (1-2 hours)
**Priority: MEDIUM**

Add to Zustand store or create new store:

```typescript
interface TTSStore {
  currentSceneId: number | null;
  isPlaying: boolean;
  autoPlayEnabled: boolean;
  queue: number[];
  
  setCurrentScene: (id: number) => void;
  toggleAutoPlay: () => void;
  addToQueue: (id: number) => void;
}
```

#### Step 5: Integration Testing (1 hour)
**Priority: MEDIUM**

- Test audio generation for different scenes
- Test play/pause/stop functionality
- Test progress tracking
- Test error handling (offline, failed generation)
- Test with different providers

---

## 📝 Detailed Phase 3 Tasks

### Task 1: useTTS Hook Implementation

**File:** `frontend/src/hooks/useTTS.ts`

**Requirements:**
1. Audio fetching from API
2. HTML5 Audio element management
3. Playback controls (play, pause, stop, seek)
4. Progress tracking with callbacks
5. Error handling and retry logic
6. Volume control
7. Speed control
8. Loading states

**API Endpoints to use:**
- `GET /api/tts/audio/{scene_id}` - Get audio file
- `POST /api/tts/generate/{scene_id}` - Generate if not cached
- `GET /api/tts/audio/{scene_id}/info` - Get audio metadata

**State to track:**
```typescript
{
  isPlaying: boolean;
  isPaused: boolean;
  isLoading: boolean;
  isGenerating: boolean;
  progress: number; // 0-100
  duration: number; // seconds
  currentTime: number; // seconds
  volume: number; // 0-1
  speed: number; // 0.5-2.0
  error: string | null;
  sceneId: number | null;
}
```

### Task 2: TTSPlayer Component

**File:** `frontend/src/components/TTSPlayer.tsx`

**Props:**
```typescript
interface TTSPlayerProps {
  sceneId: number;
  autoPlay?: boolean;
  onEnded?: () => void;
  compact?: boolean; // Mini player vs full player
  className?: string;
}
```

**Layout (Full Mode):**
```
┌─────────────────────────────────────────┐
│  ▶️  [━━━━━━━━━━━━━━━━━━━━━━] 2:34/5:12 │
│  🔊  [▰▰▰▰▰▱▱▱]  1.0x  ⚙️  ⬇️            │
└─────────────────────────────────────────┘
```

**Layout (Compact Mode):**
```
┌─────────────────────────────┐
│  ▶️  [━━━━━━━━━] 2:34/5:12  │
└─────────────────────────────┘
```

**Features:**
- Play/Pause button with icon swap
- Stop button
- Progress bar (clickable for seek)
- Current time / Total time
- Volume slider
- Speed selector dropdown
- Download button
- Regenerate button (⚙️)
- Loading spinner during generation
- Error display with retry

### Task 3: Scene Integration

**File:** `frontend/src/app/story/[id]/page.tsx` (or SceneDisplay component)

**Changes needed:**
1. Add speaker button to scene header/footer
2. Show TTSPlayer when audio is playing
3. Highlight currently playing scene
4. Add keyboard shortcuts (Space to play/pause)
5. Handle auto-play for new scenes

**Visual integration:**
```tsx
<div className={`scene ${isPlaying ? 'playing' : ''}`}>
  <div className="scene-header">
    <h3>Scene {scene.number}</h3>
    <button 
      onClick={() => handleNarrate(scene.id)}
      className="narrate-btn"
    >
      {isCurrentScene ? '⏸️' : '🔊'}
    </button>
  </div>
  
  <div className="scene-content">
    {scene.content}
  </div>
  
  {isCurrentScene && (
    <TTSPlayer 
      sceneId={scene.id}
      onEnded={() => handleSceneEnd()}
    />
  )}
</div>
```

### Task 4: TTS Store Setup

**File:** `frontend/src/store/ttsStore.ts`

```typescript
import { create } from 'zustand';

interface TTSState {
  // Current playback
  currentSceneId: number | null;
  isPlaying: boolean;
  
  // Queue management
  queue: number[];
  autoPlayNext: boolean;
  
  // Settings
  defaultSpeed: number;
  defaultVolume: number;
  
  // Actions
  setCurrentScene: (id: number | null) => void;
  setPlaying: (playing: boolean) => void;
  addToQueue: (sceneId: number) => void;
  removeFromQueue: (sceneId: number) => void;
  clearQueue: () => void;
  toggleAutoPlay: () => void;
  setSpeed: (speed: number) => void;
  setVolume: (volume: number) => void;
}

export const useTTSStore = create<TTSState>((set) => ({
  currentSceneId: null,
  isPlaying: false,
  queue: [],
  autoPlayNext: false,
  defaultSpeed: 1.0,
  defaultVolume: 1.0,
  
  setCurrentScene: (id) => set({ currentSceneId: id }),
  setPlaying: (playing) => set({ isPlaying: playing }),
  addToQueue: (sceneId) => set((state) => ({ 
    queue: [...state.queue, sceneId] 
  })),
  // ... other actions
}));
```

---

## 🎯 Success Criteria for Phase 3

### Must Have:
- ✅ Audio plays when clicking speaker button
- ✅ Progress bar shows playback progress
- ✅ Play/Pause/Stop controls work
- ✅ Time display shows current/total time
- ✅ Loading state during audio generation
- ✅ Error handling with user-friendly messages

### Nice to Have:
- Volume control
- Speed control
- Seek functionality
- Download audio
- Keyboard shortcuts
- Waveform visualization

### Testing Checklist:
- [ ] Play audio for a scene
- [ ] Pause and resume
- [ ] Stop playback
- [ ] Progress bar updates correctly
- [ ] Time display is accurate
- [ ] Loading state shows during generation
- [ ] Error shows if generation fails
- [ ] Works with all 3 providers (Chatterbox, Kokoro, OpenAI-compatible)
- [ ] Audio caching works (second play is instant)
- [ ] Multiple scenes can queue

---

## 🚀 After Phase 3

### Phase 4: Enhanced Scene Integration
- Auto-narration for new scenes
- Scene-to-scene playback queue
- Background audio generation
- Mini player that stays visible

### Phase 5: Advanced Features
- Streaming audio during generation
- Progressive playback (start before full generation)
- Waveform visualization
- Character voice assignments
- Playlist creation

### Phase 6: Polish
- Animations and transitions
- Loading skeletons
- Toast notifications
- Help tooltips
- Mobile optimization
- Accessibility (ARIA labels, keyboard nav)

---

## 📊 Overall Progress

**Completed:** 40%
- ✅ Backend foundation
- ✅ Settings UI
- ✅ Provider configuration
- ✅ Audio generation
- ⏳ Frontend player (0%)
- ⏳ Scene integration (0%)
- ⏳ Advanced features (0%)

**Estimated Time Remaining:**
- Phase 3 (Player): 8-10 hours
- Phase 4 (Scene Integration): 6-8 hours  
- Phase 5+ (Advanced): 10-15 hours

**Total: ~25-35 hours to complete full TTS feature**

---

## 🎉 What You've Built So Far

Your TTS foundation is **solid**! You have:

1. ✅ **Complete backend infrastructure**
   - Multi-provider architecture
   - Audio generation and caching
   - Streaming support
   - Health checks
   - Voice management

2. ✅ **Advanced settings UI**
   - Provider selection
   - Per-provider configuration persistence
   - Voice browser with preview
   - Auto health checks
   - Provider-specific settings (Chatterbox params)

3. ✅ **Database schema**
   - TTS settings per user
   - Provider configs per user/provider
   - Scene audio caching
   - Proper migrations

**What's missing:** The playback UI! Users can configure everything but can't actually listen to their scenes yet.

---

## 🎯 Recommendation: Start Phase 3 Now

**Why Phase 3 is perfect next step:**
- Backend is ready to serve audio
- Settings allow full configuration
- Natural progression: "I can configure TTS, now let me use it!"
- Unlocks immediate value for users
- Enables testing of end-to-end flow

**Start with:** `useTTS` hook → `TTSPlayer` component → Add to scene display

This will give you a **working, usable TTS feature** that users can actually interact with!
