'use client';

import { useState } from 'react';
import { UserPlus, X, Crown } from 'lucide-react';
import type { RoleplayCharacter } from '@/lib/api/roleplay';

interface CharacterRosterProps {
  characters: RoleplayCharacter[];
  isOpen: boolean;
  onToggle: () => void;
  onRemoveCharacter?: (storyCharacterId: number) => void;
  onAddCharacter?: () => void;
}

const CHAR_COLORS = [
  'bg-blue-500/30 border-blue-500/40',
  'bg-emerald-500/30 border-emerald-500/40',
  'bg-amber-500/30 border-amber-500/40',
  'bg-purple-500/30 border-purple-500/40',
  'bg-rose-500/30 border-rose-500/40',
  'bg-cyan-500/30 border-cyan-500/40',
];

export default function CharacterRoster({
  characters,
  isOpen,
  onToggle,
  onRemoveCharacter,
  onAddCharacter,
}: CharacterRosterProps) {
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);

  if (!isOpen) return null;

  const activeChars = characters.filter(c => c.is_active);
  const inactiveChars = characters.filter(c => !c.is_active);

  const handleRemove = (scId: number) => {
    if (confirmRemove === scId) {
      onRemoveCharacter?.(scId);
      setConfirmRemove(null);
    } else {
      setConfirmRemove(scId);
      setTimeout(() => setConfirmRemove(null), 3000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onToggle}>
      <div
        className="bg-gray-900/95 backdrop-blur-md border border-white/20 rounded-2xl shadow-2xl w-full max-w-sm mx-4 max-h-[70vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
          <div>
            <h3 className="text-base font-semibold text-white">Characters</h3>
            <p className="text-xs text-white/40">{activeChars.length} active</p>
          </div>
          <button onClick={onToggle} className="p-1.5 hover:bg-white/10 rounded-lg transition-colors">
            <X className="w-5 h-5 text-white/60" />
          </button>
        </div>

        {/* Character list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {activeChars.map((char, i) => (
            <div
              key={char.story_character_id}
              className={`relative rounded-xl border p-3 ${CHAR_COLORS[i % CHAR_COLORS.length]}`}
            >
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold text-white/70">
                  {char.name.charAt(0)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-white truncate">{char.name}</span>
                    {char.is_player && (
                      <Crown className="w-3 h-3 text-yellow-400 flex-shrink-0" />
                    )}
                  </div>
                  <div className="text-[10px] text-white/40 capitalize">{char.role}</div>
                </div>
                {!char.is_player && onRemoveCharacter && (
                  <button
                    onClick={() => handleRemove(char.story_character_id)}
                    className={`p-1 rounded-lg transition-colors ${
                      confirmRemove === char.story_character_id
                        ? 'bg-red-500/30 text-red-300'
                        : 'hover:bg-white/10 text-white/30'
                    }`}
                    title={confirmRemove === char.story_character_id ? 'Click again to confirm' : 'Remove'}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}

          {/* Add character button */}
          {onAddCharacter && (
            <button
              onClick={onAddCharacter}
              className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-dashed border-white/20 text-white/40 hover:text-white/60 hover:border-white/30 hover:bg-white/5 transition-colors text-sm"
            >
              <UserPlus className="w-4 h-4" />
              Add Character
            </button>
          )}

          {/* Inactive characters */}
          {inactiveChars.length > 0 && (
            <div className="mt-4 pt-3 border-t border-white/10">
              <div className="text-[10px] text-white/25 uppercase tracking-wider mb-2 px-1">Left the scene</div>
              {inactiveChars.map(char => (
                <div key={char.story_character_id} className="px-3 py-1.5 text-xs text-white/25">
                  {char.name}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
