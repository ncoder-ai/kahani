'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';

interface Character {
  id: number;
  name: string;
  description: string;
  personality_traits: string[];
  background: string | null;
  goals: string | null;
  fears: string | null;
  appearance: string | null;
  is_template: boolean;
  is_public: boolean;
}

interface CharacterSelectionProps {
  onContinue: (selectedCharacterIds: number[]) => void;
  onSkip: () => void;
}

export default function CharacterSelection({ onContinue, onSkip }: CharacterSelectionProps) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadCharacters();
  }, []);

  const loadCharacters = async () => {
    try {
      setIsLoading(true);
      // Load user's characters and public templates
      const chars = await apiClient.getCharacters(0, 100, true, false);
      setCharacters(chars);
    } catch (error) {
      console.error('Failed to load characters:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCharacter = (id: number) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const filteredCharacters = characters.filter(char =>
    char.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    char.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleContinue = () => {
    onContinue(Array.from(selectedIds));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-2">
          Do you want to use existing characters?
        </h2>
        <p className="text-white/70">
          Choose characters from your library to include in your story. The AI will incorporate them when generating story ideas based on your theme.
        </p>
        <p className="text-white/50 text-sm mt-2">
          Optional - you can skip this step if you want the AI to create all characters
        </p>
      </div>

      {/* Selected Count Badge */}
      {selectedIds.size > 0 && (
        <div className="flex justify-center">
          <div className="bg-purple-500/20 border border-purple-400/30 rounded-full px-4 py-2 text-purple-200">
            {selectedIds.size} character{selectedIds.size !== 1 ? 's' : ''} selected
          </div>
        </div>
      )}

      {/* Search */}
      <div className="max-w-xl mx-auto">
        <input
          type="text"
          placeholder="Search characters..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
        />
      </div>

      {/* Character Grid */}
      <div className="max-w-6xl mx-auto">
        {isLoading ? (
          <div className="text-center text-white/70 py-12">
            <div className="inline-block w-8 h-8 border-4 border-white/20 border-t-white rounded-full animate-spin mb-4"></div>
            <p>Loading your characters...</p>
          </div>
        ) : filteredCharacters.length === 0 ? (
          <div className="text-center text-white/70 py-12">
            <p className="text-lg mb-2">
              {searchQuery ? 'No characters found matching your search' : 'No characters in your library yet'}
            </p>
            <p className="text-sm">
              {!searchQuery && 'You can skip this step and create characters during brainstorming'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredCharacters.map((char) => {
              const isSelected = selectedIds.has(char.id);
              return (
                <div
                  key={char.id}
                  onClick={() => toggleCharacter(char.id)}
                  className={`
                    relative p-4 rounded-lg border-2 cursor-pointer transition-all
                    ${isSelected 
                      ? 'bg-purple-500/20 border-purple-400 shadow-lg shadow-purple-500/20' 
                      : 'bg-white/5 border-white/10 hover:border-white/30 hover:bg-white/10'
                    }
                  `}
                >
                  {/* Checkbox */}
                  <div className="absolute top-3 right-3">
                    <div className={`
                      w-6 h-6 rounded border-2 flex items-center justify-center transition-all
                      ${isSelected 
                        ? 'bg-purple-500 border-purple-400' 
                        : 'bg-white/10 border-white/30'
                      }
                    `}>
                      {isSelected && (
                        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                  </div>

                  {/* Character Info */}
                  <div className="pr-8">
                    <h3 className="text-lg font-semibold text-white mb-2">
                      {char.name}
                    </h3>
                    <p className="text-sm text-white/70 line-clamp-3 mb-3">
                      {char.description}
                    </p>
                    
                    {/* Personality Traits */}
                    {char.personality_traits && char.personality_traits.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {char.personality_traits.slice(0, 3).map((trait, i) => (
                          <span
                            key={i}
                            className="text-xs px-2 py-1 bg-white/10 text-white/80 rounded"
                          >
                            {trait}
                          </span>
                        ))}
                        {char.personality_traits.length > 3 && (
                          <span className="text-xs px-2 py-1 text-white/60">
                            +{char.personality_traits.length - 3} more
                          </span>
                        )}
                      </div>
                    )}

                    {/* Template Badge */}
                    {char.is_template && (
                      <div className="mt-2">
                        <span className="text-xs px-2 py-1 bg-blue-500/20 text-blue-300 rounded">
                          Template
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex justify-center gap-4 pt-6">
        <button
          onClick={onSkip}
          className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors border border-white/20"
        >
          Skip - No Existing Characters
        </button>
        <button
          onClick={handleContinue}
          disabled={selectedIds.size === 0}
          className={`
            px-6 py-3 rounded-lg transition-colors font-medium
            ${selectedIds.size > 0
              ? 'theme-btn-primary'
              : 'bg-white/5 text-white/40 cursor-not-allowed'
            }
          `}
        >
          Continue with {selectedIds.size > 0 ? selectedIds.size : ''} {selectedIds.size > 0 ? `Character${selectedIds.size !== 1 ? 's' : ''}` : 'Selected Characters'}
        </button>
      </div>
    </div>
  );
}

