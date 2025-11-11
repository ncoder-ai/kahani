# iOS TTS Fix Plan

## Executive Summary
TTS (Text-to-Speech) is broken on iOS due to several iOS Safari-specific audio handling issues. This document outlines the root causes and a comprehensive fix plan.

## Current Architecture

The app uses **AudioContext API (Web Audio API)** for TTS playback via `GlobalTTSContext`:
- Audio chunks are received via WebSocket as base64-encoded MP3
- Converted to Blob → ArrayBuffer → decoded with `decodeAudioData()`
- Played through AudioContext using `AudioBufferSourceNode`

## Root Causes of iOS Issues

### 1. **AudioContext Re-Suspension** ⚠️ CRITICAL
**Problem:** iOS Safari suspends AudioContext when:
- App goes to background (tab switch, home button)
- Audio interruption occurs (phone call, alarm)
- Screen locks
- After certain time periods of inactivity

**Current Code Issue:**
```typescript
// audioContextManager.ts line 87-89
isAudioUnlocked(): boolean {
  return this.isUnlocked && this.context?.state === 'running';
}
```
The `isUnlocked` flag is set once but never reset when iOS re-suspends the context.

**Impact:** After backgrounding the app, TTS will fail silently because the context is suspended but `isUnlocked` is still `true`.

---

### 2. **No Visibility/Lifecycle Handlers** ⚠️ CRITICAL
**Problem:** The app doesn't listen for iOS-specific lifecycle events:
- `visibilitychange` - when app goes to background/foreground
- `pageshow`/`pagehide` - iOS back/forward navigation
- Audio interruption events

**Current Code:** No handlers exist for these events.

**Impact:** AudioContext remains suspended when user returns to the app.

---

### 3. **Insufficient Audio Unlock Mechanism** ⚠️ HIGH
**Problem:** The silent audio used to "unlock" audio on iOS is inadequate:

```typescript
// GlobalTTSContext.tsx lines 297-306
const silentAudio = new Audio('data:audio/mp3;base64,...');
silentAudio.volume = 0.01;
silentAudio.muted = true;
```

Issues:
- MP3 data URL is very long and might not load properly
- Muted audio doesn't always trigger the unlock on iOS
- No retry mechanism if unlock fails
- The AudioContext unlock and HTMLAudioElement unlock are separate - only doing AudioContext

**Impact:** Users may tap "Enable TTS" but audio still doesn't work.

---

### 4. **AudioContext Doesn't Auto-Resume** ⚠️ HIGH
**Problem:** When iOS re-suspends AudioContext, the code doesn't detect or handle it:

```typescript
// GlobalTTSContext.tsx playNextChunk() - lines 143-154
const context = audioContextManager.getContext();

if (!context || !audioContextManager.isAudioUnlocked()) {
  console.error('[Global TTS] AudioContext not unlocked');
  setError('🔊 Audio locked - click "Enable TTS" button...');
  return;
}
```

This check happens too late - after chunks are queued. By then, the context might be suspended.

**Impact:** TTS generation starts but audio never plays, confusing users.

---

### 5. **WebSocket Disconnection on Background** ⚠️ MEDIUM
**Problem:** iOS suspends network connections when app is backgrounded:
- WebSocket closes (code 1006 - abnormal closure)
- No reconnection mechanism when app returns to foreground
- Chunks arriving during background are lost

**Current Code:** No handling for background WebSocket reconnection.

**Impact:** If user backgrounds the app during TTS generation, it breaks entirely.

---

### 6. **MP3 Decoding Issues** ⚠️ MEDIUM
**Problem:** iOS Safari's `decodeAudioData()` is picky about MP3 format:
- Some MP3 encodings fail silently
- No fallback if decoding fails
- Error messages are not user-friendly

```typescript
// GlobalTTSContext.tsx lines 157-205
chunk.audio_blob.arrayBuffer()
  .then(arrayBuffer => context.decodeAudioData(arrayBuffer))
  .catch(err => {
    console.error('[Global TTS] Failed to play chunk:', err);
    setError(`Playback failed: ${err.message}`);
  });
```

**Impact:** Some TTS audio chunks fail to play on iOS, causing gaps or complete failure.

---

### 7. **No Fallback Playback Method** ⚠️ MEDIUM
**Problem:** If AudioContext fails, there's no fallback to HTMLAudioElement.

**Note:** The codebase has `useTTSWebSocket` hook that uses HTMLAudioElement, but it's not used as a fallback.

**Impact:** Users with broken AudioContext have no way to hear TTS.

