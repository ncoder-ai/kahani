'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';
import Link from 'next/link';

interface Character {
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

export default function CharacterLibrary() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'mine' | 'public'>('all');
  const [templatesOnly, setTemplatesOnly] = useState(false);

  useEffect(() => {
    loadCharacters();
  }, [filter, templatesOnly]);

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
    } catch (error) {
      console.error('Failed to load characters:', error);
    } finally {
      setLoading(false);
    }
  };

  const deleteCharacter = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this character?')) {
      return;
    }

    try {
      await apiClient.deleteCharacter(id);
      setCharacters(characters.filter(char => char.id !== id));
    } catch (error) {
      console.error('Failed to delete character:', error);
      alert('Failed to delete character');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center pt-16">
        <div className="text-white text-xl">Loading characters...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 p-6 pt-16">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-bold text-white mb-2">Character Library</h1>
            <p className="text-white/80">Manage your characters across all stories</p>
          </div>
          <Link
            href="/characters/create"
            className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:from-purple-600 hover:to-pink-600 transition-colors font-semibold"
          >
            + Create Character
          </Link>
        </div>

        {/* Filters */}
        <div className="bg-white/10 rounded-xl p-6 mb-8">
          <div className="flex flex-wrap gap-4 items-center">
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  filter === 'all'
                    ? 'bg-purple-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30'
                }`}
              >
                All Characters
              </button>
              <button
                onClick={() => setFilter('mine')}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  filter === 'mine'
                    ? 'bg-purple-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30'
                }`}
              >
                My Characters
              </button>
              <button
                onClick={() => setFilter('public')}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  filter === 'public'
                    ? 'bg-purple-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30'
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
        </div>

        {/* Characters Grid */}
        {characters.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-white/60 text-lg mb-4">No characters found</div>
            <Link
              href="/characters/create"
              className="inline-flex px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:from-purple-600 hover:to-pink-600 transition-colors font-semibold"
            >
              Create Your First Character
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {characters.map((character) => (
              <div key={character.id} className="bg-white/10 rounded-xl p-6 hover:bg-white/15 transition-colors">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-xl font-bold text-white">{character.name}</h3>
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
                          className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded"
                        >
                          {trait}
                        </span>
                      ))}
                      {character.personality_traits.length > 3 && (
                        <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded">
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
                      className="px-3 py-1 bg-white/20 text-white text-sm rounded hover:bg-white/30 transition-colors"
                    >
                      View
                    </Link>
                    <Link
                      href={`/characters/${character.id}/edit`}
                      className="px-3 py-1 bg-blue-500/20 text-blue-300 text-sm rounded hover:bg-blue-500/30 transition-colors"
                    >
                      Edit
                    </Link>
                  </div>
                  <button
                    onClick={() => deleteCharacter(character.id)}
                    className="px-3 py-1 bg-red-500/20 text-red-300 text-sm rounded hover:bg-red-500/30 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}