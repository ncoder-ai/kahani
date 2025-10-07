'use client';

import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, BookOpen, AlertCircle } from 'lucide-react';
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
}

export default function ChapterSidebar({ storyId, isOpen, onToggle }: ChapterSidebarProps) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeChapter, setActiveChapter] = useState<Chapter | null>(null);
  const [contextStatus, setContextStatus] = useState<ChapterContextStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="fixed right-4 top-24 z-40 p-2 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
        aria-label="Open chapter sidebar"
      >
        <ChevronLeft className="w-5 h-5" />
      </button>
    );
  }

  return (
    <div className="fixed right-0 top-16 bottom-0 w-80 bg-slate-900 border-l border-slate-700 z-40 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-purple-400" />
          <h2 className="text-lg font-semibold">Chapters</h2>
        </div>
        <button
          onClick={onToggle}
          className="p-1 hover:bg-slate-800 rounded transition-colors"
          aria-label="Close chapter sidebar"
        >
          <ChevronRight className="w-5 h-5" />
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
                      <div className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400">
                        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold mb-1">Context Warning</p>
                          <p className="text-yellow-400/80">
                            {contextStatus.reason === 'context_limit' 
                              ? 'Context usage is high. Consider starting a new chapter to maintain quality.'
                              : 'Consider starting a new chapter.'}
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Scene Count */}
                    <div className="text-sm text-gray-400">
                      <span className="font-semibold">{activeChapter.scenes_count || 0}</span> scenes in this chapter
                    </div>
                  </div>
                )}

                {/* Story So Far */}
                {activeChapter.story_so_far && (
                  <div className="mt-3 pt-3 border-t border-slate-700">
                    <h4 className="text-xs font-semibold text-gray-400 uppercase mb-2">Story So Far</h4>
                    <p className="text-sm text-gray-300 whitespace-pre-wrap">
                      {activeChapter.story_so_far}
                    </p>
                  </div>
                )}

                {/* Auto Summary */}
                {activeChapter.auto_summary && (
                  <div className="mt-3 pt-3 border-t border-slate-700">
                    <h4 className="text-xs font-semibold text-gray-400 uppercase mb-2">Chapter Summary</h4>
                    <p className="text-sm text-gray-300 whitespace-pre-wrap">
                      {activeChapter.auto_summary}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* All Chapters List */}
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-400 uppercase mb-3">All Chapters</h3>
              <div className="space-y-2">
                {chapters.map((chapter) => (
                  <div
                    key={chapter.id}
                    className={`p-3 rounded-lg border transition-colors ${
                      chapter.id === activeChapter?.id
                        ? 'bg-purple-500/10 border-purple-500/30'
                        : 'bg-slate-800/50 border-slate-700 hover:bg-slate-800'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <span className="font-medium text-sm">
                        {chapter.title || `Chapter ${chapter.chapter_number}`}
                      </span>
                      <span className={`px-1.5 py-0.5 text-xs rounded border ${getStatusBadgeColor(chapter.status)}`}>
                        {chapter.status}
                      </span>
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
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
