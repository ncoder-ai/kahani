'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useRealtimeSTT } from '../hooks/useRealtimeSTT';
import { Mic, MicOff, Loader2 } from 'lucide-react';

export interface MicrophoneButtonProps {
  onTranscriptComplete: (text: string) => void;
  disabled?: boolean;
  className?: string;
  position?: 'inline' | 'absolute';
  showPreview?: boolean;
  placeholder?: string;
}

export default function MicrophoneButton({
  onTranscriptComplete,
  disabled = false,
  className = '',
  position = 'inline',
  showPreview = true,
  placeholder = 'Click to start recording...'
}: MicrophoneButtonProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [previewText, setPreviewText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSTTEnabled, setIsSTTEnabled] = useState(true);
  
  const {
    isConnected,
    isTranscribing,
    transcript,
    partialTranscript,
    error: sttError,
    startTranscription,
    stopTranscription,
    clearTranscript,
    isReady
  } = useRealtimeSTT({
    onTranscript: (text, isPartial) => {
      if (isPartial) {
        setPreviewText(text);
      } else {
        // Final transcript - append to parent
        onTranscriptComplete(text);
        setPreviewText('');
        clearTranscript();
      }
    },
    onError: (error) => {
      setError(error);
      setIsRecording(false);
    },
    onStatusChange: (recording, transcribing) => {
      setIsRecording(recording);
    }
  });

  // Check if STT is enabled on mount
  useEffect(() => {
    const checkSTTEnabled = async () => {
      try {
        const response = await fetch('/api/settings/');
        if (response.ok) {
          const data = await response.json();
          const sttSettings = data.settings?.stt_settings;
          setIsSTTEnabled(sttSettings?.enabled ?? true);
        }
      } catch (error) {
        console.error('Error checking STT settings:', error);
        setIsSTTEnabled(true); // Default to enabled if check fails
      }
    };
    
    checkSTTEnabled();
  }, []);

  const handleToggleRecording = useCallback(async () => {
    if (disabled || !isSTTEnabled) return;
    
    if (isRecording) {
      stopTranscription();
      setPreviewText('');
    } else {
      setError(null);
      clearTranscript();
      await startTranscription();
    }
  }, [disabled, isSTTEnabled, isRecording, startTranscription, stopTranscription, clearTranscript]);

  const getButtonState = () => {
    if (!isSTTEnabled) return 'disabled';
    if (error || sttError) return 'error';
    if (isRecording) return 'recording';
    if (isTranscribing) return 'transcribing';
    if (!isConnected) return 'disconnected';
    return 'idle';
  };

  const getButtonIcon = () => {
    const state = getButtonState();
    
    switch (state) {
      case 'recording':
        return <Mic className="w-4 h-4" />;
      case 'transcribing':
        return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'error':
      case 'disabled':
        return <MicOff className="w-4 h-4" />;
      default:
        return <Mic className="w-4 h-4" />;
    }
  };

  const getButtonColor = () => {
    const state = getButtonState();
    
    switch (state) {
      case 'recording':
        return 'bg-red-600 hover:bg-red-700 text-white animate-pulse';
      case 'transcribing':
        return 'bg-blue-600 hover:bg-blue-700 text-white';
      case 'error':
        return 'bg-red-600 hover:bg-red-700 text-white';
      case 'disabled':
        return 'bg-gray-600 text-gray-400 cursor-not-allowed';
      case 'disconnected':
        return 'bg-yellow-600 hover:bg-yellow-700 text-white';
      default:
        return 'bg-gray-600 hover:bg-gray-700 text-white';
    }
  };

  const getTooltipText = () => {
    if (!isSTTEnabled) return 'STT is disabled in Settings';
    if (error || sttError) return `Error: ${error || sttError}`;
    if (isRecording) return 'Click to stop recording';
    if (isTranscribing) return 'Processing audio...';
    if (!isConnected) return 'Connecting to STT service...';
    return 'Click to start recording';
  };

  // Don't render if STT is disabled
  if (!isSTTEnabled) {
    return null;
  }

  return (
    <div className={`relative ${position === 'absolute' ? 'absolute' : ''} ${className}`}>
      {/* Microphone Button */}
      <button
        onClick={handleToggleRecording}
        disabled={disabled || !isSTTEnabled || !isReady}
        className={`
          flex items-center justify-center w-8 h-8 rounded-full transition-all duration-200
          ${getButtonColor()}
          ${disabled || !isSTTEnabled || !isReady ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
          focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900
        `}
        title={getTooltipText()}
      >
        {getButtonIcon()}
      </button>

      {/* Live Preview */}
      {showPreview && (previewText || partialTranscript) && (
        <div className="absolute top-full left-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg z-50">
          <div className="text-xs text-gray-400 mb-1">Live transcription:</div>
          <div className="text-sm text-white whitespace-pre-wrap">
            {previewText || partialTranscript}
            {isRecording && <span className="animate-pulse">|</span>}
          </div>
        </div>
      )}

      {/* Error Display */}
      {(error || sttError) && (
        <div className="absolute top-full left-0 mt-2 w-64 bg-red-900/20 border border-red-500/30 rounded-lg p-3 shadow-lg z-50">
          <div className="text-xs text-red-400">
            {error || sttError}
          </div>
        </div>
      )}
    </div>
  );
}
