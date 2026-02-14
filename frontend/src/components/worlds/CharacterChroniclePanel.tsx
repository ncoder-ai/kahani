'use client';

import { useState, useEffect, useCallback } from 'react';
import { Trash2, Star, Check, X } from 'lucide-react';
import { WorldsApi } from '@/lib/api/worlds';

const worldsApi = new WorldsApi();
import type { ChronicleEntry } from '@/lib/api/types';

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
}

export default function CharacterChroniclePanel({ worldId, characterId, characterName }: CharacterChroniclePanelProps) {
  const [entries, setEntries] = useState<ChronicleEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDescription, setEditDescription] = useState('');
  const [editEntryType, setEditEntryType] = useState('');
  const [saving, setSaving] = useState(false);

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

  useEffect(() => { loadEntries(); }, [loadEntries]);

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

  if (loading) {
    return (
      <div className="py-6 text-center">
        <div className="w-6 h-6 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto"></div>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="py-6 text-center text-white/50 text-sm">
        No chronicle entries for {characterName} yet.
      </div>
    );
  }

  return (
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
  );
}
