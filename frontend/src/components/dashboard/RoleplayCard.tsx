'use client';

import { useRouter } from 'next/navigation';
import { Trash2, MessageSquare, Users, Clock } from 'lucide-react';
import type { RoleplayListItem } from '@/lib/api/roleplay';

interface RoleplayCardProps {
  roleplay: RoleplayListItem;
  formatRelativeDate: (dateStr: string) => string;
  onDelete: (id: number, title: string, e: React.MouseEvent) => void;
}

export default function RoleplayCard({ roleplay, formatRelativeDate, onDelete }: RoleplayCardProps) {
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/roleplay/${roleplay.story_id}`)}
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
      <div className="flex items-center justify-between pt-2 border-t border-white/10">
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
        <button
          onClick={(e) => onDelete(roleplay.story_id, roleplay.title, e)}
          className="p-2 hover:bg-red-500/20 active:bg-red-500/30 rounded-lg transition-colors sm:opacity-0 sm:group-hover:opacity-100"
          title="Delete roleplay"
        >
          <Trash2 className="w-4 h-4 text-red-400" />
        </button>
      </div>
    </div>
  );
}
