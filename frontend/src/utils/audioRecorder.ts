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
    this.state.isSupported = !!(
      navigator.mediaDevices &&
      navigator.mediaDevices.getUserMedia &&
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

      // Create MediaRecorder with WebM/Opus for best compression and quality
      const mimeType = this.getSupportedMimeType();
      this.mediaRecorder = new MediaRecorder(this.mediaStream, {
        mimeType,
        audioBitsPerSecond: 128000 // 128kbps for good quality/size balance
      });

      // Set up event handlers
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && this.options.onDataAvailable) {
          this.options.onDataAvailable(event.data);
        }
      };

      this.mediaRecorder.onerror = (event) => {
        const error = new Error(`MediaRecorder error: ${event}`);
        this.state.error = error.message;
        this.options.onError?.(error);
      };

      this.mediaRecorder.onstart = () => {
        this.state.isRecording = true;
        this.state.error = null;
        this.options.onStart?.();
        console.log('[AudioRecorder] Recording started');
      };

      this.mediaRecorder.onstop = () => {
        this.state.isRecording = false;
        this.options.onStop?.();
        console.log('[AudioRecorder] Recording stopped');
      };

      // Start recording with time slices for real-time processing
      this.mediaRecorder.start(this.options.chunkDuration);
      
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
        console.log(`[AudioRecorder] Using MIME type: ${type}`);
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
