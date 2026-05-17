'use client';

import React, { createContext, useContext, useRef, useState, useCallback, useEffect } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { audioContextManager } from '@/utils/audioContextManager';
import { nativeTTSPlayer } from '@/utils/nativeTTS';
import { getAuthToken } from '@/utils/jwt';

interface TTSMessage {
  type: string;
  // chunk_ready (legacy / non-streaming providers)
  chunk_number?: number;
  total_chunks?: number;
  audio_base64?: string;
  text_preview?: string;
  // stream_start / frame / stream_end (PCM frame streaming, e.g. Qwen3)
  stream_id?: string;
  format?: string;
  sample_rate?: number;
  channels?: number;
  bits_per_sample?: number;
  seq?: number;
  pcm_base64?: string;
  frames_sent?: number;
  total_bytes?: number;
  // progress / complete / error
  progress_percent?: number;
  chunks_ready?: number;
  message?: string;
}

interface GlobalTTSContextType {
  // State
  isPlaying: boolean;
  isPaused: boolean;       // true only on native iOS path; pause is a no-op for web (we stop instead)
  isGenerating: boolean;
  currentSceneId: number | null;
  currentSessionId: string | null;
  progress: number;
  totalChunks: number;
  chunksReceived: number;
  error: string | null;
  // True when the active audio engine supports real pause/resume.
  // UI uses this to show pause-icon-toggle vs stop-only.
  supportsPause: boolean;

  // Actions
  playScene: (sceneId: number) => Promise<void>;
  connectToSession: (sessionId: string, sceneId: number) => Promise<void>;
  stop: () => void;
  pause: () => void;
  resume: () => void;
  clearError: () => void;
}

const GlobalTTSContext = createContext<GlobalTTSContextType | undefined>(undefined);

export const useGlobalTTS = () => {
  const context = useContext(GlobalTTSContext);
  if (!context) {
    throw new Error('useGlobalTTS must be used within GlobalTTSProvider');
  }
  return context;
};

interface GlobalTTSProviderProps {
  children: React.ReactNode;
}

/**
 * Global TTS Context Provider
 * 
 * Uses Web Audio API (AudioContext) for reliable iOS playback.
 * Manages TTS state and WebSocket connections globally.
 */