---

### 8. **Blob URL Issues on iOS** ⚠️ LOW
**Problem:** Some iOS versions have issues with blob URLs:
- Blob URLs might not work in certain contexts
- Need to ensure blob URLs are revoked properly
- Memory leaks if URLs aren't cleaned up

**Current Code:** Blob URLs are created and (mostly) revoked correctly, but there's no iOS-specific handling.

---

## Fix Plan

### Phase 1: Critical Fixes (Must Have)

#### Fix 1.1: Enhanced AudioContext State Management
**File:** `frontend/src/utils/audioContextManager.ts`

**Changes:**
1. Remove the manual `isUnlocked` flag
2. Always check `context.state === 'running'` dynamically
3. Add auto-resume capability when context is suspended
4. Add state change event listener
5. Handle iOS-specific audio interruptions

**Implementation:**
```typescript
class AudioContextManager {
  private context: AudioContext | null = null;
  private stateChangeListeners: Array<(state: AudioContextState) => void> = [];
  
  constructor() {
    if (typeof window !== 'undefined') {
      this.initializeContext();
      this.setupLifecycleHandlers();
    }
  }
  
  private initializeContext() {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (AudioContextClass) {
      this.context = new AudioContextClass();
      
      // Monitor state changes
      this.context.addEventListener('statechange', () => {
        console.log('[AudioContext] State changed to:', this.context?.state);
        this.notifyStateChange();
      });
    }
  }
  
  private setupLifecycleHandlers() {
    // iOS visibility handling
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        console.log('[AudioContext] App became visible - attempting auto-resume');
        this.attemptAutoResume();
      }
    });
    
    // iOS page show/hide (back/forward navigation)
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) {
        console.log('[AudioContext] Page shown from cache - attempting auto-resume');
        this.attemptAutoResume();
      }
    });
    
    // Audio interruption ended (iOS)
    if ('onended' in AudioContext.prototype) {
      // This is a made-up event - actual implementation needs iOS audio session handling
    }
  }
  
  private async attemptAutoResume(): Promise<void> {
    if (this.context?.state === 'suspended') {
      try {
        await this.context.resume();
        console.log('[AudioContext] Auto-resumed successfully');
      } catch (err) {
        console.warn('[AudioContext] Auto-resume failed:', err);
      }
    }
  }
  
  async unlock(): Promise<boolean> {
    if (!this.context) return false;
    
    // Always try to resume if suspended
    if (this.context.state === 'suspended') {
      try {
        await this.context.resume();
        
        // Play silent buffer to confirm unlock
        const buffer = this.context.createBuffer(1, 1, 22050);
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);
        source.start();
        
        console.log('[AudioContext] ✅ Unlocked, state:', this.context.state);
        return this.context.state === 'running';
      } catch (err) {
        console.error('[AudioContext] ❌ Unlock failed:', err);
        return false;
      }
    }
    
    return this.context.state === 'running';
  }
  
  isAudioUnlocked(): boolean {
    // ALWAYS check actual state - no cached flag
    return this.context?.state === 'running';
  }
  
  // Add listener for state changes
  addStateChangeListener(listener: (state: AudioContextState) => void) {
    this.stateChangeListeners.push(listener);
  }
  
  private notifyStateChange() {
    const state = this.context?.state || 'closed';
    this.stateChangeListeners.forEach(listener => listener(state as AudioContextState));
  }
}
```

---

#### Fix 1.2: Improve Audio Unlock with Better iOS Support
**File:** `frontend/src/utils/audioContextManager.ts`

**Changes:**
1. Use a simpler, more reliable silent audio format (WAV instead of MP3)
2. Don't mute the silent audio (iOS might ignore muted audio for unlock)
3. Add retry mechanism
4. Unlock both AudioContext AND HTMLAudioElement

