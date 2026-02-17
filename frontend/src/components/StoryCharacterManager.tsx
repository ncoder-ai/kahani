'use client';

import { useState, useEffect } from 'react';
import { X, Edit, Trash2, User, Image as ImageIcon } from 'lucide-react';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import CharacterForm from './CharacterForm';

interface StoryCharacter {
  id: number;
  character_id: number;
  name: string;
  description: string | null;
  gender?: string | null;
  appearance?: string | null;
  role: string | null;
  portrait_image_id?: number | null;
}

interface StoryCharacterManagerProps {
  storyId: number;
  branchId?: number;
  isOpen: boolean;
  onClose: () => void;
  onCharacterUpdated?: () => void;
}

export default function StoryCharacterManager({
  storyId,
  branchId,
  isOpen,
  onClose,
  onCharacterUpdated
}: StoryCharacterManagerProps) {
  const [characters, setCharacters] = useState<StoryCharacter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingCharacterId, setEditingCharacterId] = useState<number | null>(null);
  const [removingCharacterId, setRemovingCharacterId] = useState<number | null>(null);
  const [apiBaseUrl, setApiBaseUrl] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      loadCharacters();
      // Load API base URL for image URLs
      getApiBaseUrl().then(url => setApiBaseUrl(url));
    }
  }, [isOpen, storyId, branchId]);

  const loadCharacters = async () => {
    try {
      setLoading(true);
      setError(null);

      // If branchId is not provided, fetch the story to get its current_branch_id
      let effectiveBranchId = branchId;
      if (effectiveBranchId === undefined) {
        console.log('[StoryCharacterManager] branchId is undefined, fetching story to get current_branch_id');
        try {
          const story = await apiClient.getStory(storyId);
          effectiveBranchId = story.current_branch_id;
          console.log('[StoryCharacterManager] Got current_branch_id from story:', effectiveBranchId);
        } catch (err) {
          console.warn('[StoryCharacterManager] Failed to get story, proceeding without branch filter');
        }
      }

      console.log('[StoryCharacterManager] Loading characters with storyId:', storyId, 'branchId:', effectiveBranchId);
      const storyCharacters = await apiClient.getStoryCharacters(storyId, effectiveBranchId);
      console.log('[StoryCharacterManager] Loaded characters:', storyCharacters);
      setCharacters(storyCharacters);
    } catch (err: any) {
      console.error('Failed to load story characters:', err);
      setError(err.message || 'Failed to load characters');
    } finally {
      setLoading(false);
    }
  };

  const handleEditCharacter = (characterId: number) => {
    setEditingCharacterId(characterId);
  };

  const handleSaveCharacter = async () => {
    setEditingCharacterId(null);
    await loadCharacters();
    onCharacterUpdated?.();
  };

  const handleRemoveCharacter = async (storyCharacterId: number, characterName: string) => {
    if (!confirm(`Remove "${characterName}" from this story?\n\nThe character will remain in your library but won't be part of this story anymore.`)) {
      return;
    }

    try {
      setRemovingCharacterId(storyCharacterId);
      await apiClient.removeStoryCharacter(storyId, storyCharacterId);
      await loadCharacters();
      onCharacterUpdated?.();
    } catch (err: any) {
      console.error('Failed to remove character:', err);
      alert(err.message || 'Failed to remove character');
    } finally {
      setRemovingCharacterId(null);
    }
  };

  const getPortraitUrl = (portraitImageId: number | null | undefined): string | undefined => {
    if (!portraitImageId) return undefined;
    return `${apiBaseUrl}/api/image-generation/images/${portraitImageId}/file`;
  };

  if (!isOpen) return null;

  // If editing a character, show the CharacterForm
  if (editingCharacterId !== null) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          onClick={() => setEditingCharacterId(null)}
        />
        <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-gray-900 rounded-2xl shadow-2xl">
          <div className="sticky top-0 z-10 flex items-center justify-between p-4 bg-gray-900 border-b border-white/10">
            <h2 className="text-xl font-bold text-white">Edit Character</h2>
            <button
              onClick={() => setEditingCharacterId(null)}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-white/70" />
            </button>
          </div>
          <div className="p-4">
            <CharacterForm
              characterId={editingCharacterId}
              mode="edit"
              storyId={storyId}
              onSave={handleSaveCharacter}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-3xl max-h-[85vh] overflow-hidden bg-gray-900 rounded-2xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div>
            <h2 className="text-xl font-bold text-white">Manage Story Characters</h2>
            <p className="text-sm text-white/60 mt-1">
              Edit character details, generate portraits, and manage story roles
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-white/70" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full" />
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={loadCharacters}
                className="px-4 py-2 bg-white/20 text-white rounded-lg hover:bg-white/30 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : characters.length === 0 ? (
            <div className="text-center py-12">
              <User className="w-12 h-12 text-white/30 mx-auto mb-4" />
              <p className="text-white/60 mb-2">No characters in this story yet</p>
              <p className="text-white/40 text-sm">
                Add characters from the menu to get started
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {characters.map((character) => (
                <div
                  key={character.id}
                  className="p-4 bg-white/5 rounded-xl border border-white/10 hover:border-white/20 transition-colors"
                >
                  <div className="flex items-start gap-4">
                    {/* Portrait */}
                    <div className="w-14 h-14 flex-shrink-0 rounded-lg overflow-hidden bg-white/10">
                      {character.portrait_image_id ? (
                        <img
                          src={getPortraitUrl(character.portrait_image_id)}
                          alt={character.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <User className="w-6 h-6 text-white/30" />
                        </div>
                      )}
                    </div>

                    {/* Character Info */}
                    <div className="flex-1 min-w-0">
                      {/* Name - always visible */}
                      <h3 className="text-lg font-semibold text-white mb-1">{character.name}</h3>

                      {/* Role, gender, and portrait badges */}
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        {character.role && (
                          <span className="px-2 py-0.5 text-xs bg-purple-500/20 text-purple-300 rounded-full">
                            {character.role}
                          </span>
                        )}
                        {character.gender && (
                          <span className="px-2 py-0.5 text-xs bg-blue-500/20 text-blue-300 rounded-full">
                            {character.gender}
                          </span>
                        )}
                        {!character.portrait_image_id && (
                          <span className="px-2 py-0.5 text-xs bg-amber-500/20 text-amber-300 rounded-full flex items-center gap-1">
                            <ImageIcon className="w-3 h-3" />
                            No portrait
                          </span>
                        )}
                      </div>

                      {/* Description */}
                      <p className="text-sm text-white/60 line-clamp-2">
                        {character.appearance || character.description || 'No description'}
                      </p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={() => handleEditCharacter(character.character_id)}
                        className="p-2 bg-blue-500/20 text-blue-300 rounded-lg hover:bg-blue-500/30 transition-colors"
                        title="Edit character"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleRemoveCharacter(character.id, character.name)}
                        disabled={removingCharacterId === character.id}
                        className="p-2 bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30 transition-colors disabled:opacity-50"
                        title="Remove from story"
                      >
                        {removingCharacterId === character.id ? (
                          <div className="w-4 h-4 border-2 border-red-300/30 border-t-red-300 rounded-full animate-spin" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 bg-gray-900/50">
          <p className="text-xs text-white/40 text-center">
            Click "Edit" to modify character details including appearance, background, and portrait generation
          </p>
        </div>
      </div>
    </div>
  );
}
