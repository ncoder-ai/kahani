/**
 * useRealtimeSTT Hook
 * 
 * Manages real-time Speech-to-Text using WebSocket connection.
 * Handles audio recording, WebSocket communication, and transcription state.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { AudioRecorder, useAudioRecorder } from '../utils/audioRecorder';
import { useConfig } from '@/contexts/ConfigContext';
import { getAuthToken } from '@/utils/jwt';

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
  const config = useConfig(); // Use config from React context
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
  const isConnectingRef = useRef<boolean>(false);
  const fullTranscriptRef = useRef<string>(''); // Accumulate all partials here
  const optionsRef = useRef(options); // Keep stable reference to options
  const audioRecorderControllingState = useRef<boolean>(false); // Track when audio recorder controls isRecording
  
  // Update options ref when they change
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  /**
   * Check if STT is enabled for the current user
   */
  const checkSTTEnabled = useCallback(async (): Promise<boolean> => {
    try {
      // Get auth token from store
      const token = getAuthToken();
      
      // Get API base URL from config
      const { getApiBaseUrl } = await import('@/lib/apiUrl');
      const apiBaseUrl = await getApiBaseUrl();
      
      const response = await fetch(`${apiBaseUrl}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        const sttSettings = data.settings?.stt_settings;
        return sttSettings?.enabled ?? true; // Default to enabled if not set
      }
      return true; // Default to enabled if API fails
    } catch (error) {
      console.error('Error checking STT settings:', error);
      return true; // Default to enabled if check fails
    }
  }, []);

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
      optionsRef.current.onError?.(error.message);
    },
    onStart: () => {
      audioRecorderControllingState.current = true;
      setState(prev => ({ ...prev, isRecording: true, error: null }));
      optionsRef.current.onStatusChange?.(true, false);
    },
    onStop: () => {
      audioRecorderControllingState.current = false;
      setState(prev => ({ ...prev, isRecording: false }));
      optionsRef.current.onStatusChange?.(false, false);
    }
  });

  /**
   * Create STT session
   */
  const createSession = useCallback(async (): Promise<string> => {
    try {
      // Get auth token from store
      const token = getAuthToken();
      
      // Get API base URL and STT path from config context
      const apiBaseUrl = await config.getApiBaseUrl();
      const sttPath = await config.getSTTWebSocketPath();
      
      const response = await fetch(`${apiBaseUrl}${sttPath}/create-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
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
    // Prevent multiple simultaneous connections
    if (isConnectingRef.current) {
      return;
    }
    
    if (wsRef.current?.readyState === WebSocket.OPEN || 
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    isConnectingRef.current = true;
    try {
      // Create session
      const sessionId = await createSession();
      sessionIdRef.current = sessionId;

      // Get WebSocket URL (connect to backend)
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const hostname = window.location.hostname;
      const backendPort = await config.getBackendPort();
      const sttPath = await config.getSTTWebSocketPath();
      const wsUrl = `${protocol}//${hostname}:${backendPort}${sttPath}/${sessionId}`;


      // Create WebSocket connection
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        isConnectingRef.current = false;
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
        setState(prev => ({ ...prev, isConnected: false, isRecording: false, isTranscribing: false }));
        
        // Don't auto-reconnect - let user click mic button to reconnect
        isConnectingRef.current = false;
      };

      ws.onerror = (error) => {
        console.error('[STT] WebSocket error:', error);
        isConnectingRef.current = false;
        setState(prev => ({ ...prev, error: 'WebSocket connection error' }));
      };

    } catch (error) {
      const err = error as Error;
      console.error('[STT] Connection failed:', err);
      isConnectingRef.current = false;
      setState(prev => ({ ...prev, error: err.message, isConnected: false }));
    }
  }, [createSession]);

  /**
   * Handle WebSocket messages
   */
  const handleWebSocketMessage = useCallback((message: STTMessage) => {
    switch (message.type) {
      case 'partial':
        if (message.text) {
          // Backend sends the full accumulated sentence
          fullTranscriptRef.current = message.text;
          
          setState(prev => ({ 
            ...prev, 
            transcript: fullTranscriptRef.current,
            partialTranscript: message.text || ''
          }));
          optionsRef.current.onTranscript?.(fullTranscriptRef.current, true);
          
          // Calculate latency
          if (startTimeRef.current) {
            const latency = Date.now() - startTimeRef.current;
            setState(prev => ({ ...prev, latency }));
          }
        }
        break;

      case 'final':
        if (message.text) {
          // Final transcript replaces the current transcript
          fullTranscriptRef.current = message.text;
          
          setState(prev => ({
            ...prev,
            transcript: fullTranscriptRef.current,
            partialTranscript: ''
          }));
          optionsRef.current.onTranscript?.(fullTranscriptRef.current, false);
          
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
            // Only update isRecording if audio recorder is not controlling it
            isRecording: audioRecorderControllingState.current ? prev.isRecording : (message.recording ?? prev.isRecording),
            isTranscribing: message.transcribing ?? prev.isTranscribing
          }));
          optionsRef.current.onStatusChange?.(
            message.recording ?? false,
            message.transcribing ?? false
          );
        }
        break;

      case 'error':
        setState(prev => ({ ...prev, error: message.message || 'Unknown error' }));
        optionsRef.current.onError?.(message.message || 'Unknown error');
        break;

      case 'complete':
        break;
    }
  }, []); // No dependencies - use refs for everything

  // Removed scheduleReconnect - no auto-reconnect, user clicks mic to connect

  /**
   * Start recording and transcription
   */
  const startTranscription = useCallback(async () => {
    try {
      // Check if STT is enabled
      const isEnabled = await checkSTTEnabled();
      if (!isEnabled) {
        const errorMsg = 'STT is disabled in Settings. Please enable it to use voice input.';
        setState(prev => ({ ...prev, error: errorMsg }));
        optionsRef.current.onError?.(errorMsg);
        return;
      }

      if (!state.isConnected) {
        await connect();
      }

      startTimeRef.current = Date.now();
      await startRecording();
    } catch (error) {
      const err = error as Error;
      setState(prev => ({ ...prev, error: err.message }));
      optionsRef.current.onError?.(err.message);
    }
  }, [state.isConnected, connect, startRecording, checkSTTEnabled]);

  /**
   * Stop recording and transcription
   */
  const stopTranscription = useCallback(() => {
    audioRecorderControllingState.current = false;
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
    isConnectingRef.current = false;
    setState(prev => ({ ...prev, isConnected: false }));
  }, []);

  /**
   * Clear transcript
   */
  const clearTranscript = useCallback(() => {
    fullTranscriptRef.current = ''; // Also clear the accumulator
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only cleanup on unmount, not when functions change

  /**
   * No auto-connect - WebSocket connects only when user clicks microphone
   */

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
    isReady: !state.error // Ready to connect even if not currently connected
  };
}
