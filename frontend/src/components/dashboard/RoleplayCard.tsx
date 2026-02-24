'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { MessageSquare, Users, Clock } from 'lucide-react';
import type { RoleplayListItem } from '@/lib/api/roleplay';

interface RoleplayCardProps {
  roleplay: RoleplayListItem;
  formatRelativeDate: (dateStr: string) => string;
  onDelete: (id: number, title: string) => Promise<void> | void;
}

export default function RoleplayCard({ roleplay, formatRelativeDate, onDelete }: RoleplayCardProps) {
  const router = useRouter();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    setDeleteError(false);
    try {
      await Promise.resolve(onDelete(roleplay.story_id, roleplay.title));
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
        const target = e.target as HTMLElement;
        if (target.closest('[data-actions]')) return;
        router.push(`/roleplay/${roleplay.story_id}`);
      }}
      className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 backdrop-blur-md border border-purple-500/30 rounded-xl p-4 cursor-pointer hover:from-purple-500/20 hover:to-pink-500/20 transition-all group"
    >
      <div className="flex items-start justify-between mb-2">
        <h4 className="text-sm sm:text-base text-white font-semibold line-clamp-1 group-hover:text-purple-200 transition-colors">
          {roleplay.title}
        </h4>
        {roleplay.content_rating === 'nsfw' && (
          <span className="text-xs px-2 py-0.5 bg-red-500/30 text-red-300 rounded-full flex-shrink-0 ml-2">
            NSFW
          </span>
        )}
      </div>
      {roleplay.scenario && (
        <p className="text-white/50 text-sm line-clamp-2 mb-3">{roleplay.scenario}</p>
      )}
      <div className="flex items-center gap-2 mb-3">
        <Users className="w-3.5 h-3.5 text-white/40 flex-shrink-0" />
        <span className="text-sm text-white/60 line-clamp-1">{roleplay.characters.join(', ')}</span>
      </div>

      <div className="pt-2 border-t border-white/10" data-actions>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3 text-xs text-white/40">
            <span className="flex items-center gap-1">
              <MessageSquare className="w-3 h-3" />
              {roleplay.turn_count} turns
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatRelativeDate(roleplay.updated_at || roleplay.created_at)}
            </span>
          </div>
        </div>

        {deleteError && (
          <div className="mb-2 px-3 py-1.5 bg-red-600/20 border border-red-500/30 rounded-lg text-red-300 text-xs">
            Delete failed. Try again.
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => router.push(`/roleplay/${roleplay.story_id}`)}
            className="flex-1 bg-purple-600/20 hover:bg-purple-600/40 active:bg-purple-600/50 text-purple-200 hover:text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200"
          >
            Continue
          </button>
          {confirmingDelete ? (
            <div className="flex gap-1">
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="bg-red-600 hover:bg-red-700 active:bg-red-800 disabled:bg-red-800 text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-bold transition-all duration-200"
              >
                {isDeleting ? '...' : 'Yes'}
              </button>
              <button
                onClick={() => setConfirmingDelete(false)}
                disabled={isDeleting}
                className="bg-white/10 hover:bg-white/20 active:bg-white/30 text-white/70 px-3 py-2.5 sm:py-2 rounded-lg text-sm transition-all duration-200"
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
