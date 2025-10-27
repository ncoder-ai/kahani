'use client';

import React, { createContext, useContext, useRef, useState, useCallback, useEffect, useMemo } from 'react';
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
  browserBlockedAutoplay: boolean;
  audioPermissionBlocked: boolean;
  debugLogs: string[];
  
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
  // Fix localhost URL when running on mobile/network
  const actualApiUrl = useMemo(() => {
    // If URL contains localhost, replace with actual hostname from browser
    if (apiBaseUrl.includes('localhost') && typeof window !== 'undefined') {
      const protocol = window.location.protocol;
      const hostname = window.location.hostname;
      const port = apiBaseUrl.match(/:(\d+)/)?.[1] || '9876';
      const fixedUrl = `${protocol}//${hostname}:${port}`;
      console.log('[Global TTS] Fixed localhost URL:', apiBaseUrl, '→', fixedUrl);
      return fixedUrl;
    }
    return apiBaseUrl;
  }, [apiBaseUrl]);
  
  // State
  const [isPlaying, setIsPlaying] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentSceneId, setCurrentSceneId] = useState<number | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);
  const [chunksReceived, setChunksReceived] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [browserBlockedAutoplay, setBrowserBlockedAutoplay] = useState(false);
  const [audioPermissionBlocked, setAudioPermissionBlocked] = useState(false);
  const [debugLogs, setDebugLogs] = useState<string[]>([]);
  
  // Debug logging helper
  const addDebugLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `${timestamp}: ${message}`;
    setDebugLogs(prev => [...prev.slice(-19), logEntry]); // Keep last 20 logs
    console.log('[Global TTS]', message);
  }, []);
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const audioQueueRef = useRef<AudioChunk[]>([]);
  const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const isPlayingRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(null);
  
  // Check AudioContext unlock status on mount
  useEffect(() => {
    const checkUnlock = () => {
      const unlocked = audioContextManager.isAudioUnlocked();
      if (unlocked) {
        setAudioPermissionBlocked(false);
      }
    };
    checkUnlock();
    // Check periodically in case user unlocks later
    const interval = setInterval(checkUnlock, 1000);
    return () => clearInterval(interval);
  }, []);
  
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
   * Play next chunk in queue using AudioContext
   */
  const playNextChunk = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }
    
    const chunk = audioQueueRef.current.shift()!;
    console.log('[Global TTS] Playing chunk', chunk.chunk_number);
    
    const context = audioContextManager.getContext();
    
    // Check if AudioContext is unlocked
    if (!context || !audioContextManager.isAudioUnlocked()) {
      console.error('[Global TTS] AudioContext not unlocked');
      setError('🔊 Audio locked - click "Enable TTS" button in top banner first');
      setAudioPermissionBlocked(true);
      setBrowserBlockedAutoplay(true);
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }
    
    // Decode audio from blob and play through AudioContext
    chunk.audio_blob.arrayBuffer()
      .then(arrayBuffer => {
        return context.decodeAudioData(arrayBuffer);
      })
      .then(audioBuffer => {
        console.log('[Global TTS] AudioBuffer decoded:', {
          duration: audioBuffer.duration,
          sampleRate: audioBuffer.sampleRate,
          numberOfChannels: audioBuffer.numberOfChannels,
          contextState: context.state
        });
        
        // Create gain node for volume control
        const gainNode = context.createGain();
        gainNode.gain.value = 1.0; // Full volume
        
        // Create audio source
        const source = context.createBufferSource();
        source.buffer = audioBuffer;
        
        // Connect: source → gain → destination
        source.connect(gainNode);
        gainNode.connect(context.destination);
        currentAudioSourceRef.current = source;
        
        // Handle end of playback
        source.onended = () => {
          console.log('[Global TTS] Chunk', chunk.chunk_number, 'ended');
          URL.revokeObjectURL(chunk.audio_url);
          currentAudioSourceRef.current = null;
          playNextChunk(); // Play next chunk
        };
        
        // Start playback
        source.start(0);
        console.log('[Global TTS] Chunk', chunk.chunk_number, 'playing via AudioContext at full volume');
        console.log('[Global TTS] AudioContext state:', context.state);
        setIsPlaying(true);
        isPlayingRef.current = true;
        setBrowserBlockedAutoplay(false);
        setAudioPermissionBlocked(false);
      })
      .catch(err => {
        console.error('[Global TTS] Failed to play chunk:', err);
        setError(`Playback failed: ${err.message}`);
        isPlayingRef.current = false;
        setIsPlaying(false);
        URL.revokeObjectURL(chunk.audio_url);
      });
  }, []);
  
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
        break;
        
      case 'error':
        console.error('[Global TTS] Error:', message.message);
        setError(message.message || 'Unknown error');
        setIsGenerating(false);
        break;
    }
  }, [base64ToBlob, playNextChunk]);
  
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
    
    // If already playing or generating this scene, don't reconnect
    if (currentSceneId === sceneId && (isPlaying || isGenerating)) {
      console.log('[Global TTS] Already playing/generating scene:', sceneId, '- skipping reconnect');
      return;
    }
    
    // Close existing connection if connecting to different session
    if (wsRef.current && currentSessionIdRef.current !== sessionId) {
      console.log('[Global TTS] Closing previous session:', currentSessionIdRef.current);
      wsRef.current.close();
    }
    
    // Clear state
    audioQueueRef.current = [];
    setError(null);
    setProgress(0);
    setChunksReceived(0);
    setTotalChunks(0);
    setCurrentSceneId(sceneId);
    setCurrentSessionId(sessionId);
    currentSessionIdRef.current = sessionId; // Update ref
    setIsGenerating(true);
    setBrowserBlockedAutoplay(false); // Clear any previous block state
    
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
    const wsProtocol = actualApiUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = actualApiUrl.replace(/^https?:\/\//, '');
    const wsUrl = `${wsProtocol}://${wsHost}/ws/tts/${sessionId}`;
    console.log('[Global TTS] WebSocket URL:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    
    // Set a timeout for WebSocket connection
    const connectionTimeout = setTimeout(() => {
      if (ws.readyState === WebSocket.CONNECTING) {
        console.error('[Global TTS] WebSocket connection timeout');
        ws.close();
        setError('Connection timeout - please try again');
        setIsGenerating(false);
      }
    }, 10000); // 10 second timeout
    
    ws.onopen = () => {
      console.log('[Global TTS] WebSocket connected');
      clearTimeout(connectionTimeout);
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
      setError('Connection failed - check your network');
      setIsGenerating(false);
    };
    
    ws.onclose = (event) => {
      console.log('[Global TTS] WebSocket disconnected. Code:', event.code, 'Reason:', event.reason);
      
      // Handle different close codes
      if (event.code === 1008 || event.code === 1011 || event.reason?.includes('not found') || event.reason?.includes('expired')) {
        setError('TTS session expired or not found');
        console.warn('[Global TTS] Session expired or not found');
      } else if (event.code === 1006) {
        // Abnormal closure - often network issues
        setError('Connection lost - check your network');
      } else if (event.code !== 1000) {
        // Normal closure is 1000, anything else is an error
        setError(`Connection closed (${event.code}) - please try again`);
      }
      
      setIsGenerating(false);
    };
  }, [actualApiUrl, handleWebSocketMessage, currentSceneId, isPlaying, isGenerating]);
  
  /**
   * Start manual TTS generation for a scene
   */
  const playScene = useCallback(async (sceneId: number) => {
    addDebugLog(`▶️ Starting TTS for scene ${sceneId}`);
    console.log('[Global TTS] Starting manual TTS for scene:', sceneId);
    
    try {
      // FIRST: Stop any existing playback/generation
      stop();
      
      // Wait a moment for cleanup
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // AUTO-UNLOCK: For manual play, automatically unlock AudioContext
      if (!audioContextManager.isAudioUnlocked()) {
        addDebugLog('🔓 Auto-unlocking AudioContext for manual play...');
        console.log('[Global TTS] Auto-unlocking AudioContext for manual play');
        const unlockSuccess = await audioContextManager.unlock();
        if (!unlockSuccess) {
          addDebugLog('❌ Failed to unlock AudioContext');
          setError('🔊 Failed to enable audio - please try again');
          setAudioPermissionBlocked(true);
          setIsGenerating(false);
          return;
        }
        addDebugLog('✅ AudioContext unlocked successfully');
        setAudioPermissionBlocked(false);
      }
      
      // Check if online
      if (!navigator.onLine) {
        addDebugLog('❌ No internet connection');
        setError('No internet connection - please check your network');
        setIsGenerating(false);
        return;
      }
      
      addDebugLog('✓ Making API call...');
      
      // Clear any previous errors
      setError(null);
      setIsGenerating(true);
      
      // Create TTS session (use WebSocket endpoint)
      const response = await fetch(`${actualApiUrl}/api/tts/generate-ws/${sceneId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
        }
      });
      
      addDebugLog(`Response: HTTP ${response.status}`);
      
      if (!response.ok) {
        // Better error parsing to show helpful messages
        let errorMessage = `HTTP ${response.status}`;
        try {
          const contentType = response.headers.get('content-type');
          if (contentType && contentType.includes('application/json')) {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorData.message || errorMessage;
            console.error('[Global TTS] Error response (JSON):', errorData);
          } else {
            const errorText = await response.text();
            errorMessage = errorText || errorMessage;
            console.error('[Global TTS] Error response (text):', errorText);
          }
        } catch (parseError) {
          console.error('[Global TTS] Failed to parse error response:', parseError);
        }
        
        // Add user-friendly context to common errors
        if (response.status === 403) {
          errorMessage = 'Access denied - please check your login';
        } else if (response.status === 404) {
          errorMessage = 'Scene not found - please refresh the page';
        } else if (response.status === 500) {
          errorMessage = `Server error: ${errorMessage}`;
        }
        
        console.error('[Global TTS] Final error message:', errorMessage);
        addDebugLog(`❌ Error: ${errorMessage}`);
        throw new Error(errorMessage);
      }
      
      const data = await response.json();
      addDebugLog(`✓ Session created, connecting...`);
      
      // Connect to the session (manual TTS)
      await connectToSession(data.session_id, sceneId);
    } catch (err) {
      console.error('[Global TTS] TTS failed:', err);
      
      setIsGenerating(false);
      const errorMessage = err instanceof Error ? err.message : 'Failed to start TTS';
      setError(errorMessage);
      addDebugLog(`❌ FAILED: ${errorMessage}`);
    }
  }, [actualApiUrl, connectToSession, addDebugLog]);
  
  /**
   * Stop playback
   */
  const stop = useCallback(() => {
    console.log('[Global TTS] Stopping playback');
    
    // Stop current audio source
    if (currentAudioSourceRef.current) {
      try {
        currentAudioSourceRef.current.stop();
      } catch (e) {
        // Already stopped, ignore
      }
      currentAudioSourceRef.current = null;
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
    setBrowserBlockedAutoplay(false);
    setAudioPermissionBlocked(false);
  }, []);
  
  /**
   * Pause playback
   * Note: AudioContext sources don't support pause/resume like Audio elements
   * We'll just stop for now
   */
  const pause = useCallback(() => {
    console.log('[Global TTS] Pause requested - stopping playback');
    stop();
  }, [stop]);
  
  /**
   * Resume playback
   * Note: AudioContext sources don't support pause/resume like Audio elements
   * User will need to restart playback
   */
  const resume = useCallback(() => {
    console.log('[Global TTS] Resume not supported with AudioContext - user must restart');
    // No-op for now
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
        browserBlockedAutoplay,
        audioPermissionBlocked,
        debugLogs,
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
