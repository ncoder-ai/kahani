import { useState, useEffect, useRef, useCallback } from 'react';
import api, { getApiBaseUrl } from '@/lib/api';
import { audioContextManager } from '@/utils/audioContextManager';

interface UseTTSWebSocketOptions {
  sceneId: number;
  onPlaybackStart?: () => void;
  onPlaybackEnd?: () => void;
  onError?: (error: string) => void;
  onProgress?: (progress: number) => void;
  pendingAutoPlay?: {session_id: string, scene_id: number} | null;
  onAutoPlayProcessed?: () => void;
}

interface TTSSessionResponse {
  session_id: string;
  scene_id: number;
  websocket_url: string;
  message: string;
}

interface WebSocketMessage {
  type: 'chunk_ready' | 'progress' | 'complete' | 'error';
  chunk_number?: number;
  total_chunks?: number;
  audio_base64?: string;
  text_preview?: string;
  size_bytes?: number;
  duration?: number;
  chunks_ready?: number;
  progress_percent?: number;
  message?: string;
}

/**
 * WebSocket-based TTS Hook
 * 
 * Uses Web Audio API (AudioContext) for reliable iOS playback.
 * Eliminates polling by using WebSocket for real-time audio chunk delivery.
 * 
 * Benefits:
 * - Reliable iOS audio playback via AudioContext
 * - Gapless chunk playback with precise scheduling
 * - 5-10× faster to first audio
 * - Real-time progress updates
 * 
 * Usage:
 * ```tsx
 * const { generate, isGenerating, isPlaying, progress, stop } = useTTSWebSocket({
 *   sceneId: 123,
 *   onPlaybackStart: () => console.log('Started'),
 *   onPlaybackEnd: () => console.log('Ended'),
 *   onError: (err) => console.error(err)
 * });
 * 
 * <button onClick={generate}>Generate & Play</button>
 * ```
 */
