'use client';

import { useState, useEffect } from 'react';
import { X, Plus, ChevronDown, RefreshCw } from 'lucide-react';
import apiClient from '@/lib/api';

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
  });
  const [userAllowsNsfw, setUserAllowsNsfw] = useState(false);
  
  // Interaction types state
  const [interactionTypes, setInteractionTypes] = useState<string[]>([]);
  const [newInteractionType, setNewInteractionType] = useState('');
  const [interactionPresets, setInteractionPresets] = useState<Record<string, InteractionPreset>>({});
  const [showPresetDropdown, setShowPresetDropdown] = useState(false);

  useEffect(() => {
    if (isOpen && storyId) {
      loadStoryData();
      loadInteractionPresets();
    }
  }, [isOpen, storyId]);

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
      setFormData({
        title: story.title || '',
        description: story.description ?? '',
        genre: story.genre || '',
        tone: story.tone || '',
        world_setting: story.world_setting ?? '',
        initial_premise: story.initial_premise ?? '',
        scenario: story.scenario ?? '',
        content_rating: (story.content_rating || 'sfw') as 'sfw' | 'nsfw',
      });
      setInteractionTypes(story.interaction_types || []);
      
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
        ...formData,
        interaction_types: interactionTypes,
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
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-slate-700 bg-gradient-to-r from-purple-900/50 to-pink-900/50">
            <h2 className="text-2xl font-bold text-white">Edit Story Settings</h2>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-400" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {isLoading ? (
              <div className="text-center py-12">
                <div className="text-gray-400">Loading story data...</div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-6">
                {error && (
                  <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-200">
                    {error}
                  </div>
                )}

                {/* Title */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Title *
                  </label>
                  <input
                    type="text"
                    value={formData.title}
                    onChange={(e) => handleChange('title', e.target.value)}
                    required
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="Story title"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => handleChange('description', e.target.value)}
                    rows={3}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="Brief description of the story"
                  />
                </div>

                {/* Genre */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Genre
                  </label>
                  <input
                    type="text"
                    value={formData.genre}
                    onChange={(e) => handleChange('genre', e.target.value)}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="e.g., Fantasy, Sci-Fi, Romance"
                  />
                </div>

                {/* Tone */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Tone
                  </label>
                  <input
                    type="text"
                    value={formData.tone}
                    onChange={(e) => handleChange('tone', e.target.value)}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="e.g., Dark, Lighthearted, Mysterious"
                  />
                </div>

                {/* World Setting */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    World Setting
                  </label>
                  <textarea
                    value={formData.world_setting}
                    onChange={(e) => handleChange('world_setting', e.target.value)}
                    rows={3}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="Describe the world or setting of your story"
                  />
                </div>

                {/* Initial Premise */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Initial Premise
                  </label>
                  <textarea
                    value={formData.initial_premise}
                    onChange={(e) => handleChange('initial_premise', e.target.value)}
                    rows={3}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="The initial premise or concept of your story"
                  />
                </div>

                {/* Scenario */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Scenario
                  </label>
                  <textarea
                    value={formData.scenario}
                    onChange={(e) => handleChange('scenario', e.target.value)}
                    rows={4}
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="The scenario that sets up your story"
                  />
                </div>

                {/* Interaction Tracking */}
                <div className="border-t border-slate-700 pt-6">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Interaction Tracking
                  </label>
                  <p className="text-xs text-gray-500 mb-3">
                    Track specific interactions between characters to maintain story consistency.
                    The system will record when these events first occur.
                  </p>
                  
                  {/* Current interaction types */}
                  <div className="flex flex-wrap gap-2 mb-3 min-h-[32px]">
                    {interactionTypes.length === 0 ? (
                      <span className="text-gray-500 text-sm italic">No interaction types configured</span>
                    ) : (
                      interactionTypes.map((type) => (
                        <span
                          key={type}
                          className="inline-flex items-center gap-1 px-3 py-1 bg-purple-900/50 border border-purple-700 rounded-full text-sm text-purple-200"
                        >
                          {type}
                          <button
                            type="button"
                            onClick={() => removeInteractionType(type)}
                            className="hover:text-red-400 transition-colors"
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
                      className="flex-1 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    <button
                      type="button"
                      onClick={addInteractionType}
                      className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  
                  {/* Preset selector and scan button */}
                  <div className="flex gap-2 flex-wrap">
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowPresetDropdown(!showPresetDropdown)}
                        className="flex items-center gap-2 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-gray-300 hover:border-slate-500 transition-colors"
                      >
                        Load from preset
                        <ChevronDown className={`w-4 h-4 transition-transform ${showPresetDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      
                      {showPresetDropdown && (
                        <div className="absolute top-full left-0 mt-1 w-64 bg-slate-700 border border-slate-600 rounded-lg shadow-xl z-10 max-h-64 overflow-y-auto">
                          {Object.entries(interactionPresets).map(([key, preset]) => (
                            <button
                              key={key}
                              type="button"
                              onClick={() => loadPreset(key)}
                              className="w-full px-3 py-2 text-left hover:bg-slate-600 transition-colors first:rounded-t-lg last:rounded-b-lg"
                            >
                              <div className="text-sm font-medium text-white">{preset.name}</div>
                              <div className="text-xs text-gray-400">{preset.description}</div>
                            </button>
                          ))}
                          {Object.keys(interactionPresets).length === 0 && (
                            <div className="px-3 py-2 text-sm text-gray-400">No presets available</div>
                          )}
                        </div>
                      )}
                    </div>
                    
                    <button
                      type="button"
                      onClick={runRetroactiveExtraction}
                      disabled={isExtracting || interactionTypes.length === 0}
                      className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-gray-500 text-white rounded-lg text-sm transition-colors"
                      title="Scan existing scenes for these interaction types"
                    >
                      <RefreshCw className={`w-4 h-4 ${isExtracting ? 'animate-spin' : ''}`} />
                      {isExtracting ? 'Scanning...' : 'Scan Existing Scenes'}
                    </button>
                  </div>
                  
                  {extractionMessage && (
                    <p className="text-xs text-blue-400 mt-2">{extractionMessage}</p>
                  )}
                  
                  {extractionProgress && (
                    <div className="mt-3 space-y-2">
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Processing batches...</span>
                        <span>{extractionProgress.current} of {extractionProgress.total} batches</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                        <div 
                          className="bg-gradient-to-r from-purple-500 to-pink-500 h-full transition-all duration-500 ease-out"
                          style={{ width: `${extractionProgress.percentage}%` }}
                        />
                      </div>
                      <p className="text-xs text-gray-500">
                        {extractionProgress.percentage}% complete
                      </p>
                    </div>
                  )}
                </div>

                {/* Content Rating */}
                <div className="border-t border-slate-700 pt-6">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Content Rating
                  </label>
                  <div className="flex items-center gap-4">
                    <button
                      type="button"
                      onClick={() => handleChange('content_rating', 'sfw')}
                      className={`px-4 py-2 rounded-lg border transition-colors ${
                        formData.content_rating === 'sfw'
                          ? 'bg-green-600 border-green-500 text-white'
                          : 'bg-slate-700 border-slate-600 text-gray-400 hover:border-slate-500'
                      }`}
                    >
                      SFW
                    </button>
                    <button
                      type="button"
                      onClick={() => userAllowsNsfw && handleChange('content_rating', 'nsfw')}
                      disabled={!userAllowsNsfw}
                      className={`px-4 py-2 rounded-lg border transition-colors ${
                        formData.content_rating === 'nsfw'
                          ? 'bg-red-600 border-red-500 text-white'
                          : userAllowsNsfw
                            ? 'bg-slate-700 border-slate-600 text-gray-400 hover:border-slate-500'
                            : 'bg-slate-800 border-slate-700 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      NSFW
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
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
                <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
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

