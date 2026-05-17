'use client';

import { useState, useEffect } from 'react';
import { Loader2, Save } from 'lucide-react';
import { RoleplayApi } from '@/lib/api/roleplay';
import type { RoleplayCharacter } from '@/lib/api/roleplay';

const rpApi = new RoleplayApi();

interface RelationshipData {
  type: string;
  strength: number;
  arc_summary: string;
}

interface Props {
  roleplayId: number;
  characters: RoleplayCharacter[];
}

const RELATIONSHIP_TYPES = [
  'friend', 'rival', 'lover', 'mentor', 'protege',
  'sibling', 'parent', 'colleague', 'enemy', 'stranger',
];

export default function RelationshipPanel({ roleplayId, characters }: Props) {
  const [relationships, setRelationships] = useState<Record<string, Record<string, RelationshipData>>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeChars = characters.filter(c => c.is_active);

  useEffect(() => {
    loadRelationships();
  }, [roleplayId]);

  const loadRelationships = async () => {
    try {
      setIsLoading(true);
      const data = await rpApi.getRelationships(roleplayId);
      setRelationships(data);
    } catch {
      setError('Failed to load relationships');
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdate = async (
    char: RoleplayCharacter,
    targetName: string,
    field: string,
    value: string | number,
  ) => {
    const charName = char.name;
    const current = relationships[charName]?.[targetName] || { type: 'stranger', strength: 0.5, arc_summary: '' };
    const updated = { ...current, [field]: value };

    // Optimistic update
    setRelationships(prev => ({
      ...prev,
      [charName]: { ...(prev[charName] || {}), [targetName]: updated },
    }));

    const saveKey = `${char.story_character_id}-${targetName}`;
    setSaving(saveKey);
    try {
      await rpApi.updateRelationship(roleplayId, char.story_character_id, {
        target_character_name: targetName,
        relationship_type: updated.type,
        strength: updated.strength,
        description: updated.arc_summary,
      });
    } catch {
      setError('Failed to save');
    } finally {
      setSaving(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="w-4 h-4 text-white/30 animate-spin" />
        <span className="text-xs text-white/30 ml-2">Loading relationships...</span>
      </div>
    );
  }

  if (error) {
    return <div className="text-xs text-white/30 py-2 text-center">{error}</div>;
  }

  // Build unique character pairs (only among AI chars + player)
  const pairs: { from: RoleplayCharacter; to: RoleplayCharacter }[] = [];
  for (let i = 0; i < activeChars.length; i++) {
    for (let j = i + 1; j < activeChars.length; j++) {
      pairs.push({ from: activeChars[i], to: activeChars[j] });
    }
  }

  if (pairs.length === 0) {
    return <div className="text-xs text-white/30 py-2 text-center">Need at least 2 characters</div>;
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-white/40 mb-2">Override how characters relate to each other</div>

      {pairs.map(({ from, to }) => {
        const rel = relationships[from.name]?.[to.name] || { type: 'stranger', strength: 0.5, arc_summary: '' };
        const saveKey = `${from.story_character_id}-${to.name}`;
        const isSaving = saving === saveKey;

        return (
          <div key={saveKey} className="bg-white/5 rounded-lg p-2.5 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-white/70">
                {from.name} — {to.name}
              </span>
              {isSaving && <Save className="w-3 h-3 text-blue-400 animate-pulse" />}
            </div>

            <select
              value={rel.type}
              onChange={e => handleUpdate(from, to.name, 'type', e.target.value)}
              className="w-full bg-black/30 border border-white/10 rounded text-xs text-white/80 px-2 py-1.5"
            >
              {RELATIONSHIP_TYPES.map(t => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>

            <div className="flex items-center gap-2">
              <span className="text-[10px] text-white/30 w-12">Strength</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={rel.strength}
                onChange={e => handleUpdate(from, to.name, 'strength', Number(e.target.value))}
                className="flex-1 accent-blue-500 h-1"
              />
              <span className="text-[10px] text-white/40 w-6 text-right">{rel.strength.toFixed(1)}</span>
            </div>

            <input
              type="text"
              value={rel.arc_summary}
              onChange={e => handleUpdate(from, to.name, 'arc_summary', e.target.value)}
              placeholder="Brief description..."
              className="w-full bg-black/30 border border-white/10 rounded text-xs text-white/60 px-2 py-1 placeholder:text-white/20"
            />
          </div>
        );
      })}
    </div>
  );
}
