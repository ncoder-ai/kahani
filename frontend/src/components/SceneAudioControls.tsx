import React from 'react';
import { useTTS } from '@/hooks/useTTS';
import { Play, Pause, RotateCcw, Volume2 } from 'lucide-react';

interface SceneAudioControlsProps {
  sceneId: number;
  className?: string;
}

export const SceneAudioControls: React.FC<SceneAudioControlsProps> = ({ sceneId, className = '' }) => {
  const {
    isGenerating,
    isPlaying,
    hasAudio,
    progress,
    error,
    currentChunk,
    totalChunks,
    togglePlayback,
    generate,
    seek,
  } = useTTS({ sceneId });

  const formatTime = (seconds: number): string => {
    if (!seconds || !isFinite(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`bg-gray-800/50 border border-gray-700 rounded-lg p-3 ${className}`}>
      <div className="flex items-center gap-3">
        {/* Play/Pause Button */}
        <button
          onClick={togglePlayback}
          disabled={isGenerating}
          className="flex items-center justify-center w-10 h-10 rounded-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed transition-colors"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isGenerating ? (
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent" />
          ) : isPlaying ? (
            <Pause className="w-5 h-5 text-white" />
          ) : (
            <Play className="w-5 h-5 text-white ml-0.5" />
          )}
        </button>

        {/* Progress Bar */}
        <div className="flex-1">
          <div
            className="h-2 bg-gray-700 rounded-full cursor-pointer relative group"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const percentage = ((e.clientX - rect.left) / rect.width) * 100;
              seek(percentage);
            }}
          >
            <div
              className="h-full bg-purple-600 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
            {/* Hover indicator */}
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <div className="h-full bg-purple-400/20 rounded-full" />
            </div>
          </div>
        </div>

        {/* Regenerate Button */}
        {hasAudio && !isGenerating && (
          <button
            onClick={() => generate()}
            disabled={isGenerating}
            className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:cursor-not-allowed transition-colors"
            title="Regenerate audio"
          >
            <RotateCcw className="w-4 h-4 text-gray-300" />
          </button>
        )}

        {/* Audio Icon */}
        <Volume2 className="w-5 h-5 text-gray-400" />
      </div>

      {/* Error Message */}
      {error && (
        <div className="mt-2 text-xs text-red-400 flex items-center gap-1">
          <span className="font-semibold">Error:</span>
          <span>{error}</span>
        </div>
      )}

      {/* Status Text */}
      {!error && (
        <div className="mt-2 text-xs text-gray-500">
          {isGenerating && 'Generating audio...'}
          {!isGenerating && !hasAudio && 'Click play to generate narration'}
          {!isGenerating && hasAudio && !isPlaying && 'Ready to play'}
          {isPlaying && totalChunks > 1 && `Playing chunk ${currentChunk + 1}/${totalChunks}...`}
          {isPlaying && totalChunks === 1 && 'Playing...'}
        </div>
      )}
    </div>
  );
};
