'use client';

import React, { createContext, useContext, useRef, useState, useCallback, useEffect, useMemo } from 'react';
import { audioContextManager } from '@/utils/audioContextManager';
import { getApiBaseUrl } from '@/lib/api';

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
    // Use the same logic as getApiBaseUrl for consistency
    if (typeof window !== 'undefined') {
      const hostname = window.location.hostname;
      const protocol = window.location.protocol;
      const port = window.location.port;
      
      // Check if we're using a reverse proxy (no port in URL or standard ports)
      const isReverseProxy = !port || port === '80' || port === '443';
      
      if (isReverseProxy) {
        // For reverse proxy: use same domain without port
        return `${protocol}//${hostname}`;
      }
      
      // For direct access: get backend port from config
      // Note: This requires config to be loaded first
      // In practice, apiBaseUrl should already have the correct port from config
      if (apiBaseUrl && apiBaseUrl.trim() !== '') {
        return apiBaseUrl;
      }
      // Fallback to default backend port if config not loaded yet
      console.warn('[Global TTS] Config not loaded, using fallback port 9876');
      return `${protocol}//${hostname}:9876`;
    }
    
    // Server-side fallback
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
  const playNextChunk = useCallback(async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }
    
    const chunk = audioQueueRef.current.shift()!;
    
    const context = audioContextManager.getContext();
    
    if (!context) {
      console.error('[Global TTS] AudioContext not available');
      setError('🔊 Audio system not available');
      setAudioPermissionBlocked(true);
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }
    
    // CRITICAL: Check AudioContext state dynamically and try to resume if suspended
    // This is especially important on iOS where context can be suspended at any time
    const currentState = context.state;
    if (currentState === 'suspended') {
      console.warn('[Global TTS] AudioContext suspended, attempting resume...');
      addDebugLog('⚠️ AudioContext suspended, resuming...');
      
      try {
        await context.resume();
        
        if (context.state !== 'running') {
          throw new Error(`Failed to resume AudioContext, state: ${context.state}`);
        }
        
        addDebugLog('✅ AudioContext resumed');
      } catch (err) {
        console.error('[Global TTS] ❌ Cannot resume AudioContext:', err);
        addDebugLog(`❌ Resume failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
        setError('🔊 Audio locked - please tap "Enable TTS" button in top banner');
        setAudioPermissionBlocked(true);
        setBrowserBlockedAutoplay(true);
        isPlayingRef.current = false;
        setIsPlaying(false);
        // Put chunk back in queue so it can be retried later
        audioQueueRef.current.unshift(chunk);
        return;
      }
    }
    
    // Double-check state is running before proceeding
    if (context.state !== 'running') {
      console.error('[Global TTS] AudioContext not running, state:', context.state);
      addDebugLog(`❌ AudioContext state: ${context.state}`);
      setError('🔊 Audio not ready - please tap "Enable TTS" button');
      setAudioPermissionBlocked(true);
      isPlayingRef.current = false;
      setIsPlaying(false);
      audioQueueRef.current.unshift(chunk);
      return;
    }
    
    // Decode audio from blob and play through AudioContext
    chunk.audio_blob.arrayBuffer()
      .then(arrayBuffer => {
        return context.decodeAudioData(arrayBuffer);
      })
      .then(audioBuffer => {
        addDebugLog(`✅ Chunk ${chunk.chunk_number} decoded (${audioBuffer.duration.toFixed(2)}s)`);
        
        // Verify context is still running before creating nodes
        if (context.state !== 'running') {
          throw new Error(`AudioContext suspended during decode, state: ${context.state}`);
        }
        
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
          addDebugLog(`✓ Chunk ${chunk.chunk_number} playback completed`);
          URL.revokeObjectURL(chunk.audio_url);
          currentAudioSourceRef.current = null;
          playNextChunk(); // Play next chunk
        };
        
        
        // Start playback
        try {
          source.start(0);
          addDebugLog(`▶️ Playing chunk ${chunk.chunk_number}`);
          setIsPlaying(true);
          isPlayingRef.current = true;
          setBrowserBlockedAutoplay(false);
          setAudioPermissionBlocked(false);
        } catch (err) {
          console.error('[Global TTS] Failed to start playback:', err);
          addDebugLog(`❌ Failed to start: ${err instanceof Error ? err.message : 'Unknown error'}`);
          throw err;
        }
      })
      .catch(err => {
        console.error('[Global TTS] Failed to play chunk:', err);
        addDebugLog(`❌ Playback failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
        setError(`Playback failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
        isPlayingRef.current = false;
        setIsPlaying(false);
        URL.revokeObjectURL(chunk.audio_url);
      });
  }, [addDebugLog]);
  
  /**
   * Handle WebSocket messages
   */
  const handleWebSocketMessage = useCallback((message: TTSMessage) => {
    
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
        setIsGenerating(false);
        break;
        
      case 'error':
        console.error('[Global TTS] WebSocket error:', message.message);
        // Provide more helpful error messages
        let errorMsg = message.message || 'Unknown error';
        if (errorMsg.includes('Failed to generate chunk')) {
          errorMsg = 'TTS generation failed - please check your TTS provider settings in Settings > Voice Settings';
        } else if (errorMsg.includes('timeout') || errorMsg.includes('Timeout')) {
          errorMsg = 'TTS generation timed out - please try again or check your TTS provider connection';
        } else if (errorMsg.includes('API key') || errorMsg.includes('authentication')) {
          errorMsg = 'TTS authentication failed - please check your TTS provider API key in Settings > Voice Settings';
        }
        setError(errorMsg);
        setIsGenerating(false);
        break;
    }
  }, [base64ToBlob, playNextChunk]);
  
  /**
   * Connect to existing TTS session (for auto-play or manual)
   */
  const connectToSession = useCallback(async (sessionId: string, sceneId: number) => {
    
    // If already connected to this session, don't reconnect
    if (currentSessionIdRef.current === sessionId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return;
    }
    
    // If already playing or generating this scene, don't reconnect
    if (currentSceneId === sceneId && (isPlaying || isGenerating)) {
      return;
    }
    
    // Close existing connection if connecting to different session
    if (wsRef.current && currentSessionIdRef.current !== sessionId) {
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
      }
    } catch (err) {
      console.warn('[Global TTS] Autoplay permission may be blocked:', err);
      // Continue anyway - user might have already granted permission
    }
    
    // Get API URL with proper port (like settings modal does)
    let apiUrl: string;
    try {
      apiUrl = await getApiBaseUrl();
    } catch (error) {
      const errorMsg = 'Failed to get API URL for WebSocket connection';
      console.error('[Global TTS]', errorMsg, error);
      setError(errorMsg);
      setIsGenerating(false);
      return;
    }
    
    // Connect WebSocket
    const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = apiUrl.replace(/^https?:\/\//, '');
    
    // Validate hostname before creating WebSocket URL
    if (!wsHost || wsHost.trim() === '') {
      const errorMsg = 'Invalid API hostname - cannot create WebSocket connection';
      console.error('[Global TTS]', errorMsg);
      console.error('[Global TTS] apiUrl:', apiUrl);
      setError(errorMsg);
      setIsGenerating(false);
      return;
    }
    
    if (!sessionId || sessionId.trim() === '') {
      const errorMsg = 'Invalid session ID - cannot create WebSocket connection';
      console.error('[Global TTS]', errorMsg);
      setError(errorMsg);
      setIsGenerating(false);
      return;
    }
    
    const wsUrl = `${wsProtocol}://${wsHost}/ws/tts/${sessionId}`;
    
    // Validate WebSocket URL before connecting
    if (!wsUrl || (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://'))) {
      const errorMsg = `Invalid WebSocket URL: ${wsUrl}`;
      console.error('[Global TTS]', errorMsg);
      setError(errorMsg);
      setIsGenerating(false);
      return;
    }
    
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to create WebSocket';
      console.error('[Global TTS] WebSocket creation failed:', errorMsg, err);
      setError(`WebSocket creation failed: ${errorMsg}`);
      setIsGenerating(false);
      return;
    }
    
    // Set a timeout for WebSocket connection
    const connectionTimeout = setTimeout(() => {
      if (ws.readyState === WebSocket.CONNECTING) {
        console.error('[Global TTS] WebSocket connection timeout after 10 seconds');
        ws.close();
        setError('Connection timeout - please check your network and try again');
        setIsGenerating(false);
      }
    }, 10000); // 10 second timeout
    
    ws.onopen = () => {
      clearTimeout(connectionTimeout);
    };
    
    ws.onmessage = (event) => {
      try {
        const message: TTSMessage = JSON.parse(event.data);
        handleWebSocketMessage(message);
      } catch (err) {
        console.error('[Global TTS] Failed to parse message:', err);
        console.error('[Global TTS] Raw message data:', event.data);
      }
    };
    
    ws.onerror = (error) => {
      // WebSocket error event doesn't provide detailed error info
      // Log connection state and URL for debugging
      console.error('[Global TTS] WebSocket error occurred');
      console.error('[Global TTS] WebSocket state:', ws.readyState);
      console.error('[Global TTS] WebSocket URL:', wsUrl);
      console.error('[Global TTS] Error event:', error);
      
      // Provide more specific error message based on connection state
      let errorMessage = 'Connection failed - check your network';
      if (ws.readyState === WebSocket.CLOSED) {
        errorMessage = 'Connection closed unexpectedly - please try again';
      } else if (ws.readyState === WebSocket.CONNECTING) {
        errorMessage = 'Connection failed - check your network or backend server';
      }
      
      setError(errorMessage);
      setIsGenerating(false);
      clearTimeout(connectionTimeout);
    };
    
    ws.onclose = (event) => {
      
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
  }, [handleWebSocketMessage, currentSceneId, isPlaying, isGenerating]);
  
  /**
   * Start manual TTS generation for a scene
   */
  const playScene = useCallback(async (sceneId: number) => {
    addDebugLog(`▶️ Starting TTS for scene ${sceneId}`);
    
    // Get API URL with proper port (like settings modal does)
    let apiUrl: string;
    try {
      apiUrl = await getApiBaseUrl();
    } catch (error) {
      const errorMsg = 'TTS service initializing - please wait a moment and try again';
      console.warn('[Global TTS] Failed to get API URL:', error);
      addDebugLog(`❌ ${errorMsg}`);
      setError(errorMsg);
      setIsGenerating(false);
      return;
    }
    
    // Construct full URL and check auth token (declare before try for error logging)
    const fullUrl = `${apiUrl}/api/tts/generate-ws/${sceneId}`;
    const authToken = localStorage.getItem('auth_token');
    
    try {
      // FIRST: Stop any existing playback/generation
      stop();
      
      // Wait a moment for cleanup
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // AUTO-UNLOCK: For manual play, automatically unlock AudioContext
      if (!audioContextManager.isAudioUnlocked()) {
        addDebugLog('🔓 Auto-unlocking AudioContext for manual play...');
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
      
      // Comprehensive logging for debugging
      console.log('[Global TTS] ===== TTS Request Details =====');
      console.log('[Global TTS] Full URL:', fullUrl);
      console.log('[Global TTS] apiUrl (from getApiBaseUrl):', apiUrl);
      console.log('[Global TTS] sceneId:', sceneId);
      console.log('[Global TTS] Auth token exists:', !!authToken);
      console.log('[Global TTS] Auth token length:', authToken ? authToken.length : 0);
      console.log('[Global TTS] URL is absolute:', fullUrl.startsWith('http://') || fullUrl.startsWith('https://'));
      addDebugLog(`📡 Calling: ${fullUrl}`);
      
      // Create TTS session (use WebSocket endpoint)
      const response = await fetch(fullUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
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
      // Comprehensive error logging for debugging
      console.error('[Global TTS] ===== TTS Error Details =====');
      console.error('[Global TTS] Error object:', err);
      console.error('[Global TTS] Error type:', err instanceof Error ? err.constructor.name : typeof err);
      console.error('[Global TTS] Error message:', err instanceof Error ? err.message : String(err));
      console.error('[Global TTS] Error name:', err instanceof Error ? err.name : 'Unknown');
      if (err instanceof Error && err.stack) {
        console.error('[Global TTS] Error stack:', err.stack);
      }
      console.error('[Global TTS] Full URL that failed:', fullUrl);
      console.error('[Global TTS] apiUrl (from getApiBaseUrl):', apiUrl);
      console.error('[Global TTS] sceneId:', sceneId);
      console.error('[Global TTS] Has auth token:', !!authToken);
      console.error('[Global TTS] ===============================');
      
      setIsGenerating(false);
      let errorMessage = 'Failed to start TTS';
      
      if (err instanceof TypeError) {
        // Network errors (Load failed, Failed to fetch, etc.)
        if (err.message.includes('Load failed') || err.message.includes('Failed to fetch')) {
          errorMessage = 'Network error - unable to connect to TTS service. Please check your connection.';
        } else {
          errorMessage = `Network error: ${err.message}`;
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
      addDebugLog(`❌ FAILED: ${errorMessage}`);
    }
  }, [connectToSession, addDebugLog]);
  
  /**
   * Stop playback
   */
  const stop = useCallback(() => {
    
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
    stop();
  }, [stop]);
  
  /**
   * Resume playback
   * Note: AudioContext sources don't support pause/resume like Audio elements
   * User will need to restart playback
   */
  const resume = useCallback(() => {
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
