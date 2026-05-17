'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, useHasHydrated } from '@/store';
import {
  ArrowLeft, ArrowRight, Check, Users, UserCircle, MessageSquare,
  Loader2, ChevronDown, ChevronUp
} from 'lucide-react';
import { RoleplayApi } from '@/lib/api/roleplay';
import { CharactersApi } from '@/lib/api/characters';
import type { RoleplayCreateData, RoleplayCharacterConfig, CharacterStoryEntry } from '@/lib/api/roleplay';
import type { Character } from '@/lib/api/types';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient from '@/lib/api';

const roleplayApi = new RoleplayApi();
const charactersApi = new CharactersApi();

// --- Types ---

interface RoleplayCharacterData extends RoleplayCharacterConfig {
  name: string;
  description?: string;
  gender?: string;
}

interface RoleplayWizardData {
  mode: 'one_on_one' | 'group';
  characters: RoleplayCharacterData[];
  player_character_id: number | null;
  player_mode: 'character' | 'narrator' | 'director';
  title: string;
  scenario: string;
  setting: string;
  tone: string;
  content_rating: 'sfw' | 'nsfw';
  turn_mode: 'natural' | 'round_robin' | 'manual';
  response_length: 'concise' | 'detailed';
  narration_style: 'minimal' | 'moderate' | 'rich';
  auto_continue: boolean;
  max_auto_turns: number;
}

const DEFAULT_DATA: RoleplayWizardData = {
  mode: 'one_on_one',
  characters: [],
  player_character_id: null,
  player_mode: 'character',
  title: '',
  scenario: '',
  setting: '',
  tone: '',
  content_rating: 'sfw',
  turn_mode: 'natural',
  response_length: 'concise',
  narration_style: 'moderate',
  auto_continue: false,
  max_auto_turns: 3,
};

const STEPS = [
  { id: 'mode', title: 'Mode' },
  { id: 'characters', title: 'Characters' },
  { id: 'role', title: 'Your Role' },
  { id: 'scenario', title: 'Scenario' },
  { id: 'review', title: 'Review' },
];

const TONES = ['lighthearted', 'dramatic', 'tense', 'romantic', 'humorous', 'dark', 'mysterious', 'casual'];

