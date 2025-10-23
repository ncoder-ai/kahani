'use client';

import React, { createContext, useContext, useRef, useState, useCallback, useEffect } from 'react';
import { useAutoplayPermission } from '@/hooks/useAutoplayPermission';

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

interface AudioChunk {
  chunk_number: number;
  audio_blob: Blob;
  audio_url: string;
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
  apiBaseUrl: string;
}

export const GlobalTTSProvider: React.FC<GlobalTTSProviderProps> = ({ children, apiBaseUrl }) => {
  // Autoplay permission
  const { hasPermission } = useAutoplayPermission();
  
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
  const audioQueueRef = useRef<AudioChunk[]>([]);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(null);
  
  /**
   * Convert base64 to Blob
   */
  const base64ToBlob = useCallback((base64: string, mimeType: string = 'audio/mp3'): Blob => {
    const base64Data = base64.includes(',') ? base64.split(',')[1] : base64;
    const binaryString = window.atob(base64Data);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return new Blob([bytes], { type: mimeType });
  }, []);
  
  /**
   * Play next chunk in queue
   */
  const playNextChunk = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }
    
    const chunk = audioQueueRef.current.shift()!;
    console.log('[Global TTS] Playing chunk', chunk.chunk_number);
    
    const audio = new Audio(chunk.audio_url);
    currentAudioRef.current = audio;
    
    audio.onended = () => {
      console.log('[Global TTS] Chunk', chunk.chunk_number, 'ended');
      URL.revokeObjectURL(chunk.audio_url);
      playNextChunk();
    };
    
    audio.onerror = (e) => {
      console.error('[Global TTS] Audio playback error:', e);
      setError('Audio playback failed');
      isPlayingRef.current = false;
      setIsPlaying(false);
    };
    
    audio.play().then(() => {
      console.log('[Global TTS] Chunk', chunk.chunk_number, 'playing');
      setIsPlaying(true);
      isPlayingRef.current = true;
    }).catch(err => {
      console.error('[Global TTS] Failed to play chunk:', err);
      
      // Check if this is an autoplay permission issue
      if (err.name === 'NotAllowedError' && !hasPermission) {
        setError('Please enable audio autoplay in the banner above');
      } else {
        setError(`Playback failed: ${err.message}`);
      }
      
      isPlayingRef.current = false;
      setIsPlaying(false);
    });
  }, [hasPermission]);
  
  /**
   * Handle WebSocket messages
   */
  const handleWebSocketMessage = useCallback((message: TTSMessage) => {
    console.log('[Global TTS] Received message:', message.type);
    
    switch (message.type) {
      case 'chunk_ready':
        if (message.audio_base64 && message.chunk_number) {
          const blob = base64ToBlob(message.audio_base64);
          const url = URL.createObjectURL(blob);
          
          const chunk: AudioChunk = {
            chunk_number: message.chunk_number,
            audio_blob: blob,
            audio_url: url
          };
          
          audioQueueRef.current.push(chunk);
          setChunksReceived(prev => prev + 1);
          
          // Start playing if not already playing
          if (!isPlayingRef.current) {
            playNextChunk();
          }
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
        // Note: isPlaying will be set to false by playNextChunk when queue is empty
        break;
        
      case 'error':
        console.error('[Global TTS] Error:', message.message);
        setError(message.message || 'Unknown error');
        setIsGenerating(false);
        break;
    }
  }, [base64ToBlob, playNextChunk]);
  
  /**
   * Connect to existing TTS session
   */
  const connectToSession = useCallback(async (sessionId: string, sceneId: number, isManual = false) => {
    console.log('[Global TTS] Connecting to session:', sessionId, 'for scene:', sceneId, isManual ? '(manual)' : '(auto)');
    
    // If already connected to this session, don't reconnect
    if (currentSessionIdRef.current === sessionId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[Global TTS] Already connected to session:', sessionId, '- skipping reconnect');
      return;
    }
    
    // If already playing or generating this scene, don't reconnect
    if (currentSceneId === sceneId && (isPlaying || isGenerating)) {
      console.log('[Global TTS] Already playing/generating scene:', sceneId, '- skipping reconnect');
      return;
    }
    
    // Stop any existing audio and close WebSocket if connecting to different session
    if (wsRef.current && currentSessionIdRef.current !== sessionId) {
      console.log('[Global TTS] Closing previous session:', currentSessionIdRef.current);
      wsRef.current.close();
    }
    
    // Stop any currently playing audio to prevent overlap
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    
    // Clear audio queue and revoke URLs to prevent memory leaks
    audioQueueRef.current.forEach(chunk => URL.revokeObjectURL(chunk.audio_url));
    audioQueueRef.current = [];
    
    // Clear state
    setError(null);
    setProgress(0);
    setChunksReceived(0);
    setTotalChunks(0);
    setCurrentSceneId(sceneId);
    setCurrentSessionId(sessionId);
    currentSessionIdRef.current = sessionId; // Update ref
    setIsGenerating(true);
    
    // Only check autoplay permission for automatic TTS, not manual
    if (!isManual && !hasPermission) {
      console.log('[Global TTS] Autoplay not enabled - skipping automatic audio generation');
      setIsGenerating(false);
      return;
    }
    
    // Establish autoplay permission for mobile browsers
    try {
      const silentAudio = new Audio('data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAADhAC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7///////////////////////////////////////////////////////////////////////////AAAA5TEFNRTMuMTAwBK8AAAAAAAAAABUgJAU9QgAAgAAABITMLqMCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sQZAAP8AAAaQAAAAgAAA0gAAABAAABpAAAACAAADSAAAAETEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV');
      silentAudio.volume = 0.01;
      silentAudio.muted = true;
      
      // Try to play immediately (this should work since user just clicked)
      const playPromise = silentAudio.play();
      if (playPromise !== undefined) {
        await playPromise;
        console.log('[Global TTS] Autoplay permission established');
      }
    } catch (err) {
      console.warn('[Global TTS] Autoplay permission may be blocked:', err);
      // Continue anyway - user might have already granted permission
    }
    
    // Connect WebSocket
    const wsUrl = `${apiBaseUrl.replace('http', 'ws')}/ws/tts/${sessionId}`;
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
      
      // Handle session not found/expired (code 1008 or 1011 typically)
      if (event.code === 1008 || event.code === 1011 || event.reason?.includes('not found') || event.reason?.includes('expired')) {
        setError('TTS session expired or not found');
        console.warn('[Global TTS] Session expired or not found');
      }
      
      setIsGenerating(false);
    };
  }, [apiBaseUrl, handleWebSocketMessage, currentSceneId, isPlaying, isGenerating]);
  
  /**
   * Stop playback
   */
  const stop = useCallback(() => {
    console.log('[Global TTS] Stopping playback');
    
    // Stop current audio
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    
    // Clear queue
    audioQueueRef.current.forEach(chunk => URL.revokeObjectURL(chunk.audio_url));
    audioQueueRef.current = [];
    
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
    currentSessionIdRef.current = null; // Clear ref
  }, []);
  
  /**
   * Pause playback
   */
  const pause = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      setIsPlaying(false);
      isPlayingRef.current = false;
    }
  }, []);
  
  /**
   * Resume playback
   */
  const resume = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.play();
      setIsPlaying(true);
      isPlayingRef.current = true;
    }
  }, []);
  
  /**
   * Start manual TTS generation for a scene
   */
  const playScene = useCallback(async (sceneId: number) => {
    console.log('[Global TTS] Starting manual TTS for scene:', sceneId);
    
    // Stop any existing playback first to prevent audio overlap
    stop();
    
    try {
      // Create TTS session (use WebSocket endpoint)
      const response = await fetch(`${apiBaseUrl}/api/tts/generate-ws/${sceneId}`, {
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
      
      // Connect to the session (manual TTS - bypass autoplay check)
      await connectToSession(data.session_id, sceneId, true);
    } catch (err) {
      console.error('[Global TTS] Failed to start TTS:', err);
      setError(err instanceof Error ? err.message : 'Failed to start TTS');
    }
  }, [apiBaseUrl, connectToSession, stop]);
  
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
