'use client';

import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, ChevronDown, BookOpen, AlertCircle, Edit2, Save, X, Plus, CheckCircle, RefreshCw, Trash2 } from 'lucide-react';
import apiClient, { getApiBaseUrl, StoryArc } from '@/lib/api';
import { getAuthToken } from '@/utils/jwt';
import dynamic from 'next/dynamic';

const ChapterWizard = dynamic(() => import('@/components/ChapterWizard'), {
  loading: () => null,
  ssr: false
});

const ChapterBrainstormModal = dynamic(() => import('@/components/ChapterBrainstormModal'), {
  loading: () => null,
  ssr: false
});

interface Chapter {
  id: number;
  story_id: number;
  chapter_number: number;
  title: string | null;
  description: string | null;
  plot_point: string | null;
  story_so_far: string | null;
  auto_summary: string | null;
  status: 'draft' | 'active' | 'completed';
  creation_step?: number | null;
  context_tokens_used: number;
  scenes_count: number;
  last_summary_scene_count: number;
  created_at: string;
  updated_at: string | null;
  characters?: Array<{
    id: number;
    name: string;
    role: string | null;
    description: string | null;
  }>;
  location_name?: string | null;
  time_period?: string | null;
  scenario?: string | null;
  continues_from_previous?: boolean;
  chapter_plot?: any;
  arc_phase_id?: string | null;
}

interface ChapterContextStatus {
  chapter_id: number;
  current_tokens: number;
  max_tokens: number;
  percentage_used: number;
  should_create_new_chapter: boolean;
  reason: string | null;
  scenes_count: number;
  avg_generation_time?: number | null;
}

interface ChapterSidebarProps {
  storyId: number;
  isOpen: boolean;
  onToggle: () => void;
  onChapterChange?: (newChapterId?: number) => void; // Callback when a new chapter is activated
  onChapterSelect?: (chapterId: number) => void; // Callback when user selects a chapter to view
  currentChapterId?: number; // Currently selected chapter for viewing
  storyArc?: StoryArc | null; // Story arc for display
  enableStreaming?: boolean; // Whether streaming is enabled for LLM responses
  showThinkingContent?: boolean; // Whether to show LLM thinking content
  initialActiveChapter?: any; // Pre-fetched active chapter from parent (avoids redundant API call)
  initialContextPercent?: number; // Pre-fetched context percentage from parent
}

