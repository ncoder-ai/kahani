'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, useHasHydrated } from '@/store';
import { ArrowLeft, StopCircle } from 'lucide-react';
import { RoleplayApi } from '@/lib/api/roleplay';
import apiClient from '@/lib/api';
import { getApiBaseUrlSync } from '@/lib/apiUrl';
import type {
  RoleplayDetail, RoleplayTurn, RoleplayCharacter, RoleplaySettings,
} from '@/lib/api/roleplay';
import type { InputMode, TurnInputHandle } from './TurnInput';
import TurnDisplay from './TurnDisplay';
import SceneImageGenerator from '../SceneImageGenerator';
import TurnInput from './TurnInput';
import CharacterRoster from './CharacterRoster';
import RoleplaySettingsModal from './RoleplaySettingsModal';
import RoleplayActionMenu from './RoleplayActionMenu';
import AddCharacterModal from './AddCharacterModal';
import BranchSelector from '../BranchSelector';

const roleplayApi = new RoleplayApi();

interface Props {
  roleplayId: number;
}

export default function RoleplaySession({ roleplayId }: Props) {
  const router = useRouter();
  const { user } = useAuthStore();
  const hasHydrated = useHasHydrated();

  // Core data
  const [roleplay, setRoleplay] = useState<RoleplayDetail | null>(null);
  const [turns, setTurns] = useState<RoleplayTurn[]>([]);
  const [characters, setCharacters] = useState<RoleplayCharacter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Streaming state
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingMethod, setStreamingMethod] = useState<string>('auto');
  const [autoTurnProgress, setAutoTurnProgress] = useState<{ current: number; total: number } | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // UI state
  const [showRoster, setShowRoster] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showAddCharacter, setShowAddCharacter] = useState(false);

  // User settings (for consistent display with story pages)
  const [userSettings, setUserSettings] = useState<any>(null);

  // Image generation state
  const [imageGenTurnId, setImageGenTurnId] = useState<number | null>(null);

  // Edit state
  const [editingTurn, setEditingTurn] = useState<RoleplayTurn | null>(null);
  const [editContent, setEditContent] = useState('');

  // Delete confirmation state
  const [deleteConfirmTurn, setDeleteConfirmTurn] = useState<RoleplayTurn | null>(null);

  // TTS state
  const [voiceMapping, setVoiceMapping] = useState<Record<string, { voice_id: string; speed: number }>>({});
  const [playingTurnId, setPlayingTurnId] = useState<number | null>(null);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);

  // Input ref
  const turnInputRef = useRef<TurnInputHandle>(null);

  // Scroll
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);

  // Settings derived from roleplay
  const settings = roleplay?.roleplay_settings as RoleplaySettings | undefined;
  const isGroupMode = (characters.filter(c => c.is_active && !c.is_player).length) > 1;
  const playerChar = characters.find(c => c.is_player);

  // --- Load data ---
  useEffect(() => {
    if (!hasHydrated || !user) return;
    loadRoleplay();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleplayId, hasHydrated, user]);

  const loadRoleplay = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await roleplayApi.getRoleplay(roleplayId);
      setRoleplay(data);
      setTurns(data.turns);
      setCharacters(data.characters);
      // Load voice mapping
      try {
        const voices = await roleplayApi.getVoiceMapping(roleplayId);
        setVoiceMapping(voices.voice_mapping || {});
      } catch {
        // Voice mapping is optional
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load roleplay');
    } finally {
      setIsLoading(false);
    }
  };

  // --- Load user settings ---
  useEffect(() => {
    if (!hasHydrated || !user) return;
    const loadSettings = () => {
      apiClient.getUserSettings().then(r => setUserSettings(r.settings)).catch(() => {});
    };
    loadSettings();
    window.addEventListener('kahaniSettingsChanged', loadSettings);
    return () => window.removeEventListener('kahaniSettingsChanged', loadSettings);
  }, [hasHydrated, user]);

  // --- Auto-scroll ---
  useEffect(() => {
    if (shouldAutoScroll.current) {
      scrollToBottom();
    }
  }, [turns, streamingContent]);

  // Scroll to bottom after initial load finishes rendering
  useEffect(() => {
    if (!isLoading && turns.length > 0) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [isLoading, turns.length]);

  const scrollToBottom = () => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  };

  const handleScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    shouldAutoScroll.current = atBottom;
  };

  // --- Generate opening ---
  const generateOpening = useCallback(async () => {
    if (isGenerating) return;
    setIsGenerating(true);
    setStreamingContent('');
    setStreamingMethod('auto');
    abortControllerRef.current = new AbortController();

    try {
      await roleplayApi.generateOpeningStream(
        roleplayId,
        {
          onContent: (chunk) => {
            setStreamingContent(prev => prev + chunk);
          },
          onComplete: (data) => {
            const newTurn: RoleplayTurn = {
              sequence: turns.length + 1,
              scene_id: data.scene_id as number,
              variant_id: data.variant_id as number,
              content: data.content as string,
              generation_method: 'auto',
              created_at: new Date().toISOString(),
            };
            setTurns(prev => [...prev, newTurn]);
            setStreamingContent('');
          },
          onError: (msg) => setError(msg),
          onDone: () => setIsGenerating(false),
        },
        abortControllerRef.current.signal,
      );
    } catch {
      setIsGenerating(false);
    }
  }, [roleplayId, turns.length, isGenerating]);

  // Auto-generate opening if no turns
  useEffect(() => {
    if (roleplay && turns.length === 0 && !isLoading && !isGenerating) {
      generateOpening();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleplay, isLoading]);

  // --- Submit turn ---
  const handleSubmit = useCallback(async (content: string, mode: InputMode) => {
    if (isGenerating) return;

    // Optimistically add user turn
    const userTurn: RoleplayTurn = {
      sequence: turns.length + 1,
      scene_id: 0,
      variant_id: 0,
      content,
      generation_method: mode === 'direction' ? 'direction' : 'user_written',
      created_at: new Date().toISOString(),
    };
    setTurns(prev => [...prev, userTurn]);

    // Start AI generation
    setIsGenerating(true);
    setStreamingContent('');
    setStreamingMethod('auto');
    abortControllerRef.current = new AbortController();

    try {
      await roleplayApi.generateTurnStream(
        roleplayId,
        content,
        mode,
        {
          onStart: (data) => {
            // Update user turn with real scene_id
            if (data.user_turn_scene_id) {
              setTurns(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.generation_method !== 'auto') {
                  updated[updated.length - 1] = { ...last, scene_id: data.user_turn_scene_id as number };
                }
                return updated;
              });
            }
          },
          onContent: (chunk) => {
            setStreamingContent(prev => prev + chunk);
          },
          onComplete: (data) => {
            const aiTurn: RoleplayTurn = {
              sequence: turns.length + 2,
              scene_id: data.scene_id as number,
              variant_id: data.variant_id as number,
              content: data.content as string,
              generation_method: 'auto',
              created_at: new Date().toISOString(),
            };
            setTurns(prev => [...prev, aiTurn]);
            setStreamingContent('');
          },
          onError: (msg) => setError(msg),
          onDone: () => setIsGenerating(false),
        },
        undefined,
        abortControllerRef.current.signal,
      );
    } catch {
      setIsGenerating(false);
    }
  }, [roleplayId, turns.length, isGenerating]);

  // --- Auto-continue ---
  const handleAutoContinue = useCallback(async (numTurns: number) => {
    if (isGenerating) return;
    setIsGenerating(true);
    setStreamingContent('');
    setStreamingMethod('auto');
    setAutoTurnProgress({ current: 1, total: numTurns });
    abortControllerRef.current = new AbortController();

    try {
      await roleplayApi.autoContinueStream(
        roleplayId,
        numTurns,
        {
          onAutoTurnStart: (turn) => {
            // If there's accumulated streaming content from previous turn, finalize it
            setAutoTurnProgress({ current: turn, total: numTurns });
            setStreamingContent('');
          },
          onContent: (chunk) => {
            setStreamingContent(prev => prev + chunk);
          },
          onAutoTurnComplete: (turn, sceneId, variantId) => {
            // Snapshot current streaming content into a completed turn
            setStreamingContent(prev => {
              const aiTurn: RoleplayTurn = {
                sequence: turns.length + turn,
                scene_id: sceneId,
                variant_id: variantId,
                content: prev,
                generation_method: 'auto',
                created_at: new Date().toISOString(),
              };
              setTurns(tPrev => [...tPrev, aiTurn]);
              return '';
            });
          },
          onError: (msg) => setError(msg),
          onDone: () => {
            setIsGenerating(false);
            setAutoTurnProgress(null);
          },
        },
        abortControllerRef.current.signal,
      );
    } catch {
      setIsGenerating(false);
      setAutoTurnProgress(null);
    }
  }, [roleplayId, turns.length, isGenerating]);

  // --- Auto-generate player turn (fills input as draft) ---
  const handleAutoPlayer = useCallback(async () => {
    if (isGenerating) return;
    setIsGenerating(true);
    setStreamingContent('');
    setStreamingMethod('auto_player');
    abortControllerRef.current = new AbortController();

    let draft = '';
    try {
      await roleplayApi.autoPlayerStream(
        roleplayId,
        {
          onContent: (chunk) => {
            draft += chunk;
            setStreamingContent(prev => prev + chunk);
          },
          onComplete: () => {
            // Fill the input area with the draft for user to review/edit
            setStreamingContent('');
            turnInputRef.current?.setText(draft.trim());
          },
          onError: (msg) => setError(msg),
          onDone: () => setIsGenerating(false),
        },
        abortControllerRef.current.signal,
      );
    } catch {
      setIsGenerating(false);
    }
  }, [roleplayId, turns.length, isGenerating]);

  // --- Stop generation ---
  const handleStop = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsGenerating(false);
    setAutoTurnProgress(null);
    // If there was partial streaming content, add it as a turn
    if (streamingContent.trim()) {
      const partialTurn: RoleplayTurn = {
        sequence: turns.length + 1,
        scene_id: 0,
        variant_id: 0,
        content: streamingContent,
        generation_method: 'auto',
        created_at: new Date().toISOString(),
      };
      setTurns(prev => [...prev, partialTurn]);
      setStreamingContent('');
    }
  }, [streamingContent, turns.length]);

  // --- TTS playback ---
  const handlePlayTTS = useCallback(async (turn: RoleplayTurn) => {
    // Stop any current playback
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current = null;
    }

    if (playingTurnId === turn.scene_id) {
      setPlayingTurnId(null);
      return;
    }

    if (!turn.scene_id) return;

    setPlayingTurnId(turn.scene_id);
    const charNames = characters.filter(c => !c.is_player && c.is_active).map(c => c.name);

    try {
      const { token: accessToken } = useAuthStore.getState();
      const baseUrl = getApiBaseUrlSync();
      const res = await fetch(`${baseUrl}/api/tts/generate-roleplay/${turn.scene_id}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          voice_mapping: voiceMapping,
          character_names: charNames,
        }),
      });

      if (!res.ok) throw new Error('TTS generation failed');

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      ttsAudioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPlayingTurnId(null);
        ttsAudioRef.current = null;
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setPlayingTurnId(null);
        ttsAudioRef.current = null;
      };
      await audio.play();
    } catch (err) {
      console.error('TTS playback failed:', err);
      setPlayingTurnId(null);
    }
  }, [playingTurnId, characters, voiceMapping]);

  // --- Edit turn ---
  const handleEdit = useCallback((turn: RoleplayTurn) => {
    setEditingTurn(turn);
    setEditContent(turn.content);
  }, []);

  const handleEditSave = useCallback(async () => {
    if (!editingTurn || !editContent.trim()) return;
    try {
      await roleplayApi.editTurn(roleplayId, editingTurn.scene_id, editContent);
      setTurns(prev => prev.map(t =>
        t.scene_id === editingTurn.scene_id ? { ...t, content: editContent.trim() } : t
      ));
      setEditingTurn(null);
      setEditContent('');
    } catch (err) {
      console.error('Failed to edit turn:', err);
    }
  }, [roleplayId, editingTurn, editContent]);

  const handleEditCancel = useCallback(() => {
    setEditingTurn(null);
    setEditContent('');
  }, []);

  // --- Delete turn ---
  const handleDelete = useCallback((turn: RoleplayTurn) => {
    setDeleteConfirmTurn(turn);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteConfirmTurn) return;
    try {
      await roleplayApi.deleteTurnsFrom(roleplayId, deleteConfirmTurn.sequence);
      setTurns(prev => prev.filter(t => t.sequence < deleteConfirmTurn.sequence));
    } catch (err) {
      console.error('Failed to delete turns:', err);
    }
    setDeleteConfirmTurn(null);
  }, [roleplayId, deleteConfirmTurn]);

  // --- Regenerate turn ---
  const handleRegenerate = useCallback(async () => {
    if (isGenerating) return;
    const lastAiTurn = [...turns].reverse().find(t => t.generation_method === 'auto');
    if (!lastAiTurn || !lastAiTurn.scene_id) return;

    setIsGenerating(true);
    setStreamingContent('');
    setStreamingMethod('auto');
    // Remove the last AI turn optimistically
    setTurns(prev => prev.filter(t => t.scene_id !== lastAiTurn.scene_id));
    abortControllerRef.current = new AbortController();

    try {
      await roleplayApi.regenerateTurnStream(
        roleplayId,
        lastAiTurn.scene_id,
        {
          onContent: (chunk) => {
            setStreamingContent(prev => prev + chunk);
          },
          onComplete: (data) => {
            const newTurn: RoleplayTurn = {
              sequence: lastAiTurn.sequence,
              scene_id: data.scene_id as number,
              variant_id: data.variant_id as number,
              content: data.content as string,
              generation_method: 'auto',
              created_at: new Date().toISOString(),
            };
            setTurns(prev => [...prev, newTurn]);
            setStreamingContent('');
          },
          onError: (msg) => setError(msg),
          onDone: () => setIsGenerating(false),
        },
        abortControllerRef.current.signal,
      );
    } catch {
      setIsGenerating(false);
    }
  }, [roleplayId, turns, isGenerating]);

  // --- Character management ---
  const handleRemoveCharacter = async (storyCharacterId: number) => {
    try {
      await roleplayApi.removeCharacter(roleplayId, storyCharacterId);
      // Reload to get updated character list and narration turn
      const data = await roleplayApi.getRoleplay(roleplayId);
      setCharacters(data.characters);
      setTurns(data.turns);
    } catch (err) {
      console.error('Failed to remove character:', err);
    }
  };

  // --- Settings update ---
  const handleSettingsUpdate = async (newSettings: RoleplaySettings) => {
    try {
      await roleplayApi.updateSettings(roleplayId, newSettings);
      // Update local state
      setRoleplay(prev => prev ? {
        ...prev,
        roleplay_settings: { ...prev.roleplay_settings, ...newSettings },
      } : null);
      setShowSettings(false);
    } catch (err) {
      console.error('Failed to update settings:', err);
    }
  };

  // --- Branch switch ---
  const handleBranchChange = useCallback(async (branchId: number) => {
    try {
      const data = await roleplayApi.getRoleplay(roleplayId);
      setRoleplay(data);
      setTurns(data.turns);
      setCharacters(data.characters);
    } catch (err) {
      console.error('Failed to reload after branch switch:', err);
    }
  }, [roleplayId]);

  // --- Cleanup ---
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // --- Loading state ---
  if (!hasHydrated || !user || isLoading) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (error && !roleplay) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <button onClick={() => router.push('/roleplay')} className="text-white/60 hover:text-white">
            Back to Roleplays
          </button>
        </div>
      </div>
    );
  }

  const lastAiTurnIdx = turns.map(t => t.generation_method).lastIndexOf('auto');

  return (
    <div className="h-screen flex flex-col theme-bg-primary">
      {/* Header */}
      <header className="flex-shrink-0 h-14 border-b border-white/10 bg-black/40 backdrop-blur-md flex items-center px-4 gap-3 z-10">
        <button onClick={() => router.push('/roleplay')} className="p-1.5 hover:bg-white/10 rounded-lg">
          <ArrowLeft className="w-5 h-5 text-white/60" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-semibold text-white truncate">{roleplay?.title || 'Roleplay'}</h1>
          <div className="text-[10px] text-white/30">
            {turns.length} turn{turns.length !== 1 ? 's' : ''}
            {autoTurnProgress && (
              <span className="ml-2 text-purple-300">
                Auto-continue {autoTurnProgress.current}/{autoTurnProgress.total}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isGenerating && (
            <button onClick={handleStop} className="p-1.5 hover:bg-red-500/20 rounded-lg" title="Stop">
              <StopCircle className="w-5 h-5 text-red-400" />
            </button>
          )}
          {roleplay && (
            <BranchSelector
              storyId={roleplayId}
              currentBranchId={roleplay.branch_id}
              currentSceneSequence={turns.length}
              onBranchChange={handleBranchChange}
            />
          )}
        </div>
      </header>

      {/* Turn history */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 md:p-6"
        style={{ overscrollBehaviorY: 'contain' }}
      >
        <div className="max-w-4xl mx-auto">
        {/* Scenario context */}
        {roleplay?.scenario && (
          <div className="text-center mb-6 py-3">
            <p className="text-sm text-white/30 italic">{roleplay.scenario}</p>
          </div>
        )}

        {/* Turns */}
        <div className="prose prose-invert prose-lg max-w-none mb-8">
          <div className="space-y-8">
            {turns.map((turn, i) => {
              const isEditing = editingTurn?.scene_id === turn.scene_id;
              return (
                <div key={`${turn.scene_id}-${turn.sequence}-${i}`}>
                  <TurnDisplay
                    turn={turn}
                    characters={characters}
                    playerCharacterName={playerChar?.name}
                    isLastAiTurn={i === lastAiTurnIdx}
                    userSettings={userSettings}
                    onRegenerate={handleRegenerate}
                    onEdit={turn.scene_id ? handleEdit : undefined}
                    onDelete={turn.scene_id ? handleDelete : undefined}
                    onPlayTTS={turn.generation_method === 'auto' && turn.scene_id ? handlePlayTTS : undefined}
                    isPlayingTTS={playingTurnId === turn.scene_id}
                    onImage={(t) => setImageGenTurnId(prev => prev === t.scene_id ? null : t.scene_id)}
                    isEditing={isEditing}
                    editContent={isEditing ? editContent : undefined}
                    onEditChange={isEditing ? setEditContent : undefined}
                    onEditSave={isEditing ? handleEditSave : undefined}
                    onEditCancel={isEditing ? handleEditCancel : undefined}
                  />
                  {imageGenTurnId === turn.scene_id && turn.scene_id > 0 && (
                    <SceneImageGenerator
                      sceneId={turn.scene_id}
                      storyId={roleplayId}
                      sceneContent={turn.content}
                      forceShow={true}
                      onClose={() => setImageGenTurnId(null)}
                      defaultCheckpoint={userSettings?.image_generation_settings?.comfyui_checkpoint || ''}
                      defaultStyle={userSettings?.image_generation_settings?.default_style || 'illustrated'}
                      defaultSteps={userSettings?.image_generation_settings?.steps}
                      defaultCfgScale={userSettings?.image_generation_settings?.cfg_scale}
                    />
                  )}
                </div>
              );
            })}

            {/* Streaming turn */}
            {isGenerating && streamingContent && (
              <TurnDisplay
                turn={{
                  sequence: turns.length + 1,
                  scene_id: 0,
                  variant_id: 0,
                  content: '',
                  generation_method: streamingMethod,
                  created_at: null,
                }}
                characters={characters}
                playerCharacterName={playerChar?.name}
                isLastAiTurn={false}
                isStreaming={true}
                streamingContent={streamingContent}
                userSettings={userSettings}
              />
            )}
          </div>
        </div>

        {/* Generating indicator (no content yet) */}
        {isGenerating && !streamingContent && turns.length > 0 && (
          <div className="flex justify-start mb-4">
            <div className="bg-white/5 border border-white/10 rounded-2xl rounded-tl-md px-4 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-white/30 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-white/30 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-white/30 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="text-center py-2">
            <span className="text-xs text-red-400 bg-red-500/10 px-3 py-1 rounded-full">{error}</span>
          </div>
        )}
        </div>{/* close max-w-4xl */}
      </div>

      {/* Input */}
      <div className="flex-shrink-0">
        <TurnInput
          ref={turnInputRef}
          playerCharacterName={playerChar?.name}
          isGroupMode={isGroupMode}
          isGenerating={isGenerating}
          autoContinueEnabled={settings?.auto_continue !== false}
          maxAutoTurns={settings?.max_auto_turns as number || 3}
          onSubmit={handleSubmit}
          onAutoContinue={handleAutoContinue}
          onAutoPlayer={handleAutoPlayer}
        />
      </div>

      {/* Floating action menu */}
      <RoleplayActionMenu
        isGenerating={isGenerating}
        hasTurns={turns.length > 0}
        hasLastAiTurn={lastAiTurnIdx >= 0}
        isPlayingTTS={playingTurnId !== null}
        onRegenerate={handleRegenerate}
        onAutoContinue={handleAutoContinue}
        onStop={handleStop}
        onPlayTTS={() => {
          const lastAi = turns[lastAiTurnIdx];
          if (lastAi) handlePlayTTS(lastAi);
        }}
        onDelete={() => {
          const lastAi = turns[lastAiTurnIdx];
          if (lastAi) handleDelete(lastAi);
        }}
        onToggleRoster={() => setShowRoster(prev => !prev)}
        onOpenSettings={() => setShowSettings(true)}
        onSubmitDirection={(direction) => handleSubmit(direction, 'direction')}
        showRoster={showRoster}
      />

      {/* Character roster */}
      <CharacterRoster
        characters={characters}
        isOpen={showRoster}
        onToggle={() => setShowRoster(prev => !prev)}
        onRemoveCharacter={handleRemoveCharacter}
        onAddCharacter={() => setShowAddCharacter(true)}
      />

      {/* Settings modal */}
      {showSettings && roleplay && (
        <RoleplaySettingsModal
          roleplayId={roleplayId}
          settings={settings || {}}
          characters={characters}
          voiceMapping={voiceMapping}
          onSave={handleSettingsUpdate}
          onVoiceMappingChange={async (mapping) => {
            setVoiceMapping(mapping);
            try {
              await roleplayApi.updateVoiceMapping(roleplayId, mapping);
            } catch (err) {
              console.error('Failed to save voice mapping:', err);
            }
          }}
          onClose={() => setShowSettings(false)}
        />
      )}

      {showAddCharacter && (
        <AddCharacterModal
          roleplayId={roleplayId}
          existingCharacterIds={characters.map(c => c.character_id)}
          onAdded={async () => {
            setShowAddCharacter(false);
            const data = await roleplayApi.getRoleplay(roleplayId);
            setCharacters(data.characters);
            setTurns(data.turns);
          }}
          onClose={() => setShowAddCharacter(false)}
        />
      )}

      {/* Delete confirmation bar — portal-style overlay above everything */}
      {deleteConfirmTurn && (
        <>
          {/* Backdrop to catch outside clicks */}
          <div className="fixed inset-0 z-[100]" onClick={() => setDeleteConfirmTurn(null)} />
          <div className="fixed bottom-32 left-1/2 -translate-x-1/2 bg-red-900/95 backdrop-blur-sm border border-red-500/40 rounded-xl px-5 py-3 flex items-center gap-3 z-[101] shadow-2xl">
            <span className="text-sm text-red-100 whitespace-nowrap">Delete this turn and all after it?</span>
            <button
              onClick={confirmDelete}
              className="px-3 py-1.5 text-xs font-medium bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
            >
              Delete
            </button>
            <button
              onClick={() => setDeleteConfirmTurn(null)}
              className="px-3 py-1.5 text-xs font-medium bg-white/10 hover:bg-white/20 text-white/70 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  );
}