**Implementation:**
```typescript
async unlock(): Promise<boolean> {
  if (!this.context) return false;
  
  console.log('[AudioContext] Unlocking... Current state:', this.context.state);
  
  // Step 1: Resume AudioContext
  if (this.context.state === 'suspended') {
    try {
      await this.context.resume();
    } catch (err) {
      console.error('[AudioContext] Resume failed:', err);
      return false;
    }
  }
  
  // Step 2: Play silent buffer through AudioContext
  try {
    const buffer = this.context.createBuffer(1, 1, 22050);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    source.start();
  } catch (err) {
    console.error('[AudioContext] Silent buffer failed:', err);
  }
  
  // Step 3: ALSO unlock HTMLAudioElement (iOS requires both)
  try {
    const audio = new Audio();
    // Use simple, reliable WAV format (44 bytes, empty audio)
    audio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAAABmYWN0BAAAAAAAAABkYXRhAAAAAA==';
    audio.volume = 0.01; // Very quiet but not muted
    
    const playPromise = audio.play();
    if (playPromise !== undefined) {
      await Promise.race([
        playPromise,
        new Promise((resolve) => setTimeout(resolve, 200))
      ]);
      audio.pause();
    }
  } catch (err) {
    console.warn('[AudioContext] HTMLAudioElement unlock failed:', err);
    // Don't fail entirely - AudioContext might still work
  }
  
  // Step 4: Verify final state
  const isUnlocked = this.context.state === 'running';
  console.log('[AudioContext] Unlock result:', isUnlocked ? '✅ Success' : '❌ Failed');
  console.log('[AudioContext] Final state:', this.context.state);
  
  return isUnlocked;
}
```

---

#### Fix 1.3: Add Lifecycle Handlers to GlobalTTSContext
**File:** `frontend/src/contexts/GlobalTTSContext.tsx`

**Changes:**
1. Listen for visibility changes
2. Auto-resume AudioContext when app returns to foreground
3. Handle WebSocket reconnection
4. Show user-friendly message if audio is suspended

**Implementation:**
```typescript
export const GlobalTTSProvider: React.FC<GlobalTTSProviderProps> = ({ children, apiBaseUrl }) => {
  // ... existing state ...
  
  // Monitor AudioContext state changes
  useEffect(() => {
    const handleStateChange = (state: AudioContextState) => {
      console.log('[Global TTS] AudioContext state changed:', state);
      
      if (state === 'suspended' && isPlaying) {
        setAudioPermissionBlocked(true);
        setError('🔊 Audio suspended - tap to resume');
      } else if (state === 'running') {
        setAudioPermissionBlocked(false);
      }
    };
    
    audioContextManager.addStateChangeListener(handleStateChange);
    
    return () => {
      // Remove listener on unmount
    };
  }, [isPlaying]);
  
  // Handle visibility changes (iOS backgrounding)
  useEffect(() => {
    const handleVisibilityChange = async () => {
      if (document.visibilityState === 'visible') {
        console.log('[Global TTS] App became visible');
        
        // If we were playing, try to resume
        if (currentSceneId && (isPlaying || isGenerating)) {
          console.log('[Global TTS] Attempting to resume after visibility change');
          
          // Check if AudioContext needs resume
          const context = audioContextManager.getContext();
          if (context?.state === 'suspended') {
            const unlocked = await audioContextManager.unlock();
            if (!unlocked) {
              setError('🔊 Audio locked - please tap the Enable TTS button');
              setAudioPermissionBlocked(true);
            }
          }
          
          // Check WebSocket connection
          if (wsRef.current?.readyState !== WebSocket.OPEN && currentSessionIdRef.current) {
            console.log('[Global TTS] WebSocket disconnected, reconnecting...');
            // Note: This will reconnect but might miss chunks sent while backgrounded
            // Better solution: backend should buffer chunks or allow chunk re-fetch
            await connectToSession(currentSessionIdRef.current, currentSceneId);
          }
        }
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [currentSceneId, isPlaying, isGenerating]);
  
  // ... rest of component ...
};
```

---

### Phase 2: High Priority Fixes

#### Fix 2.1: Improve Error Messages and User Feedback
**File:** `frontend/src/contexts/GlobalTTSContext.tsx`

**Changes:**
1. Detect iOS specifically and show iOS-specific instructions
2. Better error messages for common iOS issues
3. Add "Try Again" button for failed audio

**Implementation:**
```typescript
// Helper to detect iOS
const isIOS = () => {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
};

// In playNextChunk, better error handling:
.catch(err => {
  console.error('[Global TTS] Failed to play chunk:', err);
  
  let errorMessage = 'Playback failed';
  
  if (err.name === 'NotSupportedError') {
    errorMessage = isIOS() 
      ? '🎵 Audio format not supported on iOS - please contact support'
      : 'Audio format not supported';
  } else if (err.name === 'NotAllowedError') {
    errorMessage = '🔊 Audio permission needed - tap "Enable TTS" in top banner';
  } else {
    errorMessage = `Playback error: ${err.message}`;
  }
  
  setError(errorMessage);
  setAudioPermissionBlocked(true);
  isPlayingRef.current = false;
  setIsPlaying(false);
  URL.revokeObjectURL(chunk.audio_url);
});
```

---

