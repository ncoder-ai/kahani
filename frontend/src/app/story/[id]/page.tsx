'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useParams } from 'next/navigation';
import { useAuthStore, useStoryStore, useHasHydrated } from '@/store';
import apiClient from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';
import { TokenInfo } from '@/components/TokenInfo';
import { ContextInfo } from '@/components/ContextInfo';
import FormattedText from '@/components/FormattedText';
import SceneDisplay from '@/components/SceneDisplay';
import SceneVariantDisplay from '@/components/SceneVariantDisplay';
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
  
  // New variant system states - now managed by SceneVariantDisplay
  // const [selectedSceneVariants, setSelectedSceneVariants] = useState<{[sceneId: number]: SceneVariant[]}>({});
  // const [currentVariantIds, setCurrentVariantIds] = useState<{[sceneId: number]: number}>({});
  // const [showVariantSelector, setShowVariantSelector] = useState<{[sceneId: number]: boolean}>({});
  const [isDeletingScenes, setIsDeletingScenes] = useState(false);
  const [selectedScenesForDeletion, setSelectedScenesForDeletion] = useState<number[]>([]);
  const [isInDeleteMode, setIsInDeleteMode] = useState(false);
  
  // Streaming states
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingSceneNumber, setStreamingSceneNumber] = useState<number | null>(null);
  const [useStreaming, setUseStreaming] = useState(true); // Enable streaming by default
  
  // Continue scene streaming states
  const [isStreamingContinuation, setIsStreamingContinuation] = useState(false);
  const [streamingContinuation, setStreamingContinuation] = useState('');
  const [streamingContinuationSceneId, setStreamingContinuationSceneId] = useState<number | null>(null);
  
  // Scene pagination for performance
  const [displayMode, setDisplayMode] = useState<'recent' | 'all'>('recent'); // Start with recent scenes only
  const [scenesToShow, setScenesToShow] = useState(5); // Show last 5 scenes initially
  const [isLoadingEarlierScenes, setIsLoadingEarlierScenes] = useState(false);
  
  // New content indicator
  const [newContentAdded, setNewContentAdded] = useState(false);
  
  // Modern scene layout states
  const [sceneLayoutMode, setSceneLayoutMode] = useState<'stacked' | 'modern'>('modern');
  const [isNewSceneAdded, setIsNewSceneAdded] = useState(false);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [showChoicesDuringGeneration, setShowChoicesDuringGeneration] = useState(true);
  const [previousSceneCount, setPreviousSceneCount] = useState(0);
  
  const storyContentRef = useRef<HTMLDivElement>(null);
  const scenesEndRef = useRef<HTMLDivElement>(null);
  const lastSceneRef = useRef<HTMLDivElement | null>(null);  useEffect(() => {
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

  // Get scenes to display based on current mode
  const getScenesToDisplay = (): Scene[] => {
    if (!story?.scenes || story.scenes.length === 0) return [];
    
    if (displayMode === 'all') {
      return story.scenes.sort((a, b) => a.sequence_number - b.sequence_number);
    }
    
    // For 'recent' mode, show only the last N scenes
    const sortedScenes = story.scenes.sort((a, b) => a.sequence_number - b.sequence_number);
    const totalScenes = sortedScenes.length;
    const startIndex = Math.max(0, totalScenes - scenesToShow);
    return sortedScenes.slice(startIndex);
  };

  // Load all scenes (when user clicks "Load All Scenes")
  const loadAllScenes = async () => {
    setIsLoadingEarlierScenes(true);
    try {
      setDisplayMode('all');
      // Story is already loaded, just change the display mode
      // If we wanted to optimize further, we could implement server-side pagination
    } catch (err) {
      console.error('Failed to load all scenes:', err);
    } finally {
      setIsLoadingEarlierScenes(false);
    }
  };

  // Load more recent scenes
  const loadMoreRecentScenes = () => {
    setScenesToShow(prev => Math.min(prev + 10, story?.scenes?.length || 0));
  };

  // Targeted story refresh that doesn't cause scrolling
  const refreshStoryContent = async (preventScroll = true) => {
    try {
      const storyData = await apiClient.getStory(storyId);
      setStory(storyData);
      
      // If scroll is allowed and we're not preventing it, use loadStory logic
      if (!preventScroll && sceneLayoutMode === 'modern') {
        setTimeout(() => {
          if (lastSceneRef.current) {
            lastSceneRef.current.scrollIntoView({
              behavior: 'auto',
              block: 'start'
            });
          }
        }, 100);
      }
    } catch (err) {
      console.error('Failed to refresh story:', err);
    }
  };

  // Track scene count to detect new scenes
  useEffect(() => {
    if (story?.scenes) {
      setPreviousSceneCount(story.scenes.length);
    }
  }, [story?.scenes?.length]);

  // Scroll to last scene (for initial load and after generation)
  const scrollToLastScene = useCallback((behavior: 'auto' | 'smooth' = 'smooth') => {
    if (lastSceneRef.current && sceneLayoutMode === 'modern') {
      lastSceneRef.current.scrollIntoView({
        behavior,
        block: 'start'
      });
    }
  }, [sceneLayoutMode]);

  // Scroll to newly generated scene
  const scrollToNewScene = useCallback((delay: number = 200) => {
    setTimeout(() => {
      if (lastSceneRef.current) {
        lastSceneRef.current.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    }, delay);
  }, []);

  // Track if user has manually scrolled away to avoid unwanted auto-scroll
  const [userScrolledAway, setUserScrolledAway] = useState(false);

  // More refined scrolling approach to reduce jarring movement
  const smartScrollToNewContent = (force = false, showIndicator = true) => {
    console.log('📜 smartScrollToNewContent called', { force, showIndicator });
    if (scenesEndRef.current) {
      // Check if user is near the bottom of the page
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      const windowHeight = window.innerHeight;
      const documentHeight = document.documentElement.scrollHeight;
      const isNearBottom = scrollTop + windowHeight >= documentHeight - 200;
      
      console.log('📊 Scroll analysis:', {
        scrollTop,
        windowHeight,
        documentHeight,
        isNearBottom,
        userScrolledAway
      });
      
      // Show visual indicator for new content regardless of scroll
      if (showIndicator) {
        setNewContentAdded(true);
        // Auto-hide indicator after 3 seconds
        setTimeout(() => setNewContentAdded(false), 3000);
      }
      
      // Only auto-scroll if:
      // 1. User is near bottom already, OR
      // 2. We're forcing the scroll (like after generation), OR  
      // 3. User hasn't manually scrolled away
      if (force || (isNearBottom && !userScrolledAway)) {
        console.log('✅ Scrolling to new content');
        scenesEndRef.current.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest' // Less aggressive than 'end'
        });
        setUserScrolledAway(false);
      } else {
        console.log('❌ Skipping scroll - user scrolled away or not near bottom');
      }
    } else {
      console.log('❌ scenesEndRef not available');
    }
  };

  // Track when user manually scrolls
  useEffect(() => {
    let scrollTimer: NodeJS.Timeout;

    const handleScroll = () => {
      console.log('👆 User scroll detected, position:', window.pageYOffset);
      
      // Clear existing timer
      clearTimeout(scrollTimer);
      
      // Set timer to mark user as having scrolled away
      scrollTimer = setTimeout(() => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const windowHeight = window.innerHeight;
        const documentHeight = document.documentElement.scrollHeight;
        const isAtBottom = scrollTop + windowHeight >= documentHeight - 100;
        
        // If user scrolled away from bottom, mark it
        if (!isAtBottom && !isGenerating && !isStreaming) {
          console.log('🔄 User scrolled away from bottom');
          setUserScrolledAway(true);
        } else if (isAtBottom) {
          console.log('🔄 User scrolled back to bottom');
          setUserScrolledAway(false);
        }
      }, 150);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      clearTimeout(scrollTimer);
    };
  }, [isGenerating, isStreaming]);

  // Single consolidated scroll effect - much less aggressive
  useEffect(() => {
    console.log('🎬 Scroll effect triggered:', {
      isLoading,
      scenesCount: story?.scenes?.length,
      isGenerating,
      isStreaming,
      streamingContent: streamingContent.length,
      isRegenerating,
      isStreamingContinuation
    });
    
    if (!isLoading && story?.scenes && story.scenes.length > 0) {
      // Only scroll during active NEW scene generation (not regeneration or continuation)
      const isActiveNewGeneration = (isGenerating || isStreaming) && !isRegenerating && !isStreamingContinuation;
      console.log('🔍 isActiveNewGeneration:', isActiveNewGeneration);
      
      if (isActiveNewGeneration) {
        const scrollDelay = isStreaming && streamingContent ? 500 : 300;
        console.log('⏰ Setting scroll timer with delay:', scrollDelay);
        
        const scrollTimer = setTimeout(() => {
          // Triple-check states before scrolling to prevent any race conditions
          if ((isGenerating || isStreaming) && !isRegenerating && !isStreamingContinuation) {
            console.log('📜 Executing smartScrollToNewContent');
            smartScrollToNewContent();
          } else {
            console.log('❌ Scroll cancelled due to state change');
          }
        }, scrollDelay);

        return () => {
          console.log('🧹 Clearing scroll timer');
          clearTimeout(scrollTimer);
        };
      }
    }
  }, [story?.scenes?.length, isLoading, isGenerating, isStreaming, streamingContent, isRegenerating, isStreamingContinuation]);

  const loadStory = async (scrollToLastScene = true) => {
    console.log('🔍 loadStory called with scrollToLastScene:', scrollToLastScene);
    try {
      setIsLoading(true);

      // Preserve scroll position before loading if we're not supposed to scroll
      const preserveScroll = !scrollToLastScene;
      const savedScrollTop = preserveScroll ? window.pageYOffset : 0;
      console.log('📍 Current scroll position:', savedScrollTop, 'preserveScroll:', preserveScroll);

      const storyData = await apiClient.getStory(storyId);
      setStory(storyData);
      console.log('📖 Story loaded, scenes count:', storyData.scenes?.length);

      // Load choices for the current story
      await loadChoices();
      console.log('🎯 Choices loaded');

      // Restore preserved scroll position first, before any other scrolling logic
      if (preserveScroll && savedScrollTop > 0) {
        console.log('🔄 Restoring scroll position to:', savedScrollTop);
        setTimeout(() => {
          window.scrollTo(0, savedScrollTop);
          console.log('✅ Scroll restored, current position:', window.pageYOffset);
        }, 10);
      }

      // Modern layout: Position at top of last scene instead of bottom (only if requested)
      if (scrollToLastScene && sceneLayoutMode === 'modern') {
        console.log('🎯 Scrolling to last scene (modern mode)');
        setTimeout(() => {
          if (lastSceneRef.current) {
            console.log('📍 Scrolling to last scene element');
            lastSceneRef.current.scrollIntoView({
              behavior: 'auto', // Use auto for initial load to avoid jarring
              block: 'start'
            });
          }
        }, 100);
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load story');
    } finally {
      setIsLoading(false);
      console.log('🏁 loadStory completed, final scroll position:', window.pageYOffset);
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
      await loadStory(false); // Don't use initial load scrolling
      setCustomPrompt('');

      // Reset choice selection state
      setSelectedChoice(null);
      setShowChoicesDuringGeneration(true);

      // For modern layout, scroll to the new scene
      if (sceneLayoutMode === 'modern') {
        setIsNewSceneAdded(true);
        scrollToNewScene(300); // Scroll to new scene after DOM update
        setTimeout(() => setIsNewSceneAdded(false), 1000);
      } else {
        // Legacy behavior - gentle scroll
        setTimeout(() => {
          smartScrollToNewContent(true); // Force scroll after generation
        }, 400);
      }
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

          // Reset choice selection state
          setSelectedChoice(null);
          setShowChoicesDuringGeneration(true);

          // Reload the story to get the updated data
          await loadStory(false); // Don't scroll to last scene after streaming
          setCustomPrompt('');

          // For modern layout, mark new scene as added for smooth reveal
          if (sceneLayoutMode === 'modern') {
            setIsNewSceneAdded(true);
            setTimeout(() => setIsNewSceneAdded(false), 1000);
          } else {
            // Legacy behavior - gentle scroll
            setTimeout(() => {
              smartScrollToNewContent(true); // Force scroll after streaming
            }, 600);
          }
        },
        // onError
        (error: string) => {
          console.error('Streaming error:', error);
          setError(error);
          setStreamingContent('');
          setStreamingSceneNumber(null);
          setIsStreaming(false);

          // Reset choice selection state on error
          setSelectedChoice(null);
          setShowChoicesDuringGeneration(true);
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
    // Set the selected choice for UI feedback
    setSelectedChoice(prompt || null);
    setShowChoicesDuringGeneration(false);

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
      await loadStory(false); // Don't scroll to top after regeneration
      
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

  const createNewVariant = async (sceneId: number, customPrompt?: string) => {
    if (!story) return;
    
    console.log('createNewVariant called', { sceneId, customPrompt, useStreaming });
    
    try {
      setIsRegenerating(true);
      
      if (useStreaming) {
        // Streaming variant creation with animation
        setIsStreaming(true);
        setStreamingContent('');
        
        // For now, use regular API (we can add streaming later)
        const response = await apiClient.createSceneVariant(story.id, sceneId, customPrompt);
        
        // Reload story to show new variant
        await loadStory(false); // Don't scroll to top after variant creation
        
        setIsStreaming(false);
        console.log('New variant created (streaming mode):', response.variant);
      } else {
        // Non-streaming variant creation
        const response = await apiClient.createSceneVariant(story.id, sceneId, customPrompt);
        
        // Reload story to show new variant
        await loadStory(false); // Don't scroll to top after variant creation
        
        console.log('New variant created:', response.variant);
      }
      
    } catch (error) {
      console.error('Failed to create variant:', error);
      setError(error instanceof Error ? error.message : 'Failed to create variant');
      setIsStreaming(false);
    } finally {
      setIsRegenerating(false);
    }
  };

  const continueScene = async (sceneId: number, customPrompt?: string) => {
    if (!story) return;
    
    console.log('continueScene called', { sceneId, customPrompt });
    
    try {
      setIsRegenerating(true);
      
      if (useStreaming) {
        // Use streaming for continuation
        setIsStreamingContinuation(true);
        setStreamingContinuation('');
        setStreamingContinuationSceneId(sceneId);
        
        await apiClient.continueSceneStreaming(
          story.id,
          sceneId,
          customPrompt || "Continue this scene with more details and development, adding to the existing content.",
          // onChunk
          (chunk: string) => {
            setStreamingContinuation(prev => prev + chunk);
          },
          // onComplete
          async (completedSceneId: number, newContent: string) => {
            console.log('🎬 Scene continuation complete', { completedSceneId, newContent: newContent.substring(0, 50) + '...' });
            console.log('📍 Scroll position before loadStory:', window.pageYOffset);
            
            // Reload story first while streaming states are still active to prevent scroll effects
            await loadStory(false); // Don't scroll to top after continuing scene
            
            console.log('📍 Scroll position after loadStory:', window.pageYOffset);
            
            // Then clear streaming states after story is loaded
            setIsStreamingContinuation(false);
            setStreamingContinuation('');
            setStreamingContinuationSceneId(null);
            
            console.log('✅ Scene continued successfully, final scroll position:', window.pageYOffset);
          },
          // onError
          (error: string) => {
            setIsStreamingContinuation(false);
            setStreamingContinuation('');
            setStreamingContinuationSceneId(null);
            setError(error);
          }
        );
      } else {
        // Use non-streaming continuation
        const response = await apiClient.continueScene(story.id, sceneId, customPrompt);
        
        // Reload story to show updated scene
        await loadStory(false); // Don't scroll to top after continuing scene
        
        console.log('Scene continued:', response.scene);
      }
      
    } catch (error) {
      console.error('Failed to continue scene:', error);
      setError(error instanceof Error ? error.message : 'Failed to continue scene');
    } finally {
      setIsRegenerating(false);
    }
  };

  const stopGeneration = () => {
    // Stop all streaming states
    setIsStreaming(false);
    setStreamingContent('');
    setStreamingSceneNumber(null);
    setIsStreamingContinuation(false);
    setStreamingContinuation('');
    setStreamingContinuationSceneId(null);
    setIsGenerating(false);
    setIsRegenerating(false);
    
    // Reset UI states
    setSelectedChoice(null);
    setShowChoicesDuringGeneration(true);
    
    console.log('Generation stopped by user');
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
      
      if (story?.scenes.length) {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          // Right arrow: Navigate to next variant of last scene
          console.log('Right arrow: Next variant navigation handled by SceneVariantDisplay');
          // This will be handled by the SceneVariantDisplay component
        } else if (event.key === 'ArrowLeft') {
          event.preventDefault();
          // Left arrow: Navigate to previous variant of last scene
          console.log('Left arrow: Previous variant navigation handled by SceneVariantDisplay');
          // This will be handled by the SceneVariantDisplay component
        }
      }
      
      if (event.key === 'ArrowUp' && story?.scenes.length) {
        event.preventDefault();
        // Navigate up in the story (scroll up)
        if (storyContentRef.current) {
          storyContentRef.current.scrollTop -= 200;
        }
      } else if (event.key === 'ArrowDown' && story?.scenes.length) {
        event.preventDefault();
        // Navigate down in the story (scroll down)
        if (storyContentRef.current) {
          storyContentRef.current.scrollTop += 200;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isGenerating, isRegenerating, sceneHistory, story]);

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

            {/* Scenes Display with Performance Optimization */}
            <div className="prose prose-invert prose-lg max-w-none mb-8">
              {story?.scenes && story.scenes.length > 0 ? (
                <div className="space-y-8">
                  {/* Load Earlier Scenes - Thin Line Design */}
                  {displayMode === 'recent' && story.scenes.length > scenesToShow && (
                    <div className="flex items-center justify-center py-8">
                      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-gray-600 to-transparent"></div>
                      <button
                        onClick={loadMoreRecentScenes}
                        disabled={isLoadingEarlierScenes}
                        className="mx-4 text-gray-400 hover:text-gray-300 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isLoadingEarlierScenes ? 'Loading...' : 'load more messages'}
                      </button>
                      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-gray-600 to-transparent"></div>
                    </div>
                  )}

                  {getScenesToDisplay().map((scene, displayIndex) => {
                    // Calculate the actual scene number in the full story
                    const actualSceneNumber = story.scenes.findIndex(s => s.id === scene.id) + 1;
                    const isLastSceneInStory = scene.id === story.scenes[story.scenes.length - 1].id;

                    return (
                      <div
                        key={scene.id}
                        data-scene-id={scene.id}
                        ref={isLastSceneInStory ? lastSceneRef : null}
                        className={`scene-container ${sceneLayoutMode === 'modern' ? 'modern-scene' : 'stacked-scene'} ${
                          isLastSceneInStory && isNewSceneAdded ? 'new-scene' : ''
                        }`}
                      >
                        {/* Scene Separator */}
                        {displayIndex > 0 && userSettings?.show_scene_titles === true && (
                          <div className="flex items-center my-8">
                            <div className="flex-1 h-px bg-gray-600"></div>
                            <div className="px-4 text-gray-500 text-sm">Scene {actualSceneNumber}</div>
                            <div className="flex-1 h-px bg-gray-600"></div>
                          </div>
                        )}

                        {/* Delete Mode Checkbox - Show at top of scene */}
                        {isInDeleteMode && (
                          <div className="mb-4 p-3 bg-red-900/20 rounded-lg border border-red-600/50">
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

                        <SceneVariantDisplay
                          scene={scene}
                          sceneNumber={actualSceneNumber}
                          storyId={story.id}
                          isLastScene={isLastSceneInStory}
                          userSettings={userSettings}
                          isEditing={editingScene === scene.id}
                          editContent={editContent}
                          onStartEdit={startEditingScene}
                          onSaveEdit={(sceneId: number, content: string) => updateScene(sceneId, content)}
                          onCancelEdit={() => setEditingScene(null)}
                          onContentChange={setEditContent}
                          isRegenerating={isRegenerating}
                          isGenerating={isGenerating}
                          isStreaming={isStreaming}
                          onCreateVariant={createNewVariant}
                          onVariantChanged={refreshStoryContent}
                          onContinueScene={continueScene}
                          onStopGeneration={stopGeneration}
                          showChoices={showChoices}
                          directorMode={directorMode}
                          customPrompt={customPrompt}
                          onCustomPromptChange={setCustomPrompt}
                          onGenerateScene={generateScene}
                          layoutMode={sceneLayoutMode}
                          onNewSceneAdded={() => setIsNewSceneAdded(true)}
                          selectedChoice={selectedChoice}
                          showChoicesDuringGeneration={showChoicesDuringGeneration}
                          setShowChoicesDuringGeneration={setShowChoicesDuringGeneration}
                          setSelectedChoice={setSelectedChoice}
                          streamingContinuation={streamingContinuationSceneId === scene.id ? streamingContinuation : ''}
                          isStreamingContinuation={streamingContinuationSceneId === scene.id && isStreamingContinuation}
                        />
                      </div>
                    );
                  })}
                  
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
                  
                  {/* New content indicator */}
                  {newContentAdded && !isGenerating && !isStreaming && (
                    <div className="flex items-center justify-center py-4 animate-fade-in">
                      <div className="bg-gradient-to-r from-pink-600 to-purple-600 text-white px-4 py-2 rounded-full text-sm font-medium flex items-center space-x-2 shadow-lg">
                        <CheckIcon className="w-4 h-4" />
                        <span>New content added</span>
                      </div>
                    </div>
                  )}
                  
                  {/* End of scenes marker for scrolling */}
                  <div ref={scenesEndRef} className="h-1"></div>
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-gray-400 mb-6">Your story awaits...</p>
                  <button
                    onClick={() => useStreaming ? generateNewSceneStreaming() : generateNewScene()}
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

            {/* Note: Continue Input is now handled by SceneVariantDisplay component for last scene */}

            {/* More Button - Keep in DOM but hide with opacity to prevent layout shifts */}
            <div className={`flex justify-center mt-6 transition-opacity duration-200 ${
              !isGenerating && !isStreaming && !isRegenerating && !isStreamingContinuation
                ? 'opacity-100 pointer-events-auto'
                : 'opacity-0 pointer-events-none'
            }`}>
              <button 
                onClick={generateMoreOptions}
                disabled={isGeneratingMoreOptions || isGenerating || isStreaming || isRegenerating || isStreamingContinuation}
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
        <div className="fixed top-4 right-4 bg-red-600 text-white px-4 py-3 rounded-lg shadow-lg z-50 max-w-md">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="font-medium mb-1">Error</div>
              <div className="text-sm">{error}</div>
              {error.includes('No models loaded') && (
                <div className="mt-2 text-xs bg-red-700 rounded p-2">
                  <strong>Solution:</strong> Load a model in LM Studio's developer page or use the `lms load` command.
                </div>
              )}
              {error.includes('Failed to connect') && (
                <div className="mt-2 text-xs bg-red-700 rounded p-2">
                  <strong>Solution:</strong> Make sure LM Studio is running on localhost:1234
                </div>
              )}
            </div>
            <button
              onClick={() => setError('')}
              className="ml-2 text-white hover:text-gray-200 flex-shrink-0"
            >
              ✕
            </button>
          </div>
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

