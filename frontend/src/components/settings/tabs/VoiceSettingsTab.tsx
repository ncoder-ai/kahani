'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Volume2, Loader2, Check, AlertCircle, Eye } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';
import { useConfig } from '@/contexts/ConfigContext';
import { SettingsTabProps, TTSProvider, TTSVoice, TTSSettings } from '../types';

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
  });

  // STT State
  const [sttEnabled, setSttEnabled] = useState(true);
  const [sttModel, setSttModel] = useState('small');
  const [sttModelDownloaded, setSttModelDownloaded] = useState<boolean | null>(null);
  const [vadModelDownloaded, setVadModelDownloaded] = useState<boolean | null>(null);
  const [isDownloadingSTTModel, setIsDownloadingSTTModel] = useState(false);
  const [sttDownloadError, setSttDownloadError] = useState<string | null>(null);

  // Chatterbox-specific settings
  const [chatterboxExaggeration, setChatterboxExaggeration] = useState(0.5);
  const [chatterboxCfgWeight, setChatterboxCfgWeight] = useState(0.5);
  const [chatterboxTemperature, setChatterboxTemperature] = useState(0.7);

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

  useEffect(() => {
    loadTTSProviders();
    loadCurrentTTSSettings();
    loadSTTSettings();
  }, []);

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
        }
      }
    } catch (error) {
      console.error('Failed to load STT settings:', error);
    }
  };

  const handleTTSProviderChange = async (providerType: string) => {
    const providerUrls = await config.getTTSProviderUrls();
    const defaultUrl = (providerUrls as Record<string, string>)[providerType] || '';
    setTtsSettings(prev => ({
      ...prev,
      provider_type: providerType,
      api_url: defaultUrl,
      voice_id: 'default',
    }));
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
          <div className="flex gap-2">
            <select
              value={ttsSettings.voice_id}
              onChange={(e) => setTtsSettings(prev => ({ ...prev, voice_id: e.target.value }))}
              disabled={isLoadingTTSVoices || isLoadingTTSSettings || ttsVoices.length === 0}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
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
            {ttsVoices.length > 0 && (
              <button
                onClick={() => setShowVoiceBrowser(true)}
                disabled={isLoadingTTSSettings}
                className="flex items-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                <Eye className="w-4 h-4" />
                <span>See All</span>
              </button>
            )}
            <button
              onClick={handleTTSTest}
              disabled={isTestingTTS || isLoadingTTSSettings || !ttsSettings.api_url}
              className="flex items-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
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
      <div className="flex items-center justify-end pt-6 border-t border-gray-700">
        <button
          onClick={handleTTSSave}
          disabled={isSavingTTS || isLoadingTTSSettings || !ttsSettings.api_url}
          className="flex items-center gap-2 px-6 py-2 theme-btn-primary rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSavingTTS ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Saving...</span>
            </>
          ) : (
            <span>Save TTS Settings</span>
          )}
        </button>
      </div>

      {/* STT Settings Section */}
      <div className="border-t border-gray-700 pt-6 mt-6">
        <h3 className="text-lg font-semibold text-white mb-4">
          Speech-to-Text (STT) Settings
        </h3>

        {/* iOS Warning */}
        <div className="bg-yellow-900/20 border border-yellow-600/30 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-yellow-500 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-yellow-500 mb-1">iOS Compatibility Notice</h4>
              <p className="text-xs text-yellow-200/80">
                Speech-to-Text currently does not work on iOS devices.
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

          {/* Save Button */}
          <div className="flex justify-end">
            <button
              onClick={handleSTTSave}
              className="flex items-center gap-2 px-6 py-2 theme-btn-primary rounded-lg font-semibold"
            >
              <span>Save STT Settings</span>
            </button>
          </div>
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
