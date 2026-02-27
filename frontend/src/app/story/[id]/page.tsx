'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { flushSync } from 'react-dom';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useAuthStore, useStoryStore, useHasHydrated } from '@/store';
import RouteProtection from '@/components/RouteProtection';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { useStoryActions, StoryActions } from '@/contexts/StoryContext';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient, { getApiBaseUrl, StoryArc } from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';
import StoryCharacterVoiceEditor from '@/components/StoryCharacterVoiceEditor';
import StoryCharacterManager from '@/components/StoryCharacterManager';
import { ContextInfo } from '@/components/ContextInfo';
import FormattedText from '@/components/FormattedText';
import SceneDisplay from '@/components/SceneDisplay';
import SceneVariantDisplay from '@/components/SceneVariantDisplay';
import BranchCreationModal from '@/components/BranchCreationModal';
import { GlobalTTSWidget } from '@/components/GlobalTTSWidget';
import MicrophoneButton from '@/components/MicrophoneButton';
import BranchSelector from '@/components/BranchSelector';
import ThinkingBox from '@/components/ThinkingBox';
import ImageGallery from '@/components/ImageGallery';

// Lazy load heavy components - only load when needed
const CharacterWizard = dynamic(() => import('@/components/CharacterWizard'), {
  loading: () => null,
  ssr: false
});

const ChapterSidebar = dynamic(() => import('@/components/ChapterSidebar'), {
  loading: () => null,
  ssr: false
});

const ChapterWizard = dynamic(() => import('@/components/ChapterWizard'), {
  loading: () => null,
  ssr: false
});

const TTSSettingsModal = dynamic(() => import('@/components/TTSSettingsModal'), {
  loading: () => null,
  ssr: false
});

const StorySettingsModal = dynamic(() => import('@/components/StorySettingsModal'), {
  loading: () => null,
  ssr: false
});

const StoryArcViewer = dynamic(() => import('@/components/StoryArcViewer'), {
  loading: () => null,
  ssr: false
});

const ChapterBrainstormModal = dynamic(() => import('@/components/ChapterBrainstormModal'), {
  loading: () => null,
  ssr: false
});

const CharacterInteractionsModal = dynamic(() => import('@/components/CharacterInteractionsModal'), {
  loading: () => null,
  ssr: false
});

const EntityStatesModal = dynamic(() => import('@/components/EntityStatesModal'), {
  loading: () => null,
  ssr: false
});

const ContradictionsModal = dynamic(() => import('@/components/ContradictionsModal'), {
  loading: () => null,
  ssr: false
});

const CharacterRoleEditor = dynamic(() => import('@/components/CharacterRoleEditor'), {
  loading: () => null,
  ssr: false
});

const ChapterProgressIndicator = dynamic(() => import('@/components/ChapterProgressIndicator'), {
  loading: () => null,
  ssr: false
});
import { BookOpen, ChevronRight, X, AlertCircle, Sparkles, Volume2, Trash2, Edit2 } from 'lucide-react';
import { 
  BookOpenIcon, 
  FilmIcon,
  PhotoIcon,
  ClockIcon,
  CheckIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  DocumentDuplicateIcon,
  PlusIcon,
  PlayIcon,
  DocumentTextIcon,
  TrashIcon
} from '@heroicons/react/24/outline';

interface Scene {
  id: number;
  sequence_number: number;
  title: string;
  content: string;
  location: string;
  characters_present: string[];
  chapter_id?: number; // Link to chapter
  // New variant properties
  variant_id?: number;
  variant_number?: number;
  is_original?: boolean;
  has_multiple_variants?: boolean;
  total_variants?: number; // Total number of variants for multi-generation
  choices?: Array<{
    id: number;
    text: string;
    description?: string;
    order: number;
    is_user_created?: boolean;
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
  content_rating?: string;  // "sfw" or "nsfw"
  plot_check_mode?: '1' | '3' | 'all';  // How many events to check
  scenes: Scene[];
  story_arc?: StoryArc | null;
  flow_info?: {
    total_scenes: number;
    has_variants: boolean;
  };
  branch?: {
    id: number;
    name: string;
    is_main: boolean;
    total_branches: number;
  };
  current_branch_id?: number;
}

export default function StoryPage() {
  const params = useParams();
  const storyId = parseInt(params.id as string);

  // Key forces full unmount/remount when storyId changes.
  // Without this, React reuses the component instance when navigating
  // between /story/8 and /story/11, leaving stale state visible.
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <StoryPageContent key={storyId} storyId={storyId} />
    </RouteProtection>
  );
}

