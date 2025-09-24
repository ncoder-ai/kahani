'use client';

import { useState, useEffect, useRef } from 'react';
import { ArrowLeftIcon, ArrowRightIcon, PlayIcon } from '@heroicons/react/24/outline';
import SceneDisplay from './SceneDisplay';
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
  setSelectedChoice
}: SceneVariantDisplayProps) {
  const [variants, setVariants] = useState<SceneVariant[]>([]);
  const [currentVariantId, setCurrentVariantId] = useState<number | null>(null);
  const [isLoadingVariants, setIsLoadingVariants] = useState(false);
  const sceneContentRef = useRef<HTMLDivElement>(null);

  // Scroll to the top of this scene
  const scrollToSceneTop = () => {
    if (sceneContentRef.current) {
      sceneContentRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  };

  // Load variants for this scene
  const loadVariants = async () => {
    if (isLoadingVariants) return;
    
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

      // For modern layout, no scrolling - just smooth transition
      if (layoutMode === 'modern') {
        // Add a subtle animation class for smooth transitions
        const container = sceneContentRef.current;
        if (container) {
          container.classList.add('variant-transitioning');
          setTimeout(() => {
            container.classList.remove('variant-transitioning');
          }, 300);
        }
      } else {
        // Legacy behavior for stacked layout
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setTimeout(() => {
              scrollToSceneTop();
            }, 100);
          });
        });
      }

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
    if (scene.has_multiple_variants || isLastScene) {
      loadVariants();
    }
  }, [scene.id, scene.has_multiple_variants, isLastScene]);

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

  return (
    <div ref={sceneContentRef} className="scene-variant-container">
      <SceneDisplay
        scene={scene}
        sceneNumber={sceneNumber}
        format={userSettings?.scene_display_format || 'default'}
        showTitle={userSettings?.show_scene_titles === true}
        isEditing={isEditing}
        editContent={editContent}
        onStartEdit={onStartEdit}
        onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
        onContentChange={onContentChange}
      />
      
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
          
          {/* Regenerate Button */}
          <div className="flex justify-center">
            <button
              onClick={() => onCreateVariant(scene.id)}
              disabled={isGenerating || isStreaming || isRegenerating}
              className="flex items-center space-x-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 rounded-lg transition-colors text-sm"
              title="Regenerate current scene"
            >
              <ArrowRightIcon className="w-4 h-4" />
              <span>
                {isRegenerating ? 'Regenerating...' : 'Regenerate'}
              </span>
              {isRegenerating && (
                <div className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin"></div>
              )}
            </button>
          </div>
          
          {/* Keyboard hints - Only show if has variants */}
          {shouldShowNavigation() && (
            <div className="text-center text-xs text-gray-400 mt-3">
              Use ← → keys to navigate variants
            </div>
          )}
        </div>
      )}
      
      {/* Story continuation choices and input - Only show for last scene */}
      {isLastScene && (
        <div className="mt-6">
          {/* Choice Buttons - Only show if story has scenes and not in director mode */}
          {showChoices && !directorMode && showChoicesDuringGeneration && (
            <div className="space-y-3 mb-6">
              {getAvailableChoices().length > 0 ? (
                getAvailableChoices().map((choice, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      setSelectedChoice?.(choice);
                      setShowChoicesDuringGeneration?.(false);
                      onGenerateScene?.(choice);
                    }}
                    disabled={isGenerating || isStreaming}
                    className={`w-full text-left p-4 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed group modern-choice-button ${
                      layoutMode === 'modern' ? 'rounded-xl' : 'bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-xl'
                    } ${selectedChoice === choice ? 'ring-2 ring-pink-500 bg-pink-900/20' : ''}`}
                  >
                    <div className="flex items-center justify-between relative z-10">
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

          {/* Selected Choice Placeholder - Show when choice is selected but generation hasn't started */}
          {selectedChoice && !isGenerating && !isStreaming && !showChoicesDuringGeneration && (
            <div className="mb-6 p-4 bg-gray-800/50 rounded-xl border border-gray-600">
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-pink-500 rounded-full animate-pulse"></div>
                <span className="text-gray-300 text-sm">Selected: "{selectedChoice}"</span>
              </div>
            </div>
          )}

          {/* Continue Input - Only show in non-director mode */}
          {!directorMode && (
            <div className={`${
              layoutMode === 'modern'
                ? 'modern-input-container'
                : 'bg-gray-700 rounded-xl border border-gray-600'
            } p-4`}>
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
                />
                <button
                  onClick={() => onGenerateScene?.(customPrompt)}
                  disabled={isGenerating || isStreaming || !customPrompt.trim()}
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