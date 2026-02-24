'use client';

import { useState, useEffect } from 'react';
import { StoryData } from '@/app/create-story/page';
import apiClient from '@/lib/api';
import CharacterForm from '@/components/CharacterForm';
import RoleSelector, { CHARACTER_ROLES, getRoleInfo } from '@/components/RoleSelector';

// Inline role selector for library modal - supports custom roles
function LibraryCharacterRoleSelector({ onRoleSelect }: { onRoleSelect: (role: string) => void }) {
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
                if (role.id === 'other') {
                  // Don't close, show custom input
                } else {
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
  gender?: string;
  id?: number; // Optional for persistent characters
}

interface PersistentCharacter {
  id: number;
  name: string;
  description: string;
  gender?: string;
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
      // Load both user's characters and public templates
      console.log('[CharacterSetup] Loading characters with params: skip=0, limit=100, includePublic=true, templatesOnly=false');
      const characters = await apiClient.getCharacters(0, 100, true, false);
      console.log('[CharacterSetup] Loaded characters:', characters.length, 'characters');
      console.log('[CharacterSetup] Characters:', characters.map(c => ({ id: c.id, name: c.name, is_template: c.is_template })));
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
      description: persistentChar.description,
      gender: persistentChar.gender
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
        description: character.description,
        gender: character.gender
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

  const getCharacterRoleInfo = (roleId: string) => {
    return getRoleInfo(roleId) || CHARACTER_ROLES[CHARACTER_ROLES.length - 1];
  };

  const canProceed = characters.length > 0;

  return (
    <div className="space-y-4 sm:space-y-8">
      <div className="text-center">
        <h2 className="text-xl sm:text-3xl font-bold text-white mb-2 sm:mb-4">Create Your Characters</h2>
        <p className="text-white/80 text-sm sm:text-lg">
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
            const roleInfo = getCharacterRoleInfo(character.role);
            return (
              <div
                key={index}
                className="bg-white/10 border border-white/30 rounded-xl p-4 sm:p-6 relative group"
              >
                <button
                  onClick={() => handleRemoveCharacter(index)}
                  className="absolute top-3 right-3 text-white/60 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  ✕
                </button>
                <div className="flex items-start space-x-3 sm:space-x-4">
                  <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-gradient-to-r ${roleInfo.color} flex items-center justify-center text-white text-base sm:text-xl`}>
                    {roleInfo.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-base sm:text-xl font-semibold text-white">{character.name}</h3>
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
        <div className="bg-white/10 border border-white/30 rounded-xl p-4 sm:p-6 space-y-4">
          <h3 className="text-base sm:text-xl font-semibold text-white">Add New Character</h3>
          
          <div>
            <label className="block text-white/80 mb-2">Character Name</label>
            <input
              type="text"
              value={currentCharacter.name ?? ''}
              onChange={(e) => setCurrentCharacter({ ...currentCharacter, name: e.target.value })}
              placeholder="Enter character name..."
                    className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
            />
          </div>

          <RoleSelector
            value={currentCharacter.role ?? ''}
            onChange={(role) => setCurrentCharacter({ ...currentCharacter, role })}
            label="Character Role"
          />

          <div>
            <label className="block text-white/80 mb-2">Description (Optional)</label>
            <textarea
              value={currentCharacter.description ?? ''}
              onChange={(e) => setCurrentCharacter({ ...currentCharacter, description: e.target.value })}
              placeholder="Describe this character..."
              rows={3}
                    className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
            />
          </div>

          <div className="flex space-x-3">
            <button
              onClick={handleAddCharacter}
              disabled={!currentCharacter.name || !currentCharacter.role}
              className={`px-6 py-2 rounded-lg font-semibold transition-colors ${
                currentCharacter.name && currentCharacter.role
                  ? 'theme-btn-primary'
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
                className="px-6 py-3 theme-btn-secondary rounded-xl transition-colors font-semibold"
              >
                📚 Choose from Library
              </button>
              <button
                onClick={() => setIsAdding(true)}
                className="px-6 py-3 theme-btn-primary rounded-xl transition-colors font-semibold"
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
          <div className="theme-bg-secondary rounded-xl max-w-4xl w-full max-h-[80vh] overflow-hidden border theme-border-accent">
            <div className="p-4 sm:p-6 border-b border-white/20">
              <div className="flex justify-between items-center">
                <h3 className="text-xl sm:text-2xl font-bold text-white">Choose Character from Library</h3>
                <button
                  onClick={() => setShowLibrary(false)}
                  className="text-white/60 hover:text-white text-xl"
                >
                  ✕
                </button>
              </div>
              <p className="text-white/80 mt-2">Select a character and assign them a role in your story</p>
            </div>
            
            <div className="p-4 sm:p-6 overflow-y-auto max-h-96">
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
                    className="px-4 py-2 theme-btn-primary rounded-lg"
                  >
                    Create Your First Character
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {persistentCharacters.map((char) => (
                    <div key={char.id} className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <h4 className="text-base sm:text-lg font-semibold text-white mb-2">{char.name}</h4>
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

                      <LibraryCharacterRoleSelector 
                        onRoleSelect={(role) => addPersistentCharacter(char, role)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            <div className="p-4 sm:p-6 border-t border-white/20">
              <button
                onClick={() => {
                  setShowLibrary(false);
                  setShowCreateForm(true);
                }}
                className="w-full px-4 py-2 theme-btn-primary rounded-lg transition-colors"
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
          <div className="theme-bg-secondary rounded-xl max-w-2xl w-full max-h-[90vh] overflow-hidden border theme-border-accent">
            <div className="p-4 sm:p-6 border-b border-white/20">
              <h3 className="text-xl sm:text-2xl font-bold text-white">Create New Character</h3>
              <p className="text-white/80 mt-2">This character will be saved to your library for reuse</p>
            </div>
            
            <div className="overflow-y-auto max-h-[70vh]">
              <div className="p-6">
                <CharacterForm
                  mode="inline"
                  onSave={handleCreateNewCharacter}
                  storyContext={{
                    genre: storyData.genre || undefined,
                    tone: storyData.tone || undefined,
                    world_setting: storyData.world_setting || undefined,
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between pt-4 sm:pt-6">
        <button
          onClick={onBack}
          className="px-5 sm:px-8 py-2.5 sm:py-3 rounded-xl font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors"
        >
          ← Back
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={`px-5 sm:px-8 py-2.5 sm:py-3 rounded-xl font-semibold transition-all duration-200 ${
            canProceed
              ? 'theme-btn-primary'
              : 'bg-white/20 text-white/50 cursor-not-allowed'
          }`}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}