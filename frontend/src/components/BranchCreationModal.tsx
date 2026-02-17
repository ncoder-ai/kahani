'use client';

import React, { useState } from 'react';
import { GitFork, Plus, X } from 'lucide-react';
import apiClient from '@/lib/api';

interface Branch {
  id: number;
  story_id: number;
  name: string;
  description: string | null;
  is_main: boolean;
  is_active: boolean;
  forked_from_branch_id: number | null;
  forked_at_scene_sequence: number | null;
  scene_count: number;
  chapter_count: number;
  created_at: string;
}

interface BranchCreationModalProps {
  storyId: number;
  currentSceneSequence: number;
  preselectedScene?: number;
  onClose: () => void;
  onBranchCreated: (branch: Branch) => void;
}

export default function BranchCreationModal({
  storyId,
  currentSceneSequence,
  preselectedScene,
  onClose,
  onBranchCreated,
}: BranchCreationModalProps) {
  const [newBranchName, setNewBranchName] = useState('');
  const [newBranchDescription, setNewBranchDescription] = useState('');
  const [forkFromSequence, setForkFromSequence] = useState(preselectedScene || currentSceneSequence);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreateBranch = async () => {
    if (!newBranchName.trim()) {
      setError('Branch name is required');
      return;
    }

    setIsCreating(true);
    setError(null);
    try {
      const response = await apiClient.createBranch(storyId, {
        name: newBranchName.trim(),
        description: newBranchDescription.trim() || undefined,
        fork_from_scene_sequence: forkFromSequence,
        activate: true,
      });

      onBranchCreated(response.branch);
    } catch (err) {
      console.error('Failed to create branch:', err);
      setError('Failed to create branch');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-600/50 rounded-xl shadow-2xl w-full max-w-md">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-600/50">
          <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
            <GitFork className="w-5 h-5 text-emerald-400" />
            Create New Branch
          </h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-700 rounded"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Branch Name *
            </label>
            <input
              type="text"
              value={newBranchName}
              onChange={(e) => setNewBranchName(e.target.value)}
              placeholder="e.g., Alternative Ending"
              className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600/50 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Description (optional)
            </label>
            <textarea
              value={newBranchDescription}
              onChange={(e) => setNewBranchDescription(e.target.value)}
              placeholder="Describe what this branch explores..."
              rows={2}
              className="w-full px-3 py-2 bg-slate-900/50 border border-slate-600/50 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Fork from Scene
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                max={currentSceneSequence}
                value={forkFromSequence}
                onChange={(e) => setForkFromSequence(parseInt(e.target.value) || 1)}
                className="w-24 px-3 py-2 bg-slate-900/50 border border-slate-600/50 rounded-lg text-slate-200 focus:outline-none focus:border-emerald-500"
              />
              <span className="text-sm text-slate-400">
                (max: {currentSceneSequence})
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              The new branch will include all scenes up to and including this scene.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-slate-600/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleCreateBranch}
            disabled={isCreating || !newBranchName.trim()}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors flex items-center gap-2"
          >
            {isCreating ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Create Branch
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