export default function RoleplayCreationWizard() {
  const router = useRouter();
  const { user } = useAuthStore();
  const hasHydrated = useHasHydrated();
  const [currentStep, setCurrentStep] = useState(0);
  const [data, setData] = useState<RoleplayWizardData>(DEFAULT_DATA);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [userSettings, setUserSettings] = useState<any>(null);

  useUISettings(userSettings?.ui_preferences || null);

  useEffect(() => {
    if (hasHydrated && user) {
      apiClient.getUserSettings().then(setUserSettings).catch(() => {});
    }
  }, [hasHydrated, user]);

  const updateData = useCallback((updates: Partial<RoleplayWizardData>) => {
    setData(prev => ({ ...prev, ...updates }));
    setError(null);
  }, []);

  const canProceed = (): boolean => {
    const stepId = STEPS[currentStep].id;
    switch (stepId) {
      case 'mode':
        return true;
      case 'characters':
        if (data.mode === 'one_on_one') return data.characters.length === 2;
        return data.characters.length >= 2;
      case 'role':
        return data.player_mode !== 'character' || data.player_character_id !== null;
      case 'scenario':
        return true;
      case 'review':
        return true;
      default:
        return true;
    }
  };

  const handleNext = () => {
    if (currentStep < STEPS.length - 1 && canProceed()) {
      setCurrentStep(prev => prev + 1);
      setError(null);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
      setError(null);
    }
  };

  const handleCreate = async () => {
    setIsCreating(true);
    setError(null);
    try {
      const config: RoleplayCreateData = {
        title: data.title || `Roleplay - ${new Date().toLocaleDateString()}`,
        scenario: data.scenario,
        setting: data.setting,
        tone: data.tone,
        content_rating: data.content_rating,
        characters: data.characters.map(c => ({
          character_id: c.character_id,
          role: c.role || 'participant',
          source_story_id: c.source_story_id || undefined,
          source_branch_id: c.source_branch_id || undefined,
          talkativeness: c.talkativeness ?? 0.5,
          is_player: c.character_id === data.player_character_id,
        })),
        player_mode: data.player_mode,
        turn_mode: data.turn_mode,
        response_length: data.response_length,
        narration_style: data.narration_style,
        auto_continue: data.auto_continue,
        max_auto_turns: data.max_auto_turns,
        generate_opening: true,
      };

      const result = await roleplayApi.createRoleplay(config);
      router.push(`/roleplay/${result.story_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create roleplay');
    } finally {
      setIsCreating(false);
    }
  };

  if (!hasHydrated || !user) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
        {/* Progress bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <button onClick={() => router.push('/roleplay')} className="text-white/50 hover:text-white text-sm flex items-center gap-1">
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
            <span className="text-sm text-white/50">Step {currentStep + 1} of {STEPS.length}</span>
          </div>
          <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full theme-bg-accent rounded-full transition-all duration-300"
              style={{ width: `${((currentStep + 1) / STEPS.length) * 100}%` }}
            />
          </div>
          <div className="flex justify-between mt-2">
            {STEPS.map((step, i) => (
              <span key={step.id} className={`text-xs ${i <= currentStep ? 'text-white' : 'text-white/30'}`}>
                {step.title}
              </span>
            ))}
          </div>
        </div>

        {/* Step content */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 sm:p-8 mb-6">
          {STEPS[currentStep].id === 'mode' && (
            <StepMode data={data} onUpdate={updateData} onNext={handleNext} />
          )}
          {STEPS[currentStep].id === 'characters' && (
            <StepCharacters data={data} onUpdate={updateData} />
          )}
          {STEPS[currentStep].id === 'role' && (
            <StepRole data={data} onUpdate={updateData} />
          )}
          {STEPS[currentStep].id === 'scenario' && (
            <StepScenario data={data} onUpdate={updateData} />
          )}
          {STEPS[currentStep].id === 'review' && (
            <StepReview data={data} onUpdate={updateData} />
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/20 border border-red-500/30 rounded-xl p-3 mb-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Navigation buttons */}
        <div className="flex justify-between">
          <button
            onClick={handleBack}
            disabled={currentStep === 0}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium transition-colors ${
              currentStep === 0 ? 'text-white/20 cursor-not-allowed' : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>

          {STEPS[currentStep].id === 'review' ? (
            <button
              onClick={handleCreate}
              disabled={isCreating}
              className="theme-btn-primary flex items-center gap-2 px-6 py-2.5 rounded-xl font-medium"
            >
              {isCreating ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Creating...</>
              ) : (
                <><Check className="w-4 h-4" /> Create Roleplay</>
              )}
            </button>
          ) : (
            <button
              onClick={handleNext}
              disabled={!canProceed()}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium transition-colors ${
                canProceed() ? 'theme-btn-primary' : 'bg-white/10 text-white/30 cursor-not-allowed'
              }`}
            >
              Next <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Step 1: Mode Selection
// =============================================================================

function StepMode({ data, onUpdate, onNext }: {
  data: RoleplayWizardData;
  onUpdate: (d: Partial<RoleplayWizardData>) => void;
  onNext: () => void;
}) {
  const selectMode = (mode: 'one_on_one' | 'group') => {
    onUpdate({ mode, characters: [] });
    setTimeout(onNext, 300);
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-2">Choose Roleplay Mode</h2>
      <p className="text-white/50 mb-6">How many characters will be in this session?</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <button
          onClick={() => selectMode('one_on_one')}
          className={`p-6 rounded-xl border-2 text-left transition-all ${
            data.mode === 'one_on_one'
              ? 'border-white/50 bg-white/10'
              : 'border-white/10 hover:border-white/30 hover:bg-white/5'
          }`}
        >
          <UserCircle className="w-10 h-10 theme-accent-primary mb-3" />
          <div className="text-lg font-semibold text-white mb-1">1-on-1</div>
          <div className="text-sm text-white/50">You and one AI character. Focused, intimate conversations.</div>
        </button>

        <button
          onClick={() => selectMode('group')}
          className={`p-6 rounded-xl border-2 text-left transition-all ${
            data.mode === 'group'
              ? 'border-white/50 bg-white/10'
              : 'border-white/10 hover:border-white/30 hover:bg-white/5'
          }`}
        >
          <Users className="w-10 h-10 theme-accent-primary mb-3" />
          <div className="text-lg font-semibold text-white mb-1">Group</div>
          <div className="text-sm text-white/50">Multiple AI characters. Dynamic group interactions with turn-taking.</div>
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Step 2: Character Selection
// =============================================================================

function StepCharacters({ data, onUpdate }: {
  data: RoleplayWizardData;
  onUpdate: (d: Partial<RoleplayWizardData>) => void;
}) {
  const [library, setLibrary] = useState<Character[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(true);
  const [expandedChar, setExpandedChar] = useState<number | null>(null);
  const maxChars = data.mode === 'one_on_one' ? 2 : 6;

  useEffect(() => {
    loadLibrary();
  }, []);

  const loadLibrary = async () => {
    try {
      const chars = await charactersApi.getCharacters(0, 100, true, false);
      setLibrary(chars);
    } catch (err) {
      console.error('Failed to load characters:', err);
    } finally {
      setLoadingLibrary(false);
    }
  };

  const addCharacter = (char: Character) => {
    if (data.characters.length >= maxChars) return;
    if (data.characters.some(c => c.character_id === char.id)) return;

    const newChar: RoleplayCharacterData = {
      character_id: char.id,
      name: char.name,
      description: char.description,
      gender: char.gender,
      role: 'participant',
      talkativeness: 0.5,
      is_player: false,
      source_story_id: null,
      source_branch_id: null,
    };
    onUpdate({ characters: [...data.characters, newChar] });
  };

  const removeCharacter = (charId: number) => {
    const updated = data.characters.filter(c => c.character_id !== charId);
    onUpdate({
      characters: updated,
      player_character_id: data.player_character_id === charId ? null : data.player_character_id,
    });
  };

  const updateCharacter = (charId: number, updates: Partial<RoleplayCharacterData>) => {
    onUpdate({
      characters: data.characters.map(c =>
        c.character_id === charId ? { ...c, ...updates } : c
      ),
    });
  };

  const selectedIds = new Set(data.characters.map(c => c.character_id));
  const availableChars = library.filter(c => !selectedIds.has(c.id));

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-2">Select Characters</h2>
      <p className="text-white/50 mb-6">
        {data.mode === 'one_on_one'
          ? 'Pick 2 characters (you\'ll choose which one to play next)'
          : `Pick 2-${maxChars} characters for the group`}
      </p>

      {/* Selected characters */}
      {data.characters.length > 0 && (
        <div className="space-y-3 mb-6">
          <h3 className="text-sm font-medium text-white/60 uppercase tracking-wide">Selected ({data.characters.length})</h3>
          {data.characters.map(char => (
            <div key={char.character_id} className="bg-white/5 border border-white/10 rounded-xl p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-white/10 rounded-full flex items-center justify-center text-white font-medium">
                    {char.name[0]}
                  </div>
                  <div>
                    <div className="text-white font-medium">{char.name}</div>
                    {char.description && (
                      <div className="text-xs text-white/40 line-clamp-1">{char.description}</div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setExpandedChar(expandedChar === char.character_id ? null : char.character_id)}
                    className="p-1 hover:bg-white/10 rounded"
                  >
                    {expandedChar === char.character_id ? (
                      <ChevronUp className="w-4 h-4 text-white/50" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-white/50" />
                    )}
                  </button>
                  <button
                    onClick={() => removeCharacter(char.character_id)}
                    className="text-red-400/60 hover:text-red-400 text-xs"
                  >
                    Remove
                  </button>
                </div>
              </div>

              {/* Expanded: talkativeness + dev stage */}
              {expandedChar === char.character_id && (
                <div className="mt-4 pt-3 border-t border-white/10 space-y-4">
                  {/* Talkativeness */}
                  {data.mode === 'group' && (
                    <div>
                      <label className="text-xs text-white/50 block mb-1">
                        Talkativeness: {char.talkativeness === 0.2 ? 'Quiet' : char.talkativeness === 0.8 ? 'Chatty' : 'Balanced'}
                      </label>
                      <input
                        type="range"
                        min="0.1"
                        max="0.9"
                        step="0.1"
                        value={char.talkativeness ?? 0.5}
                        onChange={(e) => updateCharacter(char.character_id, { talkativeness: parseFloat(e.target.value) })}
                        className="w-full accent-white/50"
                      />
                      <div className="flex justify-between text-xs text-white/30 mt-1">
                        <span>Quiet</span>
                        <span>Chatty</span>
                      </div>
                    </div>
                  )}

                  {/* Development stage */}
                  <CharacterStagePicker
                    characterId={char.character_id}
                    selectedStoryId={char.source_story_id || null}
                    onChange={(storyId) => updateCharacter(char.character_id, { source_story_id: storyId })}
                  />

                  {/* Role */}
                  <div>
                    <label className="text-xs text-white/50 block mb-1">Role</label>
                    <input
                      type="text"
                      value={char.role || ''}
                      onChange={(e) => updateCharacter(char.character_id, { role: e.target.value })}
                      placeholder="e.g. protagonist, mentor, rival"
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-white/30"
                    />
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Available characters from library */}
      {data.characters.length < maxChars && (
        <div>
          <h3 className="text-sm font-medium text-white/60 uppercase tracking-wide mb-3">
            Character Library
          </h3>
          {loadingLibrary ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 text-white/30 animate-spin" />
            </div>
          ) : availableChars.length === 0 ? (
            <p className="text-white/30 text-sm py-4 text-center">No more characters available</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
              {availableChars.map(char => (
                <button
                  key={char.id}
                  onClick={() => addCharacter(char)}
                  className="flex items-center gap-3 p-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-left transition-colors"
                >
                  <div className="w-8 h-8 bg-white/10 rounded-full flex items-center justify-center text-white/70 text-sm font-medium flex-shrink-0">
                    {char.name[0]}
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm text-white font-medium truncate">{char.name}</div>
                    {char.description && (
                      <div className="text-xs text-white/40 truncate">{char.description}</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Character Stage Picker (inline)
// =============================================================================

function CharacterStagePicker({ characterId, selectedStoryId, onChange }: {
  characterId: number;
  selectedStoryId: number | null;
  onChange: (storyId: number | null) => void;
}) {
  const [stories, setStories] = useState<CharacterStoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    roleplayApi.getCharacterStories(characterId)
      .then(setStories)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [characterId]);

  if (loading) return <div className="text-xs text-white/30">Loading stories...</div>;
  if (stories.length === 0) return null;

  return (
    <div>
      <label className="text-xs text-white/50 block mb-1">Development Stage</label>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onChange(null)}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
            selectedStoryId === null
              ? 'border-white/50 bg-white/15 text-white'
              : 'border-white/10 text-white/50 hover:border-white/30'
          }`}
        >
          Base
        </button>
        {stories.map(s => (
          <button
            key={s.story_id}
            onClick={() => onChange(s.story_id)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              selectedStoryId === s.story_id
                ? 'border-white/50 bg-white/15 text-white'
                : 'border-white/10 text-white/50 hover:border-white/30'
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>
      <div className="text-xs text-white/30 mt-1">
        {selectedStoryId ? 'Character will have accumulated development from this story' : 'Character starts with base traits only'}
      </div>
    </div>
  );
}

// =============================================================================
// Step 3: Your Role
// =============================================================================

function StepRole({ data, onUpdate }: {
  data: RoleplayWizardData;
  onUpdate: (d: Partial<RoleplayWizardData>) => void;
}) {
  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-2">Your Role</h2>
      <p className="text-white/50 mb-6">How will you participate in this roleplay?</p>

      {/* Player mode */}
      <div className="space-y-3 mb-8">
        {[
          { id: 'character' as const, label: 'Play as a Character', desc: 'You control one of the characters in the scene' },
          { id: 'narrator' as const, label: 'Narrator', desc: 'You describe events and the world — all characters are AI-controlled' },
          { id: 'director' as const, label: 'Director', desc: 'You give meta-instructions to guide the scene without being in it' },
        ].map(mode => (
          <button
            key={mode.id}
            onClick={() => onUpdate({ player_mode: mode.id, player_character_id: mode.id !== 'character' ? null : data.player_character_id })}
            className={`w-full p-4 rounded-xl border-2 text-left transition-all ${
              data.player_mode === mode.id
                ? 'border-white/50 bg-white/10'
                : 'border-white/10 hover:border-white/30'
            }`}
          >
            <div className="font-medium text-white">{mode.label}</div>
            <div className="text-sm text-white/50">{mode.desc}</div>
          </button>
        ))}
      </div>

      {/* Character selection (only if player_mode === 'character') */}
      {data.player_mode === 'character' && (
        <div>
          <h3 className="text-sm font-medium text-white/60 uppercase tracking-wide mb-3">
            Which character will you play?
          </h3>
          <div className="space-y-2">
            {data.characters.map(char => (
              <button
                key={char.character_id}
                onClick={() => onUpdate({ player_character_id: char.character_id })}
                className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 text-left transition-all ${
                  data.player_character_id === char.character_id
                    ? 'border-white/50 bg-white/10'
                    : 'border-white/10 hover:border-white/30'
                }`}
              >
                <div className="w-10 h-10 bg-white/10 rounded-full flex items-center justify-center text-white font-medium">
                  {char.name[0]}
                </div>
                <div>
                  <div className="text-white font-medium">{char.name}</div>
                  {char.role && <div className="text-xs text-white/40">{char.role}</div>}
                </div>
                {data.player_character_id === char.character_id && (
                  <Check className="w-5 h-5 text-green-400 ml-auto" />
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Step 4: Scenario
// =============================================================================

function StepScenario({ data, onUpdate }: {
  data: RoleplayWizardData;
  onUpdate: (d: Partial<RoleplayWizardData>) => void;
}) {
  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-2">Set the Scene</h2>
      <p className="text-white/50 mb-6">Describe the scenario and setting for this roleplay</p>

      <div className="space-y-5">
        {/* Title */}
        <div>
          <label className="text-sm text-white/60 block mb-1">Title (optional)</label>
          <input
            type="text"
            value={data.title}
            onChange={(e) => onUpdate({ title: e.target.value })}
            placeholder="e.g. Coffee Shop Meeting"
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white placeholder-white/30 focus:outline-none focus:border-white/30"
          />
        </div>

        {/* Scenario */}
        <div>
          <label className="text-sm text-white/60 block mb-1">Scenario</label>
          <textarea
            value={data.scenario}
            onChange={(e) => onUpdate({ scenario: e.target.value })}
            placeholder="What's happening? e.g. A chance meeting at a coffee shop leads to an unexpected connection"
            rows={3}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white placeholder-white/30 focus:outline-none focus:border-white/30 resize-none"
          />
        </div>

        {/* Setting */}
        <div>
          <label className="text-sm text-white/60 block mb-1">Setting</label>
          <input
            type="text"
            value={data.setting}
            onChange={(e) => onUpdate({ setting: e.target.value })}
            placeholder="e.g. Modern city coffee shop, afternoon"
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white placeholder-white/30 focus:outline-none focus:border-white/30"
          />
        </div>

        {/* Tone */}
        <div>
          <label className="text-sm text-white/60 block mb-1">Tone</label>
          <div className="flex flex-wrap gap-2">
            {TONES.map(tone => (
              <button
                key={tone}
                onClick={() => onUpdate({ tone: data.tone === tone ? '' : tone })}
                className={`text-sm px-3 py-1.5 rounded-lg border transition-colors capitalize ${
                  data.tone === tone
                    ? 'border-white/50 bg-white/15 text-white'
                    : 'border-white/10 text-white/50 hover:border-white/30'
                }`}
              >
                {tone}
              </button>
            ))}
          </div>
        </div>

        {/* Content rating */}
        <div>
          <label className="text-sm text-white/60 block mb-1">Content Rating</label>
          <div className="flex gap-3">
            <button
              onClick={() => onUpdate({ content_rating: 'sfw' })}
              className={`px-4 py-2 rounded-lg border text-sm transition-colors ${
                data.content_rating === 'sfw'
                  ? 'border-green-500/50 bg-green-500/10 text-green-300'
                  : 'border-white/10 text-white/50 hover:border-white/30'
              }`}
            >
              SFW
            </button>
            <button
              onClick={() => onUpdate({ content_rating: 'nsfw' })}
              className={`px-4 py-2 rounded-lg border text-sm transition-colors ${
                data.content_rating === 'nsfw'
                  ? 'border-red-500/50 bg-red-500/10 text-red-300'
                  : 'border-white/10 text-white/50 hover:border-white/30'
              }`}
            >
              NSFW
            </button>
          </div>
        </div>

        {/* Advanced settings (collapsible) */}
        <AdvancedSettings data={data} onUpdate={onUpdate} />
      </div>
    </div>
  );
}

function AdvancedSettings({ data, onUpdate }: {
  data: RoleplayWizardData;
  onUpdate: (d: Partial<RoleplayWizardData>) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-white/10 rounded-xl">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-sm text-white/60 hover:text-white/80"
      >
        <span>Advanced Settings</span>
        {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-white/10 pt-4">
          {/* Response length */}
          <div>
            <label className="text-xs text-white/50 block mb-1">Response Length</label>
            <div className="flex gap-2">
              {(['concise', 'detailed'] as const).map(len => (
                <button
                  key={len}
                  onClick={() => onUpdate({ response_length: len })}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-colors capitalize ${
                    data.response_length === len
                      ? 'border-white/50 bg-white/15 text-white'
                      : 'border-white/10 text-white/50 hover:border-white/30'
                  }`}
                >
                  {len}
                </button>
              ))}
            </div>
          </div>

          {/* Narration style */}
          <div>
            <label className="text-xs text-white/50 block mb-1">Narration Style</label>
            <div className="flex gap-2">
              {(['minimal', 'moderate', 'rich'] as const).map(style => (
                <button
                  key={style}
                  onClick={() => onUpdate({ narration_style: style })}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-colors capitalize ${
                    data.narration_style === style
                      ? 'border-white/50 bg-white/15 text-white'
                      : 'border-white/10 text-white/50 hover:border-white/30'
                  }`}
                >
                  {style}
                </button>
              ))}
            </div>
          </div>

          {/* Turn mode (group only) */}
          {data.mode === 'group' && (
            <div>
              <label className="text-xs text-white/50 block mb-1">Turn Mode</label>
              <div className="flex gap-2">
                {([
                  { id: 'natural' as const, label: 'Natural' },
                  { id: 'round_robin' as const, label: 'Round Robin' },
                ] as const).map(mode => (
                  <button
                    key={mode.id}
                    onClick={() => onUpdate({ turn_mode: mode.id })}
                    className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                      data.turn_mode === mode.id
                        ? 'border-white/50 bg-white/15 text-white'
                        : 'border-white/10 text-white/50 hover:border-white/30'
                    }`}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Auto-continue */}
          {data.mode === 'group' && (
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs text-white/50 block">Auto-Continue</label>
                <span className="text-xs text-white/30">Let characters talk among themselves</span>
              </div>
              <button
                onClick={() => onUpdate({ auto_continue: !data.auto_continue })}
                className={`w-10 h-6 rounded-full transition-colors ${
                  data.auto_continue ? 'bg-green-500/50' : 'bg-white/10'
                }`}
              >
                <div className={`w-4 h-4 rounded-full bg-white transition-transform mx-1 ${
                  data.auto_continue ? 'translate-x-4' : 'translate-x-0'
                }`} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Step 5: Review
// =============================================================================

function StepReview({ data }: {
  data: RoleplayWizardData;
  onUpdate: (d: Partial<RoleplayWizardData>) => void;
}) {
  const playerChar = data.characters.find(c => c.character_id === data.player_character_id);
  const aiChars = data.characters.filter(c => c.character_id !== data.player_character_id);

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-2">Review & Create</h2>
      <p className="text-white/50 mb-6">Everything look good?</p>

      <div className="space-y-4">
        {/* Mode */}
        <div className="bg-white/5 rounded-lg p-4">
          <div className="text-xs text-white/40 uppercase tracking-wide mb-1">Mode</div>
          <div className="text-white">{data.mode === 'one_on_one' ? '1-on-1' : 'Group'}</div>
        </div>

        {/* Characters */}
        <div className="bg-white/5 rounded-lg p-4">
          <div className="text-xs text-white/40 uppercase tracking-wide mb-2">Characters</div>
          {data.player_mode === 'character' && playerChar && (
            <div className="text-white mb-1">
              <span className="text-green-400 text-xs font-medium mr-2">YOU</span>
              {playerChar.name}
              {playerChar.role && <span className="text-white/40 text-sm ml-2">({playerChar.role})</span>}
            </div>
          )}
          {data.player_mode !== 'character' && (
            <div className="text-white/60 text-sm mb-1">You: {data.player_mode === 'narrator' ? 'Narrator' : 'Director'}</div>
          )}
          {aiChars.map(c => (
            <div key={c.character_id} className="text-white/70 text-sm">
              <span className="text-blue-400 text-xs font-medium mr-2">AI</span>
              {c.name}
              {c.role && <span className="text-white/40 ml-2">({c.role})</span>}
              {c.source_story_id && <span className="text-white/30 ml-2 text-xs">+ dev stage</span>}
            </div>
          ))}
        </div>

        {/* Scenario */}
        {(data.scenario || data.setting) && (
          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-xs text-white/40 uppercase tracking-wide mb-1">Scenario</div>
            {data.scenario && <div className="text-white text-sm">{data.scenario}</div>}
            {data.setting && <div className="text-white/50 text-sm mt-1">{data.setting}</div>}
            {data.tone && <div className="text-white/40 text-xs mt-1 capitalize">Tone: {data.tone}</div>}
          </div>
        )}

        {/* Settings */}
        <div className="bg-white/5 rounded-lg p-4">
          <div className="text-xs text-white/40 uppercase tracking-wide mb-1">Settings</div>
          <div className="text-sm text-white/60 space-y-0.5">
            <div>Response: {data.response_length} | Narration: {data.narration_style}</div>
            <div>Content: {data.content_rating.toUpperCase()}</div>
            {data.mode === 'group' && <div>Turn mode: {data.turn_mode.replace('_', ' ')}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
