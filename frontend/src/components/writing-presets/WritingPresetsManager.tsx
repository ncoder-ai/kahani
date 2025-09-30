'use client';

import React, { useState, useEffect } from 'react';
import api from '@/lib/api';
import { WritingStylePreset, WritingPresetCreateData, WritingPresetUpdateData } from '@/types/writing-presets';
import PresetCard from './PresetCard';
import PresetEditor from './PresetEditor';

export default function WritingPresetsManager() {
  const [presets, setPresets] = useState<WritingStylePreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<WritingStylePreset | undefined>(undefined);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<WritingStylePreset | null>(null);

  useEffect(() => {
    loadPresets();
  }, []);

  const loadPresets = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listWritingPresets();
      setPresets(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load presets');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateNew = () => {
    setSelectedPreset(undefined);
    setIsEditorOpen(true);
  };

  const handleEdit = (preset: WritingStylePreset) => {
    setSelectedPreset(preset);
    setIsEditorOpen(true);
  };

  const handleSave = async (data: WritingPresetCreateData | WritingPresetUpdateData) => {
    if (selectedPreset) {
      // Update existing
      await api.updateWritingPreset(selectedPreset.id, data as WritingPresetUpdateData);
    } else {
      // Create new
      await api.createWritingPreset(data as WritingPresetCreateData);
    }
    await loadPresets();
  };

  const handleActivate = async (preset: WritingStylePreset) => {
    try {
      await api.activateWritingPreset(preset.id);
      await loadPresets();
    } catch (err: any) {
      alert(err.message || 'Failed to activate preset');
    }
  };

  const handleDuplicate = async (preset: WritingStylePreset) => {
    try {
      await api.duplicateWritingPreset(preset.id);
      await loadPresets();
    } catch (err: any) {
      alert(err.message || 'Failed to duplicate preset');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;

    try {
      await api.deleteWritingPreset(deleteConfirm.id);
      await loadPresets();
      setDeleteConfirm(null);
    } catch (err: any) {
      alert(err.message || 'Failed to delete preset');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg p-6">
        <p className="text-red-800 dark:text-red-200">{error}</p>
        <button
          onClick={loadPresets}
          className="mt-4 text-sm text-red-600 dark:text-red-400 hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  const activePreset = presets.find(p => p.is_active);
  const inactivePresets = presets.filter(p => !p.is_active);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            Writing Styles
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Customize how the AI writes your stories - tone, style, vocabulary, and more
          </p>
        </div>
        <button
          onClick={handleCreateNew}
          className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create New Style
        </button>
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex">
          <svg className="w-5 h-5 text-blue-500 mr-3 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          <div className="text-sm text-blue-900 dark:text-blue-100">
            <p className="font-semibold mb-1">What are Writing Styles?</p>
            <p>Writing styles control <strong>how</strong> the AI writes - the tone, vocabulary, pacing, and overall "voice" of your stories. The active style applies to all new story generations.</p>
          </div>
        </div>
      </div>

      {/* Active Preset */}
      {activePreset && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center">
            <span className="w-2 h-2 bg-blue-500 rounded-full mr-2"></span>
            Active Style
          </h3>
          <PresetCard
            preset={activePreset}
            onActivate={handleActivate}
            onEdit={handleEdit}
            onDuplicate={handleDuplicate}
            onDelete={setDeleteConfirm}
          />
        </div>
      )}

      {/* Inactive Presets */}
      {inactivePresets.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            Other Styles ({inactivePresets.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {inactivePresets.map((preset) => (
              <PresetCard
                key={preset.id}
                preset={preset}
                onActivate={handleActivate}
                onEdit={handleEdit}
                onDuplicate={handleDuplicate}
                onDelete={setDeleteConfirm}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {presets.length === 0 && (
        <div className="text-center py-12">
          <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-gray-600 dark:text-gray-400 mb-4">No writing styles yet</p>
          <button
            onClick={handleCreateNew}
            className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-medium transition-colors"
          >
            Create Your First Style
          </button>
        </div>
      )}

      {/* Editor Modal */}
      <PresetEditor
        preset={selectedPreset}
        isOpen={isEditorOpen}
        onClose={() => setIsEditorOpen(false)}
        onSave={handleSave}
      />

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-md w-full p-6">
            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              Delete Writing Style?
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to delete <strong>{deleteConfirm.name}</strong>? This action cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="flex-1 px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg font-medium transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

