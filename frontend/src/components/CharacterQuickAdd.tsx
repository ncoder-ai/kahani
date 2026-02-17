'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';
import CharacterForm from '@/components/CharacterForm';
import { CHARACTER_ROLES, getRoleInfo } from '@/components/RoleSelector';

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
  updated_at: string | null;
}

interface CharacterQuickAddProps {
  onCharacterAdd: (character: Character) => void;
  onClose: () => void;
  existingCharacters: Character[];
  storyId?: number;
  chapterId?: number;
  onOpenCharacterWizard?: () => void;
}

// Inline role selector for library - supports custom roles
function QuickAddRoleSelector({ onRoleSelect }: { onRoleSelect: (role: string) => void }) {
  const [showAllRoles, setShowAllRoles] = useState(false);
  const [customRole, setCustomRole] = useState('');

  if (showAllRoles) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-white/60 text-sm">Assign role:</p>
          <button
            onClick={() => setShowAllRoles(false)}
            className="text-xs text-white/50 hover:text-white/80"
          >
            ← Back
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {CHARACTER_ROLES.map((role) => (
            <button
              key={role.id}
              onClick={() => {
                if (role.id !== 'other') {
                  onRoleSelect(role.id);
                }
              }}
              className={`px-3 py-2 bg-white/10 text-white text-sm rounded hover:bg-white/20 transition-colors ${
                role.id === 'other' ? 'col-span-2 border border-dashed border-white/30' : ''
              }`}
            >
              {role.icon} {role.name}
            </button>
          ))}
        </div>
        {/* Custom role input */}
        <div className="mt-2">
          <input
            type="text"
            value={customRole}
            onChange={(e) => setCustomRole(e.target.value)}
            placeholder="Or enter custom role..."
            className="w-full p-2 bg-white/10 border border-white/30 rounded text-white placeholder-white/50 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          {customRole.trim() && (
            <button
              onClick={() => onRoleSelect(customRole.trim())}
              className="w-full mt-2 px-3 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 transition-colors"
            >
              Add as "{customRole.trim()}"
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-white/60 text-sm">Assign role:</p>
      <div className="grid grid-cols-2 gap-2">
        {CHARACTER_ROLES.slice(0, 4).map((role) => (
          <button
            key={role.id}
            onClick={() => onRoleSelect(role.id)}
            className="px-3 py-2 bg-white/10 text-white text-sm rounded hover:bg-white/20 transition-colors"
          >
            {role.icon} {role.name}
          </button>
        ))}
      </div>
      <button
        onClick={() => setShowAllRoles(true)}
        className="w-full px-3 py-2 bg-white/5 text-white/70 text-sm rounded hover:bg-white/10 transition-colors border border-dashed border-white/20"
      >
        More roles...
      </button>
    </div>
  );
}

export default function CharacterQuickAdd({ onCharacterAdd, onClose, existingCharacters, storyId, chapterId, onOpenCharacterWizard }: CharacterQuickAddProps) {
  const [activeTab, setActiveTab] = useState<'library' | 'create' | 'discover'>('library');
  const [persistentCharacters, setPersistentCharacters] = useState<PersistentCharacter[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);

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
        role: 'other', // Default role, user can change this later if needed
        description: character.description
      };
      onCharacterAdd(newCharacter);
    }
    onClose();
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
              onClick={() => setActiveTab('library')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'library'
                  ? 'theme-btn-primary'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              From Library
            </button>
            <button
              onClick={() => setActiveTab('create')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'create'
                  ? 'theme-btn-primary'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              Create New
            </button>
            {storyId && onOpenCharacterWizard && (
              <button
                onClick={() => setActiveTab('discover')}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  activeTab === 'discover'
                    ? 'bg-purple-500 text-white'
                    : 'bg-white/10 text-white/70 hover:bg-white/20'
                }`}
              >
                Discover from Story
              </button>
            )}
          </div>
        </div>
        
        <div className="overflow-y-auto max-h-[70vh]">
          <div className="p-6">
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
                      className="px-4 py-2 theme-btn-primary rounded-lg hover:bg-opacity-80"
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
                                <span key={index} className="px-2 py-1 text-xs rounded"
                                      style={{ backgroundColor: 'var(--color-accentPrimary)', opacity: 0.2, color: 'var(--color-accentPrimary)' } as React.CSSProperties}>
                                  {trait}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        <QuickAddRoleSelector 
                          onRoleSelect={(role) => addPersistentCharacter(char, role)}
                        />
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

            {activeTab === 'discover' && (
              <div className="text-center py-12">
                <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6"
                     style={{ background: 'linear-gradient(to right, var(--color-accentPrimary), var(--color-accentSecondary))' } as React.CSSProperties}>
                  <span className="text-2xl">🔍</span>
                </div>
                <h3 className="text-xl font-semibold text-white mb-4">Discover Characters from Your Story</h3>
                <p className="text-white/70 mb-8 max-w-md mx-auto">
                  Let AI analyze your story content to find characters that might be worth adding to your character library.
                </p>
                <button
                  onClick={() => {
                    onClose();
                    onOpenCharacterWizard?.();
                  }}
                  className="px-6 py-3 theme-btn-primary rounded-lg transition-all font-semibold"
                >
                  Analyze Current Chapter
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}