export default function ChapterSidebar({ storyId, isOpen, onToggle, onChapterChange, onChapterSelect, currentChapterId, storyArc, enableStreaming = true, showThinkingContent = true, initialActiveChapter, initialContextPercent }: ChapterSidebarProps) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeChapter, setActiveChapter] = useState<Chapter | null>(null);
  const [contextStatus, setContextStatus] = useState<ChapterContextStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Story So Far editing state
  const [isEditingStorySoFar, setIsEditingStorySoFar] = useState(false);
  const [storySoFarDraft, setStorySoFarDraft] = useState('');
  const [isSavingStorySoFar, setIsSavingStorySoFar] = useState(false);
  
  // Chapter Summary editing state
  const [isEditingChapterSummary, setIsEditingChapterSummary] = useState(false);
  const [chapterSummaryDraft, setChapterSummaryDraft] = useState('');
  const [isSavingChapterSummary, setIsSavingChapterSummary] = useState(false);
  
  // New Chapter creation state
  const [isCreatingChapter, setIsCreatingChapter] = useState(false);
  const [showChapterWizard, setShowChapterWizard] = useState(false);
  const [editingChapterId, setEditingChapterId] = useState<number | null>(null); // Track which chapter is being edited
  const [newChapterTitle, setNewChapterTitle] = useState('');
  const [newChapterDescription, setNewChapterDescription] = useState('');
  const [isSubmittingNewChapter, setIsSubmittingNewChapter] = useState(false);
  const [isConcludingChapter, setIsConcludingChapter] = useState(false);
  
  // Story arc expand/collapse state
  const [expandedArcPhaseId, setExpandedArcPhaseId] = useState<string | null>(null);

  // Summary generation state
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [isGeneratingStorySummary, setIsGeneratingStorySummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [storySummaryError, setStorySummaryError] = useState<string | null>(null);
  
  // Chapter activation state
  const [chapterToActivate, setChapterToActivate] = useState<Chapter | null>(null);
  const [isActivatingChapter, setIsActivatingChapter] = useState(false);
  
  // Chapter brainstorm state
  const [showBrainstormModal, setShowBrainstormModal] = useState(false);
  const [brainstormChapterId, setBrainstormChapterId] = useState<number | undefined>(undefined);
  const [brainstormPlot, setBrainstormPlot] = useState<any>(null);
  const [brainstormSessionId, setBrainstormSessionId] = useState<number | undefined>(undefined);
  const [brainstormArcPhaseId, setBrainstormArcPhaseId] = useState<string | undefined>(undefined);

  // Resume creation state
  const [isResumingCreation, setIsResumingCreation] = useState(false);

  useEffect(() => {
    loadChapters();
  }, [storyId]);

  const loadChapters = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load all chapters
      const chaptersData = await apiClient.getChapters(storyId);
      setChapters(chaptersData);

      // Use pre-fetched active chapter if available (avoids redundant API calls on initial load)
      if (initialActiveChapter && !activeChapter) {
        setActiveChapter(initialActiveChapter);
        if (initialContextPercent !== undefined) {
          setContextStatus({
            chapter_id: initialActiveChapter.id,
            current_tokens: 0,
            max_tokens: 0,
            percentage_used: initialContextPercent,
            should_create_new_chapter: false,
            reason: null,
            scenes_count: initialActiveChapter.scenes_count || 0
          });
        }
      } else {
        // Fetch fresh data (for refresh-key remounts or when no initial data)
        try {
          const activeChapterData = await apiClient.getActiveChapter(storyId);
          setActiveChapter(activeChapterData);

          // Load context status for active chapter (only if chapter has scenes)
          if (activeChapterData && activeChapterData.scenes_count > 0) {
            try {
              const statusData = await apiClient.getChapterContextStatus(storyId, activeChapterData.id);
              setContextStatus(statusData);
            } catch (err) {
              console.warn('Failed to load context status:', err);
              // Don't fail the whole load if context status fails
              setContextStatus(null);
            }
          }
        } catch (err) {
          // No active chapter found - this is expected when:
          // 1. Story is newly created and no chapter exists yet
          // 2. All chapters are completed and user needs to create a new one
          if (err instanceof Error && (err.message.includes('404') || err.message.includes('No active chapter'))) {
            setActiveChapter(null);
            // Don't show error - user should create a new chapter
          } else {
            console.error('Failed to load active chapter:', err);
            setError(err instanceof Error ? err.message : 'Failed to load active chapter');
          }
        }
      }
    } catch (err) {
      console.error('Failed to load chapters:', err);
      setError(err instanceof Error ? err.message : 'Failed to load chapters');
    } finally {
      setLoading(false);
    }
  };

  const handleEditStorySoFar = () => {
    // Initialize with auto_summary if story_so_far is empty, otherwise use existing story_so_far
    const initialContent = activeChapter?.story_so_far || activeChapter?.auto_summary || '';
    setStorySoFarDraft(initialContent);
    setIsEditingStorySoFar(true);
  };

  const handleSaveStorySoFar = async () => {
    if (!activeChapter) return;
    
    setIsSavingStorySoFar(true);
    try {
      await apiClient.updateChapter(storyId, activeChapter.id, {
        story_so_far: storySoFarDraft
      });
      
      // Update local state
      setActiveChapter({
        ...activeChapter,
        story_so_far: storySoFarDraft
      });
      
      // Also update in chapters list
      setChapters(prev => prev.map(ch => 
        ch.id === activeChapter.id 
          ? { ...ch, story_so_far: storySoFarDraft }
          : ch
      ));
      
      setIsEditingStorySoFar(false);
    } catch (err) {
      console.error('Failed to save story so far:', err);
      alert('Failed to save changes. Please try again.');
    } finally {
      setIsSavingStorySoFar(false);
    }
  };

  const handleCancelEdit = () => {
    setIsEditingStorySoFar(false);
    setStorySoFarDraft('');
  };

  const handleEditChapterSummary = () => {
    const initialContent = activeChapter?.auto_summary || '';
    setChapterSummaryDraft(initialContent);
    setIsEditingChapterSummary(true);
  };

  const handleSaveChapterSummary = async () => {
    if (!activeChapter) return;
    
    setIsSavingChapterSummary(true);
    try {
      if (!activeChapter.id) {
        alert('Cannot save: chapter ID is missing');
        return;
      }
      await apiClient.updateChapter(storyId, activeChapter.id, {
        auto_summary: chapterSummaryDraft
      });
      
      // Update local state
      setActiveChapter({
        ...activeChapter,
        auto_summary: chapterSummaryDraft
      });
      
      // Also update in chapters list
      setChapters(prev => prev.map(ch => 
        ch.id === activeChapter.id 
          ? { ...ch, auto_summary: chapterSummaryDraft }
          : ch
      ));
      
      setIsEditingChapterSummary(false);
    } catch (err) {
      console.error('Failed to save chapter summary:', err);
      alert('Failed to save changes. Please try again.');
    } finally {
      setIsSavingChapterSummary(false);
    }
  };

  const handleCancelChapterSummaryEdit = () => {
    setIsEditingChapterSummary(false);
    setChapterSummaryDraft('');
  };

  const handleCreateNewChapter = () => {
    // Show chapter wizard instead of simple modal
    const nextChapterNum = (chapters.length || 0) + 1;
    setNewChapterTitle(`Chapter ${nextChapterNum}`);
    setNewChapterDescription('');
    setEditingChapterId(null); // Clear edit mode
    setShowChapterWizard(true);
  };

  const handleEditChapter = () => {
    if (!activeChapter) return;
    setEditingChapterId(activeChapter.id);
    setShowChapterWizard(true);
  };
  
  const handleConcludeChapter = async () => {
    if (!activeChapter) return;
    
    if (activeChapter.scenes_count === 0) {
      alert('Cannot conclude a chapter with no scenes.');
      return;
    }
    
    if (!confirm(`Are you sure you want to conclude Chapter ${activeChapter.chapter_number}? This will generate a final scene and mark the chapter as completed.`)) {
      return;
    }
    
    setIsConcludingChapter(true);
    try {
      await apiClient.concludeChapter(storyId, activeChapter.id);
      
      // Reload chapters
      await loadChapters();
      
      // Notify parent component
      if (onChapterChange) {
        onChapterChange();
      }
      
      alert(`Chapter ${activeChapter.chapter_number} concluded successfully!`);
    } catch (err) {
      console.error('Failed to conclude chapter:', err);
      alert('Failed to conclude chapter. Please try again.');
    } finally {
      setIsConcludingChapter(false);
    }
  };

  const handleDeleteChapter = async (chapter: Chapter) => {
    if (!chapter) return;
    
    // Safety check: prevent deleting the only chapter
    if (chapters.length <= 1) {
      alert('Cannot delete the only chapter in the story. Stories must have at least one chapter.');
      return;
    }
    
    // Confirmation with warning
    const scenesWarning = chapter.scenes_count > 0 
      ? `\n\nWARNING: This chapter has ${chapter.scenes_count} scene(s) that will also be deleted!`
      : '';
    
    if (!confirm(
      `Are you sure you want to DELETE Chapter ${chapter.chapter_number}: "${chapter.title || 'Untitled'}"?` +
      scenesWarning +
      `\n\nThis action CANNOT be undone!`
    )) {
      return;
    }
    
    // Double confirmation for chapters with content
    if (chapter.scenes_count > 0) {
      if (!confirm(
        `FINAL CONFIRMATION:\n\nYou are about to permanently delete Chapter ${chapter.chapter_number} and all ${chapter.scenes_count} scene(s).\n\nType YES in your mind and click OK to proceed.`
      )) {
        return;
      }
    }
    
    try {
      setLoading(true);
      await apiClient.deleteChapter(storyId, chapter.id);
      
      // Reload chapters
      await loadChapters();
      
      // Notify parent component
      if (onChapterChange) {
        onChapterChange();
      }
      
      alert(`Chapter ${chapter.chapter_number} deleted successfully.`);
    } catch (err: any) {
      console.error('Failed to delete chapter:', err);
      const errorMessage = err?.response?.data?.detail || 'Failed to delete chapter. Please try again.';
      alert(`Error: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  };

  const handleChapterClick = (chapter: Chapter) => {
    // If clicking the active chapter, do nothing (it's already active)
    if (chapter.id === activeChapter?.id) {
      return;
    }
    
    // Show confirmation dialog to switch active chapter
    setChapterToActivate(chapter);
  };

  const handleConfirmActivateChapter = async () => {
    if (!chapterToActivate) return;
    
    setIsActivatingChapter(true);
    try {
      await apiClient.setActiveChapter(storyId, chapterToActivate.id);
      
      // Reload chapters to get updated statuses
      await loadChapters();

      // Notify parent component to reload story with the new chapter
      if (onChapterChange) {
        onChapterChange(chapterToActivate.id);
      }

      // Clear the dialog
      setChapterToActivate(null);
      
      alert(`Chapter ${chapterToActivate.chapter_number} is now active!`);
    } catch (err) {
      console.error('Failed to activate chapter:', err);
      alert('Failed to switch active chapter. Please try again.');
    } finally {
      setIsActivatingChapter(false);
    }
  };

  const handleCancelActivateChapter = () => {
    setChapterToActivate(null);
  };

  const handleResumeCreation = async (chapter: Chapter) => {
    setIsResumingCreation(true);
    try {
      await apiClient.resumeChapterCreation(
        storyId,
        chapter.id,
        (status) => {
          console.log('[ChapterSidebar] Resume status:', status);
        }
      );
      // Reload chapters to get updated state
      await loadChapters();
      if (onChapterChange) {
        onChapterChange(chapter.id);
      }
    } catch (err) {
      console.error('Failed to resume chapter creation:', err);
      setError(err instanceof Error ? err.message : 'Failed to resume chapter setup');
    } finally {
      setIsResumingCreation(false);
    }
  };

  const handleDiscardIncompleteChapter = async (chapter: Chapter) => {
    if (!confirm(
      `Discard Chapter ${chapter.chapter_number}: "${chapter.title || 'Untitled'}"?\n\nThis will delete the incomplete chapter.`
    )) {
      return;
    }
    try {
      setLoading(true);
      await apiClient.deleteChapter(storyId, chapter.id);
      await loadChapters();
      if (onChapterChange) {
        onChapterChange();
      }
    } catch (err: any) {
      console.error('Failed to discard chapter:', err);
      const errorMessage = err?.response?.data?.detail || 'Failed to discard chapter.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleChapterWizardComplete = async (
    chapterData: {
      title?: string;
      description?: string;
      story_character_ids?: number[];
      character_ids?: number[];
      character_roles?: { [characterId: number]: string };
      location_name?: string;
      time_period?: string;
      scenario?: string;
      continues_from_previous?: boolean;
      chapter_plot?: any;
      brainstorm_session_id?: number;
      arc_phase_id?: string;
    },
    onStatusUpdate?: (status: { message: string; step: string }) => void
  ) => {
    setIsSubmittingNewChapter(true);
    try {
      console.log('[ChapterSidebar] handleChapterWizardComplete received:', {
        chapter_plot: chapterData.chapter_plot,
        climax: chapterData.chapter_plot?.climax,
        brainstorm_session_id: chapterData.brainstorm_session_id
      });

      if (editingChapterId) {
        // Update existing chapter
        await apiClient.updateChapter(storyId, editingChapterId, {
          title: chapterData.title,
          description: chapterData.description,
          story_character_ids: chapterData.story_character_ids,
          character_ids: chapterData.character_ids,
          character_roles: chapterData.character_roles,
          location_name: chapterData.location_name,
          time_period: chapterData.time_period,
          scenario: chapterData.scenario,
          continues_from_previous: chapterData.continues_from_previous,
          chapter_plot: chapterData.chapter_plot,
          brainstorm_session_id: chapterData.brainstorm_session_id,
          arc_phase_id: chapterData.arc_phase_id
        });
        
        // Reload chapters to get updated list
        await loadChapters();
        
        // Notify parent component to reload story
        if (onChapterChange) {
          onChapterChange();
        }
        
        // Close wizard
        setShowChapterWizard(false);
        setEditingChapterId(null);
        
        // Show success message
        alert('Chapter updated successfully!');
      } else {
        // Create new chapter
        // Use previous chapter's auto_summary as story_so_far for new chapter
        const storySoFar = activeChapter?.auto_summary || activeChapter?.story_so_far || 'Continuing the story...';
        
        const handleStatusUpdate = (status: { message: string; step: string }) => {
          // Status updates are handled by ChapterWizard
        };
        
        let enrichmentFailed = false;
        const wrappedStatusUpdate = (status: { message: string; step: string }) => {
          if (status.step === 'enrichment_failed') {
            enrichmentFailed = true;
          }
          if (onStatusUpdate) {
            onStatusUpdate(status);
          } else {
            handleStatusUpdate(status);
          }
        };

        const newChapter = await apiClient.createChapter(
          storyId,
          {
            title: chapterData.title || newChapterTitle || undefined,
            description: chapterData.description || newChapterDescription || undefined,
            story_so_far: storySoFar,
            story_character_ids: chapterData.story_character_ids,
            character_ids: chapterData.character_ids,
            character_roles: chapterData.character_roles,
            location_name: chapterData.location_name,
            time_period: chapterData.time_period,
            scenario: chapterData.scenario,
            continues_from_previous: chapterData.continues_from_previous,
            chapter_plot: chapterData.chapter_plot,
            brainstorm_session_id: chapterData.brainstorm_session_id
          },
          wrappedStatusUpdate
        );

        // Reload chapters to get updated list
        await loadChapters();

        // Notify parent component to reload story with the new chapter
        if (onChapterChange) {
          onChapterChange(newChapter.id);
        }

        // Close wizard
        setShowChapterWizard(false);
        setIsCreatingChapter(false);
        setNewChapterTitle('');
        setNewChapterDescription('');

        // Show success message (with warning if enrichment failed)
        if (enrichmentFailed) {
          alert(`Chapter ${newChapter.chapter_number} created! Story context generation failed but you can retry from the chapter list.`);
        } else {
          alert(`Chapter ${newChapter.chapter_number} created successfully! You're now in the new chapter.`);
        }
      }
    } catch (err) {
      console.error('Failed to save chapter:', err);
      setIsSubmittingNewChapter(false);
      const errMsg = err instanceof Error ? err.message : 'Unknown error';
      if (editingChapterId) {
        alert('Failed to update chapter. Please try again.');
      } else {
        // Check if a chapter may have been partially created (reload to detect)
        await loadChapters();
        alert(`Failed to create new chapter: ${errMsg}`);
      }
      throw err; // Re-throw so ChapterWizard can catch and reset loading state
    }
  };
  
  const handleChapterWizardCancel = () => {
    setShowChapterWizard(false);
    setIsCreatingChapter(false);
    setEditingChapterId(null);
    setNewChapterTitle('');
    setNewChapterDescription('');
  };

  const handleCancelNewChapter = () => {
    setIsCreatingChapter(false);
    setNewChapterTitle('');
    setNewChapterDescription('');
  };

  const handleSubmitNewChapter = async () => {
    if (!newChapterTitle.trim()) return;
    
    setIsSubmittingNewChapter(true);
    try {
      const newChapter = await apiClient.createChapter(
        storyId,
        {
          title: newChapterTitle.trim(),
          description: newChapterDescription.trim() || undefined,
        }
      );
      
      // Reload chapters to get updated list
      await loadChapters();
      
      // Notify parent component to reload story
      if (onChapterChange) {
        onChapterChange();
      }
      
      // Close modal
      setIsCreatingChapter(false);
      setNewChapterTitle('');
      setNewChapterDescription('');
      
      // Show success message
      alert(`Chapter ${newChapter.chapter_number} created successfully!`);
    } catch (err) {
      console.error('Failed to create chapter:', err);
      alert('Failed to create new chapter. Please try again.');
    } finally {
      setIsSubmittingNewChapter(false);
    }
  };

  const handleGenerateSummary = async () => {
    if (!activeChapter) return;
    
    setIsGeneratingSummary(true);
    setSummaryError(null);
    
    try {
      // Only regenerate story_so_far if this is not the first chapter
      const shouldRegenerateStorySoFar = activeChapter.chapter_number > 1;
      const response = await fetch(
        `${await getApiBaseUrl()}/api/stories/${storyId}/chapters/${activeChapter.id}/generate-summary?regenerate_story_so_far=${shouldRegenerateStorySoFar}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getAuthToken()}`,
            'Content-Type': 'application/json'
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to generate summary');
      }
      
      const data = await response.json();
      
      
      // Reload chapters to get updated summaries
      await loadChapters();
      
      // Notify parent to refresh if callback exists
      if (onChapterChange) {
        onChapterChange();
      }
      
      alert('✓ Chapter summary generated successfully!');
    } catch (err) {
      console.error('Failed to generate summary:', err);
      setSummaryError(err instanceof Error ? err.message : 'Failed to generate summary');
      alert('✗ Failed to generate chapter summary. Please try again.');
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const handleRegenerateStorySoFar = async () => {
    if (!activeChapter) return;
    
    setIsGeneratingSummary(true);
    setSummaryError(null);
    
    try {
      const response = await fetch(
        `${await getApiBaseUrl()}/api/stories/${storyId}/chapters/${activeChapter.id}/regenerate-story-so-far`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getAuthToken()}`,
            'Content-Type': 'application/json'
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to regenerate story so far');
      }
      
      const data = await response.json();
      
      
      // Reload chapters to get updated story_so_far
      await loadChapters();
      
      // Notify parent to refresh if callback exists
      if (onChapterChange) {
        onChapterChange();
      }
      
      alert('✓ Story so far regenerated successfully!');
    } catch (err) {
      console.error('Failed to regenerate story so far:', err);
      setSummaryError(err instanceof Error ? err.message : 'Failed to regenerate story so far');
      alert('✗ Failed to regenerate story so far. Please try again.');
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const handleGenerateStorySummary = async () => {
    if (!activeChapter) return;
    
    setIsGeneratingStorySummary(true);
    setStorySummaryError(null);
    
    try {
      // Call regenerate-story-so-far endpoint to regenerate and display story_so_far
      const response = await fetch(
        `${await getApiBaseUrl()}/api/stories/${storyId}/chapters/${activeChapter.id}/regenerate-story-so-far`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getAuthToken()}`,
            'Content-Type': 'application/json'
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to regenerate story so far');
      }
      
      const data = await response.json();
      
      // Reload chapters to get updated story_so_far
      await loadChapters();
      
      // Notify parent to refresh if callback exists
      if (onChapterChange) {
        onChapterChange();
      }
      
      alert('✓ Story So Far regenerated successfully!');
    } catch (err) {
      console.error('Failed to regenerate story so far:', err);
      setStorySummaryError(err instanceof Error ? err.message : 'Failed to regenerate story so far');
      alert('✗ Failed to regenerate story so far. Please try again.');
    } finally {
      setIsGeneratingStorySummary(false);
    }
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-500/10 text-green-400 border-green-500/20';
      case 'completed':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'draft':
        return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
      default:
        return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
    }
  };

  const getContextWarningColor = (percentage: number) => {
    if (percentage >= 80) return 'text-red-400';
    if (percentage >= 60) return 'text-yellow-400';
    return 'text-green-400';
  };

  // Don't render anything when closed - it's controlled by the main menu now
  if (!isOpen) {
    return null;
  }

  // Full modal when open
  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
        onClick={onToggle}
      />
      
      {/* Modal - Left side to match menu */}
      <div className="fixed inset-y-4 left-4 right-4 md:right-auto md:w-96 bg-slate-900 border border-slate-700 rounded-lg z-50 flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700 theme-banner">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5" style={{ color: 'var(--color-accentPrimary)' } as React.CSSProperties} />
            <h2 className="text-lg font-semibold">Chapters</h2>
          </div>
          <button
            onClick={onToggle}
            className="p-1 hover:bg-slate-700 rounded transition-colors"
            aria-label="Close chapters"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2"
                 style={{ borderColor: 'var(--color-accentPrimary)' } as React.CSSProperties}>
            </div>
          </div>
        ) : error ? (
          <div className="p-4 text-red-400 text-sm">
            {error}
          </div>
        ) : !activeChapter && chapters.length === 0 ? (
          <div className="p-4 text-center text-gray-400 text-sm">
            <BookOpen className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Chapters will appear once you start writing your story</p>
          </div>
        ) : (
          <>
            {/* Active Chapter Info */}
            {activeChapter && (
              <div className="p-4 border-b border-slate-700 bg-slate-800/50">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-lg">
                    {activeChapter.title || `Chapter ${activeChapter.chapter_number}`}
                  </h3>
                  <span className={`px-2 py-0.5 text-xs rounded border ${getStatusBadgeColor(activeChapter.status)}`}>
                    {activeChapter.status}
                  </span>
                </div>
                
                {activeChapter.description && (
                  <p className="text-sm text-gray-400 mb-3">
                    {activeChapter.description}
                  </p>
                )}

                {/* Chapter Actions - Always Visible */}
                <div className="mt-3 pt-3 border-t border-slate-700 space-y-3">
                  <h4 className="text-xs font-semibold text-gray-400 uppercase">Chapter Actions</h4>
                  
                  {/* Edit Chapter Button - Show for active chapter */}
                  {activeChapter && (
                    <button
                      onClick={handleEditChapter}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      <Edit2 className="w-4 h-4" />
                      Edit Chapter
                    </button>
                  )}
                  
                  {/* Create New Chapter Button - Always Visible */}
                  <button
                    onClick={handleCreateNewChapter}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-lg text-sm font-medium transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Create New Chapter
                  </button>
                  
                  {/* Scene Count */}
                  {activeChapter && (
                    <div className="text-sm text-gray-400 pt-2">
                      <span className="font-semibold">{activeChapter.scenes_count || 0}</span> scenes in this chapter
                    </div>
                  )}
                  
                  {/* Conclude Chapter Button - Show if chapter has scenes and is not completed */}
                  {activeChapter && (activeChapter.scenes_count || 0) > 0 && activeChapter.status !== 'completed' && (
                    <button
                      onClick={handleConcludeChapter}
                      disabled={isConcludingChapter}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors mt-2"
                    >
                      {isConcludingChapter ? (
                        <>
                          <span className="animate-spin">⚙️</span>
                          Concluding...
                        </>
                      ) : (
                        <>
                          <CheckCircle className="w-4 h-4" />
                          Conclude Chapter
                        </>
                      )}
                    </button>
                  )}
                  
                  {/* Delete Chapter Button - Show only if there are multiple chapters */}
                  {activeChapter && chapters.length > 1 && (
                    <button
                      onClick={() => handleDeleteChapter(activeChapter)}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-red-600/80 hover:bg-red-600 text-white rounded-lg text-sm font-medium transition-colors mt-2"
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete Chapter
                    </button>
                  )}
                  
                  {/* Debug info - remove after testing */}
                  {process.env.NODE_ENV === 'development' && (
                    <div className="text-xs text-gray-500 mt-2 p-2 bg-slate-800/50 rounded">
                      Debug: scenes={activeChapter.scenes_count || 0}, status={activeChapter.status}, 
                      show={(activeChapter.scenes_count || 0) > 0 && activeChapter.status !== 'completed' ? 'YES' : 'NO'}
                    </div>
                  )}
                </div>

                {/* Context Usage */}
                {contextStatus && (
                  <div className="mt-3 pt-3 border-t border-slate-700 space-y-2">
                    <h4 className="text-xs font-semibold text-gray-400 uppercase mb-2">Context Usage</h4>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-400">Usage:</span>
                      <span className={`font-semibold ${getContextWarningColor(contextStatus.percentage_used || 0)}`}>
                        {Math.round(contextStatus.percentage_used || 0)}%
                      </span>
                    </div>
                    
                    {/* Progress Bar */}
                    <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          (contextStatus.percentage_used || 0) >= 80
                            ? 'bg-red-500'
                            : (contextStatus.percentage_used || 0) >= 60
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                        }`}
                        style={{ width: `${Math.min(100, contextStatus.percentage_used || 0)}%` }}
                      />
                    </div>

                    <div className="text-xs text-gray-500">
                      {(contextStatus.current_tokens || 0).toLocaleString()} / {(contextStatus.max_tokens || 0).toLocaleString()} tokens
                    </div>

                    {/* Warning Message - Display only, no button */}
                    {contextStatus.should_create_new_chapter && (
                      <div className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400">
                        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                        <div className="flex-1">
                          <p className="font-semibold mb-1">Context Warning</p>
                          <p className="text-yellow-400/80">
                            {contextStatus.reason === 'context_limit' 
                              ? 'Context usage is high. Consider starting a new chapter to maintain quality.'
                              : 'Consider starting a new chapter.'}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Summary of Previous Chapters - Editable */}
                {/* Only show for chapters > 1, or if chapter 1 has a story_so_far (user-edited) */}
                {activeChapter.chapter_number > 1 && (activeChapter.story_so_far || activeChapter.auto_summary) && (
                  <div className="mt-3 pt-3 border-t border-slate-700">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-semibold text-gray-400 uppercase">Summary of Previous Chapters</h4>
                      <div className="flex items-center gap-1">
                        {chapters.length > 1 && (
                          <button
                            onClick={handleGenerateStorySummary}
                            disabled={isGeneratingStorySummary}
                            className="p-1 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Regenerate Story So Far from previous chapter summaries"
                          >
                            {isGeneratingStorySummary ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <RefreshCw className="w-3 h-3" />
                            )}
                          </button>
                        )}
                        <button
                          onClick={handleEditStorySoFar}
                          className="p-1 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white"
                          title="Edit story summary"
                        >
                          <Edit2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                    <div className="max-h-32 overflow-y-auto">
                      <p className="text-sm text-gray-300 whitespace-pre-wrap">
                        {activeChapter.story_so_far || 'No summary available'}
                      </p>
                    </div>
                    {storySummaryError && (
                      <p className="text-xs text-red-400 mt-2">{storySummaryError}</p>
                    )}
                  </div>
                )}

                {/* Current Chapter Summary Display */}
                {activeChapter && (
                  <div className="mt-3 pt-3 border-t border-slate-700">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-semibold text-gray-400 uppercase">Chapter Summary</h4>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={handleGenerateSummary}
                          disabled={isGeneratingSummary || activeChapter.scenes_count === 0}
                          className="p-1 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                          title={activeChapter.scenes_count === 0 ? 'Generate at least one scene first' : 'Generate summary for current chapter'}
                        >
                          {isGeneratingSummary ? (
                            <RefreshCw className="w-3 h-3 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3 h-3" />
                          )}
                        </button>
                        {activeChapter.auto_summary && (
                          <button
                            onClick={handleEditChapterSummary}
                            className="p-1 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white"
                            title="Edit chapter summary"
                          >
                            <Edit2 className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </div>
                    {activeChapter.auto_summary ? (
                      <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3 max-h-40 overflow-y-auto">
                        <p className="text-sm text-gray-300 whitespace-pre-wrap">
                          {activeChapter.auto_summary}
                        </p>
                      </div>
                    ) : (
                      <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3">
                        <p className="text-sm text-gray-500 italic">
                          {activeChapter.scenes_count === 0 
                            ? 'Generate scenes first, then create a summary'
                            : 'No summary generated yet. Click the refresh icon above to generate.'}
                        </p>
                      </div>
                    )}
                    {summaryError && (
                      <p className="text-xs text-red-400 mt-2">{summaryError}</p>
                    )}
                    {storySummaryError && (
                      <p className="text-xs text-red-400 mt-2">{storySummaryError}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Story Arc Viewer */}
            {storyArc && storyArc.phases && storyArc.phases.length > 0 && (
              <div className="p-4 border-b border-slate-700">
                <h3 className="text-sm font-semibold text-gray-400 uppercase mb-3">Story Arc</h3>
                <div className="space-y-1.5">
                  {storyArc.phases.map((phase, index) => {
                    const isExpanded = expandedArcPhaseId === phase.id;
                    return (
                      <button
                        key={phase.id}
                        onClick={() => setExpandedArcPhaseId(isExpanded ? null : phase.id)}
                        className="w-full text-left p-2 rounded-lg bg-slate-800/50 border border-slate-700 hover:border-purple-500/40 transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-purple-600/20 text-purple-300">
                            Phase {index + 1}
                          </span>
                          <span className="font-medium text-sm text-white flex-1">{phase.name}</span>
                          <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                        </div>
                        <p className={`text-xs text-gray-400 ${isExpanded ? '' : 'line-clamp-2'}`}>{phase.description}</p>
                        {isExpanded && phase.key_events && phase.key_events.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {phase.key_events.map((event, i) => (
                              <div key={i} className="text-xs text-purple-300/80 flex gap-1.5">
                                <span className="text-purple-500 mt-0.5">•</span>
                                <span>{event}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Incomplete Chapter Banner */}
            {chapters.filter(ch => ch.creation_step != null).map((ch) => (
              <div key={`incomplete-${ch.id}`} className="mx-4 mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                <p className="text-amber-200 text-sm font-medium">
                  Chapter {ch.chapter_number} setup incomplete
                </p>
                <p className="text-white/50 text-xs mt-1">Story context generation was interrupted</p>
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => handleResumeCreation(ch)}
                    disabled={isResumingCreation}
                    className="flex-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-xs rounded-lg font-medium transition-colors flex items-center justify-center gap-1.5"
                  >
                    {isResumingCreation ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Resuming...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-3 h-3" />
                        Resume Setup
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => handleDiscardIncompleteChapter(ch)}
                    disabled={isResumingCreation}
                    className="px-3 py-1.5 bg-red-600/60 hover:bg-red-600 disabled:bg-gray-600 text-white text-xs rounded-lg font-medium transition-colors flex items-center justify-center gap-1.5"
                  >
                    <Trash2 className="w-3 h-3" />
                    Discard
                  </button>
                </div>
              </div>
            ))}

            {/* All Chapters List */}
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-400 uppercase mb-3">All Chapters</h3>
              <div className="space-y-2">
                {chapters.map((chapter) => (
                  <button
                    key={chapter.id}
                    onClick={() => handleChapterClick(chapter)}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      currentChapterId === chapter.id
                        ? 'border-2 ring-2'
                        : chapter.id === activeChapter?.id
                        ? 'border-2'
                        : 'bg-slate-800/50 border-slate-700 hover:bg-slate-800 hover:border-slate-600'
                    }`}
                    style={currentChapterId === chapter.id ? {
                      backgroundColor: 'var(--color-accentPrimary)',
                      opacity: 0.2,
                      borderColor: 'var(--color-accentPrimary)',
                      boxShadow: '0 0 0 2px var(--color-accentPrimary)',
                      boxShadowOpacity: 0.3
                    } as React.CSSProperties & { boxShadowOpacity?: number } : chapter.id === activeChapter?.id ? {
                      backgroundColor: 'var(--color-accentPrimary)',
                      opacity: 0.1,
                      borderColor: 'var(--color-accentPrimary)',
                      borderOpacity: 0.3
                    } as React.CSSProperties & { borderOpacity?: number } : {}}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <span className="font-medium text-sm">
                        {chapter.title || `Chapter ${chapter.chapter_number}`}
                      </span>
                      <div className="flex items-center gap-2">
                        {currentChapterId === chapter.id && (
                          <span className="text-xs font-semibold"
                                style={{ color: 'var(--color-accentPrimary)' } as React.CSSProperties}>VIEWING</span>
                        )}
                        <span className={`px-1.5 py-0.5 text-xs rounded border ${getStatusBadgeColor(chapter.status)}`}>
                          {chapter.status}
                        </span>
                      </div>
                    </div>
                    
                    {chapter.description && (
                      <p className="text-xs text-gray-400 mb-2 line-clamp-2">
                        {chapter.description}
                      </p>
                    )}
                    
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>{chapter.scenes_count} scenes</span>
                      <span>•</span>
                      <span>{chapter.context_tokens_used.toLocaleString()} tokens</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
      
      {/* Edit Story So Far Modal */}
      {isEditingStorySoFar && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={(e) => {
          if (e.target === e.currentTarget) handleCancelEdit();
        }}>
          <div className="bg-slate-800 rounded-lg border border-slate-700 w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div>
                <h3 className="text-lg font-semibold text-white">Edit Story So Far</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Customize the chapter summary that provides context for scene generation
                </p>
              </div>
              <button
                onClick={handleCancelEdit}
                className="p-2 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white"
                disabled={isSavingStorySoFar}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              <textarea
                value={storySoFarDraft}
                onChange={(e) => setStorySoFarDraft(e.target.value)}
                className="w-full h-full min-h-[300px] bg-slate-900 border border-slate-600 rounded-lg p-3 text-gray-200 placeholder-gray-500 resize-none focus:outline-none theme-focus-ring"
                placeholder="Enter a summary of the story so far to provide context for future scenes..."
                disabled={isSavingStorySoFar}
              />
              <p className="text-xs text-gray-500 mt-2">
                {storySoFarDraft.length} characters
              </p>
            </div>
            
            {/* Footer */}
            <div className="flex items-center justify-between p-4 border-t border-slate-700">
              <div className="text-xs text-gray-500">
                {!activeChapter?.story_so_far && activeChapter?.auto_summary && (
                  <span>💡 Started with auto-generated summary</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCancelEdit}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                  disabled={isSavingStorySoFar}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveStorySoFar}
                  disabled={isSavingStorySoFar}
                  className="px-4 py-2 theme-btn-primary disabled:bg-gray-600 rounded-lg font-medium transition-colors flex items-center gap-2"
                >
                  {isSavingStorySoFar ? (
                    <>
                      <span className="animate-spin">⚙️</span>
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      Save Changes
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Chapter Summary Modal */}
      {isEditingChapterSummary && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={(e) => {
          if (e.target === e.currentTarget) handleCancelChapterSummaryEdit();
        }}>
          <div className="bg-slate-800 rounded-lg border border-slate-700 w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div>
                <h3 className="text-lg font-semibold text-white">Edit Chapter Summary</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Customize the auto-generated summary for this chapter
                </p>
              </div>
              <button
                onClick={handleCancelChapterSummaryEdit}
                className="p-2 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white"
                disabled={isSavingChapterSummary}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              <textarea
                value={chapterSummaryDraft}
                onChange={(e) => setChapterSummaryDraft(e.target.value)}
                className="w-full h-full min-h-[300px] bg-slate-900 border border-slate-600 rounded-lg p-3 text-gray-200 placeholder-gray-500 resize-none focus:outline-none theme-focus-ring"
                placeholder="Enter a summary of this chapter's content..."
                disabled={isSavingChapterSummary}
              />
              <p className="text-xs text-gray-500 mt-2">
                {chapterSummaryDraft.length} characters
              </p>
            </div>
            
            {/* Footer */}
            <div className="flex items-center justify-end gap-2 p-4 border-t border-slate-700">
              <button
                onClick={handleCancelChapterSummaryEdit}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                disabled={isSavingChapterSummary}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveChapterSummary}
                disabled={isSavingChapterSummary}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {isSavingChapterSummary ? (
                  <>
                    <span className="animate-spin">⚙️</span>
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    Save Changes
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Chapter Wizard Modal */}
      {showChapterWizard && (
        <ChapterWizard
          storyId={storyId}
          chapterNumber={editingChapterId ? activeChapter?.chapter_number : (chapters.length + 1)}
          chapterId={editingChapterId || undefined}
          storyArc={storyArc}
          onBrainstorm={() => {
            setBrainstormChapterId(editingChapterId || undefined);
            setShowBrainstormModal(true);
          }}
          brainstormSessionId={brainstormSessionId}
          initialData={editingChapterId && activeChapter ? {
            title: activeChapter.title || undefined,
            description: brainstormPlot?.summary || activeChapter.description || undefined,
            characters: activeChapter.characters || [],
            location_name: brainstormPlot?.location || activeChapter.location_name || undefined,
            time_period: activeChapter.time_period || undefined,
            scenario: brainstormPlot?.opening_situation || activeChapter.scenario || undefined,
            continues_from_previous: activeChapter.continues_from_previous !== undefined ? activeChapter.continues_from_previous : true,
            chapter_plot: brainstormPlot || activeChapter.chapter_plot,
            recommended_characters: brainstormPlot?.recommended_characters || [],
            mood: brainstormPlot?.mood || undefined,
            arc_phase_id: brainstormArcPhaseId || activeChapter.arc_phase_id || undefined
          } : {
            title: newChapterTitle || undefined,
            description: brainstormPlot?.summary || newChapterDescription || undefined,
            chapter_plot: brainstormPlot,
            recommended_characters: brainstormPlot?.recommended_characters || [],
            mood: brainstormPlot?.mood || undefined,
            location_name: brainstormPlot?.location || undefined,
            scenario: brainstormPlot?.opening_situation || undefined,
            arc_phase_id: brainstormArcPhaseId
          }}
          onComplete={(data, onStatusUpdate) => {
            // Clear brainstorm data after completion
            setBrainstormPlot(null);
            setBrainstormSessionId(undefined);
            setBrainstormArcPhaseId(undefined);
            handleChapterWizardComplete(data, onStatusUpdate);
          }}
          onCancel={() => {
            // Clear brainstorm data on cancel too
            setBrainstormPlot(null);
            setBrainstormSessionId(undefined);
            setBrainstormArcPhaseId(undefined);
            handleChapterWizardCancel();
          }}
        />
      )}
      
      {/* Chapter Brainstorm Modal */}
      {showBrainstormModal && (
        <ChapterBrainstormModal
          isOpen={showBrainstormModal}
          onClose={() => {
            setShowBrainstormModal(false);
            setBrainstormChapterId(undefined);
          }}
          storyId={storyId}
          chapterId={brainstormChapterId}
          storyArc={storyArc}
          existingPlot={editingChapterId && activeChapter ? activeChapter.chapter_plot : brainstormPlot}
          existingArcPhaseId={editingChapterId && activeChapter ? activeChapter.arc_phase_id || undefined : brainstormArcPhaseId}
          enableStreaming={enableStreaming}
          showThinkingContent={showThinkingContent}
          onPlotApplied={(plot, sessionId, arcPhaseId) => {
            setShowBrainstormModal(false);
            setBrainstormChapterId(undefined);
            
            if (plot) {
              // Plot returned - store it for ChapterWizard
              setBrainstormPlot(plot);
              setBrainstormSessionId(sessionId);
              setBrainstormArcPhaseId(arcPhaseId);
              console.log('[ChapterSidebar] Brainstorm plot saved:', { plot, sessionId, arcPhaseId });
              
              // Reopen the ChapterWizard with the new plot data
              setShowChapterWizard(true);
            } else {
              // Plot was applied directly to existing chapter via API
              setBrainstormArcPhaseId(arcPhaseId);
              loadChapters(); // Reload to get updated chapter plot
              if (onChapterChange) onChapterChange();
            }
          }}
        />
      )}

      {/* Create New Chapter Modal */}
      {isCreatingChapter && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 rounded-lg shadow-xl w-full max-w-lg">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700 theme-banner">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Plus className="w-5 h-5" />
                Create New Chapter
              </h3>
              <button
                onClick={handleCancelNewChapter}
                className="text-white/80 hover:text-white transition-colors"
                disabled={isSubmittingNewChapter}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-4 space-y-4">
              {/* Story-Level Summary Generation */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-gray-300">
                    Story Summary (All Chapters)
                  </label>
                  <button
                    onClick={handleGenerateStorySummary}
                    disabled={isGeneratingStorySummary || chapters.length === 0}
                    className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-xs rounded-lg font-medium transition-colors flex items-center gap-1.5"
                    title={chapters.length === 0 ? 'Create chapters first' : 'Generate summary of entire story from all chapters'}
                  >
                    {isGeneratingStorySummary ? (
                      <>
                        <span className="animate-spin">⚙️</span>
                        Generating...
                      </>
                    ) : (
                      <>
                        <BookOpen className="w-3 h-3" />
                        Generate Story Summary
                      </>
                    )}
                  </button>
                </div>
                <p className="text-xs text-gray-500">
                  Regenerates Story So Far from previous chapter summaries
                </p>
                {storySummaryError && (
                  <p className="text-xs text-red-400">{storySummaryError}</p>
                )}
              </div>
              
              {/* Current Chapter Summary Display */}
              {activeChapter && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="block text-sm font-medium text-gray-300">
                      Current Chapter Summary
                    </label>
                    <button
                      onClick={handleGenerateSummary}
                      disabled={isGeneratingSummary || activeChapter.scenes_count === 0}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-xs rounded-lg font-medium transition-colors flex items-center gap-1.5"
                      title={activeChapter.scenes_count === 0 ? 'Generate at least one scene first' : 'Generate summary for current chapter'}
                    >
                      {isGeneratingSummary ? (
                        <>
                          <span className="animate-spin">⚙️</span>
                          Generating...
                        </>
                      ) : (
                        <>
                          <BookOpen className="w-3 h-3" />
                          Generate Chapter Summary
                        </>
                      )}
                    </button>
                  </div>
                  
                  <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3 max-h-40 overflow-y-auto">
                    {activeChapter.auto_summary ? (
                      <p className="text-sm text-gray-300 whitespace-pre-wrap">
                        {activeChapter.auto_summary}
                      </p>
                    ) : (
                      <p className="text-sm text-gray-500 italic">
                        {activeChapter.scenes_count === 0 
                          ? 'Generate scenes first, then create a summary'
                          : 'No summary generated yet. Click "Generate Summary" above.'}
                      </p>
                    )}
                  </div>
                  
                  {summaryError && (
                    <p className="text-xs text-red-400">{summaryError}</p>
                  )}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Chapter Title
                </label>
                <input
                  type="text"
                  value={newChapterTitle}
                  onChange={(e) => setNewChapterTitle(e.target.value)}
                  placeholder="Enter chapter title"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none theme-focus-ring"
                  disabled={isSubmittingNewChapter}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Description (Optional)
                </label>
                <textarea
                  value={newChapterDescription}
                  onChange={(e) => setNewChapterDescription(e.target.value)}
                  placeholder="Brief description of this chapter"
                  rows={3}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                  disabled={isSubmittingNewChapter}
                />
              </div>

              {/* Story So Far Preview for New Chapter */}
              {activeChapter && activeChapter.story_so_far && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-300">
                    Story So Far (will be used for new chapter)
                  </label>
                  <div className="bg-slate-700/50 border border-slate-600 rounded-lg p-3 max-h-32 overflow-y-auto">
                    <p className="text-sm text-gray-300 whitespace-pre-wrap">
                      {activeChapter.story_so_far}
                    </p>
                  </div>
                </div>
              )}

              <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-sm text-blue-400">
                <p className="font-semibold mb-1">💡 Story Continuity</p>
                <p className="text-blue-400/80">
                  The AI will combine summaries from all previous chapters to create context for this new chapter.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 p-4 border-t border-slate-700">
              <button
                onClick={handleCancelNewChapter}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                disabled={isSubmittingNewChapter}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitNewChapter}
                disabled={isSubmittingNewChapter || !newChapterTitle.trim()}
                className="px-4 py-2 theme-btn-primary disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {isSubmittingNewChapter ? (
                  <>
                    <span className="animate-spin">⚙️</span>
                    Creating...
                  </>
                ) : (
                  <>
                    <Plus className="w-4 h-4" />
                    Create Chapter
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Dialog for Switching Active Chapter */}
      {chapterToActivate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-white mb-2">
              Switch Active Chapter?
            </h3>
            <p className="text-gray-300 mb-4">
              Are you sure you want to make <strong>Chapter {chapterToActivate.chapter_number}</strong> the active chapter? 
              This will make it the chapter where new scenes are generated and will update the context for scene generation.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={handleCancelActivateChapter}
                disabled={isActivatingChapter}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmActivateChapter}
                disabled={isActivatingChapter}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {isActivatingChapter ? 'Switching...' : 'Switch Chapter'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
