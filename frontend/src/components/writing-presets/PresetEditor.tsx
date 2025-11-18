'use client';

import React, { useState, useEffect } from 'react';
import { WritingStylePreset, WritingPresetCreateData, WritingPresetUpdateData, SUGGESTED_PRESETS } from '@/types/writing-presets';

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
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuggested, setShowSuggested] = useState(false);

  useEffect(() => {
    if (preset) {
      setFormData({
        name: preset.name,
        description: preset.description || '',
        system_prompt: preset.system_prompt,
        summary_system_prompt: preset.summary_system_prompt || '',
      });
    } else {
      // New preset - start with default template
      setFormData({
        name: '',
        description: '',
        system_prompt: SUGGESTED_PRESETS[0].system_prompt,
        summary_system_prompt: '',
      });
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

          {/* System Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Writing Style Prompt *
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
              This controls how the AI writes ALL your stories (scenes, dialogue, descriptions, etc.)
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