#### Fix 2.2: Add Automatic AudioContext Resume Before Playing
**File:** `frontend/src/contexts/GlobalTTSContext.tsx`

**Changes:**
- Before playing each chunk, verify AudioContext is running
- If suspended, try to auto-resume (might work on iOS in some cases)
- If auto-resume fails, show clear message

**Implementation:**
```typescript
const playNextChunk = useCallback(async () => {
  if (audioQueueRef.current.length === 0) {
    isPlayingRef.current = false;
    setIsPlaying(false);
    return;
  }
  
  const chunk = audioQueueRef.current.shift()!;
  console.log('[Global TTS] Playing chunk', chunk.chunk_number);
  
  const context = audioContextManager.getContext();
  
  if (!context) {
    setError('Audio system not available');
    return;
  }
  
  // CRITICAL: Check state before EVERY chunk
  if (context.state === 'suspended') {
    console.warn('[Global TTS] Context suspended, attempting resume...');
    
    try {
      await context.resume();
      
      if (context.state !== 'running') {
        throw new Error('Failed to resume AudioContext');
      }
    } catch (err) {
      console.error('[Global TTS] Cannot resume AudioContext:', err);
      setError('🔊 Audio locked - please tap "Enable TTS" button in top banner');
      setAudioPermissionBlocked(true);
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }
  }
  
  // Now proceed with playback...
  chunk.audio_blob.arrayBuffer()
    .then(arrayBuffer => context.decodeAudioData(arrayBuffer))
    .then(audioBuffer => {
      // ... existing playback code ...
    })
    .catch(err => {
      // ... enhanced error handling from Fix 2.1 ...
    });
}, []);
```

---

### Phase 3: Medium Priority Fixes

#### Fix 3.1: Add Fallback to HTMLAudioElement
**File:** `frontend/src/contexts/GlobalTTSContext.tsx`

**Changes:**
1. If AudioContext consistently fails, fall back to HTMLAudioElement
2. Track failure count and switch modes
3. Show message to user about degraded experience

**Implementation:**
```typescript
const [playbackMode, setPlaybackMode] = useState<'audiocontext' | 'htmlaudio'>('audiocontext');
const audioContextFailureCount = useRef(0);

const playNextChunk = useCallback(async () => {
  // ... existing queue checks ...
  
  if (playbackMode === 'audiocontext') {
    // Try AudioContext first
    try {
      // ... existing AudioContext playback ...
    } catch (err) {
      console.error('[Global TTS] AudioContext playback failed:', err);
      audioContextFailureCount.current += 1;
      
      // After 3 failures, switch to HTMLAudioElement fallback
      if (audioContextFailureCount.current >= 3) {
        console.warn('[Global TTS] Switching to HTMLAudioElement fallback mode');
        setPlaybackMode('htmlaudio');
        setError('⚠️ Using fallback audio mode due to repeated failures');
      }
      
      // Retry this chunk with HTMLAudioElement
      audioQueueRef.current.unshift(chunk); // Put chunk back
      setPlaybackMode('htmlaudio');
      playNextChunk(); // Retry
      return;
    }
  } else {
    // Fallback: Use HTMLAudioElement
    console.log('[Global TTS] Using HTMLAudioElement fallback for chunk', chunk.chunk_number);
    
    const audio = new Audio(chunk.audio_url);
    currentAudioRef.current = audio;
    
    audio.onended = () => {
      URL.revokeObjectURL(chunk.audio_url);
      playNextChunk();
    };
    
    audio.onerror = (e) => {
      console.error('[Global TTS] HTMLAudioElement error:', e);
      URL.revokeObjectURL(chunk.audio_url);
      playNextChunk(); // Try next chunk
    };
    
    try {
      await audio.play();
      setIsPlaying(true);
      isPlayingRef.current = true;
    } catch (err) {
      console.error('[Global TTS] HTMLAudioElement play failed:', err);
      setError('🔊 Cannot play audio - check permissions');
    }
  }
}, [playbackMode]);
```

---

#### Fix 3.2: Improve WebSocket Handling for Background
**File:** `frontend/src/contexts/GlobalTTSContext.tsx`

**Changes:**
1. Detect when WebSocket disconnects due to backgrounding
2. Automatically reconnect when app returns
3. Handle missed chunks gracefully

