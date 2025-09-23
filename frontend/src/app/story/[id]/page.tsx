'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useParams } from 'next/navigation';
import { useAuthStore, useStoryStore, useHasHydrated } from '@/store';
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
  // New variant properties
  variant_id?: number;
  variant_number?: number;
  is_original?: boolean;
  has_multiple_variants?: boolean;
  choices?: Array<{
    id: number;
    text: string;
    description?: string;
    order: number;
  }>;
}

interface SceneVariant {
  id: number;
  variant_number: number;
  content: string;
  title: string;
  is_original: boolean;
  generation_method: string;
  user_rating?: number;
  is_favorite: boolean;
  created_at: string;
  choices: Array<{
    id: number;
    text: string;
    description?: string;
    order: number;
  }>;
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
  flow_info?: {
    total_scenes: number;
    has_variants: boolean;
  };
}

export default function StoryPage() {
  const router = useRouter();
  const params = useParams();
  const storyId = parseInt(params.id as string);
  
  const { user } = useAuthStore();
  const hasHydrated = useHasHydrated();
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
  
  // New variant system states
  const [selectedSceneVariants, setSelectedSceneVariants] = useState<{[sceneId: number]: SceneVariant[]}>({});
  const [currentVariantIds, setCurrentVariantIds] = useState<{[sceneId: number]: number}>({});
  const [showVariantSelector, setShowVariantSelector] = useState<{[sceneId: number]: boolean}>({});
  const [isDeletingScenes, setIsDeletingScenes] = useState(false);
  const [selectedScenesForDeletion, setSelectedScenesForDeletion] = useState<number[]>([]);
  const [isInDeleteMode, setIsInDeleteMode] = useState(false);
  
  // Streaming states
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingSceneNumber, setStreamingSceneNumber] = useState<number | null>(null);
  const [useStreaming, setUseStreaming] = useState(true); // Enable streaming by default
  const storyContentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Wait for auth store to hydrate before checking authentication
    if (!hasHydrated) {
      return;
    }
    
    if (!user) {
      router.push('/login');
      return;
    }
    
    loadStory();
    loadUserSettings();
  }, [user, hasHydrated, storyId, router]);

  const loadUserSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings.settings);
    } catch (err) {
      console.error('Failed to load user settings:', err);
    }
  };

  const scrollToBottom = () => {
    if (storyContentRef.current) {
      const element = storyContentRef.current;
      // Use requestAnimationFrame for better timing and smooth scrolling
      requestAnimationFrame(() => {
        element.scrollTo({
          top: element.scrollHeight,
          behavior: 'smooth'
        });
      });
    }
  };

  // Auto-scroll to bottom when new scenes are added
  useEffect(() => {
    if (storyContentRef.current && story?.scenes && story.scenes.length > 0) {
      // Use setTimeout to ensure DOM is updated after scene render
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    }
  }, [story?.scenes?.length]);

  // Additional auto-scroll when story content changes
  useEffect(() => {
    if (storyContentRef.current && story) {
      // Delayed scroll to ensure content is fully rendered
      setTimeout(() => {
        scrollToBottom();
      }, 200);
    }
  }, [story?.scenes]);

  // Auto-scroll during streaming with more responsive timing
  useEffect(() => {
    if (storyContentRef.current && isStreaming) {
      // Scroll when streaming starts
      if (streamingContent === '') {
        setTimeout(() => {
          scrollToBottom();
        }, 100);
      }
      // Continue scrolling as content updates
      if (streamingContent) {
        setTimeout(() => {
          scrollToBottom();
        }, 50);
      }
    }
  }, [streamingContent, isStreaming]);

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
    
    // Don't clear choices immediately - hide more options
    setShowMoreOptions(false);
    
    try {
      const response = await apiClient.generateScene(story.id, prompt || customPrompt);
      console.log('generateNewScene response', response);

      // Reload the story to get the new scene and its choices
      await loadStory();
      setCustomPrompt('');
      
      // Ensure we scroll to bottom after scene is loaded
      setTimeout(() => {
        scrollToBottom();
      }, 300);
    } catch (err) {
      console.error('generateNewScene error', err);
      setError(err instanceof Error ? err.message : 'Failed to generate scene');
    } finally {
      setIsGenerating(false);
    }
  };

  const generateNewSceneStreaming = async (prompt?: string) => {
    if (!story) return;
    console.log('generateNewSceneStreaming called', { storyId: story.id, prompt });
    setError('');
    setIsStreaming(true);
    setStreamingContent('');
    
    // Calculate the next scene number
    const nextSceneNumber = (story.scenes?.length || 0) + 1;
    setStreamingSceneNumber(nextSceneNumber);
    
    // Don't clear choices immediately - hide more options
    setShowMoreOptions(false);
    
    // Scroll to bottom when starting generation
    setTimeout(() => {
      scrollToBottom();
    }, 100);
    
    try {
      await apiClient.generateSceneStreaming(
        story.id,
        prompt || customPrompt,
        // onChunk
        (chunk: string) => {
          setStreamingContent(prev => prev + chunk);
        },
        // onComplete
        async (sceneId: number, choices: any[]) => {
          console.log('Scene generation complete', { sceneId, choices });
          setStreamingContent('');
          setStreamingSceneNumber(null);
          setIsStreaming(false);
          
          // Reload the story to get the updated data
          await loadStory();
          setCustomPrompt('');
          
          // Ensure we scroll to bottom after scene is loaded
          setTimeout(() => {
            scrollToBottom();
          }, 300);
        },
        // onError
        (error: string) => {
          console.error('Streaming error:', error);
          setError(error);
          setStreamingContent('');
          setStreamingSceneNumber(null);
          setIsStreaming(false);
        }
      );
    } catch (err) {
      console.error('generateNewSceneStreaming error', err);
      setError(err instanceof Error ? err.message : 'Failed to generate scene');
      setStreamingContent('');
      setStreamingSceneNumber(null);
      setIsStreaming(false);
    }
  };

  // Wrapper function to choose between streaming and regular generation
  const generateScene = async (prompt?: string) => {
    if (useStreaming) {
      return generateNewSceneStreaming(prompt);
    } else {
      return generateNewScene(prompt);
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
      const response = await apiClient.regenerateLastScene(story.id);
      
      // Reload the story to get the updated flow
      await loadStory();
      
      // Show success message or handle the new variant
      console.log('Scene regenerated:', response.variant);
      
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

  const goToNextScene = () => {
    // Navigate forward in linear scene progression
    if (story && story.scenes.length > 0) {
      // For now, this could scroll to the next scene or enable "continue story" functionality
      console.log('Go to next scene - to be implemented');
    }
  };

  const loadSceneVariants = async (sceneId: number) => {
    if (!story) return;
    
    try {
      const response = await apiClient.getSceneVariants(story.id, sceneId);
      setSelectedSceneVariants(prev => ({
        ...prev,
        [sceneId]: response.variants
      }));
    } catch (error) {
      console.error('Failed to load scene variants:', error);
    }
  };

  const switchToVariant = async (sceneId: number, variantId: number) => {
    if (!story) return;
    
    try {
      await apiClient.activateSceneVariant(story.id, sceneId, variantId);
      
      // Update the current variant ID
      setCurrentVariantIds(prev => ({
        ...prev,
        [sceneId]: variantId
      }));
      
      // Reload the story to show the new variant
      await loadStory();
      
    } catch (error) {
      console.error('Failed to switch variant:', error);
      setError(error instanceof Error ? error.message : 'Failed to switch variant');
    }
  };

  const createNewVariant = async (sceneId: number, customPrompt?: string) => {
    if (!story) return;
    
    try {
      setIsRegenerating(true);
      const response = await apiClient.createSceneVariant(story.id, sceneId, customPrompt);
      
      // Reload variants for this scene
      await loadSceneVariants(sceneId);
      
      // Reload the story (the new variant should be automatically active)
      await loadStory();
      
      console.log('New variant created:', response.variant);
      
    } catch (error) {
      console.error('Failed to create variant:', error);
      setError(error instanceof Error ? error.message : 'Failed to create variant');
    } finally {
      setIsRegenerating(false);
    }
  };

  const toggleDeleteMode = () => {
    setIsInDeleteMode(!isInDeleteMode);
    setSelectedScenesForDeletion([]);
  };

  const toggleSceneForDeletion = (sequenceNumber: number) => {
    if (selectedScenesForDeletion.includes(sequenceNumber)) {
      setSelectedScenesForDeletion(prev => prev.filter(seq => seq !== sequenceNumber));
    } else {
      setSelectedScenesForDeletion(prev => [...prev, sequenceNumber]);
    }
  };

  const deleteScenesFromSelected = async () => {
    if (!story || selectedScenesForDeletion.length === 0) return;
    
    // Find the earliest selected sequence number
    const earliestSequence = Math.min(...selectedScenesForDeletion);
    
    try {
      setIsDeletingScenes(true);
      await apiClient.deleteScenesFromSequence(story.id, earliestSequence);
      
      // Exit delete mode
      setIsInDeleteMode(false);
      setSelectedScenesForDeletion([]);
      
      // Reload the story
      await loadStory();
      
    } catch (error) {
      console.error('Failed to delete scenes:', error);
      setError(error instanceof Error ? error.message : 'Failed to delete scenes');
    } finally {
      setIsDeletingScenes(false);
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return; // Don't interfere with input fields
      }
      
      if (event.key === 'ArrowRight' && !isGenerating && !isRegenerating && story?.scenes.length) {
        event.preventDefault();
        const lastScene = story.scenes[story.scenes.length - 1];
        createNewVariant(lastScene.id);
      } else if (event.key === 'ArrowLeft' && sceneHistory.length > 0) {
        event.preventDefault();
        goToPreviousScene();
      } else if (event.key === 'ArrowUp' && story?.scenes.length) {
        event.preventDefault();
        // Navigate to previous scene (scroll or focus)
        // For now, just scroll up
        if (storyContentRef.current) {
          storyContentRef.current.scrollTop -= 200;
        }
      } else if (event.key === 'ArrowDown' && story?.scenes.length) {
        event.preventDefault();
        // Navigate to next scene (scroll or continue story)
        goToNextScene();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isGenerating, isRegenerating, sceneHistory, story]);

  // Use dynamic choices from LLM, or fallback choices if none available
  const getAvailableChoices = () => {
    if (dynamicChoices.length > 0) {
      return dynamicChoices.map(choice => choice.text);
    }
    
    // Only show base fallback choices when:
    // 1. No dynamic choices are available AND
    // 2. Not currently generating a new scene
    if (!isGenerating) {
      const baseChoices = [
        "Continue this naturally",
        "Add dialogue between characters", 
        "Introduce a plot twist"
      ];
      
      return baseChoices;
    }
    
    // Return empty array when generating to hide choices
    return [];
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

  if (!hasHydrated) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Loading...</p>
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
              
              {/* Streaming Toggle */}
              <button
                onClick={() => setUseStreaming(!useStreaming)}
                className={`px-3 py-1.5 rounded-lg transition-colors text-sm font-medium border ${
                  useStreaming 
                    ? 'bg-green-600/20 hover:bg-green-600/30 text-green-300 hover:text-green-200 border-green-500/30' 
                    : 'bg-gray-700/50 hover:bg-gray-700 text-gray-300 hover:text-white border-gray-600'
                }`}
              >
                {useStreaming ? '⚡ Streaming' : '📄 Standard'}
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
                      {index > 0 && userSettings?.show_scene_titles === true && (
                        <div className="flex items-center my-8">
                          <div className="flex-1 h-px bg-gray-600"></div>
                          <div className="px-4 text-gray-500 text-sm">Scene {index + 1}</div>
                          <div className="flex-1 h-px bg-gray-600"></div>
                        </div>
                      )}
                      
                      <SceneDisplay
                        scene={scene}
                        sceneNumber={index + 1}
                        format={userSettings?.scene_display_format || 'default'}
                        showTitle={userSettings?.show_scene_titles === true}
                        isEditing={editingScene === scene.id}
                        editContent={editContent}
                        onStartEdit={startEditingScene}
                        onSaveEdit={(sceneId: number, content: string) => updateScene(sceneId, content)}
                        onCancelEdit={() => setEditingScene(null)}
                        onContentChange={setEditContent}
                      />
                      
                      {/* Scene Management Buttons - Show only for the last scene */}
                      {index === story.scenes.length - 1 && (
                        <div className="flex items-center justify-center space-x-4 mt-6 pt-4 border-t border-gray-600/30">
                          <button
                            onClick={goToPreviousScene}
                            disabled={sceneHistory.length === 0}
                            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:opacity-50 rounded-lg transition-colors text-sm"
                            title="Go to previous scene version (←)"
                          >
                            <ArrowLeftIcon className="w-4 h-4" />
                            <span>Previous Scene</span>
                          </button>
                          
                          <button
                            onClick={() => createNewVariant(scene.id)}
                            disabled={isGenerating || isStreaming || isRegenerating}
                            className="flex items-center space-x-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 rounded-lg transition-colors text-sm"
                            title="Regenerate current scene (→)"
                          >
                            <ArrowRightIcon className="w-4 h-4" />
                            <span>
                              {isRegenerating ? 'Regenerating...' : 'Regenerate Scene'}
                            </span>
                            {isRegenerating && (
                              <div className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin"></div>
                            )}
                          </button>

                          <button
                            onClick={goToNextScene}
                            disabled={isGenerating || isStreaming}
                            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:opacity-50 rounded-lg transition-colors text-sm"
                            title="Continue to next scene"
                          >
                            <span>Next Scene</span>
                            <ArrowRightIcon className="w-4 h-4" />
                          </button>
                        </div>
                      )}

                      {/* Variant Selector for scenes with multiple variants */}
                      {scene.has_multiple_variants && (
                        <div className="mt-4 p-3 bg-gray-700/30 rounded-lg border border-gray-600/50">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm text-gray-300">
                              Scene has {selectedSceneVariants[scene.id]?.length || 'multiple'} variants
                            </span>
                            <button
                              onClick={() => loadSceneVariants(scene.id)}
                              className="text-xs text-pink-400 hover:text-pink-300"
                            >
                              View Variants
                            </button>
                          </div>
                          
                          {selectedSceneVariants[scene.id] && (
                            <div className="flex flex-wrap gap-2">
                              {selectedSceneVariants[scene.id].map((variant, variantIndex) => (
                                <button
                                  key={variant.id}
                                  onClick={() => switchToVariant(scene.id, variant.id)}
                                  className={`px-3 py-1 rounded-full text-xs transition-colors ${
                                    variant.id === scene.variant_id
                                      ? 'bg-pink-600 text-white'
                                      : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                                  }`}
                                >
                                  {variant.is_original ? 'Original' : `V${variant.variant_number}`}
                                  {variant.is_favorite && ' ⭐'}
                                </button>
                              ))}
                              <button
                                onClick={() => createNewVariant(scene.id)}
                                className="px-3 py-1 rounded-full text-xs bg-pink-600/20 text-pink-400 hover:bg-pink-600/30 transition-colors"
                              >
                                + New
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Delete Mode Checkbox */}
                      {isInDeleteMode && (
                        <div className="mt-4 p-3 bg-red-900/20 rounded-lg border border-red-600/50">
                          <label className="flex items-center space-x-2 text-sm text-red-300">
                            <input
                              type="checkbox"
                              checked={selectedScenesForDeletion.includes(scene.sequence_number)}
                              onChange={() => toggleSceneForDeletion(scene.sequence_number)}
                              className="w-4 h-4 text-red-600 bg-gray-700 border-gray-600 rounded focus:ring-red-500"
                            />
                            <span>Delete from here onward</span>
                          </label>
                        </div>
                      )}
                    </div>
                  ))}
                  
                  {/* Streaming Content Display */}
                  {isStreaming && streamingContent && (
                    <div className="streaming-scene">
                      {/* Scene Separator for streaming */}
                      {story.scenes.length > 0 && userSettings?.show_scene_titles === true && (
                        <div className="flex items-center my-8">
                          <div className="flex-1 h-px bg-gray-600"></div>
                          <div className="px-4 text-gray-500 text-sm">Scene {streamingSceneNumber}</div>
                          <div className="flex-1 h-px bg-gray-600"></div>
                        </div>
                      )}
                      
                      <div className="relative">
                        <div className="prose prose-invert prose-lg max-w-none">
                          <div className="streaming-content-wrapper">
                            <FormattedText 
                              content={streamingContent} 
                              className="streaming-content inline"
                            />
                            <span className="inline-block w-2 h-5 bg-pink-500 animate-pulse ml-1 align-middle">|</span>
                          </div>
                        </div>
                        
                        {/* Streaming indicator */}
                        <div className="absolute top-0 right-0 bg-pink-600 text-white text-xs px-2 py-1 rounded-full animate-pulse">
                          Generating...
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-gray-400 mb-6">Your story awaits...</p>
                  <button
                    onClick={() => generateScene()}
                    disabled={isGenerating || isStreaming}
                    className="bg-pink-600 hover:bg-pink-700 text-white px-6 py-3 rounded-lg font-medium disabled:opacity-50"
                  >
                    {isGenerating || isStreaming ? 'Creating...' : 'Begin Your Story'}
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
                      onClick={() => generateScene()}
                      disabled={isGenerating || isStreaming}
                      className="bg-pink-600 hover:bg-pink-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                    >
                      {isGenerating || isStreaming ? 'Directing...' : 'Direct Scene'}
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
                      onClick={() => generateScene(choice)}
                      disabled={isGenerating || isStreaming}
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
                        generateScene();
                      }
                    }}
                  />
                  <button
                    onClick={() => generateScene()}
                    disabled={isGenerating || isStreaming || !customPrompt.trim()}
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
              <ToolbarButton 
                icon={CheckIcon} 
                label={isInDeleteMode ? "Delete Selected" : "Delete Mode"}
                active={isInDeleteMode}
                onClick={isInDeleteMode ? deleteScenesFromSelected : toggleDeleteMode}
              />
              <ToolbarButton icon={ArrowDownIcon} label="Export" />
            </div>
            
            {/* Keyboard Navigation Hints */}
            {story?.scenes && story.scenes.length > 0 && (
              <div className="flex items-center space-x-4 text-sm text-gray-400">
                <div className="flex items-center space-x-1">
                  <span>← Previous | → Regenerate | ↑ Scroll Up | ↓ Next Scene</span>
                </div>
                {isRegenerating && (
                  <div className="flex items-center space-x-1 text-pink-400">
                    <div className="w-3 h-3 border border-pink-400 border-t-transparent rounded-full animate-spin"></div>
                    <span>Regenerating...</span>
                  </div>
                )}
                {isInDeleteMode && (
                  <div className="flex items-center space-x-1 text-red-400">
                    <span>Delete Mode: Select scenes to remove</span>
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

