'use client';

import { useState, useEffect } from 'react';
import { X, Settings as SettingsIcon, Check, AlertCircle, Volume2, Loader2, Eye } from 'lucide-react';
import VoiceBrowserModal from './VoiceBrowserModal';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import { getThemeList, applyTheme } from '@/lib/themes';
import { useAuthStore } from '@/store';
import { UIPreferences, GenerationPreferences } from '@/types/settings';

interface WritingPreset {
  id?: number;
  name: string;
  system_prompt: string;
  summary_system_prompt: string;
}

interface LLMSettings {
  temperature: number;
  top_p: number;
  top_k: number;
  repetition_penalty: number;
  max_tokens: number;
  api_url: string;
  api_key: string;
  api_type: string;
  model_name: string;
  completion_mode: 'chat' | 'text';
  text_completion_template?: string;
  text_completion_preset?: string;
}

interface ContextSettings {
  max_tokens: number;
  keep_recent_scenes: number;
  summary_threshold: number;
  summary_threshold_tokens: number;
  enable_summarization: boolean;
  enable_semantic_memory?: boolean;
  context_strategy?: string;
  semantic_search_top_k?: number;
  semantic_scenes_in_context?: number;
  semantic_context_weight?: number;
  character_moments_in_context?: number;
  auto_extract_character_moments?: boolean;
  auto_extract_plot_events?: boolean;
  extraction_confidence_threshold?: number;
}

interface TTSProvider {
  type: string;
  name: string;
  supports_streaming: boolean;
}

interface TTSVoice {
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
  tts_enabled?: boolean;
  progressive_narration?: boolean;
  chunk_size?: number;
  stream_audio?: boolean;
  auto_play_last_scene?: boolean;
}

const DEFAULT_TTS_PROVIDER_URLS: Record<string, string> = {
  'openai-compatible': process.env.NEXT_PUBLIC_TTS_URL || 'http://localhost:1234',
  'chatterbox': process.env.NEXT_PUBLIC_CHATTERBOX_URL || 'http://localhost:8880',
  'kokoro': process.env.NEXT_PUBLIC_KOKORO_URL || 'http://localhost:8188',
};

