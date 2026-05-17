/**
 * useRealtimeSTT Hook
 *
 * Manages real-time Speech-to-Text. On iOS Capacitor the hook uses
 * Apple SFSpeechRecognizer via @capacitor-community/speech-recognition
 * — on-device, free, the same engine as the iOS keyboard dictation
 * button. Everywhere else (web, Android) it streams microphone audio
 * over WebSocket to the backend's WhisperLiveKit-backed STT service.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useAudioRecorder } from '../utils/audioRecorder';
import { useConfig } from '@/contexts/ConfigContext';
import { getAuthToken } from '@/utils/jwt';
import { isIOS, isNative } from '@/lib/capacitor';
import { SpeechRecognition } from '@capacitor-community/speech-recognition';
import type { PluginListenerHandle } from '@capacitor/core';

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

  // iOS Capacitor uses the on-device SpeechRecognition plugin instead
  // of streaming to the backend. Cached at first render — the runtime
  // platform doesn't change mid-session.
  const useNativeSTT = useRef(false);
  const sttListenerRef = useRef<PluginListenerHandle | null>(null);
  const latestPartialRef = useRef<string>('');
  useEffect(() => {
    useNativeSTT.current = isNative() && isIOS();
  }, []);

  // Update options ref when they change
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  /**
   * Fetch the user's STT settings (enabled flag + language). Falls back
   * to enabled:true and empty language on any error so the mic still
   * works when the settings endpoint is unreachable.
   */
  const fetchSTTSettings = useCallback(async (): Promise<{ enabled: boolean; language: string }> => {
    try {
      const token = getAuthToken();
      const { getApiBaseUrl } = await import('@/lib/apiUrl');
      const apiBaseUrl = await getApiBaseUrl();

      const response = await fetch(`${apiBaseUrl}/api/settings/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        const sttSettings = data.settings?.stt_settings;
        return {
          enabled: sttSettings?.enabled ?? true,
          language: sttSettings?.language || '',
        };
      }
      return { enabled: true, language: '' };
    } catch (error) {
      console.error('Error checking STT settings:', error);
      return { enabled: true, language: '' };
    }
  }, []);

  // Audio recorder (web / Android path only)
  const { startRecording, stopRecording, cleanup: cleanupRecorder } = useAudioRecorder({
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
  }, [config]);

  /**
   * Connect to STT WebSocket (web/Android path)
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

      // Build WS URL from apiBaseUrl — window.location is unreliable
      // under reverse proxies and on iOS Capacitor's capacitor:// scheme.
      const apiBaseUrl = await config.getApiBaseUrl();
      const sttPath = await config.getSTTWebSocketPath();
      const apiUrl = new URL(apiBaseUrl);
      const wsProto = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${apiUrl.host}${sttPath}/${sessionId}`;


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

      ws.onclose = () => {
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
  }, [createSession, config]);

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

  /**
   * iOS native STT path — uses SFSpeechRecognizer via
   * @capacitor-community/speech-recognition. Runs fully on-device, no
   * backend WS, same engine as the iOS keyboard dictation button.
   */
  const startNativeSTT = useCallback(async (language: string) => {
    const perms = await SpeechRecognition.checkPermissions();
    if (perms.speechRecognition !== 'granted') {
      const requested = await SpeechRecognition.requestPermissions();
      if (requested.speechRecognition !== 'granted') {
        throw new Error('Speech recognition permission denied');
      }
    }

    const avail = await SpeechRecognition.available();
    if (!avail.available) {
      throw new Error('Speech recognition is not available on this device');
    }

    latestPartialRef.current = '';
    fullTranscriptRef.current = '';

    // Subscribe BEFORE start so we never miss the first event.
    sttListenerRef.current = await SpeechRecognition.addListener(
      'partialResults',
      (data: { matches: string[] }) => {
        const text = data.matches?.[0] ?? '';
        if (!text) return;
        latestPartialRef.current = text;
        fullTranscriptRef.current = text;
        setState(prev => ({ ...prev, transcript: text, partialTranscript: text }));
        optionsRef.current.onTranscript?.(text, true);
        if (startTimeRef.current) {
          setState(prev => ({ ...prev, latency: Date.now() - startTimeRef.current! }));
        }
      }
    );

    // Start dictation. If the user picked a locale in Settings, pass it
    // through; otherwise omit `language` and let SFSpeechRecognizer use
    // the device locale (Hindi keyboard → Hindi STT, etc).
    // partialResults:true streams live word-by-word.
    const startOpts: Parameters<typeof SpeechRecognition.start>[0] = {
      partialResults: true,
      popup: false,
    };
    if (language) startOpts.language = language;
    await SpeechRecognition.start(startOpts);

    audioRecorderControllingState.current = true;
    setState(prev => ({ ...prev, isRecording: true, isConnected: true, error: null }));
    optionsRef.current.onStatusChange?.(true, false);
  }, []);

  const stopNativeSTT = useCallback(async () => {
    try { await SpeechRecognition.stop(); } catch { /* ignore */ }
    if (sttListenerRef.current) {
      try { await sttListenerRef.current.remove(); } catch { /* ignore */ }
      sttListenerRef.current = null;
    }
    audioRecorderControllingState.current = false;

    // Emit the last partial as the final transcript — SFSpeechRecognizer
    // doesn't separately signal a "final" event in this plugin, but the
    // latest partialResults at stop() is the finalized recognition.
    const finalText = latestPartialRef.current;
    if (finalText) {
      fullTranscriptRef.current = finalText;
      setState(prev => ({
        ...prev,
        transcript: finalText,
        partialTranscript: '',
        isRecording: false,
      }));
      optionsRef.current.onTranscript?.(finalText, false);
    } else {
      setState(prev => ({ ...prev, isRecording: false }));
    }
    optionsRef.current.onStatusChange?.(false, false);
  }, []);

  /**
   * Start recording and transcription
   */
  const startTranscription = useCallback(async () => {
    try {
      const settings = await fetchSTTSettings();
      if (!settings.enabled) {
        const errorMsg = 'STT is disabled in Settings. Please enable it to use voice input.';
        setState(prev => ({ ...prev, error: errorMsg }));
        optionsRef.current.onError?.(errorMsg);
        return;
      }

      startTimeRef.current = Date.now();

      if (useNativeSTT.current) {
        await startNativeSTT(settings.language);
        return;
      }

      if (!state.isConnected) {
        await connect();
      }
      await startRecording();
    } catch (error) {
      const err = error as Error;
      setState(prev => ({ ...prev, error: err.message }));
      optionsRef.current.onError?.(err.message);
    }
  }, [state.isConnected, connect, startRecording, startNativeSTT, fetchSTTSettings]);

  /**
   * Stop recording and transcription
   */
  const stopTranscription = useCallback(() => {
    audioRecorderControllingState.current = false;
    if (useNativeSTT.current) {
      void stopNativeSTT();
    } else {
      stopRecording();
    }
    startTimeRef.current = null;
  }, [stopRecording, stopNativeSTT]);

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
    latestPartialRef.current = '';
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
      // Best-effort native STT cleanup if unmounted mid-recognition.
      if (sttListenerRef.current) {
        sttListenerRef.current.remove().catch(() => {});
        sttListenerRef.current = null;
      }
      if (useNativeSTT.current) {
        SpeechRecognition.stop().catch(() => {});
      }
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