**Implementation:**
```typescript
// Track visibility state
const wasBackgrounded = useRef(false);

useEffect(() => {
  const handleVisibilityChange = async () => {
    if (document.visibilityState === 'hidden') {
      console.log('[Global TTS] App backgrounded');
      wasBackgrounded.current = true;
    } else if (document.visibilityState === 'visible' && wasBackgrounded.current) {
      console.log('[Global TTS] App foregrounded');
      wasBackgrounded.current = false;
      
      // Reconnect WebSocket if needed
      if (currentSessionIdRef.current && currentSceneId) {
        const ws = wsRef.current;
        
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          console.log('[Global TTS] Reconnecting WebSocket after background...');
          
          // Show message to user
          setError('🔄 Reconnecting...');
          
          try {
            await connectToSession(currentSessionIdRef.current, currentSceneId);
            setError(null); // Clear reconnecting message
          } catch (err) {
            setError('Failed to reconnect - please try again');
          }
        }
        
        // Resume AudioContext
        await audioContextManager.unlock();
      }
    }
  };
  
  document.addEventListener('visibilitychange', handleVisibilityChange);
  return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
}, [currentSceneId]);
```

---

### Phase 4: Testing & Verification

#### Test Plan for iOS

**Test Devices:**
- iPhone with iOS 15+ (Safari)
- iPhone with iOS 16+ (Safari)  
- iPhone with iOS 17+ (Safari)
- iPad with latest iOS (Safari)

**Test Scenarios:**

1. **Basic Playback**
   - [ ] Click TTS button → audio plays
   - [ ] Audio plays without gaps between chunks
   - [ ] Stop button works correctly

2. **Permission Flow**
   - [ ] "Enable TTS" button appears on first visit
   - [ ] Clicking "Enable TTS" unlocks audio
   - [ ] Status changes from orange to green

3. **Backgrounding**
   - [ ] Play TTS → switch to another app → return
   - [ ] Audio resumes correctly
   - [ ] No error messages
   - [ ] WebSocket reconnects if needed

4. **Tab Switching**
   - [ ] Play TTS → switch browser tab → return
   - [ ] Audio state is correct

5. **Screen Lock**
   - [ ] Play TTS → lock screen → unlock
   - [ ] Audio resumes or shows clear resume button

6. **Interruptions**
   - [ ] Play TTS → receive phone call → end call
   - [ ] Audio resumes or shows clear message

7. **Long Sessions**
   - [ ] Play multiple scenes in a row
   - [ ] No degradation over time
   - [ ] Memory doesn't leak

8. **Error Recovery**
   - [ ] Simulate audio failure → clear error message shown
   - [ ] User can retry easily

---

### Phase 5: Backend Considerations

**Note:** Some issues might be partially backend-related:

1. **Audio Format:** Ensure backend generates iOS-compatible MP3:
   - Sample rate: 44100 Hz or 48000 Hz (iOS standard)
   - Bitrate: 128kbps or higher
   - Encoding: AAC-LC or MP3 with standard headers
   
2. **Chunk Buffering:** Consider buffering chunks on backend for X seconds after generation to support reconnection

3. **WebSocket Keep-Alive:** Send periodic ping messages to keep WebSocket alive

---

## Priority Implementation Order

1. **Fix 1.1** - AudioContext state management (CRITICAL)
2. **Fix 1.2** - Improved unlock mechanism (CRITICAL)
3. **Fix 1.3** - Lifecycle handlers (CRITICAL)
4. **Fix 2.1** - Better error messages (HIGH)
5. **Fix 2.2** - Auto-resume before playback (HIGH)
6. **Fix 3.1** - HTMLAudioElement fallback (MEDIUM)
7. **Fix 3.2** - WebSocket reconnection (MEDIUM)
8. **Phase 4** - Testing on real iOS devices
9. **Phase 5** - Backend improvements (if needed)

---

## Success Metrics

- [ ] TTS works on iOS Safari without manual intervention
- [ ] TTS survives app backgrounding/foregrounding
- [ ] Clear error messages guide users when issues occur
- [ ] No audio gaps or stuttering
- [ ] Memory usage remains stable over long sessions

---

## Known Limitations (Post-Fix)

Even after fixes, iOS has inherent limitations:
1. **Background playback**: iOS will stop audio if app is backgrounded for extended periods
2. **Memory pressure**: iOS might kill AudioContext under memory pressure
3. **Silent mode switch**: iOS silent mode switch affects audio playback

These are iOS platform limitations and should be documented for users.

---

## Next Steps

1. Review this plan with the team
2. Implement Phase 1 fixes (critical)
3. Test on iOS devices
4. Iterate based on test results
5. Deploy and monitor

---

**Document Version:** 1.0  
**Created:** 2025-11-02  
**Last Updated:** 2025-11-02




