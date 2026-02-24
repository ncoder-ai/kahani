'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { CheckSquare, Square } from 'lucide-react';

interface BrainstormCardProps {
  session: any;
  selectMode: boolean;
  isSelected: boolean;
  onToggleSelection: (sessionId: number, e: React.MouseEvent) => void;
  onDelete: (id: number, summary: string) => Promise<void> | void;
}

export default function BrainstormCard({ session, selectMode, isSelected, onToggleSelection, onDelete }: BrainstormCardProps) {
  const router = useRouter();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    setDeleteError(false);
    try {
      await Promise.resolve(onDelete(session.id, session.summary || 'Brainstorming session'));
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
        if (selectMode) {
          onToggleSelection(session.id, e);
        } else {
          router.push(`/brainstorm?session_id=${session.id}`);
        }
      }}
      className={`relative bg-gradient-to-r from-green-500/10 to-emerald-500/10 backdrop-blur-md border rounded-xl p-3 sm:p-4 text-left transition-all group cursor-pointer ${
        isSelected
          ? 'border-red-500 ring-2 ring-red-500/30'
          : 'border-green-500/30 hover:from-green-500/20 hover:to-emerald-500/20'
      }`}
    >
      {/* Selection checkbox */}
      {selectMode && (
        <div
          className="absolute top-2 right-2 z-10"
          onClick={(e) => onToggleSelection(session.id, e)}
        >
          {isSelected ? (
            <CheckSquare className="w-5 h-5 text-red-400" />
          ) : (
            <Square className="w-5 h-5 text-white/40 hover:text-white/70" />
          )}
        </div>
      )}

      <div className="flex items-start justify-between mb-2">
        <span className="text-green-400 text-sm font-medium capitalize">
          {session.status}
        </span>
        <span className={`text-white/40 text-xs ${selectMode ? 'mr-6' : ''}`}>
          {session.message_count} messages
        </span>
      </div>
      <p className="text-white/80 text-sm line-clamp-2 mb-2">
        {session.summary || 'Brainstorming session...'}
      </p>

      <div className="pt-2 border-t border-white/10" data-actions>
        <div className="flex items-center justify-between mb-2 text-xs text-white/50">
          <span>
            {session.updated_at ? new Date(session.updated_at).toLocaleDateString() : 'Recently'}
          </span>
        </div>

        {deleteError && (
          <div className="mb-2 px-3 py-1.5 bg-red-600/20 border border-red-500/30 rounded-lg text-red-300 text-xs">
            Delete failed. Try again.
          </div>
        )}

        {!selectMode && (
          <div className="flex gap-2">
            <button
              onClick={() => router.push(`/brainstorm?session_id=${session.id}`)}
              className="flex-1 bg-green-600/20 hover:bg-green-600/40 active:bg-green-600/50 text-green-200 hover:text-white px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200"
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
        )}
      </div>
    </div>
  );
}
