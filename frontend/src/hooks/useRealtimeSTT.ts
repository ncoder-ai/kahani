/**
 * useRealtimeSTT Hook
 * 
 * Manages real-time Speech-to-Text using WebSocket connection.
 * Handles audio recording, WebSocket communication, and transcription state.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { AudioRecorder, useAudioRecorder } from '../utils/audioRecorder';

export interface STTMessage {
  type: 'partial' | 'final' | 'status' | 'error' | 'complete';
  text?: string;
  confidence?: number;
  recording?: boolean;
  transcribing?: boolean;
  message?: string;
  timestamp?: number;
}

export interface STTState {
  isConnected: boolean;
  isRecording: boolean;
  isTranscribing: boolean;
  transcript: string;
  partialTranscript: string;
  error: string | null;
  latency: number | null; // Last measured latency in ms
}

export interface UseRealtimeSTTOptions {
  onTranscript?: (text: string, isPartial: boolean) => void;
  onError?: (error: string) => void;
  onStatusChange?: (recording: boolean, transcribing: boolean) => void;
  autoConnect?: boolean;
}

export function useRealtimeSTT(options: UseRealtimeSTTOptions = {}) {
  const [state, setState] = useState<STTState>({
    isConnected: false,
    isRecording: false,
    isTranscribing: false,
    transcript: '',
    partialTranscript: '',
    error: null,
    latency: null
  });

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Audio recorder
  const { recorder, startRecording, stopRecording, cleanup: cleanupRecorder } = useAudioRecorder({
    chunkDuration: 100, // 100ms chunks for real-time processing
    onDataAvailable: (data: Blob) => {
      // Send audio data to WebSocket
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(data);
      }
    },
    onError: (error: Error) => {
      setState(prev => ({ ...prev, error: error.message }));
      options.onError?.(error.message);
    },
    onStart: () => {
      setState(prev => ({ ...prev, isRecording: true, error: null }));
      options.onStatusChange?.(true, false);
    },
    onStop: () => {
      setState(prev => ({ ...prev, isRecording: false }));
      options.onStatusChange?.(false, false);
    }
  });

  /**
   * Create STT session
   */
  const createSession = useCallback(async (): Promise<string> => {
    try {
      const response = await fetch('/ws/stt/create-session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.statusText}`);
      }

      const data = await response.json();
      return data.session_id;
    } catch (error) {
      const err = error as Error;
      setState(prev => ({ ...prev, error: err.message }));
      throw err;
    }
  }, []);

  /**
   * Connect to STT WebSocket
   */
  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[STT] Already connected');
      return;
    }

    console.log('[STT] Starting connection process...');
    try {
      // Create session
      console.log('[STT] Creating session...');
      const sessionId = await createSession();
      console.log('[STT] Session created:', sessionId);
      sessionIdRef.current = sessionId;

      // Get WebSocket URL
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/stt/${sessionId}`;

      console.log('[STT] Connecting to WebSocket:', wsUrl);

      // Create WebSocket connection
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[STT] WebSocket connected');
        setState(prev => ({ ...prev, isConnected: true, error: null }));
      };

      ws.onmessage = (event) => {
        try {
          const message: STTMessage = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (error) {
          console.error('[STT] Error parsing WebSocket message:', error);
        }
      };

      ws.onclose = (event) => {
        console.log('[STT] WebSocket closed:', event.code, event.reason);
        setState(prev => ({ ...prev, isConnected: false }));
        
        // Auto-reconnect if not intentionally closed
        if (event.code !== 1000) {
          scheduleReconnect();
        }
      };

      ws.onerror = (error) => {
        console.error('[STT] WebSocket error:', error);
        setState(prev => ({ ...prev, error: 'WebSocket connection error' }));
      };

    } catch (error) {
      const err = error as Error;
      console.error('[STT] Connection failed:', err);
      setState(prev => ({ ...prev, error: err.message }));
    }
  }, [createSession]);

  /**
   * Handle WebSocket messages
   */
  const handleWebSocketMessage = useCallback((message: STTMessage) => {
    switch (message.type) {
      case 'partial':
        if (message.text) {
          setState(prev => ({ ...prev, partialTranscript: message.text }));
          options.onTranscript?.(message.text, true);
        }
        break;

      case 'final':
        if (message.text) {
          setState(prev => ({
            ...prev,
            transcript: prev.transcript + ' ' + message.text,
            partialTranscript: ''
          }));
          options.onTranscript?.(message.text, false);
          
          // Calculate latency
          if (startTimeRef.current) {
            const latency = Date.now() - startTimeRef.current;
            setState(prev => ({ ...prev, latency }));
          }
        }
        break;

      case 'status':
        if (message.recording !== undefined || message.transcribing !== undefined) {
          setState(prev => ({
            ...prev,
            isRecording: message.recording ?? prev.isRecording,
            isTranscribing: message.transcribing ?? prev.isTranscribing
          }));
          options.onStatusChange?.(
            message.recording ?? false,
            message.transcribing ?? false
          );
        }
        break;

      case 'error':
        setState(prev => ({ ...prev, error: message.message || 'Unknown error' }));
        options.onError?.(message.message || 'Unknown error');
        break;

      case 'complete':
        console.log('[STT] Transcription complete');
        break;
    }
  }, [options]);

  /**
   * Schedule reconnection
   */
  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    reconnectTimeoutRef.current = setTimeout(() => {
      console.log('[STT] Attempting to reconnect...');
      connect();
    }, 3000);
  }, [connect]);

  /**
   * Start recording and transcription
   */
  const startTranscription = useCallback(async () => {
    try {
      if (!state.isConnected) {
        await connect();
      }

      startTimeRef.current = Date.now();
      await startRecording();
    } catch (error) {
      const err = error as Error;
      setState(prev => ({ ...prev, error: err.message }));
      options.onError?.(err.message);
    }
  }, [state.isConnected, connect, startRecording, options]);

  /**
   * Stop recording and transcription
   */
  const stopTranscription = useCallback(() => {
    stopRecording();
    startTimeRef.current = null;
  }, [stopRecording]);

  /**
   * Disconnect WebSocket
   */
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected');
      wsRef.current = null;
    }

    sessionIdRef.current = null;
    setState(prev => ({ ...prev, isConnected: false }));
  }, []);

  /**
   * Clear transcript
   */
  const clearTranscript = useCallback(() => {
    setState(prev => ({
      ...prev,
      transcript: '',
      partialTranscript: '',
      error: null,
      latency: null
    }));
  }, []);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      disconnect();
      cleanupRecorder();
    };
  }, [disconnect, cleanupRecorder]);

  /**
   * Auto-connect if enabled
   */
  useEffect(() => {
    if (options.autoConnect) {
      connect();
    }
  }, [options.autoConnect, connect]);

  /**
   * Auto-connect on mount for testing
   */
  useEffect(() => {
    // Auto-connect for testing purposes
    connect();
  }, [connect]);

  return {
    // State
    ...state,
    
    // Actions
    connect,
    disconnect,
    startTranscription,
    stopTranscription,
    clearTranscript,
    
    // Utils
    isReady: state.isConnected && !state.error
  };
}
