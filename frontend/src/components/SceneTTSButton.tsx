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
  
  const isThisScenePlaying = currentSceneId === sceneId && (isPlaying || isGenerating);
  
  const handleClick = () => {
    if (!isThisScenePlaying) {
      playScene(sceneId);
    }
  };
  
  return (
    <button
      onClick={handleClick}
      disabled={isThisScenePlaying}
      className={`
        flex items-center gap-2 px-4 py-2 rounded-lg transition-all
        ${isThisScenePlaying 
          ? 'bg-blue-600 text-white cursor-not-allowed' 
          : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
        }
        ${className}
      `}
      title={isThisScenePlaying ? 'Playing...' : 'Click to hear scene narration'}
    >
      {isThisScenePlaying ? (
        <>
          <SpeakerWaveSolidIcon className="w-5 h-5 animate-pulse" />
          <span className="text-sm">Playing...</span>
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
