'use client';

import { useRef, useEffect } from 'react';
import FormattedText from './FormattedText';

interface Scene {
  id: number;
  sequence_number: number;
  title: string;
  content: string;
  location: string;
  characters_present: string[];
  variant_id?: number;
}

interface SceneDisplayProps {
  scene: Scene;
  sceneNumber?: number; // Use this instead of scene.sequence_number for consistent numbering
  format: string; // 'default', 'bubble', 'card', 'minimal'
  containerStyle?: string; // 'lines' or 'cards'
  showTitle: boolean;
  isEditing: boolean;
  editContent: string;
  onStartEdit: (scene: Scene) => void;
  onSaveEdit: (sceneId: number, content: string, variantId?: number) => void | Promise<void>;
  onCancelEdit: () => void;
  onContentChange: (content: string) => void;
  streamingContinuation?: string;
  isStreamingContinuation?: boolean;
  isStreamingVariant?: boolean;
  userSettings?: any; // User settings including scene_edit_mode
}

export default function SceneDisplay({ 
  scene, 
  sceneNumber,
  format, 
  containerStyle = 'lines',
  showTitle, 
  isEditing, 
  editContent, 
  onStartEdit, 
  onSaveEdit, 
  onCancelEdit, 
  onContentChange,
  streamingContinuation,
  isStreamingContinuation,
  isStreamingVariant = false,
  userSettings
}: SceneDisplayProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const contentEditableRef = useRef<HTMLDivElement>(null);
  const editMode = userSettings?.scene_edit_mode || 'textarea';

  // Auto-resize textarea based on content
  useEffect(() => {
    if (isEditing && editMode === 'textarea' && textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.max(200, textareaRef.current.scrollHeight)}px`;
    }
  }, [isEditing, editContent, editMode]);

  // Focus textarea when entering edit mode
  useEffect(() => {
    if (isEditing && editMode === 'textarea' && textareaRef.current) {
      // Focus with preventScroll to avoid unwanted scroll jumps on mobile
      textareaRef.current.focus({ preventScroll: true });
    }
  }, [isEditing, editMode]);

  // Focus contenteditable when entering edit mode and set initial content
  useEffect(() => {
    if (isEditing && editMode === 'contenteditable' && contentEditableRef.current) {
      // Only set content if it's different to avoid cursor jumping
      if (contentEditableRef.current.textContent !== editContent) {
        contentEditableRef.current.textContent = editContent;
      }
      // Use preventScroll to avoid unwanted scroll jumps on mobile
      contentEditableRef.current.focus({ preventScroll: true });
      // Place cursor at end
      const range = document.createRange();
      const selection = window.getSelection();
      if (contentEditableRef.current.firstChild) {
        range.selectNodeContents(contentEditableRef.current);
        range.collapse(false);
        selection?.removeAllRanges();
        selection?.addRange(range);
      }
    }
  }, [isEditing, editMode]); // Don't include editContent to avoid cursor jumping
  const getSceneClassName = () => {
    const baseClasses = "relative transition-all duration-200";
    
    // If user prefers simple lines, override format
    if (containerStyle === 'lines') {
      return `${baseClasses} py-4 my-2`;
    }
    
    // Otherwise use the selected format (bubble, card, etc.)
    switch (format) {
      case 'bubble':
        return `${baseClasses} theme-scene-bubble rounded-2xl p-6 mx-4 my-4 shadow-lg backdrop-blur-sm`;
      case 'card':
        return `${baseClasses} theme-card rounded-lg p-6 mx-2 my-3 shadow-md theme-card-hover`;
      case 'minimal':
        return `${baseClasses} py-4 my-2`;
      default:
        return `${baseClasses} theme-card rounded-md p-4 my-2 border border-gray-700/50`;
    }
  };

  const getTitleClassName = () => {
    switch (format) {
      case 'bubble':
        return "text-lg font-semibold text-blue-200 mb-3 flex items-center";
      case 'card':
        return "text-lg font-semibold text-gray-200 mb-3 border-b border-gray-600 pb-2";
      case 'minimal':
        return "text-sm font-medium text-gray-400 mb-2";
      default:
        return "text-md font-semibold text-gray-300 mb-2";
    }
  };

  const getContentClassName = () => {
    switch (format) {
      case 'bubble':
        return "text-gray-100 leading-relaxed";
      case 'card':
        return "text-gray-200 leading-relaxed";
      case 'minimal':
        return "text-gray-300 text-sm leading-normal";
      default:
        return "text-gray-200 leading-normal";
    }
  };

  return (
    <div className={getSceneClassName()}>
      {showTitle && (
        <div className={getTitleClassName()}>
          {format === 'bubble' && <span className="w-2 h-2 bg-blue-400 rounded-full mr-2"></span>}
          {scene.title && scene.title.trim() !== '' ? scene.title : `Scene ${sceneNumber || scene.sequence_number}`}
        </div>
      )}
      
      {isEditing ? (
        <div className="space-y-3">
          {editMode === 'textarea' ? (
            // Mode A: Auto-expanding Textarea
            <textarea
              ref={textareaRef}
              value={editContent}
              onChange={(e) => {
                onContentChange(e.target.value);
                // Auto-resize
                if (textareaRef.current) {
                  textareaRef.current.style.height = 'auto';
                  textareaRef.current.style.height = `${Math.max(200, textareaRef.current.scrollHeight)}px`;
                }
              }}
              className="w-full min-h-[200px] bg-gray-700 text-white rounded-md p-3 resize-y focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
              placeholder="Edit scene content..."
              style={{ height: 'auto' }}
            />
          ) : (
            // Mode B: ContentEditable WYSIWYG
            <div
              ref={contentEditableRef}
              contentEditable
              suppressContentEditableWarning
              onInput={(e) => {
                const text = e.currentTarget.textContent || '';
                onContentChange(text);
              }}
              className={`${getContentClassName()} w-full min-h-[200px] bg-gray-700/50 text-white rounded-md p-3 focus:ring-2 focus:ring-blue-500 focus:outline-none border-2 border-blue-500/50 transition-all`}
              style={{ 
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word'
              }}
            >
              {editContent}
            </div>
          )}
          <div className="flex space-x-2">
            <button
              onClick={() => onSaveEdit(scene.id, editContent, scene.variant_id)}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm transition-colors"
            >
              Save
            </button>
            <button
              onClick={onCancelEdit}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div 
          className={`${getContentClassName()} rounded p-2`}
        >
          <FormattedText content={scene.content} />
          {isStreamingVariant && (
            <span className="inline-block w-2 h-5 bg-pink-500 ml-1 animate-pulse"></span>
          )}
          {streamingContinuation && (
            <span className="streaming-continuation">
              <FormattedText content={streamingContinuation} />
              {isStreamingContinuation && (
                <span className="inline-block w-2 h-5 bg-blue-400 ml-1 animate-pulse"></span>
              )}
            </span>
          )}
        </div>
      )}
      
      {scene.location && format !== 'minimal' && (
        <div className="mt-3 text-sm text-gray-400">
          📍 {scene.location}
        </div>
      )}
      
      {scene.characters_present && scene.characters_present.length > 0 && format === 'card' && (
        <div className="mt-2 text-sm text-gray-400">
          👥 {scene.characters_present.join(', ')}
        </div>
      )}
    </div>
  );
}