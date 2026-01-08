'use client';

import { useState, useEffect } from 'react';
import apiClient, { VoiceStyle, VoiceStylePreset, VoiceStylePresetsResponse } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface CharacterFormProps {
  characterId?: number;
  onSave?: (character: any) => void;
  mode?: 'create' | 'edit' | 'inline';
  storyContext?: { genre?: string; tone?: string; world_setting?: string };
  initialData?: {
    name?: string;
    description?: string;
    personality_traits?: string[];
    background?: string;
    goals?: string;
    fears?: string;
    appearance?: string;
    is_template?: boolean;
    is_public?: boolean;
    voice_style?: VoiceStyle | null;
  };
  storyCharacterRole?: string; // For linking to story after creation
  storyId?: number; // For linking to story after creation
}

export default function CharacterForm({ characterId, onSave, mode = 'create', storyContext, initialData, storyCharacterRole, storyId }: CharacterFormProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creationMode, setCreationMode] = useState<'manual' | 'ai-assisted'>('manual');
  const [aiPrompt, setAiPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generatedCharacter, setGeneratedCharacter] = useState<any>(null);
  const [previousGeneration, setPreviousGeneration] = useState<any>(null);
  
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    personality_traits: [] as string[],
    background: '',
    goals: '',
    fears: '',
    appearance: '',
    is_template: true,
    is_public: false,
    voice_style: null as VoiceStyle | null
  });

  const [newTrait, setNewTrait] = useState('');
  const [selectedRole, setSelectedRole] = useState<string>('');
  
  // Voice style state
  const [voicePresets, setVoicePresets] = useState<VoiceStylePresetsResponse | null>(null);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const [showVoiceCustomization, setShowVoiceCustomization] = useState(false);

  // Character roles for story linking
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

  // Load voice style presets on mount
  useEffect(() => {
    const loadVoicePresets = async () => {
      try {
        setLoadingPresets(true);
        const presets = await apiClient.getVoiceStylePresets();
        setVoicePresets(presets);
      } catch (error) {
        console.error('Failed to load voice style presets:', error);
      } finally {
        setLoadingPresets(false);
      }
    };
    loadVoicePresets();
  }, []);

  useEffect(() => {
    if (characterId && mode === 'edit') {
      loadCharacter();
    } else if (initialData) {
      // Pre-fill form with initial data (e.g., from Discover from Story)
      setFormData({
        name: initialData.name || '',
        description: initialData.description || '',
        personality_traits: initialData.personality_traits || [],
        background: initialData.background || '',
        goals: initialData.goals || '',
        fears: initialData.fears || '',
        appearance: initialData.appearance || '',
        is_template: initialData.is_template ?? true,
        is_public: initialData.is_public ?? false,
        voice_style: initialData.voice_style || null
      });
      // Set as generated character so it shows in AI-assisted preview mode
      setGeneratedCharacter({
        name: initialData.name || '',
        description: initialData.description || '',
        personality_traits: initialData.personality_traits || [],
        background: initialData.background || '',
        goals: initialData.goals || '',
        fears: initialData.fears || '',
        appearance: initialData.appearance || '',
        is_template: initialData.is_template ?? true,
        is_public: initialData.is_public ?? false,
        voice_style: initialData.voice_style || null
      });
      setCreationMode('ai-assisted');
    }
  }, [characterId, mode, initialData]);

  // Set initial role from prop or initialData
  useEffect(() => {
    if (storyCharacterRole) {
      setSelectedRole(storyCharacterRole);
    }
  }, [storyCharacterRole]);

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
        is_public: character.is_public,
        voice_style: character.voice_style || null
      });
      // If character has custom voice style, show customization
      if (character.voice_style?.preset === 'custom') {
        setShowVoiceCustomization(true);
      }
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

  const handleGenerateWithAI = async () => {
    if (!aiPrompt.trim()) {
      alert('Please enter a character description');
      return;
    }

    try {
      setGenerating(true);
      const character = await apiClient.generateCharacterWithAI(aiPrompt, storyContext);
      setPreviousGeneration(generatedCharacter);
      setGeneratedCharacter(character);
    } catch (error) {
      console.error('Failed to generate character:', error);
      alert('Failed to generate character. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  const handleRegenerate = async () => {
    if (!aiPrompt.trim()) {
      return;
    }

    try {
      setGenerating(true);
      const character = await apiClient.generateCharacterWithAI(aiPrompt, storyContext, generatedCharacter);
      setPreviousGeneration(generatedCharacter);
      setGeneratedCharacter(character);
    } catch (error) {
      console.error('Failed to regenerate character:', error);
      alert('Failed to regenerate character. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  const handleAcceptGenerated = async () => {
    // Accept and save directly
    try {
      setSaving(true);
      let character;
      
      // If storyId and role are provided, use createCharacterFromSuggestion to link to story
      if (storyId && (selectedRole || storyCharacterRole) && generatedCharacter) {
        const roleToUse = selectedRole || storyCharacterRole || 'other';
        character = await apiClient.createCharacterFromSuggestion(
          storyId,
          generatedCharacter.name,
          {
            name: generatedCharacter.name,
            description: generatedCharacter.description,
            personality_traits: generatedCharacter.personality_traits,
            background: generatedCharacter.background,
            goals: generatedCharacter.goals,
            fears: generatedCharacter.fears,
            appearance: generatedCharacter.appearance,
            role: roleToUse
          }
        );
      } else {
        // Regular character creation
        character = await apiClient.createCharacter({
          name: generatedCharacter.name,
          description: generatedCharacter.description,
          personality_traits: generatedCharacter.personality_traits,
          background: generatedCharacter.background,
          goals: generatedCharacter.goals,
          fears: generatedCharacter.fears,
          appearance: generatedCharacter.appearance,
          is_template: generatedCharacter.is_template,
          is_public: generatedCharacter.is_public,
          voice_style: formData.voice_style  // Include voice style from form
        });
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

  const handleEditManually = () => {
    // Populate form with generated data and switch to manual mode
    if (generatedCharacter) {
      setFormData({
        name: generatedCharacter.name,
        description: generatedCharacter.description,
        personality_traits: generatedCharacter.personality_traits || [],
        background: generatedCharacter.background,
        goals: generatedCharacter.goals,
        fears: generatedCharacter.fears,
        appearance: generatedCharacter.appearance,
        is_template: generatedCharacter.is_template ?? true,
        is_public: generatedCharacter.is_public ?? false,
        voice_style: generatedCharacter.voice_style || formData.voice_style || null
      });
    }
    setCreationMode('manual');
    setGeneratedCharacter(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      alert('Character name is required');
      return;
    }

    // Validate role selection when linking to story
    if (storyId && !selectedRole && !storyCharacterRole) {
      alert('Please select a character role for this story');
      return;
    }

    try {
      setSaving(true);
      let character;
      
      // If storyId and role are provided, use createCharacterFromSuggestion to link to story
      if (storyId && (selectedRole || storyCharacterRole) && mode !== 'edit') {
        const roleToUse = selectedRole || storyCharacterRole || 'other';
        character = await apiClient.createCharacterFromSuggestion(
          storyId,
          formData.name,
          {
            name: formData.name,
            description: formData.description,
            personality_traits: formData.personality_traits,
            background: formData.background,
            goals: formData.goals,
            fears: formData.fears,
            appearance: formData.appearance,
            role: roleToUse
          }
        );
      } else if (mode === 'edit' && characterId) {
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
    <div className={mode === 'inline' ? 'space-y-6' : 'min-h-screen theme-bg-primary p-6'}>
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

        {/* Mode Toggle - Show in create and inline modes */}
        {(mode === 'create' || mode === 'inline') && (
          <div className="mb-6">
            <div className="bg-white/10 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-white">Creation Mode</label>
                <button
                  type="button"
                  onClick={() => {
                    setCreationMode(creationMode === 'manual' ? 'ai-assisted' : 'manual');
                    setGeneratedCharacter(null);
                    setAiPrompt('');
                  }}
                  className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-800 focus:ring-white"
                  style={{
                    backgroundColor: creationMode === 'ai-assisted' ? 'var(--color-accentPrimary)' : 'rgba(255, 255, 255, 0.2)'
                  }}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      creationMode === 'ai-assisted' ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
              <p className="text-xs text-white/60">
                {creationMode === 'manual' ? 'Manual creation' : 'AI-assisted generation'}
              </p>
            </div>
          </div>
        )}

        {/* AI-Assisted Mode */}
        {(mode === 'create' || mode === 'inline') && creationMode === 'ai-assisted' && (
          <div className="bg-white/10 rounded-xl p-8 space-y-6 mb-6">
            {!generatedCharacter ? (
              <>
                <div>
                  <h3 className="text-xl font-semibold text-white mb-4">Describe Your Character</h3>
                  <p className="text-white/80 text-sm mb-4">
                    Describe your character in natural language. Include details about their role, personality, appearance, or any other aspects you want.
                  </p>
                  <textarea
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                    placeholder="e.g., A mysterious detective in their 40s, haunted by a past case. They're methodical but have a dark sense of humor..."
                    rows={6}
                    className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleGenerateWithAI}
                  disabled={generating || !aiPrompt.trim()}
                  className="w-full px-6 py-3 theme-btn-primary rounded-xl transition-colors font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {generating ? 'Generating...' : 'Generate Character'}
                </button>
              </>
            ) : (
              <>
                {/* Generated Character Preview - Matches Manual Form Structure */}
                <div className="bg-white/5 rounded-lg p-6 space-y-6">
                  <h3 className="text-xl font-semibold text-white mb-4">Generated Character Preview</h3>
                  
                  {/* Basic Info */}
                  <div className="space-y-4">
                    <h4 className="text-lg font-semibold text-white">Basic Information</h4>
                    
                    <div>
                      <label className="block text-sm font-medium text-white/60 mb-1">Character Name *</label>
                      <p className="text-white">{generatedCharacter.name}</p>
                    </div>
                    
                    {generatedCharacter.description && (
                      <div>
                        <label className="block text-sm font-medium text-white/60 mb-1">Description</label>
                        <p className="text-white">{generatedCharacter.description}</p>
                      </div>
                    )}
                  </div>

                  {/* Personality Traits - Always show if traits exist */}
                  {(() => {
                    const traits = generatedCharacter.personality_traits;
                    const hasTraits = traits && Array.isArray(traits) && traits.length > 0;
                    return hasTraits ? (
                      <div className="space-y-4">
                        <h4 className="text-lg font-semibold text-white">Personality</h4>
                        <div>
                          <label className="block text-sm font-medium text-white/60 mb-2">Personality Traits</label>
                          <div className="flex flex-wrap gap-2">
                            {traits.map((trait: string, index: number) => {
                              if (!trait || !trait.trim()) return null;
                              return (
                                <span
                                  key={index}
                                  className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-white/20 text-white"
                                >
                                  {trait}
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    ) : (
                      // Debug: Show when traits are missing
                      traits && (
                        <div className="space-y-4">
                          <h4 className="text-lg font-semibold text-white">Personality</h4>
                          <div>
                            <label className="block text-sm font-medium text-white/60 mb-2">Personality Traits</label>
                            <p className="text-white text-xs">Debug: traits = {JSON.stringify(traits)}</p>
                          </div>
                        </div>
                      )
                    );
                  })()}

                  {/* Character Details */}
                  <div className="space-y-4">
                    <h4 className="text-lg font-semibold text-white">Character Details</h4>
                    
                    {(generatedCharacter.background_structured || generatedCharacter.background) && (
                      <div>
                        <label className="block text-sm font-medium text-white/60 mb-2">Background</label>
                        {generatedCharacter.background_structured ? (
                          <ul className="space-y-1">
                            {Object.entries(generatedCharacter.background_structured)
                              .filter(([, value]) => value)
                              .map(([key, value]) => (
                                <li key={key} className="text-white text-sm">
                                  <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span> {String(value)}
                                </li>
                              ))}
                          </ul>
                        ) : (
                          <p className="text-white text-sm whitespace-pre-wrap">{generatedCharacter.background}</p>
                        )}
                      </div>
                    )}

                    {(generatedCharacter.goals_structured || generatedCharacter.goals) && (
                      <div>
                        <label className="block text-sm font-medium text-white/60 mb-2">Goals & Motivations</label>
                        {generatedCharacter.goals_structured ? (
                          <ul className="space-y-1">
                            {Object.entries(generatedCharacter.goals_structured)
                              .filter(([, value]) => value)
                              .map(([key, value]) => (
                                <li key={key} className="text-white text-sm">
                                  <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span> {String(value)}
                                </li>
                              ))}
                          </ul>
                        ) : (
                          <p className="text-white text-sm whitespace-pre-wrap">{generatedCharacter.goals}</p>
                        )}
                      </div>
                    )}

                    {(generatedCharacter.fears_structured || generatedCharacter.fears) && (
                      <div>
                        <label className="block text-sm font-medium text-white/60 mb-2">Fears & Weaknesses</label>
                        {generatedCharacter.fears_structured ? (
                          <ul className="space-y-1">
                            {Object.entries(generatedCharacter.fears_structured)
                              .filter(([, value]) => value)
                              .map(([key, value]) => (
                                <li key={key} className="text-white text-sm">
                                  <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span> {String(value)}
                                </li>
                              ))}
                          </ul>
                        ) : (
                          <p className="text-white text-sm whitespace-pre-wrap">{generatedCharacter.fears}</p>
                        )}
                      </div>
                    )}

                    {(generatedCharacter.appearance_structured || generatedCharacter.appearance) && (
                      <div>
                        <label className="block text-sm font-medium text-white/60 mb-2">Appearance</label>
                        {generatedCharacter.appearance_structured ? (
                          <ul className="space-y-1">
                            {Object.entries(generatedCharacter.appearance_structured)
                              .filter(([, value]) => value)
                              .map(([key, value]) => (
                                <li key={key} className="text-white text-sm">
                                  <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span> {String(value)}
                                </li>
                              ))}
                          </ul>
                        ) : (
                          <p className="text-white text-sm whitespace-pre-wrap">{generatedCharacter.appearance}</p>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Character Settings */}
                  <div className="space-y-4">
                    <h4 className="text-lg font-semibold text-white">Character Settings</h4>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm ${generatedCharacter.is_template ? 'text-white' : 'text-white/60'}`}>
                          ✓ Template character (can be reused in multiple stories)
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-sm ${generatedCharacter.is_public ? 'text-white' : 'text-white/60'}`}>
                          {generatedCharacter.is_public ? '✓' : '○'} Public character (other users can use it)
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Story Character Role Selection */}
                  {storyId && (
                    <div className="space-y-4">
                      <h4 className="text-lg font-semibold text-white">Character Role in Story</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {CHARACTER_ROLES.map((role) => {
                          const isSelected = selectedRole === role.id;
                          return (
                            <button
                              key={role.id}
                              type="button"
                              onClick={() => setSelectedRole(role.id)}
                              className={`p-3 rounded-lg border-2 transition-all ${
                                isSelected
                                  ? 'border-2'
                                  : 'border-white/20 hover:border-white/40'
                              }`}
                              style={isSelected ? {
                                borderColor: 'var(--color-accentPrimary)',
                                backgroundColor: 'var(--color-accentPrimary)',
                                opacity: 0.2
                              } as React.CSSProperties : {}}
                            >
                              <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${role.color} flex items-center justify-center text-white text-lg mb-2 mx-auto`}>
                                {role.icon}
                              </div>
                              <div className="text-white text-sm font-medium">{role.name}</div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    type="button"
                    onClick={handleAcceptGenerated}
                    disabled={saving || !!(storyId && !selectedRole && !storyCharacterRole)}
                    className="flex-1 px-6 py-3 theme-btn-primary rounded-xl transition-colors font-semibold disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : 'Accept & Save'}
                  </button>
                  <button
                    type="button"
                    onClick={handleRegenerate}
                    disabled={generating}
                    className="flex-1 px-6 py-3 bg-white/20 text-white rounded-xl hover:bg-white/30 transition-colors font-semibold disabled:opacity-50"
                  >
                    {generating ? 'Regenerating...' : 'Regenerate'}
                  </button>
                  <button
                    type="button"
                    onClick={handleEditManually}
                    className="flex-1 px-6 py-3 bg-white/20 text-white rounded-xl hover:bg-white/30 transition-colors font-semibold"
                  >
                    Edit Manually
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Manual Mode Form */}
        {(mode === 'edit' || creationMode === 'manual') && (
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
                  className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
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
                  className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
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
                    className="flex-1 p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
                    onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addPersonalityTrait())}
                  />
                  <button
                    type="button"
                    onClick={addPersonalityTrait}
                    className="px-4 py-3 theme-btn-primary rounded-lg transition-colors"
                  >
                    Add
                  </button>
                </div>
                
                {formData.personality_traits.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {formData.personality_traits.map((trait, index) => (
                      <span
                        key={index}
                        className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-white/20 text-white"
                      >
                        {trait}
                        <button
                          type="button"
                          onClick={() => removePersonalityTrait(index)}
                          className="ml-1 hover:text-white text-white/80"
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
                  className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
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
                  className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
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
                  className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
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
                  className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
                />
              </div>
            </div>

            {/* Voice & Speech Style */}
            <div className="space-y-4">
              <h3 className="text-xl font-semibold text-white">Voice & Speech Style</h3>
              <p className="text-white/60 text-sm">
                Define how this character speaks - their accent, tone, and speech patterns
              </p>
              
              {loadingPresets ? (
                <div className="text-white/60">Loading voice style options...</div>
              ) : voicePresets ? (
                <div className="space-y-4">
                  {/* Preset Selection */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Voice Style Preset
                    </label>
                    <select
                      value={formData.voice_style?.preset || ''}
                      onChange={(e) => {
                        const presetId = e.target.value;
                        if (!presetId) {
                          handleInputChange('voice_style', null);
                          setShowVoiceCustomization(false);
                        } else if (presetId === 'custom') {
                          handleInputChange('voice_style', { 
                            preset: 'custom',
                            formality: 'casual',
                            vocabulary: 'average',
                            tone: 'calm',
                            profanity: 'none',
                            language_mixing: 'none'
                          });
                          setShowVoiceCustomization(true);
                        } else {
                          handleInputChange('voice_style', { preset: presetId });
                          setShowVoiceCustomization(false);
                        }
                      }}
                      className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white focus:outline-none theme-focus-ring"
                    >
                      <option value="">Standard (no special voice)</option>
                      <optgroup label="Regional Dialects">
                        {Object.entries(voicePresets.presets)
                          .filter(([_, p]) => p.category === 'regional')
                          .map(([id, preset]) => (
                            <option key={id} value={id}>{preset.name}</option>
                          ))}
                      </optgroup>
                      <optgroup label="Character Types">
                        {Object.entries(voicePresets.presets)
                          .filter(([_, p]) => p.category === 'archetype')
                          .map(([id, preset]) => (
                            <option key={id} value={id}>{preset.name}</option>
                          ))}
                      </optgroup>
                      <optgroup label="Fantasy/Genre">
                        {Object.entries(voicePresets.presets)
                          .filter(([_, p]) => p.category === 'fantasy')
                          .map(([id, preset]) => (
                            <option key={id} value={id}>{preset.name}</option>
                          ))}
                      </optgroup>
                      <optgroup label="Other">
                        {Object.entries(voicePresets.presets)
                          .filter(([_, p]) => p.category === 'neutral' || !['regional', 'archetype', 'fantasy'].includes(p.category))
                          .map(([id, preset]) => (
                            <option key={id} value={id}>{preset.name}</option>
                          ))}
                        <option value="custom">Custom (define your own)</option>
                      </optgroup>
                    </select>
                  </div>

                  {/* Preset Preview */}
                  {formData.voice_style?.preset && formData.voice_style.preset !== 'custom' && voicePresets.presets[formData.voice_style.preset] && (
                    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <p className="text-white/60 text-sm mb-2">{voicePresets.presets[formData.voice_style.preset].description}</p>
                      <p className="text-white/80 text-sm italic">"{voicePresets.presets[formData.voice_style.preset].example}"</p>
                    </div>
                  )}

                  {/* Custom Voice Style Options */}
                  {showVoiceCustomization && (
                    <div className="space-y-4 bg-white/5 rounded-lg p-4 border border-white/10">
                      <div className="grid grid-cols-2 gap-4">
                        {/* Formality */}
                        <div>
                          <label className="block text-sm font-medium text-white/80 mb-1">Formality</label>
                          <select
                            value={formData.voice_style?.formality || 'casual'}
                            onChange={(e) => handleInputChange('voice_style', { ...formData.voice_style, formality: e.target.value })}
                            className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm"
                          >
                            {voicePresets.attributes.formality?.map(attr => (
                              <option key={attr.id} value={attr.id}>{attr.name}</option>
                            ))}
                          </select>
                        </div>

                        {/* Vocabulary */}
                        <div>
                          <label className="block text-sm font-medium text-white/80 mb-1">Vocabulary</label>
                          <select
                            value={formData.voice_style?.vocabulary || 'average'}
                            onChange={(e) => handleInputChange('voice_style', { ...formData.voice_style, vocabulary: e.target.value })}
                            className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm"
                          >
                            {voicePresets.attributes.vocabulary?.map(attr => (
                              <option key={attr.id} value={attr.id}>{attr.name}</option>
                            ))}
                          </select>
                        </div>

                        {/* Tone */}
                        <div>
                          <label className="block text-sm font-medium text-white/80 mb-1">Tone</label>
                          <select
                            value={formData.voice_style?.tone || 'calm'}
                            onChange={(e) => handleInputChange('voice_style', { ...formData.voice_style, tone: e.target.value })}
                            className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm"
                          >
                            {voicePresets.attributes.tone?.map(attr => (
                              <option key={attr.id} value={attr.id}>{attr.name}</option>
                            ))}
                          </select>
                        </div>

                        {/* Profanity */}
                        <div>
                          <label className="block text-sm font-medium text-white/80 mb-1">Profanity</label>
                          <select
                            value={formData.voice_style?.profanity || 'none'}
                            onChange={(e) => handleInputChange('voice_style', { ...formData.voice_style, profanity: e.target.value })}
                            className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm"
                          >
                            {voicePresets.attributes.profanity?.map(attr => (
                              <option key={attr.id} value={attr.id}>{attr.name}</option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Speech Quirks */}
                      <div>
                        <label className="block text-sm font-medium text-white/80 mb-1">Speech Quirks (optional)</label>
                        <input
                          type="text"
                          value={formData.voice_style?.speech_quirks || ''}
                          onChange={(e) => handleInputChange('voice_style', { ...formData.voice_style, speech_quirks: e.target.value })}
                          placeholder="e.g., Says 'actually' often, ends questions with 'no?'"
                          className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 text-sm"
                        />
                      </div>

                      {/* Language Mixing */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-white/80 mb-1">Secondary Language</label>
                          <select
                            value={formData.voice_style?.secondary_language || ''}
                            onChange={(e) => handleInputChange('voice_style', { 
                              ...formData.voice_style, 
                              secondary_language: e.target.value || undefined,
                              language_mixing: e.target.value ? (formData.voice_style?.language_mixing || 'light') : 'none'
                            })}
                            className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm"
                          >
                            <option value="">None (English only)</option>
                            {voicePresets.attributes.secondary_languages?.map(lang => (
                              <option key={lang.id} value={lang.id}>{lang.name}</option>
                            ))}
                          </select>
                        </div>

                        {formData.voice_style?.secondary_language && (
                          <div>
                            <label className="block text-sm font-medium text-white/80 mb-1">Mixing Frequency</label>
                            <select
                              value={formData.voice_style?.language_mixing || 'light'}
                              onChange={(e) => handleInputChange('voice_style', { ...formData.voice_style, language_mixing: e.target.value })}
                              className="w-full p-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm"
                            >
                              {voicePresets.attributes.language_mixing_level?.map(level => (
                                <option key={level.id} value={level.id}>{level.name} - {level.description}</option>
                              ))}
                            </select>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Toggle Customization Button for Presets */}
                  {formData.voice_style?.preset && formData.voice_style.preset !== 'custom' && (
                    <button
                      type="button"
                      onClick={() => {
                        if (showVoiceCustomization) {
                          // Reset to just preset
                          handleInputChange('voice_style', { preset: formData.voice_style?.preset });
                        }
                        setShowVoiceCustomization(!showVoiceCustomization);
                      }}
                      className="text-sm text-white/60 hover:text-white"
                    >
                      {showVoiceCustomization ? '← Use preset only' : '+ Customize further'}
                    </button>
                  )}
                </div>
              ) : (
                <div className="text-white/40 text-sm">Voice style options not available</div>
              )}
            </div>

            {/* Story Character Role Selection */}
            {storyId && (
              <div className="space-y-4">
                <h3 className="text-xl font-semibold text-white">Character Role in Story</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {CHARACTER_ROLES.map((role) => {
                    const isSelected = selectedRole === role.id;
                    return (
                      <button
                        key={role.id}
                        type="button"
                        onClick={() => setSelectedRole(role.id)}
                        className={`p-3 rounded-lg border-2 transition-all ${
                          isSelected
                            ? 'border-2'
                            : 'border-white/20 hover:border-white/40'
                        }`}
                        style={isSelected ? {
                          borderColor: 'var(--color-accentPrimary)',
                          backgroundColor: 'var(--color-accentPrimary)',
                          opacity: 0.2
                        } as React.CSSProperties : {}}
                      >
                        <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${role.color} flex items-center justify-center text-white text-lg mb-2 mx-auto`}>
                          {role.icon}
                        </div>
                        <div className="text-white text-sm font-medium">{role.name}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

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
                className="px-8 py-3 theme-btn-primary rounded-xl transition-colors font-semibold disabled:opacity-50"
              >
                {saving ? 'Saving...' : (mode === 'edit' ? 'Update Character' : 'Create Character')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
