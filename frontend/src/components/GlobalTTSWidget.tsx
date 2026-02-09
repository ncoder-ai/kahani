'use client';

import React from 'react';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { PlayIcon, PauseIcon, StopIcon, SpeakerWaveIcon } from '@heroicons/react/24/solid';

export const GlobalTTSWidget: React.FC = () => {
  const { 
    isPlaying, 
    isGenerating, 
    currentSceneId,
    error,
    stop,
    pause,
    resume
  } = useGlobalTTS();
  
  // Don't show if nothing is playing or generating and no error
  if (!isGenerating && !isPlaying && !currentSceneId && !error) {
    return null;
  }
  
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 mb-4">
      {/* Status */}
      <div className="flex items-center gap-2 mb-2">
        <SpeakerWaveIcon className="w-4 h-4 text-blue-400 flex-shrink-0" />
        <span className="text-xs text-gray-300 flex-1">
          {error ? (
            <span className="text-red-400">{error}</span>
          ) : isGenerating ? (
            'Generating...'
          ) : isPlaying ? (
            `Narrating Scene ${currentSceneId}`
          ) : (
            `Paused - Scene ${currentSceneId}`
          )}
        </span>
      </div>
      
      {/* Controls - Icon buttons only */}
      <div className="flex items-center justify-center gap-2">
        {isPlaying ? (
          <button
            onClick={pause}
            className="flex items-center justify-center w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
            title="Pause"
            aria-label="Pause"
          >
            <PauseIcon className="w-4 h-4 text-gray-200" />
          </button>
        ) : (
          <button
            onClick={resume}
            className="flex items-center justify-center w-8 h-8 bg-blue-600 hover:bg-blue-500 rounded transition-colors"
            title="Resume"
            aria-label="Play"
            disabled={!currentSceneId}
          >
            <PlayIcon className="w-4 h-4 text-white" />
          </button>
        )}
        
        <button
          onClick={stop}
          className="flex items-center justify-center w-8 h-8 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
          title="Stop"
          aria-label="Stop"
        >
          <StopIcon className="w-4 h-4 text-gray-200" />
        </button>
      </div>
    </div>
  );
};
