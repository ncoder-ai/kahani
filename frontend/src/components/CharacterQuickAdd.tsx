'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';
import CharacterForm from '@/components/CharacterForm';

interface Character {
  name: string;
  role: string;
  description: string;
  id?: number;
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
  updated_at?: string;
}

interface CharacterQuickAddProps {
  onCharacterAdd: (character: Character) => void;
  onClose: () => void;
  existingCharacters: Character[];
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

export default function CharacterQuickAdd({ onCharacterAdd, onClose, existingCharacters }: CharacterQuickAddProps) {
  const [activeTab, setActiveTab] = useState<'library' | 'create' | 'quick'>('quick');
  const [persistentCharacters, setPersistentCharacters] = useState<PersistentCharacter[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [quickCharacter, setQuickCharacter] = useState<Partial<Character>>({});

  useEffect(() => {
    if (activeTab === 'library' && persistentCharacters.length === 0) {
      loadCharacterLibrary();
    }
  }, [activeTab]);

  const loadCharacterLibrary = async () => {
    try {
      setLoadingLibrary(true);
      const characters = await apiClient.getCharacters(0, 50, true, true);
      // Filter out characters already in the story
      const availableCharacters = characters.filter(char => 
        !existingCharacters.some(existing => existing.id === char.id)
      );
      setPersistentCharacters(availableCharacters);
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
    onCharacterAdd(newCharacter);
    onClose();
  };

  const handleCreateNewCharacter = (character: any) => {
    if (character) {
      const newCharacter: Character = {
        id: character.id,
        name: character.name,
        role: quickCharacter.role || 'other',
        description: character.description
      };
      onCharacterAdd(newCharacter);
    }
    onClose();
  };

  const handleQuickAdd = () => {
    if (quickCharacter.name && quickCharacter.role) {
      const newCharacter: Character = {
        name: quickCharacter.name,
        role: quickCharacter.role,
        description: quickCharacter.description || ''
      };
      onCharacterAdd(newCharacter);
      onClose();
    }
  };

  const getRoleInfo = (roleId: string) => {
    return CHARACTER_ROLES.find(role => role.id === roleId) || CHARACTER_ROLES[CHARACTER_ROLES.length - 1];
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
        <div className="p-6 border-b border-white/20">
          <div className="flex justify-between items-center">
            <h3 className="text-2xl font-bold text-white">Add Character to Story</h3>
            <button
              onClick={onClose}
              className="text-white/60 hover:text-white text-xl"
            >
              ✕
            </button>
          </div>
          
          {/* Tabs */}
          <div className="flex space-x-4 mt-4">
            <button
              onClick={() => setActiveTab('quick')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'quick'
                  ? 'bg-purple-500 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              Quick Add
            </button>
            <button
              onClick={() => setActiveTab('library')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'library'
                  ? 'bg-purple-500 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              From Library
            </button>
            <button
              onClick={() => setActiveTab('create')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'create'
                  ? 'bg-purple-500 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              Create New
            </button>
          </div>
        </div>
        
        <div className="overflow-y-auto max-h-[70vh]">
          <div className="p-6">
            {activeTab === 'quick' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-white/80 mb-2">Character Name</label>
                  <input
                    type="text"
                    value={quickCharacter.name || ''}
                    onChange={(e) => setQuickCharacter({ ...quickCharacter, name: e.target.value })}
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
                        onClick={() => setQuickCharacter({ ...quickCharacter, role: role.id })}
                        className={`p-3 rounded-lg border transition-all duration-200 ${
                          quickCharacter.role === role.id
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
                    value={quickCharacter.description || ''}
                    onChange={(e) => setQuickCharacter({ ...quickCharacter, description: e.target.value })}
                    placeholder="Describe this character..."
                    rows={3}
                    className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>

                <button
                  onClick={handleQuickAdd}
                  disabled={!quickCharacter.name || !quickCharacter.role}
                  className={`w-full px-6 py-3 rounded-lg font-semibold transition-colors ${
                    quickCharacter.name && quickCharacter.role
                      ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600'
                      : 'bg-white/20 text-white/50 cursor-not-allowed'
                  }`}
                >
                  Add Character
                </button>
              </div>
            )}

            {activeTab === 'library' && (
              <div>
                {loadingLibrary ? (
                  <div className="text-center py-8">
                    <div className="text-white">Loading characters...</div>
                  </div>
                ) : persistentCharacters.length === 0 ? (
                  <div className="text-center py-8">
                    <div className="text-white/60 mb-4">No available characters in your library</div>
                    <button
                      onClick={() => setActiveTab('create')}
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
            )}

            {activeTab === 'create' && (
              <div>
                <CharacterForm 
                  mode="inline"
                  onSave={handleCreateNewCharacter}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}