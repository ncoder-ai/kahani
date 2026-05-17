'use client';

import { useState, useEffect, useCallback } from 'react';
import { Trash2, Check, X } from 'lucide-react';
import { WorldsApi } from '@/lib/api/worlds';

const worldsApi = new WorldsApi();
import type { LorebookEntry } from '@/lib/api/types';

interface LocationLorebookPanelProps {
  worldId: number;
  locationName: string;
}

export default function LocationLorebookPanel({ worldId, locationName }: LocationLorebookPanelProps) {
  const [entries, setEntries] = useState<LorebookEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDescription, setEditDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const loadEntries = useCallback(async () => {
    try {
      setLoading(true);
      const data = await worldsApi.getLocationLorebook(worldId, locationName);
      setEntries(data);
    } catch (err) {
      console.error('Failed to load lorebook entries:', err);
    } finally {
      setLoading(false);
    }
  }, [worldId, locationName]);

  useEffect(() => { loadEntries(); }, [loadEntries]);

  const startEdit = (entry: LorebookEntry) => {
    setEditingId(entry.id);
    setEditDescription(entry.event_description);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditDescription('');
  };

  const saveEdit = async (entryId: number) => {
    setSaving(true);
    try {
      const original = entries.find(e => e.id === entryId);
      if (editDescription !== original?.event_description) {
        await worldsApi.updateLorebookEntry(entryId, { event_description: editDescription });
      }
      setEditingId(null);
      await loadEntries();
    } catch (err) {
      console.error('Failed to save lorebook entry:', err);
      alert('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const deleteEntry = async (entryId: number) => {
    if (!confirm('Delete this lorebook entry? This cannot be undone.')) return;
    try {
      await worldsApi.deleteLorebookEntry(entryId);
      await loadEntries();
    } catch (err) {
      console.error('Failed to delete lorebook entry:', err);
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
        No lorebook entries for {locationName} yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {entries.map((entry) => {
        const isEditing = editingId === entry.id;

        return (
          <div
            key={entry.id}
            className="bg-white/5 border border-white/10 rounded-lg p-4 group hover:border-white/20 transition-colors"
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                {entry.scene_id && (
                  <span className="text-xs text-white/30 mb-1 block">Scene #{entry.scene_id}</span>
                )}

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
                    {entry.event_description}
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