const DEFAULT_TTS_PROVIDERS: TTSProvider[] = [
  { type: 'openai-compatible', name: 'OpenAI Compatible', supports_streaming: true },
  { type: 'chatterbox', name: 'Chatterbox', supports_streaming: true },
  { type: 'kokoro', name: 'Kokoro', supports_streaming: false },
];

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { user, token } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'interface' | 'writing' | 'llm' | 'context' | 'voice'>('interface');
  
  // UI Settings
  const [uiSettings, setUiSettings] = useState<UIPreferences>({
    color_theme: 'pure-dark',
    font_size: 'medium',
    show_token_info: false,
    show_context_info: false,
    notifications: true,
    scene_display_format: 'default',
    show_scene_titles: true,
    auto_open_last_story: false,
  });

  // Writing Styles
  const [writingPresets, setWritingPresets] = useState<WritingPreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [summaryPrompt, setSummaryPrompt] = useState('');
  const [presetName, setPresetName] = useState('');
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [savingPrompts, setSavingPrompts] = useState(false);
  const [showSavePresetDialog, setShowSavePresetDialog] = useState(false);
  
  // LLM Settings - Engine-specific storage
  const [engineSettings, setEngineSettings] = useState<Record<string, LLMSettings>>({});
  const [currentEngine, setCurrentEngine] = useState<string>('');
  const [llmSettings, setLlmSettings] = useState<LLMSettings>({
    temperature: 0.7,
    top_p: 0.9,
    top_k: 40,
    repetition_penalty: 1.1,
    max_tokens: 2048,
    api_url: '',
    api_key: '',
    api_type: '',
    model_name: '',
    completion_mode: 'chat',
    text_completion_template: '',
    text_completion_preset: 'llama3',
  });
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [testingConnection, setTestingConnection] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  
  // Context Settings
  const [contextSettings, setContextSettings] = useState<ContextSettings>({
    max_tokens: 8000,
    keep_recent_scenes: 5,
    summary_threshold: 10,
    summary_threshold_tokens: 4000,
    enable_summarization: true,
    enable_semantic_memory: false,
    context_strategy: 'linear',
    semantic_search_top_k: 5,
    semantic_scenes_in_context: 3,
    semantic_context_weight: 0.7,
    character_moments_in_context: 2,
    auto_extract_character_moments: false,
    auto_extract_plot_events: false,
    extraction_confidence_threshold: 0.8,
  });
  
  // Generation Preferences
  const [generationPrefs, setGenerationPrefs] = useState<GenerationPreferences>({
    default_genre: 'fantasy',
    default_tone: 'balanced',
    scene_length: 'medium',
    auto_choices: true,
    choices_count: 4,
  });
  
  // TTS Settings
  const [ttsProviders, setTtsProviders] = useState<TTSProvider[]>([]);
  const [ttsVoices, setTtsVoices] = useState<TTSVoice[]>([]);
  const [ttsSettings, setTtsSettings] = useState<TTSSettings>({
    provider_type: 'openai-compatible',
    api_url: DEFAULT_TTS_PROVIDER_URLS['openai-compatible'],
    voice_id: 'default',
    speed: 1.0,
    timeout: 30,
    tts_enabled: true,
    progressive_narration: false,
    chunk_size: 280,
    stream_audio: true,
    auto_play_last_scene: false,
  });
  
  // STT Settings
  const [sttEnabled, setSttEnabled] = useState(true);
  const [sttModel, setSttModel] = useState('small');
  const [sttModelDownloaded, setSttModelDownloaded] = useState<boolean | null>(null);
  const [vadModelDownloaded, setVadModelDownloaded] = useState<boolean | null>(null);
  const [isDownloadingSTTModel, setIsDownloadingSTTModel] = useState(false);
  const [sttDownloadError, setSttDownloadError] = useState<string | null>(null);
  const [ttsProviderConfigs, setTtsProviderConfigs] = useState<Record<string, TTSSettings>>({});
  const [isLoadingTTSProviders, setIsLoadingTTSProviders] = useState(false);
  const [isLoadingTTSVoices, setIsLoadingTTSVoices] = useState(false);
  const [isLoadingTTSSettings, setIsLoadingTTSSettings] = useState(false);
  const [isSavingTTS, setIsSavingTTS] = useState(false);
  const [isTestingTTS, setIsTestingTTS] = useState(false);
  const [isTestingTTSConnection, setIsTestingTTSConnection] = useState(false);
  const [ttsConnectionStatus, setTtsConnectionStatus] = useState<'idle' | 'success' | 'failed'>('idle');
  const [testAudio, setTestAudio] = useState<HTMLAudioElement | null>(null);
  const [showVoiceBrowser, setShowVoiceBrowser] = useState(false);
  const [chatterboxExaggeration, setChatterboxExaggeration] = useState(0.5);
  const [chatterboxCfgWeight, setChatterboxCfgWeight] = useState(3.0);
  const [chatterboxTemperature, setChatterboxTemperature] = useState(0.7);
  
  // Messages
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
      loadAllSettings();
      if (activeTab === 'writing') {
        loadWritingPrompts();
      }
      if (activeTab === 'voice') {
        console.log('Loading Voice data for tab');
        loadTTSProviders();
        loadCurrentTTSSettings();
        loadSTTSettings();
      }
    }
  }, [isOpen, activeTab]);
  
  const loadAllSettings = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        const settings = data.settings;
        
        // Load UI preferences
        if (settings?.ui_preferences) {
          setUiSettings({
            color_theme: settings.ui_preferences.color_theme || 'pure-dark',
            font_size: settings.ui_preferences.font_size || 'medium',
            show_token_info: settings.ui_preferences.show_token_info || false,
            show_context_info: settings.ui_preferences.show_context_info || false,
            notifications: settings.ui_preferences.notifications !== false,
            scene_display_format: settings.ui_preferences.scene_display_format || 'default',
            show_scene_titles: settings.ui_preferences.show_scene_titles !== false,
            auto_open_last_story: settings.ui_preferences.auto_open_last_story || false,
          });
        }
        
        // Load engine-specific LLM settings
        if (settings?.llm_settings) {
          // If we have engine-specific settings, load them
          if (settings.engine_settings && Object.keys(settings.engine_settings).length > 0) {
            setEngineSettings(settings.engine_settings);
            // Set current engine if available
            if (settings.current_engine && settings.current_engine.trim() !== '') {
              setCurrentEngine(settings.current_engine);
              const engineSettings = settings.engine_settings[settings.current_engine];
              if (engineSettings) {
                setLlmSettings(engineSettings);
              } else {
                // Fallback to llm_settings if engine-specific settings don't exist
                setLlmSettings(settings.llm_settings);
              }
            } else if (settings.llm_settings.api_type && settings.llm_settings.api_type.trim() !== '') {
              // If no current_engine but api_type exists, use api_type as engine
              setCurrentEngine(settings.llm_settings.api_type);
              setLlmSettings(settings.llm_settings);
            } else {
              setLlmSettings(settings.llm_settings);
            }
          } else {
            // Fallback to single LLM settings
            setLlmSettings({
              temperature: settings.llm_settings.temperature ?? 0.7,
              top_p: settings.llm_settings.top_p ?? 0.9,
              top_k: settings.llm_settings.top_k ?? 40,
              repetition_penalty: settings.llm_settings.repetition_penalty ?? 1.1,
              max_tokens: settings.llm_settings.max_tokens ?? 2048,
              api_url: settings.llm_settings.api_url || '',
              api_key: settings.llm_settings.api_key || '',
              api_type: settings.llm_settings.api_type || '',
              model_name: settings.llm_settings.model_name || '',
              completion_mode: settings.llm_settings.completion_mode || 'chat',
              text_completion_template: settings.llm_settings.text_completion_template || '',
              text_completion_preset: settings.llm_settings.text_completion_preset || 'llama3',
            });
            // Set current engine if api_type exists
            if (settings.llm_settings.api_type && settings.llm_settings.api_type.trim() !== '') {
              setCurrentEngine(settings.llm_settings.api_type);
            }
          }
        }
        
        // Load Context settings
        if (settings?.context_settings) {
          setContextSettings({
            max_tokens: settings.context_settings.max_tokens ?? 8000,
            keep_recent_scenes: settings.context_settings.keep_recent_scenes ?? 5,
            summary_threshold: settings.context_settings.summary_threshold ?? 10,
            summary_threshold_tokens: settings.context_settings.summary_threshold_tokens ?? 4000,
            enable_summarization: settings.context_settings.enable_summarization !== false,
            enable_semantic_memory: settings.context_settings.enable_semantic_memory || false,
            context_strategy: settings.context_settings.context_strategy || 'linear',
            semantic_search_top_k: settings.context_settings.semantic_search_top_k ?? 5,
            semantic_scenes_in_context: settings.context_settings.semantic_scenes_in_context ?? 3,
            semantic_context_weight: settings.context_settings.semantic_context_weight ?? 0.7,
            character_moments_in_context: settings.context_settings.character_moments_in_context ?? 2,
            auto_extract_character_moments: settings.context_settings.auto_extract_character_moments || false,
            auto_extract_plot_events: settings.context_settings.auto_extract_plot_events || false,
            extraction_confidence_threshold: settings.context_settings.extraction_confidence_threshold ?? 0.8,
          });
        }
        
        // Load Generation preferences
        if (settings?.generation_preferences) {
          setGenerationPrefs({
            default_genre: settings.generation_preferences.default_genre || 'fantasy',
            default_tone: settings.generation_preferences.default_tone || 'balanced',
            scene_length: settings.generation_preferences.scene_length || 'medium',
            auto_choices: settings.generation_preferences.auto_choices !== false,
            choices_count: settings.generation_preferences.choices_count ?? 4,
          });
        }

        // Load STT settings
        if (settings?.stt_settings) {
          setSttEnabled(settings.stt_settings.enabled ?? true);
          setSttModel(settings.stt_settings.model || 'small');
        } else {
          // Set defaults if not present
          setSttEnabled(true);
          setSttModel('small');
        }
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const loadUISettings = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.settings?.ui_preferences) {
          setUiSettings({
            color_theme: data.settings.ui_preferences.color_theme || 'pure-dark',
            font_size: data.settings.ui_preferences.font_size || 'medium',
            show_token_info: data.settings.ui_preferences.show_token_info || false,
            show_context_info: data.settings.ui_preferences.show_context_info || false,
            notifications: data.settings.ui_preferences.notifications !== false,
            scene_display_format: data.settings.ui_preferences.scene_display_format || 'default',
            show_scene_titles: data.settings.ui_preferences.show_scene_titles !== false,
            auto_open_last_story: data.settings.ui_preferences.auto_open_last_story || false,
          });
        }
      }
    } catch (error) {
      console.error('Failed to load UI settings:', error);
    }
  };

  const loadWritingPrompts = async () => {
    setLoadingPrompts(true);
    try {
      // Load all presets
      const presetsResponse = await fetch(`${getApiBaseUrl()}/api/writing-presets/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (presetsResponse.ok) {
        const presets = await presetsResponse.json();
        setWritingPresets(presets);
        
        // Find and load the active preset
        const activePreset = presets.find((p: WritingPreset & { is_active: boolean }) => p.is_active);
            if (activePreset) {
              setSelectedPresetId(activePreset.id || null);
              setSystemPrompt(activePreset.system_prompt || '');
              setSummaryPrompt(activePreset.summary_system_prompt || '');
              setPresetName(activePreset.name || '');
            } else if (presets.length > 0) {
              // If no active, load first preset
              setSelectedPresetId(presets[0].id || null);
              setSystemPrompt(presets[0].system_prompt || '');
              setSummaryPrompt(presets[0].summary_system_prompt || '');
              setPresetName(presets[0].name || '');
            } else {
          // No presets, load defaults from backend (prompts.yaml)
          await loadDefaultPrompts();
        }
      }
    } catch (error) {
      console.error('Failed to load writing prompts:', error);
      showMessage('Failed to load writing prompts', 'error');
    } finally {
      setLoadingPrompts(false);
    }
  };

  const loadDefaultPrompts = async () => {
    try {
      // Get default template from backend
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/default/template`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setSystemPrompt(data.system_prompt || 'You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
        setSummaryPrompt(data.summary_system_prompt || 'Summarize the key events and character developments concisely.');
        setPresetName('Default');
      } else {
        // Fallback if API doesn't exist
        setSystemPrompt('You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
        setSummaryPrompt('Summarize the key events and character developments concisely.');
        setPresetName('Default');
      }
    } catch (error) {
      console.error('Failed to load default prompts:', error);
      // Fallback to hardcoded defaults
      setSystemPrompt('You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
      setSummaryPrompt('Summarize the key events and character developments concisely.');
      setPresetName('Default');
    }
  };

  const loadPreset = (presetId: number) => {
    const preset = writingPresets.find(p => p.id === presetId);
    if (preset) {
      setSelectedPresetId(presetId);
      setSystemPrompt(preset.system_prompt);
      setSummaryPrompt(preset.summary_system_prompt);
      setPresetName(preset.name);
    }
  };

  const deletePreset = async (presetId: number) => {
    if (!confirm('Are you sure you want to delete this preset?')) return;
    
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/${presetId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        showMessage('Preset deleted', 'success');
        loadWritingPrompts(); // Reload
      } else {
        showMessage('Failed to delete preset', 'error');
      }
    } catch (error) {
      console.error('Failed to delete preset:', error);
      showMessage('Failed to delete preset', 'error');
    }
  };

  const updateUIPreference = async (key: keyof UIPreferences, value: any) => {
    const newSettings = { ...uiSettings, [key]: value };
    setUiSettings(newSettings);

    // Apply theme immediately for instant feedback
    if (key === 'color_theme') {
      applyTheme(value);
    } else if (key === 'font_size') {
      const root = document.documentElement;
      root.classList.remove('text-small', 'text-medium', 'text-large');
      root.classList.add(`text-${value}`);
    }

    // Auto-save
    try {
      await fetch(`${getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          ui_preferences: {
            [key]: value,
          },
        }),
      });
      
      showMessage('Settings saved', 'success');
      
      // Dispatch event for other components to listen to
      window.dispatchEvent(new CustomEvent('kahaniUISettingsChanged', {
        detail: newSettings
      }));
    } catch (error) {
      console.error('Failed to save setting:', error);
      showMessage('Failed to save setting', 'error');
    }
  };

  const saveWritingPrompts = async (makeActive: boolean = false) => {
    if (!presetName.trim()) {
      showMessage('Please enter a preset name', 'error');
      return;
    }

    // If no preset selected, always create new
    if (!selectedPresetId) {
      await createNewPreset(presetName, makeActive);
      return;
    }

    // If preset selected, update it
    setSavingPrompts(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/${selectedPresetId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
            body: JSON.stringify({
              name: presetName,
              system_prompt: systemPrompt,
              summary_system_prompt: summaryPrompt,
              is_active: makeActive,
            }),
      });

      if (response.ok) {
        showMessage(`Preset "${presetName}" updated successfully`, 'success');
        loadWritingPrompts(); // Reload list
      } else {
        showMessage('Failed to update preset', 'error');
      }
    } catch (error) {
      console.error('Failed to update preset:', error);
      showMessage('Failed to update preset', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const createNewPreset = async (name: string, makeActive: boolean = false) => {
    if (!name.trim()) {
      showMessage('Please enter a preset name', 'error');
      return;
    }

    setSavingPrompts(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
            body: JSON.stringify({
              name: name.trim(),
              system_prompt: systemPrompt,
              summary_system_prompt: summaryPrompt,
              is_active: makeActive,
            }),
      });

      if (response.ok) {
        const newPreset = await response.json();
        showMessage(`Preset "${name}" created successfully`, 'success');
        loadWritingPrompts(); // Reload list
        setSelectedPresetId(newPreset.id);
      } else {
        showMessage('Failed to create preset', 'error');
      }
    } catch (error) {
      console.error('Failed to create preset:', error);
      showMessage('Failed to create preset', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const saveAsNewPreset = async () => {
    const newName = prompt('Enter a name for the new preset:', presetName + ' (Copy)');
    if (!newName || !newName.trim()) return;

    setSavingPrompts(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newName.trim(),
          system_prompt: systemPrompt,
          summary_prompt: summaryPrompt,
          is_active: false,
        }),
      });

      if (response.ok) {
        const newPreset = await response.json();
        showMessage(`New preset "${newName}" created successfully`, 'success');
        loadWritingPrompts(); // Reload to show new preset
        setSelectedPresetId(newPreset.id);
        setPresetName(newName.trim());
      } else {
        showMessage('Failed to create new preset', 'error');
      }
    } catch (error) {
      console.error('Failed to create new preset:', error);
      showMessage('Failed to create new preset', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const setActivePreset = async (presetId: number) => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/${presetId}/activate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        showMessage('Preset activated', 'success');
        loadWritingPrompts(); // Reload to update active status
      } else {
        showMessage('Failed to activate preset', 'error');
      }
    } catch (error) {
      console.error('Failed to activate preset:', error);
      showMessage('Failed to activate preset', 'error');
    }
  };

  const showMessage = (msg: string, type: 'success' | 'error') => {
    setMessage(msg);
    setMessageType(type);
    setTimeout(() => setMessage(''), 3000);
  };


  const fetchAvailableModels = async () => {
    if (!llmSettings.api_url) {
      showMessage('Please enter an API URL first', 'error');
      return;
    }

    setLoadingModels(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/available-models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          api_url: llmSettings.api_url,
          api_key: llmSettings.api_key,
          api_type: llmSettings.api_type,
          model_name: llmSettings.model_name
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setAvailableModels(data.models);
          showMessage(`Found ${data.models.length} available models`, 'success');
        } else {
          showMessage(data.message || 'Failed to fetch models', 'error');
        }
      } else {
        throw new Error(`Request failed: ${response.status}`);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      showMessage(`Failed to fetch models: ${errorMessage}`, 'error');
    } finally {
      setLoadingModels(false);
    }
  };

  const handleEngineChange = (newEngine: string) => {
    // Save current settings to the current engine
    if (currentEngine && currentEngine !== '') {
      setEngineSettings(prev => ({
        ...prev,
        [currentEngine]: { ...llmSettings }
      }));
    }

    // Load settings for the new engine
    if (newEngine && engineSettings[newEngine]) {
      setLlmSettings(engineSettings[newEngine]);
    } else {
      // Default settings for new engine
      setLlmSettings({
        temperature: 0.7,
        top_p: 0.9,
        top_k: 40,
        repetition_penalty: 1.1,
        max_tokens: 2048,
        api_url: '',
        api_key: '',
        api_type: newEngine,
        model_name: '',
        completion_mode: 'chat',
        text_completion_template: '',
        text_completion_preset: 'llama3',
      });
    }

    setCurrentEngine(newEngine);
    setAvailableModels([]); // Clear models when switching engines
  };

  const saveEngineSettings = async () => {
    try {
      // Update engine settings with current values
      const updatedEngineSettings = {
        ...engineSettings,
      };
      
      // Only save current engine settings if an engine is selected
      if (currentEngine && currentEngine.trim() !== '') {
        updatedEngineSettings[currentEngine] = { ...llmSettings };
      }
      
      setEngineSettings(updatedEngineSettings);

      // Save to backend
      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          engine_settings: {
            engine_settings: updatedEngineSettings,
            current_engine: currentEngine || '',
          },
          llm_settings: {
            ...llmSettings,
            api_url: llmSettings.api_url || '',
            api_key: llmSettings.api_key || '',
            api_type: llmSettings.api_type || '',
            model_name: llmSettings.model_name || '',
          }, // Also save as current LLM settings for backward compatibility
        }),
      });

      if (response.ok) {
        showMessage('Engine settings saved!', 'success');
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to save settings' }));
        showMessage(`Failed to save engine settings: ${errorData.detail || 'Unknown error'}`, 'error');
      }
    } catch (error) {
      showMessage('Error saving engine settings', 'error');
    }
  };

  // TTS Functions
  const loadTTSProviders = async () => {
    setIsLoadingTTSProviders(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/tts/providers`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('TTS Providers loaded:', data);
        setTtsProviders(data || DEFAULT_TTS_PROVIDERS);
      } else {
        console.error('Failed to load TTS providers:', response.status, response.statusText);
        console.log('Using default TTS providers');
        setTtsProviders(DEFAULT_TTS_PROVIDERS);
        showMessage('Using default TTS providers', 'error');
      }
    } catch (error) {
      console.error('Error loading TTS providers:', error);
      console.log('Using default TTS providers due to error');
      setTtsProviders(DEFAULT_TTS_PROVIDERS);
      showMessage('Using default TTS providers', 'error');
    } finally {
      setIsLoadingTTSProviders(false);
    }
  };

  const loadAllTTSProviderConfigs = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/tts/provider-configs`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const configs = await response.json();
        const configMap: Record<string, TTSSettings> = {};
        configs.forEach((config: TTSSettings) => {
          configMap[config.provider_type] = config;
        });
        setTtsProviderConfigs(configMap);
      }
    } catch (error) {
      console.error('Error loading TTS provider configs:', error);
    }
  };

  const loadCurrentTTSSettings = async () => {
    setIsLoadingTTSSettings(true);
    try {
      // Load global TTS settings
      const globalResponse = await fetch(`${getApiBaseUrl()}/api/tts/settings`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (globalResponse.ok) {
        const globalData = await globalResponse.json();
        
        // Load current provider settings
        const providerResponse = await fetch(`${getApiBaseUrl()}/api/tts/provider-configs`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });
        
        if (providerResponse.ok) {
          const providerConfigs = await providerResponse.json();
          const configMap: Record<string, TTSSettings> = {};
          providerConfigs.forEach((config: TTSSettings) => {
            configMap[config.provider_type] = config;
          });
          setTtsProviderConfigs(configMap);
          
          // Find the current provider from global settings or default to first available
          const currentProvider = globalData.provider_type || configMap[Object.keys(configMap)[0]]?.provider_type || 'openai-compatible';
          const currentConfig = configMap[currentProvider];
          
          if (currentConfig) {
            // Merge global settings with provider-specific settings
            const mergedSettings: TTSSettings = {
              ...currentConfig,
              // Ensure provider_type is set correctly
              provider_type: currentProvider,
              // Override with global settings
              tts_enabled: globalData.tts_enabled !== undefined ? globalData.tts_enabled : currentConfig.tts_enabled,
              progressive_narration: globalData.progressive_narration !== undefined ? globalData.progressive_narration : currentConfig.progressive_narration,
              chunk_size: globalData.chunk_size !== undefined ? globalData.chunk_size : currentConfig.chunk_size,
              stream_audio: globalData.stream_audio !== undefined ? globalData.stream_audio : currentConfig.stream_audio,
              auto_play_last_scene: globalData.auto_play_last_scene !== undefined ? globalData.auto_play_last_scene : currentConfig.auto_play_last_scene,
            };
            
            setTtsSettings(mergedSettings);
            
            // Load provider-specific settings
            if (currentProvider === 'chatterbox' && currentConfig.extra_params) {
              setChatterboxExaggeration(currentConfig.extra_params.exaggeration || 0.5);
              setChatterboxCfgWeight(currentConfig.extra_params.cfg_weight || 3.0);
              setChatterboxTemperature(currentConfig.extra_params.temperature || 0.7);
            }
            
            // Load voices for the current provider
            if (mergedSettings.api_url) {
              loadTTSVoices();
            }
          } else {
            // Provider config doesn't exist for current provider, use global settings
            if (globalData.provider_type) {
              const fallbackSettings: TTSSettings = {
                provider_type: globalData.provider_type,
                api_url: globalData.api_url || '',
                api_key: globalData.api_key || '',
                voice_id: globalData.voice_id || 'default',
                speed: globalData.speed || 1.0,
                timeout: globalData.timeout || 30,
                extra_params: globalData.extra_params || {},
                tts_enabled: globalData.tts_enabled !== undefined ? globalData.tts_enabled : true,
                progressive_narration: globalData.progressive_narration !== undefined ? globalData.progressive_narration : false,
                chunk_size: globalData.chunk_size !== undefined ? globalData.chunk_size : 280,
                stream_audio: globalData.stream_audio !== undefined ? globalData.stream_audio : true,
                auto_play_last_scene: globalData.auto_play_last_scene !== undefined ? globalData.auto_play_last_scene : false,
              };
              setTtsSettings(fallbackSettings);
            }
          }
        } else {
          // If no provider configs exist but global settings has provider_type, use it
          if (globalData.provider_type) {
            const fallbackSettings: TTSSettings = {
              provider_type: globalData.provider_type,
              api_url: globalData.api_url || '',
              api_key: globalData.api_key || '',
              voice_id: globalData.voice_id || 'default',
              speed: globalData.speed || 1.0,
              timeout: globalData.timeout || 30,
              extra_params: globalData.extra_params || {},
              tts_enabled: globalData.tts_enabled !== undefined ? globalData.tts_enabled : true,
              progressive_narration: globalData.progressive_narration !== undefined ? globalData.progressive_narration : false,
              chunk_size: globalData.chunk_size !== undefined ? globalData.chunk_size : 280,
              stream_audio: globalData.stream_audio !== undefined ? globalData.stream_audio : true,
              auto_play_last_scene: globalData.auto_play_last_scene !== undefined ? globalData.auto_play_last_scene : false,
            };
            setTtsSettings(fallbackSettings);
          }
        }
      }
    } catch (error) {
      console.error('Error loading TTS settings:', error);
      showMessage('Error loading TTS settings', 'error');
    } finally {
      setIsLoadingTTSSettings(false);
    }
  };

  const loadTTSVoices = async () => {
    if (!ttsSettings.provider_type || !ttsSettings.api_url) return;
    
    setIsLoadingTTSVoices(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/tts/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider_type: ttsSettings.provider_type,
          api_url: ttsSettings.api_url,
          api_key: ttsSettings.api_key,
          timeout: ttsSettings.timeout,
          extra_params: ttsSettings.extra_params,
        }),
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.voices) {
          setTtsVoices(data.voices || []);
          setTtsConnectionStatus('success');
        } else {
          setTtsConnectionStatus('failed');
          showMessage(data.message || 'Failed to load voices', 'error');
        }
      } else {
        setTtsConnectionStatus('failed');
        showMessage('Failed to load voices', 'error');
      }
    } catch (error) {
      console.error('Error loading voices:', error);
      setTtsConnectionStatus('failed');
      showMessage('Error loading voices', 'error');
    } finally {
      setIsLoadingTTSVoices(false);
    }
  };

  const handleTTSProviderChange = (providerType: string) => {
    // Save current settings to the current provider
    if (ttsSettings.provider_type && ttsSettings.provider_type !== '') {
      setTtsProviderConfigs(prev => ({
        ...prev,
        [ttsSettings.provider_type]: { ...ttsSettings }
      }));
    }

    // Load settings for the new provider
    const savedConfig = ttsProviderConfigs[providerType];
    
    if (savedConfig) {
      // Load saved configuration
      const newSettings: TTSSettings = {
        provider_type: providerType,
        api_url: savedConfig.api_url,
        api_key: savedConfig.api_key,
        voice_id: savedConfig.voice_id,
        speed: savedConfig.speed || 1.0,
        timeout: savedConfig.timeout || 30,
        extra_params: savedConfig.extra_params,
        // Preserve global TTS settings from current settings
        tts_enabled: ttsSettings.tts_enabled,
        progressive_narration: ttsSettings.progressive_narration,
        chunk_size: ttsSettings.chunk_size,
        stream_audio: ttsSettings.stream_audio,
        auto_play_last_scene: ttsSettings.auto_play_last_scene,
      };
      
      setTtsSettings(newSettings);
      
      // Load provider-specific settings
      if (providerType === 'chatterbox' && savedConfig.extra_params) {
        setChatterboxExaggeration(savedConfig.extra_params.exaggeration || 0.5);
        setChatterboxCfgWeight(savedConfig.extra_params.cfg_weight || 3.0);
        setChatterboxTemperature(savedConfig.extra_params.temperature || 0.7);
      }
    } else {
      // Default settings for new provider
      setTtsSettings({
        provider_type: providerType,
        api_url: DEFAULT_TTS_PROVIDER_URLS[providerType] || '',
        voice_id: 'default',
        speed: 1.0,
        timeout: 30,
        tts_enabled: ttsSettings.tts_enabled,
        progressive_narration: ttsSettings.progressive_narration,
        chunk_size: ttsSettings.chunk_size,
        stream_audio: ttsSettings.stream_audio,
        auto_play_last_scene: ttsSettings.auto_play_last_scene,
      });
    }
    
    setTtsVoices([]);
    setTtsConnectionStatus('idle');
  };

  const handleTTSSave = async () => {
    setIsSavingTTS(true);
    try {
      // Include Chatterbox-specific params if Chatterbox is selected
      const extra_params = ttsSettings.provider_type === 'chatterbox' ? {
        exaggeration: chatterboxExaggeration,
        cfg_weight: chatterboxCfgWeight,
        temperature: chatterboxTemperature,
        ...ttsSettings.extra_params,
      } : ttsSettings.extra_params;
      
      // Prepare the full settings object with all fields
      const fullSettings = {
        ...ttsSettings,
        extra_params,
        // Explicitly include these fields to ensure they're saved
        tts_enabled: ttsSettings.tts_enabled,
        progressive_narration: ttsSettings.progressive_narration,
        chunk_size: ttsSettings.chunk_size,
        stream_audio: ttsSettings.stream_audio,
        auto_play_last_scene: ttsSettings.auto_play_last_scene,
      };

      // Save provider-specific config
      const providerConfigResponse = await fetch(`${getApiBaseUrl()}/api/tts/provider-configs/${ttsSettings.provider_type}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(fullSettings),
      });

      if (!providerConfigResponse.ok) {
        throw new Error('Failed to save provider config');
      }

      // Save global TTS settings
      const globalSettingsResponse = await fetch(`${getApiBaseUrl()}/api/tts/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(fullSettings),
      });

      if (!globalSettingsResponse.ok) {
        throw new Error('Failed to save global settings');
      }

      // Update local provider configs
      setTtsProviderConfigs(prev => ({
        ...prev,
        [ttsSettings.provider_type]: fullSettings
      }));

      showMessage('TTS settings saved!', 'success');
      // Reload settings to ensure consistency
      await loadCurrentTTSSettings();
    } catch (error) {
      console.error('Error saving TTS settings:', error);
      showMessage('Error saving TTS settings', 'error');
    } finally {
      setIsSavingTTS(false);
    }
  };

  const handleTTSTest = async () => {
    if (!ttsSettings.api_url) {
      showMessage('Please configure API settings first', 'error');
      return;
    }

    setIsTestingTTS(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/tts/test`, {
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
          text: 'This is a test of the text-to-speech system.',
          extra_params: ttsSettings.provider_type === 'chatterbox' ? {
            exaggeration: chatterboxExaggeration,
            cfg_weight: chatterboxCfgWeight,
            temperature: chatterboxTemperature,
          } : undefined,
        }),
      });

      if (response.ok) {
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        
        // Stop any existing test audio
        if (testAudio) {
          testAudio.pause();
          testAudio.src = '';
        }
        
        const audio = new Audio(audioUrl);
        setTestAudio(audio);
        
        audio.play().catch(error => {
          console.error('Error playing test audio:', error);
          showMessage('Error playing test audio', 'error');
        });
        
        showMessage('Test audio generated successfully!', 'success');
      } else {
        showMessage('Failed to generate test audio', 'error');
      }
    } catch (error) {
      console.error('Error testing TTS:', error);
      showMessage('Error testing TTS', 'error');
    } finally {
      setIsTestingTTS(false);
    }
  };

  const handleTTSTestConnection = async () => {
    if (!ttsSettings.api_url) {
      showMessage('Please enter an API URL first', 'error');
      return;
    }

    setIsTestingTTSConnection(true);
    setTtsConnectionStatus('idle');
    
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/tts/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider_type: ttsSettings.provider_type,
          api_url: ttsSettings.api_url,
          api_key: ttsSettings.api_key,
          timeout: ttsSettings.timeout,
          extra_params: ttsSettings.extra_params,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setTtsConnectionStatus('success');
          showMessage('Connection successful!', 'success');
          // Load voices after successful connection
          if (data.voices) {
            setTtsVoices(data.voices || []);
          }
        } else {
          setTtsConnectionStatus('failed');
          showMessage(data.message || 'Connection failed', 'error');
        }
      } else {
        setTtsConnectionStatus('failed');
        showMessage('Connection failed', 'error');
      }
    } catch (error) {
      console.error('Error testing connection:', error);
      setTtsConnectionStatus('failed');
      showMessage('Error testing connection', 'error');
    } finally {
      setIsTestingTTSConnection(false);
    }
  };

  // STT Functions
  const loadSTTSettings = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        const sttSettings = data.settings?.stt_settings;
        if (sttSettings) {
          setSttEnabled(sttSettings.enabled);
          setSttModel(sttSettings.model);
        }
      }
      
      // Check model download status
      await checkSTTModelStatus();
    } catch (error) {
      console.error('Error loading STT settings:', error);
    }
  };

  const checkSTTModelStatus = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/stt-model-status`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        // Handle new response format with whisper and vad objects
        if (data.whisper && data.vad) {
          setSttModelDownloaded(data.whisper.downloaded);
          setVadModelDownloaded(data.vad.downloaded);
        } else if (data.downloaded !== undefined) {
          // Fallback for old format
          setSttModelDownloaded(data.downloaded);
          setVadModelDownloaded(null);
        }
      }
    } catch (error) {
      console.error('Error checking STT model status:', error);
      // Don't update state on error to prevent flickering
    }
  };

  const downloadSTTModel = async () => {
    setIsDownloadingSTTModel(true);
    setSttDownloadError(null);
    
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/download-stt-model`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          model_name: sttModel,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        showMessage(data.message || 'STT models downloaded successfully!', 'success');
        // Wait a bit before checking status to ensure download completes
        setTimeout(async () => {
          await checkSTTModelStatus();
          // Optimistically set both to true on success
          if (data.whisper?.success) setSttModelDownloaded(true);
          if (data.vad?.success) setVadModelDownloaded(true);
        }, 3000);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to download STT models' }));
        setSttDownloadError(errorData.detail || 'Failed to download STT models');
        showMessage(`Error downloading STT models: ${errorData.detail || 'Unknown error'}`, 'error');
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Failed to download STT models';
      setSttDownloadError(errorMsg);
      showMessage('Error downloading STT models', 'error');
    } finally {
      setIsDownloadingSTTModel(false);
    }
  };

  const handleSTTSave = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          stt_settings: {
            enabled: sttEnabled,
            model: sttModel || 'small',
          },
        }),
      });

      if (response.ok) {
        showMessage('STT settings saved!', 'success');
        // Reload settings to ensure consistency
        loadSTTSettings();
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to save STT settings' }));
        showMessage(`Error saving STT settings: ${errorData.detail || 'Unknown error'}`, 'error');
      }
    } catch (error) {
      console.error('Error saving STT settings:', error);
      showMessage('Error saving STT settings', 'error');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="theme-card rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700 theme-banner">
          <div className="flex items-center gap-3">
            <SettingsIcon className="w-6 h-6 text-white" />
            <h2 className="text-xl font-bold text-white">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-gray-700 bg-gray-800/50 overflow-x-auto">
          {[
            { id: 'interface', name: 'Interface' },
            { id: 'writing', name: 'Writing Styles' },
            { id: 'llm', name: 'LLM Settings' },
            { id: 'context', name: 'Generation & Context' },
            { id: 'voice', name: 'Voice Settings' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex-1 py-3 px-4 text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'theme-btn-primary border-b-2 theme-border-accent'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-180px)]">
          {/* Messages */}
          {message && (
            <div className={`mb-4 p-4 rounded-lg flex items-start gap-3 ${
              messageType === 'success' 
                ? 'bg-green-500/10 border border-green-500/50' 
                : 'bg-red-500/10 border border-red-500/50'
            }`}>
              {messageType === 'success' ? (
                <Check className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              )}
              <p className={`text-sm ${messageType === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                {message}
              </p>
            </div>
          )}

          {/* Interface Tab */}
          {activeTab === 'interface' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-4">Interface Preferences</h3>
                
                <div className="space-y-4">
                  {/* Color Theme */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Color Theme</label>
                    <select
                      value={uiSettings.color_theme}
                      onChange={(e) => updateUIPreference('color_theme', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      {getThemeList().map(theme => (
                        <option key={theme.value} value={theme.value}>
                          {theme.label} - {theme.description}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-400 mt-1">
                      Choose your preferred color scheme for the entire app
                    </p>
                  </div>

                  {/* Font Size */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Font Size</label>
                    <select
                      value={uiSettings.font_size}
                      onChange={(e) => updateUIPreference('font_size', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      <option value="small">Small</option>
                      <option value="medium">Medium</option>
                      <option value="large">Large</option>
                    </select>
                  </div>



                  {/* Checkboxes */}
                  <div className="space-y-3 pt-4 border-t border-gray-700">

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.show_context_info}
                        onChange={(e) => updateUIPreference('show_context_info', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Show context management details</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.notifications}
                        onChange={(e) => updateUIPreference('notifications', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Enable notifications</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.auto_open_last_story}
                        onChange={(e) => updateUIPreference('auto_open_last_story', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Auto-open last story on login</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Save Button */}
              <div className="flex justify-end pt-4 border-t border-gray-700">
                <button
                  onClick={async () => {
                    try {
                      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
                        method: 'PUT',
                        headers: {
                          'Content-Type': 'application/json',
                          'Authorization': `Bearer ${token}`,
                        },
                        body: JSON.stringify({
                          ui_preferences: uiSettings,
                        }),
                      });
                      
                      if (response.ok) {
                        showMessage('Interface settings saved', 'success');
                      } else {
                        showMessage('Error saving settings', 'error');
                      }
                    } catch (error) {
                      console.error('Failed to save interface settings:', error);
                      showMessage('Error saving settings', 'error');
                    }
                  }}
                  className="px-6 py-2 theme-btn-primary rounded-lg font-semibold"
                >
                  Save Interface Settings
                </button>
              </div>
            </div>
          )}

          {/* Writing Styles Tab */}
          {activeTab === 'writing' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">Writing Styles</h3>
                <p className="text-sm text-gray-400 mb-4">
                  Create and manage multiple writing style presets
                </p>

                {loadingPrompts ? (
                  <div className="text-center py-8 text-gray-400">Loading presets...</div>
                ) : (
                  <div className="space-y-6">
                    {/* Preset Selector */}
                    <div className="flex gap-3">
                      <div className="flex-1">
                        <label className="block text-sm font-medium text-white mb-2">
                          Select Preset
                        </label>
                        <select
                          value={selectedPresetId || 'default'}
                          onChange={(e) => {
                            if (e.target.value === 'new') {
                              setSelectedPresetId(null);
                              setPresetName('');
                              setSystemPrompt('');
                              setSummaryPrompt('');
                            } else if (e.target.value === 'default') {
                              setSelectedPresetId(null);
                              loadDefaultPrompts();
                            } else if (e.target.value) {
                              loadPreset(Number(e.target.value));
                            }
                          }}
                          className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        >
                          <option value="default">📄 Default (from prompts.yaml)</option>
                          <option value="new">+ Create New Preset</option>
                          {writingPresets.map((preset) => (
                            <option key={preset.id} value={preset.id}>
                              {preset.name} {writingPresets.find(p => p.id === preset.id && (p as any).is_active) ? '⭐ (Active)' : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-end gap-2">
                        {selectedPresetId && (
                          <>
                            <button
                              onClick={() => setActivePreset(selectedPresetId)}
                              className="px-4 py-2 theme-btn-primary rounded-md font-medium"
                              title="Set as active preset"
                            >
                              ✓ Set Active
                            </button>
                            <button
                              onClick={() => deletePreset(selectedPresetId)}
                              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md font-medium"
                              title="Delete preset"
                            >
                              🗑️
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Preset Name */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Preset Name
                      </label>
                      <input
                        type="text"
                        value={presetName}
                        onChange={(e) => setPresetName(e.target.value)}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        placeholder="e.g., NSFW Adventure, Family Friendly, Poetic Style"
                      />
                    </div>

                    {/* System Prompt */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        System Prompt
                      </label>
                      <p className="text-xs text-gray-400 mb-2">
                        This defines how the AI writes (tone, style, NSFW settings)
                      </p>
                      <textarea
                        value={systemPrompt}
                        onChange={(e) => setSystemPrompt(e.target.value)}
                        rows={8}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-sm"
                        placeholder="Enter your system prompt..."
                      />
                    </div>

                    {/* Summary Prompt */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Summary Prompt
                      </label>
                      <p className="text-xs text-gray-400 mb-2">
                        This defines how the AI creates summaries
                      </p>
                      <textarea
                        value={summaryPrompt}
                        onChange={(e) => setSummaryPrompt(e.target.value)}
                        rows={8}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-sm"
                        placeholder="Enter your summary prompt..."
                      />
                    </div>

                    {/* Action Buttons */}
                    <div className="flex gap-3">
                      <button
                        onClick={() => saveWritingPrompts(false)}
                        disabled={savingPrompts}
                        className="flex-1 theme-btn-primary px-6 py-3 rounded-lg font-semibold disabled:opacity-50"
                      >
                        {savingPrompts ? 'Saving...' : selectedPresetId ? 'Update Preset' : 'Save Preset'}
                      </button>
                      <button
                        onClick={saveAsNewPreset}
                        className="px-6 py-3 theme-btn-secondary rounded-lg font-semibold"
                      >
                        💾 Save As New
                      </button>
                      {selectedPresetId && (
                        <button
                          onClick={() => saveWritingPrompts(true)}
                          disabled={savingPrompts}
                          className="px-6 py-3 theme-btn-primary rounded-lg font-semibold disabled:opacity-50"
                        >
                          Save & Activate
                        </button>
                      )}
                    </div>

                    <div className="text-xs text-gray-400 bg-blue-900/20 border border-blue-700/30 rounded-lg p-3">
                      💡 <strong>Tip:</strong> Create multiple presets for different writing styles. 
                      The active preset will be used for all story generation.
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* LLM Settings Tab */}
          {activeTab === 'llm' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">LLM Settings</h3>
                <p className="text-sm text-gray-400 mb-6">
                  Configure your language model provider and generation parameters
                </p>

                {/* API Configuration */}
                <div className="space-y-4 mb-8">
                  <h4 className="text-md font-semibold text-white mb-3">API Configuration</h4>
                  
                  {/* API Type - Moved to top */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">API Engine</label>
                    <select
                      value={currentEngine}
                      onChange={(e) => handleEngineChange(e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      <option value="">Select API Engine...</option>
                      <option value="openai-compatible">OpenAI Compatible</option>
                      <option value="tabbyapi">TabbyAPI</option>
                      <option value="openai">OpenAI Official</option>
                      <option value="koboldcpp">KoboldCpp</option>
                      <option value="ollama">Ollama</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">API URL</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={llmSettings.api_url}
                        onChange={(e) => setLlmSettings({ ...llmSettings, api_url: e.target.value })}
                        className="flex-1 bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        placeholder="https://api.openai.com/v1"
                      />
                      <button
                        onClick={async () => {
                          setTestingConnection(true);
                          try {
                            const response = await fetch(`${getApiBaseUrl()}/api/settings/test-api-connection`, {
                              method: 'POST',
                              headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${token}`,
                              },
                              body: JSON.stringify({
                                api_url: llmSettings.api_url,
                                api_key: llmSettings.api_key,
                                api_type: llmSettings.api_type,
                                model_name: llmSettings.model_name,
                              }),
                            });
                            if (response.ok) {
                              const result = await response.json();
                              if (result.success) {
                                showMessage(result.message || 'Connection successful!', 'success');
                                // Auto-fetch models on successful connection
                                fetchAvailableModels();
                              } else {
                                showMessage(result.message || 'Connection failed', 'error');
                              }
                            } else {
                              const errorData = await response.json().catch(() => ({ detail: 'Connection failed' }));
                              showMessage(`Connection failed: ${errorData.detail || 'Unknown error'}`, 'error');
                            }
                          } catch (error) {
                            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
                            showMessage(`Connection error: ${errorMessage}`, 'error');
                          } finally {
                            setTestingConnection(false);
                          }
                        }}
                        disabled={testingConnection}
                        className="px-4 py-2 theme-btn-secondary rounded-md font-medium disabled:opacity-50"
                      >
                        {testingConnection ? 'Testing...' : 'Test'}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">API Key</label>
                    <input
                      type="password"
                      value={llmSettings.api_key}
                      onChange={(e) => setLlmSettings({ ...llmSettings, api_key: e.target.value })}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                      placeholder="sk-..."
                    />
                  </div>


                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Model Name</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={llmSettings.model_name}
                        onChange={(e) => setLlmSettings({ ...llmSettings, model_name: e.target.value })}
                        className="flex-1 bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        placeholder="gpt-4"
                      />
                      <button
                        onClick={fetchAvailableModels}
                        disabled={loadingModels || !llmSettings.api_url}
                        className="px-4 py-2 theme-btn-primary rounded-md font-medium disabled:opacity-50"
                      >
                        {loadingModels ? 'Loading...' : 'Fetch Models'}
                      </button>
                    </div>
                  </div>

                  {/* Available Models Dropdown */}
                  {availableModels.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">Select Model</label>
                      <select
                        value={llmSettings.model_name || ''}
                        onChange={(e) => setLlmSettings({ ...llmSettings, model_name: e.target.value })}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                      >
                        <option value="">Select a model...</option>
                        {availableModels.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                      <div className="text-xs text-gray-400 mt-1">
                        {availableModels.length} models available
                      </div>
                    </div>
                  )}
                </div>

                {/* Generation Parameters */}
                <div className="space-y-4">
                  <h4 className="text-md font-semibold text-white mb-3">Generation Parameters</h4>
                  
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Temperature: {llmSettings.temperature}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={llmSettings.temperature}
                      onChange={(e) => setLlmSettings({ ...llmSettings, temperature: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-xs text-gray-400 mt-1">Controls randomness (0=focused, 2=creative)</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Top P: {llmSettings.top_p}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={llmSettings.top_p}
                      onChange={(e) => setLlmSettings({ ...llmSettings, top_p: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-xs text-gray-400 mt-1">Nucleus sampling threshold</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Max Tokens: {llmSettings.max_tokens}
                    </label>
                    <input
                      type="range"
                      min="100"
                      max="4096"
                      step="100"
                      value={llmSettings.max_tokens}
                      onChange={(e) => setLlmSettings({ ...llmSettings, max_tokens: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-xs text-gray-400 mt-1">Maximum response length</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Repetition Penalty: {llmSettings.repetition_penalty}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="2"
                      step="0.1"
                      value={llmSettings.repetition_penalty}
                      onChange={(e) => setLlmSettings({ ...llmSettings, repetition_penalty: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-xs text-gray-400 mt-1">Penalizes repetitive text</p>
                  </div>
                </div>

          {/* Save Button */}
          <div className="flex justify-end pt-4 border-t border-gray-700">
            <button
              onClick={saveEngineSettings}
              className="px-6 py-2 theme-btn-primary rounded-lg font-semibold"
            >
              Save {currentEngine ? currentEngine.replace('-', ' ').toUpperCase() : 'Engine'} Settings
            </button>
          </div>
              </div>
            </div>
          )}

          {/* Generation & Context Tab */}
          {activeTab === 'context' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">Generation & Context</h3>
                <p className="text-sm text-gray-400 mb-6">
                  Configure context management and generation preferences
                </p>

                {/* Context Management */}
                <div className="space-y-6 mb-8">
                  <h4 className="text-md font-semibold text-white mb-3">Context Management</h4>
                  
                  {/* Enable Summarization */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={contextSettings.enable_summarization || false}
                        onChange={(e) => setContextSettings({ ...contextSettings, enable_summarization: e.target.checked })}
                        className="mr-2"
                      />
                      Enable intelligent context summarization
                    </label>
                    <div className="text-xs text-gray-400 mt-1">
                      Automatically summarize older scenes for long stories
                    </div>
                  </div>

                  {/* Max Tokens */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Context Budget: {(contextSettings.max_tokens || 4000).toLocaleString()} tokens
                    </label>
                    <input
                      type="number"
                      min="1000"
                      max="1000000"
                      step="8"
                      value={contextSettings.max_tokens || 4000}
                      onChange={(e) => {
                        const value = parseInt(e.target.value) || 4000;
                        setContextSettings({ ...contextSettings, max_tokens: value });
                      }}
                      onBlur={(e) => {
                        // Round to nearest multiple of 8 when user finishes editing
                        const value = parseInt(e.target.value) || 4000;
                        const rounded = Math.round(value / 8) * 8;
                        if (value !== rounded) {
                          setContextSettings({ ...contextSettings, max_tokens: rounded });
                        }
                      }}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white mb-2"
                    />
                    <input
                      type="range"
                      min="1000"
                      max="100000"
                      step="8"
                      value={Math.min(contextSettings.max_tokens || 4000, 100000)}
                      onChange={(e) => setContextSettings({ ...contextSettings, max_tokens: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Total context budget sent to LLM (1K - 1M tokens). Values automatically rounded to multiples of 8.
                    </div>
                  </div>

                  {/* Keep Recent Scenes */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Keep Recent Scenes: {contextSettings.keep_recent_scenes || 3}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={contextSettings.keep_recent_scenes || 3}
                      onChange={(e) => setContextSettings({ ...contextSettings, keep_recent_scenes: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Always preserve this many recent scenes
                    </div>
                  </div>

                  {/* Summary Threshold */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Summary Threshold: {contextSettings.summary_threshold || 5} scenes
                    </label>
                    <input
                      type="range"
                      min="3"
                      max="20"
                      step="1"
                      value={contextSettings.summary_threshold || 5}
                      onChange={(e) => setContextSettings({ ...contextSettings, summary_threshold: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Start summarizing when story exceeds this many scenes (OR condition)
                    </div>
                  </div>

                  {/* Summary Threshold Tokens */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Token Threshold: {(contextSettings.summary_threshold_tokens || 8000).toLocaleString()} tokens
                    </label>
                    <input
                      type="number"
                      min="1000"
                      max="50000"
                      step="8"
                      value={contextSettings.summary_threshold_tokens || 8000}
                      onChange={(e) => {
                        const value = parseInt(e.target.value) || 8000;
                        setContextSettings({ ...contextSettings, summary_threshold_tokens: value });
                      }}
                      onBlur={(e) => {
                        // Round to nearest multiple of 8 when user finishes editing
                        const value = parseInt(e.target.value) || 8000;
                        const rounded = Math.round(value / 8) * 8;
                        if (value !== rounded) {
                          setContextSettings({ ...contextSettings, summary_threshold_tokens: rounded });
                        }
                      }}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white mb-2"
                    />
                    <input
                      type="range"
                      min="1000"
                      max="50000"
                      step="8"
                      value={contextSettings.summary_threshold_tokens || 8000}
                      onChange={(e) => setContextSettings({ ...contextSettings, summary_threshold_tokens: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Start summarizing when total token count exceeds this threshold (OR condition with scenes). Values automatically rounded to multiples of 8.
                    </div>
                  </div>

                  {/* Semantic Memory Section */}
                  <div className="border-t border-gray-700 pt-6 mt-6">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
                      🧠 Semantic Memory
                      <span className="ml-2 px-2 py-1 text-xs bg-purple-600 rounded">Experimental</span>
                    </h3>
                    
                    {/* Enable Semantic Memory */}
                    <div className="mb-4">
                      <label className="flex items-center">
                        <input
                          type="checkbox"
                          checked={contextSettings.enable_semantic_memory !== false}
                          onChange={(e) => setContextSettings({ ...contextSettings, enable_semantic_memory: e.target.checked })}
                          className="mr-2"
                        />
                        Enable Semantic Memory
                      </label>
                      <div className="text-xs text-gray-400 mt-1">
                        Use vector embeddings to find semantically relevant past scenes, not just recent ones
                      </div>
                    </div>

                    {contextSettings.enable_semantic_memory !== false && (
                      <div className="space-y-4 ml-4 pl-4 border-l-2 border-purple-600">
                        
                        {/* Context Strategy */}
                        <div>
                          <label className="block text-sm font-medium text-white mb-2">Context Strategy</label>
                          <select
                            value={contextSettings.context_strategy || 'hybrid'}
                            onChange={(e) => setContextSettings({ ...contextSettings, context_strategy: e.target.value })}
                            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                          >
                            <option value="linear">Linear (Recent scenes only)</option>
                            <option value="hybrid">Hybrid (Recent + Semantic)</option>
                          </select>
                          <div className="text-xs text-gray-400 mt-1">
                            <strong>Linear:</strong> Traditional approach - only recent scenes<br/>
                            <strong>Hybrid:</strong> Recent scenes + semantically similar past scenes
                          </div>
                        </div>

                        {contextSettings.context_strategy !== 'linear' && (
                          <>
                            {/* Semantic Scenes */}
                            <div>
                              <label className="block text-sm font-medium text-white mb-2">
                                Semantic Scenes: {contextSettings.semantic_scenes_in_context || 5}
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="10"
                                step="1"
                                value={contextSettings.semantic_scenes_in_context || 5}
                                onChange={(e) => setContextSettings({ ...contextSettings, semantic_scenes_in_context: parseInt(e.target.value) })}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Max semantically relevant scenes to include in context
                              </div>
                            </div>

                            {/* Semantic Search Top K */}
                            <div>
                              <label className="block text-sm font-medium text-white mb-2">
                                Search Results: {contextSettings.semantic_search_top_k || 5}
                              </label>
                              <input
                                type="range"
                                min="1"
                                max="20"
                                step="1"
                                value={contextSettings.semantic_search_top_k || 5}
                                onChange={(e) => setContextSettings({ ...contextSettings, semantic_search_top_k: parseInt(e.target.value) })}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Number of similar scenes to retrieve (higher = more options to choose from)
                              </div>
                            </div>

                            {/* Semantic Context Weight */}
                            <div>
                              <label className="block text-sm font-medium text-white mb-2">
                                Semantic Weight: {((contextSettings.semantic_context_weight || 0.4) * 100).toFixed(0)}%
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.1"
                                value={contextSettings.semantic_context_weight || 0.4}
                                onChange={(e) => setContextSettings({ ...contextSettings, semantic_context_weight: parseFloat(e.target.value) })}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Balance between recent vs semantic scenes (higher = more semantic)
                              </div>
                            </div>

                            {/* Character Moments */}
                            <div>
                              <label className="block text-sm font-medium text-white mb-2">
                                Character Moments: {contextSettings.character_moments_in_context || 3}
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="10"
                                step="1"
                                value={contextSettings.character_moments_in_context || 3}
                                onChange={(e) => setContextSettings({ ...contextSettings, character_moments_in_context: parseInt(e.target.value) })}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Max character-specific moments to include
                              </div>
                            </div>
                          </>
                        )}

                        {/* Auto-extraction Settings */}
                        <div className="pt-2 space-y-3">
                          <div>
                            <label className="flex items-center">
                              <input
                                type="checkbox"
                                checked={contextSettings.auto_extract_character_moments !== false}
                                onChange={(e) => setContextSettings({ ...contextSettings, auto_extract_character_moments: e.target.checked })}
                                className="mr-2"
                              />
                              Auto-extract character moments
                            </label>
                            <div className="text-xs text-gray-400 mt-1 ml-6">
                              Automatically identify and save character development moments
                            </div>
                          </div>

                          <div>
                            <label className="flex items-center">
                              <input
                                type="checkbox"
                                checked={contextSettings.auto_extract_plot_events !== false}
                                onChange={(e) => setContextSettings({ ...contextSettings, auto_extract_plot_events: e.target.checked })}
                                className="mr-2"
                              />
                              Auto-extract plot events
                            </label>
                            <div className="text-xs text-gray-400 mt-1 ml-6">
                              Automatically identify and save significant plot points
                            </div>
                          </div>

                          {/* Extraction Confidence Threshold */}
                          <div>
                            <label className="block text-sm font-medium text-white mb-2">
                              Confidence Threshold: {contextSettings.extraction_confidence_threshold || 70}%
                            </label>
                            <input
                              type="range"
                              min="0"
                              max="100"
                              step="5"
                              value={contextSettings.extraction_confidence_threshold || 70}
                              onChange={(e) => setContextSettings({ ...contextSettings, extraction_confidence_threshold: parseInt(e.target.value) })}
                              className="w-full"
                            />
                            <div className="text-xs text-gray-400 mt-1">
                              Minimum confidence for auto-extraction (higher = more selective)
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Generation Preferences */}
                <div className="space-y-4">
                  <h4 className="text-md font-semibold text-white mb-3">Generation Preferences</h4>
                  
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={generationPrefs.auto_choices}
                      onChange={(e) => setGenerationPrefs({ ...generationPrefs, auto_choices: e.target.checked })}
                      className="w-4 h-4 rounded"
                    />
                    <span className="text-sm text-white">Auto-generate choices after each scene</span>
                  </label>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Number of Choices: {generationPrefs.choices_count}
                    </label>
                    <input
                      type="range"
                      min="2"
                      max="6"
                      step="1"
                      value={generationPrefs.choices_count}
                      onChange={(e) => setGenerationPrefs({ ...generationPrefs, choices_count: parseInt(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-xs text-gray-400 mt-1">Number of choices to generate</p>
                  </div>
                </div>

                {/* Save Button */}
                <div className="flex justify-end pt-4 border-t border-gray-700">
                  <button
                    onClick={async () => {
                      try {
                        const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
                          method: 'PUT',
                          headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`,
                          },
                          body: JSON.stringify({
                            context_settings: contextSettings,
                            generation_preferences: generationPrefs,
                          }),
                        });
                        if (response.ok) {
                          showMessage('Settings saved!', 'success');
                        } else {
                          showMessage('Failed to save settings', 'error');
                        }
                      } catch (error) {
                        showMessage('Error saving settings', 'error');
                      }
                    }}
                    className="px-6 py-2 theme-btn-primary rounded-lg font-semibold"
                  >
                    Save Settings
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Voice Settings Tab */}
          {activeTab === 'voice' && (
            <div className="space-y-6">
              {/* Debug info */}
              {process.env.NODE_ENV === 'development' && (
                <div className="text-xs text-gray-500 p-2 bg-gray-800 rounded">
                  Debug: TTS Providers count: {ttsProviders.length}, Loading: {isLoadingTTSProviders ? 'true' : 'false'}
                </div>
              )}
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
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>100 (Fast)</span>
                        <span>280 (Balanced)</span>
                        <span>500 (Smooth)</span>
                      </div>
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
                    <p className="text-xs text-gray-500 mt-1">
                      Enter the URL of your TTS service (e.g., OpenAI-compatible, Chatterbox, Kokoro)
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">API Key (Optional)</label>
                    <input
                      type="password"
                      value={ttsSettings.api_key || ''}
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
                    <p className="text-xs text-gray-500">
                      Test the connection and load available voices
                    </p>
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
                        title="Browse and preview all voices"
                      >
                        <Eye className="w-4 h-4" />
                        <span>See All</span>
                      </button>
                    )}
                    <button
                      onClick={handleTTSTest}
                      disabled={isTestingTTS || isLoadingTTSSettings || !ttsSettings.api_url}
                      className="flex items-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                      title="Test the selected voice"
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
                  <p className="text-xs text-gray-500">
                    Choose the voice for narration
                    {ttsVoices.length > 0 && <> • Click "See All" to preview voices • Click "Test Voice" to hear a sample</>}
                  </p>
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
                        min="0.1"
                        max="2"
                        step="0.05"
                        value={chatterboxExaggeration}
                        onChange={(e) => setChatterboxExaggeration(parseFloat(e.target.value))}
                        disabled={isLoadingTTSSettings}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>0.1 (Subtle)</span>
                        <span>1.0 (Balanced)</span>
                        <span>2.0 (Dramatic)</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Controls emotional expression intensity
                      </p>
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
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>0.0 (Slow)</span>
                        <span>0.5 (Normal)</span>
                        <span>1.0 (Fast)</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Controls speech pacing
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Temperature: {chatterboxTemperature.toFixed(2)}
                      </label>
                      <input
                        type="range"
                        min="0.05"
                        max="2"
                        step="0.05"
                        value={chatterboxTemperature}
                        onChange={(e) => setChatterboxTemperature(parseFloat(e.target.value))}
                        disabled={isLoadingTTSSettings}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>0.05 (Consistent)</span>
                        <span>1.0 (Balanced)</span>
                        <span>2.0 (Creative)</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Controls randomness in speech generation
                      </p>
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
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>0.5x (Slower)</span>
                    <span>1.0x (Normal)</span>
                    <span>2.0x (Faster)</span>
                  </div>
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

              {/* Action Buttons */}
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
                
                <div className="space-y-4">
                  {/* Enable/Disable Toggle */}
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={sttEnabled}
                        onChange={(e) => setSttEnabled(e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Enable STT</span>
                    </label>
                  </div>
                  
                  {/* Model Selection Dropdown */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      STT Model Quality
                    </label>
                    <select
                      value={sttModel}
                      onChange={(e) => setSttModel(e.target.value)}
                      disabled={isDownloadingSTTModel}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="base">Base (Fast, Good Quality)</option>
                      <option value="small">Small (Balanced, Better Quality) - Recommended</option>
                      <option value="medium">Medium (Slower, Best Quality)</option>
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Higher quality models provide better accuracy but are slower
                    </p>
                  </div>
                  
                  {/* Model Download Status */}
                  {sttEnabled && (
                    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-sm font-medium text-white">
                          STT Model Status
                        </span>
                        {sttModelDownloaded === true && vadModelDownloaded === true && (
                          <span className="text-xs text-green-400 flex items-center gap-1">
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                            All Models Ready
                          </span>
                        )}
                      </div>
                      
                      {/* Whisper Status */}
                      <div className="mb-3 pb-3 border-b border-gray-700">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-gray-400">Whisper Model ({sttModel})</span>
                          {sttModelDownloaded === true ? (
                            <span className="text-xs text-green-400 flex items-center gap-1">
                              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                              </svg>
                              Downloaded
                            </span>
                          ) : (
                            <span className="text-xs text-yellow-400 flex items-center gap-1">
                              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                              </svg>
                              Not Downloaded
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* VAD Status */}
                      <div className="mb-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-gray-400">Silero VAD Model</span>
                          {vadModelDownloaded === true ? (
                            <span className="text-xs text-green-400 flex items-center gap-1">
                              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                              </svg>
                              Downloaded
                            </span>
                          ) : (
                            <span className="text-xs text-yellow-400 flex items-center gap-1">
                              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                              </svg>
                              Not Downloaded
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {isDownloadingSTTModel && (
                        <div className="space-y-2">
                          <div className="flex items-center gap-2 text-sm text-blue-400">
                            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Downloading STT models (Whisper + VAD)... This may take a few minutes.
                          </div>
                          <div className="w-full bg-gray-700 rounded-full h-2">
                            <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{ width: '100%' }}></div>
                          </div>
                          <p className="text-xs text-gray-400">
                            Model sizes: Whisper varies by model (~150MB-1.5GB), VAD (~1.8MB)
                          </p>
                        </div>
                      )}
                      
                      {!isDownloadingSTTModel && (sttModelDownloaded === false || vadModelDownloaded === false) && (
                        <div className="space-y-2">
                          <p className="text-sm text-gray-400">
                            {sttModelDownloaded === false && vadModelDownloaded === false 
                              ? `Both STT models need to be downloaded before use.`
                              : sttModelDownloaded === false
                              ? `Whisper model needs to be downloaded.`
                              : `VAD model needs to be downloaded.`}
                          </p>
                          {sttDownloadError && (
                            <p className="text-xs text-red-400">{sttDownloadError}</p>
                          )}
                          <button
                            onClick={downloadSTTModel}
                            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
                          >
                            Download STT Models
                          </button>
                        </div>
                      )}
                      
                      {!isDownloadingSTTModel && sttModelDownloaded === true && vadModelDownloaded === true && (
                        <p className="text-xs text-gray-400">
                          All models are ready to use. STT features are available.
                        </p>
                      )}
                    </div>
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
            </div>
          )}
        </div>
      </div>

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

