'use client';

import React from 'react';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { SpeakerWaveIcon, StopIcon, PauseIcon, PlayIcon } from '@heroicons/react/24/outline';
import { SpeakerWaveIcon as SpeakerWaveSolidIcon } from '@heroicons/react/24/solid';
import { Loader2 } from 'lucide-react';

interface SceneTTSButtonProps {
  sceneId: number;
  className?: string;
}

export const SceneTTSButton: React.FC<SceneTTSButtonProps> = ({ sceneId, className = '' }) => {
  const { playScene, stop, pause, resume, clearError, currentSceneId, isPlaying, isPaused, isGenerating, error, supportsPause } = useGlobalTTS();

  // Show as active only when this scene is currently playing (not just generating)
  const isThisScenePlaying = currentSceneId === sceneId && isPlaying;
  const isThisScenePaused = currentSceneId === sceneId && isPaused;
  const isThisSceneGenerating = currentSceneId === sceneId && isGenerating && !isPlaying && !isPaused;
  const isThisSceneError = currentSceneId === sceneId && error;
  const isThisSceneActive = isThisScenePlaying || isThisScenePaused || isThisSceneGenerating;

  const handleClick = () => {
    if (isThisSceneError) {
      // Clear error and retry
      stop();
      setTimeout(() => playScene(sceneId), 100);
    } else if (isThisScenePaused) {
      // Resume from where we paused (native path) — Web Audio fallback
      // would have already stopped, so we never hit this branch there.
      resume();
    } else if (isThisScenePlaying) {
      // Native: pause and retain queued buffers. Web: stop (pause is wired
      // to stopAll inside the context for the Web Audio path).
      if (supportsPause) pause();
      else stop();
    } else if (isThisSceneGenerating) {
      // Cancel mid-preparation.
      stop();
    } else {
      // Start TTS
      playScene(sceneId);
    }
  };
  
  // Show an explicit stop button next to the main play/pause control
  // only when (a) the active engine supports real pause (native iOS) AND
  // (b) audio is currently playing or paused. On web/mobile-Safari the
  // main button already stops on click, so a separate stop is redundant
  // there. When idle/generating/error we don't render it either — generating
  // already has its own "click to cancel" semantic on the main button.
  const showStopButton = supportsPause && (isThisScenePlaying || isThisScenePaused);

  return (
    <div className={`inline-flex items-center gap-1 ${className || ''}`}>
      <button
        onClick={handleClick}
        className={`
          flex items-center justify-center transition-all duration-200
          ${isThisSceneError
            ? 'text-red-400 hover:text-red-300 hover:bg-gray-800/50 rounded p-1'
            : isThisSceneActive
            ? 'text-blue-400 hover:text-blue-300 hover:bg-gray-800/50 rounded p-1'
            : 'text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1'
          }
        `}
        title={
          isThisSceneError ? 'Error - click to retry'
          : isThisScenePaused ? 'Click to resume narration'
          : isThisScenePlaying ? (supportsPause ? 'Click to pause narration' : 'Click to stop narration')
          : isThisSceneGenerating ? 'Preparing audio… click to cancel'
          : 'Click to hear scene narration'
        }
      >
        {isThisSceneError ? (
          <SpeakerWaveIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
        ) : isThisSceneGenerating ? (
          // "Preparing" state — spinner icon makes it visibly distinct from
          // the steady icon used during actual playback. Without this the
          // user sees the same icon for "synthesizing" (which can take
          // 5–15s on a multi-speaker scene) as for "playing", giving the
          // wrong impression that the click was a no-op.
          <Loader2 className="w-3.5 h-3.5 md:w-4 md:h-4 animate-spin" />
        ) : isThisScenePaused ? (
          <PlayIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
        ) : isThisScenePlaying ? (
          supportsPause
            ? <PauseIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
            : <StopIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
        ) : (
          <SpeakerWaveIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
        )}
      </button>

      {showStopButton && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            stop();
          }}
          className="flex items-center justify-center text-gray-400 hover:text-red-400 hover:bg-gray-800/50 rounded p-1 transition-all duration-200"
          title="Stop narration"
          aria-label="Stop narration"
        >
          <StopIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
        </button>
      )}
      
      {/* Error Message Display
          Anchor to the right edge of the button so the popup grows leftward
          toward the visible area instead of running off the right edge of
          the viewport. Cap width to (viewport - 1rem) for narrow phones,
          and let long error strings wrap rather than push the layout. */}
      {isThisSceneError && (
        <div className="absolute top-10 right-0 w-64 max-w-[calc(100vw-1rem)] p-3 bg-red-500/10 border border-red-500/30 rounded-lg backdrop-blur-sm z-10">
          <div className="flex items-start gap-2">
            <div className="flex-shrink-0 mt-0.5">
              <svg className="w-4 h-4 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-red-400 mb-1">TTS Error</div>
              <div className="text-xs text-red-300 break-words">{error}</div>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                clearError();
              }}
              className="flex-shrink-0 p-0.5 rounded hover:bg-red-500/20 transition-colors"
              title="Dismiss error"
            >
              <svg className="w-4 h-4 text-red-400 hover:text-red-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
