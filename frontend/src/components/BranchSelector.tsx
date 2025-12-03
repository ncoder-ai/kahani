'use client';

import React, { useState, useEffect, useRef } from 'react';
import { GitBranch, ChevronDown, Plus, Check, Trash2, Edit2, X, GitFork } from 'lucide-react';
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

interface BranchSelectorProps {
  storyId: number;
  currentBranchId?: number;
  currentSceneSequence?: number;
  onBranchChange: (branchId: number) => void;
  onBranchCreated?: (branch: Branch) => void;
  className?: string;
}

export default function BranchSelector({
  storyId,
  currentBranchId,
  currentSceneSequence = 1,
  onBranchChange,
  onBranchCreated,
  className = '',
}: BranchSelectorProps) {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [activeBranchId, setActiveBranchId] = useState<number | null>(currentBranchId || null);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [newBranchDescription, setNewBranchDescription] = useState('');
  const [forkFromSequence, setForkFromSequence] = useState(currentSceneSequence);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Load branches on mount
  useEffect(() => {
    loadBranches();
  }, [storyId]);

  // Update fork sequence when current scene changes
  useEffect(() => {
    setForkFromSequence(currentSceneSequence);
  }, [currentSceneSequence]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const loadBranches = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.getBranches(storyId);
      setBranches(response.branches);
      if (response.active_branch_id) {
        setActiveBranchId(response.active_branch_id);
      }
    } catch (err) {
      console.error('Failed to load branches:', err);
      setError('Failed to load branches');
    } finally {
      setIsLoading(false);
    }
  };

  const handleBranchSelect = async (branchId: number) => {
    if (branchId === activeBranchId) {
      setIsOpen(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await apiClient.activateBranch(storyId, branchId);
      setActiveBranchId(branchId);
      onBranchChange(branchId);
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to switch branch:', err);
      setError('Failed to switch branch');
    } finally {
      setIsLoading(false);
    }
  };

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

      setBranches(prev => [...prev, response.branch]);
      setActiveBranchId(response.branch.id);
      onBranchChange(response.branch.id);
      if (onBranchCreated) {
        onBranchCreated(response.branch);
      }

      // Reset form
      setNewBranchName('');
      setNewBranchDescription('');
      setShowCreateModal(false);
    } catch (err) {
      console.error('Failed to create branch:', err);
      setError('Failed to create branch');
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteBranch = async (branchId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    
    const branch = branches.find(b => b.id === branchId);
    if (!branch || branch.is_main) return;

    if (!confirm(`Are you sure you want to delete branch "${branch.name}"? This action cannot be undone.`)) {
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await apiClient.deleteBranch(storyId, branchId);
      setBranches(prev => prev.filter(b => b.id !== branchId));
      
      // If we deleted the active branch, switch to main
      if (branchId === activeBranchId) {
        const mainBranch = branches.find(b => b.is_main);
        if (mainBranch) {
          await handleBranchSelect(mainBranch.id);
        }
      }
    } catch (err) {
      console.error('Failed to delete branch:', err);
      setError('Failed to delete branch');
    } finally {
      setIsLoading(false);
    }
  };

  const activeBranch = branches.find(b => b.id === activeBranchId);

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Branch selector button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="flex items-center gap-2 px-3 py-2 bg-slate-800/50 hover:bg-slate-700/50 border border-slate-600/50 rounded-lg transition-colors text-sm"
      >
        <GitBranch className="w-4 h-4 text-emerald-400" />
        <span className="text-slate-200 max-w-[150px] truncate">
          {activeBranch?.name || 'Select Branch'}
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-slate-800 border border-slate-600/50 rounded-lg shadow-xl z-50 overflow-hidden">
          {/* Branch list */}
          <div className="max-h-64 overflow-y-auto">
            {branches.length === 0 ? (
              <div className="p-4 text-center text-slate-400 text-sm">
                No branches found
              </div>
            ) : (
              branches.map(branch => (
                <div
                  key={branch.id}
                  onClick={() => handleBranchSelect(branch.id)}
                  className={`flex items-center justify-between px-3 py-2 cursor-pointer transition-colors ${
                    branch.id === activeBranchId
                      ? 'bg-emerald-600/20 border-l-2 border-emerald-500'
                      : 'hover:bg-slate-700/50'
                  }`}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {branch.is_main ? (
                      <GitBranch className="w-4 h-4 text-amber-400 flex-shrink-0" />
                    ) : (
                      <GitFork className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1">
                        <span className="text-slate-200 truncate">{branch.name}</span>
                        {branch.is_main && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded">
                            main
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {branch.scene_count} scenes • {branch.chapter_count} chapters
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {branch.id === activeBranchId && (
                      <Check className="w-4 h-4 text-emerald-400" />
                    )}
                    {!branch.is_main && (
                      <button
                        onClick={(e) => handleDeleteBranch(branch.id, e)}
                        className="p-1 hover:bg-red-500/20 rounded text-slate-400 hover:text-red-400"
                        title="Delete branch"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Create new branch button */}
          <div className="border-t border-slate-600/50 p-2">
            <button
              onClick={() => {
                setShowCreateModal(true);
                setIsOpen(false);
              }}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Create New Branch</span>
            </button>
          </div>
        </div>
      )}

      {/* Create branch modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 border border-slate-600/50 rounded-xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-4 border-b border-slate-600/50">
              <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                <GitFork className="w-5 h-5 text-emerald-400" />
                Create New Branch
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="p-1 hover:bg-slate-700 rounded"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>

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
                    (current: {currentSceneSequence})
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  The new branch will include all scenes up to and including this scene.
                </p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 p-4 border-t border-slate-600/50">
              <button
                onClick={() => setShowCreateModal(false)}
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
      )}
    </div>
  );
}

