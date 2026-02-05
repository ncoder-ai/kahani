'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { ChapterProgress } from '@/lib/api';
import apiClient from '@/lib/api';

interface ChapterProgressIndicatorProps {
  storyId: number;
  chapterId: number | null;
  enabled: boolean;
  onProgressChange?: (progress: ChapterProgress | null) => void;
  /** Increment this value to trigger a refresh (e.g., after scene generation) */
  refreshTrigger?: number;
}

/**
 * Mobile-first chapter progress indicator.
 * 
 * Shows a small circular badge in the bottom-right corner that expands
 * to a bottom sheet (mobile) or floating panel (desktop) when tapped.
 */
export default function ChapterProgressIndicator({
  storyId,
  chapterId,
  enabled,
  onProgressChange,
  refreshTrigger = 0
}: ChapterProgressIndicatorProps) {
  const [progress, setProgress] = useState<ChapterProgress | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch progress when chapter changes
  const fetchProgress = useCallback(async () => {
    if (!storyId || !chapterId || !enabled) {
      setProgress(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await apiClient.getChapterProgress(storyId, chapterId);
      setProgress(data);
      onProgressChange?.(data);
    } catch (err) {
      console.error('Failed to fetch chapter progress:', err);
      setError('Failed to load progress');
      setProgress(null);
    } finally {
      setIsLoading(false);
    }
  }, [storyId, chapterId, enabled, onProgressChange]);

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress, refreshTrigger]);

  // Toggle event completion
  const handleToggleEvent = async (event: string, currentlyCompleted: boolean) => {
    if (!storyId || !chapterId) return;

    try {
      const updatedProgress = await apiClient.toggleEventCompletion(
        storyId,
        chapterId,
        event,
        !currentlyCompleted
      );
      setProgress(updatedProgress);
      onProgressChange?.(updatedProgress);
    } catch (err) {
      console.error('Failed to toggle event:', err);
    }
  };

  // Toggle milestone (climax/resolution) completion
  const handleToggleMilestone = async (milestone: 'climax' | 'resolution', currentlyCompleted: boolean) => {
    if (!storyId || !chapterId) return;

    try {
      const updatedProgress = await apiClient.toggleMilestoneCompletion(
        storyId,
        chapterId,
        milestone,
        !currentlyCompleted
      );
      setProgress(updatedProgress);
      onProgressChange?.(updatedProgress);
    } catch (err) {
      console.error('Failed to toggle milestone:', err);
    }
  };

  // Don't render if disabled or no chapter
  if (!enabled || !chapterId) {
    return null;
  }

  // Don't render if chapter has no plot
  if (progress && !progress.has_plot) {
    return null;
  }

  // Calculate progress for visual indicator
  const completedCount = progress?.completed_events.length || 0;
  const totalCount = progress?.total_events || 0;
  const progressPercent = progress?.progress_percentage || 0;

  // Progress ring calculation
  const radius = 16;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference;

  return (
    <>
      {/* Floating Badge - Bottom Right (same vertical position as scroll-to-bottom button) */}
      <button
        onClick={() => setIsExpanded(true)}
        className={`
          fixed bottom-4 right-4 z-40
          w-12 h-12 rounded-full
          bg-black/40 backdrop-blur-sm
          border border-white/10
          flex items-center justify-center
          transition-all duration-200
          hover:bg-black/50 hover:scale-105
          active:scale-95
          ${isLoading ? 'animate-pulse' : ''}
        `}
        style={{ touchAction: 'manipulation' }}
        aria-label="View chapter progress"
      >
        {isLoading ? (
          <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        ) : error ? (
          <span className="text-red-400 text-xs">!</span>
        ) : (
          <div className="relative w-10 h-10">
            {/* Progress ring */}
            <svg className="w-10 h-10 -rotate-90" viewBox="0 0 40 40">
              {/* Background circle */}
              <circle
                cx="20"
                cy="20"
                r={radius}
                fill="none"
                stroke="rgba(255,255,255,0.1)"
                strokeWidth="3"
              />
              {/* Progress circle */}
              <circle
                cx="20"
                cy="20"
                r={radius}
                fill="none"
                stroke={progressPercent >= 80 ? '#10b981' : progressPercent >= 50 ? '#f59e0b' : '#6366f1'}
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                className="transition-all duration-500"
              />
            </svg>
            {/* Center text */}
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-white text-xs font-medium">
                {completedCount}/{totalCount}
              </span>
            </div>
          </div>
        )}
      </button>

      {/* Expanded Panel - Bottom Sheet (mobile) / Floating Panel (desktop) */}
      {isExpanded && progress && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/50 z-50 md:bg-transparent"
            onClick={() => setIsExpanded(false)}
          />

          {/* Panel */}
          <div
            className={`
              fixed z-50
              bg-gray-900/95 backdrop-blur-md
              border border-white/10
              shadow-2xl
              
              /* Mobile: Bottom sheet */
              bottom-0 left-0 right-0
              rounded-t-2xl
              max-h-[60vh]
              
              /* Desktop: Floating panel */
              md:bottom-20 md:right-4 md:left-auto
              md:w-80 md:max-h-96
              md:rounded-xl
              
              overflow-hidden
              animate-in slide-in-from-bottom duration-300
            `}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drag handle (mobile) */}
            <div className="flex justify-center py-2 md:hidden">
              <div className="w-10 h-1 bg-white/20 rounded-full" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
              <h3 className="text-white font-semibold">Chapter Progress</h3>
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-400">
                  {Math.round(progressPercent)}%
                </span>
                <button
                  onClick={() => setIsExpanded(false)}
                  className="text-gray-400 hover:text-white p-1"
                  aria-label="Close"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Progress bar */}
            <div className="px-4 py-3">
              <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    progressPercent >= 80 ? 'bg-emerald-500' : 
                    progressPercent >= 50 ? 'bg-amber-500' : 'bg-indigo-500'
                  }`}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Scrollable content area */}
            <div className="overflow-y-auto max-h-[40vh] md:max-h-64">
              {/* Events list */}
              <div className="px-4 pb-4">
                <div className="space-y-2">
                  {progress.key_events.map((event, index) => {
                    const isCompleted = progress.completed_events.includes(event);
                    return (
                      <button
                        key={index}
                        onClick={() => handleToggleEvent(event, isCompleted)}
                        className={`
                          w-full flex items-start gap-3 p-2 rounded-lg
                          text-left transition-colors
                          ${isCompleted 
                            ? 'bg-emerald-500/10 hover:bg-emerald-500/20' 
                            : 'bg-white/5 hover:bg-white/10'
                          }
                        `}
                        style={{ minHeight: '44px' }}
                      >
                        {/* Checkbox */}
                        <div className={`
                          flex-shrink-0 w-5 h-5 rounded-full border-2 mt-0.5
                          flex items-center justify-center transition-colors
                          ${isCompleted 
                            ? 'bg-emerald-500 border-emerald-500' 
                            : 'border-gray-500'
                          }
                        `}>
                          {isCompleted && (
                            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </div>
                        {/* Event text */}
                        <span className={`text-sm ${isCompleted ? 'text-gray-400 line-through' : 'text-white'}`}>
                          {event}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Climax & Resolution - inside scrollable area */}
              {(progress.climax || progress.resolution) && (
                <div className="px-4 pb-4 pt-2 border-t border-white/10 space-y-2">
                  {progress.climax && (
                    <button
                      onClick={() => handleToggleMilestone('climax', progress.climax_reached)}
                      className={`
                        w-full flex items-start gap-3 p-2 rounded-lg
                        text-left transition-colors
                        ${progress.climax_reached
                          ? 'bg-amber-500/10 hover:bg-amber-500/20'
                          : 'bg-white/5 hover:bg-white/10'
                        }
                      `}
                      style={{ minHeight: '44px' }}
                    >
                      {/* Checkbox */}
                      <div className={`
                        flex-shrink-0 w-5 h-5 rounded-full border-2 mt-0.5
                        flex items-center justify-center transition-colors
                        ${progress.climax_reached
                          ? 'bg-amber-500 border-amber-500'
                          : 'border-amber-500/50'
                        }
                      `}>
                        {progress.climax_reached && (
                          <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      {/* Content */}
                      <div className="flex-1">
                        <span className="text-xs text-amber-400 font-medium">Climax:</span>
                        <p className={`text-sm mt-0.5 break-words ${progress.climax_reached ? 'text-gray-400 line-through' : 'text-gray-300'}`}>
                          {progress.climax}
                        </p>
                      </div>
                    </button>
                  )}
                  {progress.resolution && (
                    <button
                      onClick={() => handleToggleMilestone('resolution', progress.resolution_reached)}
                      className={`
                        w-full flex items-start gap-3 p-2 rounded-lg
                        text-left transition-colors
                        ${progress.resolution_reached
                          ? 'bg-emerald-500/10 hover:bg-emerald-500/20'
                          : 'bg-white/5 hover:bg-white/10'
                        }
                      `}
                      style={{ minHeight: '44px' }}
                    >
                      {/* Checkbox */}
                      <div className={`
                        flex-shrink-0 w-5 h-5 rounded-full border-2 mt-0.5
                        flex items-center justify-center transition-colors
                        ${progress.resolution_reached
                          ? 'bg-emerald-500 border-emerald-500'
                          : 'border-emerald-500/50'
                        }
                      `}>
                        {progress.resolution_reached && (
                          <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      {/* Content */}
                      <div className="flex-1">
                        <span className="text-xs text-emerald-400 font-medium">Resolution:</span>
                        <p className={`text-sm mt-0.5 break-words ${progress.resolution_reached ? 'text-gray-400 line-through' : 'text-gray-300'}`}>
                          {progress.resolution}
                        </p>
                      </div>
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Close button (mobile) */}
            <div className="p-4 border-t border-white/10 md:hidden">
              <button
                onClick={() => setIsExpanded(false)}
                className="w-full py-3 bg-white/10 hover:bg-white/20 rounded-lg text-white font-medium transition-colors"
                style={{ minHeight: '44px' }}
              >
                Close
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

