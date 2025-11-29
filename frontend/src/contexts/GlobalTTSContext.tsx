'use client';

import React, { createContext, useContext, useRef, useState, useCallback, useEffect } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { audioContextManager } from '@/utils/audioContextManager';

interface TTSMessage {
  type: string;
  chunk_number?: number;
  total_chunks?: number;
  audio_base64?: string;
  text_preview?: string;
  progress_percent?: number;
  chunks_ready?: number;
  message?: string;
}

interface GlobalTTSContextType {
  // State
  isPlaying: boolean;
  isGenerating: boolean;
  currentSceneId: number | null;
  currentSessionId: string | null;
  progress: number;
  totalChunks: number;
  chunksReceived: number;
  error: string | null;
  
  // Actions
  playScene: (sceneId: number) => Promise<void>;
  connectToSession: (sessionId: string, sceneId: number) => Promise<void>;
  stop: () => void;
  pause: () => void;
  resume: () => void;
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
   * Handle playback end - called when all queued audio finishes
   */
  const handlePlaybackEnd = useCallback(() => {
    console.log('[Global TTS] All playback ended');
    setIsPlaying(false);
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
    
    // Ensure AudioContext is ready
    const isReady = await audioContextManager.ensureReady();
    if (!isReady) {
      console.warn('[Global TTS] AudioContext not ready - user may need to tap unlock button');
    }
    
    // Reset the queue for fresh playback
    audioContextManager.resetQueue();
    
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
    
    try {
      // Get API URL
      const apiUrl = await getApiBaseUrl();
      console.log('[Global TTS] API URL:', apiUrl);
      
      // Create TTS session
      const response = await fetch(`${apiUrl}/api/tts/generate-ws/${sceneId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
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
    
    // Stop AudioContext playback
    audioContextManager.stopAll();
    audioContextManager.setOnPlaybackEnd(null);
    
    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    // Reset state
    isPlayingRef.current = false;
    setIsPlaying(false);
    setIsGenerating(false);
    setProgress(0);
    setChunksReceived(0);
    setTotalChunks(0);
    setCurrentSceneId(null);
    setCurrentSessionId(null);
    currentSessionIdRef.current = null;
    hasStartedPlayback.current = false;
    generationCompleteRef.current = false;
  }, []);
  
  /**
   * Pause playback
   * Note: With AudioContext scheduled buffers, true pause isn't possible.
   * This effectively stops playback. Use stop() and re-generate to restart.
   */
  const pause = useCallback(() => {
    console.log('[Global TTS] Pause requested (stopping AudioContext playback)');
    // AudioContext scheduled buffers can't be paused, only stopped
    audioContextManager.stopAll();
    setIsPlaying(false);
    isPlayingRef.current = false;
  }, []);
  
  /**
   * Resume playback
   * Note: With AudioContext, we can't resume from where we paused.
   * User needs to regenerate audio to continue.
   */
  const resume = useCallback(() => {
    console.log('[Global TTS] Resume not supported with AudioContext - please regenerate audio');
    // Can't resume scheduled AudioContext buffers
    // Would need to track position and re-queue remaining chunks
  }, []);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);
  
  const value: GlobalTTSContextType = {
    isPlaying,
    isGenerating,
    currentSceneId,
    currentSessionId,
    progress,
    totalChunks,
    chunksReceived,
    error,
    playScene,
    connectToSession,
    stop,
    pause,
    resume
  };
  
  return (
    <GlobalTTSContext.Provider value={value}>
      {children}
    </GlobalTTSContext.Provider>
  );
};
