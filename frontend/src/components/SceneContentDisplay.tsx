'use client';

import { useState, useEffect, ReactNode } from 'react';
import { PencilIcon, TrashIcon, ClipboardIcon } from '@heroicons/react/24/outline';
import { GitFork, Image, RotateCcw } from 'lucide-react';
import SceneDisplay from './SceneDisplay';
import { SceneTTSButton } from './SceneTTSButton';

interface SceneContentDisplayProps {
  scene: {
    id: number;
    sequence_number: number;
    title: string;
    content: string;
    location: string;
    characters_present: string[];
    variant_id?: number;
  };
  sceneNumber?: number;
  userSettings?: any;
  // Display overrides
  showTitle?: boolean;
  format?: string;
  // Edit
  isEditing: boolean;
  editContent: string;
  onSaveEdit?: (sceneId: number, content: string, variantId?: number) => void | Promise<void>;
  onCancelEdit?: () => void;
  onContentChange?: (content: string) => void;
  // Streaming
  streamingContinuation?: string;
  isStreamingContinuation?: boolean;
  isStreamingVariant?: boolean;
  // Action button callbacks — button only shown if callback is provided
  onEdit?: () => void;
  onCopy?: () => void;
  onDelete?: () => void;
  onBranch?: () => void;
  onImage?: () => void;
  onRegenerate?: () => void;
  // TTS — uses SceneTTSButton when scene.id > 0 and showTTS is true
  showTTS?: boolean;
  // Custom TTS handler (for roleplay multi-voice)
  onPlayTTS?: () => void;
  isPlayingTTS?: boolean;
  // Delete mode visuals
  isInDeleteMode?: boolean;
  isSceneSelectedForDeletion?: boolean;
  // Slot for content above SceneDisplay (e.g. character avatar)
  headerContent?: ReactNode;
}

export default function SceneContentDisplay({
  scene,
  sceneNumber,
  userSettings,
  showTitle,
  format,
  isEditing,
  editContent,
  onSaveEdit,
  onCancelEdit,
  onContentChange,
  streamingContinuation,
  isStreamingContinuation,
  isStreamingVariant,
  onEdit,
  onCopy,
  onDelete,
  onBranch,
  onImage,
  onRegenerate,
  showTTS,
  onPlayTTS,
  isPlayingTTS,
  isInDeleteMode,
  isSceneSelectedForDeletion,
  headerContent,
}: SceneContentDisplayProps) {
  const [isClient, setIsClient] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  const handleCopy = async () => {
    if (!onCopy) return;
    onCopy();
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2000);
  };

  const resolvedFormat = format || userSettings?.scene_display_format || 'default';
  const resolvedShowTitle = showTitle ?? (userSettings?.show_scene_titles === true);

  return (
    <div className={isStreamingVariant ? 'relative streaming-variant' : 'relative'} suppressHydrationWarning>
      {isStreamingVariant && (
        <div className="absolute top-0 right-0 bg-pink-600 text-white text-xs px-2 py-1 rounded-full animate-pulse z-10">
          Generating...
        </div>
      )}

      {/* Quick Action Buttons — top-right */}
      {isClient && !isEditing && (
        <div className="absolute -top-4 -right-4 md:-top-2 md:-right-2 z-10 flex items-center gap-1">
          {onEdit && (
            <button
              onClick={onEdit}
              className="flex items-center justify-center transition-all duration-200 flex-shrink-0 text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1"
              title="Edit"
            >
              <PencilIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
            </button>
          )}

          {onCopy && (
            <button
              onClick={handleCopy}
              className={
                'flex items-center justify-center transition-all duration-200 flex-shrink-0 ' +
                (copySuccess
                  ? 'text-green-400 hover:text-green-300'
                  : 'text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1')
              }
              title={copySuccess ? 'Copied!' : 'Copy text'}
            >
              {copySuccess ? (
                <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              ) : (
                <ClipboardIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
              )}
            </button>
          )}

          {onDelete && (
            <button
              onClick={onDelete}
              className={
                'flex items-center justify-center transition-all duration-200 flex-shrink-0 ' +
                (isInDeleteMode && isSceneSelectedForDeletion
                  ? 'text-red-400 hover:text-red-300'
                  : isInDeleteMode
                  ? 'text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1'
                  : 'text-gray-400 hover:text-red-400 hover:bg-gray-800/50 rounded p-1')
              }
              title={
                isInDeleteMode
                  ? (isSceneSelectedForDeletion ? 'Cancel delete mode' : 'Delete from this scene onwards instead')
                  : 'Delete from this scene onwards'
              }
            >
              <TrashIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
            </button>
          )}

          {onBranch && (
            <button
              onClick={onBranch}
              className="flex items-center justify-center transition-all duration-200 flex-shrink-0 text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1"
              title="Create branch from this scene"
            >
              <GitFork className="w-3.5 h-3.5 md:w-4 md:h-4" />
            </button>
          )}

          {onImage && (
            <button
              onClick={onImage}
              className="flex items-center justify-center transition-all duration-200 flex-shrink-0 text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1"
              title="Generate image"
            >
              <Image className="w-3.5 h-3.5 md:w-4 md:h-4" />
            </button>
          )}

          {onRegenerate && (
            <button
              onClick={onRegenerate}
              className="flex items-center justify-center transition-all duration-200 flex-shrink-0 text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1"
              title="Regenerate"
            >
              <RotateCcw className="w-3.5 h-3.5 md:w-4 md:h-4" />
            </button>
          )}

          {onPlayTTS && (
            <button
              onClick={onPlayTTS}
              className={`flex items-center justify-center transition-all duration-200 flex-shrink-0 rounded p-1 ${
                isPlayingTTS ? 'text-blue-400' : 'text-gray-400 hover:text-gray-300 hover:bg-gray-800/50'
              }`}
              title={isPlayingTTS ? 'Playing...' : 'Play TTS'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 md:w-4 md:h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
              </svg>
            </button>
          )}

          {showTTS && !onPlayTTS && scene.id > 0 && (
            <div className="flex-shrink-0">
              <SceneTTSButton sceneId={scene.id} className="relative" />
            </div>
          )}
        </div>
      )}

      {headerContent}

      <SceneDisplay
        scene={scene}
        sceneNumber={sceneNumber}
        format={resolvedFormat}
        containerStyle="lines"
        showTitle={resolvedShowTitle}
        isEditing={isEditing}
        editContent={editContent}
        onStartEdit={() => onEdit?.()}
        onSaveEdit={onSaveEdit || (() => {})}
        onCancelEdit={onCancelEdit || (() => {})}
        onContentChange={onContentChange || (() => {})}
        streamingContinuation={streamingContinuation}
        isStreamingContinuation={isStreamingContinuation}
        isStreamingVariant={isStreamingVariant}
        userSettings={userSettings}
      />
    </div>
  );
}
