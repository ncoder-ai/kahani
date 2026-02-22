'use client';

import { useState } from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';
import type { RoleplaySettings, RoleplayCharacter } from '@/lib/api/roleplay';
import VoiceMappingPanel from './VoiceMappingPanel';
import type { VoiceMapping } from './VoiceMappingPanel';
import RelationshipPanel from './RelationshipPanel';

interface Props {
  roleplayId: number;
  settings: RoleplaySettings;
  characters: RoleplayCharacter[];
  voiceMapping: VoiceMapping;
  onSave: (settings: RoleplaySettings) => void;
  onVoiceMappingChange: (mapping: VoiceMapping) => void;
  onClose: () => void;
}

export default function RoleplaySettingsModal({
  roleplayId,
  settings,
  characters,
  voiceMapping,
  onSave,
  onVoiceMappingChange,
  onClose,
}: Props) {
  const [local, setLocal] = useState<RoleplaySettings>({ ...settings });
  const [showVoices, setShowVoices] = useState(false);
  const [showRelationships, setShowRelationships] = useState(false);

  const update = (key: keyof RoleplaySettings, value: unknown) => {
    setLocal(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-gray-900 border border-white/10 rounded-2xl w-full max-w-md mx-4 p-6 max-h-[85vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-white">Roleplay Settings</h2>
          <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-lg">
            <X className="w-5 h-5 text-white/60" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Turn mode */}
          <div>
            <label className="text-xs text-white/50 block mb-1.5">Turn Mode</label>
            <div className="flex gap-2">
              {['natural', 'round_robin', 'manual'].map(mode => (
                <button
                  key={mode}
                  onClick={() => update('turn_mode', mode)}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    local.turn_mode === mode
                      ? 'border-blue-500/50 bg-blue-500/20 text-blue-300'
                      : 'border-white/10 text-white/40 hover:bg-white/5'
                  }`}
                >
                  {mode === 'round_robin' ? 'Round Robin' : mode.charAt(0).toUpperCase() + mode.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Response length */}
          <div>
            <label className="text-xs text-white/50 block mb-1.5">Response Length</label>
            <div className="flex gap-2">
              {['concise', 'detailed'].map(len => (
                <button
                  key={len}
                  onClick={() => update('response_length', len)}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    local.response_length === len
                      ? 'border-blue-500/50 bg-blue-500/20 text-blue-300'
                      : 'border-white/10 text-white/40 hover:bg-white/5'
                  }`}
                >
                  {len.charAt(0).toUpperCase() + len.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Narration style */}
          <div>
            <label className="text-xs text-white/50 block mb-1.5">Narration Style</label>
            <div className="flex gap-2">
              {['minimal', 'moderate', 'rich'].map(style => (
                <button
                  key={style}
                  onClick={() => update('narration_style', style)}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    local.narration_style === style
                      ? 'border-blue-500/50 bg-blue-500/20 text-blue-300'
                      : 'border-white/10 text-white/40 hover:bg-white/5'
                  }`}
                >
                  {style.charAt(0).toUpperCase() + style.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Auto-continue toggle */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs text-white/50 block">Auto-Continue</label>
              <span className="text-[10px] text-white/25">Let characters talk among themselves</span>
            </div>
            <button
              onClick={() => update('auto_continue', !local.auto_continue)}
              className={`w-10 h-5 rounded-full transition-colors relative ${
                local.auto_continue ? 'bg-blue-500' : 'bg-white/15'
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                local.auto_continue ? 'left-5' : 'left-0.5'
              }`} />
            </button>
          </div>

          {/* Max auto turns */}
          {local.auto_continue && (
            <div>
              <label className="text-xs text-white/50 block mb-1.5">
                Max Auto Turns: {local.max_auto_turns || 3}
              </label>
              <input
                type="range"
                min={1}
                max={5}
                value={local.max_auto_turns || 3}
                onChange={e => update('max_auto_turns', Number(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>
          )}

          {/* Relationships (collapsible) */}
          <div className="border-t border-white/10 pt-3">
            <button
              onClick={() => setShowRelationships(!showRelationships)}
              className="flex items-center justify-between w-full text-xs text-white/50 hover:text-white/70"
            >
              <span>Character Relationships</span>
              {showRelationships ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showRelationships && (
              <div className="mt-3">
                <RelationshipPanel
                  roleplayId={roleplayId}
                  characters={characters}
                />
              </div>
            )}
          </div>

          {/* Voice mapping (collapsible) */}
          <div className="border-t border-white/10 pt-3">
            <button
              onClick={() => setShowVoices(!showVoices)}
              className="flex items-center justify-between w-full text-xs text-white/50 hover:text-white/70"
            >
              <span>Character Voices (TTS)</span>
              {showVoices ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showVoices && (
              <div className="mt-3">
                <VoiceMappingPanel
                  characters={characters}
                  voiceMapping={voiceMapping}
                  onChange={onVoiceMappingChange}
                />
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <button onClick={onClose} className="flex-1 px-4 py-2 text-sm text-white/50 hover:text-white/70 rounded-xl border border-white/10">
            Cancel
          </button>
          <button
            onClick={() => onSave(local)}
            className="flex-1 px-4 py-2 text-sm theme-btn-primary rounded-xl font-medium"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
