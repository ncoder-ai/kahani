'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import apiClient from '@/lib/api';
import Link from 'next/link';

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
  updated_at?: string | null;
}

export default function CharacterDetailPage() {
  const params = useParams();
  const characterId = parseInt(params.id as string);

  return <CharacterDetailContent key={characterId} characterId={characterId} />;
}

function CharacterDetailContent({ characterId }: { characterId: number }) {
  const router = useRouter();

  const [character, setCharacter] = useState<Character | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (characterId) {
      loadCharacter();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // characterId changes via remount (key prop on parent)

  const loadCharacter = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getCharacter(characterId);
      setCharacter(data);
    } catch (error) {
      console.error('Failed to load character:', error);
      router.push('/characters');
    } finally {
      setLoading(false);
    }
  };

  const deleteCharacter = async () => {
    if (!character || !window.confirm(`Are you sure you want to delete "${character.name}"?`)) {
      return;
    }

    try {
      await apiClient.deleteCharacter(character.id);
      router.push('/characters');
    } catch (error) {
      console.error('Failed to delete character:', error);
      alert('Failed to delete character');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="theme-text-primary text-xl">Loading character...</div>
      </div>
    );
  }

  if (!character) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="theme-text-primary text-xl mb-4">Character not found</div>
          <Link
            href="/characters"
            className="px-6 py-3 theme-btn-primary rounded-xl transition-colors"
          >
            Back to Characters
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen theme-bg-primary p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-4">
            <Link
              href="/dashboard"
              className="text-white/60 hover:text-white transition-colors flex items-center gap-2"
            >
              ← Dashboard
            </Link>
            <span className="text-white/40">•</span>
            <Link
              href="/characters"
              className="text-white/60 hover:text-white transition-colors flex items-center gap-2"
            >
              Character Library
            </Link>
          </div>
          
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-4xl font-bold text-white mb-2">{character.name}</h1>
              <div className="flex gap-2 mb-4">
                {character.gender && (
                  <span className="px-3 py-1 bg-indigo-500/20 text-indigo-300 text-sm rounded-full capitalize">
                    {character.gender}
                  </span>
                )}
                {character.is_template && (
                  <span className="px-3 py-1 bg-blue-500/20 text-blue-300 text-sm rounded-full">
                    Template
                  </span>
                )}
                {character.is_public && (
                  <span className="px-3 py-1 bg-green-500/20 text-green-300 text-sm rounded-full">
                    Public
                  </span>
                )}
              </div>
            </div>
            
            <div className="flex gap-3">
              <Link
                href={`/characters/${character.id}/edit`}
                className="px-4 py-2 bg-blue-500/20 text-blue-300 rounded-lg hover:bg-blue-500/30 transition-colors"
              >
                Edit
              </Link>
              <button
                onClick={deleteCharacter}
                className="px-4 py-2 bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>

        {/* Character Details */}
        <div className="space-y-8">
          {/* Description */}
          <div className="bg-white/10 rounded-xl p-6">
            <h2 className="text-2xl font-semibold text-white mb-4">Description</h2>
            <p className="text-white/80 text-lg leading-relaxed">
              {character.description || 'No description provided.'}
            </p>
          </div>

          {/* Personality Traits */}
          {character.personality_traits.length > 0 && (
            <div className="bg-white/10 rounded-xl p-6">
              <h2 className="text-2xl font-semibold text-white mb-4">Personality Traits</h2>
              <div className="flex flex-wrap gap-2">
                {character.personality_traits.map((trait, index) => (
                  <span
                    key={index}
                    className="px-4 py-2 rounded-full font-medium"
                    style={{ backgroundColor: 'var(--color-accentPrimary)', opacity: 0.2, color: 'var(--color-accentPrimary)' } as React.CSSProperties}
                  >
                    {trait}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Background */}
            {character.background && (
              <div className="bg-white/10 rounded-xl p-6">
                <h2 className="text-xl font-semibold text-white mb-3">Background</h2>
                <p className="text-white/80 leading-relaxed">{character.background}</p>
              </div>
            )}

            {/* Goals */}
            {character.goals && (
              <div className="bg-white/10 rounded-xl p-6">
                <h2 className="text-xl font-semibold text-white mb-3">Goals & Motivations</h2>
                <p className="text-white/80 leading-relaxed">{character.goals}</p>
              </div>
            )}

            {/* Fears */}
            {character.fears && (
              <div className="bg-white/10 rounded-xl p-6">
                <h2 className="text-xl font-semibold text-white mb-3">Fears & Weaknesses</h2>
                <p className="text-white/80 leading-relaxed">{character.fears}</p>
              </div>
            )}

            {/* Appearance */}
            {character.appearance && (
              <div className="bg-white/10 rounded-xl p-6">
                <h2 className="text-xl font-semibold text-white mb-3">Appearance</h2>
                <p className="text-white/80 leading-relaxed">{character.appearance}</p>
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className="bg-white/5 rounded-xl p-6">
            <h2 className="text-xl font-semibold text-white mb-3">Character Info</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-white/60">Created:</span>
                <span className="text-white ml-2">
                  {new Date(character.created_at).toLocaleDateString()}
                </span>
              </div>
              {character.updated_at && (
                <div>
                  <span className="text-white/60">Last Updated:</span>
                  <span className="text-white ml-2">
                    {new Date(character.updated_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}