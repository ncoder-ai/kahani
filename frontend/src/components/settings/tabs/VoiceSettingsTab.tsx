'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { Volume2, Loader2, Check, AlertCircle, Eye } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';
import { useConfig } from '@/contexts/ConfigContext';
import { SettingsTabProps, TTSProvider, TTSVoice, TTSSettings } from '../types';

// Per-story character voices (Phase A). Identical UX to the row pattern
// in TTSSettingsModal — voiceId="" means "fall back to default".
interface CharacterVoiceRow {
  key: string;       // canonical lowercased lookup name
  display: string;   // what we render
  voiceId: string;   // "" = default
}

// Lazy load VoiceBrowserModal
const VoiceBrowserModal = dynamic(() => import('../../VoiceBrowserModal'), {
  loading: () => null,
  ssr: false
});

const DEFAULT_TTS_PROVIDERS: TTSProvider[] = [
  { type: 'openai-compatible', name: 'OpenAI Compatible', supports_streaming: true },
  { type: 'chatterbox', name: 'Chatterbox', supports_streaming: true },
  { type: 'kokoro', name: 'Kokoro', supports_streaming: false },
  { type: 'vibevoice', name: 'VibeVoice', supports_streaming: true },
  { type: 'qwen3-tts', name: 'Qwen3-TTS', supports_streaming: true },
  { type: 'indextts', name: 'IndexTTS2', supports_streaming: false },
];

interface VoiceSettingsTabProps extends SettingsTabProps {
}