export const GlobalTTSProvider: React.FC<GlobalTTSProviderProps> = ({ children }) => {
  // State
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentSceneId, setCurrentSceneId] = useState<number | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);
  const [chunksReceived, setChunksReceived] = useState(0);
  const [error, setError] = useState<string | null>(null);
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const isPlayingRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(null);
  const hasStartedPlayback = useRef(false);
  const generationCompleteRef = useRef(false);
  /**
   * Refresh the user's pre-buffer setting before starting playback.
   * Cheap (~50 ms) and tolerates failure (falls back to last known value).
   * Writes the value into the audioContextManager singleton so both
   * GlobalTTSContext AND useTTSWebSocket consumers pick it up without
   * additional wiring at every call site.
   */
  const refreshPlaybackBufferSetting = useCallback(async () => {
    try {
      const token = getAuthToken();
      if (!token) return;
      const resp = await fetch(`${await getApiBaseUrl()}/api/tts/settings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        const value = data?.playback_buffer_seconds;
        if (typeof value === 'number' && value >= 0 && value <= 10) {
          audioContextManager.setDefaultBufferAheadSeconds(value);
          console.log(`[Global TTS] playback_buffer_seconds = ${value}`);
        }
      }
    } catch (e) {
      // Don't break playback if settings fetch fails — use cached/default value.
      console.warn('[Global TTS] Failed to refresh playback buffer setting:', e);
    }
  }, []);
  
  /**
   * Handle playback end - called when all queued audio finishes
   */
  const handlePlaybackEnd = useCallback(() => {
    console.log('[Global TTS] All playback ended');
    setIsPlaying(false);
    setIsPaused(false);
    isPlayingRef.current = false;
  }, []);
  
  /**
   * Queue an audio chunk for playback using AudioContext
   */
  const queueAudioChunk = useCallback(async (audioBase64: string, chunkNumber: number) => {
    try {
      // Convert base64 to ArrayBuffer
      const arrayBuffer = audioContextManager.base64ToArrayBuffer(audioBase64);
      
      // Queue for gapless playback
      const result = await audioContextManager.queueBuffer(arrayBuffer);
      console.log(`[Global TTS] Queued chunk ${chunkNumber}, duration: ${result.duration.toFixed(2)}s`);
      
      // Start playback tracking if this is the first chunk
      if (!isPlayingRef.current) {
        setIsPlaying(true);
        isPlayingRef.current = true;
        hasStartedPlayback.current = true;
        
        // Set up callback for when all audio finishes
        audioContextManager.setOnPlaybackEnd(() => {
          // Only trigger end if generation is complete
          if (generationCompleteRef.current) {
            handlePlaybackEnd();
          }
        });
      }
      
    } catch (err) {
      console.error('[Global TTS] Failed to queue audio chunk:', err);
      const errorMsg = err instanceof Error ? err.message : 'Failed to play audio chunk';
      
      // Check if this is an AudioContext permission issue
      if (errorMsg.includes('user gesture') || errorMsg.includes('not ready')) {
        setError('Audio not enabled. Please tap the audio button to enable TTS.');
      } else {
        setError(errorMsg);
      }
    }
  }, [handlePlaybackEnd]);
  
  /**
   * Handle WebSocket messages
   */
  const handleWebSocketMessage = useCallback((message: TTSMessage) => {
    console.log('[Global TTS] Received message:', message.type);
    
    switch (message.type) {
      case 'chunk_ready':
        if (message.audio_base64 && message.chunk_number) {
          // Queue for playback via AudioContext
          queueAudioChunk(message.audio_base64, message.chunk_number);
          setChunksReceived(prev => prev + 1);
        }

        if (message.total_chunks) {
          setTotalChunks(message.total_chunks);
        }
        break;

      case 'stream_start':
        if (message.stream_id && message.sample_rate) {
          const fmt = {
            sampleRate: message.sample_rate,
            channels: message.channels ?? 1,
            bitsPerSample: message.bits_per_sample ?? 16,
          };
          if (nativeTTSPlayer.isAvailable()) {
            // iOS Capacitor — route through the AVAudioEngine plugin.
            const sceneId = currentSceneId;
            (async () => {
              try {
                await nativeTTSPlayer.beginStream(message.stream_id!, fmt);
                await nativeTTSPlayer.setMetadata({
                  title: sceneId != null ? `Scene ${sceneId}` : 'Reading',
                  album: 'Saga',
                });
              } catch (err) {
                console.error('[Global TTS] Native beginStream failed:', err);
                setError('Audio engine init failed');
              }
            })();
          } else {
            // No explicit buffer override — beginPcmStream uses the
            // singleton default set via setDefaultBufferAheadSeconds()
            // from refreshPlaybackBufferSetting(). Both code paths
            // (this context and useTTSWebSocket hook) share the value.
            audioContextManager.beginPcmStream(message.stream_id, fmt);
          }
          if (message.total_chunks) {
            setTotalChunks(message.total_chunks);
          }
        }
        break;

      case 'frame':
        if (message.stream_id && message.pcm_base64) {
          if (nativeTTSPlayer.isAvailable()) {
            (async () => {
              try {
                await nativeTTSPlayer.queueFrame(message.stream_id!, message.pcm_base64!);
                if (!isPlayingRef.current) {
                  setIsPlaying(true);
                  isPlayingRef.current = true;
                  hasStartedPlayback.current = true;
                  // Native side fires the 'playbackEnded' event when its
                  // drain completes; wired in the useEffect below.
                }
              } catch (err) {
                console.error('[Global TTS] Native frame failed:', err);
              }
            })();
          } else {
            (async () => {
              try {
                const arrayBuffer = audioContextManager.base64ToArrayBuffer(message.pcm_base64!);
                await audioContextManager.queuePcmFrame(message.stream_id!, arrayBuffer);
                if (!isPlayingRef.current) {
                  setIsPlaying(true);
                  isPlayingRef.current = true;
                  hasStartedPlayback.current = true;
                  audioContextManager.setOnPlaybackEnd(() => {
                    if (generationCompleteRef.current) handlePlaybackEnd();
                  });
                }
              } catch (err) {
                console.error('[Global TTS] PCM frame failed:', err);
                const msg = err instanceof Error ? err.message : 'PCM frame error';
                if (msg.includes('user gesture') || msg.includes('not ready')) {
                  setError('Audio not enabled. Please tap the audio button to enable TTS.');
                }
              }
            })();
          }
        }
        break;

      case 'stream_end':
        if (message.stream_id) {
          if (nativeTTSPlayer.isAvailable()) {
            void nativeTTSPlayer.endStream(message.stream_id);
          } else {
            audioContextManager.endPcmStream(message.stream_id);
          }
          setChunksReceived(prev => prev + 1);
        }
        break;

      case 'progress':
        if (message.progress_percent !== undefined) {
          setProgress(message.progress_percent);
        }
        break;
        
      case 'complete':
        console.log('[Global TTS] Generation complete');
        setIsGenerating(false);
        setProgress(100);
        generationCompleteRef.current = true;
        
        // If no chunks were received, trigger end now
        if (!hasStartedPlayback.current) {
          handlePlaybackEnd();
        }
        // Otherwise, playback will end via AudioContext callback
        break;
        
      case 'error':
        console.error('[Global TTS] Error:', message.message);
        // Check if this is a chunk-specific error or a fatal error
        const errorMsg = message.message || 'Unknown error';
        const isChunkError = errorMsg.toLowerCase().includes('chunk');
        
        if (isChunkError) {
          // For chunk errors, log but don't stop - continue with other chunks
          console.warn('[Global TTS] Chunk error (continuing):', errorMsg);
          // Only set error state if we haven't received any successful chunks
          if (!hasStartedPlayback.current) {
            setError(errorMsg);
          }
        } else {
          // For fatal errors, stop everything
          setError(errorMsg);
          setIsGenerating(false);
          setIsPlaying(false);
          isPlayingRef.current = false;
        }
        break;
    }
  }, [queueAudioChunk, handlePlaybackEnd]);
  
  /**
   * Connect to existing TTS session (for auto-play or manual)
   */
  const connectToSession = useCallback(async (sessionId: string, sceneId: number) => {
    console.log('[Global TTS] Connecting to session:', sessionId, 'for scene:', sceneId);

    // Refresh setting in the background — never await; consumed at
    // stream_start which arrives after WS connects.
    refreshPlaybackBufferSetting();

    // If already connected to this session, don't reconnect
    if (currentSessionIdRef.current === sessionId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[Global TTS] Already connected to session:', sessionId, '- skipping reconnect');
      return;
    }
    
    // Close existing connection if connecting to different session
    if (wsRef.current && currentSessionIdRef.current !== sessionId) {
      console.log('[Global TTS] Closing previous session:', currentSessionIdRef.current);
      wsRef.current.close();
    }
    
    // Stop any current AudioContext playback
    audioContextManager.stopAll();
    
    // Clear state
    setError(null);
    setProgress(0);
    setChunksReceived(0);
    setTotalChunks(0);
    setCurrentSceneId(sceneId);
    setCurrentSessionId(sessionId);
    currentSessionIdRef.current = sessionId;
    setIsGenerating(true);
    hasStartedPlayback.current = false;
    generationCompleteRef.current = false;
    
    // Reset the queue for fresh playback
    audioContextManager.resetQueue();

    // CRITICAL ORDERING: kick off AudioContext.unlock() but DON'T await
    // it before opening the WebSocket. iOS can leave the audio session
    // in `interrupted` state where `context.resume()` hangs forever —
    // if we await unlock first, the backend's WS-connect timer expires
    // before the WS even opens. The WS handshake doesn't need an
    // unlocked AudioContext — only audio playback does. queueBuffer
    // will buffer chunks until unlock resolves; if unlock truly never
    // completes the audio just won't play, but the WS lifecycle stays
    // clean so the user sees a real failure instead of a silent timeout.
    audioContextManager.unlock().then(isUnlocked => {
      if (!isUnlocked) {
        console.warn('[Global TTS] AudioContext not unlocked - audio may not play');
      } else {
        console.log('[Global TTS] AudioContext unlocked');
      }
    }).catch(err => {
      console.warn('[Global TTS] AudioContext unlock errored (continuing):', err);
    });

    // Get API URL
    const apiUrl = await getApiBaseUrl();
    console.log('[Global TTS] API URL:', apiUrl);

    // Connect WebSocket
    const wsUrl = `${apiUrl.replace('http', 'ws')}/ws/tts/${sessionId}`;
    console.log('[Global TTS] WebSocket URL:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    
    ws.onopen = () => {
      console.log('[Global TTS] WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      try {
        const message: TTSMessage = JSON.parse(event.data);
        handleWebSocketMessage(message);
      } catch (err) {
        console.error('[Global TTS] Failed to parse message:', err);
      }
    };
    
    ws.onerror = (error) => {
      console.error('[Global TTS] WebSocket error:', error);
      setError('WebSocket connection failed');
      setIsGenerating(false);
    };
    
    ws.onclose = (event) => {
      console.log('[Global TTS] WebSocket disconnected. Code:', event.code, 'Reason:', event.reason);
      
      // Handle session not found/expired
      if (event.code === 1008 || event.code === 1011 || event.reason?.includes('not found') || event.reason?.includes('expired')) {
        setError('TTS session expired or not found');
      } else if (event.code === 1006) {
        setError('Connection lost - check your network');
      } else if (event.code !== 1000) {
        setError(`Connection closed (${event.code}) - please try again`);
      }
      
      setIsGenerating(false);
    };
  }, [handleWebSocketMessage]);
  
  /**
   * Start manual TTS generation for a scene
   */
  const playScene = useCallback(async (sceneId: number) => {
    console.log('[Global TTS] Starting manual TTS for scene:', sceneId);

    // CRITICAL iOS FIX: kick off AudioContext unlock SYNCHRONOUSLY at the
    // top of this handler, BEFORE any await. iOS Safari only treats the
    // synchronous code path from the user click as a "user gesture" —
    // any audio.play() / context.resume() call after the first await is
    // outside the gesture window and gets silently rejected, leaving
    // the audio session in `interrupted` mode (chunks flow but produce
    // no sound). Don't await — let it run in parallel with the POST.
    audioContextManager.unlock().catch(err => {
      console.warn('[Global TTS] Pre-unlock errored (continuing):', err);
    });

    // Refresh the user's pre-buffer setting in the background — DO NOT
    // await. The new value is consumed at stream_start (later), and
    // awaiting here would delay the POST + WS connect, which the backend
    // times out after ~10s.
    refreshPlaybackBufferSetting();

    try {
      // Get API URL
      const apiUrl = await getApiBaseUrl();
      console.log('[Global TTS] API URL:', apiUrl);
      
      // Create TTS session
      const response = await fetch(`${apiUrl}/api/tts/generate-ws/${sceneId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getAuthToken()}`
        }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      console.log('[Global TTS] Session created:', data.session_id);
      
      // Connect to the session
      await connectToSession(data.session_id, sceneId);
    } catch (err) {
      console.error('[Global TTS] Failed to start TTS:', err);
      setError(err instanceof Error ? err.message : 'Failed to start TTS');
      setIsGenerating(false);
    }
  }, [connectToSession]);
  
  /**
   * Stop playback
   */
  const stop = useCallback(() => {
    console.log('[Global TTS] Stopping playback');
    
    // Send cancel message to backend if WebSocket is open
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        console.log('[Global TTS] Sending cancel message to backend');
        wsRef.current.send(JSON.stringify({ type: 'cancel' }));
      } catch (err) {
        console.warn('[Global TTS] Failed to send cancel message:', err);
      }
    }
    
    // Stop audio playback (native plugin or Web Audio path)
    if (nativeTTSPlayer.isAvailable()) {
      void nativeTTSPlayer.stop();
    } else {
      audioContextManager.stopAll();
      audioContextManager.setOnPlaybackEnd(null);
    }
    
    // Close WebSocket (with small delay to ensure cancel message is sent)
    if (wsRef.current) {
      const ws = wsRef.current;
      wsRef.current = null;
      
      setTimeout(() => {
        try {
          ws.close();
        } catch (err) {
          console.warn('[Global TTS] Error closing WebSocket:', err);
        }
      }, 100);
    }
    
    // Reset state
    isPlayingRef.current = false;
    setIsPlaying(false);
    setIsPaused(false);
    setIsGenerating(false);
    setProgress(0);
    setChunksReceived(0);
    setTotalChunks(0);
    setCurrentSceneId(null);
    setCurrentSessionId(null);
    currentSessionIdRef.current = null;
    hasStartedPlayback.current = false;
    generationCompleteRef.current = false;
    setError(null);
  }, []);
  
  /**
   * Clear error state without stopping playback
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);
  
  /**
   * Pause playback
   * Note: With AudioContext scheduled buffers, true pause isn't possible.
   * This effectively stops playback. Use stop() and re-generate to restart.
   */
  const pause = useCallback(() => {
    if (nativeTTSPlayer.isAvailable()) {
      // Real pause — playback resumes from the same sample on resume().
      console.log('[Global TTS] Pause requested (native, retains buffers)');
      void nativeTTSPlayer.pause();
      setIsPlaying(false);
      isPlayingRef.current = false;
      setIsPaused(true);
    } else {
      // Web Audio path can't pause scheduled buffers — fall back to stop.
      // resume() on web is a no-op; the user has to tap Play to restart
      // from the beginning.
      console.log('[Global TTS] Pause requested (web, effectively stop)');
      audioContextManager.stopAll();
      setIsPlaying(false);
      isPlayingRef.current = false;
    }
  }, []);
  
  /**
   * Resume playback
   * Note: With AudioContext, we can't resume from where we paused.
   * User needs to regenerate audio to continue.
   */
  const resume = useCallback(() => {
    if (nativeTTSPlayer.isAvailable()) {
      console.log('[Global TTS] Resume requested (native)');
      void nativeTTSPlayer.resume();
      setIsPaused(false);
      setIsPlaying(true);
      isPlayingRef.current = true;
    }
    // Web Audio path can't resume scheduled buffers — see pause() comment.
  }, []);
  
  // Wire native plugin events when running inside iOS Capacitor.
  // Mirrors what audioContextManager.setOnPlaybackEnd does for Web Audio.
  useEffect(() => {
    if (!nativeTTSPlayer.isAvailable()) return;
    let endedHandle: { remove: () => Promise<void> } | undefined;
    let remoteHandle: { remove: () => Promise<void> } | undefined;

    (async () => {
      endedHandle = await nativeTTSPlayer.onPlaybackEnded(() => {
        // Native drain completed. Fire end only when generation is also
        // complete — protects against firing on a transient drain
        // between stream chunks before the WS sends 'complete'.
        if (generationCompleteRef.current) {
          handlePlaybackEnd();
        }
      });
      remoteHandle = await nativeTTSPlayer.onRemoteCommand((action) => {
        // Lock-screen / AirPods / CarPlay buttons. Web Audio doesn't
        // truly support pause/resume of scheduled buffers; treat all
        // three as stop. Future enhancement: native could expose a
        // proper pause + resume that retains scheduled buffers.
        if (action === 'play' || action === 'pause' || action === 'stop' || action === 'togglePlayPause') {
          stop();
        }
      });
    })();

    return () => {
      void endedHandle?.remove();
      void remoteHandle?.remove();
    };
  }, [handlePlaybackEnd, stop]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);
  
  const value: GlobalTTSContextType = {
    isPlaying,
    isPaused,
    isGenerating,
    currentSceneId,
    currentSessionId,
    progress,
    totalChunks,
    chunksReceived,
    error,
    supportsPause: nativeTTSPlayer.isAvailable(),
    playScene,
    connectToSession,
    stop,
    pause,
    resume,
    clearError
  };
  
  return (
    <GlobalTTSContext.Provider value={value}>
      {children}
    </GlobalTTSContext.Provider>
  );
};
