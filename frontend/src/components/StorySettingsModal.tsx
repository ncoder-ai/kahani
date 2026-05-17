'use client';

import { useState, useEffect } from 'react';
import { X, Plus, ChevronDown, RefreshCw, Globe } from 'lucide-react';
import apiClient from '@/lib/api';
import { WorldsApi } from '@/lib/api/worlds';
import type { World } from '@/lib/api/types';

const worldsApi = new WorldsApi();

interface InteractionPreset {
  name: string;
  description: string;
  types: string[];
}

interface StorySettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  storyId: number;
  onSaved?: () => void;
}

export default function StorySettingsModal({ isOpen, onClose, storyId, onSaved }: StorySettingsModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionMessage, setExtractionMessage] = useState<string | null>(null);
  const [extractionProgress, setExtractionProgress] = useState<{
    current: number;
    total: number;
    percentage: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    genre: '',
    tone: '',
    world_setting: '',
    initial_premise: '',
    scenario: '',
    content_rating: 'sfw' as 'sfw' | 'nsfw',
    plot_check_mode: '1' as '1' | '3' | 'all',
  });
  const [userAllowsNsfw, setUserAllowsNsfw] = useState(false);
  
  // World state
  const [worlds, setWorlds] = useState<World[]>([]);
  const [currentWorldId, setCurrentWorldId] = useState<number | null>(null);
  const [showWorldDropdown, setShowWorldDropdown] = useState(false);

  // Interaction types state
  const [interactionTypes, setInteractionTypes] = useState<string[]>([]);
  const [newInteractionType, setNewInteractionType] = useState('');
  const [interactionPresets, setInteractionPresets] = useState<Record<string, InteractionPreset>>({});
  const [showPresetDropdown, setShowPresetDropdown] = useState(false);

  useEffect(() => {
    if (isOpen && storyId) {
      loadStoryData();
      loadInteractionPresets();
      loadWorlds();
    }
  }, [isOpen, storyId]);

  const loadWorlds = async () => {
    try {
      const data = await worldsApi.getWorlds();
      setWorlds(data);
    } catch (err) {
      console.error('Failed to load worlds:', err);
    }
  };

  const loadInteractionPresets = async () => {
    try {
      const presets = await apiClient.getInteractionPresets();
      setInteractionPresets(presets);
    } catch (err) {
      console.error('Failed to load interaction presets:', err);
      // Non-critical, don't show error
    }
  };

  const loadStoryData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      // Load story data
      const story = await apiClient.getStory(storyId);
      const { title, description, genre, tone, world_setting, initial_premise, scenario, content_rating, plot_check_mode } = story;
      setFormData(prev => ({
        ...prev,
        title, description, genre, tone, world_setting, initial_premise, scenario, content_rating, plot_check_mode,
      }));
      setInteractionTypes(story.interaction_types || []);
      setCurrentWorldId(story.world_id ?? null);
      
      // Load user profile to check NSFW permission
      try {
        const user = await apiClient.getCurrentUser();
        // allow_nsfw is nested inside permissions object
        setUserAllowsNsfw(user.permissions?.allow_nsfw || false);
      } catch {
        setUserAllowsNsfw(false);
      }
    } catch (err) {
      console.error('Failed to load story data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load story data');
    } finally {
      setIsLoading(false);
    }
  };

  const addInteractionType = () => {
    const trimmed = newInteractionType.trim().toLowerCase();
    if (trimmed && !interactionTypes.includes(trimmed)) {
      setInteractionTypes([...interactionTypes, trimmed]);
      setNewInteractionType('');
    }
  };

  const removeInteractionType = (type: string) => {
    setInteractionTypes(interactionTypes.filter(t => t !== type));
  };

  const loadPreset = (presetKey: string) => {
    const preset = interactionPresets[presetKey];
    if (preset) {
      setInteractionTypes(preset.types);
    }
    setShowPresetDropdown(false);
  };

  const pollExtractionProgress = async () => {
    const pollInterval = setInterval(async () => {
      try {
        const result = await apiClient.getExtractionProgress(storyId);
        
        if (!result.in_progress) {
          // Extraction complete or not started
          clearInterval(pollInterval);
          setIsExtracting(false);
          
          // Get final count
          const interactions = await apiClient.getStoryInteractions(storyId);
          setExtractionMessage(`Extraction complete! Found ${interactions.total_interactions} interactions.`);
          setExtractionProgress(null);
          return;
        }
        
        const percentage = result.total_batches > 0 
          ? Math.round((result.batches_processed / result.total_batches) * 100)
          : 0;
        
        setExtractionProgress({
          current: result.batches_processed,
          total: result.total_batches,
          percentage
        });
        
      } catch (err) {
        console.error('Failed to poll extraction progress:', err);
      }
    }, 2000); // Poll every 2 seconds
    
    // Stop polling after 5 minutes max
    setTimeout(() => {
      clearInterval(pollInterval);
      setIsExtracting(false);
      setExtractionMessage('Extraction timeout. Check back later.');
      setExtractionProgress(null);
    }, 300000);
  };

  const runRetroactiveExtraction = async () => {
    if (interactionTypes.length === 0) {
      setError('Configure interaction types first before scanning existing scenes.');
      return;
    }
    
    setIsExtracting(true);
    setExtractionMessage(null);
    setExtractionProgress(null);
    setError(null);
    
    try {
      // First save the current interaction types
      await apiClient.updateStory(storyId, { interaction_types: interactionTypes });
      
      // Then trigger extraction
      const result = await apiClient.extractInteractionsRetroactively(storyId);
      setExtractionMessage(`Scanning ${result.scene_count} scenes in ${result.num_batches} batches...`);
      
      // Start polling for progress
      pollExtractionProgress();
    } catch (err) {
      console.error('Failed to start extraction:', err);
      setError(err instanceof Error ? err.message : 'Failed to start extraction');
      setIsExtracting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);

    try {
      await apiClient.updateStory(storyId, {
        title: formData.title,
        description: formData.description,
        genre: formData.genre,
        tone: formData.tone,
        world_setting: formData.world_setting,
        initial_premise: formData.initial_premise,
        scenario: formData.scenario,
        content_rating: formData.content_rating,
        plot_check_mode: formData.plot_check_mode,
        interaction_types: interactionTypes,
        ...(currentWorldId !== null ? { world_id: currentWorldId } : {}),
      });
      if (onSaved) {
        onSaved();
      }
      onClose();
    } catch (err) {
      console.error('Failed to update story:', err);
      setError(err instanceof Error ? err.message : 'Failed to update story');
    } finally {
      setIsSaving(false);
    }
  };

  const handleChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-2xl max-h-[95vh] sm:max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-3 sm:p-6 border-b border-slate-700 bg-gradient-to-r from-purple-900/50 to-pink-900/50">
            <h2 className="text-lg sm:text-2xl font-bold text-white">Edit Story Settings</h2>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 active:bg-slate-600 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-300" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-6">
            {isLoading ? (
              <div className="text-center py-12">
                <div className="text-gray-300">Loading story data...</div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-6">
                {error && (
                  <div className="bg-red-900/50 border border-red-700 rounded-lg p-3 sm:p-4 text-red-200 text-sm">
                    {error}
                  </div>
                )}

                {/* World */}
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    World
                  </label>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setShowWorldDropdown(!showWorldDropdown)}
                      className="w-full flex items-center justify-between gap-2 px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm hover:border-slate-400 active:bg-slate-600 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Globe className="w-4 h-4 text-indigo-400" />
                        <span>
                          {currentWorldId
                            ? worlds.find(w => w.id === currentWorldId)?.name || 'Unknown World'
                            : 'No world assigned'}
                        </span>
                      </div>
                      <ChevronDown className={`w-4 h-4 transition-transform ${showWorldDropdown ? 'rotate-180' : ''}`} />
                    </button>

                    {showWorldDropdown && (
                      <div className="absolute top-full left-0 right-0 mt-1 bg-slate-700 border border-slate-600 rounded-lg shadow-xl z-20 max-h-48 overflow-y-auto">
                        {worlds.map((world) => (
                          <button
                            key={world.id}
                            type="button"
                            onClick={() => {
                              setCurrentWorldId(world.id);
                              setShowWorldDropdown(false);
                            }}
                            className={`w-full px-3 py-2 text-left hover:bg-slate-600 active:bg-slate-500 transition-colors first:rounded-t-lg last:rounded-b-lg ${
                              currentWorldId === world.id ? 'bg-indigo-600/20 text-indigo-300' : ''
                            }`}
                          >
                            <div className="text-xs sm:text-sm font-medium text-white">{world.name}</div>
                            <div className="text-[10px] sm:text-xs text-gray-400">
                              {world.story_count} {world.story_count === 1 ? 'story' : 'stories'}
                            </div>
                          </button>
                        ))}
                        {worlds.length === 0 && (
                          <div className="px-3 py-2 text-xs sm:text-sm text-gray-400">No worlds available</div>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="text-[10px] sm:text-xs text-gray-400 mt-1.5">
                    Stories in the same world share characters and lore.
                  </p>
                </div>

                {/* Title */}
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Title *
                  </label>
                  <input
                    type="text"
                    value={formData.title}
                    onChange={(e) => handleChange('title', e.target.value)}
                    required
                    className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    placeholder="Story title"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => handleChange('description', e.target.value)}
                    rows={2}
                    className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
                    placeholder="Brief description of the story"
                  />
                </div>

                {/* Genre and Tone - side by side on larger screens */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                  <div>
                    <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                      Genre
                    </label>
                    <input
                      type="text"
                      value={formData.genre}
                      onChange={(e) => handleChange('genre', e.target.value)}
                      className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      placeholder="e.g., Fantasy, Sci-Fi"
                    />
                  </div>
                  <div>
                    <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                      Tone
                    </label>
                    <input
                      type="text"
                      value={formData.tone}
                      onChange={(e) => handleChange('tone', e.target.value)}
                      className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      placeholder="e.g., Dark, Lighthearted"
                    />
                  </div>
                </div>

                {/* World Setting */}
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    World Setting
                  </label>
                  <textarea
                    value={formData.world_setting}
                    onChange={(e) => handleChange('world_setting', e.target.value)}
                    rows={2}
                    className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
                    placeholder="Describe the world or setting"
                  />
                </div>

                {/* Initial Premise */}
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Initial Premise
                  </label>
                  <textarea
                    value={formData.initial_premise}
                    onChange={(e) => handleChange('initial_premise', e.target.value)}
                    rows={2}
                    className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
                    placeholder="The initial premise or concept"
                  />
                </div>

                {/* Scenario */}
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Scenario
                  </label>
                  <textarea
                    value={formData.scenario}
                    onChange={(e) => handleChange('scenario', e.target.value)}
                    rows={3}
                    className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
                    placeholder="The scenario that sets up your story"
                  />
                </div>

                {/* Interaction Tracking */}
                <div className="border-t border-slate-700 pt-4 sm:pt-6">
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Interaction Tracking
                  </label>
                  <p className="text-[10px] sm:text-xs text-gray-400 mb-3">
                    Track specific interactions between characters for story consistency.
                  </p>

                  {/* Current interaction types */}
                  <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-3 min-h-[28px]">
                    {interactionTypes.length === 0 ? (
                      <span className="text-gray-400 text-xs sm:text-sm italic">No interaction types configured</span>
                    ) : (
                      interactionTypes.map((type) => (
                        <span
                          key={type}
                          className="inline-flex items-center gap-1 px-2 sm:px-3 py-0.5 sm:py-1 bg-purple-900/50 border border-purple-700 rounded-full text-xs sm:text-sm text-purple-200"
                        >
                          {type}
                          <button
                            type="button"
                            onClick={() => removeInteractionType(type)}
                            className="hover:text-red-400 active:text-red-300 transition-colors p-0.5"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))
                    )}
                  </div>

                  {/* Add new interaction type */}
                  <div className="flex gap-2 mb-3">
                    <input
                      type="text"
                      value={newInteractionType}
                      onChange={(e) => setNewInteractionType(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          addInteractionType();
                        }
                      }}
                      placeholder="Add interaction type..."
                      className="flex-1 min-w-0 px-3 py-1.5 bg-slate-700 border border-slate-500 rounded-lg text-white text-xs sm:text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    <button
                      type="button"
                      onClick={addInteractionType}
                      className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-white rounded-lg transition-colors flex-shrink-0"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Preset selector and scan button */}
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowPresetDropdown(!showPresetDropdown)}
                        className="w-full sm:w-auto flex items-center justify-between sm:justify-start gap-2 px-3 py-1.5 bg-slate-700 border border-slate-500 rounded-lg text-xs sm:text-sm text-gray-200 hover:border-slate-400 active:bg-slate-600 transition-colors"
                      >
                        Load from preset
                        <ChevronDown className={`w-4 h-4 transition-transform ${showPresetDropdown ? 'rotate-180' : ''}`} />
                      </button>

                      {showPresetDropdown && (
                        <div className="absolute top-full left-0 right-0 sm:right-auto mt-1 w-full sm:w-64 bg-slate-700 border border-slate-600 rounded-lg shadow-xl z-10 max-h-48 sm:max-h-64 overflow-y-auto">
                          {Object.entries(interactionPresets).map(([key, preset]) => (
                            <button
                              key={key}
                              type="button"
                              onClick={() => loadPreset(key)}
                              className="w-full px-3 py-2 text-left hover:bg-slate-600 active:bg-slate-500 transition-colors first:rounded-t-lg last:rounded-b-lg"
                            >
                              <div className="text-xs sm:text-sm font-medium text-white">{preset.name}</div>
                              <div className="text-[10px] sm:text-xs text-gray-400">{preset.description}</div>
                            </button>
                          ))}
                          {Object.keys(interactionPresets).length === 0 && (
                            <div className="px-3 py-2 text-xs sm:text-sm text-gray-400">No presets available</div>
                          )}
                        </div>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={runRetroactiveExtraction}
                      disabled={isExtracting || interactionTypes.length === 0}
                      className="flex items-center justify-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-slate-700 disabled:text-gray-500 text-white rounded-lg text-xs sm:text-sm transition-colors"
                      title="Scan existing scenes for these interaction types"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${isExtracting ? 'animate-spin' : ''}`} />
                      {isExtracting ? 'Scanning...' : 'Scan Scenes'}
                    </button>
                  </div>

                  {extractionMessage && (
                    <p className="text-[10px] sm:text-xs text-blue-400 mt-2">{extractionMessage}</p>
                  )}

                  {extractionProgress && (
                    <div className="mt-3 space-y-1.5 sm:space-y-2">
                      <div className="flex justify-between text-[10px] sm:text-xs text-gray-300">
                        <span>Processing batches...</span>
                        <span>{extractionProgress.current} of {extractionProgress.total}</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-1.5 sm:h-2 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-purple-500 to-pink-500 h-full transition-all duration-500 ease-out"
                          style={{ width: `${extractionProgress.percentage}%` }}
                        />
                      </div>
                      <p className="text-[10px] sm:text-xs text-gray-400">
                        {extractionProgress.percentage}% complete
                      </p>
                    </div>
                  )}
                </div>

                {/* Plot Check Mode */}
                <div className="border-t border-slate-700 pt-4 sm:pt-6">
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Plot Check Mode
                  </label>
                  <select
                    value={formData.plot_check_mode}
                    onChange={(e) => handleChange('plot_check_mode', e.target.value)}
                    className="w-full px-3 sm:px-4 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  >
                    <option value="1">Next event only (strict linear)</option>
                    <option value="3">Next 3 events (slight flexibility)</option>
                    <option value="all">All remaining events (full flexibility)</option>
                  </select>
                  <p className="text-[10px] sm:text-xs text-gray-400 mt-2">
                    Controls how many plot events are checked after each scene.
                    Strict = events must happen in exact order. Flexible = events can be detected out of order.
                  </p>
                </div>

                {/* Content Rating */}
                <div className="border-t border-slate-700 pt-4 sm:pt-6">
                  <label className="block text-xs sm:text-sm font-medium text-gray-200 mb-1.5 sm:mb-2">
                    Content Rating
                  </label>
                  <div className="flex items-center gap-3 sm:gap-4">
                    <button
                      type="button"
                      onClick={() => handleChange('content_rating', 'sfw')}
                      className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg border text-sm transition-colors ${
                        formData.content_rating === 'sfw'
                          ? 'bg-green-600 border-green-500 text-white'
                          : 'bg-slate-700 border-slate-500 text-gray-300 hover:border-slate-400 active:bg-slate-600'
                      }`}
                    >
                      SFW
                    </button>
                    <button
                      type="button"
                      onClick={() => userAllowsNsfw && handleChange('content_rating', 'nsfw')}
                      disabled={!userAllowsNsfw}
                      className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg border text-sm transition-colors ${
                        formData.content_rating === 'nsfw'
                          ? 'bg-red-600 border-red-500 text-white'
                          : userAllowsNsfw
                            ? 'bg-slate-700 border-slate-500 text-gray-300 hover:border-slate-400 active:bg-slate-600'
                            : 'bg-slate-800 border-slate-700 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      NSFW
                    </button>
                  </div>
                  <p className="text-[10px] sm:text-xs text-gray-400 mt-2">
                    {formData.content_rating === 'sfw'
                      ? 'Content filters are enabled. Story will be family-friendly.'
                      : 'Content filters are disabled. Mature content is allowed.'}
                    {!userAllowsNsfw && (
                      <span className="block mt-1 text-yellow-500">
                        NSFW option requires NSFW permissions in your profile.
                      </span>
                    )}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3 pt-4 border-t border-slate-700">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 sm:px-6 py-2 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 text-white rounded-lg transition-colors text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="px-4 sm:px-6 py-2 bg-purple-600 hover:bg-purple-700 active:bg-purple-800 disabled:bg-purple-800 disabled:cursor-not-allowed text-white rounded-lg transition-colors text-sm"
                  >
                    {isSaving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

