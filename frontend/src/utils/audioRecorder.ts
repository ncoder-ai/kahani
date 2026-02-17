/**
 * Audio Recorder Utility
 * 
 * Handles microphone access and audio recording for real-time STT.
 * Uses MediaRecorder API with WebM/Opus encoding for optimal performance.
 */

import { useState, useEffect } from 'react';

export interface AudioRecorderOptions {
  sampleRate?: number;
  channels?: number;
  chunkDuration?: number; // Duration of each chunk in milliseconds
  onDataAvailable?: (data: Blob) => void;
  onError?: (error: Error) => void;
  onStart?: () => void;
  onStop?: () => void;
}

export interface AudioRecorderState {
  isRecording: boolean;
  isSupported: boolean;
  error: string | null;
}

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private mediaStream: MediaStream | null = null;
  private options: AudioRecorderOptions;
  private state: AudioRecorderState = {
    isRecording: false,
    isSupported: false,
    error: null
  };

  constructor(options: AudioRecorderOptions = {}) {
    this.options = {
      sampleRate: 16000,
      channels: 1,
      chunkDuration: 100, // 100ms chunks for real-time processing
      ...options
    };
    
    this.checkSupport();
  }

  /**
   * Check if MediaRecorder is supported
   */
  private checkSupport(): void {
    // Check if we're in a browser environment (not SSR)
    if (typeof window === 'undefined' || typeof navigator === 'undefined') {
      this.state.isSupported = false;
      this.state.error = 'MediaRecorder API not available in server environment';
      return;
    }

    this.state.isSupported = !!(
      navigator.mediaDevices &&
      'getUserMedia' in navigator.mediaDevices &&
      window.MediaRecorder
    );
    
    if (!this.state.isSupported) {
      this.state.error = 'MediaRecorder API not supported in this browser';
    }
  }

  /**
   * Request microphone access and start recording
   */
  async startRecording(): Promise<void> {
    if (!this.state.isSupported) {
      throw new Error('MediaRecorder not supported');
    }

    if (this.state.isRecording) {
      console.warn('Already recording');
      return;
    }

    try {
      // Request microphone access
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: this.options.sampleRate,
          channelCount: this.options.channels,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // Use AudioContext to get raw PCM data instead of MediaRecorder
      // This avoids the need for WebM decoding on the backend
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: this.options.sampleRate
      });
      
      const source = audioContext.createMediaStreamSource(this.mediaStream);
      const processor = audioContext.createScriptProcessor(4096, this.options.channels, this.options.channels);
      
      processor.onaudioprocess = (e) => {
        if (!this.state.isRecording) return;
        
        // Get raw PCM data (Float32Array)
        const inputData = e.inputBuffer.getChannelData(0);
        
        // Convert Float32 (-1 to 1) to Int16 PCM (-32768 to 32767)
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        // Send as Blob for compatibility with existing code
        const blob = new Blob([pcm16.buffer], { type: 'audio/pcm' });
        if (this.options.onDataAvailable) {
          this.options.onDataAvailable(blob);
        }
      };
      
      source.connect(processor);
      processor.connect(audioContext.destination);
      
      // Store references for cleanup
      (this as any).audioContext = audioContext;
      (this as any).processor = processor;
      (this as any).source = source;
      
      // Create a dummy MediaRecorder for compatibility
      this.mediaRecorder = {
        start: () => {
          this.state.isRecording = true;
          this.state.error = null;
          this.options.onStart?.();
        },
        stop: () => {
          this.state.isRecording = false;
          processor.disconnect();
          source.disconnect();
          audioContext.close();
          this.options.onStop?.();
        },
        state: 'inactive',
        ondataavailable: null,
        onerror: null,
        onstart: null,
        onstop: null
      } as any;

      // Start recording (triggers the start callback)
      this.mediaRecorder!.start();
      
    } catch (error) {
      const err = error as Error;
      this.state.error = err.message;
      this.options.onError?.(err);
      throw err;
    }
  }

  /**
   * Stop recording
   */
  stopRecording(): void {
    if (this.mediaRecorder && this.state.isRecording) {
      this.mediaRecorder.stop();
    }
  }

  /**
   * Pause recording
   */
  pauseRecording(): void {
    if (this.mediaRecorder && this.state.isRecording) {
      this.mediaRecorder.pause();
    }
  }

  /**
   * Resume recording
   */
  resumeRecording(): void {
    if (this.mediaRecorder && this.state.isRecording) {
      this.mediaRecorder.resume();
    }
  }

  /**
   * Get the best supported MIME type for audio recording
   */
  private getSupportedMimeType(): string {
    const types = [
      'audio/webm;codecs=opus',  // Best for Chrome/Firefox
      'audio/webm',              // Fallback
      'audio/mp4',               // Safari fallback
      'audio/wav'                // Last resort
    ];

    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }

    console.warn('[AudioRecorder] No supported MIME type found, using default');
    return 'audio/webm';
  }

  /**
   * Clean up resources
   */
  cleanup(): void {
    if (this.mediaRecorder) {
      if (this.state.isRecording) {
        this.mediaRecorder.stop();
      }
      this.mediaRecorder = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    this.state.isRecording = false;
    this.state.error = null;
  }

  /**
   * Get current state
   */
  getState(): AudioRecorderState {
    return { ...this.state };
  }

  /**
   * Check if currently recording
   */
  isRecording(): boolean {
    return this.state.isRecording;
  }

  /**
   * Get error message if any
   */
  getError(): string | null {
    return this.state.error;
  }
}

/**
 * Hook for using AudioRecorder in React components
 */
export function useAudioRecorder(options: AudioRecorderOptions = {}) {
  const [recorder] = useState(() => new AudioRecorder(options));
  const [state, setState] = useState<AudioRecorderState>(recorder.getState());

  // Update state when recorder state changes
  useEffect(() => {
    const interval = setInterval(() => {
      setState(recorder.getState());
    }, 100);

    return () => clearInterval(interval);
  }, [recorder]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      recorder.cleanup();
    };
  }, [recorder]);

  return {
    recorder,
    state,
    startRecording: () => recorder.startRecording(),
    stopRecording: () => recorder.stopRecording(),
    pauseRecording: () => recorder.pauseRecording(),
    resumeRecording: () => recorder.resumeRecording(),
    cleanup: () => recorder.cleanup()
  };
}
