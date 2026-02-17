'use client';

import React, { useState, useEffect } from 'react';
import { WritingStylePreset, WritingPresetCreateData, WritingPresetUpdateData, SUGGESTED_PRESETS, ProseStyleDefinition } from '@/types/writing-presets';
import api from '@/lib/api';

interface PresetEditorProps {
  preset?: WritingStylePreset;
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: WritingPresetCreateData | WritingPresetUpdateData) => Promise<void>;
}

export default function PresetEditor({ preset, isOpen, onClose, onSave }: PresetEditorProps) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    system_prompt: '',
    summary_system_prompt: '',
    pov: 'third' as 'first' | 'second' | 'third',
    prose_style: 'balanced',
  });
  const [showPromptInfo, setShowPromptInfo] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuggested, setShowSuggested] = useState(false);
  const [expandedProseStyle, setExpandedProseStyle] = useState<string | null>(null);
  const [proseStyles, setProseStyles] = useState<ProseStyleDefinition[]>([]);
  const [loadingProseStyles, setLoadingProseStyles] = useState(false);

  // Load prose styles from API
  useEffect(() => {
    const loadProseStyles = async () => {
      setLoadingProseStyles(true);
      try {
        const styles = await api.getProseStyles();
        setProseStyles(styles);
      } catch (error) {
        console.error('Failed to load prose styles:', error);
      } finally {
        setLoadingProseStyles(false);
      }
    };
    
    if (isOpen) {
      loadProseStyles();
    }
  }, [isOpen]);

  useEffect(() => {
    if (preset) {
      setFormData({
        name: preset.name,
        description: preset.description || '',
        system_prompt: preset.system_prompt,
        summary_system_prompt: preset.summary_system_prompt || '',
        pov: (preset.pov as 'first' | 'second' | 'third') || 'third',
        prose_style: preset.prose_style || 'balanced',
      });
    } else {
      // New preset - load default template from API
      const loadDefault = async () => {
        try {
          const data = await api.getDefaultWritingPresetTemplate();
          setFormData({
            name: '',
            description: '',
            system_prompt: data.system_prompt || SUGGESTED_PRESETS[0].system_prompt,
            summary_system_prompt: '',
            pov: (data.pov as 'first' | 'second' | 'third') || 'third',
            prose_style: data.prose_style || 'balanced',
          });
        } catch (error) {
          console.error('Failed to load default template:', error);
          // Fallback to suggested preset
          setFormData({
            name: '',
            description: '',
            system_prompt: SUGGESTED_PRESETS[0].system_prompt,
            summary_system_prompt: '',
            pov: 'third',
            prose_style: 'balanced',
          });
        }
      };
      loadDefault();
    }
    setError(null);
  }, [preset, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSaving(true);

    try {
      const data: any = {
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
        system_prompt: formData.system_prompt.trim(),
        summary_system_prompt: formData.summary_system_prompt.trim() || undefined,
        pov: formData.pov,
        prose_style: formData.prose_style,
      };

      await onSave(data);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to save preset');
    } finally {
      setIsSaving(false);
    }
  };

  const loadSuggestedPreset = (suggested: typeof SUGGESTED_PRESETS[0]) => {
    setFormData({
      ...formData,
      name: suggested.name,
      description: suggested.description,
      system_prompt: suggested.system_prompt,
      summary_system_prompt: suggested.summary_system_prompt || '',
    });
    setShowSuggested(false);
  };

  const toggleProseStyleExample = (styleKey: string) => {
    setExpandedProseStyle(expandedProseStyle === styleKey ? null : styleKey);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            {preset ? 'Edit Writing Style' : 'Create Writing Style'}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Error Message */}
          {error && (
            <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <p className="text-red-800 dark:text-red-200">{error}</p>
            </div>
          )}

          {/* Suggested Presets */}
          {!preset && (
            <div className="bg-blue-50 dark:bg-blue-950 rounded-lg p-4">
              <button
                type="button"
                onClick={() => setShowSuggested(!showSuggested)}
                className="w-full flex items-center justify-between text-left"
              >
                <span className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                  Start from a template
                </span>
                <svg
                  className={`w-5 h-5 text-blue-600 dark:text-blue-400 transition-transform ${showSuggested ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {showSuggested && (
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-2">
                  {SUGGESTED_PRESETS.map((suggested) => (
                    <button
                      key={suggested.name}
                      type="button"
                      onClick={() => loadSuggestedPreset(suggested)}
                      className="text-left p-3 bg-white dark:bg-gray-800 rounded border border-blue-200 dark:border-blue-800 hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
                    >
                      <p className="font-medium text-gray-900 dark:text-white">{suggested.name}</p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{suggested.description}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Preset Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
              placeholder="e.g., Epic Fantasy, Cozy Romance"
              required
              maxLength={100}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Description
            </label>
            <input
              type="text"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
              placeholder="Brief description of this writing style"
              maxLength={200}
            />
          </div>

          {/* Prompt Construction Info */}
          <div className="bg-blue-50 dark:bg-blue-950 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
            <button
              type="button"
              onClick={() => setShowPromptInfo(!showPromptInfo)}
              className="w-full flex items-center justify-between text-left"
            >
              <span className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                ℹ️ How prompts are constructed
              </span>
              <svg
                className={`w-5 h-5 text-blue-600 dark:text-blue-400 transition-transform ${showPromptInfo ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showPromptInfo && (
              <div className="mt-4 text-sm text-blue-900 dark:text-blue-100 space-y-2">
                <p className="font-medium">Your writing style prompt is combined with technical requirements:</p>
                <div className="bg-white dark:bg-gray-800 rounded p-3 space-y-1 text-xs">
                  <div className="flex items-start gap-2">
                    <span className="font-semibold text-green-600 dark:text-green-400">✓ Your Style:</span>
                    <span>The writing style prompt you define below (tone, pacing, character development, etc.)</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-semibold text-blue-600 dark:text-blue-400">+ POV:</span>
                    <span>Point of view selection (First/Second/Third person) - see below</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-semibold text-purple-600 dark:text-purple-400">+ Formatting Rules:</span>
                    <span>Automatically added from system defaults (dialogue format, structure, etc.)</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-semibold text-orange-600 dark:text-orange-400">+ Choices Rules:</span>
                    <span>Automatically added from system defaults (JSON format, marker placement, etc.)</span>
                  </div>
                </div>
                <p className="text-xs italic">You only need to customize the writing style - technical requirements are handled automatically.</p>
              </div>
            )}
          </div>

          {/* Point of View Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Point of View
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
              Choose the narrative perspective for your stories
            </p>
            <div className="grid grid-cols-3 gap-3">
              <button
                type="button"
                onClick={() => setFormData({ ...formData, pov: 'first' })}
                className={`px-4 py-3 rounded-lg border-2 transition-colors ${
                  formData.pov === 'first'
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-400'
                }`}
              >
                <div className="font-semibold">First Person</div>
                <div className="text-xs mt-1">I, me, my</div>
              </button>
              <button
                type="button"
                onClick={() => setFormData({ ...formData, pov: 'second' })}
                className={`px-4 py-3 rounded-lg border-2 transition-colors ${
                  formData.pov === 'second'
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-400'
                }`}
              >
                <div className="font-semibold">Second Person</div>
                <div className="text-xs mt-1">You, your</div>
              </button>
              <button
                type="button"
                onClick={() => setFormData({ ...formData, pov: 'third' })}
                className={`px-4 py-3 rounded-lg border-2 transition-colors ${
                  formData.pov === 'third'
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-400'
                }`}
              >
                <div className="font-semibold">Third Person</div>
                <div className="text-xs mt-1">He, she, they</div>
              </button>
            </div>
          </div>

          {/* Prose Style Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Prose Style
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
              Choose how the AI structures its writing. Click any style to see an example.
            </p>
            {loadingProseStyles ? (
              <div className="flex items-center justify-center py-8 text-gray-500 dark:text-gray-400">
                <svg className="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Loading prose styles...
              </div>
            ) : proseStyles.length === 0 ? (
              <div className="text-gray-500 dark:text-gray-400 text-sm py-4">
                No prose styles available. Check backend configuration.
              </div>
            ) : (
            <div className="space-y-2">
              {proseStyles.map((style) => (
                <div
                  key={style.key}
                  className={`rounded-lg border-2 transition-all ${
                    formData.prose_style === style.key
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {/* Style Header - Clickable to select */}
                  <div className="flex items-center gap-3 p-3">
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, prose_style: style.key })}
                      className="flex-1 text-left"
                    >
                      <div className="flex items-center gap-2">
                        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                          formData.prose_style === style.key
                            ? 'border-blue-500 bg-blue-500'
                            : 'border-gray-400 dark:border-gray-500'
                        }`}>
                          {formData.prose_style === style.key && (
                            <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          )}
                        </div>
                        <span className={`font-medium ${
                          formData.prose_style === style.key
                            ? 'text-blue-700 dark:text-blue-300'
                            : 'text-gray-900 dark:text-white'
                        }`}>
                          {style.name}
                        </span>
                      </div>
                      <p className={`text-xs mt-1 ml-6 ${
                        formData.prose_style === style.key
                          ? 'text-blue-600 dark:text-blue-400'
                          : 'text-gray-500 dark:text-gray-400'
                      }`}>
                        {style.description}
                      </p>
                    </button>
                    
                    {/* Toggle Example Button */}
                    <button
                      type="button"
                      onClick={() => toggleProseStyleExample(style.key)}
                      className={`px-2 py-1 text-xs rounded transition-colors ${
                        expandedProseStyle === style.key
                          ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                      }`}
                    >
                      {expandedProseStyle === style.key ? 'Hide' : 'Example'}
                    </button>
                  </div>
                  
                  {/* Expandable Example */}
                  {expandedProseStyle === style.key && (
                    <div className="px-3 pb-3">
                      <div className="bg-gray-100 dark:bg-gray-900 rounded-lg p-3 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-serif italic border border-gray-200 dark:border-gray-700">
                        {style.example}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            )}
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Writing Style Prompt *
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
              This controls how the AI writes your stories (tone, pacing, character development, etc.). Formatting and choices requirements are automatically added.
            </p>
            <textarea
              value={formData.system_prompt}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white font-mono text-sm"
              rows={12}
              placeholder="You are a creative storytelling assistant..."
              required
            />
          </div>

          {/* Summary System Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Custom Summary Style (Optional)
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
              Override how story summaries are written. Leave blank to use the main writing style.
            </p>
            <textarea
              value={formData.summary_system_prompt}
              onChange={(e) => setFormData({ ...formData, summary_system_prompt: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white font-mono text-sm"
              rows={6}
              placeholder="You are a skilled story analyst..."
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 font-medium transition-colors"
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : preset ? 'Update Preset' : 'Create Preset'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

