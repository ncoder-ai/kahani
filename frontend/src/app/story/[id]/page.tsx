'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useParams } from 'next/navigation';
import { useAuthStore, useStoryStore } from '@/store';
import apiClient from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';
import { TokenInfo } from '@/components/TokenInfo';
import { ContextInfo } from '@/components/ContextInfo';
import FormattedText from '@/components/FormattedText';
import SceneDisplay from '@/components/SceneDisplay';
import { 
  BookOpenIcon, 
  FilmIcon,
  PhotoIcon,
  ClockIcon,
  CheckIcon,
  ArrowDownIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  DocumentDuplicateIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  PlayIcon
} from '@heroicons/react/24/outline';

interface Scene {
  id: number;
  sequence_number: number;
  title: string;
  content: string;
  location: string;
  characters_present: string[];
}

interface Story {
  id: number;
  title: string;
  description: string;
  genre: string;
  tone: string;
  world_setting: string;
  status: string;
  scenes: Scene[];
}

export default function StoryPage() {
  const router = useRouter();
  const params = useParams();
  const storyId = parseInt(params.id as string);
  
  const { user } = useAuthStore();
  const [story, setStory] = useState<Story | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [currentChapterIndex, setCurrentChapterIndex] = useState(0);
  const [showLorebook, setShowLorebook] = useState(false);
  const [showChoices, setShowChoices] = useState(true);
  const [directorMode, setDirectorMode] = useState(false);
  const [editingScene, setEditingScene] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [dynamicChoices, setDynamicChoices] = useState<Array<{text: string, order: number}>>([]);
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [storyCharacters, setStoryCharacters] = useState<Array<{name: string, role: string, description: string}>>([]);
  const [showMoreOptions, setShowMoreOptions] = useState(false);
  const [isGeneratingMoreOptions, setIsGeneratingMoreOptions] = useState(false);
  const [sceneHistory, setSceneHistory] = useState<Scene[][]>([]);
  const [currentSceneIndex, setCurrentSceneIndex] = useState(0);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [userSettings, setUserSettings] = useState<any>(null);
  const storyContentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) {
      router.push('/login');
      return;
    }
    loadStory();
    loadUserSettings();
  }, [user, storyId, router]);

  const loadUserSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings.settings);
    } catch (err) {
      console.error('Failed to load user settings:', err);
    }
  };

  // Auto-scroll to bottom when new scenes are added
  useEffect(() => {
    if (storyContentRef.current && story?.scenes && story.scenes.length > 0) {
      const element = storyContentRef.current;
      element.scrollTop = element.scrollHeight;
    }
  }, [story?.scenes?.length]);

  const loadStory = async () => {
    try {
      setIsLoading(true);
      const storyData = await apiClient.getStory(storyId);
      setStory(storyData);
      // Load choices for the current story
      await loadChoices();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load story');
    } finally {
      setIsLoading(false);
    }
  };

  const loadChoices = async () => {
    try {
      const choicesData = await apiClient.getStoryChoices(storyId);
      setDynamicChoices(choicesData.choices || []);
    } catch (err) {
      console.error('Failed to load choices:', err);
      setDynamicChoices([]);
    }
  };

  const generateNewScene = async (prompt?: string) => {
    if (!story) return;
    console.log('generateNewScene called', { storyId: story.id, prompt });
    setError('');
    setIsGenerating(true);
    
    // Clear dynamic choices when generating new scene
    setDynamicChoices([]);
    setShowMoreOptions(false);
    
    try {
      const response = await apiClient.generateScene(story.id, prompt || customPrompt);
      console.log('generateNewScene response', response);

      // Reload the story to get the new scene
      await loadStory();
      setCustomPrompt('');
    } catch (err) {
      console.error('generateNewScene error', err);
      setError(err instanceof Error ? err.message : 'Failed to generate scene');
    } finally {
      setIsGenerating(false);
    }
  };

  const updateScene = async (sceneId: number, content: string) => {
    try {
      // TODO: Implement scene update API call
      console.log('Updating scene:', { sceneId, content });
      // For now, just update locally
      if (story) {
        const updatedStory = {
          ...story,
          scenes: story.scenes.map(scene => 
            scene.id === sceneId ? { ...scene, content } : scene
          )
        };
        setStory(updatedStory);
      }
      setEditingScene(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update scene');
    }
  };

  const startEditingScene = (scene: Scene) => {
    setEditingScene(scene.id);
    setEditContent(scene.content);
  };

  const handleCharacterAdd = (character: any) => {
    const newCharacter = {
      name: character.name,
      role: character.role,
      description: character.description
    };
    setStoryCharacters(prev => [...prev, newCharacter]);
    setShowCharacterQuickAdd(false);
  };

  const generateMoreOptions = async () => {
    if (!story || !story.scenes.length || isGeneratingMoreOptions) return;
    
    setIsGeneratingMoreOptions(true);
    try {
      // Generate fresh choices using the LLM
      const choicesData = await apiClient.generateMoreChoices(storyId);
      const newChoices = choicesData.choices || [];
      
      // Append new choices to existing ones instead of replacing
      setDynamicChoices(prev => [
        ...prev, 
        ...newChoices.map(choice => ({ 
          text: choice.text, 
          order: prev.length + choice.order 
        }))
      ]);
      setShowMoreOptions(true);
    } catch (error) {
      console.error('Failed to generate more options:', error);
    } finally {
      setIsGeneratingMoreOptions(false);
    }
  };

  const regenerateLastScene = async () => {
    if (!story || !story.scenes.length) return;
    
    setIsRegenerating(true);
    try {
      // Store current scenes in history before regeneration
      if (sceneHistory.length === 0 || sceneHistory[sceneHistory.length - 1] !== story.scenes) {
        setSceneHistory(prev => [...prev, [...story.scenes]]);
      }
      
      // Call the regeneration API
      await apiClient.regenerateLastScene(story.id);
      
      // Reload the story to get the new scene
      await loadStory();
    } catch (error) {
      console.error('Failed to regenerate scene:', error);
      setError(error instanceof Error ? error.message : 'Failed to regenerate scene');
    } finally {
      setIsRegenerating(false);
    }
  };

  const goToPreviousScene = () => {
    if (sceneHistory.length > 0) {
      const previousScenes = sceneHistory[sceneHistory.length - 1];
      setStory(prev => prev ? { ...prev, scenes: previousScenes } : null);
      setSceneHistory(prev => prev.slice(0, -1));
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return; // Don't interfere with input fields
      }
      
      if (event.key === 'ArrowRight' && !isGenerating && !isRegenerating) {
        event.preventDefault();
        regenerateLastScene();
      } else if (event.key === 'ArrowLeft' && sceneHistory.length > 0) {
        event.preventDefault();
        goToPreviousScene();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isGenerating, isRegenerating, sceneHistory]);

  // Use dynamic choices from LLM, or fallback choices if none available
  const getAvailableChoices = () => {
    if (dynamicChoices.length > 0) {
      return dynamicChoices.map(choice => choice.text);
    }
    
    // Base fallback choices only shown when no dynamic choices are available
    const baseChoices = [
      "Continue this naturally",
      "Add dialogue between characters", 
      "Introduce a plot twist"
    ];
    
    return baseChoices;
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto"></div>
          <p className="mt-4 text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto"></div>
          <p className="mt-4 text-gray-400">Loading story...</p>
        </div>
      </div>
    );
  }

  if (!story) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-white mb-4">Story not found</h2>
          <button
            onClick={() => router.push('/dashboard')}
            className="bg-pink-600 hover:bg-pink-700 text-white px-4 py-2 rounded-lg"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const currentScene = story.scenes?.[currentChapterIndex];

  return (
    <div className="min-h-screen bg-gray-900 text-white pt-16">
      {/* Navigation Header */}
      <div className="bg-gray-800/95 backdrop-blur-md border-b border-gray-700">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setShowCharacterQuickAdd(true)}
                className="px-3 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 hover:text-purple-200 rounded-lg transition-colors text-sm font-medium border border-purple-500/30"
              >
                + Character
              </button>
              <button
                onClick={() => router.push('/characters')}
                className="px-3 py-1.5 bg-gray-700/50 hover:bg-gray-700 text-gray-300 hover:text-white rounded-lg transition-colors text-sm font-medium border border-gray-600"
              >
                📚 Characters
              </button>
            </div>
            
            <div className="flex items-center space-x-4">
              <div className="text-gray-400 text-sm">
                {story?.title}
              </div>
              <div className="flex items-center space-x-2 text-gray-500 text-sm">
                <span>Chapter 1</span>
                <span>•</span>
                <span>{story?.scenes?.length || 0} scenes</span>
                {storyCharacters.length > 0 && (
                  <>
                    <span>•</span>
                    <span className="text-purple-400">{storyCharacters.length} characters</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Story Container */}
      <div className="max-w-4xl mx-auto flex flex-col" style={{ height: 'calc(100vh - 80px)' }}>
        {/* Story Content Area */}
        <div className="flex-1 p-6 overflow-y-auto" ref={storyContentRef}>
          <div className="bg-gray-800 rounded-2xl p-8 min-h-full shadow-2xl">
            {/* Chapter Header */}
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center space-x-3">
                <span className="text-gray-400 text-sm">Chapter 1</span>
                <ArrowDownIcon className="w-4 h-4 text-gray-400" />
              </div>
              <button className="text-gray-400 hover:text-white">
                <DocumentDuplicateIcon className="w-5 h-5" />
              </button>
            </div>

            {/* Story Title */}
            <h1 className="text-2xl font-bold text-white mb-8 leading-relaxed">
              {story?.title}
            </h1>

            {/* Character Display */}
            {storyCharacters.length > 0 && (
              <div className="bg-gray-700/30 rounded-lg p-4 mb-6 border border-gray-600/50">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-300">Story Characters</h3>
                  <span className="text-xs text-gray-500">{storyCharacters.length} characters</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {storyCharacters.map((character, index) => (
                    <div key={index} className="inline-flex items-center space-x-2 bg-gray-600/50 rounded-full px-3 py-1 text-xs">
                      <span className="text-gray-300">{character.name}</span>
                      <span className="text-gray-500">•</span>
                      <span className="text-purple-300">{character.role}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* All Scenes - Scrollable */}
            <div className="prose prose-invert prose-lg max-w-none mb-8">
              {story?.scenes && story.scenes.length > 0 ? (
                <div className="space-y-8">
                  {story.scenes
                    .sort((a, b) => a.sequence_number - b.sequence_number)
                    .map((scene, index) => (
                    <div key={scene.id}>
                      {/* Scene Separator */}
                      {index > 0 && (
                        <div className="flex items-center my-8">
                          <div className="flex-1 h-px bg-gray-600"></div>
                          <div className="px-4 text-gray-500 text-sm">Scene {scene.sequence_number}</div>
                          <div className="flex-1 h-px bg-gray-600"></div>
                        </div>
                      )}
                      
                      <SceneDisplay
                        scene={scene}
                        format={userSettings?.scene_display_format || 'default'}
                        showTitle={userSettings?.show_scene_titles !== false}
                        isEditing={editingScene === scene.id}
                        editContent={editContent}
                        onStartEdit={startEditingScene}
                        onSaveEdit={(sceneId: number, content: string) => updateScene(sceneId, content)}
                        onCancelEdit={() => setEditingScene(null)}
                        onContentChange={setEditContent}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-gray-400 mb-6">Your story awaits...</p>
                  <button
                    onClick={() => generateNewScene()}
                    disabled={isGenerating}
                    className="bg-pink-600 hover:bg-pink-700 text-white px-6 py-3 rounded-lg font-medium disabled:opacity-50"
                  >
                    {isGenerating ? 'Creating...' : 'Begin Your Story'}
                  </button>
                </div>
              )}
            </div>

            {/* Director Mode Interface - Only show if story has scenes */}
            {directorMode && story?.scenes && story.scenes.length > 0 && (
              <div className="mb-8 space-y-4">
                <div className="bg-gray-700 rounded-xl border border-gray-600 p-4">
                  <h4 className="text-pink-400 text-sm font-medium mb-3">DIRECTOR MODE</h4>
                  <textarea
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder="Describe exactly what happens next in detail..."
                    rows={4}
                    className="w-full bg-gray-800 border border-gray-600 rounded-lg p-3 text-gray-200 placeholder-gray-400 resize-none focus:outline-none focus:border-pink-500"
                  />
                  <div className="flex justify-between items-center mt-3">
                    <span className="text-xs text-gray-500">Be specific about actions, dialogue, and scene details</span>
                    <button
                      onClick={() => generateNewScene()}
                      disabled={isGenerating}
                      className="bg-pink-600 hover:bg-pink-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                    >
                      {isGenerating ? 'Directing...' : 'Direct Scene'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Choice Buttons - Only show if story has scenes and not in director mode */}
            {story?.scenes && story.scenes.length > 0 && showChoices && !directorMode && (
              <div className="space-y-3 mb-8">
                {getAvailableChoices().length > 0 ? (
                  getAvailableChoices().map((choice, index) => (
                    <button
                      key={index}
                      onClick={() => generateNewScene(choice)}
                      disabled={isGenerating}
                      className="w-full text-left bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-xl p-4 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed group"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-gray-200">{choice}</span>
                        <PlayIcon className="w-5 h-5 text-pink-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="text-center text-gray-400 py-4">
                    <div className="animate-pulse">Loading story choices...</div>
                  </div>
                )}
              </div>
            )}

            {/* Continue Input - Only show in non-director mode and if story has scenes */}
            {story?.scenes && story.scenes.length > 0 && !directorMode && (
              <div className="bg-gray-700 rounded-xl border border-gray-600 p-4">
                <div className="flex items-center justify-between">
                  <input
                    type="text"
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder="Write what happens next..."
                    className="flex-1 bg-transparent text-white placeholder-gray-400 outline-none"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter' && customPrompt.trim()) {
                        generateNewScene();
                      }
                    }}
                  />
                  <button
                    onClick={() => generateNewScene()}
                    disabled={isGenerating || !customPrompt.trim()}
                    className="ml-3 bg-pink-600 hover:bg-pink-700 disabled:bg-gray-600 rounded-lg p-2 transition-colors"
                  >
                    <PlayIcon className="w-5 h-5 text-white" />
                  </button>
                </div>
              </div>
            )}

            {/* More Button */}
            <div className="flex justify-center mt-6">
              <button 
                onClick={generateMoreOptions}
                disabled={isGeneratingMoreOptions}
                className={`text-sm transition-colors disabled:opacity-50 ${
                  showMoreOptions 
                    ? 'text-purple-400 hover:text-purple-300' 
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {isGeneratingMoreOptions ? (
                  <>
                    <span className="animate-spin inline-block mr-1">⚡</span>
                    Generating more choices...
                  </>
                ) : showMoreOptions ? (
                  `Generate more (${dynamicChoices.length} choices available)`
                ) : (
                  'More choices'
                )} 
                {!isGeneratingMoreOptions && <span className="ml-1">ⓘ</span>}
              </button>
            </div>

            {/* Info Components */}
            <div className="mt-6 space-y-4">
              <TokenInfo />
              <ContextInfo />
            </div>
          </div>
        </div>

        {/* Bottom Toolbar */}
        <div className="border-t border-gray-700 bg-gray-800">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="flex items-center space-x-6">
              <ToolbarButton 
                icon={BookOpenIcon} 
                label="Lorebook" 
                active={showLorebook}
                onClick={() => setShowLorebook(!showLorebook)}
              />
              <ToolbarButton 
                icon={FilmIcon} 
                label="Director" 
                active={directorMode}
                onClick={() => setDirectorMode(!directorMode)}
              />
              <ToolbarButton icon={PhotoIcon} label="Image" />
              <ToolbarButton icon={ClockIcon} label="History" />
              <ToolbarButton icon={CheckIcon} label="Conclude" />
              <ToolbarButton icon={ArrowDownIcon} label="Export" />
            </div>
            
            {/* Keyboard Navigation Hints */}
            {story?.scenes && story.scenes.length > 0 && (
              <div className="flex items-center space-x-4 text-sm text-gray-400">
                <div className="flex items-center space-x-1">
                  <ArrowLeftIcon className="w-4 h-4" />
                  <span>Previous Scene</span>
                </div>
                <div className="flex items-center space-x-1">
                  <ArrowRightIcon className="w-4 h-4" />
                  <span>Regenerate Scene</span>
                </div>
                {isRegenerating && (
                  <div className="flex items-center space-x-1 text-pink-400">
                    <div className="w-3 h-3 border border-pink-400 border-t-transparent rounded-full animate-spin"></div>
                    <span>Regenerating...</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Lorebook Sidebar */}
      {showLorebook && (
        <div className="fixed right-0 top-0 h-full w-80 bg-gray-800 border-l border-gray-700 z-50">
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-white">LOREBOOK</h2>
              <button
                onClick={() => setShowLorebook(false)}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>
            
            <div className="flex space-x-4 mb-6">
              <button className="text-white border-b-2 border-white pb-2">Items</button>
              <button className="text-gray-400 pb-2">Characters</button>
            </div>

            <button className="w-full flex items-center justify-center space-x-2 bg-gray-700 hover:bg-gray-600 rounded-lg p-3 mb-6 transition-colors">
              <PlusIcon className="w-5 h-5" />
              <span>Create</span>
            </button>

            <div className="text-center text-gray-400 mt-12">
              <MagnifyingGlassIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No lorebook items.</p>
              <p className="text-sm">Start by creating one</p>
            </div>

            <div className="absolute bottom-6 left-6 right-6">
              <p className="text-xs text-gray-500">
                Use @ in the editor to access lorebook items.
                The last 5 selected will be remembered by the AI.
              </p>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="fixed top-4 right-4 bg-red-600 text-white px-4 py-3 rounded-lg shadow-lg z-50">
          {error}
        </div>
      )}

      {/* Character Quick Add Modal */}
      {showCharacterQuickAdd && (
        <CharacterQuickAdd
          onCharacterAdd={handleCharacterAdd}
          onClose={() => setShowCharacterQuickAdd(false)}
          existingCharacters={storyCharacters}
        />
      )}
    </div>
  );
}

function ToolbarButton({ 
  icon: Icon, 
  label, 
  active = false, 
  onClick 
}: { 
  icon: any; 
  label: string; 
  active?: boolean; 
  onClick?: () => void; 
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center space-y-1 p-2 rounded-lg transition-colors ${
        active 
          ? 'text-pink-500 bg-pink-500/10' 
          : 'text-gray-400 hover:text-white hover:bg-gray-700'
      }`}
    >
      <Icon className="w-5 h-5" />
      <span className="text-xs">{label}</span>
    </button>
  );
}

