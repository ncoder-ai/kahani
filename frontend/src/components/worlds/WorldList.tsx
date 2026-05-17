'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import type { World } from '@/lib/api/types';

interface WorldListProps {
  worlds: World[];
  onSelectWorld: (world: World) => void;
  onCreateWorld: (name: string, description?: string) => Promise<void>;
  onDeleteWorld: (worldId: number) => Promise<void>;
}

export default function WorldList({ worlds, onSelectWorld, onCreateWorld, onDeleteWorld }: WorldListProps) {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setIsCreating(true);
    try {
      await onCreateWorld(createName.trim(), createDescription.trim() || undefined);
      setCreateName('');
      setCreateDescription('');
      setShowCreateForm(false);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, worldId: number, worldName: string, storyCount: number) => {
    e.stopPropagation();
    if (storyCount > 0) {
      alert(`Cannot delete "${worldName}" because it has ${storyCount} stories. Move or delete stories first.`);
      return;
    }
    if (!confirm(`Delete world "${worldName}"? This cannot be undone.`)) return;
    await onDeleteWorld(worldId);
  };

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {worlds.map((world) => (
          <div
            key={world.id}
            onClick={() => onSelectWorld(world)}
            className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-6 cursor-pointer hover:bg-white/15 hover:scale-105 transition-all duration-200 group"
          >
            <div className="flex justify-between items-start mb-3">
              <h4 className="text-xl font-bold text-white group-hover:text-gray-200 transition-colors">
                {world.name}
              </h4>
              <button
                onClick={(e) => handleDelete(e, world.id, world.name, world.story_count)}
                className="opacity-0 group-hover:opacity-100 text-white/40 hover:text-red-400 transition-all p-1"
                title="Delete world"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {world.description && (
              <p className="text-white/70 text-sm mb-4 line-clamp-2">{world.description}</p>
            )}
            <div className="flex items-center justify-between pt-3 border-t border-white/10">
              <span className="text-white/60 text-sm">
                {world.story_count} {world.story_count === 1 ? 'story' : 'stories'}
              </span>
              <span className="text-white/40 text-xs">
                {new Date(world.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        ))}

        {/* Create World Card */}
        {!showCreateForm ? (
          <div
            onClick={() => setShowCreateForm(true)}
            className="bg-white/5 border-2 border-dashed border-white/30 rounded-2xl p-6 cursor-pointer hover:bg-white/10 hover:border-white/50 transition-all duration-200 flex flex-col items-center justify-center text-center min-h-[180px] group"
          >
            <div className="text-3xl mb-3 group-hover:scale-110 transition-transform">+</div>
            <h4 className="text-lg font-semibold text-white mb-1">Create World</h4>
            <p className="text-white/60 text-sm">Start a new shared universe</p>
          </div>
        ) : (
          <div className="bg-white/10 backdrop-blur-md border border-indigo-500/40 rounded-2xl p-6">
            <h4 className="text-lg font-semibold text-white mb-4">New World</h4>
            <input
              type="text"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="World name"
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-white/40 mb-3 focus:outline-none focus:border-indigo-400"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />
            <textarea
              value={createDescription}
              onChange={(e) => setCreateDescription(e.target.value)}
              placeholder="Description (optional)"
              rows={2}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white placeholder-white/40 mb-4 focus:outline-none focus:border-indigo-400 resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={!createName.trim() || isCreating}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                {isCreating ? 'Creating...' : 'Create'}
              </button>
              <button
                onClick={() => { setShowCreateForm(false); setCreateName(''); setCreateDescription(''); }}
                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
