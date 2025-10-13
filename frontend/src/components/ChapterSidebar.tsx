'use client';

import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, BookOpen, AlertCircle, Edit2, Save, X, Plus } from 'lucide-react';
import apiClient from '@/lib/api';

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
  context_tokens_used: number;
  scenes_count: number;
  last_summary_scene_count: number;
  created_at: string;
  updated_at: string | null;
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
  onChapterChange?: () => void; // Callback when a new chapter is created
  onChapterSelect?: (chapterId: number) => void; // Callback when user selects a chapter to view
  currentChapterId?: number; // Currently selected chapter for viewing
}

export default function ChapterSidebar({ storyId, isOpen, onToggle, onChapterChange, onChapterSelect, currentChapterId }: ChapterSidebarProps) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeChapter, setActiveChapter] = useState<Chapter | null>(null);
  const [contextStatus, setContextStatus] = useState<ChapterContextStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Story So Far editing state
  const [isEditingStorySoFar, setIsEditingStorySoFar] = useState(false);
  const [storySoFarDraft, setStorySoFarDraft] = useState('');
  const [isSavingStorySoFar, setIsSavingStorySoFar] = useState(false);
  
  // New Chapter creation state
  const [isCreatingChapter, setIsCreatingChapter] = useState(false);
  const [newChapterTitle, setNewChapterTitle] = useState('');
  const [newChapterDescription, setNewChapterDescription] = useState('');
  const [isSubmittingNewChapter, setIsSubmittingNewChapter] = useState(false);

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
      
      // Load active chapter
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
      console.error('Failed to load chapters:', err);
      // If chapters don't exist yet (new story), don't show error
      if (err instanceof Error && err.message.includes('404')) {
        setError(null); // Silently handle - chapters will be created on first scene
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load chapters');
      }
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

  const handleCreateNewChapter = () => {
    // Auto-populate with next chapter number
    const nextChapterNum = (chapters.length || 0) + 1;
    setNewChapterTitle(`Chapter ${nextChapterNum}`);
    setNewChapterDescription('');
    setIsCreatingChapter(true);
  };

  const handleSubmitNewChapter = async () => {
    setIsSubmittingNewChapter(true);
    try {
      // Use previous chapter's auto_summary as story_so_far for new chapter
      const storySoFar = activeChapter?.auto_summary || activeChapter?.story_so_far || 'Continuing the story...';
      
      const newChapter = await apiClient.createChapter(storyId, {
        title: newChapterTitle || undefined,
        description: newChapterDescription || undefined,
        story_so_far: storySoFar
      });
      
      // Reload chapters to get updated list
      await loadChapters();
      
      // Notify parent component to reload story (this will switch to the new active chapter)
      if (onChapterChange) {
        onChapterChange();
      }
      
      // Close modal
      setIsCreatingChapter(false);
      setNewChapterTitle('');
      setNewChapterDescription('');
      
      // Show success message
      alert(`Chapter ${newChapter.chapter_number} created successfully! You're now in the new chapter.`);
    } catch (err) {
      console.error('Failed to create chapter:', err);
      alert('Failed to create new chapter. Please try again.');
    } finally {
      setIsSubmittingNewChapter(false);
    }
  };

  const handleCancelNewChapter = () => {
    setIsCreatingChapter(false);
    setNewChapterTitle('');
    setNewChapterDescription('');
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
        <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-gradient-to-r from-purple-900/50 to-pink-900/50">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-purple-400" />
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
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
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

                {/* Context Usage */}
                {contextStatus && (
                  <div className="space-y-2">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-400">Context Usage:</span>
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

                    {/* Warning Message */}
                    {contextStatus.should_create_new_chapter && (
                      <div className="space-y-2">
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
                        <button
                          onClick={handleCreateNewChapter}
                          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
                        >
                          <Plus className="w-4 h-4" />
                          Create New Chapter
                        </button>
                      </div>
                    )}

                    {/* Scene Count */}
                    <div className="text-sm text-gray-400">
                      <span className="font-semibold">{activeChapter.scenes_count || 0}</span> scenes in this chapter
                    </div>
                  </div>
                )}

                {/* Story So Far - Editable */}
                {(activeChapter.story_so_far || activeChapter.auto_summary) && (
                  <div className="mt-3 pt-3 border-t border-slate-700">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-semibold text-gray-400 uppercase">Story So Far</h4>
                      <button
                        onClick={handleEditStorySoFar}
                        className="p-1 hover:bg-slate-700 rounded transition-colors text-gray-400 hover:text-white"
                        title="Edit story summary"
                      >
                        <Edit2 className="w-3 h-3" />
                      </button>
                    </div>
                    <div className="max-h-32 overflow-y-auto">
                      <p className="text-sm text-gray-300 whitespace-pre-wrap">
                        {/* Show auto_summary if it exists and story_so_far is default text, otherwise show story_so_far */}
                        {activeChapter.auto_summary && (!activeChapter.story_so_far || activeChapter.story_so_far === 'The story begins...')
                          ? activeChapter.auto_summary
                          : activeChapter.story_so_far || activeChapter.auto_summary}
                      </p>
                    </div>
                    {activeChapter.auto_summary && (!activeChapter.story_so_far || activeChapter.story_so_far === 'The story begins...') && (
                      <p className="text-xs text-gray-500 italic mt-1">
                        Auto-generated summary (click edit to customize)
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* All Chapters List */}
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-400 uppercase mb-3">All Chapters</h3>
              <div className="space-y-2">
                {chapters.map((chapter) => (
                  <button
                    key={chapter.id}
                    onClick={() => {
                      if (onChapterSelect) {
                        onChapterSelect(chapter.id);
                      }
                    }}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      currentChapterId === chapter.id
                        ? 'bg-purple-600/20 border-purple-500/50 ring-2 ring-purple-500/30'
                        : chapter.id === activeChapter?.id
                        ? 'bg-purple-500/10 border-purple-500/30'
                        : 'bg-slate-800/50 border-slate-700 hover:bg-slate-800 hover:border-slate-600'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <span className="font-medium text-sm">
                        {chapter.title || `Chapter ${chapter.chapter_number}`}
                      </span>
                      <div className="flex items-center gap-2">
                        {currentChapterId === chapter.id && (
                          <span className="text-xs text-purple-400 font-semibold">VIEWING</span>
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
                className="w-full h-full min-h-[300px] bg-slate-900 border border-slate-600 rounded-lg p-3 text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-purple-500"
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
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
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

      {/* Create New Chapter Modal */}
      {isCreatingChapter && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 rounded-lg shadow-xl w-full max-w-lg">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-gradient-to-r from-purple-600 to-pink-600">
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
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Chapter Title
                </label>
                <input
                  type="text"
                  value={newChapterTitle}
                  onChange={(e) => setNewChapterTitle(e.target.value)}
                  placeholder="Enter chapter title"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
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

              <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-sm text-blue-400">
                <p className="font-semibold mb-1">💡 Story Continuity</p>
                <p className="text-blue-400/80">
                  The AI-generated summary from your current chapter will be used as the starting context for this new chapter.
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
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors flex items-center gap-2"
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
    </>
  );
}
