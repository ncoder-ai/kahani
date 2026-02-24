'use client';

import { useRouter } from 'next/navigation';
import { CheckSquare, Square } from 'lucide-react';

interface BrainstormCardProps {
  session: any;
  selectMode: boolean;
  isSelected: boolean;
  onToggleSelection: (sessionId: number, e: React.MouseEvent) => void;
}

export default function BrainstormCard({ session, selectMode, isSelected, onToggleSelection }: BrainstormCardProps) {
  const router = useRouter();

  return (
    <div
      onClick={(e) => {
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
      <div className="flex items-center justify-between text-xs text-white/50">
        <span>
          {session.updated_at ? new Date(session.updated_at).toLocaleDateString() : 'Recently'}
        </span>
        {!selectMode && (
          <span className="text-green-400 opacity-0 group-hover:opacity-100 transition-opacity">
            Continue &rarr;
          </span>
        )}
      </div>
    </div>
  );
}
