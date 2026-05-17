'use client';

import { useState } from 'react';

interface StoryCardProps {
  story: any;
  generatingStorySummaryId: number | null;
  onStoryClick: (storyId: number) => void;
  onViewSummary: (storyId: number) => void;
  onEditStory: (storyId: number) => void;
  onDeleteStory: (storyId: number, title: string) => Promise<void> | void;
  onGenerateStorySummary: (storyId: number, e: React.MouseEvent) => void;
}

export default function StoryCard({
  story,
  generatingStorySummaryId,
  onStoryClick,
  onViewSummary,
  onEditStory,
  onDeleteStory,
  onGenerateStorySummary,
}: StoryCardProps) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    setDeleteError(false);
    try {
      await Promise.resolve(onDeleteStory(story.id, story.title));
    } catch {
      setDeleteError(true);
    } finally {
      setIsDeleting(false);
      setConfirmingDelete(false);
    }
  };

  return (
    <div
      onClick={(e) => {
        // Don't navigate if user is interacting with the action buttons area
        const target = e.target as HTMLElement;
        if (target.closest('[data-actions]')) return;
        onStoryClick(story.id);
      }}
      className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-4 sm:p-6 cursor-pointer hover:bg-white/15 transition-all duration-200 group"
    >
      {/* Story Header */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1 min-w-0">
          <h4 className="text-base sm:text-xl font-bold text-white mb-1 group-hover:text-gray-200 transition-colors truncate">
            {story.title}
            {story.status === 'archived' && (
              <span className="ml-2 text-xs bg-gray-600/50 text-gray-300 px-2 py-0.5 rounded">
                Archived
              </span>
            )}
          </h4>
          {story.genre && (
            <span className="theme-accent-primary bg-opacity-20 text-white px-2 py-0.5 rounded-lg text-xs sm:text-sm font-medium">
              {story.genre.charAt(0).toUpperCase() + story.genre.slice(1)}
            </span>
          )}
        </div>
        <div className="text-white/60 group-hover:text-white/80 transition-colors ml-2">
          &rarr;
        </div>
      </div>

      {/* Story Description */}
      {story.description && (
        <p className="text-white/70 text-xs sm:text-sm mb-3 line-clamp-2 sm:line-clamp-3">
          {story.description}
        </p>
      )}

      {/* Story Summary — clickable to open full summary overlay */}
      {story.summary ? (
        story.content_rating === 'nsfw' ? (
          <div
            data-actions
            onClick={() => onViewSummary(story.id)}
            className="mb-3 p-2 sm:p-3 bg-red-500/10 border border-red-500/20 rounded-lg cursor-pointer hover:bg-red-500/20 transition-colors"
          >
            <span className="text-xs text-red-300 font-medium">Show Summary</span>
          </div>
        ) : (
          <div
            data-actions
            onClick={() => onViewSummary(story.id)}
            className="mb-3 p-2 sm:p-3 theme-bg-secondary border theme-border-accent rounded-lg cursor-pointer hover:bg-white/10 transition-colors"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold theme-accent-primary">STORY SO FAR</span>
            </div>
            <p className="text-white/80 text-xs line-clamp-2 sm:line-clamp-3 whitespace-pre-wrap">
              {story.summary}
            </p>
          </div>
        )
      ) : (
        <div className="mb-3 p-2 sm:p-3 bg-gray-500/10 border border-gray-500/20 rounded-lg">
          <span className="text-xs text-gray-400">No story summary available</span>
        </div>
      )}

      {/* Story Footer — data-actions prevents card navigation */}
      <div className="pt-3 border-t border-white/20" data-actions>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${
              story.status === 'active' ? 'bg-green-400' : 'bg-gray-400'
            }`}></div>
            <span className="text-white/60 text-xs sm:text-sm capitalize">{story.status}</span>
          </div>
          <span className="text-white/50 text-xs">
            {new Date(story.updated_at).toLocaleDateString()}
          </span>
        </div>

        {/* Delete error message */}
        {deleteError && (
          <div className="mb-2 px-3 py-1.5 bg-red-600/20 border border-red-500/30 rounded-lg text-red-300 text-xs">
            Delete failed. Try again.
          </div>
        )}

        {/* Action buttons — 2x2 grid on mobile, single row on desktop */}
        <div className="grid grid-cols-2 sm:flex sm:flex-row gap-2">
          <button
            onClick={() => onViewSummary(story.id)}
            className="bg-blue-600/20 hover:bg-blue-600/40 active:bg-blue-600/50 text-blue-200 hover:text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200 sm:flex-1"
          >
            Summary
          </button>
          <button
            onClick={() => onStoryClick(story.id)}
            className="bg-purple-600/20 hover:bg-purple-600/40 active:bg-purple-600/50 text-purple-200 hover:text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200 sm:flex-1"
          >
            Continue
          </button>
          <button
            onClick={() => onEditStory(story.id)}
            className="bg-yellow-600/20 hover:bg-yellow-600/40 active:bg-yellow-600/50 text-yellow-200 hover:text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200"
          >
            Edit
          </button>
          {confirmingDelete ? (
            <div className="flex gap-1">
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="flex-1 bg-red-600 hover:bg-red-700 active:bg-red-800 disabled:bg-red-800 text-white px-2 py-2.5 sm:py-2 rounded-lg text-sm font-bold transition-all duration-200"
              >
                {isDeleting ? '...' : 'Yes'}
              </button>
              <button
                onClick={() => setConfirmingDelete(false)}
                disabled={isDeleting}
                className="flex-1 bg-white/10 hover:bg-white/20 active:bg-white/30 text-white/70 px-2 py-2.5 sm:py-2 rounded-lg text-sm transition-all duration-200"
              >
                No
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmingDelete(true)}
              className="bg-red-600/20 hover:bg-red-600/40 active:bg-red-600/50 text-red-200 hover:text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
