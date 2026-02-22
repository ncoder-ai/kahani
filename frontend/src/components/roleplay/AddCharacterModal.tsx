'use client';

import { useState, useEffect } from 'react';
import { X, Search, Loader2 } from 'lucide-react';
import { CharactersApi } from '@/lib/api/characters';
import { RoleplayApi } from '@/lib/api/roleplay';
import type { Character } from '@/lib/api/types';
import type { CharacterStoryEntry } from '@/lib/api/roleplay';

const charApi = new CharactersApi();
const rpApi = new RoleplayApi();

interface Props {
  roleplayId: number;
  existingCharacterIds: number[];
  onAdded: () => void;
  onClose: () => void;
}

export default function AddCharacterModal({ roleplayId, existingCharacterIds, onAdded, onClose }: Props) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stage picker state
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [storyEntries, setStoryEntries] = useState<CharacterStoryEntry[]>([]);
  const [selectedStoryId, setSelectedStoryId] = useState<number | null>(null);
  const [loadingStories, setLoadingStories] = useState(false);

  useEffect(() => {
    loadCharacters();
  }, []);

  const loadCharacters = async () => {
    try {
      setIsLoading(true);
      const data = await charApi.getCharacters(0, 100, false, false);
      setCharacters(data);
    } catch {
      setError('Failed to load characters');
    } finally {
      setIsLoading(false);
    }
  };

  const filteredChars = characters.filter(c => {
    if (existingCharacterIds.includes(c.id)) return false;
    if (!search.trim()) return true;
    return c.name.toLowerCase().includes(search.toLowerCase());
  });

  const handleSelectChar = async (char: Character) => {
    setSelectedChar(char);
    setSelectedStoryId(null);
    setLoadingStories(true);
    try {
      const entries = await rpApi.getCharacterStories(char.id);
      setStoryEntries(entries);
    } catch {
      setStoryEntries([]);
    } finally {
      setLoadingStories(false);
    }
  };

  const handleAdd = async () => {
    if (!selectedChar) return;
    setIsAdding(true);
    setError(null);
    try {
      await rpApi.addCharacter(roleplayId, {
        character_id: selectedChar.id,
        source_story_id: selectedStoryId || undefined,
      });
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add character');
      setIsAdding(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-gray-900 border border-white/10 rounded-2xl w-full max-w-md mx-4 p-5 max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-white">
            {selectedChar ? `Add ${selectedChar.name}` : 'Add Character'}
          </h2>
          <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-lg">
            <X className="w-5 h-5 text-white/60" />
          </button>
        </div>

        {error && (
          <div className="text-xs text-red-400 bg-red-500/10 px-3 py-1.5 rounded-lg mb-3">{error}</div>
        )}

        {!selectedChar ? (
          <>
            {/* Search */}
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search characters..."
                className="w-full bg-black/30 border border-white/10 rounded-xl pl-9 pr-3 py-2 text-sm text-white/80 placeholder:text-white/25 focus:outline-none focus:border-white/20"
                autoFocus
              />
            </div>

            {/* Character list */}
            <div className="flex-1 overflow-y-auto space-y-1.5 min-h-0">
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-5 h-5 text-white/30 animate-spin" />
                </div>
              ) : filteredChars.length === 0 ? (
                <div className="text-xs text-white/30 text-center py-8">
                  {search ? 'No matching characters' : 'No characters available'}
                </div>
              ) : (
                filteredChars.map(char => (
                  <button
                    key={char.id}
                    onClick={() => handleSelectChar(char)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/5 transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold text-white/70 flex-shrink-0">
                      {char.name.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white/80 truncate">{char.name}</div>
                      {char.description && (
                        <div className="text-[10px] text-white/30 truncate">{char.description}</div>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          </>
        ) : (
          /* Stage picker */
          <div className="space-y-3">
            <div className="text-xs text-white/40">
              Optionally load development from a previous story:
            </div>

            {loadingStories ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="w-4 h-4 text-white/30 animate-spin" />
              </div>
            ) : (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                <button
                  onClick={() => setSelectedStoryId(null)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                    selectedStoryId === null
                      ? 'bg-blue-500/20 border border-blue-500/40 text-blue-300'
                      : 'border border-white/10 text-white/50 hover:bg-white/5'
                  }`}
                >
                  Fresh start (no development history)
                </button>
                {storyEntries.map(entry => (
                  <button
                    key={entry.story_id}
                    onClick={() => setSelectedStoryId(entry.story_id)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                      selectedStoryId === entry.story_id
                        ? 'bg-blue-500/20 border border-blue-500/40 text-blue-300'
                        : 'border border-white/10 text-white/50 hover:bg-white/5'
                    }`}
                  >
                    {entry.title}
                  </button>
                ))}
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setSelectedChar(null)}
                className="flex-1 px-3 py-2 text-xs text-white/50 hover:text-white/70 rounded-xl border border-white/10"
              >
                Back
              </button>
              <button
                onClick={handleAdd}
                disabled={isAdding}
                className="flex-1 px-3 py-2 text-xs theme-btn-primary rounded-xl font-medium disabled:opacity-50"
              >
                {isAdding ? 'Adding...' : 'Add to Roleplay'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
