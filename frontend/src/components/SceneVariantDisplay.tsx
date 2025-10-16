'use client';

import { useState, useEffect, useRef } from 'react';
import { ArrowLeftIcon, ArrowRightIcon, PlayIcon, ArrowPathIcon, PlusCircleIcon, StopIcon, SparklesIcon } from '@heroicons/react/24/outline';
import SceneDisplay from './SceneDisplay';
import { SceneAudioControlsWS } from './SceneAudioControlsWS';
import apiClient from '@/lib/api';

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

interface Scene {
  id: number;
  sequence_number: number;
  title: string;
  content: string;
  location: string;
  characters_present: string[];
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

interface SceneVariantDisplayProps {
  scene: Scene;
  sceneNumber: number;
  storyId: number;
  isLastScene: boolean;
  userSettings: any;
  isEditing: boolean;
  editContent: string;
  onStartEdit: (scene: Scene) => void;
  onSaveEdit: (sceneId: number, content: string) => void;
  onCancelEdit: () => void;
  onContentChange: (content: string) => void;
  isRegenerating: boolean;
  isGenerating: boolean;
  isStreaming: boolean;
  onCreateVariant: (sceneId: number, prompt?: string) => void;
  onVariantChanged?: () => void; // Callback when variant is switched
  onContinueScene?: (sceneId: number, prompt?: string) => void;
  onStopGeneration?: () => void;
  showChoices?: boolean;
  directorMode?: boolean;
  customPrompt?: string;
  onCustomPromptChange?: (prompt: string) => void;
  onGenerateScene?: (prompt?: string) => void;
  layoutMode?: 'stacked' | 'modern';
  onNewSceneAdded?: () => void;
  selectedChoice?: string | null;
  showChoicesDuringGeneration?: boolean;
  setShowChoicesDuringGeneration?: (show: boolean) => void;
  setSelectedChoice?: (choice: string | null) => void;
  // Scene continuation streaming props
  streamingContinuation?: string;
  isStreamingContinuation?: boolean;
  // Variant regeneration streaming props
  streamingVariantContent?: string;
  isStreamingVariant?: boolean;
  // Global flag to prevent scroll-disrupting operations
  isSceneOperationInProgress?: boolean;
}

export default function SceneVariantDisplay({
  scene,
  sceneNumber,
  storyId,
  isLastScene,
  userSettings,
  isEditing,
  editContent,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onContentChange,
  isRegenerating,
  isGenerating,
  isStreaming,
  onCreateVariant,
  onVariantChanged,
  onContinueScene,
  onStopGeneration,
  showChoices = true,
  directorMode = false,
  customPrompt = '',
  onCustomPromptChange,
  onGenerateScene,
  layoutMode = 'stacked',
  onNewSceneAdded,
  selectedChoice = null,
  showChoicesDuringGeneration = true,
  setShowChoicesDuringGeneration,
  setSelectedChoice,
  streamingContinuation = '',
  isStreamingContinuation = false,
  streamingVariantContent = '',
  isStreamingVariant = false,
  isSceneOperationInProgress = false
}: SceneVariantDisplayProps) {
  const [variants, setVariants] = useState<SceneVariant[]>([]);
  const [currentVariantId, setCurrentVariantId] = useState<number | null>(null);
  const [isLoadingVariants, setIsLoadingVariants] = useState(false);
  const [showGuidedOptions, setShowGuidedOptions] = useState(false);
  const sceneContentRef = useRef<HTMLDivElement>(null);
  const hasLoadedVariantsRef = useRef<Set<number>>(new Set());

  // Load variants for this scene
  const loadVariants = async () => {
    if (isLoadingVariants) {
      console.log(`[SceneVariantDisplay] Skipping loadVariants for scene ${scene.id} - already loading`);
      return;
    }
    
    console.log(`[SceneVariantDisplay] Starting loadVariants for scene ${scene.id}`);
    
    setIsLoadingVariants(true);
    try {
      const response = await apiClient.getSceneVariants(storyId, scene.id);
      setVariants(response.variants);
      
      // Set current variant ID if not set
      if (!currentVariantId && response.variants.length > 0) {
        const activeVariant = response.variants.find(v => v.id === scene.variant_id);
        if (activeVariant) {
          setCurrentVariantId(activeVariant.id);
        } else {
          setCurrentVariantId(response.variants[0].id);
        }
      }
      
      console.log(`[SceneVariantDisplay] Completed loadVariants for scene ${scene.id}, loaded ${response.variants.length} variants`);
      
    } catch (error) {
      console.error('Failed to load scene variants:', error);
    } finally {
      setIsLoadingVariants(false);
    }
  };

  // Switch to a specific variant with smooth transitions
  const switchToVariant = async (variantId: number) => {
    try {
      await apiClient.activateSceneVariant(storyId, scene.id, variantId);
      setCurrentVariantId(variantId);

      // Find the new variant content and update the scene in place
      const newVariant = variants.find(v => v.id === variantId);
      if (newVariant) {
        // Update scene content directly without full page reload
        // The parent will handle updating the scene content
        if (onVariantChanged) {
          onVariantChanged();
        }
      }

      // For modern layout, slide transition
      if (layoutMode === 'modern') {
        const container = sceneContentRef.current;
        if (container) {
          // Start slide-out animation
          container.classList.add('variant-transitioning');
          // After animation, remove class to slide back in
          setTimeout(() => {
            container.classList.remove('variant-transitioning');
          }, 400); // Match CSS transition duration
        }
      }
      // No scrolling for variant switching

    } catch (error) {
      console.error('Failed to switch variant:', error);
    }
  };

  // Navigation helpers
  const getCurrentVariantIndex = (): number => {
    if (!currentVariantId || variants.length === 0) return 0;
    const index = variants.findIndex(v => v.id === currentVariantId);
    return index >= 0 ? index : 0;
  };

  const canNavigateToPrevious = (): boolean => {
    return variants.length > 1 && getCurrentVariantIndex() > 0;
  };

  const canNavigateToNext = (): boolean => {
    return variants.length > 1 && getCurrentVariantIndex() < variants.length - 1;
  };

  const navigateToPrevious = async () => {
    const currentIndex = getCurrentVariantIndex();
    if (currentIndex > 0) {
      const previousVariant = variants[currentIndex - 1];
      await switchToVariant(previousVariant.id);
    }
  };

  const navigateToNext = async () => {
    const currentIndex = getCurrentVariantIndex();
    if (currentIndex < variants.length - 1) {
      const nextVariant = variants[currentIndex + 1];
      await switchToVariant(nextVariant.id);
    }
  };

  const shouldShowNavigation = (): boolean => {
    return isLastScene && (scene.has_multiple_variants || variants.length > 1);
  };

  // Get available choices for the current variant
  const getAvailableChoices = (): string[] => {
    // Find current variant
    const currentVariant = variants.find(v => v.id === currentVariantId);
    
    // Use choices from current variant if available
    if (currentVariant?.choices && currentVariant.choices.length > 0) {
      return currentVariant.choices
        .sort((a, b) => a.order - b.order)
        .map(choice => choice.text);
    }
    
    // Use scene choices if no variant-specific choices
    if (scene.choices && scene.choices.length > 0) {
      return scene.choices
        .sort((a, b) => a.order - b.order)
        .map(choice => choice.text);
    }
    
    // Fallback choices
    if (!isGenerating && !isStreaming) {
      return [
        "Continue this naturally",
        "Add dialogue between characters", 
        "Introduce a plot twist"
      ];
    }
    
    return [];
  };

    // Load variants on mount if scene has multiple variants
  useEffect(() => {
    // Don't load variants during any scene operations to prevent scroll issues
    if (isSceneOperationInProgress || isGenerating || isStreaming || isRegenerating) {
      console.log(`[SceneVariantDisplay] Skipping loadVariants for scene ${scene.id} - operation in progress`);
      return;
    }

    // Add longer delay to let everything settle completely
    const delayTimer = setTimeout(() => {
      // Only load variants if we don't already have them loaded for this scene
      const shouldLoadVariants = (scene.has_multiple_variants || isLastScene) && 
                                variants.length === 0 && 
                                !isLoadingVariants &&
                                !hasLoadedVariantsRef.current.has(scene.id);
      
      if (shouldLoadVariants) {
        console.log(`[SceneVariantDisplay] Loading variants for scene ${scene.id} (has_multiple: ${scene.has_multiple_variants}, isLast: ${isLastScene})`);
        hasLoadedVariantsRef.current.add(scene.id);
        loadVariants();
      } else if (hasLoadedVariantsRef.current.has(scene.id)) {
        console.log(`[SceneVariantDisplay] Skipping loadVariants for scene ${scene.id} - already loaded previously`);
      }
    }, 500); // Longer delay to ensure everything has settled

    return () => clearTimeout(delayTimer);
  }, [scene.id, isSceneOperationInProgress, isGenerating, isStreaming, isRegenerating]);

  // Set initial variant ID from scene
  useEffect(() => {
    if (scene.variant_id && !currentVariantId) {
      setCurrentVariantId(scene.variant_id);
    }
  }, [scene.variant_id, currentVariantId]);

  // Keyboard navigation for variants (only for last scene)
  useEffect(() => {
    if (!isLastScene) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return; // Don't interfere with input fields
      }

      if (event.key === 'ArrowRight') {
        event.preventDefault();
        if (canNavigateToNext()) {
          navigateToNext();
        }
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        if (canNavigateToPrevious()) {
          navigateToPrevious();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isLastScene, variants, currentVariantId]);

  // Handle regeneration animation
  useEffect(() => {
    if (isRegenerating && layoutMode === 'modern') {
      const container = sceneContentRef.current;
      if (container) {
        // Slide out the current scene when regeneration starts
        container.classList.remove('variant-slide-in');
        container.classList.add('variant-transitioning');
      }
    } else {
      // Slide in from right when regeneration completes or variant changes
      const container = sceneContentRef.current;
      if (container && container.classList.contains('variant-transitioning')) {
        container.classList.remove('variant-transitioning');
        // Trigger slide-in animation
        setTimeout(() => {
          container.classList.add('variant-slide-in');
          // Remove animation class after it completes
          setTimeout(() => {
            container.classList.remove('variant-slide-in');
          }, 400);
        }, 50);
      }
    }
  }, [isRegenerating, layoutMode, currentVariantId]);

  // Get the currently displayed variant's data
  const getCurrentVariant = (): SceneVariant | null => {
    if (!currentVariantId || variants.length === 0) return null;
    return variants.find(v => v.id === currentVariantId) || null;
  };

  // Create a scene object with the current variant's content
  const getDisplayScene = (): Scene => {
    // If streaming a variant regeneration, show the streaming content
    if (isStreamingVariant && streamingVariantContent) {
      return {
        ...scene,
        content: streamingVariantContent,
        title: scene.title,
        choices: []
      };
    }
    
    const currentVariant = getCurrentVariant();
    if (currentVariant) {
      // Replace scene content with current variant's content
      return {
        ...scene,
        content: currentVariant.content,
        title: currentVariant.title,
        choices: currentVariant.choices
      };
    }
    return scene;
  };

  return (
    <div ref={sceneContentRef} className="scene-variant-container">
      <div className={`relative ${isStreamingVariant ? 'streaming-variant' : ''}`}>
        {isStreamingVariant && (
          <div className="absolute top-0 right-0 bg-pink-600 text-white text-xs px-2 py-1 rounded-full animate-pulse z-10">
            Generating...
          </div>
        )}
        <SceneDisplay
          scene={getDisplayScene()}
          sceneNumber={sceneNumber}
          format={userSettings?.scene_display_format || 'default'}
          showTitle={userSettings?.show_scene_titles === true}
          isEditing={isEditing}
          editContent={editContent}
          onStartEdit={onStartEdit}
          onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
        onContentChange={onContentChange}
        streamingContinuation={streamingContinuation}
        isStreamingContinuation={isStreamingContinuation}
        isStreamingVariant={isStreamingVariant}
      />
      
      {/* Audio Controls */}
      <SceneAudioControlsWS sceneId={scene.id} className="mt-4" />
      </div>
      
      {/* Scene Management - Only show for last scene */}
      {isLastScene && (
        <div className="space-y-4 mt-6 pt-4 border-t border-gray-600/30">
          {/* Variant Navigation */}
          {shouldShowNavigation() && (
            <div className={`variant-navigation ${layoutMode === 'modern' ? 'modern-variant-nav' : ''}`}>
              <button
                onClick={() => {
                  if (variants.length <= 1) {
                    loadVariants().then(() => navigateToPrevious());
                  } else {
                    navigateToPrevious();
                  }
                }}
                disabled={!canNavigateToPrevious()}
                className="variant-nav-button"
                title="Previous variant (←)"
              >
                <ArrowLeftIcon className="w-4 h-4" />
                <span>Prev</span>
              </button>

              <div className="text-sm text-gray-300 px-3 font-medium">
                {variants.length > 0
                  ? `Variant ${getCurrentVariantIndex() + 1} of ${variants.length}`
                  : isLoadingVariants ? 'Loading...' : 'Variant 1 of ?'}
              </div>

              <button
                onClick={() => {
                  if (variants.length <= 1) {
                    loadVariants().then(() => navigateToNext());
                  } else {
                    navigateToNext();
                  }
                }}
                disabled={!canNavigateToNext()}
                className="variant-nav-button"
                title="Next variant (→)"
              >
                <span>Next</span>
                <ArrowRightIcon className="w-4 h-4" />
              </button>
            </div>
          )}
          
          {/* Action Buttons - Regenerate, Continue, Guided Regen, Stop */}
          <div className="flex justify-center items-center space-x-2">
            {/* Regenerate Button */}
            <button
              onClick={() => onCreateVariant(scene.id)}
              disabled={isGenerating || isStreaming || isRegenerating}
              className="flex items-center justify-center w-10 h-10 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 rounded-lg transition-colors"
              title="Regenerate current scene"
            >
              <ArrowPathIcon className="w-5 h-5" />
              {isRegenerating && (
                <div className="absolute w-3 h-3 border border-white border-t-transparent rounded-full animate-spin"></div>
              )}
            </button>

            {/* Continue Scene Button */}
            <button
              onClick={() => {
                if (onContinueScene) {
                  onContinueScene(scene.id, "Continue this scene with more details and development, adding to the existing content.");
                } else {
                  onCreateVariant?.(scene.id, "Continue this scene with more details and development, adding to the existing content rather than replacing it.");
                }
              }}
              disabled={isGenerating || isStreaming || isRegenerating}
              className="flex items-center justify-center w-10 h-10 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:opacity-50 rounded-lg transition-colors"
              title="Continue current scene"
            >
              <PlusCircleIcon className="w-5 h-5" />
            </button>

            {/* Guided Regeneration Button */}
            <button
              onClick={() => setShowGuidedOptions(!showGuidedOptions)}
              disabled={isGenerating || isStreaming || isRegenerating}
              className={`flex items-center justify-center w-10 h-10 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:opacity-50 rounded-lg transition-colors ${
                showGuidedOptions ? 'ring-2 ring-purple-400' : ''
              }`}
              title="Guided regeneration options"
            >
              <SparklesIcon className="w-5 h-5" />
            </button>

            {/* Stop Generation Button - Only show when generating */}
            {(isGenerating || isStreaming || isRegenerating || isStreamingContinuation) && onStopGeneration && (
              <button
                onClick={onStopGeneration}
                className="flex items-center justify-center w-10 h-10 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
                title="Stop generation"
              >
                <StopIcon className="w-5 h-5" />
              </button>
            )}
          </div>

          {/* Guided Options Dropdown */}
          {showGuidedOptions && (
            <div className={`mt-4 space-y-2 ${
              layoutMode === 'modern' 
                ? 'bg-gray-800/30 backdrop-filter backdrop-blur-sm rounded-lg p-3 border border-gray-600/30' 
                : 'bg-gray-800 rounded-lg p-3 border border-gray-600'
            }`}>
              {[
                { label: "Add More Dialogue", prompt: "Regenerate this scene with more dialogue and character interactions." },
                { label: "Include Internal Thoughts", prompt: "Regenerate this scene with more internal thoughts and character emotions." },
                { label: "Describe the Setting", prompt: "Regenerate this scene with more detailed descriptions of the environment and atmosphere." },
                { label: "Add Action/Movement", prompt: "Regenerate this scene with more action and character movements." },
                { label: "Build Tension", prompt: "Regenerate this scene with more tension and dramatic elements." },
                { label: "Show Character Development", prompt: "Regenerate this scene focusing more on character growth and development." }
              ].map((option, index) => (
                <button
                  key={index}
                  onClick={() => {
                    setShowGuidedOptions(false);
                    onCreateVariant?.(scene.id, option.prompt);
                  }}
                  disabled={isGenerating || isStreaming || isRegenerating}
                  className={`w-full text-left p-2 text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-700/50 rounded ${
                    layoutMode === 'modern' ? 'text-gray-300 hover:text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Story continuation choices and input - Only show for last scene */}
      {isLastScene && (
        <div className="mt-6">
          {/* Choice Buttons - Keep in DOM but hide with opacity to prevent layout shifts */}
          {showChoices && !directorMode && (
            <div className={`space-y-2 mb-4 transition-opacity duration-200 ${
              showChoicesDuringGeneration 
                ? 'opacity-100 pointer-events-auto' 
                : 'opacity-30 pointer-events-none'
            }`}>
              {getAvailableChoices().length > 0 ? (
                getAvailableChoices().map((choice, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      setSelectedChoice?.(choice);
                      setShowChoicesDuringGeneration?.(false);
                      onGenerateScene?.(choice);
                    }}
                    disabled={!showChoicesDuringGeneration || isGenerating || isStreaming}
                    className={`w-full text-left p-3 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed group modern-choice-button compact ${
                      layoutMode === 'modern' ? 'rounded-lg' : 'bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg'
                    } ${selectedChoice === choice ? 'ring-2 ring-pink-500 bg-pink-900/20' : ''}`}
                  >
                    <div className="flex items-center justify-between relative z-10">
                      <span className="text-gray-200 text-sm">{choice}</span>
                      <PlayIcon className="w-4 h-4 text-pink-500 opacity-0 group-hover:opacity-100 transition-opacity" />
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

          {/* Selected Choice Placeholder - Show when choice is selected but generation hasn't started */}
          {selectedChoice && !isGenerating && !isStreaming && !showChoicesDuringGeneration && (
            <div className="mb-6 p-4 bg-gray-800/50 rounded-xl border border-gray-600">
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-pink-500 rounded-full animate-pulse"></div>
                <span className="text-gray-300 text-sm">Selected: "{selectedChoice}"</span>
              </div>
            </div>
          )}

          {/* Continue Input - Keep in DOM but hide with opacity to prevent layout shifts */}
          {!directorMode && (
            <div className={`${
              layoutMode === 'modern'
                ? 'modern-input-container'
                : 'bg-gray-700 rounded-xl border border-gray-600'
            } p-4 transition-opacity duration-200 ${
              showChoicesDuringGeneration && !isGenerating && !isStreaming && !isRegenerating && !isStreamingContinuation
                ? 'opacity-100 pointer-events-auto'
                : 'opacity-30 pointer-events-none'
            }`}>
              <div className="flex items-center justify-between">
                <input
                  type="text"
                  value={customPrompt}
                  onChange={(e) => onCustomPromptChange?.(e.target.value)}
                  placeholder="Write what happens next..."
                  className="flex-1 bg-transparent text-white placeholder-gray-400 outline-none"
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && customPrompt.trim()) {
                      onGenerateScene?.(customPrompt);
                    }
                  }}
                  disabled={!showChoicesDuringGeneration || isGenerating || isStreaming || isRegenerating || isStreamingContinuation}
                />
                <button
                  onClick={() => onGenerateScene?.(customPrompt)}
                  disabled={!showChoicesDuringGeneration || isGenerating || isStreaming || !customPrompt.trim() || isRegenerating || isStreamingContinuation}
                  className={`ml-3 rounded-lg p-2 transition-colors ${
                    layoutMode === 'modern'
                      ? 'bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-700 hover:to-purple-700 disabled:from-gray-600 disabled:to-gray-600'
                      : 'bg-pink-600 hover:bg-pink-700 disabled:bg-gray-600'
                  }`}
                >
                  <PlayIcon className="w-5 h-5 text-white" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}