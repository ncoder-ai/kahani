'use client';

import { useState, useEffect, useCallback } from 'react';
import { Volume2, Loader2 } from 'lucide-react';
import type { RoleplayCharacter } from '@/lib/api/roleplay';
import { getApiBaseUrlSync as getApiBaseUrl } from '@/lib/apiUrl';
import { useAuthStore } from '@/store';

interface VoiceInfo {
  id: string;
  name: string;
  language: string | null;
  description: string | null;
}

export interface VoiceMapping {
  [characterName: string]: { voice_id: string; speed: number };
}

interface Props {
  characters: RoleplayCharacter[];
  voiceMapping: VoiceMapping;
  onChange: (mapping: VoiceMapping) => void;
}

export default function VoiceMappingPanel({ characters, voiceMapping, onChange }: Props) {
  const { token: accessToken } = useAuthStore();
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [isLoadingVoices, setIsLoadingVoices] = useState(false);
  const [testingVoice, setTestingVoice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load available voices
  useEffect(() => {
    loadVoices();
  }, []);

  const loadVoices = async () => {
    setIsLoadingVoices(true);
    setError(null);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/tts/voices`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        if (res.status === 400) {
          setError('TTS not configured. Set up TTS in Settings first.');
          return;
        }
        throw new Error('Failed to load voices');
      }
      const data = await res.json();
      setVoices(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load voices');
    } finally {
      setIsLoadingVoices(false);
    }
  };

  const updateCharVoice = useCallback((name: string, voiceId: string) => {
    const current = voiceMapping[name] || { voice_id: '', speed: 1.0 };
    onChange({ ...voiceMapping, [name]: { ...current, voice_id: voiceId } });
  }, [voiceMapping, onChange]);

  const updateCharSpeed = useCallback((name: string, speed: number) => {
    const current = voiceMapping[name] || { voice_id: '', speed: 1.0 };
    onChange({ ...voiceMapping, [name]: { ...current, speed } });
  }, [voiceMapping, onChange]);

  const testVoice = useCallback(async (voiceId: string, charName: string) => {
    if (!voiceId || testingVoice) return;
    setTestingVoice(charName);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/tts/test-voice-preview`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text: `Hello, I am ${charName}.`, voice_id: voiceId }),
      });
      if (!res.ok) throw new Error('Preview failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setTestingVoice(null);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setTestingVoice(null);
      };
      await audio.play();
    } catch {
      setTestingVoice(null);
    }
  }, [accessToken, testingVoice]);

  const aiCharacters = characters.filter(c => !c.is_player && c.is_active);

  if (error) {
    return (
      <div className="text-xs text-white/30 py-2 text-center">{error}</div>
    );
  }

  if (isLoadingVoices) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="w-4 h-4 text-white/30 animate-spin" />
        <span className="text-xs text-white/30 ml-2">Loading voices...</span>
      </div>
    );
  }

  if (voices.length === 0) {
    return (
      <div className="text-xs text-white/30 py-2 text-center">No voices available</div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-white/40 mb-2">Assign TTS voices to characters</div>

      {/* Narrator voice */}
      <VoiceRow
        label="Narrator"
        voiceId={voiceMapping.__narrator__?.voice_id || ''}
        speed={voiceMapping.__narrator__?.speed || 1.0}
        voices={voices}
        isTesting={testingVoice === '__narrator__'}
        onVoiceChange={(v) => updateCharVoice('__narrator__', v)}
        onSpeedChange={(s) => updateCharSpeed('__narrator__', s)}
        onTest={() => testVoice(voiceMapping.__narrator__?.voice_id || '', 'the narrator')}
      />

      {/* Character voices */}
      {aiCharacters.map(char => (
        <VoiceRow
          key={char.story_character_id}
          label={char.name}
          voiceId={voiceMapping[char.name]?.voice_id || ''}
          speed={voiceMapping[char.name]?.speed || 1.0}
          voices={voices}
          isTesting={testingVoice === char.name}
          onVoiceChange={(v) => updateCharVoice(char.name, v)}
          onSpeedChange={(s) => updateCharSpeed(char.name, s)}
          onTest={() => testVoice(voiceMapping[char.name]?.voice_id || '', char.name)}
        />
      ))}
    </div>
  );
}

function VoiceRow({
  label,
  voiceId,
  speed,
  voices,
  isTesting,
  onVoiceChange,
  onSpeedChange,
  onTest,
}: {
  label: string;
  voiceId: string;
  speed: number;
  voices: VoiceInfo[];
  isTesting: boolean;
  onVoiceChange: (id: string) => void;
  onSpeedChange: (speed: number) => void;
  onTest: () => void;
}) {
  return (
    <div className="bg-white/5 rounded-lg p-2.5 space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-white/70">{label}</span>
        <button
          onClick={onTest}
          disabled={!voiceId || isTesting}
          className="p-1 hover:bg-white/10 rounded disabled:opacity-30"
        >
          {isTesting ? (
            <Loader2 className="w-3.5 h-3.5 text-white/40 animate-spin" />
          ) : (
            <Volume2 className="w-3.5 h-3.5 text-white/40" />
          )}
        </button>
      </div>
      <select
        value={voiceId}
        onChange={e => onVoiceChange(e.target.value)}
        className="w-full bg-black/30 border border-white/10 rounded text-xs text-white/80 px-2 py-1.5"
      >
        <option value="">Default voice</option>
        {voices.map(v => (
          <option key={v.id} value={v.id}>
            {v.name}{v.description ? ` — ${v.description}` : ''}
          </option>
        ))}
      </select>
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-white/30">Speed</span>
        <input
          type="range"
          min={0.5}
          max={2.0}
          step={0.1}
          value={speed}
          onChange={e => onSpeedChange(Number(e.target.value))}
          className="flex-1 accent-blue-500 h-1"
        />
        <span className="text-[10px] text-white/40 w-6 text-right">{speed.toFixed(1)}</span>
      </div>
    </div>
  );
}
