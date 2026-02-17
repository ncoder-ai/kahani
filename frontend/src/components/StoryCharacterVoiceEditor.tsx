'use client';

import { useState, useEffect } from 'react';
import { X, Volume2, RotateCcw, Trash2 } from 'lucide-react';
import apiClient, { VoiceStyle, VoiceStylePresetsResponse } from '@/lib/api';

interface StoryCharacter {
  id: number;  // story_character id
  character_id: number;
  story_id: number;
  role: string | null;
  voice_style_override: VoiceStyle | null;
  name: string;
  description: string | null;
  default_voice_style: VoiceStyle | null;
}

interface StoryCharacterVoiceEditorProps {
  storyId: number;
  branchId?: number;
  isOpen: boolean;
  onClose: () => void;
  onUpdate?: () => void;  // Callback when voice styles are updated
}

export default function StoryCharacterVoiceEditor({
  storyId,
  branchId,
  isOpen,
  onClose,
  onUpdate
}: StoryCharacterVoiceEditorProps) {
  const [characters, setCharacters] = useState<StoryCharacter[]>([]);
  const [voicePresets, setVoicePresets] = useState<VoiceStylePresetsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);  // Track which character is being saved
  const [editingCharacterId, setEditingCharacterId] = useState<number | null>(null);
  const [editingVoiceStyle, setEditingVoiceStyle] = useState<VoiceStyle | null>(null);
  const [showCustomization, setShowCustomization] = useState(false);
  const [deletingCharacterId, setDeletingCharacterId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, storyId, branchId]);

  const loadData = async () => {
    try {
      setLoading(true);

      // If branchId is not provided, fetch the story to get its current_branch_id
      let effectiveBranchId = branchId;
      if (effectiveBranchId === undefined) {
        try {
          const story = await apiClient.getStory(storyId);
          effectiveBranchId = story.current_branch_id;
        } catch (err) {
          console.warn('[StoryCharacterVoiceEditor] Failed to get story, proceeding without branch filter');
        }
      }

      const [chars, presets] = await Promise.all([
        apiClient.getStoryCharacters(storyId, effectiveBranchId),
        apiClient.getVoiceStylePresets()
      ]);
      setCharacters(chars);
      setVoicePresets(presets);
    } catch (error) {
      console.error('Failed to load story characters:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEditCharacter = (character: StoryCharacter) => {
    setEditingCharacterId(character.id);
    // Use override if set, otherwise use default, otherwise empty
    setEditingVoiceStyle(character.voice_style_override || character.default_voice_style || null);
    setShowCustomization(character.voice_style_override?.preset === 'custom' || character.default_voice_style?.preset === 'custom');
  };

  const handleSaveVoiceStyle = async () => {
    if (editingCharacterId === null) return;

    try {
      setSaving(editingCharacterId);
      await apiClient.updateStoryCharacterVoiceStyle(storyId, editingCharacterId, editingVoiceStyle);
      
      // Update local state
      setCharacters(prev => prev.map(c => 
        c.id === editingCharacterId 
          ? { ...c, voice_style_override: editingVoiceStyle }
          : c
      ));
      
      setEditingCharacterId(null);
      setEditingVoiceStyle(null);
      setShowCustomization(false);
      
      if (onUpdate) onUpdate();
    } catch (error) {
      console.error('Failed to save voice style:', error);
      alert('Failed to save voice style. Please try again.');
    } finally {
      setSaving(null);
    }
  };

  const handleResetToDefault = async (characterId: number) => {
    try {
      setSaving(characterId);
      await apiClient.clearStoryCharacterVoiceStyle(storyId, characterId);
      
      // Update local state
      setCharacters(prev => prev.map(c => 
        c.id === characterId 
          ? { ...c, voice_style_override: null }
          : c
      ));
      
      if (onUpdate) onUpdate();
    } catch (error) {
      console.error('Failed to reset voice style:', error);
      alert('Failed to reset voice style. Please try again.');
    } finally {
      setSaving(null);
    }
  };

  const handleCancelEdit = () => {
    setEditingCharacterId(null);
    setEditingVoiceStyle(null);
    setShowCustomization(false);
  };

  const handleRemoveCharacter = async (characterId: number) => {
    try {
      setDeletingCharacterId(characterId);
      await apiClient.removeStoryCharacter(storyId, characterId);

      // Remove from local state
      setCharacters(prev => prev.filter(c => c.id !== characterId));
      setConfirmDelete(null);

      if (onUpdate) onUpdate();
    } catch (error) {
      console.error('Failed to remove character from story:', error);
      alert('Failed to remove character. Please try again.');
    } finally {
      setDeletingCharacterId(null);
    }
  };

  const getEffectiveVoiceStyle = (character: StoryCharacter): VoiceStyle | null => {
    return character.voice_style_override || character.default_voice_style;
  };

  const getVoiceStyleLabel = (voiceStyle: VoiceStyle | null): string => {
    if (!voiceStyle) return 'Standard (no special voice)';
    if (voiceStyle.preset && voiceStyle.preset !== 'custom' && voicePresets) {
      const preset = voicePresets.presets[voiceStyle.preset];
      return preset?.name || voiceStyle.preset;
    }
    if (voiceStyle.preset === 'custom') return 'Custom Voice Style';
    return 'Custom Voice Style';
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-white/20">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <Volume2 className="w-6 h-6 text-purple-400" />
              <h3 className="text-2xl font-bold text-white">Character Voice Styles</h3>
            </div>
            <button
              onClick={onClose}
              className="text-white/60 hover:text-white text-xl p-2 hover:bg-white/10 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <p className="text-white/60 mt-2">
            Customize how each character speaks in this story. Changes here override the character's default voice style.
          </p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="text-center py-12">
              <div className="text-white/60">Loading characters...</div>
            </div>
          ) : characters.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-white/60">No characters in this story yet.</div>
            </div>
          ) : editingCharacterId !== null ? (
            /* Edit Mode */
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h4 className="text-lg font-semibold text-white">
                  Editing: {characters.find(c => c.id === editingCharacterId)?.name}
                </h4>
                <button
                  onClick={handleCancelEdit}
                  className="text-white/60 hover:text-white text-sm"
                >
                  ← Back to list
                </button>
              </div>

              {voicePresets && (
                <div className="space-y-4">
                  {/* Preset Selection */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Voice Style Preset
                    </label>
                    <select
                      value={editingVoiceStyle?.preset ?? ''}
                      onChange={(e) => {
                        const presetId = e.target.value;
                        if (!presetId) {
                          setEditingVoiceStyle(null);
                          setShowCustomization(false);
                        } else if (presetId === 'custom') {
                          setEditingVoiceStyle({ 
                            preset: 'custom',
                            formality: 'casual',
                            vocabulary: 'average',
                            tone: 'calm',
                            profanity: 'none',
                            primary_language: 'english',
                            language_mixing: 'none'
                          });
                          setShowCustomization(true);
                        } else {
                          setEditingVoiceStyle({ preset: presetId });
                          setShowCustomization(false);
                        }
                      }}
                      className="w-full p-3 bg-gray-800 border border-white/30 rounded-lg text-white focus:outline-none theme-focus-ring [&>option]:bg-gray-800 [&>option]:text-white [&>optgroup]:bg-gray-800 [&>optgroup]:text-white"
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
                  {editingVoiceStyle?.preset && editingVoiceStyle.preset !== 'custom' && voicePresets.presets[editingVoiceStyle.preset] && (
                    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                      <p className="text-white/60 text-sm mb-2">{voicePresets.presets[editingVoiceStyle.preset].description}</p>
                      <p className="text-white/80 text-sm italic">"{voicePresets.presets[editingVoiceStyle.preset].example}"</p>
                    </div>
                  )}

                  {/* Custom Voice Style Options */}
                  {showCustomization && (
                    <div className="space-y-4 bg-white/5 rounded-lg p-4 border border-white/10">
                      <div className="grid grid-cols-2 gap-4">
                        {/* Formality */}
                        <div>
                          <label className="block text-sm font-medium text-white/80 mb-1">Formality</label>
                          <select
                            value={editingVoiceStyle?.formality || 'casual'}
                            onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, formality: e.target.value } as VoiceStyle)}
                            className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
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
                            value={editingVoiceStyle?.vocabulary || 'average'}
                            onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, vocabulary: e.target.value } as VoiceStyle)}
                            className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
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
                            value={editingVoiceStyle?.tone || 'calm'}
                            onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, tone: e.target.value } as VoiceStyle)}
                            className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
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
                            value={editingVoiceStyle?.profanity || 'none'}
                            onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, profanity: e.target.value } as VoiceStyle)}
                            className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
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
                          value={editingVoiceStyle?.speech_quirks ?? ''}
                          onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, speech_quirks: e.target.value } as VoiceStyle)}
                          placeholder="e.g., Says 'actually' often, ends questions with 'no?'"
                          className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white placeholder-white/40 text-sm"
                        />
                      </div>

                      {/* Language Settings */}
                      <div className="border-t border-white/10 pt-4 mt-4">
                        <h5 className="text-sm font-medium text-white mb-3">Language Settings</h5>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          {/* Primary Language */}
                          <div>
                            <label className="block text-sm font-medium text-white/80 mb-1">Primary Language</label>
                            <select
                              value={editingVoiceStyle?.primary_language || 'english'}
                              onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, primary_language: e.target.value } as VoiceStyle)}
                              className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
                            >
                              <option value="english">English</option>
                              <option value="hindi">Hindi</option>
                              <option value="spanish">Spanish</option>
                              <option value="french">French</option>
                              <option value="mandarin">Mandarin</option>
                              <option value="japanese">Japanese</option>
                              <option value="german">German</option>
                              <option value="italian">Italian</option>
                              <option value="portuguese">Portuguese</option>
                              <option value="korean">Korean</option>
                              <option value="arabic">Arabic</option>
                              <option value="russian">Russian</option>
                            </select>
                          </div>

                          {/* Secondary Language */}
                          <div>
                            <label className="block text-sm font-medium text-white/80 mb-1">Mix In Language</label>
                            <select
                              value={editingVoiceStyle?.secondary_language ?? ''}
                              onChange={(e) => setEditingVoiceStyle({ 
                                ...editingVoiceStyle, 
                                secondary_language: e.target.value || undefined,
                                language_mixing: e.target.value ? (editingVoiceStyle?.language_mixing || 'light') : 'none'
                              } as VoiceStyle)}
                              className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
                            >
                              <option value="">None</option>
                              {voicePresets.attributes.secondary_languages?.map(lang => (
                                <option key={lang.id} value={lang.id}>{lang.name}</option>
                              ))}
                            </select>
                          </div>

                          {/* Mixing Frequency */}
                          {editingVoiceStyle?.secondary_language && (
                            <div>
                              <label className="block text-sm font-medium text-white/80 mb-1">Mixing Frequency</label>
                              <select
                                value={editingVoiceStyle?.language_mixing || 'light'}
                                onChange={(e) => setEditingVoiceStyle({ ...editingVoiceStyle, language_mixing: e.target.value } as VoiceStyle)}
                                className="w-full p-2 bg-gray-800 border border-white/20 rounded-lg text-white text-sm [&>option]:bg-gray-800 [&>option]:text-white"
                              >
                                {voicePresets.attributes.language_mixing_level?.map(level => (
                                  <option key={level.id} value={level.id}>{level.name}</option>
                                ))}
                              </select>
                            </div>
                          )}
                        </div>
                        
                        {/* Mixing Frequency Description */}
                        {editingVoiceStyle?.secondary_language && editingVoiceStyle?.language_mixing && (
                          <p className="text-xs text-white/50 mt-2">
                            {editingVoiceStyle.language_mixing === 'light' && 'Occasional words from the secondary language (1-2 per dialogue line)'}
                            {editingVoiceStyle.language_mixing === 'moderate' && 'Regular mixing of secondary language (2-3 words per dialogue line)'}
                            {editingVoiceStyle.language_mixing === 'heavy' && 'Frequent use of secondary language (3-5 words per dialogue line)'}
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Toggle Customization Button for Presets */}
                  {editingVoiceStyle?.preset && editingVoiceStyle.preset !== 'custom' && (
                    <button
                      type="button"
                      onClick={() => {
                        if (showCustomization) {
                          // Reset to just preset
                          setEditingVoiceStyle({ preset: editingVoiceStyle?.preset });
                        }
                        setShowCustomization(!showCustomization);
                      }}
                      className="text-sm text-white/60 hover:text-white"
                    >
                      {showCustomization ? '← Use preset only' : '+ Customize further'}
                    </button>
                  )}

                  {/* Save/Cancel Buttons */}
                  <div className="flex justify-end gap-3 pt-4 border-t border-white/10">
                    <button
                      onClick={handleCancelEdit}
                      className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveVoiceStyle}
                      disabled={saving !== null}
                      className="px-4 py-2 theme-btn-primary rounded-lg transition-colors disabled:opacity-50"
                    >
                      {saving === editingCharacterId ? 'Saving...' : 'Save Voice Style'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Character List */
            <div className="space-y-3">
              {characters.map((character) => {
                const effectiveStyle = getEffectiveVoiceStyle(character);
                const hasOverride = character.voice_style_override !== null;
                
                return (
                  <div
                    key={character.id}
                    className="bg-white/5 rounded-lg p-4 border border-white/10 hover:border-white/20 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-lg font-semibold text-white">{character.name}</h4>
                          {character.role && (
                            <span className="text-xs px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded">
                              {character.role}
                            </span>
                          )}
                          {hasOverride && (
                            <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded">
                              Custom for this story
                            </span>
                          )}
                        </div>
                        <p className="text-white/60 text-sm mt-1">
                          Voice: {getVoiceStyleLabel(effectiveStyle)}
                        </p>
                        {effectiveStyle?.secondary_language && effectiveStyle.language_mixing !== 'none' && (
                          <p className="text-white/50 text-xs mt-1">
                            + {effectiveStyle.secondary_language} mixing ({effectiveStyle.language_mixing})
                          </p>
                        )}
                      </div>
                      
                      <div className="flex items-center gap-2">
                        {hasOverride && (
                          <button
                            onClick={() => handleResetToDefault(character.id)}
                            disabled={saving === character.id}
                            className="p-2 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                            title="Reset to default voice style"
                          >
                            <RotateCcw className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleEditCharacter(character)}
                          disabled={saving !== null}
                          className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
                        >
                          Edit Voice
                        </button>
                        {confirmDelete === character.id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleRemoveCharacter(character.id)}
                              disabled={deletingCharacterId === character.id}
                              className="px-2 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                            >
                              {deletingCharacterId === character.id ? 'Removing...' : 'Confirm'}
                            </button>
                            <button
                              onClick={() => setConfirmDelete(null)}
                              disabled={deletingCharacterId === character.id}
                              className="px-2 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs rounded-lg transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmDelete(character.id)}
                            disabled={saving !== null || deletingCharacterId !== null}
                            className="p-2 text-white/40 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-50"
                            title="Remove character from story"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/20 bg-white/5">
          <p className="text-white/50 text-sm text-center">
            Voice style changes only affect this story. Character defaults remain unchanged.
          </p>
        </div>
      </div>
    </div>
  );
}