export const useTTSWebSocket = ({
  sceneId,
  onPlaybackStart,
  onPlaybackEnd,
  onError,
  onProgress,
  pendingAutoPlay,
  onAutoPlayProcessed
}: UseTTSWebSocketOptions) => {
  // State
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);
  const [chunksReceived, setChunksReceived] = useState(0);
  const [error, setError] = useState<string | null>(null);
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const isPlayingRef = useRef(false);
  const connectedSessionRef = useRef<string | null>(null);
  const hasStartedPlayback = useRef(false);
  const generationCompleteRef = useRef(false);
  
  /**
   * Handle playback end - called when all queued audio finishes
   */
  const handlePlaybackEnd = useCallback(() => {
    console.log('[TTS WS] Playback ended');
    setIsPlaying(false);
    isPlayingRef.current = false;
    onPlaybackEnd?.();
  }, [onPlaybackEnd]);
  
  /**
   * Queue an audio chunk for playback using AudioContext
   */
  const queueAudioChunk = useCallback(async (audioBase64: string, chunkNumber: number) => {
    try {
      // Convert base64 to ArrayBuffer
      const arrayBuffer = audioContextManager.base64ToArrayBuffer(audioBase64);
      
      // Queue for gapless playback
      const result = await audioContextManager.queueBuffer(arrayBuffer);
      console.log(`[TTS WS] Queued chunk ${chunkNumber}, duration: ${result.duration.toFixed(2)}s`);
      
      // Start playback tracking if this is the first chunk
      if (!isPlayingRef.current) {
        setIsPlaying(true);
        isPlayingRef.current = true;
        hasStartedPlayback.current = true;
        onPlaybackStart?.();
        
        // Set up callback for when all audio finishes
        audioContextManager.setOnPlaybackEnd(() => {
          // Only trigger end if generation is complete
          if (generationCompleteRef.current) {
            handlePlaybackEnd();
          }
        });
      }
      
    } catch (err) {
      console.error('[TTS WS] Failed to queue audio chunk:', err);
      const errorMsg = err instanceof Error ? err.message : 'Failed to play audio chunk';
      
      // Check if this is an AudioContext permission issue
      if (errorMsg.includes('user gesture') || errorMsg.includes('not ready')) {
        setError('Audio not enabled. Please tap the audio button to enable TTS.');
      } else {
        setError(errorMsg);
      }
      onError?.(errorMsg);
    }
  }, [onPlaybackStart, onError, handlePlaybackEnd]);
  
  /**
   * Handle incoming WebSocket messages
   */
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      console.log('[TTS WS] Received:', message.type);
      
      switch (message.type) {
        case 'chunk_ready':
          if (message.audio_base64 && message.chunk_number) {
            // Queue for playback via AudioContext
            queueAudioChunk(message.audio_base64, message.chunk_number);
            
            // Update state
            setChunksReceived(prev => prev + 1);
            if (message.total_chunks) {
              setTotalChunks(message.total_chunks);
            }
          }
          break;
        
        case 'progress':
          if (message.progress_percent !== undefined) {
            setProgress(message.progress_percent);
            onProgress?.(message.progress_percent);
          }
          break;
        
        case 'complete':
          console.log('[TTS WS] Generation complete');
          setIsGenerating(false);
          setProgress(100);
          generationCompleteRef.current = true;
          
          // If no chunks were received or playback already ended, trigger end now
          if (!hasStartedPlayback.current) {
            handlePlaybackEnd();
          }
          // Otherwise, playback will end naturally via AudioContext callback
          break;
        
        case 'error':
          const errorMsg = message.message || 'TTS generation failed';
          console.error('[TTS WS] Error:', errorMsg);
          
          // Check if this is a chunk-specific error or a fatal error
          const isChunkError = errorMsg.toLowerCase().includes('chunk');
          
          if (isChunkError) {
            // For chunk errors, log but don't stop - continue with other chunks
            console.warn('[TTS WS] Chunk error (continuing):', errorMsg);
            // Only set error state if we haven't received any successful chunks
            if (!hasStartedPlayback.current) {
              setError(errorMsg);
              onError?.(errorMsg);
            }
          } else {
            // For fatal errors, stop everything
            setError(errorMsg);
            setIsGenerating(false);
            setIsPlaying(false);
            isPlayingRef.current = false;
            onError?.(errorMsg);
          }
          break;
      }
    } catch (e) {
      console.error('[TTS WS] Failed to parse message:', e);
    }
  }, [queueAudioChunk, onProgress, onError, handlePlaybackEnd]);
  
  /**
   * Generate and play audio using WebSocket
   */
  const generate = useCallback(async () => {
    console.log('[TTS WS] Starting generation for scene:', sceneId);
    
    try {
      // IMPORTANT: Stop everything first (closes WebSocket, stops audio, resets state)
      stop(); // This already calls stopAll() and resetQueue()
      
      setIsGenerating(true);
      setError(null);
      setProgress(0);
      setChunksReceived(0);
      setTotalChunks(0);
      hasStartedPlayback.current = false;
      generationCompleteRef.current = false;
      
      // Unlock AudioContext during this user gesture
      // This is critical for iOS - the context must be created/resumed during a tap
      const isUnlocked = await audioContextManager.unlock();
      if (!isUnlocked) {
        console.error('[TTS WS] Failed to unlock AudioContext');
        setError('Failed to enable audio. Please try again.');
        setIsGenerating(false);
        onError?.('Failed to enable audio');
        return;
      }
      console.log('[TTS WS] AudioContext unlocked successfully');
      
      // Reset the queue for fresh playback
      audioContextManager.resetQueue();
      
      // Create TTS session
      const data = await api.post<TTSSessionResponse>(
        `/api/tts/generate-ws/${sceneId}`
      );
      console.log('[TTS WS] Session created:', data.session_id);
      
      // Connect to WebSocket
      const apiUrl = await getApiBaseUrl();
      const apiHost = apiUrl.replace(/^https?:\/\//, '');
      const wsProtocol = apiUrl.startsWith('https') ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${apiHost}${data.websocket_url}`;
      console.log('[TTS WS] Connecting to:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('[TTS WS] Connected');
      };
      
      ws.onmessage = handleWebSocketMessage;
      
      ws.onerror = (error) => {
        console.error('[TTS WS] WebSocket error:', error);
        const errorMsg = 'WebSocket connection failed';
        setError(errorMsg);
        setIsGenerating(false);
        onError?.(errorMsg);
      };
      
      ws.onclose = () => {
        console.log('[TTS WS] Disconnected');
        wsRef.current = null;
      };
      
    } catch (err: any) {
      console.error('[TTS WS] Generation failed:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to generate audio';
      setError(errorMsg);
      setIsGenerating(false);
      onError?.(errorMsg);
    }
  }, [sceneId, handleWebSocketMessage, onError]);
  
  /**
   * Stop playback and generation
   */
  const stop = useCallback(() => {
    console.log('[TTS WS] Stopping');
    
    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    // Stop all AudioContext playback
    audioContextManager.stopAll();
    audioContextManager.setOnPlaybackEnd(null);
    
    // Reset state
    setIsGenerating(false);
    setIsPlaying(false);
    setProgress(0);
    isPlayingRef.current = false;
    hasStartedPlayback.current = false;
    generationCompleteRef.current = false;
  }, []);
  
  /**
   * Connect to existing TTS session (for auto-play)
   */
  const connectToSession = useCallback(async (session_id: string) => {
    // Prevent double connection
    if (wsRef.current) {
      console.log('[TTS WS] Already connected, skipping');
      return;
    }
    
    if (isGenerating) {
      console.log('[TTS WS] Already generating, skipping');
      return;
    }
    
    console.log('[TTS WS] Connecting to existing session:', session_id);
    
    try {
      setIsGenerating(true);
      setError(null);
      setProgress(0);
      setChunksReceived(0);
      setTotalChunks(0);
      hasStartedPlayback.current = false;
      generationCompleteRef.current = false;
      
      // Stop any current playback
      audioContextManager.stopAll();
      
      // Ensure AudioContext is unlocked
      const isReady = await audioContextManager.ensureReady();
      if (!isReady) {
        console.warn('[TTS WS] AudioContext not ready for auto-play');
      }
      
      // Reset the queue
      audioContextManager.resetQueue();
      
      // Connect to WebSocket with existing session
      const apiUrl = await getApiBaseUrl();
      const apiHost = apiUrl.replace(/^https?:\/\//, '');
      const wsProtocol = apiUrl.startsWith('https') ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${apiHost}/ws/tts/${session_id}`;
      console.log('[TTS WS] Auto-play connecting to:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('[TTS WS] Auto-play connected');
      };
      
      ws.onmessage = handleWebSocketMessage;
      
      ws.onerror = (error) => {
        console.error('[TTS WS] Auto-play error:', error);
        const errorMsg = 'Auto-play connection failed';
        setError(errorMsg);
        setIsGenerating(false);
        onError?.(errorMsg);
      };
      
      ws.onclose = () => {
        console.log('[TTS WS] Auto-play disconnected');
        wsRef.current = null;
      };
      
    } catch (err: any) {
      console.error('[TTS WS] Auto-play failed:', err);
      const errorMsg = err.message || 'Failed to start auto-play';
      setError(errorMsg);
      setIsGenerating(false);
      onError?.(errorMsg);
    }
  }, [handleWebSocketMessage, onError, isGenerating]);
  
  /**
   * Check for pending auto-play on mount and when pendingAutoPlay changes
   */
  useEffect(() => {
    // Check if there's a pending auto-play for this scene
    // AND make sure we haven't already connected to this session
    if (pendingAutoPlay && 
        pendingAutoPlay.scene_id === sceneId && 
        connectedSessionRef.current !== pendingAutoPlay.session_id &&
        !isGenerating && 
        !wsRef.current) {
      connectedSessionRef.current = pendingAutoPlay.session_id;
      connectToSession(pendingAutoPlay.session_id);
      onAutoPlayProcessed?.();
    }
  }, [sceneId, pendingAutoPlay, connectToSession, onAutoPlayProcessed, isGenerating]);
  
  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);
  
  return {
    generate,
    stop,
    isGenerating,
    isPlaying,
    progress,
    chunksReceived,
    totalChunks,
    error
  };
};