export default function VoiceSettingsTab({
  token,
  showMessage,
}: VoiceSettingsTabProps) {
  const config = useConfig();

  // TTS State
  const [ttsProviders, setTtsProviders] = useState<TTSProvider[]>([]);
  const [ttsVoices, setTtsVoices] = useState<TTSVoice[]>([]);
  const [ttsSettings, setTtsSettings] = useState<TTSSettings>({
    provider_type: 'openai-compatible',
    api_url: '',
    voice_id: 'default',
    speed: 1.0,
    timeout: 30,
    tts_enabled: true,
    progressive_narration: false,
    chunk_size: 280,
    stream_audio: true,
    auto_play_last_scene: false,
    playback_buffer_seconds: 1.0,
  });

  // STT State
  const [sttEnabled, setSttEnabled] = useState(true);
  const [sttModel, setSttModel] = useState('small');
  const [sttLanguage, setSttLanguage] = useState(''); // '' = system / auto
  const [sttModelDownloaded, setSttModelDownloaded] = useState<boolean | null>(null);
  const [vadModelDownloaded, setVadModelDownloaded] = useState<boolean | null>(null);
  const [isDownloadingSTTModel, setIsDownloadingSTTModel] = useState(false);
  const [sttDownloadError, setSttDownloadError] = useState<string | null>(null);

  // Chatterbox-specific settings
  const [chatterboxExaggeration, setChatterboxExaggeration] = useState(0.5);
  const [chatterboxCfgWeight, setChatterboxCfgWeight] = useState(0.5);
  const [chatterboxTemperature, setChatterboxTemperature] = useState(0.7);

  // Per-story character voices (Phase A). Story id comes from the URL —
  // when this tab is opened on `/story/<id>/...` we show the section;
  // otherwise (global settings access) it stays hidden because there's
  // no story context to scope the mapping to.
  const params = useParams() as { id?: string } | null;
  const storyId = params?.id ? parseInt(params.id, 10) || null : null;
  const [characterVoiceRows, setCharacterVoiceRows] = useState<CharacterVoiceRow[]>([]);
  const [characterVoicesLoading, setCharacterVoicesLoading] = useState(false);
  const [characterVoicesError, setCharacterVoicesError] = useState<string>('');
  // Saved snapshot — used to detect dirty rows so auto-save only fires
  // when the user actually changed something.
  const characterVoicesSavedRef = useRef<string>('');
  // Set to true once the initial GET completes for the current
  // (storyId, provider_type) combination. The auto-save effect MUST NOT
  // fire before this — otherwise it races the GET with empty rows and
  // silently PUTs an empty map, wiping the user's saved voices.
  const characterVoicesLoadedRef = useRef<boolean>(false);

  // Loading/Status states
  const [isLoadingTTSProviders, setIsLoadingTTSProviders] = useState(false);
  const [isLoadingTTSVoices, setIsLoadingTTSVoices] = useState(false);
  const [isLoadingTTSSettings, setIsLoadingTTSSettings] = useState(false);
  const [isSavingTTS, setIsSavingTTS] = useState(false);
  const [isTestingTTS, setIsTestingTTS] = useState(false);
  const [isTestingTTSConnection, setIsTestingTTSConnection] = useState(false);
  const [ttsConnectionStatus, setTtsConnectionStatus] = useState<'idle' | 'success' | 'failed'>('idle');
  const [showVoiceBrowser, setShowVoiceBrowser] = useState(false);
  const [testAudio, setTestAudio] = useState<HTMLAudioElement | null>(null);
  const [hasAutoConnected, setHasAutoConnected] = useState(false);
  const [hasCheckedSTT, setHasCheckedSTT] = useState(false);

  // --- Auto-save ---
  const ttsLoadedRef = useRef(false);
  const sttLoadedRef = useRef(false);
  const ttsSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sttSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doTTSAutoSave = useCallback(async () => {
    if (!ttsLoadedRef.current || !token) return;
    try {
      const extraParams: Record<string, any> = {};
      if (ttsSettings.provider_type === 'chatterbox') {
        extraParams.exaggeration = chatterboxExaggeration;
        extraParams.cfg_weight = chatterboxCfgWeight;
        extraParams.temperature = chatterboxTemperature;
      }
      const fullSettings = {
        ...ttsSettings,
        extra_params: Object.keys(extraParams).length > 0 ? extraParams : (ttsSettings.extra_params || {}),
      };
      await fetch(`${await getApiBaseUrl()}/api/tts/provider-configs/${ttsSettings.provider_type}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(fullSettings),
      });
      await fetch(`${await getApiBaseUrl()}/api/tts/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(fullSettings),
      });
    } catch (error) {
      console.error('TTS auto-save failed:', error);
    }
  }, [token, ttsSettings, chatterboxExaggeration, chatterboxCfgWeight, chatterboxTemperature]);

  const doSTTAutoSave = useCallback(async () => {
    if (!sttLoadedRef.current || !token) return;
    try {
      await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ stt_settings: { enabled: sttEnabled, model: sttModel, language: sttLanguage } }),
      });
    } catch (error) {
      console.error('STT auto-save failed:', error);
    }
  }, [token, sttEnabled, sttModel, sttLanguage]);

  // Debounced TTS auto-save
  useEffect(() => {
    if (!ttsLoadedRef.current) return;
    if (ttsSaveTimerRef.current) clearTimeout(ttsSaveTimerRef.current);
    ttsSaveTimerRef.current = setTimeout(() => doTTSAutoSave(), 800);
    return () => { if (ttsSaveTimerRef.current) clearTimeout(ttsSaveTimerRef.current); };
  }, [ttsSettings, chatterboxExaggeration, chatterboxCfgWeight, chatterboxTemperature, doTTSAutoSave]);

  // Debounced STT auto-save
  useEffect(() => {
    if (!sttLoadedRef.current) return;
    if (sttSaveTimerRef.current) clearTimeout(sttSaveTimerRef.current);
    sttSaveTimerRef.current = setTimeout(() => doSTTAutoSave(), 800);
    return () => { if (sttSaveTimerRef.current) clearTimeout(sttSaveTimerRef.current); };
  }, [sttEnabled, sttModel, sttLanguage, doSTTAutoSave]);

  useEffect(() => {
    loadTTSProviders();
    loadCurrentTTSSettings();
    loadSTTSettings();
  }, []);

  // Load per-story character voices when storyId / provider changes.
  // Skipped entirely when this tab isn't opened from a story page.
  useEffect(() => {
    if (!storyId || !ttsSettings.provider_type || !token) return;
    // Mark as not-loaded so the save effect skips while the GET is in flight.
    // (storyId/provider changes are also a "remount" for the data — old saved
    // ref no longer applies to the new context.)
    characterVoicesLoadedRef.current = false;
    let cancelled = false;
    (async () => {
      setCharacterVoicesLoading(true);
      setCharacterVoicesError('');
      try {
        const apiBase = await getApiBaseUrl();
        const headers = { 'Authorization': `Bearer ${token}` };
        const [charsResp, savedResp] = await Promise.all([
          fetch(`${apiBase}/api/characters/story/${storyId}/characters`, { headers }),
          fetch(`${apiBase}/api/stories/${storyId}/tts-character-voices?provider=${encodeURIComponent(ttsSettings.provider_type)}`, { headers }),
        ]);
        if (cancelled) return;
        const chars = charsResp.ok ? await charsResp.json() : [];
        const saved = savedResp.ok ? await savedResp.json() : { voices: {} };
        const savedMap: Record<string, string> = saved?.voices || {};

        const rows: CharacterVoiceRow[] = [
          { key: 'narrator', display: 'Narrator', voiceId: savedMap['narrator'] || '' },
        ];
        const seen = new Set(['narrator']);
        for (const c of (chars || []) as Array<{ name?: string }>) {
          const key = (c.name || '').trim().toLowerCase();
          if (!key || seen.has(key)) continue;
          seen.add(key);
          rows.push({ key, display: c.name || key, voiceId: savedMap[key] || '' });
        }
        // Surface saved entries whose character is no longer in the cast
        // (renamed/removed) so the user can clean them up.
        for (const [key, voiceId] of Object.entries(savedMap)) {
          if (seen.has(key)) continue;
          rows.push({ key, display: key, voiceId });
        }
        setCharacterVoiceRows(rows);
        characterVoicesSavedRef.current = JSON.stringify(savedMap);
        // Now the save effect is allowed to PUT — it'll only fire when
        // the user actually edits a row.
        characterVoicesLoadedRef.current = true;
      } catch (err: any) {
        if (!cancelled) setCharacterVoicesError(err?.message || 'Failed to load character voices');
      } finally {
        if (!cancelled) setCharacterVoicesLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [storyId, ttsSettings.provider_type, token]);

  // Debounced auto-save for character voices (mirrors the TTS auto-save
  // debouncing pattern above — dirty check via JSON comparison so we
  // only PUT when something actually changed).
  const characterVoicesSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!storyId || !token || !ttsSettings.provider_type) return;
    // CRITICAL: do not auto-save until the initial GET has completed.
    // Otherwise the save effect runs on mount with empty rows, schedules
    // a timer, and PUTs `{}` to the backend before the load returns —
    // wiping the user's saved voice mappings to "default".
    if (!characterVoicesLoadedRef.current) return;
    // Build the canonical map we'd send — same dropping rules as the
    // backend (empty voiceIds become absence).
    const map: Record<string, string> = {};
    for (const row of characterVoiceRows) {
      if (row.voiceId && row.voiceId.trim()) map[row.key] = row.voiceId.trim();
    }
    const serialized = JSON.stringify(map);
    if (serialized === characterVoicesSavedRef.current) return;
    if (characterVoicesSaveTimerRef.current) clearTimeout(characterVoicesSaveTimerRef.current);
    characterVoicesSaveTimerRef.current = setTimeout(async () => {
      try {
        const apiBase = await getApiBaseUrl();
        const resp = await fetch(
          `${apiBase}/api/stories/${storyId}/tts-character-voices?provider=${encodeURIComponent(ttsSettings.provider_type)}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ voices: map }),
          },
        );
        if (resp.ok) {
          characterVoicesSavedRef.current = serialized;
          setCharacterVoicesError('');
        } else {
          setCharacterVoicesError(`Save failed (${resp.status})`);
        }
      } catch (err: any) {
        setCharacterVoicesError(err?.message || 'Save failed');
      }
    }, 800);
    return () => {
      if (characterVoicesSaveTimerRef.current) clearTimeout(characterVoicesSaveTimerRef.current);
    };
  }, [characterVoiceRows, storyId, token, ttsSettings.provider_type]);

  // Auto-test TTS connection once settings are loaded (api_url becomes available)
  useEffect(() => {
    if (!hasAutoConnected && !isLoadingTTSSettings && ttsSettings.api_url && ttsVoices.length === 0) {
      setHasAutoConnected(true);
      autoTestTTSConnection();
    }
  }, [isLoadingTTSSettings, ttsSettings.api_url]);

  // Auto-check STT model download status once STT settings are loaded
  useEffect(() => {
    if (!hasCheckedSTT && sttEnabled && sttModel) {
      setHasCheckedSTT(true);
      checkSTTModelStatus();
    }
  }, [sttEnabled, sttModel]);

  const autoTestTTSConnection = async () => {
    if (!ttsSettings.api_url) return;
    setIsTestingTTSConnection(true);
    setTtsConnectionStatus('idle');
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/tts/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider_type: ttsSettings.provider_type,
          api_url: ttsSettings.api_url,
          api_key: ttsSettings.api_key,
        }),
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setTtsConnectionStatus('success');
        if (data.voices && data.voices.length > 0) {
          setTtsVoices(data.voices);
          if (!ttsSettings.voice_id || ttsSettings.voice_id === 'default') {
            setTtsSettings(prev => ({ ...prev, voice_id: data.voices[0].id }));
          }
        }
      } else {
        setTtsConnectionStatus('failed');
      }
    } catch (error) {
      setTtsConnectionStatus('failed');
    } finally {
      setIsTestingTTSConnection(false);
    }
  };

  const checkSTTModelStatus = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/stt-model-status`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        if (data.enabled) {
          setSttModelDownloaded(data.whisper?.downloaded ?? null);
          setVadModelDownloaded(data.vad?.downloaded ?? null);
        }
      }
    } catch (error) {
      // Silent failure - STT model status check is non-critical
    }
  };

  const loadTTSProviders = async () => {
    setIsLoadingTTSProviders(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/tts/providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        // Backend returns list directly, not wrapped in 'providers'
        setTtsProviders(Array.isArray(data) ? data : (data.providers || DEFAULT_TTS_PROVIDERS));
      } else {
        setTtsProviders(DEFAULT_TTS_PROVIDERS);
      }
    } catch (error) {
      console.error('Failed to load TTS providers:', error);
      setTtsProviders(DEFAULT_TTS_PROVIDERS);
    } finally {
      setIsLoadingTTSProviders(false);
    }
  };

  const loadCurrentTTSSettings = async () => {
    setIsLoadingTTSSettings(true);
    try {
      const providerUrls = await config.getTTSProviderUrls();
      const response = await fetch(`${await getApiBaseUrl()}/api/tts/settings`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        // Backend returns TTSSettingsResponse directly, not wrapped in 'settings'
        const settings = data.settings || data;
        if (settings) {
          const providerType = settings.provider_type || 'openai-compatible';
          const defaultUrl = (providerUrls as Record<string, string>)[providerType] || '';
          setTtsSettings({
            ...settings,
            api_url: settings.api_url || defaultUrl,
          });

          if (settings.extra_params) {
            if (settings.extra_params.exaggeration !== undefined) {
              setChatterboxExaggeration(settings.extra_params.exaggeration);
            }
            if (settings.extra_params.cfg_weight !== undefined) {
              setChatterboxCfgWeight(settings.extra_params.cfg_weight);
            }
            if (settings.extra_params.temperature !== undefined) {
              setChatterboxTemperature(settings.extra_params.temperature);
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to load TTS settings:', error);
    } finally {
      setIsLoadingTTSSettings(false);
      setTimeout(() => { ttsLoadedRef.current = true; }, 100);
    }
  };

  const loadSTTSettings = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        if (data.settings?.stt_settings) {
          setSttEnabled(data.settings.stt_settings.enabled ?? true);
          setSttModel(data.settings.stt_settings.model || 'small');
          setSttLanguage(data.settings.stt_settings.language || '');
        }
      }
    } catch (error) {
      console.error('Failed to load STT settings:', error);
    }
    setTimeout(() => { sttLoadedRef.current = true; }, 100);
  };

  const handleTTSProviderChange = async (providerType: string) => {
    // Load the user's saved config for this provider first (custom URL,
    // voice, extra params) so switching back doesn't clobber it with the
    // app default. Falls back to the registry default URL when no saved
    // config exists yet.
    const apiBase = await getApiBaseUrl();
    let saved: any = null;
    try {
      const resp = await fetch(`${apiBase}/api/tts/provider-configs/${providerType}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (resp.ok) saved = await resp.json();
    } catch {
      // Non-fatal — fall through to defaults.
    }

    const providerUrls = await config.getTTSProviderUrls();
    const defaultUrl = (providerUrls as Record<string, string>)[providerType] || '';

    setTtsSettings(prev => ({
      ...prev,
      provider_type: providerType,
      api_url: saved?.api_url || defaultUrl,
      api_key: saved?.api_key || '',
      voice_id: saved?.voice_id || 'default',
      speed: saved?.speed ?? prev.speed,
      timeout: saved?.timeout ?? prev.timeout,
      extra_params: saved?.extra_params || {},
    }));

    // Restore Chatterbox-specific sliders so they don't reset to defaults
    // when the user toggles back to chatterbox.
    if (providerType === 'chatterbox' && saved?.extra_params) {
      if (saved.extra_params.exaggeration !== undefined) setChatterboxExaggeration(saved.extra_params.exaggeration);
      if (saved.extra_params.cfg_weight !== undefined) setChatterboxCfgWeight(saved.extra_params.cfg_weight);
      if (saved.extra_params.temperature !== undefined) setChatterboxTemperature(saved.extra_params.temperature);
    }

    setTtsVoices([]);
    setTtsConnectionStatus('idle');
  };

  const handleTTSTestConnection = async () => {
    if (!ttsSettings.api_url) {
      showMessage('Please enter an API URL', 'error');
      return;
    }

    setIsTestingTTSConnection(true);
    setTtsConnectionStatus('idle');

    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/tts/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider_type: ttsSettings.provider_type,
          api_url: ttsSettings.api_url,
          api_key: ttsSettings.api_key,
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setTtsConnectionStatus('success');
        if (data.voices && data.voices.length > 0) {
          setTtsVoices(data.voices);
          if (!ttsSettings.voice_id || ttsSettings.voice_id === 'default') {
            setTtsSettings(prev => ({ ...prev, voice_id: data.voices[0].id }));
          }
          showMessage(`Connected! Found ${data.voices.length} voices`, 'success');
        } else {
          showMessage('Connected but no voices found', 'success');
        }
      } else {
        setTtsConnectionStatus('failed');
        showMessage(data.message || 'Connection failed', 'error');
      }
    } catch (error) {
      setTtsConnectionStatus('failed');
      showMessage('Connection test failed', 'error');
    } finally {
      setIsTestingTTSConnection(false);
    }
  };

  const handleTTSTest = async () => {
    if (!ttsSettings.api_url) {
      showMessage('Please enter an API URL', 'error');
      return;
    }

    setIsTestingTTS(true);
    try {
      const extraParams: Record<string, any> = {};
      if (ttsSettings.provider_type === 'chatterbox') {
        extraParams.exaggeration = chatterboxExaggeration;
        extraParams.cfg_weight = chatterboxCfgWeight;
        extraParams.temperature = chatterboxTemperature;
      }

      // Use test-voice endpoint which accepts provider settings directly (for testing before saving)
      const response = await fetch(`${await getApiBaseUrl()}/api/tts/test-voice`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider_type: ttsSettings.provider_type,
          api_url: ttsSettings.api_url,
          api_key: ttsSettings.api_key,
          voice_id: ttsSettings.voice_id,
          speed: ttsSettings.speed,
          timeout: ttsSettings.timeout,
          extra_params: Object.keys(extraParams).length > 0 ? extraParams : undefined,
        }),
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        if (testAudio) {
          testAudio.pause();
          URL.revokeObjectURL(testAudio.src);
        }

        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        audio.play();
        setTestAudio(audio);
        showMessage('Playing test audio...', 'success');
      } else {
        const error = await response.json();
        showMessage(error.detail || 'TTS test failed', 'error');
      }
    } catch (error) {
      showMessage('TTS test failed', 'error');
    } finally {
      setIsTestingTTS(false);
    }
  };

  const handleTTSSave = async () => {
    setIsSavingTTS(true);
    try {
      const extraParams: Record<string, any> = {};
      if (ttsSettings.provider_type === 'chatterbox') {
        extraParams.exaggeration = chatterboxExaggeration;
        extraParams.cfg_weight = chatterboxCfgWeight;
        extraParams.temperature = chatterboxTemperature;
      }

      const fullSettings = {
        ...ttsSettings,
        extra_params: Object.keys(extraParams).length > 0 ? extraParams : (ttsSettings.extra_params || {}),
      };

      // Save provider-specific config first
      const providerConfigResponse = await fetch(`${await getApiBaseUrl()}/api/tts/provider-configs/${ttsSettings.provider_type}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(fullSettings),
      });

      if (!providerConfigResponse.ok) {
        const error = await providerConfigResponse.json();
        showMessage(error.detail || 'Failed to save provider config', 'error');
        return;
      }

      // Save global TTS settings
      const globalResponse = await fetch(`${await getApiBaseUrl()}/api/tts/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(fullSettings),
      });

      if (globalResponse.ok) {
        showMessage('TTS settings saved', 'success');
      } else {
        const error = await globalResponse.json();
        showMessage(error.detail || 'Failed to save settings', 'error');
      }
    } catch (error) {
      showMessage('Failed to save settings', 'error');
    } finally {
      setIsSavingTTS(false);
    }
  };

  const handleSTTSave = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          stt_settings: {
            enabled: sttEnabled,
            model: sttModel,
          },
        }),
      });

      if (response.ok) {
        showMessage('STT settings saved', 'success');
      } else {
        showMessage('Failed to save STT settings', 'error');
      }
    } catch (error) {
      showMessage('Failed to save STT settings', 'error');
    }
  };

  const downloadSTTModel = async () => {
    setIsDownloadingSTTModel(true);
    setSttDownloadError(null);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/stt/download-model`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ model: sttModel }),
      });

      if (response.ok) {
        setSttModelDownloaded(true);
        setVadModelDownloaded(true);
        showMessage('STT models downloaded successfully', 'success');
      } else {
        const error = await response.json();
        setSttDownloadError(error.detail || 'Failed to download models');
        showMessage('Failed to download STT models', 'error');
      }
    } catch (error) {
      setSttDownloadError('Download failed');
      showMessage('Failed to download STT models', 'error');
    } finally {
      setIsDownloadingSTTModel(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Behavior Settings */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white mb-4">Behavior Settings</h3>

        <div className="space-y-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={ttsSettings.tts_enabled !== false}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, tts_enabled: e.target.checked }))}
              disabled={isLoadingTTSSettings}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm text-white">Enable TTS</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={ttsSettings.progressive_narration === true}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, progressive_narration: e.target.checked }))}
              disabled={isLoadingTTSSettings}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm text-white">Progressive Narration (Streaming)</span>
          </label>

          {ttsSettings.progressive_narration && (
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Chunk Size: {ttsSettings.chunk_size || 280} characters
              </label>
              <input
                type="range"
                min="100"
                max="500"
                step="20"
                value={ttsSettings.chunk_size || 280}
                onChange={(e) => setTtsSettings(prev => ({ ...prev, chunk_size: parseInt(e.target.value) }))}
                disabled={isLoadingTTSSettings}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
            </div>
          )}

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={ttsSettings.auto_play_last_scene === true}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, auto_play_last_scene: e.target.checked }))}
              disabled={isLoadingTTSSettings}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm text-white">Auto-play New Scenes</span>
          </label>

          <div className="mt-2 p-3 rounded-lg bg-blue-600/10 border border-blue-500/30 space-y-3">
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={ttsSettings.use_segment_extraction === true}
                onChange={(e) => setTtsSettings(prev => ({ ...prev, use_segment_extraction: e.target.checked }))}
                disabled={isLoadingTTSSettings}
                className="w-4 h-4 rounded mt-0.5 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-sm text-white font-medium">Multi-voice + emotion (immersive)</div>
                <div className="text-xs text-gray-400 mt-1">
                  Run an LLM pass to split each scene by speaker and emotion. Each character's
                  lines play in their assigned voice (set above), and dialogue carries an emotion
                  hint (whisper, shout, etc.) when supported by the provider. Cached after first run.
                </div>
              </div>
            </label>

            {ttsSettings.use_segment_extraction && (
              <div className="ml-6 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                <label className="text-xs text-gray-400 whitespace-nowrap">Use LLM:</label>
                <select
                  value={ttsSettings.tts_extraction_llm_choice || 'extraction'}
                  onChange={(e) => setTtsSettings(prev => ({
                    ...prev,
                    tts_extraction_llm_choice: e.target.value as 'extraction' | 'main',
                  }))}
                  disabled={isLoadingTTSSettings}
                  className="w-full sm:w-auto sm:flex-1 min-w-0 text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="extraction">Extraction LLM (default — typically local)</option>
                  <option value="main">Main LLM (typically cloud — faster, costs credits)</option>
                </select>
              </div>
            )}

            <label className="flex items-start gap-2 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={ttsSettings.use_streaming === true}
                onChange={(e) => setTtsSettings(prev => ({
                  ...prev,
                  use_streaming: e.target.checked,
                }))}
                disabled={isLoadingTTSSettings}
                className="w-4 h-4 rounded mt-0.5 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-sm text-white font-medium">Use streaming</div>
                <div className="text-xs text-gray-400 mt-1">
                  When the provider supports PCM streaming, send the entire
                  scene as ONE call and play PCM frames as they're generated
                  (sub-second time to first audio, no chunk seams). Falls
                  back to chunked playback when streaming isn't supported
                  or fails.
                </div>
              </div>
            </label>

            <label className="flex items-start gap-2 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={ttsSettings.use_whole_scene === true}
                onChange={(e) => setTtsSettings(prev => ({
                  ...prev,
                  use_whole_scene: e.target.checked,
                }))}
                disabled={isLoadingTTSSettings}
                className="w-4 h-4 rounded mt-0.5 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-sm text-white font-medium">Send whole scene</div>
                <div className="text-xs text-gray-400 mt-1">
                  When streaming isn't being used (off or unsupported), send
                  the whole scene to the TTS as ONE block call instead of
                  chunking. Wait time is longer (full audio file generates
                  before playback starts) but no chunk-boundary artifacts.
                </div>
              </div>
            </label>

            <label className="flex items-start gap-2 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={ttsSettings.use_multi_speaker === true}
                onChange={(e) => setTtsSettings(prev => ({
                  ...prev,
                  use_multi_speaker: e.target.checked,
                  // Multi-voice requires segment extraction; auto-enable.
                  use_segment_extraction: e.target.checked ? true : prev.use_segment_extraction,
                }))}
                disabled={isLoadingTTSSettings}
                className="w-4 h-4 rounded mt-0.5 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-sm text-white font-medium">Use multi-voice</div>
                <div className="text-xs text-gray-400 mt-1">
                  When the provider supports it (VibeVoice/F5-TTS), render the
                  whole scene in ONE inference call with each character in
                  their assigned voice and seamless turn-taking. The provider
                  has a slot cap (VibeVoice = 4) — if a scene has more
                  distinct speakers than slots, characters beyond the cap
                  use the narrator voice. Assign voices to the most important
                  characters under Story → Voices to control which ones get
                  their own slot. Auto-enables segment extraction. Falls
                  back to per-utterance chunking when the provider doesn't
                  support it.
                </div>
              </div>
            </label>

            {/* Pre-buffer slider — accumulates this many seconds of audio
                ahead of the playhead before playback starts. Absorbs
                generation jitter when streaming RTF is close to realtime. */}
            <div className="pt-2">
              <label className="block text-sm font-medium text-white mb-1">
                Pre-buffer: {(ttsSettings.playback_buffer_seconds ?? 1.0).toFixed(1)}s
              </label>
              <input
                type="range"
                min={0.5}
                max={10}
                step={0.5}
                value={ttsSettings.playback_buffer_seconds ?? 1.0}
                onChange={(e) => setTtsSettings(prev => ({
                  ...prev,
                  playback_buffer_seconds: parseFloat(e.target.value),
                }))}
                disabled={isLoadingTTSSettings}
                className="w-full"
              />
              <div className="flex justify-between text-[10px] text-gray-500 mt-1 px-1">
                <span>0.5s (snappy)</span>
                <span>10s (max smoothing)</span>
              </div>
              <div className="text-xs text-gray-400 mt-2">
                Audio waits this many seconds before starting playback so
                subsequent generated frames pile up ahead of the playhead.
                Higher values absorb more upstream generation jitter at
                the cost of a longer initial delay before audio starts.
                If you hear stuttering during playback, increase this.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Provider Configuration */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white mb-4">Provider Configuration</h3>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-white mb-2">TTS Provider</label>
            <select
              value={ttsSettings.provider_type}
              onChange={(e) => handleTTSProviderChange(e.target.value)}
              disabled={isLoadingTTSProviders || isLoadingTTSSettings}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {isLoadingTTSProviders ? (
                <option>Loading providers...</option>
              ) : ttsProviders.length === 0 ? (
                <option>No providers available</option>
              ) : (
                ttsProviders.map((provider) => (
                  <option key={provider.type} value={provider.type}>
                    {provider.name} {provider.supports_streaming && '🔄'}
                  </option>
                ))
              )}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-white mb-2">API URL</label>
            <input
              type="url"
              value={ttsSettings.api_url}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, api_url: e.target.value }))}
              disabled={isLoadingTTSSettings}
              placeholder="http://localhost:1234"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-white mb-2">API Key (Optional)</label>
            <input
              type="password"
              value={ttsSettings.api_key ?? ''}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, api_key: e.target.value }))}
              disabled={isLoadingTTSSettings}
              placeholder="Enter API key if required"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleTTSTestConnection}
              disabled={isTestingTTSConnection || isLoadingTTSSettings || !ttsSettings.api_url}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isTestingTTSConnection ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Testing...</span>
                </>
              ) : ttsConnectionStatus === 'success' ? (
                <>
                  <Check className="w-4 h-4 text-green-400" />
                  <span>Connected</span>
                </>
              ) : ttsConnectionStatus === 'failed' ? (
                <>
                  <AlertCircle className="w-4 h-4 text-red-400" />
                  <span>Failed</span>
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  <span>Test Connection</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Voice Selection */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white mb-4">Voice Selection</h3>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-white mb-2">Voice</label>
          <div className="flex flex-col sm:flex-row gap-2">
            <select
              value={ttsSettings.voice_id}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, voice_id: e.target.value }))}
              disabled={isLoadingTTSVoices || isLoadingTTSSettings || ttsVoices.length === 0}
              className="w-full sm:flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {isLoadingTTSVoices ? (
                <option>Loading voices...</option>
              ) : ttsVoices.length === 0 ? (
                <option value="default">Test connection to load voices</option>
              ) : (
                ttsVoices.map((voice) => (
                  <option key={voice.id} value={voice.id}>
                    {voice.name} {voice.language ? `(${voice.language})` : ''}
                  </option>
                ))
              )}
            </select>
            <div className="flex gap-2 sm:contents">
              {ttsVoices.length > 0 && (
                <button
                  onClick={() => setShowVoiceBrowser(true)}
                  disabled={isLoadingTTSSettings}
                  className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  <Eye className="w-4 h-4" />
                  <span>See All</span>
                </button>
              )}
              <button
                onClick={handleTTSTest}
                disabled={isTestingTTS || isLoadingTTSSettings || !ttsSettings.api_url}
                className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {isTestingTTS ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Testing...</span>
                  </>
                ) : (
                  <>
                    <Volume2 className="w-4 h-4" />
                    <span>Test Voice</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Per-story Character voices section (Phase A) */}
      {storyId && (
        <div className="space-y-3 p-4 bg-blue-600/10 border border-blue-500/30 rounded-lg">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-blue-300">Character voices</h3>
            {characterVoicesLoading && (
              <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
            )}
          </div>
          <p className="text-xs text-gray-400">
            Pick a voice for each character in this story. Rows left as
            <span className="font-mono"> Default </span> fall back to the voice
            above. Mappings are saved per provider — switching providers shows
            that provider's mappings.
          </p>
          {characterVoicesError && (
            <p className="text-xs text-red-400">{characterVoicesError}</p>
          )}
          {!characterVoicesLoading && characterVoiceRows.length === 0 && (
            <p className="text-xs text-gray-500 italic">No characters in this story yet.</p>
          )}
          <div className="space-y-3 sm:space-y-2">
            {characterVoiceRows.map((row, idx) => {
              const isUnknownVoice = row.voiceId && !ttsVoices.some(v => v.id === row.voiceId);
              return (
                // Stack label above select on mobile so the select takes the
                // full row width — the earlier inline `flex` + `w-32` label
                // squeezed the select past the modal's right edge on phones.
                <div key={row.key} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2 min-w-0">
                  <label
                    className="text-sm text-gray-200 truncate sm:w-32 sm:flex-shrink-0"
                    title={row.display}
                  >
                    {row.display}
                  </label>
                  <select
                    value={row.voiceId}
                    onChange={(e) => {
                      const next = [...characterVoiceRows];
                      next[idx] = { ...row, voiceId: e.target.value };
                      setCharacterVoiceRows(next);
                    }}
                    disabled={isLoadingTTSVoices || characterVoicesLoading}
                    className="w-full sm:flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="">Default</option>
                    {isUnknownVoice && (
                      <option value={row.voiceId}>
                        {row.voiceId} (unavailable)
                      </option>
                    )}
                    {ttsVoices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name || v.id}
                        {v.language ? ` — ${v.language}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Chatterbox-Specific Settings */}
      {ttsSettings.provider_type === 'chatterbox' && (
        <div className="space-y-4 p-4 bg-purple-600/10 border border-purple-500/30 rounded-lg">
          <h3 className="text-sm font-semibold text-purple-300">Chatterbox Advanced Settings</h3>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Exaggeration: {chatterboxExaggeration.toFixed(2)}
              </label>
              <input
                type="range"
                min="0.25"
                max="2.0"
                step="0.05"
                value={chatterboxExaggeration}
                onChange={(e) => setChatterboxExaggeration(parseFloat(e.target.value))}
                disabled={isLoadingTTSSettings}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Pace (CFG Weight): {chatterboxCfgWeight.toFixed(2)}
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={chatterboxCfgWeight}
                onChange={(e) => setChatterboxCfgWeight(parseFloat(e.target.value))}
                disabled={isLoadingTTSSettings}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Temperature: {chatterboxTemperature.toFixed(2)}
              </label>
              <input
                type="range"
                min="0.05"
                max="5.0"
                step="0.05"
                value={chatterboxTemperature}
                onChange={(e) => setChatterboxTemperature(parseFloat(e.target.value))}
                disabled={isLoadingTTSSettings}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
            </div>
          </div>
        </div>
      )}

      {/* Speed Control */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white mb-4">Speed Control</h3>

        <div>
          <label className="block text-sm font-medium text-white mb-2">
            Speech Speed: {ttsSettings.speed.toFixed(2)}x
          </label>
          <input
            type="range"
            min="0.5"
            max="2.0"
            step="0.1"
            value={ttsSettings.speed}
            onChange={(e) => setTtsSettings(prev => ({ ...prev, speed: parseFloat(e.target.value) }))}
            disabled={isLoadingTTSSettings}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
          />
        </div>
      </div>

      {/* Timeout Setting */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white mb-4">Advanced Settings</h3>

        <div>
          <label className="block text-sm font-medium text-white mb-2">
            Request Timeout (seconds)
          </label>
          <input
            type="number"
            min="5"
            max="120"
            value={ttsSettings.timeout}
            onChange={(e) => setTtsSettings(prev => ({ ...prev, timeout: parseInt(e.target.value) }))}
            disabled={isLoadingTTSSettings}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
          />
        </div>
      </div>

      {/* TTS Action Buttons */}
      {/* STT Settings Section */}
      <div className="border-t border-gray-700 pt-6 mt-6">
        <h3 className="text-lg font-semibold text-white mb-4">
          Speech-to-Text (STT) Settings
        </h3>

        {/* iOS uses on-device Apple SFSpeechRecognizer (same engine as
            the keyboard dictation button). Web/Android stream to the
            backend STT service. */}
        <div className="bg-blue-900/20 border border-blue-600/30 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-blue-300 mb-1">iOS Support</h4>
              <p className="text-xs text-blue-100/80">
                The Saga iOS app uses on-device Apple speech recognition —
                tap the microphone next to any text input to dictate. Web and
                Android stream audio to the backend transcription service.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={sttEnabled}
                onChange={(e) => setSttEnabled(e.target.checked)}
                className="w-4 h-4 rounded"
              />
              <span className="text-sm text-white">Enable Speech-to-Text</span>
            </label>
          </div>

          {sttEnabled && (
            <>
              <div>
                <label className="block text-sm font-medium text-white mb-2">Whisper Model</label>
                <select
                  value={sttModel}
                  onChange={(e) => setSttModel(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="tiny">Tiny (~150MB, fast)</option>
                  <option value="small">Small (~500MB, balanced)</option>
                  <option value="medium">Medium (~1.5GB, accurate)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Language / Accent</label>
                <select
                  value={sttLanguage}
                  onChange={(e) => setSttLanguage(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="">System / auto-detect</option>
                  <option value="en-US">English (US)</option>
                  <option value="en-GB">English (UK)</option>
                  <option value="en-IN">English (India)</option>
                  <option value="en-AU">English (Australia)</option>
                  <option value="en-CA">English (Canada)</option>
                  <option value="hi-IN">Hindi (India)</option>
                  <option value="es-ES">Spanish (Spain)</option>
                  <option value="es-MX">Spanish (Mexico)</option>
                  <option value="fr-FR">French (France)</option>
                  <option value="de-DE">German (Germany)</option>
                  <option value="it-IT">Italian (Italy)</option>
                  <option value="pt-BR">Portuguese (Brazil)</option>
                  <option value="ja-JP">Japanese</option>
                  <option value="ko-KR">Korean</option>
                  <option value="zh-CN">Chinese (Simplified)</option>
                </select>
                <p className="text-xs text-gray-400 mt-1">
                  On iOS this picks the Apple speech recognition locale.
                  Elsewhere the backend Whisper takes the language prefix
                  (e.g. <code>en-IN</code> → English).
                </p>
              </div>

              {/* Model download status */}
              {(sttModelDownloaded === false || vadModelDownloaded === false) && (
                <div className="space-y-2">
                  <p className="text-sm text-gray-400">
                    STT models need to be downloaded before use.
                  </p>
                  {sttDownloadError && (
                    <p className="text-xs text-red-400">{sttDownloadError}</p>
                  )}
                  <button
                    onClick={downloadSTTModel}
                    disabled={isDownloadingSTTModel}
                    className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                  >
                    {isDownloadingSTTModel ? 'Downloading...' : 'Download STT Models'}
                  </button>
                </div>
              )}
            </>
          )}

        </div>
      </div>

      {/* System / Maintenance */}
      {/* Voice Browser Modal */}
      <VoiceBrowserModal
        isOpen={showVoiceBrowser}
        onClose={() => setShowVoiceBrowser(false)}
        voices={ttsVoices}
        selectedVoiceId={ttsSettings.voice_id}
        onSelectVoice={(voiceId) => setTtsSettings(prev => ({ ...prev, voice_id: voiceId }))}
        providerSettings={{
          provider_type: ttsSettings.provider_type,
          api_url: ttsSettings.api_url,
          api_key: ttsSettings.api_key,
          speed: ttsSettings.speed,
        }}
      />
    </div>
  );
}