function StoryPageContent({ storyId }: { storyId: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const { user, token } = useAuthStore();
  const hasHydrated = useHasHydrated();
  const globalTTS = useGlobalTTS();
  const { setStoryActions } = useStoryActions();
  const loadStoryRef = useRef<((scrollToLastScene?: boolean, scrollToNewScene?: boolean, overrideBranchId?: number) => Promise<void>) | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [currentChapterIndex, setCurrentChapterIndex] = useState(0);
  const [showChoices, setShowChoices] = useState(true);
  const [directorMode, setDirectorMode] = useState(false);
  const [showImages, setShowImages] = useState(true); // Global toggle for scene images
  const [showGallery, setShowGallery] = useState(false); // Image gallery modal
  const [editingScene, setEditingScene] = useState<number | null>(null);
  const [editingVariantId, setEditingVariantId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [showCharacterWizard, setShowCharacterWizard] = useState(false);
  const [showCharacterVoiceEditor, setShowCharacterVoiceEditor] = useState(false);
  const [showCharacterRoleEditor, setShowCharacterRoleEditor] = useState(false);
  const [showStoryCharacterManager, setShowStoryCharacterManager] = useState(false);
  const [showCharacterBanner, setShowCharacterBanner] = useState(false);
  const [showChapterBrainstormModal, setShowChapterBrainstormModal] = useState(false);
  const [brainstormChapterId, setBrainstormChapterId] = useState<number | undefined>(undefined);
  const [brainstormPlot, setBrainstormPlot] = useState<any>(null);  // Plot from brainstorm to use in chapter creation
  const [brainstormSessionId, setBrainstormSessionId] = useState<number | undefined>(undefined);
  const [currentChapterId, setCurrentChapterId] = useState<number | undefined>(undefined);
  const [storyCharacters, setStoryCharacters] = useState<Array<{name: string, role: string, description: string, gender?: string}>>([]);
  const [isGeneratingMoreOptions, setIsGeneratingMoreOptions] = useState(false);
  const [sceneHistory, setSceneHistory] = useState<Scene[][]>([]);
  const [currentSceneIndex, setCurrentSceneIndex] = useState(0);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [userSettings, setUserSettings] = useState<any>(null);
  
  // First scene input mode states
  const [firstSceneMode, setFirstSceneMode] = useState<'ai' | 'write'>('ai');
  const [userSceneContent, setUserSceneContent] = useState('');
  const [writeMode, setWriteMode] = useState<'scene' | 'prompt'>('prompt');
  
  // New variant system states - now managed by SceneVariantDisplay
  // const [selectedSceneVariants, setSelectedSceneVariants] = useState<{[sceneId: number]: SceneVariant[]}>({});
  // const [currentVariantIds, setCurrentVariantIds] = useState<{[sceneId: number]: number}>({});
  // const [showVariantSelector, setShowVariantSelector] = useState<{[sceneId: number]: boolean}>({});
  const [isDeletingScenes, setIsDeletingScenes] = useState(false);
  const [selectedScenesForDeletion, setSelectedScenesForDeletion] = useState<number[]>([]);
  const [isInDeleteMode, setIsInDeleteMode] = useState(false);
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  
  // Streaming states
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingSceneNumber, setStreamingSceneNumber] = useState<number | null>(null);
  // Load streaming preference - default to true, will be updated from settings
  // Don't use localStorage in initializer to avoid hydration mismatch
  const [useStreaming, setUseStreaming] = useState(true);
  
  // Thinking/Reasoning states (for models that support reasoning)
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingContent, setThinkingContent] = useState('');
  
  // Variant regeneration streaming states
  const [streamingVariantSceneId, setStreamingVariantSceneId] = useState<number | null>(null);
  const [streamingVariantContent, setStreamingVariantContent] = useState('');
  
  // Continue scene streaming states
  const [isStreamingContinuation, setIsStreamingContinuation] = useState(false);
  const [streamingContinuation, setStreamingContinuation] = useState('');
  const [streamingContinuationSceneId, setStreamingContinuationSceneId] = useState<number | null>(null);
  
  // Scene pagination for performance
  const [displayMode, setDisplayMode] = useState<'recent' | 'all'>('recent'); // Start with recent scenes only
  
  // Debug state for mobile
  const [debugStep, setDebugStep] = useState('init');

  // Summary modal states
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [storySummary, setStorySummary] = useState<any>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [isGeneratingAISummary, setIsGeneratingAISummary] = useState(false);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [scenesToShow, setScenesToShow] = useState(5); // Show last 5 scenes initially
  const [isLoadingEarlierScenes, setIsLoadingEarlierScenes] = useState(false);
  const [isAutoLoadingScenes, setIsAutoLoadingScenes] = useState(false);
  
  // Ref for infinite scroll sentinel element
  const sentinelRef = useRef<HTMLDivElement>(null);
  
  // Chapter sidebar state
  const [isChapterSidebarOpen, setIsChapterSidebarOpen] = useState(false); // Start closed
  
  // Branch state
  const [currentBranchId, setCurrentBranchId] = useState<number | undefined>(undefined);
  const [showBranchCreationModal, setShowBranchCreationModal] = useState(false);
  const [branchCreationFromScene, setBranchCreationFromScene] = useState<number>(1);
  
  const [chapterSidebarRefreshKey, setChapterSidebarRefreshKey] = useState(0);
  const [activeChapterId, setActiveChapterId] = useState<number | null>(null); // Active chapter from backend
  const [currentChapterInfo, setCurrentChapterInfo] = useState<{id: number, number: number, title: string | null, isActive: boolean} | null>(null);
  
  // Main menu modal state
  const [showMainMenu, setShowMainMenu] = useState(false);
  
  // TTS Settings modal state
  const [showTTSSettings, setShowTTSSettings] = useState(false);
  
  // Story Settings Edit modal state
  const [showEditStoryModal, setShowEditStoryModal] = useState(false);
  
  // Character Interactions modal state
  const [showInteractionsModal, setShowInteractionsModal] = useState(false);
  
  // Entity States modal state
  const [showEntityStatesModal, setShowEntityStatesModal] = useState(false);

  // Contradictions modal state
  const [showContradictionsModal, setShowContradictionsModal] = useState(false);
  
  // Chapter wizard state
  const [showChapterWizard, setShowChapterWizard] = useState(false);
  const [activeChapter, setActiveChapter] = useState<any>(null);
  
  // Modern scene layout states
  const [sceneLayoutMode, setSceneLayoutMode] = useState<'stacked' | 'modern'>('modern');
  const [isNewSceneAdded, setIsNewSceneAdded] = useState(false);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [showChoicesDuringGeneration, setShowChoicesDuringGeneration] = useState(true);
  const [previousSceneCount, setPreviousSceneCount] = useState(0);
  
  // Global flag to prevent variant loading during operations
  const [isSceneOperationInProgress, setIsSceneOperationInProgress] = useState(false);
  
  // Context usage and timing states
  const [contextUsagePercent, setContextUsagePercent] = useState(0);
  const [lastGenerationTime, setLastGenerationTime] = useState<number | null>(null);
  const [generationStartTime, setGenerationStartTime] = useState<number | null>(null);
  const [extractionStatus, setExtractionStatus] = useState<{ status: 'extracting' | 'complete' | 'error'; message: string } | null>(null);
  // Plot progress refresh trigger - incremented after scene generation to refetch progress
  const [plotProgressRefreshTrigger, setPlotProgressRefreshTrigger] = useState(0);
  // Contradiction check state (inline post-generation check)
  const [sceneContradictions, setSceneContradictions] = useState<Record<number, Array<{
    id: number; type: string; character_name: string | null;
    previous_value: string | null; current_value: string | null;
    severity: string; scene_sequence: number;
  }>>>({});
  const [checkingContradictions, setCheckingContradictions] = useState(false);
  const [showContextWarning, setShowContextWarning] = useState(false);
  const [hasShownContextWarning, setHasShownContextWarning] = useState(false);
  const [isGeneratingChoices, setIsGeneratingChoices] = useState(false);
  const [waitingForChoicesSceneId, setWaitingForChoicesSceneId] = useState<number | null>(null);
  
  const storyContentRef = useRef<HTMLDivElement>(null);
  const variantReloadTriggerRef = useRef<number>(0);
  const manualChoiceUpdateTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const visibleSceneIdRef = useRef<number | null>(null);
  
  // AbortControllers for streaming operations
  const sceneGenerationAbortControllerRef = useRef<AbortController | null>(null);
  const variantGenerationAbortControllerRef = useRef<AbortController | null>(null);
  const continuationAbortControllerRef = useRef<AbortController | null>(null);
  
  // Apply UI settings (theme, font size, etc.)
  useUISettings(userSettings?.ui_preferences || null);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, hasHydrated]); // storyId comes via props+key (remount on change); router intentionally excluded - it can be unstable and cause unwanted reloads

  // Initialize showImages from user settings when they load
  useEffect(() => {
    if (userSettings?.ui_preferences?.show_scene_images !== undefined) {
      setShowImages(userSettings.ui_preferences.show_scene_images);
    }
  }, [userSettings?.ui_preferences?.show_scene_images]);

  // Toggle images and save to user settings
  const toggleShowImages = useCallback(async () => {
    const newValue = !showImages;
    setShowImages(newValue);
    try {
      await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          ui_preferences: { show_scene_images: newValue }
        }),
      });
    } catch (err) {
      console.error('Failed to save show_scene_images setting:', err);
    }
  }, [showImages, token]);

  const loadUserSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings.settings);
      
      // Update streaming preference from settings
      const enableStreaming = settings.settings?.generation_preferences?.enable_streaming !== false;
      setUseStreaming(enableStreaming);
      
      // Also save to localStorage as fallback (client-side only)
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem('enable_streaming', String(enableStreaming));
        } catch (e) {
          // Ignore localStorage errors (e.g., in private browsing)
          console.warn('Failed to save streaming preference to localStorage:', e);
        }
      }
    } catch (err) {
      console.error('Failed to load user settings:', err);
      // Fallback to localStorage if settings load fails (client-side only)
      if (typeof window !== 'undefined') {
        try {
          const saved = localStorage.getItem('enable_streaming');
          if (saved !== null) {
            setUseStreaming(saved === 'true');
          }
        } catch (e) {
          // Ignore localStorage errors
        }
      }
    }
  };
  
  // Sync streaming preference when userSettings change
  useEffect(() => {
    if (userSettings?.generation_preferences?.enable_streaming !== undefined) {
      const enableStreaming = userSettings.generation_preferences.enable_streaming !== false;
      setUseStreaming(enableStreaming);
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem('enable_streaming', String(enableStreaming));
        } catch (e) {
          // Ignore localStorage errors
          console.warn('Failed to save streaming preference to localStorage:', e);
        }
      }
    }
  }, [userSettings?.generation_preferences?.enable_streaming]);
  
  // Listen for settings changes from SettingsModal
  useEffect(() => {
    const handleSettingsChanged = () => {
      loadUserSettings();
    };
    
    window.addEventListener('kahaniSettingsChanged', handleSettingsChanged);
    return () => {
      window.removeEventListener('kahaniSettingsChanged', handleSettingsChanged);
    };
  }, []);

  // Set up story actions for the PersistentBanner menu
  useEffect(() => {
    if (story) {
      setStoryActions({
        onChapters: () => setIsChapterSidebarOpen(true),
        onAddCharacter: () => setShowCharacterQuickAdd(true),
        onEditCharacterVoices: () => setShowCharacterVoiceEditor(true),
        onEditCharacterRoles: () => setShowCharacterRoleEditor(true),
        onManageStoryCharacters: () => setShowStoryCharacterManager(true),
        onViewAllCharacters: () => router.push('/characters'),
        onDirectorMode: () => setDirectorMode(!directorMode),
        onDeleteMode: () => setIsInDeleteMode(!isInDeleteMode),
        onEditStorySettings: () => setShowEditStoryModal(true),
        onShowInteractions: () => setShowInteractionsModal(true),
        onShowEntityStates: () => setShowEntityStatesModal(true),
        onShowContradictions: () => setShowContradictionsModal(true),
        directorModeActive: directorMode,
        deleteModeActive: isInDeleteMode,
        showImagesActive: showImages,
        onToggleImages: toggleShowImages,
        onOpenGallery: () => setShowGallery(true),
        showCharacterBanner: showCharacterBanner,
        onDiscoverCharacters: () => setShowCharacterWizard(true),
        // Generation/extraction status
        lastGenerationTime,
        generationStartTime,
        extractionStatus,
        // Story title and content rating for banner display
        storyTitle: story.title,
        contentRating: (story.content_rating || 'sfw') as 'sfw' | 'nsfw',
        // Branch-related props
        storyId: storyId,
        currentBranchId: currentBranchId,
        currentSceneSequence: story?.scenes?.length || 1,
        // Branch callbacks - use ref to access loadStory
        onBranchChange: async (branchId: number) => {
          setCurrentBranchId(branchId);
          if (loadStoryRef.current) {
            // Pass branchId directly to avoid React state timing issues
            await loadStoryRef.current(true, false, branchId);
          }
        },
        onBranchCreated: (branchId?: number) => {
          if (loadStoryRef.current) {
            // Pass branchId directly if provided
            loadStoryRef.current(true, false, branchId);
          }
        },
      });
    } else {
      setStoryActions(undefined);
    }
  }, [story, directorMode, isInDeleteMode, showImages, toggleShowImages, showCharacterBanner, lastGenerationTime, generationStartTime, extractionStatus, setStoryActions, router, storyId, currentBranchId]);

  // Auto-scroll to bottom when streaming starts
  useEffect(() => {
    if (isStreaming && streamingContent) {
      // Scroll to bottom smoothly when streaming content appears
      setTimeout(() => {
        if (storyContentRef.current) {
          storyContentRef.current.scrollTo({
            top: storyContentRef.current.scrollHeight,
            behavior: 'instant'
          });
        }
      }, 100);
    }
  }, [isStreaming, streamingContent]);

  // Show context warning popup when reaching 80% (only if user has enabled the setting)
  useEffect(() => {
    // Check if user has enabled the alert setting (default to true if not set)
    const alertEnabled = userSettings?.generation_preferences?.alert_on_high_context !== false;
    
    if (alertEnabled && contextUsagePercent >= 80 && !hasShownContextWarning) {
      setShowContextWarning(true);
      setHasShownContextWarning(true);
    }
  }, [contextUsagePercent, hasShownContextWarning, userSettings?.generation_preferences?.alert_on_high_context]);

  // Preserve scroll position on resize/orientation change
  // Disabled: This was causing scroll jumps on mobile when address bar hides/shows
  // The overscroll-behavior-y: contain on the container should handle most cases
  /*
  useEffect(() => {
    const container = storyContentRef.current;
    if (!container) return;

    // Function to find which scene is currently at the top of viewport
    const getVisibleSceneId = () => {
      const sceneElements = container.querySelectorAll('[data-scene-id]');
      for (const element of sceneElements) {
        const rect = element.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        // Scene is visible if its top is within the container viewport
        if (rect.top >= containerRect.top && rect.top <= containerRect.bottom) {
          return parseInt(element.getAttribute('data-scene-id') || '0');
        }
      }
      return null;
    };

    // Save visible scene before resize
    const handleResizeStart = () => {
      visibleSceneIdRef.current = getVisibleSceneId();
    };

    // Restore visible scene after resize
    const handleResizeEnd = () => {
      if (visibleSceneIdRef.current) {
        const element = container.querySelector(
          `[data-scene-id="${visibleSceneIdRef.current}"]`
        );
        if (element) {
          element.scrollIntoView({ behavior: 'instant', block: 'start' });
        }
      }
    };

    // Debounce resize handling
    let resizeTimeout: NodeJS.Timeout;
    const handleResize = () => {
      if (!resizeTimeout) handleResizeStart();
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(handleResizeEnd, 150);
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      clearTimeout(resizeTimeout);
    };
  }, [story?.scenes]);
  */

  // Load chapter info when active chapter changes
  useEffect(() => {
    const loadChapterInfo = async () => {
      try {
        if (activeChapterId) {
          // Use already-fetched activeChapter if it matches (avoids redundant API call)
          if (activeChapter && activeChapter.id === activeChapterId) {
            setCurrentChapterInfo({
              id: activeChapter.id,
              number: activeChapter.chapter_number,
              title: activeChapter.title,
              isActive: activeChapter.status === 'active'
            });
            return;
          }
          // Fallback: fetch if we don't have it in state
          const chapter = await apiClient.getChapter(storyId, activeChapterId);
          setCurrentChapterInfo({
            id: chapter.id,
            number: chapter.chapter_number,
            title: chapter.title,
            isActive: chapter.status === 'active'
          });
        } else {
          // Try to find active chapter from chapters list
          const chapters = await apiClient.getChapters(storyId);
          const active = chapters.find((ch: any) => ch.status === 'active');
          if (active) {
            setActiveChapterId(active.id);
            setCurrentChapterInfo({
              id: active.id,
              number: active.chapter_number,
              title: active.title,
              isActive: true
            });
          }
        }
      } catch (err) {
        console.error('Failed to load chapter info:', err);
      }
    };
    loadChapterInfo();
  }, [activeChapterId, storyId, activeChapter]);

  // Get scenes to display based on current mode and active chapter
  const getScenesToDisplay = (): Scene[] => {
    if (!story?.scenes || story.scenes.length === 0) return [];

    // Filter by active chapter - always show only active chapter's scenes
    let filteredScenes = story.scenes;
    if (activeChapterId !== null) {
      filteredScenes = story.scenes.filter(scene => scene.chapter_id === activeChapterId);
    }
    
    if (displayMode === 'all') {
      return filteredScenes.sort((a, b) => a.sequence_number - b.sequence_number);
    }
    
    // For 'recent' mode, show only the last N scenes
    const sortedScenes = [...filteredScenes].sort((a, b) => a.sequence_number - b.sequence_number);
    const totalScenes = sortedScenes.length;
    const startIndex = Math.max(0, totalScenes - scenesToShow);
    const displayedScenes = sortedScenes.slice(startIndex);
    
    // Debug log to verify only last N scenes are returned
    if (displayedScenes.length !== scenesToShow && displayedScenes.length < totalScenes) {
      }
    
    return displayedScenes;
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

  // Automatically load more scenes when scrolling to top (infinite scroll)
  const loadMoreScenesAutomatically = useCallback(() => {
    // Prevent duplicate loads
    if (isAutoLoadingScenes) {
      return;
    }
    
    // Only load if in 'recent' mode and there are more scenes to load
    if (displayMode !== 'recent' || !story?.scenes) {
      return;
    }
    
    // Get filtered scenes count (accounting for chapter filtering)
    let filteredScenes = story.scenes;
    if (activeChapterId !== null) {
      filteredScenes = story.scenes.filter(scene => scene.chapter_id === activeChapterId);
    }
    const totalScenes = filteredScenes.length;
    
    if (scenesToShow >= totalScenes) {
      return;
    }
    
    setIsAutoLoadingScenes(true);
    
    // Save current scroll position before loading
    const container = storyContentRef.current;
    if (!container) {
      setIsAutoLoadingScenes(false);
      return;
    }
    
    const scrollTop = container.scrollTop;
    const scrollHeight = container.scrollHeight;
    const firstVisibleElement = container.querySelector('[data-scene-id]') as HTMLElement;
    const firstVisibleSceneId = firstVisibleElement?.getAttribute('data-scene-id');
    
    // Load 10 more scenes (or all remaining if less than 10)
    const newScenesToShow = Math.min(scenesToShow + 10, totalScenes);
    setScenesToShow(newScenesToShow);
    
    // Restore scroll position after DOM update
    // Use multiple RAFs to ensure React has rendered the new scenes
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (container) {
            // Try to restore position relative to the first visible scene
            if (firstVisibleSceneId && firstVisibleElement) {
              const newFirstVisibleElement = container.querySelector(`[data-scene-id="${firstVisibleSceneId}"]`) as HTMLElement;
              if (newFirstVisibleElement) {
                // Calculate offset from top of container
                const containerRect = container.getBoundingClientRect();
                const elementRect = newFirstVisibleElement.getBoundingClientRect();
                const offsetFromTop = elementRect.top - containerRect.top + container.scrollTop;
                container.scrollTop = offsetFromTop;
              } else {
                // Fallback: maintain scroll position by height difference
                const newScrollHeight = container.scrollHeight;
                const heightDifference = newScrollHeight - scrollHeight;
                container.scrollTop = scrollTop + heightDifference;
              }
            } else {
              // Fallback: maintain scroll position by height difference
              const newScrollHeight = container.scrollHeight;
              const heightDifference = newScrollHeight - scrollHeight;
              container.scrollTop = scrollTop + heightDifference;
            }
          }
          setIsAutoLoadingScenes(false);
        });
      });
    });
  }, [displayMode, story?.scenes, scenesToShow, isAutoLoadingScenes, activeChapterId]);

  // Targeted story refresh that doesn't cause scrolling
  const refreshStoryContent = async () => {
    try {
      const storyData = await apiClient.getStory(
        storyId,
        currentBranchId || undefined,
        activeChapterId || undefined
      );
      setStory(storyData);
      if (storyData.current_branch_id) {
        setCurrentBranchId(storyData.current_branch_id);
      }
    } catch (err) {
      console.error('Failed to refresh story:', err);
    }
  };

  // Targeted variant update - updates a specific scene's variant without full refresh
  const handleVariantChanged = (sceneId: number, newVariant?: { id: number; content: string }) => {
    if (!story || !newVariant) return;

    // Update only the specific scene's content and variant_id locally
    const updatedStory = {
      ...story,
      scenes: story.scenes.map((scene: Scene) =>
        scene.id === sceneId
          ? { ...scene, content: newVariant.content, variant_id: newVariant.id }
          : scene
      )
    };
    setStory(updatedStory);
  };

  // Refresh choices for a specific scene without reloading the entire story
  const refreshSceneChoices = async (sceneId: number) => {
    try {
      // Get the story for the current chapter to get updated choices for the scene
      const storyData = await apiClient.getStory(
        storyId,
        currentBranchId || undefined,
        activeChapterId || undefined
      );
      
      // Find the scene in the new data and update only its choices in state
      if (story && storyData.scenes) {
        const updatedScene = storyData.scenes.find((s: Scene) => s.id === sceneId);
        if (updatedScene) {
          // Update only the choices for this scene, preserve everything else
          const updatedStory = {
            ...story,
            scenes: story.scenes.map((s: Scene) => 
              s.id === sceneId 
                ? { ...s, choices: updatedScene.choices || [] }
                : s
            )
          };
          setStory(updatedStory);
        }
      }
    } catch (err) {
      console.error('Failed to refresh scene choices:', err);
    }
  };

  // --- iOS Background Tab Recovery ---
  // When iOS Safari backgrounds a tab during scene generation, WebKit kills the
  // SSE stream. The backend continues generating and saves to DB. This recovery
  // mechanism detects the return to foreground and retrieves the completed scene.
  const handleRecovery = useCallback(async () => {
    if (!story || !isStreaming) return;
    try {
      const result = await apiClient.recoverGeneration(storyId);
      if (result.status === 'completed' && result.scene_id && result.content) {
        // Scene completed in background — add it to state
        const nextSceneNumber = (story.scenes?.length || 0) + 1;
        const recoveredChoices = (result.choices || []).map((c: any, i: number) => ({
          id: -(i + 1), // Temporary negative ID, will be synced from backend on refresh
          text: c.text || c,
          order: c.order || i + 1,
        }));
        const newScene: Scene = {
          id: result.scene_id,
          sequence_number: nextSceneNumber,
          title: `Scene ${nextSceneNumber}`,
          content: result.content,
          location: '',
          characters_present: [],
          choices: recoveredChoices,
          variant_id: result.variant_id,
          has_multiple_variants: false,
          total_variants: 1,
          chapter_id: result.chapter_id ?? activeChapterId ?? undefined,
        };
        const updatedStory = { ...story, scenes: [...story.scenes, newScene] };
        flushSync(() => { setStory(updatedStory); });
        setStreamingContent('');
        setStreamingSceneNumber(null);
        setIsStreaming(false);
        setSelectedChoice(null);
        setShowChoicesDuringGeneration(true);
        setGenerationStartTime(null);
        setExtractionStatus(null);
        setIsSceneOperationInProgress(false);
        sceneGenerationAbortControllerRef.current = null;
        // Auto-play TTS if provided
        if (result.auto_play && result.auto_play.session_id) {
          globalTTS.connectToSession(result.auto_play.session_id, result.auto_play.scene_id);
        }
        // Refresh in background
        setTimeout(() => refreshStoryContent(), 500);
        setChapterSidebarRefreshKey(prev => prev + 1);
        console.log('[RECOVERY] Scene recovered after background tab kill');
      } else if (result.status === 'generating') {
        // Still running — poll again in 2s
        console.log('[RECOVERY] Generation still in progress, polling...');
        setTimeout(() => handleRecovery(), 2000);
      } else if (result.status === 'error') {
        // Generation failed in background
        setError(result.error || 'Generation failed while in background');
        setStreamingContent('');
        setStreamingSceneNumber(null);
        setIsStreaming(false);
        setGenerationStartTime(null);
        setExtractionStatus(null);
        setSelectedChoice(null);
        setShowChoicesDuringGeneration(true);
        setIsSceneOperationInProgress(false);
        sceneGenerationAbortControllerRef.current = null;
      }
      // status === 'none' — no active generation, stream probably completed normally
    } catch (err) {
      console.warn('[RECOVERY] Recovery check failed:', err);
    }
  }, [story, storyId, isStreaming, activeChapterId]);

  // Listen for tab returning to foreground during streaming
  useEffect(() => {
    if (!isStreaming) return;
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && isStreaming) {
        // Wait briefly to let the stream error propagate naturally first
        setTimeout(() => {
          // If still streaming after delay, the stream may be dead — try recovery
          if (isStreaming) {
            handleRecovery();
          }
        }, 500);
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [isStreaming, handleRecovery]);

  // Track scene count to detect new scenes
  useEffect(() => {
    if (story?.scenes) {
      setPreviousSceneCount(story.scenes.length);
    }
  }, [story?.scenes?.length]);

  // Infinite scroll: detect when user scrolls to top using scroll listener
  useEffect(() => {
    let cleanupFunction: (() => void) | null = null;
    let retryTimeout: NodeJS.Timeout;

    // Wait for container to be available (retry mechanism)
    const setupScrollListener = () => {
      const scrollContainer = storyContentRef.current;
      if (!scrollContainer) {
        // Retry after a short delay
        retryTimeout = setTimeout(setupScrollListener, 100);
        return;
      }

      // Only enable infinite scroll in 'recent' mode
      if (displayMode !== 'recent') {
        return;
      }

      // Get filtered scenes count to check if there are more to load
      let filteredScenes = story?.scenes || [];
      if (activeChapterId !== null && story?.scenes) {
        filteredScenes = story.scenes.filter(scene => scene.chapter_id === activeChapterId);
      }
      const hasMoreScenes = filteredScenes.length > scenesToShow;

      if (!hasMoreScenes) {
        return;
      }

      let scrollTimeout: NodeJS.Timeout;
      let lastScrollTop = scrollContainer.scrollTop;
      let lastWindowScroll = typeof window !== 'undefined' ? window.pageYOffset : 0;
      let hasTriggered = false; // Prevent multiple rapid triggers
      let triggerCooldown: NodeJS.Timeout;
      let observerSetupTimeout: NodeJS.Timeout;
      let isInitialLoad = true; // Track if this is the initial page load
      
      // Mark initial load as complete after a delay to prevent immediate triggering
      setTimeout(() => {
        isInitialLoad = false;
      }, 2000); // 2 second grace period after page load

    // Scroll event listener for container
    const handleContainerScroll = () => {
      // Clear previous timeout
      clearTimeout(scrollTimeout);
      
      // Throttle scroll events
      scrollTimeout = setTimeout(() => {
        // Don't trigger on initial load - wait for user to actually scroll
        if (isAutoLoadingScenes || hasTriggered || isInitialLoad) {
          if (isInitialLoad) {
          }
          return;
        }

        const currentScrollTop = scrollContainer.scrollTop;
        const scrollHeight = scrollContainer.scrollHeight;
        const clientHeight = scrollContainer.clientHeight;
        const scrollDirection = currentScrollTop < lastScrollTop ? 'up' : 'down';
        
        // Mark that user has scrolled, so we can enable infinite scroll
        if (Math.abs(currentScrollTop - lastScrollTop) > 10) {
          isInitialLoad = false;
        }
        
        lastScrollTop = currentScrollTop;

        // Log every scroll for debugging
        // Only trigger on scroll up AND when actually near the top
        // This prevents false triggers from elastic bounce at bottom
        if (scrollDirection === 'up') {
          // Calculate distance from top
          const distanceFromTop = currentScrollTop;
          
          // Calculate scroll percentage (0% = top, 100% = bottom)
          const maxScroll = Math.max(1, scrollHeight - clientHeight);
          const scrollPercentage = maxScroll > 0 ? (currentScrollTop / maxScroll) * 100 : 0;
          
          // Only trigger when ACTUALLY near the top (not just scrolling up direction)
          // This prevents false triggers from elastic bounce at bottom
          const isActuallyNearTop = currentScrollTop < 600;
          
          // Trigger only when near top: within 600px of top OR in top 20% OR scrollTop is very small
          const shouldTrigger = isActuallyNearTop && (
            distanceFromTop < 600 || 
            scrollPercentage < 20 || 
            currentScrollTop < 50
          );
          
          if (shouldTrigger) {
            hasTriggered = true;
            loadMoreScenesAutomatically();
            
            // Reset trigger flag after cooldown
            clearTimeout(triggerCooldown);
            triggerCooldown = setTimeout(() => {
              hasTriggered = false;
            }, 2000);
          }
        }
      }, 50); // Reduced throttle to 50ms for more responsive detection
    };

    // Also listen to window scroll in case that's what's actually scrolling
    const handleWindowScroll = () => {
      if (isAutoLoadingScenes || hasTriggered || isInitialLoad) {
        return;
      }

      const currentWindowScroll = typeof window !== 'undefined' ? window.pageYOffset : 0;
      const scrollDirection = currentWindowScroll < lastWindowScroll ? 'up' : 'down';
      
      // Mark that user has scrolled
      if (Math.abs(currentWindowScroll - lastWindowScroll) > 10) {
        isInitialLoad = false;
      }
      
      lastWindowScroll = currentWindowScroll;

      // Only trigger when ACTUALLY near the top of the page (not just scrolling up)
      // This prevents false triggers from elastic bounce at bottom
      if (scrollDirection === 'up' && currentWindowScroll < 200) {
        hasTriggered = true;
        loadMoreScenesAutomatically();
        clearTimeout(triggerCooldown);
        triggerCooldown = setTimeout(() => {
          hasTriggered = false;
        }, 2000);
      }
    };

    // Also set up IntersectionObserver as secondary method
    let observer: IntersectionObserver | null = null;
    
    // Wait for sentinel to be rendered
    const setupObserver = () => {
      const sentinel = sentinelRef.current;
      if (!sentinel || observer) return;

      observer = new IntersectionObserver(
        (entries) => {
          const entry = entries[0];
          // Don't trigger on initial load - wait for user to actually scroll
          if (entry.isIntersecting && !isAutoLoadingScenes && !hasTriggered && !isInitialLoad) {
            hasTriggered = true;
            loadMoreScenesAutomatically();
            clearTimeout(triggerCooldown);
            triggerCooldown = setTimeout(() => {
              hasTriggered = false;
            }, 1500);
          } else if (entry.isIntersecting && isInitialLoad) {
          }
        },
        {
          root: scrollContainer,
          rootMargin: '400px 0px',
          threshold: [0, 0.1, 0.5, 1.0],
        }
      );

      observer.observe(sentinel);
    };

    // Try to set up observer immediately, then retry after a short delay
    setupObserver();
    observerSetupTimeout = setTimeout(setupObserver, 200);

    // Add listeners to both container and window
    scrollContainer.addEventListener('scroll', handleContainerScroll, { passive: true });
    
    // Also listen to window scroll as fallback
    if (typeof window !== 'undefined') {
      window.addEventListener('scroll', handleWindowScroll, { passive: true });
    }

    // Test if scroll events work at all
    setTimeout(() => {
      }, 1000);

      cleanupFunction = () => {
        clearTimeout(scrollTimeout);
        clearTimeout(triggerCooldown);
        clearTimeout(observerSetupTimeout);
        scrollContainer.removeEventListener('scroll', handleContainerScroll);
        if (typeof window !== 'undefined') {
          window.removeEventListener('scroll', handleWindowScroll);
        }
        if (observer) {
          observer.disconnect();
        }
      };
    };

    // Start setup
    setupScrollListener();

    // Return cleanup function
    return () => {
      clearTimeout(retryTimeout);
      if (cleanupFunction) {
        cleanupFunction();
      }
    };
  }, [displayMode, loadMoreScenesAutomatically, isAutoLoadingScenes, story?.scenes, scenesToShow, activeChapterId]);

  const loadStory = async (scrollToLastScene = true, scrollToNewScene = false, overrideBranchId?: number, overrideChapterId?: number) => {
    try {
      console.log('[DEBUG] loadStory: Starting');
      setDebugStep('1-start');
      setIsLoading(true);

      // Use overrideBranchId if provided (for immediate branch switches), otherwise use currentBranchId
      const branchIdToUse = overrideBranchId ?? currentBranchId;

      // Determine chapter ID to use for filtering
      let chapterIdToUse: number | undefined = overrideChapterId;
      let activeChapterData: any = null;

      // Check if chapter setup is needed
      const setupChapter = searchParams?.get('setup_chapter') === 'true';

      // If no override chapter ID, fetch the active chapter first
      if (!chapterIdToUse) {
        try {
          setDebugStep('2-fetchChapter');
          console.log('[DEBUG] loadStory: Fetching active chapter');
          activeChapterData = await apiClient.getActiveChapter(storyId);
          setDebugStep('3-gotChapter:' + activeChapterData?.id);
          console.log('[DEBUG] loadStory: Got active chapter', activeChapterData?.id);
          setActiveChapter(activeChapterData);
          setActiveChapterId(activeChapterData.id);
          chapterIdToUse = activeChapterData.id;
        } catch (err: any) {
          // No active chapter found - this is expected for new stories
          const is404Error = err?.status === 404 ||
                            (err instanceof Error && (err.message.includes('404') || err.message.includes('No active chapter')));

          if (is404Error) {
            setActiveChapter(null);
            setActiveChapterId(null);
            // Show chapter wizard for new stories or when no active chapter exists
            setShowChapterWizard(true);
            // Don't log this as an error - it's expected behavior for new stories
          } else {
            // Only log unexpected errors
            console.error('Failed to load active chapter:', err);
          }
        }
      } else {
        // Explicit chapter switch - fetch and set the full chapter object + ID
        setActiveChapterId(chapterIdToUse);
        try {
          activeChapterData = await apiClient.getChapter(storyId, chapterIdToUse);
          setActiveChapter(activeChapterData);
        } catch (err) {
          console.warn('Failed to fetch switched chapter details:', err);
        }
      }

      // Fetch story and context status in parallel (they don't depend on each other)
      setDebugStep('4-fetch');
      console.log('[DEBUG] loadStory: Fetching story', storyId, branchIdToUse, chapterIdToUse);
      const [storyData] = await Promise.all([
        apiClient.getStory(storyId, branchIdToUse || undefined, chapterIdToUse),
        chapterIdToUse ? loadContextStatus(chapterIdToUse) : Promise.resolve()
      ]);
      setDebugStep('5-got:' + (storyData?.scenes?.length || 0));
      console.log('[DEBUG] loadStory: Got story data, scenes:', storyData?.scenes?.length);
      setStory(storyData);
      setDebugStep('6-setState');
      console.log('[DEBUG] loadStory: Set story state');

      // Set current branch ID from story data (only if not already set by user selection or override)
      if (storyData.current_branch_id && !branchIdToUse) {
        setCurrentBranchId(storyData.current_branch_id);
      }

      // Handle chapter wizard display if we fetched the active chapter
      if (activeChapterData) {
        // Always show wizard when coming from story creation
        if (setupChapter) {
          setShowChapterWizard(true);
        } else if (!storyData.scenes || storyData.scenes.length === 0) {
          // For existing stories without scenes, check if setup is needed
          const needsSetup = !activeChapterData.characters ||
                            activeChapterData.characters.length === 0 ||
                            !activeChapterData.location_name;

          if (needsSetup) {
            setShowChapterWizard(true);
          }
        }
      }

      // Helper function to scroll to a scene element within the container
      const scrollToScene = (container: HTMLElement, element: HTMLElement) => {
        // Calculate scroll position to bring element to top of container
        const containerRect = container.getBoundingClientRect();
        const elementRect = element.getBoundingClientRect();
        const relativeTop = elementRect.top - containerRect.top;
        const scrollTop = container.scrollTop + relativeTop;

        container.scrollTo({ top: scrollTop, behavior: 'instant' });
      };

      // Scroll to bottom only on initial page load OR when explicitly requested for new scenes
      if ((scrollToLastScene || scrollToNewScene) && storyData.scenes && storyData.scenes.length > 0) {
        // Wait for React to render the scenes, then scroll within the container
        // Use multiple timeouts to ensure DOM is fully updated
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setTimeout(() => {
              const container = storyContentRef.current;
              if (!container) {
                return;
              }

              // Get the last scene that will actually be displayed (based on getScenesToDisplay logic)
              // This matches the logic in getScenesToDisplay()
              let filteredScenes = storyData.scenes;
              if (activeChapterId !== null) {
                filteredScenes = storyData.scenes.filter((s: Scene) => s.chapter_id === activeChapterId);
              }
              
              // In 'recent' mode, only the last N scenes are displayed
              const sortedScenes = [...filteredScenes].sort((a, b) => a.sequence_number - b.sequence_number);
              const totalScenes = sortedScenes.length;
              const startIndex = Math.max(0, totalScenes - scenesToShow);
              const displayedScenes = sortedScenes.slice(startIndex);
              const targetScene = displayedScenes[displayedScenes.length - 1]; // Last scene in displayed list
              
              // Guard: if no scenes, just scroll to bottom
              if (!targetScene) {
                container.scrollTo({ top: container.scrollHeight, behavior: 'instant' });
                return;
              }
              
              // Try to find the scene element - wait a bit more if not found
              let targetSceneElement = container.querySelector(`[data-scene-id="${targetScene.id}"]`) as HTMLElement;
              
              if (!targetSceneElement) {
                // Retry after a short delay
                setTimeout(() => {
                  targetSceneElement = container.querySelector(`[data-scene-id="${targetScene.id}"]`) as HTMLElement;
                  if (targetSceneElement) {
                    scrollToScene(container, targetSceneElement);
                  } else {
                    // Final fallback: scroll container to bottom
                    container.scrollTo({ top: container.scrollHeight, behavior: 'instant' });
                  }
                }, 200);
              } else {
                scrollToScene(container, targetSceneElement);
              }
            }, 200);
          });
        });
      }

    } catch (err) {
      console.error('[DEBUG] loadStory: ERROR', err);
      setError(err instanceof Error ? err.message : 'Failed to load story');
    } finally {
      console.log('[DEBUG] loadStory: Finally block - setting isLoading false');
      setIsLoading(false);
    }
  };

  // Store loadStory in ref so branch callbacks can access it
  loadStoryRef.current = loadStory;

  // Handle branch change - scroll to last scene of new branch
  const handleBranchChange = async (branchId: number) => {
    setCurrentBranchId(branchId);
    // Pass branchId directly to loadStory to avoid React state timing issues
    await loadStory(true, false, branchId);  // scrollToLastScene=true to show last scene of new branch
  };

  const loadContextStatus = async (chapterIdParam?: number) => {
    try {
      const chapterId = chapterIdParam ?? activeChapterId;
      if (chapterId) {
        const contextStatus = await apiClient.getChapterContextStatus(storyId, chapterId);
        setContextUsagePercent(contextStatus.percentage_used);
      } else {
        // Fallback: fetch active chapter if no ID available
        const activeChapter = await apiClient.getActiveChapter(storyId);
        if (activeChapter) {
          const contextStatus = await apiClient.getChapterContextStatus(storyId, activeChapter.id);
          setContextUsagePercent(contextStatus.percentage_used);
        }
      }
    } catch (err) {
      console.error('Failed to load context status:', err);
    }
  };

  const handleViewSummary = async () => {
    setLoadingSummary(true);
    setShowSummaryModal(true);
    
    try {
      // Load active chapter to get auto_summary
      const activeChapter = await apiClient.getActiveChapter(storyId);
      
      if (activeChapter && activeChapter.auto_summary) {
        // Set the chapter's auto_summary as the AI summary
        setAiSummary(activeChapter.auto_summary);
        // Don't set storySummary - we'll only show the chapter summary in aiSummary
        setStorySummary(null);
      } else {
        // Fallback to old summary endpoint if no chapter summary exists
        const response = await fetch(`${await getApiBaseUrl()}/api/stories/${storyId}/summary`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        
        if (response.ok) {
          const summaryData = await response.json();
          setStorySummary(summaryData);
        } else {
          console.error('Failed to load summary');
          setStorySummary({ error: 'Failed to load summary' });
        }
      }
    } catch (error) {
      console.error('Error loading summary:', error);
      setStorySummary({ error: 'Error loading summary' });
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleCloseStory = () => {
    router.push('/dashboard');
  };

  const handleGenerateAISummary = async () => {
    setIsGeneratingAISummary(true);
    setAiSummary(null);
    
    try {
      // First try to get active chapter and generate its summary
      const activeChapter = await apiClient.getActiveChapter(storyId);
      
      if (activeChapter) {
        const summary = await apiClient.generateChapterSummary(storyId, activeChapter.id);
        
        if (summary && summary.auto_summary) {
          setAiSummary(summary.auto_summary);
          return;
        }
      }
      
      // Fallback to old regenerate-summary endpoint
      const url = `${await getApiBaseUrl()}/api/stories/${storyId}/regenerate-summary`;
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      
      
      if (response.ok) {
        const summaryData = await response.json();
        setAiSummary(summaryData.summary);
      } else {
        const errorText = await response.text();
        console.error('[SUMMARY] Failed to generate AI summary:', response.status, errorText);
        setAiSummary('Failed to generate AI summary. Please try again.');
      }
    } catch (error) {
      console.error('[SUMMARY] Error generating AI summary:', error);
      setAiSummary('Error generating AI summary. Please try again.');
    } finally {
      setIsGeneratingAISummary(false);
    }
  };

  const generateNewSceneStreaming = async (prompt?: string, isConcluding?: boolean) => {
    if (!story) return;

    setError('');
    setIsStreaming(true);  // Always show loading state
    setIsSceneOperationInProgress(true); // Block variant loading operations
    setIsGeneratingChoices(false);
    setWaitingForChoicesSceneId(null);
    setStreamingContent('');
    // Clear thinking state for new generation
    setIsThinking(false);
    setThinkingContent('');
    
    // Start timing
    const startTime = Date.now();
    setGenerationStartTime(startTime);
    
    // Calculate the next scene number
    const nextSceneNumber = (story.scenes?.length || 0) + 1;
    setStreamingSceneNumber(nextSceneNumber);
    
    // Accumulate content locally so callback can access it
    let accumulatedContent = '';
    // Flag to prevent catch block from showing error while async recovery is in progress
    let recoveryInProgress = false;

    try {
      // Determine content mode and user content based on first scene mode
      let userContent: string | undefined;
      let contentMode: 'ai_generate' | 'user_scene' | 'user_prompt' = 'ai_generate';
      
      if (firstSceneMode === 'write' && userSceneContent.trim()) {
        if (writeMode === 'prompt') {
          contentMode = 'user_prompt';
          userContent = userSceneContent.trim();
        } else {
          contentMode = 'user_scene';
          userContent = userSceneContent.trim();
        }
      }
      
      // Detect iOS Safari
      const isIOS = typeof window !== 'undefined' && 
        (/iPad|iPhone|iPod/.test(navigator.userAgent) || 
         (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
      
      // For iOS, batch chunks to prevent too many synchronous renders
      let iosChunkBuffer = '';
      let iosFlushTimer: ReturnType<typeof setTimeout> | null = null;
      
      const flushIOSChunks = () => {
        if (iosChunkBuffer) {
          flushSync(() => {
            setStreamingContent(prev => prev + iosChunkBuffer);
          });
          iosChunkBuffer = '';
        }
        if (iosFlushTimer) {
          clearTimeout(iosFlushTimer);
          iosFlushTimer = null;
        }
      };
      
      // Create AbortController for this streaming operation
      const abortController = new AbortController();
      sceneGenerationAbortControllerRef.current = abortController;
      
      await apiClient.generateSceneStreaming(
        story.id,
        prompt || customPrompt,
        userContent,
        contentMode,
        // onChunk
        (chunk: string) => {
          accumulatedContent += chunk;
          if (isIOS) {
            // Buffer chunks and flush frequently on iOS (every 50ms max, or immediately if buffer gets large)
            iosChunkBuffer += chunk;
            
            // Flush immediately if buffer is getting large (more than 200 chars)
            if (iosChunkBuffer.length > 200) {
              flushIOSChunks();
            } else if (!iosFlushTimer) {
              // Schedule flush every 50ms for responsive updates
              iosFlushTimer = setTimeout(() => {
                flushIOSChunks();
              }, 50);
            }
          } else {
            setStreamingContent(prev => prev + chunk);
          }
        },
        // onComplete
        async (sceneId: number, variantId: number, choices: any[], autoPlay?: { enabled: boolean; session_id: string; scene_id: number }, multiGen?: { isMultiGeneration: boolean; totalVariants: number; variants: any[] }, chapterId?: number | null) => {
          
          // Flush any remaining buffered chunks on iOS
          if (isIOS) {
            flushIOSChunks();
          }
          
          // End timing
          const endTime = Date.now();
          const generationTime = (endTime - startTime) / 1000; // Convert to seconds
          setLastGenerationTime(generationTime);
          setGenerationStartTime(null);
          // Clear extraction status if still showing
          setExtractionStatus(null);

          // AUTO-PLAY TTS if enabled and session provided
          // This is a fallback in case onAutoPlayReady wasn't called
          // (Global TTS will ignore duplicate connections to same session)
          if (autoPlay && autoPlay.session_id) {
            globalTTS.connectToSession(autoPlay.session_id, autoPlay.scene_id);
          }

          // ADD the new scene to the story FIRST, before clearing streaming
          // This ensures seamless visual transition - scene appears in list before streaming view hides
          const isMultiGen = multiGen?.isMultiGeneration && multiGen.totalVariants > 1;

          if (story && accumulatedContent) {
            const newScene = {
              id: sceneId,
              sequence_number: nextSceneNumber,
              title: `Scene ${nextSceneNumber}`,
              content: isMultiGen && multiGen.variants[0] ? multiGen.variants[0].content : accumulatedContent,
              location: '',
              characters_present: [],
              choices: isMultiGen && multiGen.variants[0]?.choices
                ? multiGen.variants[0].choices.map((c: any) => c.text || c.choice_text || c)
                : (choices || []),
              variant_id: variantId,
              has_multiple_variants: isMultiGen || false,
              total_variants: isMultiGen ? multiGen.totalVariants : 1,
              chapter_id: chapterId ?? activeChapterId ?? undefined
            };

            const updatedStory = {
              ...story,
              scenes: [...story.scenes, newScene]
            };

            // Use flushSync to ensure scene is rendered before clearing streaming state
            flushSync(() => {
              setStory(updatedStory);
            });

            // NOW clear streaming state - scene is already visible in the regular list
            setStreamingContent('');
            setStreamingSceneNumber(null);
            setIsStreaming(false);
            setSelectedChoice(null);
            setShowChoicesDuringGeneration(true);
            
            // Show toast for multi-generation
            if (isMultiGen) {
              console.log(`[MULTI-GEN] Generated ${multiGen.totalVariants} variants - swipe to explore`);
            }

            // Trigger plot progress refresh after a delay to allow background extraction to complete
            // Plot extraction runs asynchronously after scene generation, so we wait before refreshing
            setTimeout(() => {
              setPlotProgressRefreshTrigger(prev => prev + 1);
            }, 8000); // 8 seconds should be enough for extraction to complete
            
            // Check if choices were received
            if (choices && choices.length > 0) {
              setIsGeneratingChoices(false);
              setWaitingForChoicesSceneId(null);
            } else {
              // No choices received - start retry mechanism
              setIsGeneratingChoices(true);
              setWaitingForChoicesSceneId(sceneId);
              
              // Retry fetching scene data after 2 seconds
              setTimeout(async () => {
                try {
                  const storyData = await apiClient.getStory(storyId);
                  const updatedScene = storyData.scenes.find((s: Scene) => s.id === sceneId);
                  if (updatedScene && updatedScene.choices && updatedScene.choices.length > 0) {
                    // Update the scene in state with choices
                    setStory((prevStory) => {
                      if (!prevStory) return prevStory;
                      return {
                        ...prevStory,
                        scenes: prevStory.scenes.map((s: Scene) =>
                          s.id === sceneId ? { ...s, choices: updatedScene.choices } : s
                        )
                      };
                    });
                    setIsGeneratingChoices(false);
                    setWaitingForChoicesSceneId(null);
                  } else {
                    // Still no choices, retry again after 3 more seconds
                    setTimeout(async () => {
                      try {
                        const storyData2 = await apiClient.getStory(storyId);
                        const updatedScene2 = storyData2.scenes.find((s: Scene) => s.id === sceneId);
                        if (updatedScene2 && updatedScene2.choices && updatedScene2.choices.length > 0) {
                          setStory((prevStory) => {
                            if (!prevStory) return prevStory;
                            return {
                              ...prevStory,
                              scenes: prevStory.scenes.map((s: Scene) =>
                                s.id === sceneId ? { ...s, choices: updatedScene2.choices } : s
                              )
                            };
                          });
                        } else {
                          console.warn('[CHOICES RETRY] No choices found after multiple retries');
                        }
                        setIsGeneratingChoices(false);
                        setWaitingForChoicesSceneId(null);
                      } catch (err) {
                        console.error('[CHOICES RETRY] Error on second retry:', err);
                        setIsGeneratingChoices(false);
                        setWaitingForChoicesSceneId(null);
                      }
                    }, 3000);
                  }
                } catch (err) {
                  console.error('[CHOICES RETRY] Error fetching scene data:', err);
                  setIsGeneratingChoices(false);
                  setWaitingForChoicesSceneId(null);
                }
              }, 2000);
            }
          } else {
            console.error('[SCENE COMPLETE] Failed to add scene - story:', !!story, 'content length:', accumulatedContent?.length || 0);
            // Still need to clear streaming state even if scene wasn't added
            setStreamingContent('');
            setStreamingSceneNumber(null);
            setIsStreaming(false);
            setSelectedChoice(null);
            setShowChoicesDuringGeneration(true);
          }

          setCustomPrompt('');
          setUserSceneContent(''); // Clear user content after successful generation
          setFirstSceneMode('ai'); // Reset to AI mode after first scene

          // Refresh story content in background to sync with backend
          // Use setTimeout to avoid blocking the UI and causing flicker
          setTimeout(() => {
            refreshStoryContent();
          }, 500);

          // Refresh chapter sidebar to update context counter
          setChapterSidebarRefreshKey(prev => prev + 1);
          
          // Clear operation flag with delay to let DOM settle
          setTimeout(() => setIsSceneOperationInProgress(false), 1500);
          
          // Clear abort controller reference after completion
          sceneGenerationAbortControllerRef.current = null;
        },
        // onError — attempt recovery for network errors (iOS background tab kill)
        async (error: string) => {
          console.error('Streaming error:', error);

          // Check if this might be a network error from iOS background kill
          // (not a server-sent error like "LLM server unavailable")
          const isNetworkError = error.includes('Failed to fetch') ||
            error.includes('network') ||
            error.includes('NetworkError') ||
            error.includes('Load failed') ||
            error.includes('The network connection was lost') ||
            error.includes('Stream timeout');

          if (isNetworkError) {
            console.log('[RECOVERY] Network error detected, attempting recovery...');
            recoveryInProgress = true;
            try {
              const result = await apiClient.recoverGeneration(storyId);
              if (result.status === 'completed' && result.scene_id && result.content) {
                // Scene completed in background — recover it
                const nextSceneNumber = (story?.scenes?.length || 0) + 1;
                const recoveredChoices = (result.choices || []).map((c: any, i: number) => ({
                  id: -(i + 1),
                  text: c.text || c,
                  order: c.order || i + 1,
                }));
                const newScene: Scene = {
                  id: result.scene_id,
                  sequence_number: nextSceneNumber,
                  title: `Scene ${nextSceneNumber}`,
                  content: result.content,
                  location: '',
                  characters_present: [],
                  choices: recoveredChoices,
                  variant_id: result.variant_id,
                  has_multiple_variants: false,
                  total_variants: 1,
                  chapter_id: result.chapter_id ?? activeChapterId ?? undefined,
                };
                if (story) {
                  const updatedStory = { ...story, scenes: [...story.scenes, newScene] };
                  flushSync(() => { setStory(updatedStory); });
                }
                setStreamingContent('');
                setStreamingSceneNumber(null);
                setIsStreaming(false);
                setSelectedChoice(null);
                setShowChoicesDuringGeneration(true);
                setGenerationStartTime(null);
                setExtractionStatus(null);
                setIsSceneOperationInProgress(false);
                sceneGenerationAbortControllerRef.current = null;
                if (result.auto_play && result.auto_play.session_id) {
                  globalTTS.connectToSession(result.auto_play.session_id, result.auto_play.scene_id);
                }
                setTimeout(() => refreshStoryContent(), 500);
                setChapterSidebarRefreshKey(prev => prev + 1);
                console.log('[RECOVERY] Scene recovered from network error');
                return; // Don't show error
              } else if (result.status === 'generating') {
                // Still running — trigger polling via handleRecovery
                console.log('[RECOVERY] Generation still in progress after network error');
                handleRecovery();
                return; // Don't show error yet
              }
              // status 'none' or 'error' — fall through to show error
              recoveryInProgress = false;
            } catch (recoverErr) {
              console.warn('[RECOVERY] Recovery attempt failed:', recoverErr);
              recoveryInProgress = false;
            }
          }

          // Show error (non-network error or recovery failed)
          recoveryInProgress = false;
          setError(error);
          setStreamingContent('');
          setStreamingSceneNumber(null);
          setIsStreaming(false);
          setGenerationStartTime(null);
          setExtractionStatus(null);

          // Reset choice selection state on error
          setSelectedChoice(null);
          setShowChoicesDuringGeneration(true);

          // Clear operation flag
          setIsSceneOperationInProgress(false);

          // Clear abort controller reference on error
          sceneGenerationAbortControllerRef.current = null;
        },
        // onAutoPlayReady - Connect to global TTS session immediately
        (sessionId: string, sceneId: number) => {
          globalTTS.connectToSession(sessionId, sceneId);
        },
        // onExtractionStatus - Handle extraction status updates
        (status: 'extracting' | 'complete' | 'error', message: string) => {
          setExtractionStatus({ status, message });
          if (status === 'complete' || status === 'error') {
            // Clear extraction status after a short delay
            setTimeout(() => setExtractionStatus(null), 2000);
          }
        },
        // isConcluding - Generate a chapter-concluding scene
        isConcluding,
        // abortSignal - Allow cancellation
        abortController.signal,
        // onThinkingStart - LLM is starting to reason
        () => {
          setIsThinking(true);
          setThinkingContent('');
        },
        // onThinkingChunk - Stream thinking content
        (chunk: string) => {
          setThinkingContent(prev => prev + chunk);
        },
        // onThinkingEnd - Thinking phase complete
        (totalChars: number) => {
          setIsThinking(false);
          // Keep thinking content for display (will be cleared on next generation)
        },
        // onContradictionCheck - Handle inline contradiction check results
        (data: { status: string; contradictions?: Array<{
          id: number; type: string; character_name: string | null;
          previous_value: string | null; current_value: string | null;
          severity: string; scene_sequence: number;
        }>; auto_regenerating?: boolean }) => {
          if (data.status === 'checking') {
            setCheckingContradictions(true);
          } else if (data.status === 'found' && data.contradictions) {
            setCheckingContradictions(false);
            // Key contradictions by scene sequence
            const seqNum = data.contradictions[0]?.scene_sequence;
            if (seqNum) {
              setSceneContradictions(prev => ({
                ...prev,
                [seqNum]: data.contradictions!
              }));
            }
          } else if (data.status === 'clear' || data.status === 'error') {
            setCheckingContradictions(false);
          }
        }
      );

      // Check for new important characters
      checkCharacterImportance();
    } catch (err) {
      // If recovery is in progress (async onError handler), don't touch state
      // The recovery handler will clean up when it completes
      if (recoveryInProgress) {
        console.log('[RECOVERY] Catch block skipped — recovery in progress');
        return;
      }
      // If onError already handled recovery (set isStreaming=false), don't overwrite
      console.error('generateNewSceneStreaming error', err);
      setIsStreaming(prev => {
        if (prev) {
          const errorMessage = err instanceof Error
            ? (err.message === 'Load failed'
               ? 'Network request failed. Please check your connection and try again.'
               : err.message)
            : 'Failed to generate scene';
          setError(errorMessage);
          setStreamingContent('');
          setStreamingSceneNumber(null);
          setGenerationStartTime(null);
          setIsSceneOperationInProgress(false);
          sceneGenerationAbortControllerRef.current = null;
        }
        return false;
      });
    }
  };

  // Scene generation - chooses endpoint based on streaming setting
  const generateScene = async (prompt?: string, isConcluding?: boolean) => {
    // Set the selected choice for UI feedback
    setSelectedChoice(prompt || null);
    setShowChoicesDuringGeneration(false);
    // Always use streaming endpoint - backend returns JSON when streaming disabled
    return generateNewSceneStreaming(prompt, isConcluding);
  };

  const updateScene = async (sceneId: number, content: string, variantId?: number) => {
    try {
      const variantIdToUse = variantId || editingVariantId;

      if (!variantIdToUse) {
        setError('Cannot update scene: variant ID not found');
        return;
      }

      // Call the API to update the scene variant
      const response = await apiClient.updateSceneVariant(storyId, sceneId, variantIdToUse, content);

      // Update local state with response data (no full refresh needed)
      if (story) {
        const updatedStory = {
          ...story,
          scenes: story.scenes.map(scene =>
            scene.id === sceneId && scene.variant_id === variantIdToUse
              ? {
                  ...scene,
                  content: response.variant.content,
                  user_edited: response.variant.user_edited,
                  updated_at: response.variant.updated_at
                }
              : scene
          )
        };
        setStory(updatedStory);
      }

      setEditingScene(null);
      setEditingVariantId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update scene');
    }
  };

  const startEditingScene = (scene: Scene) => {
    setEditingScene(scene.id);
    setEditingVariantId(scene.variant_id || null);
    setEditContent(scene.content);
  };

  const handleCharacterAdd = async (character: any) => {
    const newCharacter = {
      name: character.name,
      role: character.role,
      description: character.description,
      gender: character.gender
    };
    setStoryCharacters(prev => [...prev, newCharacter]);
    setShowCharacterQuickAdd(false);
    
    // Automatically add character to current active chapter
    if (activeChapter && activeChapter.id) {
      try {
        await apiClient.addCharacterToChapter(storyId, activeChapter.id, character.id, undefined, character.role);
        // Reload active chapter to get updated character list
        const updatedChapter = await apiClient.getActiveChapter(storyId);
        setActiveChapter(updatedChapter);
        // Refresh chapter sidebar
        setChapterSidebarRefreshKey(prev => prev + 1);
      } catch (error) {
        console.error('Failed to add character to chapter:', error);
        // Don't show error to user - character is still added to story
      }
    }
  };
  
  const handleChapterWizardComplete = async (chapterData: {
    title?: string;
    description?: string;
    story_character_ids?: number[];
    character_ids?: number[];
    character_roles?: { [characterId: number]: string };
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
  }) => {
    try {
      if (activeChapter && activeChapter.id) {
        // Update existing chapter (e.g., first chapter setup after story creation)
        await apiClient.updateChapter(storyId, activeChapter.id, {
          title: chapterData.title,
          description: chapterData.description,
          story_character_ids: chapterData.story_character_ids,
          character_ids: chapterData.character_ids,
          character_roles: chapterData.character_roles,
          location_name: chapterData.location_name,
          time_period: chapterData.time_period,
          scenario: chapterData.scenario,
          continues_from_previous: chapterData.continues_from_previous
        });
      } else {
        // Create new chapter (for new stories or when no active chapter exists)
        await apiClient.createChapter(storyId, chapterData);
      }
      
      // Reload story and active chapter
      await loadStory(false, false);
      try {
        const updatedChapter = await apiClient.getActiveChapter(storyId);
        setActiveChapter(updatedChapter);
      } catch (err) {
        // If still no active chapter, that's okay - user will create one
        console.warn('No active chapter after wizard completion:', err);
      }
      setShowChapterWizard(false);
      
      // Remove setup_chapter from URL
      router.replace(`/story/${storyId}`);
    } catch (error) {
      console.error('Failed to save chapter setup:', error);
      alert('Failed to save chapter setup. Please try again.');
      throw error; // Re-throw so ChapterWizard can catch and reset loading state
    }
  };
  
  const handleChapterWizardCancel = () => {
    setShowChapterWizard(false);
    // Remove setup_chapter from URL
    router.replace(`/story/${storyId}`);
  };

  const checkCharacterImportance = async () => {
    try {
      const response = await apiClient.checkCharacterImportance(storyId, currentChapterId, currentBranchId);
      setShowCharacterBanner(response.new_character_detected);
    } catch (error) {
      console.error('Failed to check character importance:', error);
    }
  };

  const handleCharacterCreated = (character: any) => {
    // Refresh story characters or add to local state
    setStoryCharacters(prev => [...prev, {
      name: character.name,
      role: character.role,
      description: character.description,
      gender: character.gender
    }]);
    setShowCharacterBanner(false);
  };

  const updateManualChoice = async (variantId: number, newChoiceText: string) => {
    try {
      await apiClient.updateManualChoice(storyId, variantId, newChoiceText);
    } catch (error) {
      console.error('Failed to update manual choice:', error);
    }
  };

  const handleCustomPromptChange = useCallback((newValue: string) => {
    setCustomPrompt(newValue);
    
    // If this is the last scene and we're editing an existing manual choice
    if (story && story.scenes.length > 0) {
      const lastScene = story.scenes[story.scenes.length - 1];
      if (lastScene.variant_id !== undefined) {
        // Clear existing timeout
        if (manualChoiceUpdateTimeoutRef.current) {
          clearTimeout(manualChoiceUpdateTimeoutRef.current);
        }
        
        // Debounce the update to avoid too many API calls
        // Update after 1 second of no typing
        manualChoiceUpdateTimeoutRef.current = setTimeout(() => {
          if (newValue.trim() && lastScene.variant_id !== undefined) {
            updateManualChoice(lastScene.variant_id, newValue);
          }
        }, 1000);
      }
    }
  }, [story, storyId]);

  const generateMoreOptions = async (variantId: number) => {
    if (!story || !story.scenes.length || isGeneratingMoreOptions || !variantId) return;
    
    setIsGeneratingMoreOptions(true);
    try {
      // Generate choices
      const response = await apiClient.generateMoreChoices(storyId, variantId);
      
      // Update local state with new choices (no full refresh needed)
      const sceneWithVariant = story.scenes.find(s => s.variant_id === variantId);
      if (sceneWithVariant && response.choices) {
        setStory(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            scenes: prev.scenes.map(s =>
              s.id === sceneWithVariant.id
                ? {
                    ...s,
                    choices: [...(s.choices || []), ...response.choices.map((c: any) => c.text || c.choice_text || c)]
                  }
                : s
            )
          };
        });
      }

      // Trigger variant reload to show new choices in component
      variantReloadTriggerRef.current += 1;
      
    } catch (error) {
      console.error('Failed to generate more options:', error);
      // Extract error message from the error response
      // The API client already extracts the detail/message from the backend response
      let errorMessage = 'Failed to generate choices. Please try again.';
      if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === 'object' && error !== null && 'message' in error) {
        errorMessage = String(error.message);
      }
      // Show user-friendly error message
      setError(errorMessage);
      // Clear error after 8 seconds to give user time to read
      setTimeout(() => setError(''), 8000);
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
      await loadStory(false, true); // Scroll to updated last scene after regeneration
      
      // Show success message or handle the new variant
      
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
    }
  };

  const createNewVariant = async (sceneId: number, customPrompt?: string, variantId?: number) => {
    if (!story) return;
    
    
    try {
      setIsRegenerating(true);
      
      // Always use streaming endpoint - backend returns JSON when streaming disabled
      {
        // Always show loading state - streaming UI used for loading indicator
        setIsStreaming(true);
        setStreamingVariantSceneId(sceneId);
        setStreamingVariantContent('');
        
        // Track if we already received auto_play_ready event to avoid double-connection
        let autoPlayAlreadyTriggered = false;
        
        // Accumulate streaming content locally for use in completion callback
        let accumulatedVariantContent = '';
        
        // Detect iOS Safari for variant streaming
        const isIOSVariant = typeof window !== 'undefined' && 
          (/iPad|iPhone|iPod/.test(navigator.userAgent) || 
           (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
        
        // For iOS, batch chunks to prevent too many synchronous renders
        let iosVariantChunkBuffer = '';
        let iosVariantFlushTimer: ReturnType<typeof setTimeout> | null = null;
        
        const flushIOSVariantChunks = () => {
          if (iosVariantChunkBuffer) {
            flushSync(() => {
              setStreamingVariantContent(prev => prev + iosVariantChunkBuffer);
            });
            iosVariantChunkBuffer = '';
          }
          if (iosVariantFlushTimer) {
            clearTimeout(iosVariantFlushTimer);
            iosVariantFlushTimer = null;
          }
        };
        
        // Create AbortController for this streaming operation
        const abortController = new AbortController();
        variantGenerationAbortControllerRef.current = abortController;
        
        await apiClient.createSceneVariantStreaming(
          story.id,
          sceneId,
          customPrompt || '',
          variantId,
          // onChunk
          (chunk: string) => {
            // Always accumulate content for use in completion callback
            accumulatedVariantContent += chunk;
            
            if (isIOSVariant) {
              // Buffer chunks and flush frequently on iOS (every 50ms max, or immediately if buffer gets large)
              iosVariantChunkBuffer += chunk;
              
              // Flush immediately if buffer is getting large (more than 200 chars)
              if (iosVariantChunkBuffer.length > 200) {
                flushIOSVariantChunks();
              } else if (!iosVariantFlushTimer) {
                // Schedule flush every 50ms for responsive updates
                iosVariantFlushTimer = setTimeout(() => {
                  flushIOSVariantChunks();
                }, 50);
              }
            } else {
              setStreamingVariantContent(prev => prev + chunk);
            }
          },
          // onComplete
          async (response: any) => {
            // Flush any remaining buffered chunks on iOS
            if (isIOSVariant) {
              flushIOSVariantChunks();
            }
            
            // Flush any remaining iOS chunks before using accumulated content
            if (isIOSVariant) {
              flushIOSVariantChunks();
            }
            
            // Check if this is a multi-generation response
            const isMultiGen = response.isMultiGeneration && response.variants && response.variants.length > 1;
            
            if (isMultiGen) {
              // Multi-generation: update with first variant, flag scene as having multiple
              const firstVariant = response.variants[0];
              if (story) {
                const updatedScenes = story.scenes.map(s => {
                  if (s.id === sceneId) {
                    return {
                      ...s,
                      content: firstVariant.content || accumulatedVariantContent || s.content,
                      variant_id: firstVariant.id,
                      variant_number: firstVariant.variant_number,
                      has_multiple_variants: true,
                      total_variants: response.new_variants_count + (s.total_variants || 1) - 1,
                      choices: firstVariant.choices 
                        ? firstVariant.choices.map((c: any) => c.text || c.choice_text || c)
                        : s.choices
                    };
                  }
                  return s;
                });
                setStory({ ...story, scenes: updatedScenes });
                console.log(`[MULTI-GEN VARIANT] Generated ${response.new_variants_count} new variants - swipe to explore`);
              }
            }
            // Update the scene with the new variant content and choices directly in state
            else if (response.variant && story) {
              const updatedScenes = story.scenes.map(s => {
                if (s.id === sceneId) {
                  // Update scene with new variant content and choices
                  // Prefer response.variant.content, fall back to accumulated streaming content, then original
                  const newContent = response.variant.content || accumulatedVariantContent || s.content;
                  return {
                    ...s,
                    content: newContent,
                    variant_id: response.variant.id,
                    variant_number: response.variant.variant_number,
                    has_multiple_variants: true,  // Set flag to show navigation arrows
                    choices: response.variant.choices 
                      ? response.variant.choices.map((c: any) => c.text || c.choice_text)
                      : s.choices
                  };
                }
                return s;
              });
              setStory({ ...story, scenes: updatedScenes });
            }
            
            // Check if auto-play was triggered - but ONLY if we didn't already handle it via auto_play_ready
            if (response.auto_play_session_id && !autoPlayAlreadyTriggered) {
              globalTTS.connectToSession(response.auto_play_session_id, sceneId);
            } else if (autoPlayAlreadyTriggered) {
            } else {
            }
            
            // Clear streaming states
            setCustomPrompt('');
            setStreamingVariantContent('');
            setStreamingVariantSceneId(null);
            setIsStreaming(false);
            setIsRegenerating(false);

            // Clear abort controller reference after completion
            variantGenerationAbortControllerRef.current = null;
            
            // No need to reload story - state is already updated with new variant
            // SceneVariantDisplay will detect has_multiple_variants flag and load variants automatically
          },
          // onError
          (error: string) => {
            console.error('[VARIANT ERROR]', error);
            setStreamingVariantContent('');
            setStreamingVariantSceneId(null);
            setIsStreaming(false);
            alert(`Failed to create variant: ${error}`);
            
            // Clear abort controller reference on error
            variantGenerationAbortControllerRef.current = null;
          },
          // onAutoPlayReady - Connect to global TTS immediately when ready
          (sessionId: string) => {
            autoPlayAlreadyTriggered = true; // Mark that we handled auto-play
            globalTTS.connectToSession(sessionId, sceneId);
          },
          // isConcluding - not used for variants
          undefined,
          // abortSignal - Allow cancellation
          abortController.signal
        );
        
        // Clear abort controller reference after completion
        variantGenerationAbortControllerRef.current = null;
      }
      
    } catch (error) {
      console.error('Failed to create variant:', error);
      setError(error instanceof Error ? error.message : 'Failed to create variant');
      setIsStreaming(false);
      
      // Clear abort controller reference on error
      variantGenerationAbortControllerRef.current = null;
    } finally {
      setIsRegenerating(false);
    }
  };

  const continueScene = async (sceneId: number, customPrompt?: string) => {
    if (!story) return;
    
    
    try {
      setIsRegenerating(true);
      
      // Always use streaming endpoint - backend returns JSON when streaming disabled
      {
        // Always show loading state - streaming UI used for loading indicator
        setIsStreamingContinuation(true);
        setStreamingContinuation('');
        setStreamingContinuationSceneId(sceneId);
        
        // Detect iOS Safari for continuation streaming
        const isIOSContinuation = typeof window !== 'undefined' && 
          (/iPad|iPhone|iPod/.test(navigator.userAgent) || 
           (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
        
        // For iOS, batch chunks to prevent too many synchronous renders
        let iosContinuationChunkBuffer = '';
        let iosContinuationFlushTimer: ReturnType<typeof setTimeout> | null = null;
        
        const flushIOSContinuationChunks = () => {
          if (iosContinuationChunkBuffer) {
            flushSync(() => {
              setStreamingContinuation(prev => prev + iosContinuationChunkBuffer);
            });
            iosContinuationChunkBuffer = '';
          }
          if (iosContinuationFlushTimer) {
            clearTimeout(iosContinuationFlushTimer);
            iosContinuationFlushTimer = null;
          }
        };
        
        // Create AbortController for this streaming operation
        const abortController = new AbortController();
        continuationAbortControllerRef.current = abortController;
        
        await apiClient.continueSceneStreaming(
          story.id,
          sceneId,
          customPrompt || "Continue this scene with more details and development, adding to the existing content.",
          // onChunk
          (chunk: string) => {
            if (isIOSContinuation) {
              // Buffer chunks and flush frequently on iOS (every 50ms max, or immediately if buffer gets large)
              iosContinuationChunkBuffer += chunk;
              
              // Flush immediately if buffer is getting large (more than 200 chars)
              if (iosContinuationChunkBuffer.length > 200) {
                flushIOSContinuationChunks();
              } else if (!iosContinuationFlushTimer) {
                // Schedule flush every 50ms for responsive updates
                iosContinuationFlushTimer = setTimeout(() => {
                  flushIOSContinuationChunks();
                }, 50);
              }
            } else {
              setStreamingContinuation(prev => prev + chunk);
            }
          },
          // onComplete
          async (completedSceneId: number, newContent: string) => {
            // Flush any remaining buffered chunks on iOS
            if (isIOSContinuation) {
              flushIOSContinuationChunks();
            }
            
            // Preserve current scroll position
            const currentScrollPosition = window.pageYOffset;
            
            // Reload story to get updated scene data from backend
            await loadStory(false, false); // Don't auto-scroll, we'll handle it manually
            
            // Restore scroll position and then scroll to the continued scene
            window.scrollTo({ top: currentScrollPosition, behavior: 'instant' });
            
            // Now scroll to the scene that was continued
            setTimeout(() => {
              const sceneElement = document.querySelector(`[data-scene-id="${completedSceneId}"]`);
              if (sceneElement) {
                sceneElement.scrollIntoView({ behavior: 'instant', block: 'start' });
              }
            }, 50);
            
            
            // Then clear streaming states after story is loaded
            setCustomPrompt('');
            setIsStreamingContinuation(false);
            setStreamingContinuation('');
            setStreamingContinuationSceneId(null);

            // Clear abort controller reference after completion
            continuationAbortControllerRef.current = null;
          },
          // onError
          (error: string) => {
            setIsStreamingContinuation(false);
            setStreamingContinuation('');
            setStreamingContinuationSceneId(null);
            setError(error);
            
            // Clear abort controller reference on error
            continuationAbortControllerRef.current = null;
          },
          // abortSignal - Allow cancellation
          abortController.signal
        );
        
        // Clear abort controller reference after completion
        continuationAbortControllerRef.current = null;
      }
      
    } catch (error) {
      console.error('Failed to continue scene:', error);
      const errorMessage = error instanceof Error 
        ? (error.message === 'Load failed' 
           ? 'Network request failed. Please check your connection and try again.'
           : error.message)
        : 'Failed to continue scene';
      setError(errorMessage);
      setIsStreamingContinuation(false);
      setStreamingContinuation('');
      setStreamingContinuationSceneId(null);
      
      // Clear abort controller reference on error
      continuationAbortControllerRef.current = null;
    } finally {
      setIsRegenerating(false);
    }
  };

  const stopGeneration = () => {
    // Abort all active streaming operations
    if (sceneGenerationAbortControllerRef.current) {
      sceneGenerationAbortControllerRef.current.abort();
      sceneGenerationAbortControllerRef.current = null;
    }
    if (variantGenerationAbortControllerRef.current) {
      variantGenerationAbortControllerRef.current.abort();
      variantGenerationAbortControllerRef.current = null;
    }
    if (continuationAbortControllerRef.current) {
      continuationAbortControllerRef.current.abort();
      continuationAbortControllerRef.current = null;
    }

    // Tell backend to release the generation lock
    apiClient.cancelSceneGeneration(storyId).catch(() => {});

    // Stop all streaming states
    setIsStreaming(false);
    setStreamingContent('');
    setStreamingSceneNumber(null);
    setIsStreamingContinuation(false);
    setStreamingContinuation('');
    setStreamingContinuationSceneId(null);
    setIsGenerating(false);
    setIsRegenerating(false);
    setStreamingVariantContent('');
    setStreamingVariantSceneId(null);

    // Reset UI states
    setSelectedChoice(null);
    setShowChoicesDuringGeneration(true);

  };

  const toggleDeleteMode = () => {
    setIsInDeleteMode(!isInDeleteMode);
    setSelectedScenesForDeletion([]);
    setShowDeleteConfirmation(false);
  };

  const toggleSceneForDeletion = (sequenceNumber: number) => {
    if (selectedScenesForDeletion.includes(sequenceNumber)) {
      setSelectedScenesForDeletion(prev => prev.filter(seq => seq !== sequenceNumber));
    } else {
      setSelectedScenesForDeletion(prev => [...prev, sequenceNumber]);
    }
  };

  // Activate delete mode and select this scene and all subsequent scenes
  const activateDeleteModeFromScene = (sequenceNumber: number) => {
    if (!story) return;
    
    // Activate delete mode
    setIsInDeleteMode(true);
    
    // Select this scene and all subsequent scenes
    const scenesToDelete: number[] = [];
    story.scenes.forEach(scene => {
      if (scene.sequence_number >= sequenceNumber) {
        scenesToDelete.push(scene.sequence_number);
      }
    });
    
    setSelectedScenesForDeletion(scenesToDelete);
  };

  // Deactivate delete mode
  const deactivateDeleteMode = () => {
    setIsInDeleteMode(false);
    setSelectedScenesForDeletion([]);
    setShowDeleteConfirmation(false);
  };

  const deleteScenesFromSelected = () => {
    if (!story || selectedScenesForDeletion.length === 0) return;
    
    // Show confirmation dialog
    setShowDeleteConfirmation(true);
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
          // This will be handled by the SceneVariantDisplay component
        } else if (event.key === 'ArrowLeft') {
          event.preventDefault();
          // Left arrow: Navigate to previous variant of last scene
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
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto"></div>
          <p className="mt-4 text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (!hasHydrated) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto"></div>
          <p className="mt-4 text-gray-400">Loading story...</p>
        </div>
      </div>
    );
  }

  if (!story) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
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
    <div className="min-h-screen theme-bg-primary text-white">
      {/* Context Usage Progress Bar - Fixed at top */}
      <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-gray-800">
        <div 
          className="h-full transition-all duration-500 ease-out"
          style={{ 
            width: `${contextUsagePercent}%`,
            background: contextUsagePercent >= 80 
              ? 'linear-gradient(90deg, #ef4444, #dc2626)' // Red when high
              : contextUsagePercent >= 50 
              ? 'linear-gradient(90deg, #f59e0b, #d97706)' // Orange when medium
              : 'linear-gradient(90deg, #10b981, #059669)' // Green when low
          }}
        />
      </div>
      
      {/* Context Warning Modal - Shows at 80% */}
      {showContextWarning && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-gradient-to-br from-yellow-900/90 to-orange-900/90 backdrop-blur-md rounded-lg shadow-2xl w-full max-w-md border-2 border-yellow-500/50">
            {/* Header */}
            <div className="p-6 border-b border-yellow-500/30">
              <div className="flex items-start gap-4">
                <div className="p-3 bg-yellow-500/20 rounded-full">
                  <AlertCircle className="w-8 h-8 text-yellow-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-xl font-bold text-white mb-1">Context Limit Warning</h3>
                  <p className="text-yellow-200/80 text-sm">Your chapter is reaching its context capacity</p>
                </div>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4">
              <div className="bg-black/20 rounded-lg p-4 border border-yellow-500/20">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-yellow-200 font-semibold">Context Usage</span>
                  <span className="text-2xl font-bold text-yellow-400">{contextUsagePercent}%</span>
                </div>
                <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-yellow-500 to-orange-500 transition-all duration-500"
                    style={{ width: `${contextUsagePercent}%` }}
                  />
                </div>
              </div>

              <div className="space-y-3 text-sm text-yellow-100">
                <p className="leading-relaxed">
                  Your current chapter has used <span className="font-semibold text-yellow-300">{contextUsagePercent}%</span> of its available context window. 
                  To maintain story quality and coherence, consider creating a new chapter soon.
                </p>
                
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
                  <p className="text-blue-200 text-xs">
                    💡 <span className="font-semibold">What happens when you create a new chapter?</span>
                  </p>
                  <p className="text-blue-200/80 text-xs mt-1">
                    The AI will generate a summary of your current chapter and use it as context for the new chapter, 
                    ensuring your story continues smoothly without losing important details.
                  </p>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-yellow-500/30 flex gap-3">
              <button
                onClick={() => setShowContextWarning(false)}
                className="flex-1 px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium transition-colors"
              >
                Continue Current Chapter
              </button>
              <button
                onClick={() => {
                  setShowContextWarning(false);
                  setIsChapterSidebarOpen(true);
                }}
                className="flex-1 px-4 py-3 bg-gradient-to-r from-yellow-600 to-orange-600 hover:from-yellow-700 hover:to-orange-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
              >
                <BookOpen className="w-4 h-4" />
                Open Chapters
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Note: Floating menu button is now in PersistentBanner - always visible */}
      
      {/* Story Menu Modal - For Phase 2: This will be removed when UnifiedMenu has all story actions */}
      {showMainMenu && (
        <>
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={() => setShowMainMenu(false)}
          />
          
          {/* Menu Modal */}
          <div className="fixed left-4 bottom-20 z-50 w-80 max-w-[calc(100vw-2rem)] bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-gradient-to-r from-purple-900/50 to-pink-900/50">
              <h2 className="text-lg font-semibold">Story Menu</h2>
              <button
                onClick={() => setShowMainMenu(false)}
                className="p-1 hover:bg-slate-700 rounded transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Menu Items */}
            <div className="p-2 max-h-[calc(100vh-12rem)] overflow-y-auto">
              {/* TTS Audio Player */}
              <GlobalTTSWidget />
              
              {/* Branch Selector */}
              <div className="px-3 py-2 border-b border-slate-700/50 mb-2">
                <div className="text-xs text-slate-400 mb-2">Story Branch</div>
                <BranchSelector
                  storyId={storyId}
                  currentBranchId={currentBranchId}
                  currentSceneSequence={story?.scenes?.length || 1}
                  onBranchChange={handleBranchChange}
                  onBranchCreated={(branch) => {
                    setShowMainMenu(false);
                    setCurrentBranchId(branch.id);
                    loadStory(true, false, branch.id);
                  }}
                />
              </div>
              
              {/* Chapter Navigation */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  setIsChapterSidebarOpen(true);
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-purple-600/20 rounded-lg group-hover:bg-purple-600/30 transition-colors">
                  <BookOpen className="w-5 h-5 text-purple-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Chapters</div>
                  <div className="text-xs text-gray-400">View chapter info & summaries</div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-500" />
              </button>
              
              {/* Add Character */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  setShowCharacterQuickAdd(true);
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-purple-600/20 rounded-lg group-hover:bg-purple-600/30 transition-colors">
                  <PlusIcon className="w-5 h-5 text-purple-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Add Character</div>
                  <div className="text-xs text-gray-400">Quick add a new character</div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-500" />
              </button>
              
              {/* Edit Character Voices */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  setShowCharacterVoiceEditor(true);
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-pink-600/20 rounded-lg group-hover:bg-pink-600/30 transition-colors">
                  <Volume2 className="w-5 h-5 text-pink-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Character Voices</div>
                  <div className="text-xs text-gray-400">Edit how characters speak</div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-500" />
              </button>
              
              {/* View All Characters */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  router.push('/characters');
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-blue-600/20 rounded-lg group-hover:bg-blue-600/30 transition-colors">
                  <BookOpenIcon className="w-5 h-5 text-blue-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">All Characters</div>
                  <div className="text-xs text-gray-400">Manage your characters</div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-500" />
              </button>

              {/* Edit Latest Scene */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  if (story?.scenes && story.scenes.length > 0) {
                    const lastScene = story.scenes[story.scenes.length - 1];
                    startEditingScene(lastScene);
                  }
                }}
                disabled={!story?.scenes || story.scenes.length === 0}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="p-2 bg-indigo-600/20 rounded-lg group-hover:bg-indigo-600/30 transition-colors">
                  <Edit2 className="w-5 h-5 text-indigo-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Edit Scene</div>
                  <div className="text-xs text-gray-400">Edit the latest scene</div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-500" />
              </button>

              {/* Play TTS for Latest Scene */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  if (story?.scenes && story.scenes.length > 0) {
                    const lastScene = story.scenes[story.scenes.length - 1];
                    globalTTS.playScene(lastScene.id);
                  }
                }}
                disabled={!story?.scenes || story.scenes.length === 0}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="p-2 bg-green-600/20 rounded-lg group-hover:bg-green-600/30 transition-colors">
                  <Volume2 className="w-5 h-5 text-green-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Play TTS</div>
                  <div className="text-xs text-gray-400">Play the latest scene</div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-500" />
              </button>

              {/* Divider */}
              <div className="my-2 border-t border-slate-700"></div>
              
              {/* Director Mode */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  setDirectorMode(!directorMode);
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className={`p-2 rounded-lg transition-colors ${
                  directorMode 
                    ? 'bg-pink-600/20 group-hover:bg-pink-600/30' 
                    : 'bg-gray-600/20 group-hover:bg-gray-600/30'
                }`}>
                  <FilmIcon className={`w-5 h-5 ${directorMode ? 'text-pink-400' : 'text-gray-400'}`} />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Director Mode</div>
                  <div className={`text-xs ${directorMode ? 'text-pink-400' : 'text-gray-400'}`}>
                    {directorMode ? 'Control scene details' : 'Direct what happens next'}
                  </div>
                </div>
                <div className={`px-2 py-1 rounded text-xs font-medium ${
                  directorMode 
                    ? 'bg-pink-600/20 text-pink-400' 
                    : 'bg-gray-600/20 text-gray-400'
                }`}>
                  {directorMode ? 'ON' : 'OFF'}
                </div>
              </button>

              {/* Delete Mode */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  if (isInDeleteMode) {
                    if (selectedScenesForDeletion.length === 0) {
                      // If no scenes selected, just exit delete mode
                      toggleDeleteMode();
                    } else {
                      deleteScenesFromSelected();
                    }
                  } else {
                    toggleDeleteMode();
                  }
                }}
                disabled={isInDeleteMode && selectedScenesForDeletion.length === 0}
                className={`w-full flex items-center gap-3 p-3 rounded-lg transition-colors text-left group ${
                  isInDeleteMode && selectedScenesForDeletion.length === 0
                    ? 'opacity-50 cursor-not-allowed'
                    : 'hover:bg-slate-800'
                }`}
              >
                <div className={`p-2 rounded-lg transition-colors ${
                  isInDeleteMode 
                    ? 'bg-red-600/20 group-hover:bg-red-600/30' 
                    : 'bg-gray-600/20 group-hover:bg-gray-600/30'
                }`}>
                  <CheckIcon className={`w-5 h-5 ${isInDeleteMode ? 'text-red-400' : 'text-gray-400'}`} />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">
                    {isInDeleteMode ? 'Delete Selected' : 'Delete Mode'}
                  </div>
                  <div className={`text-xs ${isInDeleteMode ? 'text-red-400' : 'text-gray-400'}`}>
                    {isInDeleteMode 
                      ? selectedScenesForDeletion.length === 0 
                        ? 'Select scenes to delete' 
                        : 'Confirm deletion'
                      : 'Select scenes to delete'}
                  </div>
                </div>
                {isInDeleteMode && selectedScenesForDeletion.length > 0 && (
                  <div className="px-2 py-1 rounded text-xs font-medium bg-red-600/20 text-red-400">
                    {selectedScenesForDeletion.length} selected
                  </div>
                )}
              </button>

              {/* Divider */}
              <div className="my-2 border-t border-slate-700"></div>

              {/* Streaming Toggle */}
              <button
                onClick={() => setUseStreaming(!useStreaming)}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className={`p-2 rounded-lg transition-colors ${
                  useStreaming 
                    ? 'bg-green-600/20 group-hover:bg-green-600/30' 
                    : 'bg-gray-600/20 group-hover:bg-gray-600/30'
                }`}>
                  {useStreaming ? (
                    <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  ) : (
                    <DocumentTextIcon className="w-5 h-5 text-gray-400" />
                  )}
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Streaming Mode</div>
                  <div className={`text-xs ${useStreaming ? 'text-green-400' : 'text-gray-400'}`}>
                    {useStreaming ? 'Real-time generation' : 'Standard mode'}
                  </div>
                </div>
                <div className={`px-2 py-1 rounded text-xs font-medium ${
                  useStreaming 
                    ? 'bg-green-600/20 text-green-400' 
                    : 'bg-gray-600/20 text-gray-400'
                }`}>
                  {useStreaming ? 'ON' : 'OFF'}
                </div>
              </button>

              {/* TTS Settings */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  setShowTTSSettings(true);
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-purple-600/20 group-hover:bg-purple-600/30 rounded-lg transition-colors">
                  <Volume2 className="w-5 h-5 text-purple-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Text-to-Speech</div>
                  <div className="text-xs text-gray-400">Configure voice narration</div>
                </div>
              </button>

              {/* Divider */}
              <div className="my-2 border-t border-slate-700"></div>

              {/* Placeholders for future features */}
              <button
                disabled
                className="w-full flex items-center gap-3 p-3 opacity-50 cursor-not-allowed rounded-lg text-left group"
              >
                <div className="p-2 bg-gray-600/20 rounded-lg">
                  <PhotoIcon className="w-5 h-5 text-gray-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Image Generation</div>
                  <div className="text-xs text-gray-400">Coming soon</div>
                </div>
              </button>

              <button
                disabled
                className="w-full flex items-center gap-3 p-3 opacity-50 cursor-not-allowed rounded-lg text-left group"
              >
                <div className="p-2 bg-gray-600/20 rounded-lg">
                  <ClockIcon className="w-5 h-5 text-gray-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">History</div>
                  <div className="text-xs text-gray-400">Coming soon</div>
                </div>
              </button>

              <button
                disabled
                className="w-full flex items-center gap-3 p-3 opacity-50 cursor-not-allowed rounded-lg text-left group"
              >
                <div className="p-2 bg-gray-600/20 rounded-lg">
                  <ArrowDownIcon className="w-5 h-5 text-gray-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Export</div>
                  <div className="text-xs text-gray-400">Coming soon</div>
                </div>
              </button>

              {/* Divider */}
              <div className="my-2 border-t border-slate-700"></div>

              {/* Close Story */}
              <button
                onClick={() => {
                  setShowMainMenu(false);
                  handleCloseStory();
                }}
                className="w-full flex items-center gap-3 p-3 hover:bg-red-900/20 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-orange-600/20 rounded-lg group-hover:bg-orange-600/30 transition-colors">
                  <X className="w-5 h-5 text-orange-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Close Story</div>
                  <div className="text-xs text-orange-400">Return to dashboard</div>
                </div>
              </button>
            </div>
          </div>
        </>
      )}
      
      {/* Chapter Sidebar - Opens from main menu */}
      <ChapterSidebar
        key={`${storyId}-${chapterSidebarRefreshKey}`}
        storyId={storyId}
        isOpen={isChapterSidebarOpen}
        onToggle={() => setIsChapterSidebarOpen(!isChapterSidebarOpen)}
        onChapterChange={(newChapterId?: number) => {
          // Reload story with the new chapter (optimized - only fetches that chapter's scenes)
          // loadContextStatus is called inside loadStory in parallel with story fetch
          loadStory(false, false, undefined, newChapterId);
        }}
        onChapterSelect={(chapterId) => {
          // This will trigger the switch active chapter flow with confirmation
          // The actual switching happens in ChapterSidebar component
        }}
        currentChapterId={activeChapterId ?? undefined}
        storyArc={story?.story_arc}
        enableStreaming={userSettings?.generation_preferences?.enable_streaming !== false}
        showThinkingContent={userSettings?.llm_settings?.show_thinking_content !== false}
        initialActiveChapter={activeChapter}
        initialContextPercent={contextUsagePercent}
      />

      {/* Main Story Container */}
      <div className="max-w-4xl mx-auto flex flex-col pt-10 md:pt-12" style={{ height: '100vh' }}>
        {/* Story Content Area */}
        <div className="flex-1 p-4 md:p-6 overflow-y-auto" ref={storyContentRef} style={{ overscrollBehaviorY: 'contain' }}>
          <div className="min-h-full">

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
              {getScenesToDisplay().length > 0 ? (
                <div className="space-y-8">
                  {/* Infinite scroll sentinel and manual load button */}
                  {displayMode === 'recent' && (() => {
                    // Get filtered scenes count (accounting for chapter filtering)
                    let filteredScenes = story.scenes;
                    if (activeChapterId !== null) {
                      filteredScenes = story.scenes.filter(scene => scene.chapter_id === activeChapterId);
                    }
                    const hasMoreScenes = filteredScenes.length > scenesToShow;
                    
                    if (!hasMoreScenes) return null;
                    
                    return (
                      <div className="relative">
                        {/* Sentinel for IntersectionObserver - made more visible for better detection */}
                        <div 
                          ref={sentinelRef} 
                          className="h-1 w-full" 
                          aria-hidden="true"
                          style={{ minHeight: '1px' }}
                        />
                        
                        {/* Manual load button as fallback */}
                        <div className="flex justify-center my-4">
                          <button
                            onClick={() => {
                              if (!isAutoLoadingScenes) {
                                loadMoreScenesAutomatically();
                              }
                            }}
                            disabled={isAutoLoadingScenes}
                            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
                          >
                            {isAutoLoadingScenes ? (
                              <>
                                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                <span>Loading...</span>
                              </>
                            ) : (
                              <>
                                <ArrowUpIcon className="h-4 w-4" />
                                <span>Load Earlier Scenes ({filteredScenes.length - scenesToShow} more)</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })()}

                  {(() => {
                    const scenesToRender = getScenesToDisplay();
                    // Debug: Log what's being rendered
                    if (scenesToRender.length > 0) {
                      }
                    return scenesToRender.map((scene, displayIndex) => {
                      // Calculate the actual scene number in the full story
                      const actualSceneNumber = story.scenes.findIndex(s => s.id === scene.id) + 1;
                      const isLastSceneInStory = scene.id === story.scenes[story.scenes.length - 1].id;

                    return (
                      <div
                        key={scene.id}
                        data-scene-id={scene.id}
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

                        {/* Delete Mode Indicator - Show at top of scene (read-only) */}
                        {isInDeleteMode && selectedScenesForDeletion.includes(scene.sequence_number) && (
                          <div className="mb-4 p-3 bg-red-900/20 rounded-lg border border-red-600/50">
                            <div className="flex items-center space-x-2 text-sm text-red-300">
                              <div className="w-4 h-4 flex items-center justify-center">
                                <svg className="w-4 h-4 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                </svg>
                              </div>
                              <span>
                                {selectedScenesForDeletion.length > 0 && Math.min(...selectedScenesForDeletion) === scene.sequence_number
                                  ? 'Delete from here onwards' 
                                  : 'Will be deleted'}
                              </span>
                            </div>
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
                          onSaveEdit={(sceneId: number, content: string, variantId?: number) => updateScene(sceneId, content, variantId)}
                          onCancelEdit={() => setEditingScene(null)}
                          onContentChange={setEditContent}
                          isRegenerating={isRegenerating}
                          isGenerating={isGenerating}
                          isStreaming={isStreaming}
                          onCreateVariant={createNewVariant}
                          onVariantChanged={handleVariantChanged}
                          onContinueScene={continueScene}
                          onStopGeneration={stopGeneration}
                          showChoices={showChoices}
                          directorMode={directorMode}
                          customPrompt={customPrompt}
                          onCustomPromptChange={handleCustomPromptChange}
                          onGenerateScene={generateScene}
                          layoutMode={sceneLayoutMode}
                          onNewSceneAdded={() => setIsNewSceneAdded(true)}
                          selectedChoice={selectedChoice}
                          showChoicesDuringGeneration={showChoicesDuringGeneration}
                          setShowChoicesDuringGeneration={setShowChoicesDuringGeneration}
                          setSelectedChoice={setSelectedChoice}
                          variantReloadTrigger={variantReloadTriggerRef.current}
                          streamingContinuation={streamingContinuationSceneId === scene.id ? streamingContinuation : ''}
                          isStreamingContinuation={streamingContinuationSceneId === scene.id && isStreamingContinuation}
                          isSceneOperationInProgress={isSceneOperationInProgress}
                          streamingVariantContent={streamingVariantSceneId === scene.id ? streamingVariantContent : ''}
                          isStreamingVariant={streamingVariantSceneId === scene.id}
                          isInDeleteMode={isInDeleteMode}
                          isSceneSelectedForDeletion={selectedScenesForDeletion.includes(scene.sequence_number)}
                          onToggleSceneDeletion={toggleSceneForDeletion}
                          onActivateDeleteMode={activateDeleteModeFromScene}
                          onDeactivateDeleteMode={deactivateDeleteMode}
                          onCopySceneText={async (text: string) => {
                            try {
                              await navigator.clipboard.writeText(text);
                            } catch (error) {
                              console.error('Failed to copy text:', error);
                            }
                          }}
                          onCreateBranch={(sceneSequence) => {
                            setShowBranchCreationModal(true);
                            setBranchCreationFromScene(sceneSequence);
                          }}
                          isGeneratingChoices={isGeneratingChoices && waitingForChoicesSceneId === scene.id}
                          showImages={showImages}
                          contradictions={sceneContradictions[scene.sequence_number]}
                          checkingContradictions={checkingContradictions && isLastSceneInStory}
                          onContradictionResolved={(seqNum: number) => {
                            setSceneContradictions(prev => {
                              const next = { ...prev };
                              delete next[seqNum];
                              return next;
                            });
                          }}
                        />
                      </div>
                    );
                  });
                  })()}
                  
                </div>
              ) : (
                <div className="text-center py-12">
                  {activeChapterId !== null && currentChapterInfo && !currentChapterInfo.isActive ? (
                    // Viewing a COMPLETED chapter with no scenes (rare case)
                    <>
                      <BookOpen className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                      <p className="text-gray-400 mb-2">
                        {currentChapterInfo.title || `Chapter ${currentChapterInfo.number}`} - No scenes yet
                      </p>
                      <p className="text-gray-500 text-sm mb-6">
                        This chapter is completed. Return to the active chapter to continue writing.
                      </p>
                      <button
                        onClick={() => {
                          // Reload story to get the active chapter
                          loadStory(false, false);
                        }}
                        className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-lg font-medium"
                      >
                        Return to Active Chapter
                      </button>
                    </>
                  ) : (
                    // Active chapter with no scenes - allow generation
                    <>
                      <div className="space-y-6 max-w-2xl mx-auto">
                        <div>
                          <BookOpen className="w-16 h-16 text-purple-500 mx-auto mb-4" />
                          <p className="text-gray-400 mb-2 text-lg">
                            {currentChapterInfo ? `Begin ${currentChapterInfo.title || `Chapter ${currentChapterInfo.number}`}` : 'Your story awaits...'}
                          </p>
                          {currentChapterInfo && (
                            <p className="text-gray-500 text-sm mb-6">
                              The story will continue from where you left off
                            </p>
                          )}
                        </div>

                        {/* Mode Selector */}
                        <div className="flex gap-2 mb-6">
                          <button
                            onClick={() => setFirstSceneMode('ai')}
                            className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${
                              firstSceneMode === 'ai'
                                ? 'bg-purple-600 text-white'
                                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                            }`}
                          >
                            AI Generate
                          </button>
                          <button
                            onClick={() => setFirstSceneMode('write')}
                            className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${
                              firstSceneMode === 'write'
                                ? 'bg-purple-600 text-white'
                                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                            }`}
                          >
                            Write Your Own
                          </button>
                        </div>

                        {/* Write Your Own Mode */}
                        {firstSceneMode === 'write' && (
                          <div className="mb-6 space-y-4">
                            <textarea
                              value={userSceneContent}
                              onChange={(e) => setUserSceneContent(e.target.value)}
                              placeholder="Write your opening scene here... You can write a complete scene or describe what you want the AI to generate."
                              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                              rows={8}
                            />
                            
                            {/* Radio buttons for write mode */}
                            <div className="space-y-2">
                              <label className="flex items-center space-x-2 cursor-pointer">
                                <input
                                  type="radio"
                                  name="writeMode"
                                  value="prompt"
                                  checked={writeMode === 'prompt'}
                                  onChange={() => setWriteMode('prompt')}
                                  className="w-4 h-4 text-purple-600 bg-gray-700 border-gray-600 focus:ring-purple-500"
                                />
                                <span className="text-gray-300">Use as prompt for AI</span>
                              </label>
                              <label className="flex items-center space-x-2 cursor-pointer">
                                <input
                                  type="radio"
                                  name="writeMode"
                                  value="scene"
                                  checked={writeMode === 'scene'}
                                  onChange={() => setWriteMode('scene')}
                                  className="w-4 h-4 text-purple-600 bg-gray-700 border-gray-600 focus:ring-purple-500"
                                />
                                <span className="text-gray-300">Use as my first scene</span>
                              </label>
                            </div>
                            
                            <p className="text-gray-500 text-xs">
                              {writeMode === 'prompt' 
                                ? 'The AI will generate a scene based on your description'
                                : 'Your text will be saved as the first scene, and AI will generate continuation choices'}
                            </p>
                          </div>
                        )}

                        {/* Director Mode Input for First Scene (only in AI mode) */}
                        {firstSceneMode === 'ai' && directorMode && (
                          <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-400 mb-2">
                              Direct the opening scene:
                            </label>
                            <textarea
                              value={customPrompt}
                              onChange={(e) => setCustomPrompt(e.target.value)}
                              placeholder="e.g., 'Start with the protagonist waking up in an unfamiliar place' or leave blank for AI to decide"
                              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                              rows={3}
                            />
                          </div>
                        )}

                        {/* Generation Button */}
                        <button
                          onClick={() => {
                            if (firstSceneMode === 'write' && !userSceneContent.trim()) {
                              setError('Please enter your scene content or prompt');
                              return;
                            }
                            generateScene();  // Always use streaming endpoint - backend returns JSON when streaming disabled
                          }}
                          disabled={isGenerating || isStreaming || (firstSceneMode === 'write' && !userSceneContent.trim())}
                          className="w-full sm:w-auto theme-btn-primary px-8 py-4 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-xl"
                        >
                          {isGenerating || isStreaming ? (
                            <span className="flex items-center justify-center gap-2">
                              <span className="animate-spin">⚙️</span>
                              {firstSceneMode === 'write' && writeMode === 'scene' ? 'Saving scene...' : 'Creating first scene...'}
                            </span>
                          ) : (
                            <span className="flex items-center justify-center gap-2">
                              <Sparkles className="w-5 h-5" />
                              {firstSceneMode === 'write' && writeMode === 'scene' 
                                ? 'Save & Continue'
                                : firstSceneMode === 'write' && writeMode === 'prompt'
                                ? 'Generate Scene'
                                : currentChapterInfo 
                                ? 'Begin Chapter' 
                                : 'Begin Your Story'}
                            </span>
                          )}
                        </button>

                        {/* Director Mode Toggle Hint */}
                        {firstSceneMode === 'ai' && !directorMode && (
                          <p className="text-gray-500 text-xs">
                            💡 Tip: Enable Director Mode from the menu to guide the opening scene
                          </p>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}
              
              {/* Thinking Box - Show when LLM is reasoning or has reasoning content */}
              {/* Persists after streaming ends so user can view the thinking */}
              {(isThinking || thinkingContent) && (
                <div className="thinking-container mt-8">
                  <ThinkingBox
                    thinking={thinkingContent}
                    isThinking={isThinking}
                    showContent={userSettings?.llm_settings?.show_thinking_content ?? true}
                  />
                </div>
              )}
              
              {/* Streaming Content Display - Show at bottom after existing scenes */}
              {/* Also show when thinking but no content yet (to display the Thinking... indicator) */}
              {isStreaming && (streamingContent || isThinking) && (
                <div className="streaming-scene mt-8">
                  {/* Scene Separator for streaming */}
                  {story?.scenes && story.scenes.length > 0 && userSettings?.show_scene_titles === true && (
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

                    {/* Streaming indicator: Thinking only when reasoning tokens are detected */}
                    <div className={`absolute top-0 right-0 ${isThinking ? 'bg-purple-600' : 'bg-pink-600'} text-white text-xs px-2 py-1 rounded-full animate-pulse`}>
                      {isThinking ? 'Thinking...' : 'Generating...'}
                    </div>
                  </div>
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
                    <div className="flex gap-2">
                      <MicrophoneButton
                        onTranscriptUpdate={(text) => {
                          // Real-time update while recording - replace with STT text
                          setCustomPrompt(text);
                        }}
                        onTranscriptComplete={(text) => {
                          // Final transcript when stopped - replace with STT text
                          setCustomPrompt(text);
                        }}
                        disabled={isGenerating || isStreaming}
                        showPreview={true}
                      />
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
              </div>
            )}

            {/* Note: Continue Input is now handled by SceneVariantDisplay component for last scene */}

            {/* More Button - Keep in DOM but hide with opacity to prevent layout shifts */}
            {story && story.scenes.length > 0 && story.scenes[story.scenes.length - 1].variant_id && (
              <div className={`flex justify-center mt-6 transition-opacity duration-200 ${
                !isGenerating && !isStreaming && !isRegenerating && !isStreamingContinuation
                  ? 'opacity-100 pointer-events-auto'
                  : 'opacity-0 pointer-events-none'
              }`}>
                <button 
                  onClick={() => {
                    const lastScene = story.scenes[story.scenes.length - 1];
                    if (lastScene.variant_id) {
                      generateMoreOptions(lastScene.variant_id);
                    }
                  }}
                  disabled={isGeneratingMoreOptions || isGenerating || isStreaming || isRegenerating || isStreamingContinuation}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                    isGeneratingMoreOptions 
                      ? 'bg-gray-600 text-gray-400 cursor-not-allowed opacity-50' 
                      : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }`}
                >
                  {isGeneratingMoreOptions ? (
                    <>
                      <span className="animate-spin inline-block mr-1">⚡</span>
                      Generating more choices...
                    </>
                  ) : (
                    'More choices'
                  )} 
                  {!isGeneratingMoreOptions && <span className="ml-1">ⓘ</span>}
                </button>
              </div>
            )}

            {/* Info Components */}
            <div className="mt-6 space-y-4">
              <ContextInfo storyId={storyId} />
            </div>
          </div>
        </div>
      </div>

      {/* Scroll to Bottom Button */}
      <button
        onClick={() => {
          if (storyContentRef.current) {
            storyContentRef.current.scrollTo({
              top: storyContentRef.current.scrollHeight,
              behavior: 'instant'
            });
          }
        }}
        className="fixed bottom-4 left-4 z-50 p-3 bg-gray-700/80 hover:bg-gray-600 text-white rounded-full shadow-lg backdrop-blur-sm transition-all"
        aria-label="Scroll to bottom"
        title="Scroll to bottom"
      >
        <ArrowDownIcon className="h-5 w-5" />
      </button>

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
          storyId={storyId}
          chapterId={currentChapterId}
          onOpenCharacterWizard={() => setShowCharacterWizard(true)}
        />
      )}

      {/* Character Wizard Modal */}
      {showCharacterWizard && (
        <CharacterWizard
          storyId={storyId}
          chapterId={currentChapterId}
          branchId={currentBranchId}
          onCharacterCreated={handleCharacterCreated}
          onClose={() => setShowCharacterWizard(false)}
        />
      )}

      {/* Story Character Voice Editor Modal */}
      <StoryCharacterVoiceEditor
        storyId={storyId}
        branchId={currentBranchId}
        isOpen={showCharacterVoiceEditor}
        onClose={() => setShowCharacterVoiceEditor(false)}
      />

      {/* Character Role Editor Modal */}
      <CharacterRoleEditor
        storyId={storyId}
        branchId={currentBranchId}
        isOpen={showCharacterRoleEditor}
        onClose={() => setShowCharacterRoleEditor(false)}
      />

      {/* Story Character Manager Modal */}
      <StoryCharacterManager
        storyId={storyId}
        branchId={currentBranchId}
        isOpen={showStoryCharacterManager}
        onClose={() => setShowStoryCharacterManager(false)}
      />

      {/* Branch Creation Modal */}
      {showBranchCreationModal && (
        <BranchCreationModal
          storyId={storyId}
          currentSceneSequence={story?.scenes?.length || 1}
          preselectedScene={branchCreationFromScene}
          onClose={() => {
            setShowBranchCreationModal(false);
            setBranchCreationFromScene(1);
          }}
          onBranchCreated={(branch) => {
            setShowBranchCreationModal(false);
            setBranchCreationFromScene(1);
            setCurrentBranchId(branch.id);
            loadStory(true, false, branch.id);
          }}
        />
      )}

      {/* Image Gallery Modal */}
      <ImageGallery
        storyId={storyId}
        isOpen={showGallery}
        onClose={() => setShowGallery(false)}
        scenes={story?.scenes?.map(s => ({
          id: s.id,
          sequence_number: s.sequence_number,
          title: s.title,
        })) || []}
      />

      {/* Chapter Wizard Modal */}
      {showChapterWizard && (() => {
        // Check if we have a brainstorm scenario to pre-populate
        const brainstormScenario = searchParams?.get('brainstorm_scenario');
        const decodedScenario = brainstormScenario ? decodeURIComponent(brainstormScenario) : undefined;
        
        return (
          <ChapterWizard
            storyId={storyId}
            chapterNumber={activeChapter?.chapter_number || 1}
            chapterId={activeChapter?.id || undefined}
            storyArc={story?.story_arc}
            onBrainstorm={() => {
              setBrainstormChapterId(activeChapter?.id);
              setShowChapterBrainstormModal(true);
            }}
            initialData={{
              title: activeChapter?.title || undefined,
              description: activeChapter?.description || undefined,
              characters: activeChapter?.characters || [],
              // Use brainstorm plot data if available, otherwise use existing chapter data
              location_name: brainstormPlot?.location || activeChapter?.location_name || undefined,
              time_period: activeChapter?.time_period || undefined,  // Keep time_period separate from mood
              scenario: brainstormPlot?.opening_situation || activeChapter?.scenario || decodedScenario || undefined,
              continues_from_previous: activeChapter?.continues_from_previous !== undefined ? activeChapter.continues_from_previous : true,
              arc_phase_id: (activeChapter as any)?.arc_phase_id,
              // Use brainstorm plot if available, otherwise use chapter's existing plot
              chapter_plot: brainstormPlot || (activeChapter as any)?.chapter_plot,
              // Pass recommended characters from brainstorm
              recommended_characters: brainstormPlot?.recommended_characters || [],
              // Pass mood separately for display
              mood: brainstormPlot?.mood || undefined
            }}
            brainstormSessionId={brainstormSessionId}
            onComplete={(data) => {
              // Clear brainstorm data after completion
              setBrainstormPlot(null);
              setBrainstormSessionId(undefined);
              handleChapterWizardComplete(data);
            }}
            onCancel={() => {
              // Clear brainstorm data on cancel too
              setBrainstormPlot(null);
              setBrainstormSessionId(undefined);
              handleChapterWizardCancel();
            }}
          />
        );
      })()}

      {/* TTS Settings Modal */}
      <TTSSettingsModal
        isOpen={showTTSSettings}
        onClose={() => setShowTTSSettings(false)}
        onSaved={() => {
          // Optionally refresh story or show success message
        }}
      />
      
      {/* Story Settings Edit Modal */}
      <StorySettingsModal
        isOpen={showEditStoryModal}
        onClose={() => setShowEditStoryModal(false)}
        storyId={storyId}
        onSaved={() => {
          loadStory(); // Reload story after save
        }}
      />
      
      {/* Character Interactions Modal */}
      <CharacterInteractionsModal
        isOpen={showInteractionsModal}
        onClose={() => setShowInteractionsModal(false)}
        storyId={storyId}
        branchId={currentBranchId}
        storyTitle={story?.title || ''}
      />

      {/* Entity States Modal */}
      <EntityStatesModal
        isOpen={showEntityStatesModal}
        onClose={() => setShowEntityStatesModal(false)}
        storyId={storyId}
        branchId={currentBranchId}
        storyTitle={story?.title || ''}
      />

      {/* Contradictions Modal */}
      <ContradictionsModal
        isOpen={showContradictionsModal}
        onClose={() => setShowContradictionsModal(false)}
        storyId={storyId}
        branchId={currentBranchId}
        storyTitle={story?.title || ''}
      />
      
      {/* Chapter Brainstorm Modal */}
      {showChapterBrainstormModal && (
        <ChapterBrainstormModal
          isOpen={showChapterBrainstormModal}
          onClose={() => {
            setShowChapterBrainstormModal(false);
            setBrainstormChapterId(undefined);
          }}
          storyId={storyId}
          chapterId={brainstormChapterId}
          storyArc={story?.story_arc}
          enableStreaming={userSettings?.generation_preferences?.enable_streaming !== false}
          showThinkingContent={userSettings?.llm_settings?.show_thinking_content !== false}
          onPlotApplied={(plot, sessionId) => {
            setShowChapterBrainstormModal(false);
            setBrainstormChapterId(undefined);
            
            if (plot) {
              // Plot returned for new chapter - store it for ChapterWizard
              setBrainstormPlot(plot);
              setBrainstormSessionId(sessionId);
              console.log('[Story] Brainstorm plot saved for new chapter:', plot);
            } else {
              // Plot was applied to existing chapter
              loadStory(); // Reload to get updated chapter plot
            }
          }}
        />
      )}
      
      {/* Story Summary Modal */}
      {showSummaryModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[60] p-4">
          <div className="bg-gray-800 rounded-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
            {/* Header - fixed */}
            <div className="flex items-center justify-between p-6 border-b border-gray-700 flex-shrink-0">
              <h2 className="text-xl font-bold text-white">Story Summary & Context</h2>
              <div className="flex items-center space-x-3">
                <button
                  onClick={handleGenerateAISummary}
                  disabled={isGeneratingAISummary}
                  className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  {isGeneratingAISummary ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>Generating...</span>
                    </>
                  ) : (
                    <>
                      <DocumentTextIcon className="w-4 h-4" />
                      <span>Summarize Now</span>
                    </>
                  )}
                </button>
                <button
                  onClick={() => setShowSummaryModal(false)}
                  className="text-gray-400 hover:text-white p-2 hover:bg-gray-700 rounded-lg"
                >
                  ✕
                </button>
              </div>
            </div>
            
            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto p-6">
              {loadingSummary ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                  <span className="ml-3 text-gray-300">Loading summary...</span>
                </div>
              ) : storySummary?.error ? (
                <div className="text-center py-8 text-red-400">
                  {storySummary.error}
                </div>
              ) : storySummary ? (
                <div className="space-y-6">
                  {/* Story Info */}
                  <div className="bg-gray-700/50 rounded-lg p-4">
                    <h3 className="font-semibold text-white mb-2">{storySummary.story?.title}</h3>
                    <p className="text-gray-300 text-sm mb-2">{storySummary.story?.description}</p>
                    <div className="text-xs text-gray-400">
                      Genre: {storySummary.story?.genre || 'Not specified'} • 
                      Scenes: {storySummary.story?.total_scenes}
                    </div>
                  </div>

                  {/* Context Management Info */}
                  {storySummary.context_info && (
                    <div className="bg-gray-700/30 rounded-lg p-4">
                      <h3 className="font-semibold text-blue-300 mb-3">Context Management</h3>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-gray-400">Total Scenes:</span>
                          <span className="ml-2 text-white">{storySummary.context_info.total_scenes}</span>
                        </div>
                        <div>
                          <span className="text-gray-400">Recent (Full):</span>
                          <span className="ml-2 text-green-400">{storySummary.context_info.recent_scenes}</span>
                        </div>
                        <div>
                          <span className="text-gray-400">Summarized:</span>
                          <span className="ml-2 text-blue-400">{storySummary.context_info.summarized_scenes}</span>
                        </div>
                        <div>
                          <span className="text-gray-400">Budget:</span>
                          <span className="ml-2 text-white">{storySummary.context_info.context_budget.toLocaleString()} tokens</span>
                        </div>
                      </div>
                      
                      {/* Usage Bar */}
                      <div className="mt-4">
                        <div className="flex justify-between text-xs text-gray-400 mb-1">
                          <span>Context Usage</span>
                          <span>{storySummary.context_info.estimated_tokens.toLocaleString()} / {storySummary.context_info.context_budget.toLocaleString()} tokens</span>
                        </div>
                        <div className="w-full bg-gray-600 rounded-full h-2">
                          <div 
                            className={`h-2 rounded-full ${
                              storySummary.context_info.usage_percentage > 80 ? 'bg-red-500' :
                              storySummary.context_info.usage_percentage > 60 ? 'bg-yellow-500' :
                              'bg-blue-500'
                            }`}
                            style={{ width: `${Math.min(100, storySummary.context_info.usage_percentage)}%` }}
                          ></div>
                        </div>
                        <div className="text-xs text-gray-400 mt-1">
                          {storySummary.context_info.usage_percentage.toFixed(1)}% used
                        </div>
                      </div>
                    </div>
                  )}

                  {/* AI Generated Summary */}
                  {(aiSummary || isGeneratingAISummary) && (
                    <div className="bg-blue-900/30 border border-blue-600/30 rounded-lg p-4">
                      <h3 className="font-semibold text-blue-300 mb-3">AI Generated Summary</h3>
                      {isGeneratingAISummary ? (
                        <div className="flex items-center justify-center py-8">
                          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-400"></div>
                          <span className="ml-3 text-gray-300">Generating comprehensive story summary...</span>
                        </div>
                      ) : aiSummary ? (
                        <div className="text-gray-300 text-sm leading-relaxed h-96 overflow-y-auto border border-blue-600/50 rounded p-3 bg-blue-900/20">
                          {aiSummary}
                        </div>
                      ) : null}
                      <div className="text-xs text-blue-400 mt-2">
                        This is an AI-generated comprehensive summary using advanced prompts
                      </div>
                    </div>
                  )}

                  {/* Story Summary */}
                  <div className="bg-gray-700/30 rounded-lg p-4">
                    <h3 className="font-semibold text-green-300 mb-3">Story Summary</h3>
                    <div className="text-gray-300 text-sm leading-relaxed h-64 overflow-y-auto border border-gray-600/50 rounded p-3 bg-gray-800/50">
                      {storySummary.summary}
                    </div>
                    <div className="text-xs text-gray-400 mt-2">
                      Scroll to read the complete summary
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* Floating Delete Button - Appears when scenes are selected */}
      {isInDeleteMode && selectedScenesForDeletion.length > 0 && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50">
          <button
            onClick={() => deleteScenesFromSelected()}
            disabled={isDeletingScenes}
            className="flex items-center gap-3 px-6 py-4 bg-red-600 hover:bg-red-700 text-white rounded-full shadow-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed border-2 border-red-500"
          >
            {isDeletingScenes ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                <span>Deleting...</span>
              </>
            ) : (
              <>
                <Trash2 className="w-5 h-5" />
                <span>Delete {selectedScenesForDeletion.length} Scene{selectedScenesForDeletion.length !== 1 ? 's' : ''}</span>
              </>
            )}
          </button>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteConfirmation && story && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg max-w-md w-full p-6 border border-gray-700">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-red-600/20 rounded-lg">
                <AlertCircle className="w-6 h-6 text-red-400" />
              </div>
              <h3 className="text-xl font-bold text-white">Confirm Deletion</h3>
            </div>
            
            <p className="text-gray-300 mb-2">
              Are you sure you want to delete scenes from scene {Math.min(...selectedScenesForDeletion)} onwards?
            </p>
            
            {(() => {
              const earliestSequence = Math.min(...selectedScenesForDeletion);
              const scenesToDelete = story.scenes.filter(scene => scene.sequence_number >= earliestSequence);
              return (
                <div className="mb-6">
                  <p className="text-red-400 font-semibold mb-2">
                    This will permanently delete {scenesToDelete.length} scene{scenesToDelete.length !== 1 ? 's' : ''}:
                  </p>
                  <div className="bg-gray-900/50 rounded p-3 max-h-32 overflow-y-auto">
                    <ul className="text-sm text-gray-400 space-y-1">
                      {scenesToDelete.map((scene, idx) => (
                        <li key={scene.id}>
                          • Scene {scene.sequence_number}: {scene.title || 'Untitled'}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    All variants, choices, and related data will also be deleted. This action cannot be undone.
                  </p>
                </div>
              );
            })()}
            
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowDeleteConfirmation(false);
                }}
                className="flex-1 px-4 py-2 border border-gray-600 rounded-lg text-gray-300 hover:bg-gray-700 font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  if (!story || selectedScenesForDeletion.length === 0) return;
                  
                  const earliestSequence = Math.min(...selectedScenesForDeletion);
                  
                  try {
                    setIsDeletingScenes(true);
                    await apiClient.deleteScenesFromSequence(story.id, earliestSequence);
                    
                    // Exit delete mode and close confirmation
                    setIsInDeleteMode(false);
                    setSelectedScenesForDeletion([]);
                    setShowDeleteConfirmation(false);
                    
                    // Reload the story
                    await loadStory();
                    
                  } catch (error) {
                    console.error('Failed to delete scenes:', error);
                    setError(error instanceof Error ? error.message : 'Failed to delete scenes');
                    setShowDeleteConfirmation(false);
                  } finally {
                    setIsDeletingScenes(false);
                  }
                }}
                disabled={isDeletingScenes}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDeletingScenes ? 'Deleting...' : 'Delete Scenes'}
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Chapter Progress Indicator */}
      <ChapterProgressIndicator
        storyId={storyId}
        chapterId={activeChapterId}
        enabled={userSettings?.generation_preferences?.enable_chapter_plot_tracking !== false}
        refreshTrigger={plotProgressRefreshTrigger}
      />
    </div>
  );
}
