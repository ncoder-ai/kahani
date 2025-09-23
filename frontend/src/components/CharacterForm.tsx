'use client';

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface CharacterFormProps {
  characterId?: number;
  onSave?: (character: any) => void;
  mode?: 'create' | 'edit' | 'inline';
}

export default function CharacterForm({ characterId, onSave, mode = 'create' }: CharacterFormProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    personality_traits: [] as string[],
    background: '',
    goals: '',
    fears: '',
    appearance: '',
    is_template: true,
    is_public: false
  });

  const [newTrait, setNewTrait] = useState('');

  useEffect(() => {
    if (characterId && mode === 'edit') {
      loadCharacter();
    }
  }, [characterId, mode]);

  const loadCharacter = async () => {
    if (!characterId) return;
    
    try {
      setLoading(true);
      const character = await apiClient.getCharacter(characterId);
      setFormData({
        name: character.name,
        description: character.description,
        personality_traits: character.personality_traits,
        background: character.background,
        goals: character.goals,
        fears: character.fears,
        appearance: character.appearance,
        is_template: character.is_template,
        is_public: character.is_public
      });
    } catch (error) {
      console.error('Failed to load character:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const addPersonalityTrait = () => {
    if (newTrait.trim() && !formData.personality_traits.includes(newTrait.trim())) {
      setFormData(prev => ({
        ...prev,
        personality_traits: [...prev.personality_traits, newTrait.trim()]
      }));
      setNewTrait('');
    }
  };

  const removePersonalityTrait = (index: number) => {
    setFormData(prev => ({
      ...prev,
      personality_traits: prev.personality_traits.filter((_, i) => i !== index)
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      alert('Character name is required');
      return;
    }

    try {
      setSaving(true);
      let character;
      
      if (mode === 'edit' && characterId) {
        character = await apiClient.updateCharacter(characterId, formData);
      } else {
        character = await apiClient.createCharacter(formData);
      }

      if (onSave) {
        onSave(character);
      } else {
        router.push('/characters');
      }
    } catch (error) {
      console.error('Failed to save character:', error);
      alert('Failed to save character');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (mode === 'inline' && onSave) {
      onSave(null);
    } else {
      router.back();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-white">Loading character...</div>
      </div>
    );
  }

  return (
    <div className={mode === 'inline' ? 'space-y-6' : 'min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 p-6'}>
      <div className={mode === 'inline' ? '' : 'max-w-2xl mx-auto'}>
        {mode !== 'inline' && (
          <div className="text-center mb-8">
            <div className="flex items-center justify-center gap-4 mb-4">
              <button
                onClick={() => router.push('/dashboard')}
                className="text-white/60 hover:text-white transition-colors flex items-center gap-2"
              >
                ← Dashboard
              </button>
              <span className="text-white/40">•</span>
              <button
                onClick={() => router.push('/characters')}
                className="text-white/60 hover:text-white transition-colors flex items-center gap-2"
              >
                Character Library
              </button>
            </div>
            <h1 className="text-4xl font-bold text-white mb-2">
              {mode === 'edit' ? 'Edit Character' : 'Create Character'}
            </h1>
            <p className="text-white/80">
              {mode === 'edit' ? 'Update your character details' : 'Bring your character to life'}
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-white/10 rounded-xl p-8 space-y-6">
          {/* Basic Info */}
          <div className="space-y-4">
            <h3 className="text-xl font-semibold text-white">Basic Information</h3>
            
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Character Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => handleInputChange('name', e.target.value)}
                placeholder="Enter character name..."
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Description
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => handleInputChange('description', e.target.value)}
                placeholder="Brief description of your character..."
                rows={3}
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          {/* Personality Traits */}
          <div className="space-y-4">
            <h3 className="text-xl font-semibold text-white">Personality</h3>
            
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Personality Traits
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newTrait}
                  onChange={(e) => setNewTrait(e.target.value)}
                  placeholder="Add a personality trait..."
                  className="flex-1 p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addPersonalityTrait())}
                />
                <button
                  type="button"
                  onClick={addPersonalityTrait}
                  className="px-4 py-3 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors"
                >
                  Add
                </button>
              </div>
              
              {formData.personality_traits.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {formData.personality_traits.map((trait, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 px-3 py-1 bg-purple-500/20 text-purple-300 rounded-full text-sm"
                    >
                      {trait}
                      <button
                        type="button"
                        onClick={() => removePersonalityTrait(index)}
                        className="ml-1 text-purple-300 hover:text-white"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Detailed Character Info */}
          <div className="space-y-4">
            <h3 className="text-xl font-semibold text-white">Character Details</h3>
            
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Background
              </label>
              <textarea
                value={formData.background}
                onChange={(e) => handleInputChange('background', e.target.value)}
                placeholder="Character's history and background..."
                rows={3}
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Goals & Motivations
              </label>
              <textarea
                value={formData.goals}
                onChange={(e) => handleInputChange('goals', e.target.value)}
                placeholder="What does this character want to achieve?"
                rows={2}
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Fears & Weaknesses
              </label>
              <textarea
                value={formData.fears}
                onChange={(e) => handleInputChange('fears', e.target.value)}
                placeholder="What does this character fear or struggle with?"
                rows={2}
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Appearance
              </label>
              <textarea
                value={formData.appearance}
                onChange={(e) => handleInputChange('appearance', e.target.value)}
                placeholder="Describe how this character looks..."
                rows={2}
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          {/* Settings */}
          <div className="space-y-4">
            <h3 className="text-xl font-semibold text-white">Character Settings</h3>
            
            <div className="space-y-3">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={formData.is_template}
                  onChange={(e) => handleInputChange('is_template', e.target.checked)}
                  className="rounded"
                />
                <span className="text-white">
                  Make this a template character (can be reused in multiple stories)
                </span>
              </label>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={formData.is_public}
                  onChange={(e) => handleInputChange('is_public', e.target.checked)}
                  className="rounded"
                />
                <span className="text-white">
                  Make this character public (other users can use it)
                </span>
              </label>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-between pt-6">
            <button
              type="button"
              onClick={handleCancel}
              className="px-6 py-3 bg-white/20 text-white rounded-xl hover:bg-white/30 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-8 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:from-purple-600 hover:to-pink-600 transition-colors font-semibold disabled:opacity-50"
            >
              {saving ? 'Saving...' : (mode === 'edit' ? 'Update Character' : 'Create Character')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}