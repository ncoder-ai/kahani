'use client';

import React from 'react';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { SpeakerWaveIcon, StopIcon } from '@heroicons/react/24/outline';
import { SpeakerWaveIcon as SpeakerWaveSolidIcon } from '@heroicons/react/24/solid';

interface SceneTTSButtonProps {
  sceneId: number;
  className?: string;
}

export const SceneTTSButton: React.FC<SceneTTSButtonProps> = ({ sceneId, className = '' }) => {
  const { playScene, stop, currentSceneId, isPlaying, isGenerating, error } = useGlobalTTS();
  
  // Show as active only when this scene is currently playing (not just generating)
  const isThisScenePlaying = currentSceneId === sceneId && isPlaying;
  const isThisSceneGenerating = currentSceneId === sceneId && isGenerating && !isPlaying;
  const isThisSceneError = currentSceneId === sceneId && error;
  
  const handleClick = () => {
    if (isThisSceneError) {
      // Clear error and retry
      stop();
      setTimeout(() => playScene(sceneId), 100);
    } else if (isThisScenePlaying || isThisSceneGenerating) {
      // Stop TTS and clear session
      stop();
    } else {
      // Start TTS
      playScene(sceneId);
    }
  };
  
  return (
    <div className={`absolute -top-2 -right-2 z-10 ${className}`}>
      <button
        onClick={handleClick}
        className={`
          w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200
          backdrop-blur-sm border shadow-lg
          ${isThisSceneError
            ? 'bg-red-500/90 hover:bg-red-600/90 text-white border-red-400/50'
            : isThisScenePlaying || isThisSceneGenerating
            ? 'bg-blue-500/90 hover:bg-blue-600/90 text-white border-blue-400/50' 
            : 'bg-gray-700/90 hover:bg-gray-600/90 text-gray-200 border-gray-500/50'
          }
        `}
        title={
          isThisSceneError ? 'Error - click to retry'
          : isThisScenePlaying ? 'Click to stop narration' 
          : isThisSceneGenerating ? 'Generating audio - click to stop' 
          : 'Click to hear scene narration'
        }
      >
        {isThisSceneError ? (
          <SpeakerWaveIcon className="w-4 h-4" />
        ) : isThisScenePlaying || isThisSceneGenerating ? (
          <StopIcon className="w-4 h-4" />
        ) : (
          <SpeakerWaveIcon className="w-4 h-4" />
        )}
      </button>
      
      {/* Error Message Display */}
      {isThisSceneError && (
        <div className="absolute top-10 left-0 w-64 p-3 bg-red-500/10 border border-red-500/30 rounded-lg backdrop-blur-sm">
          <div className="flex items-start gap-2">
            <div className="flex-shrink-0 mt-0.5">
              <svg className="w-4 h-4 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="flex-1">
              <div className="text-xs font-semibold text-red-400 mb-1">TTS Error</div>
              <div className="text-xs text-red-300">{error}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
