'use client';

import React from 'react';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { PlayIcon, PauseIcon, StopIcon, SpeakerWaveIcon } from '@heroicons/react/24/solid';

export const GlobalTTSWidget: React.FC = () => {
  const { 
    isPlaying, 
    isGenerating, 
    currentSceneId,
    progress, 
    totalChunks, 
    chunksReceived,
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
    <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-700 rounded-lg shadow-xl p-4 min-w-[300px] z-50">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <SpeakerWaveIcon className="w-5 h-5 text-blue-400" />
          <span className="text-sm font-medium text-gray-200">
            {isGenerating ? 'Generating Audio...' : isPlaying ? 'Playing' : 'Ready'}
          </span>
        </div>
        {currentSceneId && (
          <span className="text-xs text-gray-400">Scene {currentSceneId}</span>
        )}
      </div>
      
      {/* Progress Bar */}
      {totalChunks > 0 && (
        <div className="mb-3">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{chunksReceived} / {totalChunks} chunks</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div 
              className="bg-blue-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
      
      {/* Error Display */}
      {error && (
        <div className="mb-3 text-xs text-red-400 bg-red-900/20 p-2 rounded flex items-center justify-between">
          <span>{error}</span>
          <button 
            onClick={stop}
            className="ml-2 text-red-400 hover:text-red-300"
            title="Dismiss"
          >
            ×
          </button>
        </div>
      )}
      
      {/* Controls */}
      <div className="flex items-center gap-2">
        {isPlaying ? (
          <button
            onClick={pause}
            className="flex items-center justify-center w-10 h-10 bg-gray-700 hover:bg-gray-600 rounded-full transition-colors"
            title="Pause"
          >
            <PauseIcon className="w-5 h-5 text-gray-200" />
          </button>
        ) : (
          <button
            onClick={resume}
            className="flex items-center justify-center w-10 h-10 bg-blue-600 hover:bg-blue-500 rounded-full transition-colors"
            title="Resume"
            disabled={!currentSceneId}
          >
            <PlayIcon className="w-5 h-5 text-white" />
          </button>
        )}
        
        <button
          onClick={stop}
          className="flex items-center justify-center w-10 h-10 bg-gray-700 hover:bg-gray-600 rounded-full transition-colors"
          title="Stop"
        >
          <StopIcon className="w-5 h-5 text-gray-200" />
        </button>
        
        <div className="flex-1" />
        
        {isGenerating && (
          <div className="flex items-center gap-2">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400" />
            <span className="text-xs text-gray-400">Generating...</span>
          </div>
        )}
      </div>
    </div>
  );
};
