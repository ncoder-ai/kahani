'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';
import { useUISettings } from '@/hooks/useUISettings';
import Link from 'next/link';
import { Trash2, X } from 'lucide-react';

interface Character {
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

// Confirmation dialog state
interface DeleteConfirmation {
  type: 'single' | 'bulk';
  characterId?: number;
  characterName?: string;
  count?: number;
}

export default function CharacterLibrary() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'mine' | 'public'>('all');
  const [templatesOnly, setTemplatesOnly] = useState(false);
  const [userSettings, setUserSettings] = useState<any>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState<DeleteConfirmation | null>(null);

  // Apply UI settings (theme, font size, etc.)
  useUISettings(userSettings?.ui_preferences || null);

  useEffect(() => {
    loadCharacters();
    loadUserSettings();
  }, [filter, templatesOnly]);

  const loadUserSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings.settings);
    } catch (err) {
      console.error('Failed to load user settings:', err);
    }
  };

  const loadCharacters = async () => {
    try {
      setLoading(true);
      const includePublic = filter !== 'mine';
      const data = await apiClient.getCharacters(0, 50, includePublic, templatesOnly);
      
      // Filter based on selected filter
      let filteredData = data;
      if (filter === 'public') {
        // Only show public characters from others (would need user info to filter properly)
        filteredData = data.filter(char => char.is_public);
      }
      
      setCharacters(filteredData);
      // Clear selection when reloading
      setSelectedIds(new Set());
    } catch (error) {
      console.error('Failed to load characters:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelection = (id: number) => {
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

  const selectAll = () => {
    if (selectedIds.size === characters.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(characters.map(c => c.id)));
    }
  };

  // Show confirmation dialog for single delete
  const promptDeleteCharacter = (id: number) => {
    const character = characters.find(c => c.id === id);
    setDeleteConfirmation({
      type: 'single',
      characterId: id,
      characterName: character?.name || 'this character'
    });
  };

  // Show confirmation dialog for bulk delete
  const promptBulkDelete = () => {
    if (selectedIds.size === 0) return;
    setDeleteConfirmation({
      type: 'bulk',
      count: selectedIds.size
    });
  };

  // Actually perform the delete after confirmation
  const confirmDelete = async () => {
    if (!deleteConfirmation) return;

    setIsDeleting(true);
    try {
      if (deleteConfirmation.type === 'single' && deleteConfirmation.characterId) {
        await apiClient.deleteCharacter(deleteConfirmation.characterId);
        setCharacters(characters.filter(char => char.id !== deleteConfirmation.characterId));
        setSelectedIds(prev => {
          const newSet = new Set(prev);
          newSet.delete(deleteConfirmation.characterId!);
          return newSet;
        });
      } else if (deleteConfirmation.type === 'bulk') {
        const result = await apiClient.bulkDeleteCharacters(Array.from(selectedIds));
        setCharacters(characters.filter(char => !result.deleted_ids.includes(char.id)));
        setSelectedIds(new Set());
      }
    } catch (error) {
      console.error('Failed to delete character(s):', error);
      alert('Failed to delete. The character(s) may be in use in stories.');
    } finally {
      setIsDeleting(false);
      setDeleteConfirmation(null);
    }
  };

  const cancelDelete = () => {
    setDeleteConfirmation(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center pt-16">
        <div className="text-white text-xl">Loading characters...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen theme-bg-primary p-6 pt-16">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-bold text-white mb-2">Character Library</h1>
            <p className="text-white/80">Manage your characters across all stories</p>
          </div>
          <Link
            href="/characters/create"
            className="px-6 py-3 theme-btn-primary rounded-xl transition-colors font-semibold"
          >
            + Create Character
          </Link>
        </div>

        {/* Filters */}
        <div className="bg-white/10 rounded-xl p-6 mb-8">
          <div className="flex flex-wrap gap-4 items-center justify-between">
            <div className="flex flex-wrap gap-4 items-center">
              <div className="flex gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    setFilter('all');
                  }}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors touch-manipulation min-h-[44px] ${
                    filter === 'all'
                      ? 'theme-btn-primary'
                      : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                  }`}
                >
                  All Characters
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    setFilter('mine');
                  }}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors touch-manipulation min-h-[44px] ${
                    filter === 'mine'
                      ? 'theme-btn-primary'
                      : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                  }`}
                >
                  My Characters
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    setFilter('public');
                  }}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors touch-manipulation min-h-[44px] ${
                    filter === 'public'
                      ? 'theme-btn-primary'
                      : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                  }`}
                >
                  Public Gallery
                </button>
              </div>
              
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="templates-only"
                  checked={templatesOnly}
                  onChange={(e) => setTemplatesOnly(e.target.checked)}
                  className="rounded"
                />
                <label htmlFor="templates-only" className="text-white text-sm">
                  Templates only
                </label>
              </div>
            </div>

            {/* Bulk Actions */}
            {characters.length > 0 && (
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    selectAll();
                  }}
                  className="px-4 py-2 bg-white/20 text-white text-sm rounded hover:bg-white/30 active:bg-white/40 transition-colors touch-manipulation min-h-[44px]"
                >
                  {selectedIds.size === characters.length ? 'Deselect All' : 'Select All'}
                </button>
                {selectedIds.size > 0 && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      promptBulkDelete();
                    }}
                    disabled={isDeleting}
                    className="px-4 py-2 bg-red-500/80 text-white text-sm rounded hover:bg-red-600 active:bg-red-700 transition-colors flex items-center gap-2 disabled:opacity-50 touch-manipulation min-h-[44px]"
                  >
                    <Trash2 className="w-4 h-4" />
                    {isDeleting ? 'Deleting...' : `Delete (${selectedIds.size})`}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Characters Grid */}
        {characters.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-white/60 text-lg mb-4">No characters found</div>
            <Link
              href="/characters/create"
              className="inline-flex px-6 py-3 theme-btn-primary rounded-xl transition-colors font-semibold"
            >
              Create Your First Character
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {characters.map((character) => (
              <div 
                key={character.id} 
                className={`bg-white/10 rounded-xl p-6 hover:bg-white/15 transition-colors relative ${
                  selectedIds.has(character.id) ? 'ring-2 ring-blue-500' : ''
                }`}
              >
                {/* Selection Checkbox */}
                <div className="absolute top-4 left-4">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(character.id)}
                    onChange={() => toggleSelection(character.id)}
                    className="w-5 h-5 rounded border-white/30 bg-white/10 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
                  />
                </div>

                <div className="flex justify-between items-start mb-4 pl-8">
                  <div>
                    <h3 className="text-xl font-bold text-white">{character.name}</h3>
                    {character.gender && (
                      <span className="text-white/50 text-xs capitalize">{character.gender}</span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {character.is_template && (
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-300 text-xs rounded">
                        Template
                      </span>
                    )}
                    {character.is_public && (
                      <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded">
                        Public
                      </span>
                    )}
                  </div>
                </div>

                <p className="text-white/80 text-sm mb-4 line-clamp-3">
                  {character.description || 'No description provided'}
                </p>

                {character.personality_traits.length > 0 && (
                  <div className="mb-4">
                    <div className="flex flex-wrap gap-1">
                      {character.personality_traits.slice(0, 3).map((trait, index) => (
                        <span
                          key={index}
                          className="px-2 py-1 bg-white/20 text-white/80 text-xs rounded"
                        >
                          {trait}
                        </span>
                      ))}
                      {character.personality_traits.length > 3 && (
                        <span className="px-2 py-1 bg-white/20 text-white/80 text-xs rounded">
                          +{character.personality_traits.length - 3} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                <div className="flex justify-between items-center">
                  <div className="flex gap-2">
                    <Link
                      href={`/characters/${character.id}`}
                      className="px-3 py-2 bg-white/20 text-white text-sm rounded hover:bg-white/30 active:bg-white/40 transition-colors touch-manipulation"
                    >
                      View
                    </Link>
                    <Link
                      href={`/characters/${character.id}/edit`}
                      className="px-3 py-2 bg-blue-500/20 text-blue-300 text-sm rounded hover:bg-blue-500/30 active:bg-blue-500/40 transition-colors touch-manipulation"
                    >
                      Edit
                    </Link>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      promptDeleteCharacter(character.id);
                    }}
                    className="px-4 py-2 bg-red-500/20 text-red-300 text-sm rounded hover:bg-red-500/30 active:bg-red-500/40 transition-colors touch-manipulation min-h-[44px] min-w-[44px]"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmation && (
        <div 
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={cancelDelete}
        >
          <div 
            className="bg-gray-800 rounded-xl p-6 max-w-sm w-full shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-xl font-bold text-white">Confirm Delete</h3>
              <button
                type="button"
                onClick={cancelDelete}
                className="text-white/60 hover:text-white p-1 touch-manipulation"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <p className="text-white/80 mb-6">
              {deleteConfirmation.type === 'single' 
                ? `Are you sure you want to delete "${deleteConfirmation.characterName}"?`
                : `Are you sure you want to delete ${deleteConfirmation.count} character${deleteConfirmation.count! > 1 ? 's' : ''}?`
              }
              <br />
              <span className="text-red-400 text-sm">This action cannot be undone.</span>
            </p>

            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={cancelDelete}
                className="px-4 py-2 bg-white/20 text-white rounded-lg hover:bg-white/30 active:bg-white/40 transition-colors touch-manipulation min-h-[44px]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={isDeleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 active:bg-red-800 transition-colors disabled:opacity-50 touch-manipulation min-h-[44px]"
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
