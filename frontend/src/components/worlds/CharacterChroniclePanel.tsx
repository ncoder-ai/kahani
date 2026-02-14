'use client';

import { useState, useEffect, useCallback } from 'react';
import { Trash2, Star, Check, X, RefreshCw, Pencil } from 'lucide-react';
import { WorldsApi } from '@/lib/api/worlds';

const worldsApi = new WorldsApi();
import type { ChronicleEntry, CharacterSnapshotData, WorldStory } from '@/lib/api/types';

const ENTRY_TYPE_OPTIONS = [
  'personality_shift', 'knowledge_gained', 'secret', 'relationship_change',
  'trauma', 'physical_change', 'skill_gained', 'goal_change', 'other',
];

const ENTRY_TYPE_COLORS: Record<string, string> = {
  personality_shift: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  knowledge_gained: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  secret: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  relationship_change: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
  trauma: 'bg-red-500/20 text-red-300 border-red-500/30',
  physical_change: 'bg-green-500/20 text-green-300 border-green-500/30',
  skill_gained: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  goal_change: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  other: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
};

function formatEntryType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

interface CharacterChroniclePanelProps {
  worldId: number;
  characterId: number;
  characterName: string;
  stories?: WorldStory[];
}

export default function CharacterChroniclePanel({ worldId, characterId, characterName, stories = [] }: CharacterChroniclePanelProps) {
  const [entries, setEntries] = useState<ChronicleEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDescription, setEditDescription] = useState('');
  const [editEntryType, setEditEntryType] = useState('');
  const [saving, setSaving] = useState(false);

  // Snapshot state
  const [snapshot, setSnapshot] = useState<CharacterSnapshotData | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [selectedStoryId, setSelectedStoryId] = useState<number | ''>('');
  const [selectedBranchId, setSelectedBranchId] = useState<number | ''>('');
  const [editingSnapshot, setEditingSnapshot] = useState(false);
  const [editSnapshotText, setEditSnapshotText] = useState('');
  const [savingSnapshot, setSavingSnapshot] = useState(false);

  const loadEntries = useCallback(async () => {
    try {
      setLoading(true);
      const data = await worldsApi.getCharacterChronicle(worldId, characterId);
      setEntries(data);
    } catch (err) {
      console.error('Failed to load chronicle entries:', err);
    } finally {
      setLoading(false);
    }
  }, [worldId, characterId]);

  const loadSnapshot = useCallback(async (branchId?: number) => {
    try {
      setSnapshotLoading(true);
      const data = await worldsApi.getCharacterSnapshot(worldId, characterId, branchId);
      setSnapshot(data);
    } catch (err) {
      console.error('Failed to load snapshot:', err);
    } finally {
      setSnapshotLoading(false);
    }
  }, [worldId, characterId]);

  useEffect(() => {
    loadEntries();
    loadSnapshot();
  }, [loadEntries, loadSnapshot]);

  // Reload snapshot when branch selection changes
  useEffect(() => {
    if (selectedBranchId !== '') {
      loadSnapshot(Number(selectedBranchId));
    }
  }, [selectedBranchId, loadSnapshot]);

  // Auto-select first story in dropdown
  useEffect(() => {
    if (stories.length > 0 && selectedStoryId === '') {
      // Default to the last story in timeline order (or first available)
      const sorted = [...stories].sort((a, b) => (a.timeline_order ?? 999) - (b.timeline_order ?? 999));
      setSelectedStoryId(sorted[sorted.length - 1].id);
    }
  }, [stories, selectedStoryId]);

  // Auto-select main branch when story changes
  const selectedStory = stories.find(s => s.id === selectedStoryId);
  const storyBranches = selectedStory?.branches || [];
  const showBranchSelector = storyBranches.length > 1;

  useEffect(() => {
    if (!selectedStoryId) {
      setSelectedBranchId('');
      return;
    }
    const story = stories.find(s => s.id === selectedStoryId);
    const branches = story?.branches || [];
    if (branches.length > 1) {
      const main = branches.find(b => b.is_main);
      setSelectedBranchId(main ? main.id : branches[0].id);
    } else {
      setSelectedBranchId('');
    }
  }, [selectedStoryId, stories]);

  const startEdit = (entry: ChronicleEntry) => {
    setEditingId(entry.id);
    setEditDescription(entry.description);
    setEditEntryType(entry.entry_type);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditDescription('');
    setEditEntryType('');
  };

  const saveEdit = async (entryId: number) => {
    setSaving(true);
    try {
      const original = entries.find(e => e.id === entryId);
      const updates: Record<string, string> = {};
      if (editDescription !== original?.description) updates.description = editDescription;
      if (editEntryType !== original?.entry_type) updates.entry_type = editEntryType;
      if (Object.keys(updates).length > 0) {
        await worldsApi.updateChronicleEntry(entryId, updates);
      }
      setEditingId(null);
      await loadEntries();
    } catch (err) {
      console.error('Failed to save chronicle entry:', err);
      alert('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const toggleDefining = async (entry: ChronicleEntry) => {
    try {
      await worldsApi.updateChronicleEntry(entry.id, { is_defining: !entry.is_defining });
      await loadEntries();
    } catch (err) {
      console.error('Failed to toggle defining:', err);
    }
  };

  const deleteEntry = async (entryId: number) => {
    if (!confirm('Delete this chronicle entry? This cannot be undone.')) return;
    try {
      await worldsApi.deleteChronicleEntry(entryId);
      await loadEntries();
    } catch (err) {
      console.error('Failed to delete chronicle entry:', err);
    }
  };

  const generateSnapshot = async () => {
    if (!selectedStoryId) return;
    setGenerating(true);
    try {
      const branchId = selectedBranchId ? Number(selectedBranchId) : undefined;
      const result = await worldsApi.generateCharacterSnapshot(worldId, characterId, Number(selectedStoryId), branchId);
      setSnapshot({ ...result, current_entry_count: result.chronicle_entry_count, is_stale: false });
    } catch (err) {
      console.error('Failed to generate snapshot:', err);
      alert('Failed to generate snapshot. Check that the character has chronicle entries.');
    } finally {
      setGenerating(false);
    }
  };

  const startEditSnapshot = () => {
    setEditingSnapshot(true);
    setEditSnapshotText(snapshot?.snapshot_text || '');
  };

  const saveSnapshotEdit = async () => {
    setSavingSnapshot(true);
    try {
      const branchId = snapshot?.branch_id ?? undefined;
      const result = await worldsApi.updateCharacterSnapshot(worldId, characterId, editSnapshotText, branchId);
      setSnapshot((prev) => prev ? { ...prev, snapshot_text: result.snapshot_text, updated_at: result.updated_at } : prev);
      setEditingSnapshot(false);
    } catch (err) {
      console.error('Failed to save snapshot:', err);
      alert('Failed to save snapshot.');
    } finally {
      setSavingSnapshot(false);
    }
  };

  if (loading) {
    return (
      <div className="py-6 text-center">
        <div className="w-6 h-6 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto"></div>
      </div>
    );
  }

  const storyName = (id: number | undefined) => {
    if (!id) return 'Unknown';
    const s = stories.find((s) => s.id === id);
    return s?.title || `Story #${id}`;
  };

  return (
    <div className="space-y-4">
      {/* Snapshot section */}
      <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-indigo-300 text-sm font-medium">Character Snapshot</h4>
          {snapshot?.is_stale && (
            <span className="text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded">
              Stale
            </span>
          )}
        </div>

        {snapshotLoading ? (
          <div className="py-3 text-center">
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto"></div>
          </div>
        ) : snapshot?.snapshot_text ? (
          <div>
            {editingSnapshot ? (
              <div className="space-y-2">
                <textarea
                  value={editSnapshotText}
                  onChange={(e) => setEditSnapshotText(e.target.value)}
                  rows={5}
                  className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-400 resize-none"
                  autoFocus
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={saveSnapshotEdit}
                    disabled={savingSnapshot}
                    className="px-3 py-1 bg-green-600 hover:bg-green-500 disabled:bg-green-600/50 text-white text-xs rounded transition-colors"
                  >
                    {savingSnapshot ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    onClick={() => setEditingSnapshot(false)}
                    className="px-3 py-1 bg-white/10 hover:bg-white/20 text-white/70 text-xs rounded transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-white/80 text-sm leading-relaxed">{snapshot.snapshot_text}</p>
                <div className="flex items-center justify-between mt-3">
                  <span className="text-white/30 text-xs">
                    As of: {storyName(snapshot.up_to_story_id)}{snapshot.branch_id ? (() => {
                      const story = stories.find(s => s.branches?.some(b => b.id === snapshot.branch_id));
                      const branch = story?.branches?.find(b => b.id === snapshot.branch_id);
                      return branch ? ` [${branch.name}]` : '';
                    })() : ''} ({snapshot.chronicle_entry_count} entries)
                  </span>
                  <button
                    onClick={startEditSnapshot}
                    className="text-white/30 hover:text-white/60 transition-colors"
                    title="Edit snapshot"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-white/40 text-sm">No snapshot generated yet.</p>
        )}

        {/* Generate controls */}
        {!editingSnapshot && (
          <div className="flex items-center gap-2 mt-3 pt-3 border-t border-indigo-500/10">
            <span className="text-white/40 text-xs">Generate as of:</span>
            <select
              value={selectedStoryId}
              onChange={(e) => setSelectedStoryId(e.target.value ? Number(e.target.value) : '')}
              className="bg-white/10 border border-white/20 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-400 flex-1 max-w-[200px]"
            >
              <option value="" className="bg-gray-800">Select story...</option>
              {[...stories]
                .sort((a, b) => (a.timeline_order ?? 999) - (b.timeline_order ?? 999))
                .map((s) => (
                  <option key={s.id} value={s.id} className="bg-gray-800">
                    {s.timeline_order != null ? `#${s.timeline_order} ` : ''}{s.title}
                  </option>
                ))}
            </select>
            {showBranchSelector && (
              <select
                value={selectedBranchId}
                onChange={(e) => setSelectedBranchId(e.target.value ? Number(e.target.value) : '')}
                className="bg-white/10 border border-white/20 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-400 max-w-[140px]"
              >
                {storyBranches.map((b) => (
                  <option key={b.id} value={b.id} className="bg-gray-800">
                    {b.name}{b.is_main ? ' (main)' : ''}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={generateSnapshot}
              disabled={generating || !selectedStoryId}
              className="flex items-center gap-1 px-3 py-1 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-600/50 disabled:cursor-not-allowed text-white text-xs rounded transition-colors"
            >
              <RefreshCw className={`w-3 h-3 ${generating ? 'animate-spin' : ''}`} />
              {generating ? 'Generating...' : snapshot?.snapshot_text ? 'Regenerate' : 'Generate'}
            </button>
          </div>
        )}
      </div>

      {/* Chronicle entries */}
      {entries.length === 0 ? (
        <div className="py-4 text-center text-white/50 text-sm">
          No chronicle entries for {characterName} yet.
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => {
            const isEditing = editingId === entry.id;
            const colorClass = ENTRY_TYPE_COLORS[entry.entry_type] || ENTRY_TYPE_COLORS.other;

            return (
              <div
                key={entry.id}
                className="bg-white/5 border border-white/10 rounded-lg p-4 group hover:border-white/20 transition-colors"
              >
                <div className="flex items-start gap-3">
                  {/* Defining star */}
                  <button
                    onClick={() => toggleDefining(entry)}
                    className={`mt-0.5 flex-shrink-0 transition-colors ${
                      entry.is_defining ? 'text-yellow-400' : 'text-white/20 hover:text-yellow-400/60'
                    }`}
                    title={entry.is_defining ? 'Defining entry (click to unmark)' : 'Mark as defining'}
                  >
                    <Star className="w-4 h-4" fill={entry.is_defining ? 'currentColor' : 'none'} />
                  </button>

                  <div className="flex-1 min-w-0">
                    {/* Entry type badge */}
                    <div className="flex items-center gap-2 mb-2">
                      {isEditing ? (
                        <select
                          value={editEntryType}
                          onChange={(e) => setEditEntryType(e.target.value)}
                          className="bg-white/10 border border-white/20 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-400"
                        >
                          {ENTRY_TYPE_OPTIONS.map(t => (
                            <option key={t} value={t} className="bg-gray-800">{formatEntryType(t)}</option>
                          ))}
                        </select>
                      ) : (
                        <span className={`text-xs px-2 py-0.5 rounded border ${colorClass}`}>
                          {formatEntryType(entry.entry_type)}
                        </span>
                      )}
                      {entry.scene_id && (
                        <span className="text-xs text-white/30">Scene #{entry.scene_id}</span>
                      )}
                    </div>

                    {/* Description */}
                    {isEditing ? (
                      <textarea
                        value={editDescription}
                        onChange={(e) => setEditDescription(e.target.value)}
                        rows={3}
                        className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-400 resize-none"
                        autoFocus
                      />
                    ) : (
                      <p
                        className="text-white/80 text-sm cursor-pointer hover:text-white transition-colors"
                        onClick={() => startEdit(entry)}
                        title="Click to edit"
                      >
                        {entry.description}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {isEditing ? (
                      <>
                        <button
                          onClick={() => saveEdit(entry.id)}
                          disabled={saving}
                          className="p-1.5 text-green-400 hover:bg-green-500/20 rounded transition-colors"
                          title="Save"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="p-1.5 text-white/40 hover:bg-white/10 rounded transition-colors"
                          title="Cancel"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => deleteEntry(entry.id)}
                        className="p-1.5 text-white/20 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all rounded"
                        title="Delete entry"
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
  );
}
