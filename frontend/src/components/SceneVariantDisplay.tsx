'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { PlayIcon, ArrowPathIcon, PlusCircleIcon, StopIcon, SparklesIcon, TrashIcon, ClipboardIcon, XMarkIcon, FlagIcon, PencilIcon, CheckIcon } from '@heroicons/react/24/outline';
import { GitFork, Volume2, Image } from 'lucide-react';
import SceneDisplay from './SceneDisplay';
import SceneImageGenerator from './SceneImageGenerator';
import { SceneTTSButton } from './SceneTTSButton';
import MicrophoneButton from './MicrophoneButton';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
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
  user_edited?: boolean;
  created_at: string;
  choices: Array<{
    id: number;
    text: string;
    description?: string;
    order: number;
    is_user_created?: boolean;
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
    is_user_created?: boolean;
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
  onSaveEdit: (sceneId: number, content: string, variantId?: number) => void | Promise<void>;
  onCancelEdit: () => void;
  onContentChange: (content: string) => void;
  isRegenerating: boolean;
  isGenerating: boolean;
  isStreaming: boolean;
  onCreateVariant: (sceneId: number, prompt?: string, variantId?: number) => void;
  onVariantChanged?: (sceneId: number, newVariant?: { id: number; content: string }) => void; // Callback when variant is switched
  onContinueScene?: (sceneId: number, prompt?: string) => void;
  onStopGeneration?: () => void;
  showChoices?: boolean;
  directorMode?: boolean;
  customPrompt?: string;
  onCustomPromptChange?: (prompt: string) => void;
  onGenerateScene?: (prompt?: string, isConcluding?: boolean) => void;
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
  // Additional choices from "generate more choices"
  dynamicChoices?: Array<{text: string, order: number}>;
  showMoreOptions?: boolean;
  // Delete mode props
  isInDeleteMode?: boolean;
  isSceneSelectedForDeletion?: boolean;
  onToggleSceneDeletion?: (sequenceNumber: number) => void;
  onActivateDeleteMode?: (sequenceNumber: number) => void;
  onDeactivateDeleteMode?: () => void;
  // Copy functionality
  onCopySceneText?: (content: string) => void;
  // Branch creation
  onCreateBranch?: (sceneSequence: number) => void;
  // Choices generation loading state
  isGeneratingChoices?: boolean;
  // Variant reload trigger from parent
  variantReloadTrigger?: number;
  // Image display toggle
  showImages?: boolean;
  // Contradiction check props
  contradictions?: Array<{
    id: number; type: string; character_name: string | null;
    previous_value: string | null; current_value: string | null;
    severity: string; scene_sequence: number;
  }>;
  checkingContradictions?: boolean;
  onContradictionResolved?: (sequenceNumber: number) => void;
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
  isSceneOperationInProgress = false,
  dynamicChoices = [],
  showMoreOptions = false,
  isInDeleteMode = false,
  isSceneSelectedForDeletion = false,
  onToggleSceneDeletion,
  onActivateDeleteMode,
  onDeactivateDeleteMode,
  onCopySceneText,
  onCreateBranch,
  isGeneratingChoices = false,
  variantReloadTrigger,
  showImages = true,
  contradictions,
  checkingContradictions = false,
  onContradictionResolved
}: SceneVariantDisplayProps) {
  const [variants, setVariants] = useState<SceneVariant[]>([]);
  const [currentVariantId, setCurrentVariantId] = useState<number | null>(null);
  const [isLoadingVariants, setIsLoadingVariants] = useState(false);
  const [isRegeneratingChoices, setIsRegeneratingChoices] = useState(false);
  const [choicesVersion, setChoicesVersion] = useState(0);
  const [showGuidedOptions, setShowGuidedOptions] = useState(false);
  const [customGuideText, setCustomGuideText] = useState('');
  // Editable choice state
  const [editingChoiceId, setEditingChoiceId] = useState<number | null>(null);
  const [editingChoiceText, setEditingChoiceText] = useState<string>('');
  const [isSavingChoice, setIsSavingChoice] = useState(false);
  const sceneContentRef = useRef<HTMLDivElement>(null);
  const hasLoadedVariantsRef = useRef<Set<number>>(new Set());
  const lastTriggerRef = useRef<number>(0);
  const [copySuccess, setCopySuccess] = useState(false);
  const [showFloatingMenu, setShowFloatingMenu] = useState(false);
  const [isClient, setIsClient] = useState(false);
  const [showImageGenerator, setShowImageGenerator] = useState(false);
  const [isMenuVisible, setIsMenuVisible] = useState(true);
  // Contradiction resolution state
  const [resolvingContradictionId, setResolvingContradictionId] = useState<number | null>(null);
  const [resolutionNote, setResolutionNote] = useState('');
  const [isResolvingContradiction, setIsResolvingContradiction] = useState(false);
  const menuTimerRef = useRef<NodeJS.Timeout | null>(null);
  const choiceInputRef = useRef<HTMLInputElement>(null);
  const customPromptInputRef = useRef<HTMLInputElement>(null);
  const customPromptFocusHandledRef = useRef(false);
  
  // Handle resolving a contradiction
  const handleResolveContradiction = async (contradictionId: number) => {
    setIsResolvingContradiction(true);
    try {
      await apiClient.resolveContradiction(contradictionId, resolutionNote);
      setResolvingContradictionId(null);
      setResolutionNote('');
      // Notify parent to remove this contradiction from state
      if (onContradictionResolved) {
        onContradictionResolved(scene.sequence_number);
      }
    } catch (err) {
      console.error('Failed to resolve contradiction:', err);
    } finally {
      setIsResolvingContradiction(false);
    }
  };

  // Global TTS context for play/stop functionality
  const { playScene, stop, currentSceneId, isPlaying: isTTSPlaying } = useGlobalTTS();
  
  // Only render client-side only elements after hydration
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Auto-hide menu timer functions
  const resetMenuTimer = useCallback(() => {
    if (menuTimerRef.current) {
      clearTimeout(menuTimerRef.current);
    }
    setIsMenuVisible(true);
    menuTimerRef.current = setTimeout(() => {
      setIsMenuVisible(false);
    }, 3000); // 3 seconds
  }, []);

  const hideMenu = useCallback(() => {
    setIsMenuVisible(false);
  }, []);

  // Initialize timer on mount and clean up on unmount
  useEffect(() => {
    if (isClient) {
      resetMenuTimer();
    }
    return () => {
      if (menuTimerRef.current) {
        clearTimeout(menuTimerRef.current);
      }
    };
  }, [isClient, resetMenuTimer]);

  // Keep menu visible when floating menu is open
  useEffect(() => {
    if (showFloatingMenu) {
      // Cancel any pending hide timer
      if (menuTimerRef.current) {
        clearTimeout(menuTimerRef.current);
      }
      setIsMenuVisible(true);
    } else {
      // Start timer when menu closes
      resetMenuTimer();
    }
  }, [showFloatingMenu, resetMenuTimer]);

  // Load variants for this scene
  const loadVariants = async (forceSetVariantId?: number) => {
    if (isLoadingVariants) {
      console.log('[VARIANT RELOAD] Already loading, skipping');
      return;
    }
    
    console.log('[VARIANT RELOAD] Starting variant load for scene', scene.id);
    setIsLoadingVariants(true);
    try {
      const response = await apiClient.getSceneVariants(storyId, scene.id);
      console.log('[VARIANT RELOAD] Loaded', response.variants.length, 'variants');
      
      // Log choices for current variant
      const currentVar = response.variants.find(v => v.id === currentVariantId);
      if (currentVar) {
        console.log('[VARIANT RELOAD] Current variant has', currentVar.choices?.length || 0, 'choices');
      }
      
      setVariants(response.variants);
      setChoicesVersion(prev => prev + 1); // Force re-render
      
      // Set current variant ID - prioritize scene.variant_id or forced variant ID
      const targetVariantId = forceSetVariantId || scene.variant_id;
      if (targetVariantId && response.variants.length > 0) {
        const activeVariant = response.variants.find(v => v.id === targetVariantId);
        if (activeVariant) {
          setCurrentVariantId(activeVariant.id);
        } else if (!currentVariantId) {
          // Fallback to first variant only if we don't have a current variant
          setCurrentVariantId(response.variants[0].id);
        }
      } else if (!currentVariantId && response.variants.length > 0) {
        // Set to first variant if no variant_id specified and no current variant
        setCurrentVariantId(response.variants[0].id);
      }
      
      
    } catch (error) {
      console.error('[VARIANT RELOAD] Failed to load variants:', error);
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
      if (newVariant && onVariantChanged) {
        // Update parent's local state with the new variant content (no full refresh)
        onVariantChanged(scene.id, { id: variantId, content: newVariant.content });
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
  const getAvailableChoices = useCallback((): string[] => {
    // Hide choices when streaming a variant - old variant choices should not be shown
    if (isStreamingVariant) {
      return [];
    }
    
    const baseChoices: string[] = [];
    
    // Find current variant
    const currentVariant = variants.find(v => v.id === currentVariantId);
    
    // Use choices from current variant if available
    if (currentVariant?.choices && currentVariant.choices.length > 0) {
      baseChoices.push(...currentVariant.choices
        .sort((a, b) => a.order - b.order)
        .map(choice => choice.text));
    }
    // Use scene choices if no variant-specific choices
    else if (scene.choices && scene.choices.length > 0) {
      baseChoices.push(...scene.choices
        .sort((a, b) => a.order - b.order)
        .map(choice => choice.text));
    }
    // No fallback choices - return empty array if no choices available
    
    // All choices now come from variant data (including "more choices" stored in DB)
    return baseChoices;
  }, [variants, currentVariantId, isStreamingVariant, scene.choices, isGenerating, isStreaming, choicesVersion]);

  // Get available choices with full data (including IDs) for editing
  const getAvailableChoicesWithData = useCallback((): Array<{id: number; text: string; order: number; is_user_created?: boolean}> => {
    // Hide choices when streaming a variant
    if (isStreamingVariant) {
      return [];
    }
    
    // Find current variant
    const currentVariant = variants.find(v => v.id === currentVariantId);
    
    // Use choices from current variant if available
    if (currentVariant?.choices && currentVariant.choices.length > 0) {
      return [...currentVariant.choices].sort((a, b) => a.order - b.order);
    }
    // Use scene choices if no variant-specific choices
    else if (scene.choices && scene.choices.length > 0) {
      return [...scene.choices].sort((a, b) => a.order - b.order);
    }
    
    return [];
  }, [variants, currentVariantId, isStreamingVariant, scene.choices, choicesVersion]);

  // Handle starting to edit a choice
  const handleStartEditChoice = useCallback((choice: {id: number; text: string}) => {
    setEditingChoiceId(choice.id);
    setEditingChoiceText(choice.text);
  }, []);

  // Focus choice input when editing starts, without scrolling
  useEffect(() => {
    if (editingChoiceId && choiceInputRef.current) {
      choiceInputRef.current.focus({ preventScroll: true });
    }
  }, [editingChoiceId]);

  // Handle saving an edited choice
  const handleSaveEditChoice = useCallback(async () => {
    if (!editingChoiceId || !editingChoiceText.trim() || isSavingChoice) return;
    
    setIsSavingChoice(true);
    try {
      await apiClient.updateChoice(storyId, editingChoiceId, editingChoiceText.trim());
      
      // Update local state optimistically
      setVariants(prevVariants => prevVariants.map(variant => ({
        ...variant,
        choices: variant.choices.map(choice => 
          choice.id === editingChoiceId 
            ? { ...choice, text: editingChoiceText.trim(), is_user_created: true }
            : choice
        )
      })));
      setChoicesVersion(prev => prev + 1);
      setEditingChoiceId(null);
      setEditingChoiceText('');
    } catch (error) {
      console.error('Failed to update choice:', error);
    } finally {
      setIsSavingChoice(false);
    }
  }, [editingChoiceId, editingChoiceText, isSavingChoice, storyId]);

  // Handle canceling choice edit
  const handleCancelEditChoice = useCallback(() => {
    setEditingChoiceId(null);
    setEditingChoiceText('');
  }, []);

  // Get manual choice from current variant
  const getManualChoice = useCallback((): string => {
    // Find current variant
    const currentVariant = variants.find(v => v.id === currentVariantId);
    
    // Find the user-created choice
    if (currentVariant?.choices) {
      const manualChoice = currentVariant.choices.find(c => c.is_user_created);
      return manualChoice?.text || '';
    }
    
    return '';
  }, [variants, currentVariantId]);

    // Load variants on mount if scene has multiple variants
  useEffect(() => {
    // Load variants if scene has multiple variants and we haven't loaded yet
    // OR if has_multiple_variants is true but variants array is empty/outdated
    if ((scene.has_multiple_variants || isLastScene) && !isLoadingVariants) {
      // If has_multiple_variants is true but we have 1 or fewer variants, force reload
      if (scene.has_multiple_variants && variants.length <= 1) {
        hasLoadedVariantsRef.current.delete(scene.id);
      }
      
      const shouldLoad = variants.length === 0 || 
                        (scene.has_multiple_variants && !hasLoadedVariantsRef.current.has(scene.id));
      
      if (shouldLoad) {
        hasLoadedVariantsRef.current.add(scene.id);
        loadVariants();
      }
    }
  }, [scene.id, scene.has_multiple_variants, isLastScene, isLoadingVariants, variants.length]);

  // Set initial variant ID from scene and reload variants when variant_id changes
  useEffect(() => {
    if (scene.variant_id) {
      // If variant_id changed or we don't have a current variant, reload variants
      if (scene.variant_id !== currentVariantId || !currentVariantId) {
        // Reload variants to get the updated list (including new variants)
        // Wait for operations to complete before reloading
        if (!isSceneOperationInProgress && !isGenerating && !isStreaming && !isRegenerating) {
          // Clear the loaded flag to force reload
          hasLoadedVariantsRef.current.delete(scene.id);
          // Pass the variant_id to ensure it's set after loading
          loadVariants(scene.variant_id);
        } else {
          // If operations are in progress, wait a bit and try again
          // This handles the case where variant completes but isRegenerating is still true briefly
          const timeoutId = setTimeout(() => {
            if (!isSceneOperationInProgress && !isGenerating && !isStreaming && !isRegenerating) {
              hasLoadedVariantsRef.current.delete(scene.id);
              loadVariants(scene.variant_id);
            }
          }, 500);
          return () => clearTimeout(timeoutId);
        }
      }
    } else if (!currentVariantId && variants.length > 0) {
      // If no variant_id but we have variants, use the first one
      setCurrentVariantId(variants[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.variant_id, currentVariantId, isSceneOperationInProgress, isGenerating, isStreaming, isRegenerating]);

  // Watch for scene object changes (e.g., after refreshStoryContent) and reload variants if needed
  // This ensures variants are reloaded when choices are updated via story refresh
  const previousSceneRef = useRef<Scene | null>(null);
  const sceneReloadInProgressRef = useRef<boolean>(false);
  useEffect(() => {
    // If scene object changed and we have variants loaded, check if we need to reload
    if (previousSceneRef.current && 
        previousSceneRef.current.id === scene.id && 
        hasLoadedVariantsRef.current.has(scene.id) &&
        variants.length > 0 &&
        !isLoadingVariants &&
        !isSceneOperationInProgress &&
        !sceneReloadInProgressRef.current) {
      
      // Check if choices count increased (new choices were added)
      const prevChoicesCount = previousSceneRef.current.choices?.length || 0;
      const currentChoicesCount = scene.choices?.length || 0;
      
      if (currentChoicesCount > prevChoicesCount) {
        // New choices were added, reload variants to get them
        console.log('[VARIANT RELOAD] Scene choices increased, reloading variants');
        sceneReloadInProgressRef.current = true;
        hasLoadedVariantsRef.current.delete(scene.id);
        loadVariants().finally(() => {
          sceneReloadInProgressRef.current = false;
        });
      }
    }
    
    previousSceneRef.current = scene;
  }, [scene, isLoadingVariants, isSceneOperationInProgress]);

  // Watch for variant reload trigger from parent (e.g., after generating more choices)
  useEffect(() => {
    // When trigger changes and we have a current variant, reload variants
    // Only process if trigger value has actually changed
    if (variantReloadTrigger && 
        variantReloadTrigger > 0 && 
        variantReloadTrigger !== lastTriggerRef.current &&
        currentVariantId && 
        !isLoadingVariants) {
      
      console.log('[VARIANT RELOAD] Triggered by parent, reloading variants. Trigger value:', variantReloadTrigger);
      lastTriggerRef.current = variantReloadTrigger;
      hasLoadedVariantsRef.current.delete(scene.id);
      loadVariants();
    }
  }, [variantReloadTrigger, currentVariantId, isLoadingVariants, scene.id]);

  // Reload variants when scene choices change (e.g., after generating more choices)
  // This ensures we get the latest choices including newly generated "more choices"
  const previousChoicesCountRef = useRef<number>(0);
  const sceneChoicesKeyRef = useRef<string>('');
  const choicesReloadInProgressRef = useRef<boolean>(false);
  
  useEffect(() => {
    // Skip if already processing a reload to prevent loops
    if (choicesReloadInProgressRef.current || sceneReloadInProgressRef.current) {
      return;
    }
    
    // Create a key from choices to detect changes (not just count)
    const currentChoicesKey = JSON.stringify(scene.choices?.map(c => ({ id: c.id, text: c.text, order: c.order })) || []);
    const currentChoicesCount = scene.choices?.length || 0;
    
    // For NEW scenes (no variants loaded yet), trigger initial load when choices appear
    if (variants.length === 0 && currentChoicesCount > 0 && !isLoadingVariants) {
      hasLoadedVariantsRef.current.delete(scene.id);
      loadVariants();
      previousChoicesCountRef.current = currentChoicesCount;
      sceneChoicesKeyRef.current = currentChoicesKey;
      return;
    }
    
    // For existing scenes, reload when choices change or count increases
    // This handles both choice updates and new choices being added
    if (hasLoadedVariantsRef.current.has(scene.id) && 
        variants.length > 0 && 
        currentVariantId &&
        !isLoadingVariants &&
        (currentChoicesKey !== sceneChoicesKeyRef.current || currentChoicesCount > previousChoicesCountRef.current)) {
      
      console.log('[VARIANT RELOAD] Choices changed, reloading variants');
      choicesReloadInProgressRef.current = true;
      hasLoadedVariantsRef.current.delete(scene.id); // Allow reload
      loadVariants().finally(() => {
        choicesReloadInProgressRef.current = false;
      });
    }
    
    // Update refs for next comparison
    previousChoicesCountRef.current = currentChoicesCount;
    sceneChoicesKeyRef.current = currentChoicesKey;
  }, [scene.choices, scene.id, currentVariantId, isLoadingVariants]);

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

  // Swipe gesture handlers removed - use arrow buttons for variant navigation on mobile

  // Handle copy scene text
  const handleCopyScene = async () => {
    const sceneToCopy = getDisplayScene();
    const textToCopy = sceneToCopy.content;
    
    try {
      if (onCopySceneText) {
        onCopySceneText(textToCopy);
      } else {
        // Fallback: use clipboard API directly
        await navigator.clipboard.writeText(textToCopy);
      }
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  // Handle delete button click
  const handleDeleteClick = () => {
    if (!isInDeleteMode) {
      // Not in delete mode: activate it and select this scene + subsequent scenes
      if (onActivateDeleteMode && scene.sequence_number) {
        onActivateDeleteMode(scene.sequence_number);
      }
    } else {
      // In delete mode: clicking adjusts the selection range
      if (isSceneSelectedForDeletion) {
        // If this scene is selected (and is the starting point), deactivate delete mode
        // Check if this is the earliest selected scene (starting point)
        // We'll deactivate if clicking the starting scene
        if (onDeactivateDeleteMode) {
          onDeactivateDeleteMode();
        }
      } else {
        // If this scene is NOT selected, adjust selection to start from here
        // This will deselect earlier scenes and select from here onwards
        if (onActivateDeleteMode && scene.sequence_number) {
          onActivateDeleteMode(scene.sequence_number);
        }
      }
    }
  };

  // Handle regeneration animation - only for manual variant switching, not new variant generation
  useEffect(() => {
    // Only animate if we're in modern layout and not streaming a new variant
    // Streaming variants should appear smoothly without slide animation
    if (isStreamingVariant || isStreaming) {
      // Don't animate during streaming - content appears naturally
      // Also clear any existing animation classes
      const container = sceneContentRef.current;
      if (container) {
        container.classList.remove('variant-transitioning');
        container.classList.remove('variant-slide-in');
      }
      return;
    }
    
    if (isRegenerating && layoutMode === 'modern') {
      const container = sceneContentRef.current;
      if (container) {
        // Slide out the current scene when regeneration starts (manual regeneration only)
        container.classList.remove('variant-slide-in');
        container.classList.add('variant-transitioning');
      }
    } else {
      // Slide in from right when regeneration completes or variant changes
      // But only if we had the transitioning class (manual switch), not for new variant generation
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
  }, [isRegenerating, layoutMode, currentVariantId, isStreamingVariant, isStreaming]);

  // Get the currently displayed variant's data
  const getCurrentVariant = (): SceneVariant | null => {
    if (!currentVariantId || variants.length === 0) return null;
    return variants.find(v => v.id === currentVariantId) || null;
  };

  // Regenerate choices for the current variant
  const handleRegenerateChoices = async () => {
    if (!currentVariantId) {
      console.error('[RegenerateChoices] No current variant ID available');
      alert('Cannot regenerate choices: no variant selected');
      return;
    }
    
    // Get the current variant to verify it exists
    const currentVariant = getCurrentVariant();
    if (!currentVariant) {
      console.error('[RegenerateChoices] Current variant not found in variants list');
      alert('Cannot regenerate choices: variant not found');
      return;
    }
    
    setIsRegeneratingChoices(true);
    try {
      const response = await apiClient.regenerateSceneVariantChoices(storyId, scene.id, currentVariantId);
      
      // Force reload variants to get updated choices
      hasLoadedVariantsRef.current.delete(scene.id);
      await loadVariants();

      // Notify parent (choices are loaded locally, no full refresh needed)
      if (onVariantChanged) {
        onVariantChanged(scene.id);
      }
    } catch (error) {
      console.error('[RegenerateChoices] Failed to regenerate choices:', error);
      // Extract error message - API client already extracts detail/message from backend
      const errorMessage = error instanceof Error 
        ? error.message 
        : 'Failed to regenerate choices. Please try again or use the custom prompt field to specify your continuation.';
      alert(errorMessage);
    } finally {
      setIsRegeneratingChoices(false);
    }
  };

  // Create a scene object with the current variant's content
  const getDisplayScene = (): Scene => {
    // If streaming a variant regeneration, show the streaming content
    // When streaming a variant, show streaming content or hide old variant
    if (isStreamingVariant) {
      if (streamingVariantContent) {
        // Show streaming content as it arrives
        return {
          ...scene,
          content: streamingVariantContent,
          title: scene.title,
          choices: []
        };
      } else {
        // Hide old variant immediately when streaming starts (before content arrives)
        return {
          ...scene,
          content: '',
          title: scene.title,
          choices: []
        };
      }
    }
    
    const currentVariant = getCurrentVariant();
    if (currentVariant) {
      // Replace scene content with current variant's content
      return {
        ...scene,
        content: currentVariant.content,
        title: currentVariant.title,
        choices: currentVariant.choices,
        variant_id: currentVariant.id
      };
    }
    return scene;
  };

  return (
    <div ref={sceneContentRef} className="scene-variant-container">
      <div className={isStreamingVariant ? 'relative streaming-variant' : 'relative'} suppressHydrationWarning>
        {isStreamingVariant && (
          <div className="absolute top-0 right-0 bg-pink-600 text-white text-xs px-2 py-1 rounded-full animate-pulse z-10">
            Generating...
          </div>
        )}
        
        <SceneDisplay
          scene={getDisplayScene()}
          sceneNumber={sceneNumber}
          format={userSettings?.scene_display_format || 'default'}
          containerStyle="lines"
          showTitle={userSettings?.show_scene_titles === true}
          isEditing={isEditing}
          editContent={editContent}
          onStartEdit={onStartEdit}
          onSaveEdit={async (sceneId, content, variantId) => {
            await onSaveEdit(sceneId, content, variantId);
            // Reload variants after save to get updated user_edited flag
            await loadVariants();
          }}
        onCancelEdit={onCancelEdit}
        onContentChange={onContentChange}
        streamingContinuation={streamingContinuation}
        isStreamingContinuation={isStreamingContinuation}
        isStreamingVariant={isStreamingVariant}
        userSettings={userSettings}
      />

      {/* Inline Contradiction Check Display */}
      {checkingContradictions && (
        <div className="mt-3 px-4 py-2 rounded-lg border border-amber-700/50 bg-amber-900/20 flex items-center gap-2">
          <div className="animate-spin h-4 w-4 border-2 border-amber-400 border-t-transparent rounded-full" />
          <span className="text-amber-300 text-sm">Checking continuity...</span>
        </div>
      )}

      {contradictions && contradictions.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-600/60 bg-amber-950/40 overflow-hidden">
          <div className="px-4 py-2 border-b border-amber-700/40 flex items-center gap-2">
            <span className="text-amber-400 text-sm font-medium">Continuity Issue Detected</span>
          </div>
          <div className="px-4 py-3 space-y-2">
            {contradictions.map((c) => (
              <div key={c.id} className="text-sm">
                <div className="flex items-start gap-2">
                  <span className={`inline-block mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
                    c.severity === 'error' ? 'bg-red-400' : c.severity === 'warning' ? 'bg-amber-400' : 'bg-blue-400'
                  }`} />
                  <div className="flex-1">
                    <span className="text-gray-300 font-medium">
                      [{c.type.replace(/_/g, ' ')}]
                    </span>
                    {c.character_name && (
                      <span className="text-white ml-1">{c.character_name}:</span>
                    )}
                    <div className="text-gray-400 mt-0.5">
                      {c.previous_value && c.current_value ? (
                        <>was &quot;{c.previous_value}&quot; → now &quot;{c.current_value}&quot;</>
                      ) : (
                        c.current_value || c.previous_value || 'Unknown issue'
                      )}
                    </div>
                  </div>
                </div>

                {/* Resolution form for this contradiction */}
                {resolvingContradictionId === c.id ? (
                  <div className="mt-2 ml-4 space-y-2">
                    <input
                      type="text"
                      value={resolutionNote}
                      onChange={(e) => setResolutionNote(e.target.value)}
                      placeholder="Resolution note (optional)"
                      className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white placeholder-gray-500"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          handleResolveContradiction(c.id);
                        } else if (e.key === 'Escape') {
                          setResolvingContradictionId(null);
                          setResolutionNote('');
                        }
                      }}
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleResolveContradiction(c.id)}
                        disabled={isResolvingContradiction}
                        className="px-3 py-1 text-xs bg-green-700 hover:bg-green-600 text-white rounded disabled:opacity-50"
                      >
                        {isResolvingContradiction ? 'Resolving...' : 'Confirm'}
                      </button>
                      <button
                        onClick={() => { setResolvingContradictionId(null); setResolutionNote(''); }}
                        className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          <div className="px-4 py-2 border-t border-amber-700/40 flex gap-2">
            <button
              onClick={() => {
                const firstUnresolved = contradictions.find(c => resolvingContradictionId !== c.id);
                if (firstUnresolved) {
                  setResolvingContradictionId(firstUnresolved.id);
                  setResolutionNote('');
                }
              }}
              className="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
            >
              Resolve
            </button>
            <button
              onClick={() => onCreateVariant(scene.id)}
              className="px-3 py-1.5 text-xs bg-amber-700 hover:bg-amber-600 text-white rounded transition-colors"
            >
              Regenerate Scene
            </button>
          </div>
        </div>
      )}

      {/* Inline Scene Image Generator - show if global toggle is on OR user clicked to open */}
      {(showImages || showImageGenerator) && (
        <SceneImageGenerator
          sceneId={scene.id}
          storyId={storyId}
          sceneContent={getDisplayScene().content}
          forceShow={showImageGenerator}
          onClose={() => setShowImageGenerator(false)}
          defaultCheckpoint={userSettings?.image_generation_settings?.comfyui_checkpoint || ''}
          defaultStyle={userSettings?.image_generation_settings?.default_style || 'illustrated'}
          defaultSteps={userSettings?.image_generation_settings?.steps}
          defaultCfgScale={userSettings?.image_generation_settings?.cfg_scale}
        />
      )}

      {/* Variant Indicator - Below scene content */}
      {isLastScene && shouldShowNavigation() && (
        <div className="flex items-center justify-center gap-3 mt-2 mb-4">
          {/* Left Arrow */}
          <button
            onClick={() => {
              if (variants.length <= 1) {
                loadVariants().then(() => navigateToPrevious());
              } else {
                navigateToPrevious();
              }
            }}
            disabled={!canNavigateToPrevious()}
            className="flex items-center justify-center transition-all opacity-70 hover:opacity-100 active:opacity-100 disabled:opacity-30 disabled:cursor-not-allowed text-white hover:text-gray-200 active:text-gray-200 text-2xl font-light px-2 py-1 min-w-[44px] min-h-[44px] touch-manipulation"
            title="Previous variant (←)"
          >
            &lt;
          </button>
          
          {/* Variant count text */}
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {variants.length > 0
              ? (getCurrentVariantIndex() + 1) + ' of ' + variants.length
              : isLoadingVariants ? 'Loading...' : '1 of ?'}
          </span>
          
          {/* Right Arrow */}
          <button
            onClick={() => {
              if (variants.length <= 1) {
                loadVariants().then(() => navigateToNext());
              } else {
                navigateToNext();
              }
            }}
            disabled={!canNavigateToNext()}
            className="flex items-center justify-center transition-all opacity-70 hover:opacity-100 active:opacity-100 disabled:opacity-30 disabled:cursor-not-allowed text-white hover:text-gray-200 active:text-gray-200 text-2xl font-light px-2 py-1 min-w-[44px] min-h-[44px] touch-manipulation"
            title="Next variant (→)"
          >
            &gt;
          </button>
        </div>
      )}
      
      {/* Quick Action Buttons - Floating buttons in top-right */}
      {isClient && (
        <div className="absolute -top-4 -right-4 md:-top-2 md:-right-2 z-10 flex items-center gap-1">
          {/* Edit Button */}
          {!isEditing && (
            <button
              onClick={() => onStartEdit(scene)}
              className="flex items-center justify-center transition-all duration-200 flex-shrink-0 text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1"
              title="Edit scene"
            >
              <PencilIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
            </button>
          )}

          {/* Copy Button */}
          <button
            onClick={handleCopyScene}
            className={
              'flex items-center justify-center transition-all duration-200 flex-shrink-0 ' +
              (copySuccess 
                ? 'text-green-400 hover:text-green-300' 
                : 'text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1')
            }
            title={copySuccess ? 'Copied!' : 'Copy scene text'}
          >
            {copySuccess ? (
              <svg className="w-3.5 h-3.5 md:w-4 md:h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
            ) : (
              <ClipboardIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
            )}
          </button>

          {/* Delete Button - Always visible */}
          <button
            onClick={handleDeleteClick}
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
                ? (isSceneSelectedForDeletion 
                    ? 'Cancel delete mode' 
                    : 'Delete from this scene onwards instead')
                : 'Delete from this scene onwards'
            }
          >
            <TrashIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
          </button>

          {/* Create Branch Button */}
          <button
            onClick={() => onCreateBranch?.(scene.sequence_number)}
            className="flex items-center justify-center transition-all duration-200 flex-shrink-0 text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 rounded p-1"
            title="Create branch from this scene"
          >
            <GitFork className="w-3.5 h-3.5 md:w-4 md:h-4" />
          </button>

          {/* Generate Image Button */}
          <button
            onClick={() => setShowImageGenerator(!showImageGenerator)}
            className={`flex items-center justify-center transition-all duration-200 flex-shrink-0 hover:bg-gray-800/50 rounded p-1 ${
              showImageGenerator ? 'text-purple-400' : 'text-gray-400 hover:text-gray-300'
            }`}
            title={showImageGenerator ? 'Hide image generator' : 'Generate image for this scene'}
          >
            <Image className="w-3.5 h-3.5 md:w-4 md:h-4" />
          </button>

          {/* Audio Controls - Floating speaker button */}
          <div className="flex-shrink-0">
            <SceneTTSButton sceneId={scene.id} className="relative" />
          </div>
        </div>
      )}
      </div>
      
      {/* Scene Management - Only show for last scene */}
      {isLastScene && (
        <div className="space-y-4 mt-6 pt-4 border-t border-gray-600/30">
          {/* Floating Action Menu - Works on both mobile and desktop */}
          {isClient && (
          <div 
            className="fixed right-0 bottom-24 z-50"
            onMouseEnter={resetMenuTimer}
            onMouseLeave={() => {
              if (!showFloatingMenu) {
                hideMenu();
              }
            }}
            onTouchStart={resetMenuTimer}
          >
            {/* Floating Menu Items */}
            {showFloatingMenu && (
              <div className="absolute right-16 md:right-20 bottom-0 space-y-2 animate-fade-in">
                {/* Regenerate */}
                <button
                  onClick={() => {
                    setShowFloatingMenu(false);
                    resetMenuTimer();
                    onCreateVariant(scene.id, undefined, currentVariantId || undefined);
                  }}
                  disabled={isGenerating || isStreaming || isRegenerating}
                  className="flex items-center gap-2 w-full px-4 py-2 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
                  title="Regenerate current scene"
                >
                  <ArrowPathIcon className="w-5 h-5" />
                  <span className="text-sm font-medium">Regenerate</span>
                </button>
                
                {/* Continue */}
                <button
                  onClick={() => {
                    setShowFloatingMenu(false);
                    resetMenuTimer();
                    if (onContinueScene) {
                      onContinueScene(scene.id, "Continue this scene with more details and development, adding to the existing content.");
                    } else {
                      onCreateVariant?.(scene.id, "Continue this scene with more details and development, adding to the existing content rather than replacing it.", currentVariantId || undefined);
                    }
                  }}
                  disabled={isGenerating || isStreaming || isRegenerating}
                  className="flex items-center gap-2 w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
                  title="Continue current scene"
                >
                  <PlusCircleIcon className="w-5 h-5" />
                  <span className="text-sm font-medium">Continue</span>
                </button>
                
                {/* Guided */}
                <button
                  onClick={() => {
                    setShowGuidedOptions(!showGuidedOptions);
                    if (!showGuidedOptions) {
                      setShowFloatingMenu(false);
                      resetMenuTimer();
                    }
                  }}
                  disabled={isGenerating || isStreaming || isRegenerating}
                  className={'flex items-center gap-2 w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm ' + (showGuidedOptions ? 'ring-2 ring-purple-400' : '')}
                  title="Guided regeneration options"
                >
                  <SparklesIcon className="w-5 h-5" />
                  <span className="text-sm font-medium">Guided</span>
                </button>
                
                {/* Conclude */}
                <button
                  onClick={() => {
                    setShowFloatingMenu(false);
                    resetMenuTimer();
                    onGenerateScene?.(undefined, true);
                  }}
                  disabled={isGenerating || isStreaming || isRegenerating}
                  className="flex items-center gap-2 w-full px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
                  title="Write concluding scene for this chapter"
                >
                  <FlagIcon className="w-5 h-5" />
                  <span className="text-sm font-medium">Conclude</span>
                </button>
                
                {/* Edit Scene */}
                <button
                  onClick={() => {
                    setShowFloatingMenu(false);
                    resetMenuTimer();
                    onStartEdit(scene);
                  }}
                  disabled={isEditing}
                  className="flex items-center gap-2 w-full px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
                  title="Edit scene"
                >
                  <PencilIcon className="w-5 h-5" />
                  <span className="text-sm font-medium">Edit Scene</span>
                </button>

                {/* Play/Stop TTS */}
                <button
                  onClick={() => {
                    setShowFloatingMenu(false);
                    resetMenuTimer();
                    if (isTTSPlaying && currentSceneId === scene.id) {
                      stop();
                    } else {
                      playScene(scene.id);
                    }
                  }}
                  className={`flex items-center gap-2 w-full px-4 py-2 rounded-lg shadow-lg transition-all backdrop-blur-sm text-white ${
                    isTTSPlaying && currentSceneId === scene.id
                      ? 'bg-red-600 hover:bg-red-700'
                      : 'bg-green-600 hover:bg-green-700'
                  }`}
                  title={isTTSPlaying && currentSceneId === scene.id ? 'Stop TTS' : 'Play TTS'}
                >
                  {isTTSPlaying && currentSceneId === scene.id ? (
                    <StopIcon className="w-5 h-5" />
                  ) : (
                    <Volume2 className="w-5 h-5" />
                  )}
                  <span className="text-sm font-medium">
                    {isTTSPlaying && currentSceneId === scene.id ? 'Stop TTS' : 'Play TTS'}
                  </span>
                </button>
                
                {/* Delete Mode Toggle */}
                <button
                  onClick={() => {
                    setShowFloatingMenu(false);
                    resetMenuTimer();
                    handleDeleteClick();
                  }}
                  className={'flex items-center gap-2 w-full px-4 py-2 rounded-lg shadow-lg transition-all backdrop-blur-sm ' + (isInDeleteMode && isSceneSelectedForDeletion
                      ? 'bg-red-600 hover:bg-red-700 text-white'
                      : isInDeleteMode
                      ? 'bg-gray-700 hover:bg-gray-600 text-gray-200'
                      : 'bg-gray-700 hover:bg-red-600 text-gray-200')}
                  title={isInDeleteMode ? 'Cancel delete mode' : 'Delete from this scene onwards'}
                >
                  <TrashIcon className="w-5 h-5" />
                  <span className="text-sm font-medium">
                    {isInDeleteMode ? 'Cancel Delete' : 'Delete'}
                  </span>
                </button>
                
                {/* Stop Generation - Only show when generating */}
                {(isGenerating || isStreaming || isRegenerating || isStreamingContinuation) && onStopGeneration && (
                  <button
                    onClick={() => {
                      setShowFloatingMenu(false);
                      resetMenuTimer();
                      onStopGeneration();
                    }}
                    className="flex items-center gap-2 w-full px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
                    title="Stop generation"
                  >
                    <StopIcon className="w-5 h-5" />
                    <span className="text-sm font-medium">Stop</span>
                  </button>
                )}
              </div>
            )}
            
            {/* Guided Options Panel */}
            {showGuidedOptions && (
              <div className="fixed right-16 md:right-20 top-16 bottom-4 w-52 md:w-64 animate-fade-in z-50">
                <div className="bg-gray-900/95 backdrop-blur-md rounded-xl border border-purple-500/30 shadow-2xl overflow-hidden h-auto max-h-full flex flex-col">
                  {/* Header */}
                  <div className="flex items-center justify-between px-3 py-2 bg-gradient-to-r from-purple-600/30 to-pink-600/30 border-b border-purple-500/20 flex-shrink-0">
                    <span className="text-xs font-semibold text-purple-200">Guided Options</span>
                    <button
                      onClick={() => setShowGuidedOptions(false)}
                      className="p-1 hover:bg-white/10 rounded transition-colors"
                    >
                      <XMarkIcon className="w-4 h-4 text-purple-200" />
                    </button>
                  </div>
                  {/* Options */}
                  <div className="p-2 space-y-1 overflow-y-auto flex-1">
                    {[
                      { label: "More Dialogue", prompt: "Regenerate this scene with more dialogue and character interactions." },
                      { label: "Internal Thoughts", prompt: "Regenerate this scene with more internal thoughts and character emotions." },
                      { label: "Describe Setting", prompt: "Regenerate this scene with more detailed descriptions of the environment and atmosphere." },
                      { label: "Action/Movement", prompt: "Regenerate this scene with more action and character movements." },
                      { label: "Build Tension", prompt: "Regenerate this scene with more tension and dramatic elements." },
                      { label: "Character Growth", prompt: "Regenerate this scene focusing more on character growth and development." }
                    ].map((option, index) => (
                      <button
                        key={index}
                        onClick={() => {
                          setShowGuidedOptions(false);
                          resetMenuTimer();
                          onCreateVariant?.(scene.id, option.prompt, currentVariantId || undefined);
                        }}
                        disabled={isGenerating || isStreaming || isRegenerating}
                        className="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:text-white hover:bg-purple-600/30 rounded-lg transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                  {/* Custom Guide Input */}
                  <div className="p-2 border-t border-purple-500/20">
                    <div className="text-xs text-purple-300 mb-1.5 px-1">Custom Guide</div>
                    <textarea
                      value={customGuideText}
                      onChange={(e) => setCustomGuideText(e.target.value)}
                      placeholder="Describe how to regenerate this scene..."
                      disabled={isGenerating || isStreaming || isRegenerating}
                      className="w-full px-3 py-2 text-sm bg-gray-800/80 border border-purple-500/30 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/50 resize-none disabled:opacity-50"
                      rows={2}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey && customGuideText.trim()) {
                          e.preventDefault();
                          setShowGuidedOptions(false);
                          resetMenuTimer();
                          onCreateVariant?.(scene.id, customGuideText.trim(), currentVariantId || undefined);
                          setCustomGuideText('');
                        }
                      }}
                    />
                    <button
                      onClick={() => {
                        if (customGuideText.trim()) {
                          setShowGuidedOptions(false);
                          resetMenuTimer();
                          onCreateVariant?.(scene.id, customGuideText.trim(), currentVariantId || undefined);
                          setCustomGuideText('');
                        }
                      }}
                      disabled={isGenerating || isStreaming || isRegenerating || !customGuideText.trim()}
                      className="w-full mt-2 px-3 py-2 text-sm font-medium text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-lg transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
                    >
                      Generate with Custom Guide
                    </button>
                  </div>
                </div>
              </div>
            )}
            
            {/* Edge Tab Button */}
            <button
              onClick={() => {
                setShowFloatingMenu(!showFloatingMenu);
                resetMenuTimer();
              }}
              onMouseEnter={resetMenuTimer}
              className={
                'w-8 md:w-10 h-20 md:h-24 rounded-l-xl bg-gradient-to-r from-pink-600 to-purple-600 ' +
                'hover:from-pink-700 hover:to-purple-700 shadow-lg ' +
                'flex items-center justify-center transition-all backdrop-blur-sm ' +
                'border-l border-t border-b border-white/20 ' +
                (showFloatingMenu || isMenuVisible ? 'translate-x-0 opacity-100' : 'translate-x-6 md:translate-x-8 opacity-30 hover:translate-x-0 hover:opacity-100')
              }
              title="Scene actions"
            >
              {showFloatingMenu ? (
                <XMarkIcon className="w-5 h-5 md:w-6 md:h-6 text-white" />
              ) : (
                <SparklesIcon className="w-5 h-5 md:w-6 md:h-6 text-white" />
              )}
            </button>
          </div>
          )}

        </div>
      )}
      
      {/* Story continuation choices and input - Only show for last scene */}
      {isLastScene && (
        <div className="mt-6">
          {/* Choice Buttons - Keep in DOM but hide with opacity to prevent layout shifts */}
          {showChoices && !directorMode && (
            <div className={'space-y-1.5 mb-4 transition-opacity duration-200 ' + (showChoicesDuringGeneration 
                ? 'opacity-100 pointer-events-auto' 
                : 'opacity-30 pointer-events-none')}>
              {getAvailableChoicesWithData().length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                  {getAvailableChoicesWithData().map((choice, index) => 
                    editingChoiceId === choice.id ? (
                      // Edit mode - show input field
                      <div
                        key={`edit-${choice.id ?? index}`}
                        className={'w-full p-2 transition-all duration-200 ' + (layoutMode === 'modern' ? 'rounded-lg' : 'theme-btn-secondary border border-pink-500 rounded-lg') + ' bg-gray-800/80'}
                      >
                        <div className="flex items-center gap-2">
                          <input
                            ref={choiceInputRef}
                            type="text"
                            value={editingChoiceText}
                            onChange={(e) => setEditingChoiceText(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                handleSaveEditChoice();
                              } else if (e.key === 'Escape') {
                                handleCancelEditChoice();
                              }
                            }}
                            disabled={isSavingChoice}
                            className="flex-1 bg-transparent outline-none text-gray-200 text-xs leading-tight placeholder-gray-500 min-w-0"
                            placeholder="Edit choice..."
                          />
                          <button
                            onClick={handleSaveEditChoice}
                            disabled={isSavingChoice || !editingChoiceText.trim()}
                            className="p-1 text-green-500 hover:text-green-400 disabled:text-gray-600 transition-colors flex-shrink-0"
                            title="Save (Enter)"
                          >
                            {isSavingChoice ? (
                              <div className="w-3.5 h-3.5 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
                            ) : (
                              <CheckIcon className="w-3.5 h-3.5" />
                            )}
                          </button>
                          <button
                            onClick={handleCancelEditChoice}
                            disabled={isSavingChoice}
                            className="p-1 text-gray-400 hover:text-gray-300 disabled:text-gray-600 transition-colors flex-shrink-0"
                            title="Cancel (Esc)"
                          >
                            <XMarkIcon className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ) : (
                      // Display mode - show choice button with edit icon
                      // On mobile: tap text to use choice, edit icon always visible
                      // On desktop: hover reveals play button
                      <div
                        key={`choice-${choice.id ?? index}`}
                        className={'w-full text-left py-2 pl-2 pr-0 md:p-2 transition-all duration-200 group modern-choice-button compact cursor-pointer ' + (layoutMode === 'modern' ? 'rounded-lg' : 'theme-btn-secondary hover:opacity-80 border border-gray-600 rounded-lg') + ' ' + (selectedChoice === choice.text ? 'ring-2 ring-pink-500 bg-pink-900/20' : '') + ' ' + ((!showChoicesDuringGeneration || isGenerating || isStreaming) ? 'opacity-50 pointer-events-none' : '')}
                        onClick={() => {
                          if (!showChoicesDuringGeneration || isGenerating || isStreaming) return;
                          setSelectedChoice?.(choice.text);
                          setShowChoicesDuringGeneration?.(false);
                          onGenerateScene?.(choice.text);
                        }}
                      >
                        <div className="flex items-center justify-between relative z-10">
                          <span className="text-gray-200 text-xs leading-tight flex-1 min-w-0">{choice.text}</span>
                          {/* Edit button - always visible on mobile, hover on desktop */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!showChoicesDuringGeneration || isGenerating || isStreaming) return;
                              handleStartEditChoice(choice);
                            }}
                            className="px-2 py-1 text-gray-400 hover:text-purple-400 md:opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                            title="Edit choice"
                          >
                            <PencilIcon className="w-3.5 h-3.5" />
                          </button>
                          {/* Play button - desktop only, hidden on mobile since tap on text works */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!showChoicesDuringGeneration || isGenerating || isStreaming) return;
                              setSelectedChoice?.(choice.text);
                              setShowChoicesDuringGeneration?.(false);
                              onGenerateScene?.(choice.text);
                            }}
                            className="hidden md:block p-0.5 text-pink-500 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                            title="Use this choice"
                          >
                            <PlayIcon className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <div className="text-center py-4">
                  {isGeneratingChoices ? (
                    <div className="flex items-center justify-center space-x-2">
                      <div className="w-4 h-4 border-2 border-pink-500 border-t-transparent rounded-full animate-spin"></div>
                      <span className="text-sm text-gray-400">Generating choices...</span>
                    </div>
                  ) : !isGenerating && !isStreaming ? (
                    <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-4 text-left">
                      <p className="text-sm text-blue-300 mb-2">
                        AI failed to generate choices. You can regenerate choices using the button below, or specify your own continuation in the custom prompt field.
                      </p>
                    </div>
                  ) : (
                    <div className="animate-pulse text-gray-400">Loading story choices...</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Regenerate Choices Button - Show for last scene if variant has been manually edited OR if no choices available */}
          {isLastScene && (getCurrentVariant()?.user_edited || getAvailableChoices().length === 0) && (
            <div className="mb-4 flex justify-center">
              <button
                onClick={handleRegenerateChoices}
                disabled={isRegeneratingChoices || isGenerating || isStreaming || isRegenerating}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-md text-sm transition-colors flex items-center space-x-2"
              >
                {isRegeneratingChoices ? (
                  <>
                    <span className="animate-spin">⚡</span>
                    <span>Regenerating choices...</span>
                  </>
                ) : (
                  <>
                    <span>🔄</span>
                    <span>Regenerate Choices</span>
                  </>
                )}
              </button>
            </div>
          )}

          {/* Selected Choice Placeholder - Show when choice is selected but generation hasn't started */}
          {selectedChoice && !isGenerating && !isStreaming && !showChoicesDuringGeneration && (
            <div className="mb-6 p-4 theme-bg-secondary/50 rounded-xl border border-gray-600">
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-pink-500 rounded-full animate-pulse"></div>
                <span className="text-gray-300 text-sm">Selected: "{selectedChoice}"</span>
              </div>
            </div>
          )}

          {/* Continue Input - Keep in DOM but hide with opacity to prevent layout shifts */}
          {!directorMode && (
            <div className={(layoutMode === 'modern'
                ? 'modern-input-container'
                : 'theme-bg-secondary rounded-xl border border-gray-600') + ' p-4 transition-opacity duration-200 ' + (showChoicesDuringGeneration && !isGenerating && !isStreaming && !isRegenerating && !isStreamingContinuation
                ? 'opacity-100 pointer-events-auto'
                : 'opacity-30 pointer-events-none')}>
              <div className="flex items-center justify-between">
                <input
                  ref={customPromptInputRef}
                  type="text"
                  value={customPrompt}
                  onChange={(e) => onCustomPromptChange?.(e.target.value)}
                  placeholder="Write what happens next..."
                  className="flex-1 bg-transparent outline-none theme-placeholder"
                  style={{ color: 'var(--color-textPrimary)' }}
                  onFocus={() => {
                    // Prevent scroll on mobile when focusing
                    if (customPromptFocusHandledRef.current) {
                      customPromptFocusHandledRef.current = false;
                      return;
                    }
                    customPromptFocusHandledRef.current = true;
                    customPromptInputRef.current?.blur();
                    requestAnimationFrame(() => {
                      customPromptInputRef.current?.focus({ preventScroll: true });
                    });
                  }}
                  onKeyPress={(e) => {
                    const currentValue = customPrompt;
                    if (e.key === 'Enter' && currentValue.trim()) {
                      // Use the current value from the input, not customPrompt state
                      const inputValue = (e.target as HTMLInputElement).value;
                      if (inputValue.trim()) {
                        onGenerateScene?.(inputValue);
                      }
                    }
                  }}
                  disabled={!showChoicesDuringGeneration || isGenerating || isStreaming || isRegenerating || isStreamingContinuation}
                />
                <MicrophoneButton
                  onTranscriptUpdate={(text) => {
                    // Real-time update while recording - replace with STT text only
                    // The backend sends the full accumulated sentence
                    onCustomPromptChange?.(text);
                  }}
                  onTranscriptComplete={(text) => {
                    // Final transcript when stopped - replace with STT text only
                    onCustomPromptChange?.(text);
                  }}
                  disabled={!showChoicesDuringGeneration || isGenerating || isStreaming || isRegenerating || isStreamingContinuation}
                  className="ml-2"
                  showPreview={true}
                />
                <button
                  onClick={() => {
                    const currentValue = customPrompt;
                    if (currentValue.trim()) {
                      onGenerateScene?.(currentValue);
                    }
                  }}
                  disabled={!showChoicesDuringGeneration || isGenerating || isStreaming || !customPrompt.trim() || isRegenerating || isStreamingContinuation}
                  className={'ml-3 rounded-lg p-2 transition-colors ' + (layoutMode === 'modern'
                      ? 'bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-700 hover:to-purple-700 disabled:from-gray-600 disabled:to-gray-600'
                      : 'bg-pink-600 hover:bg-pink-700 disabled:bg-gray-600')}
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