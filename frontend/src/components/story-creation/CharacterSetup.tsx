'use client';

import { useState, useEffect } from 'react';
import { StoryData } from '@/app/create-story/page';
import apiClient from '@/lib/api';
import CharacterForm from '@/components/CharacterForm';

interface CharacterSetupProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  onBack: () => void;
}

interface Character {
  name: string;
  role: string;
  description: string;
  id?: number; // Optional for persistent characters
}

interface PersistentCharacter {
  id: number;
  name: string;
  description: string;
  personality_traits: string[];
  background: string;
  goals: string;
  fears: string;
  appearance: string;
  is_template: boolean;
  is_public: boolean;
  creator_id: number;
  created_at: string;
  updated_at: string | null;
}

interface CharacterSetupProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  onBack: () => void;
}

interface Character {
  name: string;
  role: string;
  description: string;
}

const CHARACTER_ROLES = [
  { id: 'protagonist', name: 'Main Character', icon: '⭐', color: 'from-yellow-400 to-orange-500' },
  { id: 'antagonist', name: 'Antagonist', icon: '⚔️', color: 'from-red-500 to-red-700' },
  { id: 'ally', name: 'Ally/Friend', icon: '🤝', color: 'from-green-400 to-green-600' },
  { id: 'mentor', name: 'Mentor', icon: '🎓', color: 'from-blue-400 to-blue-600' },
  { id: 'love_interest', name: 'Love Interest', icon: '💕', color: 'from-pink-400 to-pink-600' },
  { id: 'comic_relief', name: 'Comic Relief', icon: '😄', color: 'from-purple-400 to-purple-600' },
  { id: 'mysterious', name: 'Mysterious Figure', icon: '🎭', color: 'from-gray-500 to-gray-700' },
  { id: 'other', name: 'Other', icon: '👤', color: 'from-indigo-400 to-indigo-600' }
];

