'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';
import CharacterForm from '@/components/CharacterForm';

interface BrainstormCharacter {
  name: string;
  role: string;
  description: string;
  personality_traits?: string[];
}

interface PersistentCharacter {
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
  user_id?: number;
  creator_id?: number;
  created_at: string;
  updated_at: string | null;
}

interface CharacterMapping {
  brainstormChar: BrainstormCharacter;
  action: 'create' | 'use_existing' | 'skip';
  existingCharacterId?: number;
  newCharacterId?: number;
}

interface CharacterReviewProps {
  characters: BrainstormCharacter[];
  onComplete: (characterMappings: CharacterMapping[]) => void;
  onBack: () => void;
}

const CHARACTER_ROLE_ICONS: Record<string, string> = {
  protagonist: '⭐',
  antagonist: '⚔️',
  ally: '🤝',
  mentor: '🎓',
  love_interest: '💕',
  comic_relief: '😄',
  mysterious: '🎭',
  other: '👤'
};

export default function CharacterReview({ characters, onComplete, onBack }: CharacterReviewProps) {
  const [characterMappings, setCharacterMappings] = useState<CharacterMapping[]>(
    characters.map(char => ({
      brainstormChar: char,
      action: 'create' // Default to creating new characters
    }))
  );
  const [persistentCharacters, setPersistentCharacters] = useState<PersistentCharacter[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [creatingCharacters, setCreatingCharacters] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState<number | null>(null);
  const [showLibraryFor, setShowLibraryFor] = useState<number | null>(null);

  useEffect(() => {
    loadCharacterLibrary();
  }, []);

  const loadCharacterLibrary = async () => {
    try {
      setLoadingLibrary(true);
      const chars = await apiClient.getCharacters(0, 100, true, false); // Include user's characters
      setPersistentCharacters(chars);
    } catch (error) {
      console.error('Failed to load character library:', error);
    } finally {
      setLoadingLibrary(false);
    }
  };

  const updateMapping = (index: number, updates: Partial<CharacterMapping>) => {
    setCharacterMappings(prev => {
      const newMappings = [...prev];
      newMappings[index] = { ...newMappings[index], ...updates };
      return newMappings;
    });
  };

  const handleCreateCharacter = async (index: number) => {
    const mapping = characterMappings[index];
    const char = mapping.brainstormChar;

    try {
      const newChar = await apiClient.createCharacter({
        name: char.name,
        description: char.description,
        personality_traits: char.personality_traits || [],
        is_template: false,
        is_public: false
      });

      updateMapping(index, {
        action: 'create',
        newCharacterId: newChar.id
      });

      // Refresh library to show the newly created character
      await loadCharacterLibrary();
      setShowCreateForm(null);
    } catch (error) {
      console.error('Failed to create character:', error);
      alert('Failed to create character. Please try again.');
    }
  };

  const handleUseExisting = (index: number, characterId: number) => {
    updateMapping(index, {
      action: 'use_existing',
      existingCharacterId: characterId
    });
    setShowLibraryFor(null);
  };

  const handleSkip = (index: number) => {
    updateMapping(index, {
      action: 'skip'
    });
  };

  const handleComplete = async () => {
    setCreatingCharacters(true);
    try {
      // Create any remaining characters that are marked for creation but don't have IDs yet
      const updatedMappings = [...characterMappings];
      
      for (let i = 0; i < updatedMappings.length; i++) {
        const mapping = updatedMappings[i];
        if (mapping.action === 'create' && !mapping.newCharacterId) {
          const char = mapping.brainstormChar;
          const newChar = await apiClient.createCharacter({
            name: char.name,
            description: char.description,
            personality_traits: char.personality_traits || [],
            is_template: false,
            is_public: false
          });
          updatedMappings[i].newCharacterId = newChar.id;
        }
      }

      onComplete(updatedMappings);
    } catch (error) {
      console.error('Failed to create characters:', error);
      alert('Failed to create some characters. Please try again.');
    } finally {
      setCreatingCharacters(false);
    }
  };

  const getCharacterIcon = (role: string) => {
    return CHARACTER_ROLE_ICONS[role.toLowerCase()] || CHARACTER_ROLE_ICONS.other;
  };

  const getExistingCharacter = (characterId: number) => {
    return persistentCharacters.find(c => c.id === characterId);
  };

  return (
    <div className="space-y-6">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold text-white mb-2">Review Characters</h2>
        <p className="text-white/70">
          For each character, choose to create a new character, use an existing one, or skip
        </p>
      </div>

      <div className="space-y-4">
        {characterMappings.map((mapping, index) => {
          const char = mapping.brainstormChar;
          const existingChar = mapping.existingCharacterId 
            ? getExistingCharacter(mapping.existingCharacterId)
            : null;

          return (
            <div
              key={index}
              className="theme-bg-secondary rounded-lg p-6 border border-white/10"
            >
              <div className="flex items-start gap-4">
                <div className="text-4xl">{getCharacterIcon(char.role)}</div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-xl font-semibold text-white">{char.name}</h3>
                    <span className="text-sm px-2 py-1 rounded-full bg-white/10 text-white/70">
                      {char.role}
                    </span>
                  </div>
                  <p className="text-white/70 mb-4">{char.description}</p>

                  {/* Action Selection */}
                  <div className="flex flex-wrap gap-2 mb-4">
                    <button
                      onClick={() => updateMapping(index, { action: 'create', existingCharacterId: undefined })}
                      className={`px-4 py-2 rounded-lg transition-colors ${
                        mapping.action === 'create'
                          ? 'theme-accent-primary text-white'
                          : 'bg-white/10 text-white/70 hover:bg-white/20'
                      }`}
                    >
                      ✨ Create New
                    </button>
                    <button
                      onClick={() => setShowLibraryFor(index)}
                      className={`px-4 py-2 rounded-lg transition-colors ${
                        mapping.action === 'use_existing'
                          ? 'theme-accent-primary text-white'
                          : 'bg-white/10 text-white/70 hover:bg-white/20'
                      }`}
                    >
                      📚 Use Existing
                    </button>
                    <button
                      onClick={() => handleSkip(index)}
                      className={`px-4 py-2 rounded-lg transition-colors ${
                        mapping.action === 'skip'
                          ? 'bg-red-500/20 text-red-300'
                          : 'bg-white/10 text-white/70 hover:bg-white/20'
                      }`}
                    >
                      ⏭️ Skip
                    </button>
                  </div>

                  {/* Show selected existing character */}
                  {mapping.action === 'use_existing' && existingChar && (
                    <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                      <p className="text-sm text-green-300">
                        ✓ Will use: <strong>{existingChar.name}</strong>
                      </p>
                    </div>
                  )}

                  {/* Show character library */}
                  {showLibraryFor === index && (
                    <div className="mt-4 p-4 bg-black/30 rounded-lg max-h-64 overflow-y-auto">
                      <div className="flex justify-between items-center mb-3">
                        <h4 className="text-sm font-semibold text-white">Select Character</h4>
                        <button
                          onClick={() => setShowLibraryFor(null)}
                          className="text-white/50 hover:text-white"
                        >
                          ✕
                        </button>
                      </div>
                      {loadingLibrary ? (
                        <p className="text-white/50 text-sm">Loading...</p>
                      ) : persistentCharacters.length === 0 ? (
                        <p className="text-white/50 text-sm">No existing characters found</p>
                      ) : (
                        <div className="space-y-2">
                          {persistentCharacters.map(pChar => (
                            <button
                              key={pChar.id}
                              onClick={() => handleUseExisting(index, pChar.id)}
                              className="w-full text-left p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                            >
                              <p className="font-medium text-white">{pChar.name}</p>
                              <p className="text-sm text-white/60 line-clamp-1">
                                {pChar.description}
                              </p>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Show creation status */}
                  {mapping.action === 'create' && mapping.newCharacterId && (
                    <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                      <p className="text-sm text-blue-300">
                        ✓ Character created successfully
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Action Buttons */}
      <div className="flex justify-between pt-6">
        <button
          onClick={onBack}
          className="px-6 py-3 rounded-lg bg-white/10 text-white hover:bg-white/20 transition-colors"
          disabled={creatingCharacters}
        >
          ← Back
        </button>
        <button
          onClick={handleComplete}
          disabled={creatingCharacters}
          className="px-6 py-3 rounded-lg theme-accent-primary text-white hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {creatingCharacters ? (
            <>
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></span>
              Creating Characters...
            </>
          ) : (
            'Continue to Story Creation →'
          )}
        </button>
      </div>
    </div>
  );
}

