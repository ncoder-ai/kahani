'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';
import CharacterForm from '@/components/CharacterForm';

interface BrainstormCharacter {
  name: string;
  role: string;
  description: string;
  gender?: string;
  personality_traits?: string[];
  background?: string;
  goals?: string;
  fears?: string;
  appearance?: string;
  suggested_voice_style?: string;
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
  preSelectedCharacterIds?: number[];
  onComplete: (characterMappings: CharacterMapping[]) => void;
  onBack: () => void;
  continueButtonText?: string;
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

export default function CharacterReview({ characters, preSelectedCharacterIds = [], onComplete, onBack, continueButtonText = 'Continue to Story Creation →' }: CharacterReviewProps) {
  const [persistentCharacters, setPersistentCharacters] = useState<PersistentCharacter[]>([]);
  const [preSelectedCharacters, setPreSelectedCharacters] = useState<PersistentCharacter[]>([]);
  const [characterMappings, setCharacterMappings] = useState<CharacterMapping[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [creatingCharacters, setCreatingCharacters] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState<number | null>(null);
  const [showLibraryFor, setShowLibraryFor] = useState<number | null>(null);

  useEffect(() => {
    loadCharacterLibrary();
    loadPreSelectedCharacters();
  }, []);

  const loadPreSelectedCharacters = async () => {
    if (preSelectedCharacterIds.length === 0) {
      // No pre-selected characters, use all AI-generated characters
      setCharacterMappings(
        characters.map(char => ({
          brainstormChar: char,
          action: 'create'
        }))
      );
      return;
    }
    
    try {
      const chars = await Promise.all(
        preSelectedCharacterIds.map(id => apiClient.getCharacter(id))
      );
      setPreSelectedCharacters(chars);
      
      // Filter out AI-generated characters that match pre-selected character names
      // Use improved fuzzy matching to catch variations
      const preSelectedNames = chars.map(c => c.name.toLowerCase());
      console.log('[CharacterReview] Pre-selected character names:', preSelectedNames);
      console.log('[CharacterReview] AI-generated characters:', characters.map(c => c.name));
      
      const filteredCharacters = characters.filter(char => {
        const aiName = char.name.toLowerCase().trim();
        
        // Check for exact match
        if (preSelectedNames.includes(aiName)) {
          console.log(`[CharacterReview] Filtering out "${char.name}" - exact match`);
          return false;
        }
        
        // Check each pre-selected character
        for (const preSelectedName of preSelectedNames) {
          // Case 1: Substring match (one name fully contained in another)
          // This catches "John" in "John Smith" or vice versa
          if (preSelectedName.includes(aiName) || aiName.includes(preSelectedName)) {
            console.log(`[CharacterReview] Filtering out "${char.name}" - substring match with "${chars.find(c => c.name.toLowerCase() === preSelectedName)?.name}"`);
            return false;
          }
          
          // Case 2: Word-based matching for more complex cases
          const aiWords = aiName.split(/\s+/).filter(w => w.length > 2);
          const preSelectedWords = preSelectedName.split(/\s+/).filter(w => w.length > 2);
          
          if (aiWords.length === 0 || preSelectedWords.length === 0) continue;
          
          const sharedWords = aiWords.filter(w => preSelectedWords.includes(w));
          
          // If AI name is a single word and it matches any word in pre-selected name
          // This catches "Kate" matching "Kate Reynolds" or "Smith" matching "Dr. Smith"
          if (aiWords.length === 1 && sharedWords.length >= 1) {
            console.log(`[CharacterReview] Filtering out "${char.name}" - single word match with "${chars.find(c => c.name.toLowerCase() === preSelectedName)?.name}"`);
            return false;
          }
          
          // If they share 2+ significant words (existing logic for multi-word names)
          // This catches "Sheriff Reynolds" matching "Sheriff Kate Reynolds"
          if (sharedWords.length >= 2) {
            console.log(`[CharacterReview] Filtering out "${char.name}" - multi-word match with "${chars.find(c => c.name.toLowerCase() === preSelectedName)?.name}"`);
            return false;
          }
        }
        
        return true;
      });
      
      console.log('[CharacterReview] After filtering:', filteredCharacters.map(c => c.name));
      console.log('[CharacterReview] Filtered out', characters.length - filteredCharacters.length, 'duplicate characters');
      
      setCharacterMappings(
        filteredCharacters.map(char => ({
          brainstormChar: char,
          action: 'create'
        }))
      );
    } catch (error) {
      console.error('Failed to load pre-selected characters:', error);
    }
  };

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
        gender: char.gender || undefined,
        personality_traits: char.personality_traits || [],
        background: char.background || undefined,
        goals: char.goals || undefined,
        fears: char.fears || undefined,
        appearance: char.appearance || undefined,
        is_template: false,
        is_public: false,
        voice_style: char.suggested_voice_style ? { preset: char.suggested_voice_style } : undefined
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
            gender: char.gender || undefined,
            personality_traits: char.personality_traits || [],
            background: char.background || undefined,
            goals: char.goals || undefined,
            fears: char.fears || undefined,
            appearance: char.appearance || undefined,
            is_template: false,
            is_public: false,
            voice_style: char.suggested_voice_style ? { preset: char.suggested_voice_style } : undefined
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
          {preSelectedCharacters.length > 0 
            ? 'Your pre-selected characters will be automatically included. Review AI-suggested characters below.'
            : 'For each character, choose to create a new character, use an existing one, or skip'
          }
        </p>
      </div>

      {/* Pre-selected Characters Section */}
      {preSelectedCharacters.length > 0 && (
        <div className="space-y-4 mb-8">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-xl font-semibold text-white">Your Characters</h3>
            <span className="text-sm px-3 py-1 rounded-full bg-green-500/20 text-green-300 border border-green-500/30">
              {preSelectedCharacters.length} pre-selected
            </span>
          </div>
          {preSelectedCharacters.map((char) => (
            <div
              key={char.id}
              className="theme-bg-secondary rounded-lg p-6 border-2 border-green-500/30 bg-green-500/5"
            >
              <div className="flex items-start gap-4">
                <div className="text-4xl">👤</div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-xl font-semibold text-white">{char.name}</h3>
                    <span className="text-sm px-2 py-1 rounded-full bg-green-500/20 text-green-300">
                      ✓ Auto-included
                    </span>
                  </div>
                  <p className="text-white/70 mb-3">{char.description}</p>
                  {char.personality_traits && char.personality_traits.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {char.personality_traits.map((trait, i) => (
                        <span
                          key={i}
                          className="text-xs px-2 py-1 bg-white/10 text-white/80 rounded"
                        >
                          {trait}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* AI-Generated Characters Section */}
      {characterMappings.length > 0 && (
        <div className="space-y-4">
          {preSelectedCharacters.length > 0 && (
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-xl font-semibold text-white">AI-Suggested Characters</h3>
              <span className="text-sm px-3 py-1 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                {characterMappings.length} suggested
              </span>
            </div>
          )}
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
      )}

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
            continueButtonText
          )}
        </button>
      </div>
    </div>
  );
}

