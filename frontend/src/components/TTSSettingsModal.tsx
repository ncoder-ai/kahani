'use client';

import { useState, useEffect } from 'react';
import { X, Volume2, Loader2, Check, AlertCircle, Eye } from 'lucide-react';
import apiClient from '@/lib/api';
import VoiceBrowserModal from './VoiceBrowserModal';

interface TTSProvider {
  type: string;
  name: string;
  supports_streaming: boolean;
}

interface Voice {
  id: string;
  name: string;
  language?: string;
  description?: string;
}

interface TTSSettings {
  id?: number;
  user_id?: number;
  provider_type: string;
  api_url: string;
  api_key?: string;
  voice_id: string;
  speed: number;
  timeout: number;
  extra_params?: Record<string, any>;
  // Behavior settings
  tts_enabled?: boolean;
  progressive_narration?: boolean;
  chunk_size?: number;
  stream_audio?: boolean;
}

interface TTSSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

const DEFAULT_PROVIDER_URLS: Record<string, string> = {
  'openai-compatible': 'http://localhost:1234/v1',
  'chatterbox': 'http://localhost:8880/v1',
  'kokoro': 'http://localhost:8188/v1',
};

export default function TTSSettingsModal({ isOpen, onClose, onSaved }: TTSSettingsModalProps) {
  const [providers, setProviders] = useState<TTSProvider[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [settings, setSettings] = useState<TTSSettings>({
    provider_type: 'openai-compatible',
    api_url: 'http://localhost:1234/v1',
    voice_id: 'default',
    speed: 1.0,
    timeout: 30,
    tts_enabled: true,
    progressive_narration: false,
    chunk_size: 280,
    stream_audio: true,
  });
  const [providerConfigs, setProviderConfigs] = useState<Record<string, TTSSettings>>({});
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [isLoadingVoices, setIsLoadingVoices] = useState(false);
  const [isLoadingSettings, setIsLoadingSettings] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [error, setError] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string>('');
  const [testAudio, setTestAudio] = useState<HTMLAudioElement | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'success' | 'failed'>('idle');
  const [showVoiceBrowser, setShowVoiceBrowser] = useState(false);
  
  // Chatterbox-specific settings
  const [chatterboxExaggeration, setChatterboxExaggeration] = useState(0.5);
  const [chatterboxCfgWeight, setChatterboxCfgWeight] = useState(3.0);
  const [chatterboxTemperature, setChatterboxTemperature] = useState(0.7);

  // Load providers and current settings on mount
  useEffect(() => {
    if (isOpen) {
      loadProviders();
      loadAllProviderConfigs();
      loadCurrentSettings();
    }
  }, [isOpen]);

  // Load voices when provider changes
  useEffect(() => {
    if (isOpen && settings.provider_type && settings.api_url) {
      loadVoices();
    }
  }, [isOpen, settings.provider_type, settings.api_url]);

  const loadProviders = async () => {
    setIsLoadingProviders(true);
    setError('');
    try {
      const data = await apiClient.get<TTSProvider[]>('/api/tts/providers');
      setProviders(data);
    } catch (err: any) {
      setError(`Failed to load providers: ${err.message}`);
    } finally {
      setIsLoadingProviders(false);
    }
  };

  const loadAllProviderConfigs = async () => {
    try {
      const configs = await apiClient.get<TTSSettings[]>('/api/tts/provider-configs');
      const configMap: Record<string, TTSSettings> = {};
      configs.forEach(config => {
        configMap[config.provider_type] = config;
      });
      setProviderConfigs(configMap);
    } catch (err: any) {
      console.error('Failed to load provider configs:', err);
      // Don't show error, just use defaults
    }
  };

  const loadCurrentSettings = async () => {
    setIsLoadingSettings(true);
    try {
      const data = await apiClient.get<TTSSettings>('/api/tts/settings');
      if (data) {
        setSettings({
          provider_type: data.provider_type || 'openai-compatible',
          api_url: data.api_url || DEFAULT_PROVIDER_URLS['openai-compatible'],
          api_key: data.api_key,
          voice_id: data.voice_id || 'default',
          speed: data.speed || 1.0,
          timeout: data.timeout || 30,
          extra_params: data.extra_params,
          tts_enabled: data.tts_enabled !== undefined ? data.tts_enabled : true,
          progressive_narration: data.progressive_narration || false,
          chunk_size: data.chunk_size || 280,
          stream_audio: data.stream_audio !== undefined ? data.stream_audio : true,
        });
        
        // Load Chatterbox-specific settings if present
        if (data.extra_params) {
          if (data.extra_params.exaggeration !== undefined) {
            setChatterboxExaggeration(data.extra_params.exaggeration);
          }
          if (data.extra_params.cfg_weight !== undefined) {
            setChatterboxCfgWeight(data.extra_params.cfg_weight);
          }
          if (data.extra_params.temperature !== undefined) {
            setChatterboxTemperature(data.extra_params.temperature);
          }
        }
      }
    } catch (err: any) {
      console.error('Failed to load settings:', err);
      // Don't show error, just use defaults
    } finally {
      setIsLoadingSettings(false);
    }
  };

  const loadVoices = async () => {
    if (!settings.api_url) return;
    
    setIsLoadingVoices(true);
    setError('');
    try {
      const data = await apiClient.get<Voice[]>('/api/tts/voices');
      setVoices(data);
      
      // If current voice_id not in list, use first voice
      if (data.length > 0 && !data.find((v: Voice) => v.id === settings.voice_id)) {
        setSettings(prev => ({ ...prev, voice_id: data[0].id }));
      }
    } catch (err: any) {
      setError(`Failed to load voices: ${err.message}`);
      setVoices([]);
    } finally {
      setIsLoadingVoices(false);
    }
  };

  const handleProviderChange = async (providerType: string) => {
    // Check if we have saved config for this provider
    const savedConfig = providerConfigs[providerType];
    
    let newSettings: TTSSettings;
    
    if (savedConfig) {
      // Load saved configuration
      newSettings = {
        provider_type: providerType,
        api_url: savedConfig.api_url,
        api_key: savedConfig.api_key,
        voice_id: savedConfig.voice_id,
        speed: savedConfig.speed || 1.0,
        timeout: savedConfig.timeout || 30,
        extra_params: savedConfig.extra_params,
      };
      
      // Load provider-specific settings
      if (providerType === 'chatterbox' && savedConfig.extra_params) {
        setChatterboxExaggeration(savedConfig.extra_params.exaggeration || 0.5);
        setChatterboxCfgWeight(savedConfig.extra_params.cfg_weight || 0.5);
        setChatterboxTemperature(savedConfig.extra_params.temperature || 0.7);
      }
    } else {
      // Use default configuration
      newSettings = {
        provider_type: providerType,
        api_url: DEFAULT_PROVIDER_URLS[providerType] || '',
        api_key: '',
        voice_id: 'default',
        speed: 1.0,
        timeout: 30,
        extra_params: {},
      };
      
      // Reset provider-specific settings to defaults
      if (providerType === 'chatterbox') {
        setChatterboxExaggeration(0.5);
        setChatterboxCfgWeight(0.5);
        setChatterboxTemperature(0.7);
      }
    }
    
    setSettings(newSettings);
    setConnectionStatus('idle');
    setVoices([]);
    
    // Auto-test connection if we have saved config with URL
    if (savedConfig && savedConfig.api_url) {
      // Small delay to ensure state is updated
      setTimeout(() => {
        autoTestConnection(newSettings, savedConfig.voice_id);
      }, 100);
    }
  };

  const autoTestConnection = async (currentSettings: TTSSettings, savedVoiceId?: string) => {
    setIsTestingConnection(true);
    setError('');
    setConnectionStatus('idle');
    
    try {
      const response = await apiClient.post<{
        success: boolean;
        message: string;
        voices: Voice[];
      }>('/api/tts/test-connection', {
        provider_type: currentSettings.provider_type,
        api_url: currentSettings.api_url,
        api_key: currentSettings.api_key,
        voice_id: currentSettings.voice_id,
        speed: currentSettings.speed,
        timeout: currentSettings.timeout,
        extra_params: currentSettings.extra_params,
      });
      
      if (response.success) {
        setConnectionStatus('success');
        setVoices(response.voices);
        
        // Try to pre-select the saved voice if it exists in the list
        if (savedVoiceId && response.voices.some(v => v.id === savedVoiceId)) {
          setSettings(prev => ({ ...prev, voice_id: savedVoiceId }));
        } else if (response.voices.length > 0 && !currentSettings.voice_id) {
          // Auto-select first voice if none selected
          setSettings(prev => ({ ...prev, voice_id: response.voices[0].id }));
        }
      } else {
        setConnectionStatus('failed');
        console.warn('Auto connection test failed:', response.message);
      }
    } catch (err: any) {
      setConnectionStatus('failed');
      console.warn('Auto connection test failed:', err.message);
      // Don't show error to user for auto-test, just log it
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleTestConnection = async () => {
    setIsTestingConnection(true);
    setError('');
    setConnectionStatus('idle');
    
    try {
      const response = await apiClient.post<{
        success: boolean;
        message: string;
        voices: Voice[];
      }>('/api/tts/test-connection', {
        provider_type: settings.provider_type,
        api_url: settings.api_url,
        api_key: settings.api_key,
        voice_id: settings.voice_id,
        speed: settings.speed,
        timeout: settings.timeout,
        extra_params: settings.extra_params,
      });
      
      if (response.success) {
        setConnectionStatus('success');
        setSuccessMessage(response.message);
        setVoices(response.voices);
        
        // Try to keep the current voice_id if it exists in the list
        const currentVoiceExists = settings.voice_id && response.voices.some(v => v.id === settings.voice_id);
        
        if (currentVoiceExists) {
          // Keep current voice
          setSettings(prev => ({ ...prev, voice_id: settings.voice_id }));
        } else if (response.voices.length > 0) {
          // Auto-select first voice if current voice not found
          setSettings(prev => ({ ...prev, voice_id: response.voices[0].id }));
        }
        
        setTimeout(() => setSuccessMessage(''), 3000);
      } else {
        setConnectionStatus('failed');
        setError(response.message);
      }
    } catch (err: any) {
      setConnectionStatus('failed');
      setError(`Connection test failed: ${err.message}`);
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError('');
    setSuccessMessage('');
    
    try {
      // Include Chatterbox-specific params if Chatterbox is selected
      const extra_params = settings.provider_type === 'chatterbox' ? {
        exaggeration: chatterboxExaggeration,
        cfg_weight: chatterboxCfgWeight,
        temperature: chatterboxTemperature,
        ...settings.extra_params,
      } : settings.extra_params;
      
      // Prepare the full settings object with all fields
      const fullSettings = {
        ...settings,
        extra_params,
        // Explicitly include these fields to ensure they're saved
        tts_enabled: settings.tts_enabled,
        progressive_narration: settings.progressive_narration,
        chunk_size: settings.chunk_size,
        stream_audio: settings.stream_audio,
      };
      
      // Save to provider-specific config endpoint
      const savedConfig = await apiClient.put<TTSSettings>(
        `/api/tts/provider-configs/${settings.provider_type}`,
        fullSettings
      );
      
      // Update local provider configs cache
      setProviderConfigs(prev => ({
        ...prev,
        [settings.provider_type]: savedConfig,
      }));
      
      // Also update the global TTS settings (this is the main one that matters)
      await apiClient.put('/api/tts/settings', fullSettings);
      
      setSuccessMessage('Settings saved successfully!');
      setTimeout(() => {
        setSuccessMessage('');
        if (onSaved) onSaved();
      }, 2000);
    } catch (err: any) {
      setError(`Failed to save settings: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    setError('');
    
    // Stop any currently playing test audio
    if (testAudio) {
      testAudio.pause();
      testAudio.currentTime = 0;
    }
    
    try {
      const testText = "Hello! This is a test of the text to speech system. How do I sound?";
      
      const response = await fetch(`${apiClient.getBaseURL()}/api/tts/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiClient.getToken()}`,
        },
        body: JSON.stringify({
          text: testText,
          voice_id: settings.voice_id,
          speed: settings.speed,
        }),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || 'Failed to generate test audio');
      }
      
      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      
      const audio = new Audio(audioUrl);
      setTestAudio(audio);
      
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setIsTesting(false);
      };
      
      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        setError('Failed to play test audio');
        setIsTesting(false);
      };
      
      await audio.play();
      
    } catch (err: any) {
      setError(`Test failed: ${err.message}`);
      setIsTesting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <Volume2 className="w-6 h-6 text-purple-400" />
            <h2 className="text-xl font-bold text-white">Text-to-Speech Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Error/Success Messages */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}
          
          {successMessage && (
            <div className="bg-green-500/10 border border-green-500/50 rounded-lg p-4 flex items-start gap-3">
              <Check className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
              <p className="text-green-400 text-sm">{successMessage}</p>
            </div>
          )}

          {/* Global TTS Settings */}
          <div className="bg-purple-600/10 border border-purple-500/30 rounded-lg p-4 space-y-4">
            <h3 className="text-sm font-semibold text-purple-300">Global TTS Settings</h3>
            
            {/* Enable TTS Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <label className="text-sm font-medium text-gray-300">
                  Enable Text-to-Speech
                </label>
                <p className="text-xs text-gray-500 mt-1">
                  Turn TTS on or off for your stories
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSettings(prev => ({ ...prev, tts_enabled: !prev.tts_enabled }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.tts_enabled ? 'bg-purple-600' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.tts_enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Progressive Narration Toggle */}
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <label className="text-sm font-medium text-gray-300">
                  Progressive Narration
                </label>
                <p className="text-xs text-gray-500 mt-1">
                  Split scenes into chunks for faster audio playback start
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSettings(prev => ({ ...prev, progressive_narration: !prev.progressive_narration }))}
                disabled={!settings.tts_enabled}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.progressive_narration ? 'bg-purple-600' : 'bg-gray-700'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.progressive_narration ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Chunk Size - shown when Progressive is enabled */}
            {settings.progressive_narration && (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-300">
                  Chunk Size: {settings.chunk_size} characters
                </label>
                <input
                  type="range"
                  min="100"
                  max="500"
                  step="20"
                  value={settings.chunk_size || 280}
                  onChange={(e) => setSettings(prev => ({ ...prev, chunk_size: parseInt(e.target.value) }))}
                  disabled={!settings.tts_enabled}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500 disabled:opacity-50"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>100 (Sentence)</span>
                  <span>280 (Balanced)</span>
                  <span>500 (Paragraph)</span>
                </div>
                <p className="text-xs text-gray-500">
                  Smaller chunks = faster audio start, but more API calls.
                  Larger chunks = slower start, but smoother playback.
                </p>
              </div>
            )}
          </div>

          {/* Provider Selection */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              TTS Provider
            </label>
            <select
              value={settings.provider_type}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={isLoadingProviders || isLoadingSettings}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {isLoadingProviders ? (
                <option>Loading providers...</option>
              ) : (
                providers.map((provider) => (
                  <option key={provider.type} value={provider.type}>
                    {provider.name} {provider.supports_streaming ? '(Streaming)' : ''}
                  </option>
                ))
              )}
            </select>
            <p className="text-xs text-gray-500">
              Select your preferred TTS provider
            </p>
          </div>

          {/* API URL */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              API URL
            </label>
            <input
              type="text"
              value={settings.api_url}
              onChange={(e) => setSettings(prev => ({ ...prev, api_url: e.target.value }))}
              disabled={isLoadingSettings}
              placeholder="http://localhost:1234/v1"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            />
            <p className="text-xs text-gray-500">
              Base URL for the TTS API endpoint
            </p>
          </div>

          {/* API Key (Optional) */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              API Key <span className="text-gray-500">(optional)</span>
            </label>
            <input
              type="password"
              value={settings.api_key || ''}
              onChange={(e) => {
                setSettings(prev => ({ ...prev, api_key: e.target.value }));
                setConnectionStatus('idle');
              }}
              disabled={isLoadingSettings}
              placeholder="Leave empty if not required"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            />
          </div>

          {/* Test Connection Button */}
          <div className="space-y-2">
            <button
              onClick={handleTestConnection}
              disabled={isTestingConnection || isLoadingSettings || !settings.api_url}
              className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg transition-colors ${
                connectionStatus === 'success'
                  ? 'bg-green-600/20 border-2 border-green-500/50 text-green-400'
                  : connectionStatus === 'failed'
                  ? 'bg-red-600/20 border-2 border-red-500/50 text-red-400'
                  : 'bg-purple-600 hover:bg-purple-700 text-white'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {isTestingConnection ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Testing Connection...</span>
                </>
              ) : connectionStatus === 'success' ? (
                <>
                  <Check className="w-5 h-5" />
                  <span>Connection Successful</span>
                </>
              ) : connectionStatus === 'failed' ? (
                <>
                  <AlertCircle className="w-5 h-5" />
                  <span>Connection Failed - Retry</span>
                </>
              ) : (
                <>
                  <Volume2 className="w-5 h-5" />
                  <span>Test Connection</span>
                </>
              )}
            </button>
            <p className="text-xs text-gray-500">
              Test the connection and load available voices
            </p>
          </div>

          {/* Voice Selection */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              Voice
            </label>
            <div className="flex gap-2">
              <select
                value={settings.voice_id}
                onChange={(e) => setSettings(prev => ({ ...prev, voice_id: e.target.value }))}
                disabled={isLoadingVoices || isLoadingSettings || voices.length === 0}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
              >
                {isLoadingVoices ? (
                  <option>Loading voices...</option>
                ) : voices.length === 0 ? (
                  <option value="default">Test connection to load voices</option>
                ) : (
                  voices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name} {voice.language ? `(${voice.language})` : ''}
                    </option>
                  ))
                )}
              </select>
              {voices.length > 0 && (
                <button
                  onClick={() => setShowVoiceBrowser(true)}
                  disabled={isLoadingSettings}
                  className="flex items-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                  title="Browse and preview all voices"
                >
                  <Eye className="w-4 h-4" />
                  <span>See All</span>
                </button>
              )}
            </div>
            <p className="text-xs text-gray-500">
              Choose the voice for narration
              {voices.length > 0 && <> • Click "See All" to preview voices</>}
            </p>
          </div>

          {/* Chatterbox-Specific Settings */}
          {settings.provider_type === 'chatterbox' && (
            <div className="space-y-4 p-4 bg-purple-600/10 border border-purple-500/30 rounded-lg">
              <h3 className="text-sm font-semibold text-purple-300">Chatterbox Advanced Settings</h3>
              
              {/* Exaggeration */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-300">
                  Exaggeration: {chatterboxExaggeration.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="2"
                  step="0.05"
                  value={chatterboxExaggeration}
                  onChange={(e) => setChatterboxExaggeration(parseFloat(e.target.value))}
                  disabled={isLoadingSettings}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>0.1 (Subtle)</span>
                  <span>1.0 (Balanced)</span>
                  <span>2.0 (Dramatic)</span>
                </div>
                <p className="text-xs text-gray-500">
                  Controls emotional expression intensity
                </p>
              </div>

              {/* Pace (CFG Weight) */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-300">
                  Pace (CFG Weight): {chatterboxCfgWeight.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={chatterboxCfgWeight}
                  onChange={(e) => setChatterboxCfgWeight(parseFloat(e.target.value))}
                  disabled={isLoadingSettings}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>0.0 (Slow)</span>
                  <span>0.5 (Normal)</span>
                  <span>1.0 (Fast)</span>
                </div>
                <p className="text-xs text-gray-500">
                  Controls speech pacing
                </p>
              </div>

              {/* Temperature */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-300">
                  Temperature: {chatterboxTemperature.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0.05"
                  max="2"
                  step="0.05"
                  value={chatterboxTemperature}
                  onChange={(e) => setChatterboxTemperature(parseFloat(e.target.value))}
                  disabled={isLoadingSettings}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>0.05 (Consistent)</span>
                  <span>1.0 (Balanced)</span>
                  <span>2.0 (Creative)</span>
                </div>
                <p className="text-xs text-gray-500">
                  Controls randomness in speech generation
                </p>
              </div>
            </div>
          )}

          {/* Speed */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              Speech Speed: {settings.speed.toFixed(2)}x
            </label>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.1"
              value={settings.speed}
              onChange={(e) => setSettings(prev => ({ ...prev, speed: parseFloat(e.target.value) }))}
              disabled={isLoadingSettings}
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>0.5x (Slower)</span>
              <span>1.0x (Normal)</span>
              <span>2.0x (Faster)</span>
            </div>
          </div>

          {/* Timeout */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-300">
              Request Timeout (seconds)
            </label>
            <input
              type="number"
              min="5"
              max="120"
              value={settings.timeout}
              onChange={(e) => setSettings(prev => ({ ...prev, timeout: parseInt(e.target.value) }))}
              disabled={isLoadingSettings}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-800 bg-gray-900/50">
          <button
            onClick={handleTest}
            disabled={isTesting || isLoadingSettings || !settings.api_url}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isTesting ? (
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

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || isLoadingSettings || !settings.api_url}
              className="flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Save Settings</span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Voice Browser Modal */}
      <VoiceBrowserModal
        isOpen={showVoiceBrowser}
        onClose={() => setShowVoiceBrowser(false)}
        voices={voices}
        selectedVoiceId={settings.voice_id}
        onSelectVoice={(voiceId) => setSettings(prev => ({ ...prev, voice_id: voiceId }))}
        providerSettings={{
          provider_type: settings.provider_type,
          api_url: settings.api_url,
          api_key: settings.api_key,
          speed: settings.speed,
        }}
      />
    </div>
  );
}
