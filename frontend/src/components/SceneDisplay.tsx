'use client';

import FormattedText from './FormattedText';

interface Scene {
  id: number;
  sequence_number: number;
  title: string;
  content: string;
  location: string;
  characters_present: string[];
}

interface SceneDisplayProps {
  scene: Scene;
  format: string; // 'default', 'bubble', 'card', 'minimal'
  showTitle: boolean;
  isEditing: boolean;
  editContent: string;
  onStartEdit: (scene: Scene) => void;
  onSaveEdit: (sceneId: number, content: string) => void;
  onCancelEdit: () => void;
  onContentChange: (content: string) => void;
}

export default function SceneDisplay({ 
  scene, 
  format, 
  showTitle, 
  isEditing, 
  editContent, 
  onStartEdit, 
  onSaveEdit, 
  onCancelEdit, 
  onContentChange 
}: SceneDisplayProps) {
  const getSceneClassName = () => {
    const baseClasses = "transition-all duration-200";
    
    switch (format) {
      case 'bubble':
        return `${baseClasses} bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-2xl p-6 mx-4 my-4 border border-blue-500/20 shadow-lg backdrop-blur-sm`;
      case 'card':
        return `${baseClasses} bg-gray-800 rounded-lg p-6 mx-2 my-3 border border-gray-600 shadow-md hover:shadow-lg hover:border-gray-500`;
      case 'minimal':
        return `${baseClasses} py-4 border-l-2 border-gray-600 pl-4 my-2`;
      default:
        return `${baseClasses} bg-gray-800/50 rounded-md p-4 my-2 border border-gray-700/50`;
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
          Scene {scene.sequence_number}: {scene.title}
        </div>
      )}
      
      {isEditing ? (
        <div className="space-y-3">
          <textarea
            value={editContent}
            onChange={(e) => onContentChange(e.target.value)}
            className="w-full h-40 bg-gray-700 text-white rounded-md p-3 resize-none focus:ring-2 focus:ring-blue-500 focus:outline-none"
            placeholder="Edit scene content..."
          />
          <div className="flex space-x-2">
            <button
              onClick={() => onSaveEdit(scene.id, editContent)}
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
          className={`${getContentClassName()} cursor-pointer hover:bg-gray-700/20 rounded p-2 transition-colors`}
          onClick={() => onStartEdit(scene)}
        >
          <FormattedText content={scene.content} />
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