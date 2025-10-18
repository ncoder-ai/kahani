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
  const { playScene, currentSceneId, isPlaying, isGenerating } = useGlobalTTS();
  
  // Show as active only when this scene is currently playing (not just generating)
  const isThisScenePlaying = currentSceneId === sceneId && isPlaying;
  const isThisSceneGenerating = currentSceneId === sceneId && isGenerating && !isPlaying;
  
  const handleClick = () => {
    if (!isThisScenePlaying && !isThisSceneGenerating) {
      playScene(sceneId);
    }
  };
  
  return (
    <button
      onClick={handleClick}
      disabled={isThisScenePlaying || isThisSceneGenerating}
      className={`
        flex items-center gap-2 px-4 py-2 rounded-lg transition-all
        ${isThisScenePlaying || isThisSceneGenerating
          ? 'bg-blue-600 text-white cursor-not-allowed' 
          : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
        }
        ${className}
      `}
      title={isThisScenePlaying ? 'Playing...' : isThisSceneGenerating ? 'Generating audio...' : 'Click to hear scene narration'}
    >
      {isThisScenePlaying ? (
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
  );
};
