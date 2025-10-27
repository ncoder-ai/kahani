'use client';

import React from 'react';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { SpeakerWaveIcon } from '@heroicons/react/24/outline';
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
    // IMMEDIATE feedback for debugging
    console.log('[SceneTTSButton] BUTTON CLICKED for scene:', sceneId);
    
    if (isThisSceneError) {
      console.log('[SceneTTSButton] Retrying after error');
      // Clear error and retry
      stop();
      setTimeout(() => playScene(sceneId), 100);
    } else if (!isThisScenePlaying && !isThisSceneGenerating) {
      console.log('[SceneTTSButton] Starting playScene');
      playScene(sceneId);
    } else {
      console.log('[SceneTTSButton] Button disabled - already playing/generating');
    }
  };
  
  return (
    <div className={className}>
      <button
        onClick={handleClick}
        disabled={isThisScenePlaying || isThisSceneGenerating}
        className={`
          w-full flex items-center gap-2 px-4 py-2 rounded-lg transition-all
          ${isThisSceneError
            ? 'bg-red-600 hover:bg-red-700 text-white'
            : isThisScenePlaying || isThisSceneGenerating
            ? 'bg-blue-600 text-white cursor-not-allowed' 
            : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
          }
        `}
        title={
          isThisSceneError ? 'Error - click to retry'
          : isThisScenePlaying ? 'Playing...' 
          : isThisSceneGenerating ? 'Generating audio...' 
          : 'Click to hear scene narration'
        }
      >
        {isThisSceneError ? (
          <>
            <SpeakerWaveIcon className="w-5 h-5" />
            <span className="text-sm">Retry TTS</span>
          </>
        ) : isThisScenePlaying ? (
          <>
            <SpeakerWaveSolidIcon className="w-5 h-5 animate-pulse" />
            <span className="text-sm">Playing...</span>
          </>
        ) : isThisSceneGenerating ? (
          <>
            <SpeakerWaveSolidIcon className="w-5 h-5 animate-spin" />
            <span className="text-sm">Generating...</span>
          </>
        ) : (
          <>
            <SpeakerWaveIcon className="w-5 h-5" />
            <span className="text-sm">Narrate</span>
          </>
        )}
      </button>
      
      {/* Error Message Display */}
      {isThisSceneError && (
        <div className="mt-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
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