export default function CharacterSetup({ storyData, onUpdate, onNext, onBack }: CharacterSetupProps) {
  const [characters, setCharacters] = useState<Character[]>(storyData.characters || []);
  const [persistentCharacters, setPersistentCharacters] = useState<PersistentCharacter[]>([]);
  const [currentCharacter, setCurrentCharacter] = useState<Partial<Character>>({});
  const [isAdding, setIsAdding] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [loadingLibrary, setLoadingLibrary] = useState(false);

  useEffect(() => {
    if (showLibrary && persistentCharacters.length === 0) {
      loadCharacterLibrary();
    }
  }, [showLibrary]);

  const loadCharacterLibrary = async () => {
    try {
      setLoadingLibrary(true);
      const characters = await apiClient.getCharacters(0, 50, true, true); // Include public, templates only
      setPersistentCharacters(characters);
    } catch (error) {
      console.error('Failed to load character library:', error);
    } finally {
      setLoadingLibrary(false);
    }
  };

  const addPersistentCharacter = (persistentChar: PersistentCharacter, role: string) => {
    const newCharacter: Character = {
      id: persistentChar.id,
      name: persistentChar.name,
      role: role,
      description: persistentChar.description
    };
    
    const updatedCharacters = [...characters, newCharacter];
    setCharacters(updatedCharacters);
    onUpdate({ characters: updatedCharacters });
    setShowLibrary(false);
  };

  const handleCreateNewCharacter = (character: any) => {
    if (character) {
      // Character was created, add it to the story
      const newCharacter: Character = {
        id: character.id,
        name: character.name,
        role: currentCharacter.role || 'other',
        description: character.description
      };
      
      const updatedCharacters = [...characters, newCharacter];
      setCharacters(updatedCharacters);
      onUpdate({ characters: updatedCharacters });
    }
    
    setShowCreateForm(false);
    setCurrentCharacter({});
  };

  const handleAddCharacter = () => {
    if (currentCharacter.name && currentCharacter.role) {
      const newCharacter: Character = {
        name: currentCharacter.name,
        role: currentCharacter.role,
        description: currentCharacter.description || ''
      };
      const updatedCharacters = [...characters, newCharacter];
      setCharacters(updatedCharacters);
      onUpdate({ characters: updatedCharacters });
      setCurrentCharacter({});
      setIsAdding(false);
    }
  };

  const handleRemoveCharacter = (index: number) => {
    const updatedCharacters = characters.filter((_, i) => i !== index);
    setCharacters(updatedCharacters);
    onUpdate({ characters: updatedCharacters });
  };

  const handleEditCharacter = (index: number, character: Character) => {
    const updatedCharacters = [...characters];
    updatedCharacters[index] = character;
    setCharacters(updatedCharacters);
    onUpdate({ characters: updatedCharacters });
  };

  const getRoleInfo = (roleId: string) => {
    return CHARACTER_ROLES.find(role => role.id === roleId) || CHARACTER_ROLES[CHARACTER_ROLES.length - 1];
  };

  const canProceed = characters.length > 0;

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Create Your Characters</h2>
        <p className="text-white/80 text-lg">
          Add the key characters that will drive your story forward
        </p>
        <div className="mt-3 text-sm text-white/60">
          💡 Tip: You can add more characters at any time using the "+ Add Character" button in the header
        </div>
      </div>

      {/* Existing Characters */}
      {characters.length > 0 && (
        <div className="grid gap-4">
          {characters.map((character, index) => {
            const roleInfo = getRoleInfo(character.role);
            return (
              <div
                key={index}
                className="bg-white/10 border border-white/30 rounded-xl p-6 relative group"
              >
                <button
                  onClick={() => handleRemoveCharacter(index)}
                  className="absolute top-3 right-3 text-white/60 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  ✕
                </button>
                <div className="flex items-start space-x-4">
                  <div className={`w-12 h-12 rounded-full bg-gradient-to-r ${roleInfo.color} flex items-center justify-center text-white text-xl`}>
                    {roleInfo.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-white">{character.name}</h3>
                    <p className="text-purple-300 font-medium">{roleInfo.name}</p>
                    {character.description && (
                      <p className="text-white/70 mt-2">{character.description}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Character Form */}
      {isAdding ? (
        <div className="bg-white/10 border border-white/30 rounded-xl p-6 space-y-4">
          <h3 className="text-xl font-semibold text-white">Add New Character</h3>
          
          <div>
            <label className="block text-white/80 mb-2">Character Name</label>
            <input
              type="text"
              value={currentCharacter.name || ''}
              onChange={(e) => setCurrentCharacter({ ...currentCharacter, name: e.target.value })}
              placeholder="Enter character name..."
              className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          <div>
            <label className="block text-white/80 mb-2">Character Role</label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {CHARACTER_ROLES.map((role) => (
                <button
                  key={role.id}
                  onClick={() => setCurrentCharacter({ ...currentCharacter, role: role.id })}
                  className={`p-3 rounded-lg border transition-all duration-200 ${
                    currentCharacter.role === role.id
                      ? `bg-gradient-to-r ${role.color} text-white border-transparent`
                      : 'bg-white/10 border-white/30 text-white hover:bg-white/20'
                  }`}
                >
                  <div className="text-lg mb-1">{role.icon}</div>
                  <div className="text-xs font-medium">{role.name}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-white/80 mb-2">Description (Optional)</label>
            <textarea
              value={currentCharacter.description || ''}
              onChange={(e) => setCurrentCharacter({ ...currentCharacter, description: e.target.value })}
              placeholder="Describe this character..."
              rows={3}
              className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          <div className="flex space-x-3">
            <button
              onClick={handleAddCharacter}
              disabled={!currentCharacter.name || !currentCharacter.role}
              className={`px-6 py-2 rounded-lg font-semibold transition-colors ${
                currentCharacter.name && currentCharacter.role
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
                  : 'bg-white/20 text-white/50 cursor-not-allowed'
              }`}
            >
              Add Character
            </button>
            <button
              onClick={() => {
                setIsAdding(false);
                setCurrentCharacter({});
              }}
              className="px-6 py-2 rounded-lg font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-center">
            <p className="text-white/80 mb-4">Add characters to your story</p>
            <div className="flex justify-center gap-4">
              <button
                onClick={() => setShowLibrary(true)}
                className="px-6 py-3 bg-gradient-to-r from-blue-500 to-cyan-500 text-white rounded-xl hover:from-blue-600 hover:to-cyan-600 transition-colors font-semibold"
              >
                📚 Choose from Library
              </button>
              <button
                onClick={() => setIsAdding(true)}
                className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:from-purple-600 hover:to-pink-600 transition-colors font-semibold"
              >
                ✏️ Create New
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Character Library Modal */}
      {showLibrary && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-xl max-w-4xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-6 border-b border-white/20">
              <div className="flex justify-between items-center">
                <h3 className="text-2xl font-bold text-white">Choose Character from Library</h3>
                <button
                  onClick={() => setShowLibrary(false)}
                  className="text-white/60 hover:text-white text-xl"
                >
                  ✕
                </button>
              </div>
              <p className="text-white/80 mt-2">Select a character and assign them a role in your story</p>
            </div>
            
            <div className="p-6 overflow-y-auto max-h-96">
              {loadingLibrary ? (
                <div className="text-center py-8">
                  <div className="text-white">Loading characters...</div>
                </div>
              ) : persistentCharacters.length === 0 ? (
                <div className="text-center py-8">
                  <div className="text-white/60 mb-4">No characters found in your library</div>
                  <button
                    onClick={() => {
                      setShowLibrary(false);
                      setShowCreateForm(true);
                    }}
                    className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600"
                  >
                    Create Your First Character
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {persistentCharacters.map((char) => (
                    <div key={char.id} className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <h4 className="text-lg font-semibold text-white mb-2">{char.name}</h4>
                      <p className="text-white/70 text-sm mb-3 line-clamp-2">{char.description}</p>
                      
                      {char.personality_traits.length > 0 && (
                        <div className="mb-3">
                          <div className="flex flex-wrap gap-1">
                            {char.personality_traits.slice(0, 3).map((trait, index) => (
                              <span key={index} className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded">
                                {trait}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="space-y-2">
                        <p className="text-white/60 text-sm">Assign role:</p>
                        <div className="grid grid-cols-2 gap-2">
                          {CHARACTER_ROLES.slice(0, 4).map((role) => (
                            <button
                              key={role.id}
                              onClick={() => addPersistentCharacter(char, role.id)}
                              className="px-3 py-2 bg-white/10 text-white text-sm rounded hover:bg-white/20 transition-colors"
                            >
                              {role.icon} {role.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            <div className="p-6 border-t border-white/20">
              <button
                onClick={() => {
                  setShowLibrary(false);
                  setShowCreateForm(true);
                }}
                className="w-full px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:from-purple-600 hover:to-pink-600 transition-colors"
              >
                + Create New Character Instead
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Character Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
            <div className="p-6 border-b border-white/20">
              <h3 className="text-2xl font-bold text-white">Create New Character</h3>
              <p className="text-white/80 mt-2">This character will be saved to your library for reuse</p>
            </div>
            
            <div className="overflow-y-auto max-h-[70vh]">
              <div className="p-6">
                <CharacterForm 
                  mode="inline"
                  onSave={handleCreateNewCharacter}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between pt-6">
        <button
          onClick={onBack}
          className="px-8 py-3 rounded-xl font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors"
        >
          ← Back
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={`px-8 py-3 rounded-xl font-semibold transition-all duration-200 ${
            canProceed
              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600'
              : 'bg-white/20 text-white/50 cursor-not-allowed'
          }`}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}