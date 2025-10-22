'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useUISettings } from '@/hooks/useUISettings';
import { useNotifications } from '@/hooks/useNotifications';
import WritingPresetsManager from '@/components/writing-presets/WritingPresetsManager';
import { API_BASE_URL } from '@/lib/api';

interface LLMSettings {
  temperature: number;
  top_p: number;
  top_k: number;
  repetition_penalty: number;
  max_tokens: number;
  // API Configuration
  api_url: string;
  api_key: string;
  api_type: string;
  model_name: string;
}

interface ContextSettings {
  max_tokens: number;
  keep_recent_scenes: number;
  summary_threshold: number;
  summary_threshold_tokens: number;
  enable_summarization: boolean;
  // Semantic Memory Settings
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

interface GenerationPreferences {
  default_genre: string;
  default_tone: string;
  scene_length: string;
  auto_choices: boolean;
  choices_count: number;
}

interface UIPreferences {
  theme: string;
  font_size: string;
  show_token_info: boolean;
  show_context_info: boolean;
  notifications: boolean;
  scene_display_format: string; // 'default', 'bubble', 'card', 'minimal'
  show_scene_titles: boolean;
  auto_open_last_story: boolean;
}

interface UserSettings {
  llm_settings: LLMSettings;
  context_settings: ContextSettings;
  generation_preferences: GenerationPreferences;
  ui_preferences: UIPreferences;
}

interface SettingsPreset {
  name: string;
  description: string;
  llm_settings: Partial<LLMSettings>;
  context_settings?: Partial<ContextSettings>;
}

export default function SettingsPage() {
  const router = useRouter();
  const { user, token } = useAuthStore();
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [presets, setPresets] = useState<Record<string, SettingsPreset>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('writing');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error' | 'info'>('success');
  const { addNotification } = useNotifications();

  // Permission checks
  const canChangeLLMProvider = user?.can_change_llm_provider ?? true;
  const canChangeTTSSettings = user?.can_change_tts_settings ?? true;

  // Model management state
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [currentModel, setCurrentModel] = useState<string>('');
  const [loadingModels, setLoadingModels] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);

  // Prompt templates state
  const [promptTemplates, setPromptTemplates] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(false);

  // Apply UI settings when they change
  useUISettings(settings?.ui_preferences || null);

  useEffect(() => {
    if (!user) {
      router.push('/login');
      return;
    }
    loadSettings();
    loadPresets();
    if (activeTab === 'prompts') {
      loadPromptTemplates();
    }
  }, [user, router, activeTab]);

  const loadSettings = async () => {
    try {
      console.log('Loading settings with token:', token ? 'exists' : 'missing');
      const response = await fetch(`${API_BASE_URL}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      console.log('Settings response status:', response.status);
      if (response.ok) {
        const data = await response.json();
        console.log('Settings data:', data);
        setSettings(data.settings);
      } else {
        console.error('Failed to load settings, status:', response.status);
        const errorData = await response.text();
        console.error('Error response:', errorData);
        
        // Set an error message for the user
        if (response.status === 401) {
          setMessage('Authentication error. Please log in again.');
          setMessageType('error');
          setTimeout(() => router.push('/login'), 2000);
        } else {
          setMessage(`Failed to load settings (${response.status}). Please try again.`);
          setMessageType('error');
        }
      }
    } catch (error) {
      console.error('Error loading settings:', error);
      setMessage('Network error. Please check your connection and try again.');
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/settings/presets`);
      if (response.ok) {
        const data = await response.json();
        setPresets(data.presets);
      }
    } catch (error) {
      console.error('Error loading presets:', error);
    }
  };

  const loadPromptTemplates = async () => {
    setLoadingTemplates(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/prompt-templates/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setPromptTemplates(data);
      } else {
        console.error('Failed to load prompt templates');
      }
    } catch (error) {
      console.error('Error loading prompt templates:', error);
    } finally {
      setLoadingTemplates(false);
    }
  };

  const updatePromptTemplate = async (templateId: number, updates: any) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/prompt-templates/${templateId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(updates),
      });
      
      if (response.ok) {
        setMessage('Prompt template updated successfully!');
        loadPromptTemplates(); // Reload templates
        setSelectedTemplate(null);
        setEditingTemplate(false);
      } else {
        setMessage('Failed to update prompt template');
      }
    } catch (error) {
      console.error('Error updating prompt template:', error);
      setMessage('Error updating prompt template');
    }
  };

  const saveSettings = async () => {
    if (!settings) return;

    setSaving(true);
    try {
      // Transform the settings to match the backend's expected format
      const settingsPayload = {
        llm_settings: {
          temperature: settings.llm_settings.temperature,
          top_p: settings.llm_settings.top_p,
          top_k: settings.llm_settings.top_k,
          repetition_penalty: settings.llm_settings.repetition_penalty,
          max_tokens: settings.llm_settings.max_tokens,
          api_url: settings.llm_settings.api_url,
          api_key: settings.llm_settings.api_key,
          api_type: settings.llm_settings.api_type,
          model_name: settings.llm_settings.model_name,
        },
        context_settings: {
          max_tokens: settings.context_settings.max_tokens,
          keep_recent_scenes: settings.context_settings.keep_recent_scenes,
          summary_threshold: settings.context_settings.summary_threshold,
          summary_threshold_tokens: settings.context_settings.summary_threshold_tokens,
          enable_summarization: settings.context_settings.enable_summarization,
          // Semantic Memory Settings
          enable_semantic_memory: settings.context_settings.enable_semantic_memory,
          context_strategy: settings.context_settings.context_strategy,
          semantic_search_top_k: settings.context_settings.semantic_search_top_k,
          semantic_scenes_in_context: settings.context_settings.semantic_scenes_in_context,
          semantic_context_weight: settings.context_settings.semantic_context_weight,
          character_moments_in_context: settings.context_settings.character_moments_in_context,
          auto_extract_character_moments: settings.context_settings.auto_extract_character_moments,
          auto_extract_plot_events: settings.context_settings.auto_extract_plot_events,
          extraction_confidence_threshold: settings.context_settings.extraction_confidence_threshold,
        },
        generation_preferences: {
          default_genre: settings.generation_preferences.default_genre,
          default_tone: settings.generation_preferences.default_tone,
          scene_length: settings.generation_preferences.scene_length,
          auto_choices: settings.generation_preferences.auto_choices,
          choices_count: settings.generation_preferences.choices_count,
        },
        ui_preferences: {
          theme: settings.ui_preferences.theme,
          font_size: settings.ui_preferences.font_size,
          show_token_info: settings.ui_preferences.show_token_info,
          show_context_info: settings.ui_preferences.show_context_info,
          notifications: settings.ui_preferences.notifications,
          scene_display_format: settings.ui_preferences.scene_display_format,
          show_scene_titles: settings.ui_preferences.show_scene_titles,
          auto_open_last_story: settings.ui_preferences.auto_open_last_story,
        },
      };

      const response = await fetch(`${API_BASE_URL}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(settingsPayload),
      });

      if (response.ok) {
        setMessage('Settings saved successfully!');
        setMessageType('success');
        addNotification('Settings saved successfully!', 'success');
        setTimeout(() => setMessage(''), 3000);
      } else {
        setMessage('Failed to save settings');
        setMessageType('error');
        addNotification('Failed to save settings', 'error');
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      setMessage('Error saving settings');
      setMessageType('error');
    } finally {
      setSaving(false);
    }
  };

  const resetSettings = async () => {
    if (!confirm('Are you sure you want to reset all settings to defaults?')) return;

    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/settings/reset`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setSettings(data.settings);
        setMessage('Settings reset to defaults');
        setMessageType('success');
      } else {
        setMessage('Failed to reset settings');
        setMessageType('error');
      }
    } catch (error) {
      console.error('Error resetting settings:', error);
      setMessage('Error resetting settings');
      setMessageType('error');
    } finally {
      setSaving(false);
    }
  };

  const applyPreset = (presetKey: string) => {
    if (!settings || !presets[presetKey]) return;

    const preset = presets[presetKey];
    const newSettings = {
      ...settings,
      llm_settings: {
        ...settings.llm_settings,
        ...preset.llm_settings,
      },
    };

    if (preset.context_settings) {
      newSettings.context_settings = {
        ...settings.context_settings,
        ...preset.context_settings,
      };
    }

    setSettings(newSettings);
    setMessage(`Applied "${preset.name}" preset`);
    addNotification(`Applied "${preset.name}" preset`, 'success', 2000);
    setTimeout(() => setMessage(''), 3000);
  };

  const updateLLMSetting = (key: keyof LLMSettings, value: number | string) => {
    if (!settings) return;
    setSettings({
      ...settings,
      llm_settings: {
        ...settings.llm_settings,
        [key]: value,
      },
    });
  };

  // Helper function to round down to nearest multiple of 8
  const roundToMultipleOf8 = (value: number): number => {
    return Math.floor(value / 8) * 8;
  };

  const updateContextSetting = (key: keyof ContextSettings, value: number | boolean) => {
    if (!settings) return;
    
    // Apply rounding to specific token fields
    let finalValue = value;
    if (typeof value === 'number' && (key === 'max_tokens' || key === 'summary_threshold_tokens')) {
      finalValue = roundToMultipleOf8(value);
    }
    
    setSettings({
      ...settings,
      context_settings: {
        ...settings.context_settings,
        [key]: finalValue,
      },
    });
  };

  const updateGenerationPreference = (key: keyof GenerationPreferences, value: string | boolean | number) => {
    if (!settings) return;
    setSettings({
      ...settings,
      generation_preferences: {
        ...settings.generation_preferences,
        [key]: value,
      },
    });
  };

  const updateUIPreference = (key: keyof UIPreferences, value: string | boolean) => {
    if (!settings) return;
    const newSettings = {
      ...settings,
      ui_preferences: {
        ...settings.ui_preferences,
        [key]: value,
      },
    };
    setSettings(newSettings);
    
    // Apply UI changes immediately for better UX
    if (key === 'theme' || key === 'font_size') {
      addNotification(`${key === 'theme' ? 'Theme' : 'Font size'} updated`, 'info', 1500);
    }
  };

  // API Configuration Functions
  const testApiConnection = async () => {
    if (!settings) return;
    
    setTestingConnection(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/settings/test-api-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setMessage('API connection successful!');
          setMessageType('success');
          fetchAvailableModels(); // Auto-fetch models on successful connection
        } else {
          setMessage(data.message || 'Connection failed');
          setMessageType('error');
        }
      } else {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      setMessage(`Connection failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setMessageType('error');
    } finally {
      setTestingConnection(false);
    }
  };

  const fetchAvailableModels = async () => {
    if (!settings) return;
    
    setLoadingModels(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/settings/available-models`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setAvailableModels(data.models);
          setMessage(`Found ${data.models.length} available models`);
          setMessageType('success');
        } else {
          setMessage(data.message || 'Failed to fetch models');
          setMessageType('error');
        }
      } else {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      setMessage(`Failed to fetch models: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setMessageType('error');
    } finally {
      setLoadingModels(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white">Loading settings...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white">Please log in to access settings</div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="text-white mb-4">Error loading settings</div>
          <button
            onClick={() => {
              setLoading(true);
              loadSettings();
            }}
            className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-md text-white"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white pt-16">
      {/* Settings Actions Bar */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-4">
              <h1 className="text-xl font-semibold">Settings</h1>
            </div>
            <div className="flex items-center space-x-4">
              {message && (
                <span className={`text-sm ${
                  messageType === 'success' ? 'text-green-400' :
                  messageType === 'error' ? 'text-red-400' :
                  'text-blue-400'
                }`}>
                  {message}
                </span>
              )}
              <button
                onClick={saveSettings}
                disabled={saving}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
              <button
                onClick={resetSettings}
                className="bg-gray-600 hover:bg-gray-700 px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                Reset to Defaults
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tab Navigation */}
        <div className="flex space-x-1 bg-gray-800 p-1 rounded-lg mb-8 overflow-x-auto">
          {[
            { id: 'writing', name: 'Writing Styles' },
            { id: 'llm', name: 'LLM Settings' },
            { id: 'context', name: 'Context Management' },
            { id: 'generation', name: 'Generation' },
            { id: 'prompts', name: '👁️ Prompt Inspector' },
            { id: 'ui', name: 'Interface' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Settings Panel */}
          <div className="lg:col-span-3">
            
            {/* Writing Styles */}
            {activeTab === 'writing' && (
              <div className="bg-gray-800 rounded-lg p-6">
                <WritingPresetsManager />
              </div>
            )}

            {/* LLM Settings */}
            {activeTab === 'llm' && (
              <div className="bg-gray-800 rounded-lg p-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold">LLM Generation Settings</h2>
                  <div className="text-sm text-gray-400">
                    Fine-tune how the AI generates text
                  </div>
                </div>

                {/* Presets */}
                <div className="mb-8">
                  <h3 className="text-lg font-medium mb-4">Quick Presets</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {Object.entries(presets).map(([key, preset]) => (
                      <button
                        key={key}
                        onClick={() => applyPreset(key)}
                        className="bg-gray-700 hover:bg-gray-600 p-4 rounded-lg text-left transition-colors"
                      >
                        <div className="font-medium">{preset.name}</div>
                        <div className="text-sm text-gray-400 mt-1">{preset.description}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* API Configuration */}
                <div className="mb-8">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-medium">API Configuration</h3>
                    {!canChangeLLMProvider && (
                      <div className="text-xs text-yellow-400 bg-yellow-400/10 px-3 py-1 rounded-full border border-yellow-400/30">
                        🔒 View Only - Contact admin for changes
                      </div>
                    )}
                  </div>
                  <div className="space-y-4">
                    
                    {/* API Type */}
                    <div>
                      <label className="block text-sm font-medium mb-2">API Type</label>
                      <select
                        value={settings.llm_settings.api_type || 'openai-compatible'}
                        onChange={(e) => updateLLMSetting('api_type', e.target.value)}
                        disabled={!canChangeLLMProvider}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <option value="openai-compatible">OpenAI Compatible</option>
                        <option value="openai">OpenAI Official</option>
                        <option value="koboldcpp">KoboldCpp</option>
                        <option value="ollama">Ollama</option>
                      </select>
                      <div className="text-xs text-gray-400 mt-1">
                        Select the type of API server you're connecting to
                      </div>
                    </div>

                    {/* API URL */}
                    <div>
                      <label className="block text-sm font-medium mb-2">API URL</label>
                      <input
                        type="url"
                        value={settings.llm_settings.api_url || ''}
                        onChange={(e) => updateLLMSetting('api_url', e.target.value)}
                        disabled={!canChangeLLMProvider}
                        placeholder="Enter your LLM API URL (e.g., https://api.openai.com/v1)"
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <div className="text-xs text-gray-400 mt-1">
                        Base URL for your LLM API server
                      </div>
                    </div>

                    {/* API Key */}
                    <div>
                      <label className="block text-sm font-medium mb-2">API Key (Optional)</label>
                      <input
                        type="password"
                        value={settings.llm_settings.api_key || ''}
                        onChange={(e) => updateLLMSetting('api_key', e.target.value)}
                        disabled={!canChangeLLMProvider}
                        placeholder="Enter API key if required"
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <div className="text-xs text-gray-400 mt-1">
                        API key for authentication (leave empty for local servers)
                      </div>
                    </div>

                    {/* Connection Test and Model Discovery */}
                    <div className="flex gap-3">
                      <button
                        onClick={testApiConnection}
                        disabled={testingConnection || !canChangeLLMProvider}
                        className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed px-4 py-2 rounded-md text-white transition-colors"
                      >
                        {testingConnection ? 'Testing...' : 'Test Connection'}
                      </button>
                      <button
                        onClick={fetchAvailableModels}
                        disabled={loadingModels || !canChangeLLMProvider}
                        className="flex-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed px-4 py-2 rounded-md text-white transition-colors"
                      >
                        {loadingModels ? 'Loading...' : 'Fetch Models'}
                      </button>
                    </div>

                    {/* Current Model */}
                    {currentModel && (
                      <div className="bg-gray-700 p-3 rounded-md">
                        <div className="text-sm font-medium text-green-400">Current Model:</div>
                        <div className="text-white">{currentModel}</div>
                      </div>
                    )}

                    {/* Available Models */}
                    {availableModels.length > 0 && (
                      <div>
                        <label className="block text-sm font-medium mb-2">Select Model</label>
                        <select
                          value={settings.llm_settings.model_name || ''}
                          onChange={(e) => {
                            updateLLMSetting('model_name', e.target.value);
                            setCurrentModel(e.target.value);
                          }}
                          disabled={!canChangeLLMProvider}
                          className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50 disabled:cursor-not-allowed"
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
                </div>

                {/* LLM Parameters */}
                <div className="space-y-6">
                  {/* Temperature */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Temperature: {settings.llm_settings.temperature}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={settings.llm_settings.temperature}
                      onChange={(e) => updateLLMSetting('temperature', parseFloat(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Controls creativity. Lower = more focused, Higher = more creative
                    </div>
                  </div>

                  {/* Top P */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Top P: {settings.llm_settings.top_p}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={settings.llm_settings.top_p}
                      onChange={(e) => updateLLMSetting('top_p', parseFloat(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Nucleus sampling. Controls diversity of word choices
                    </div>
                  </div>

                  {/* Top K */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Top K: {settings.llm_settings.top_k}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="100"
                      step="1"
                      value={settings.llm_settings.top_k}
                      onChange={(e) => updateLLMSetting('top_k', parseInt(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Limits vocabulary to top K words
                    </div>
                  </div>

                  {/* Repetition Penalty */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Repetition Penalty: {settings.llm_settings.repetition_penalty}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="2"
                      step="0.05"
                      value={settings.llm_settings.repetition_penalty}
                      onChange={(e) => updateLLMSetting('repetition_penalty', parseFloat(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Penalizes repetition. Higher = less repetitive
                    </div>
                  </div>

                  {/* Max Tokens */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Max Tokens: {settings.llm_settings.max_tokens}
                    </label>
                    <input
                      type="range"
                      min="100"
                      max="4096"
                      step="64"
                      value={settings.llm_settings.max_tokens}
                      onChange={(e) => updateLLMSetting('max_tokens', parseInt(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Maximum tokens per generation
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Context Management */}
            {activeTab === 'context' && settings && settings.context_settings && (
              <div className="bg-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-semibold mb-6">Context Management</h2>
                <div className="space-y-6">
                  
                  {/* Enable Summarization */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.context_settings.enable_summarization || false}
                        onChange={(e) => updateContextSetting('enable_summarization', e.target.checked)}
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
                    <label className="block text-sm font-medium mb-2">
                      Context Budget: {(settings.context_settings.max_tokens || 4000).toLocaleString()} tokens
                    </label>
                    <input
                      type="number"
                      min="1000"
                      max="1000000"
                      step="8"
                      value={settings.context_settings.max_tokens || 4000}
                      onChange={(e) => {
                        const value = parseInt(e.target.value) || 4000;
                        updateContextSetting('max_tokens', value);
                      }}
                      onBlur={(e) => {
                        // Round to nearest multiple of 8 when user finishes editing
                        const value = parseInt(e.target.value) || 4000;
                        const rounded = roundToMultipleOf8(value);
                        if (value !== rounded) {
                          updateContextSetting('max_tokens', rounded);
                        }
                      }}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white mb-2"
                    />
                    <input
                      type="range"
                      min="1000"
                      max="100000"
                      step="8"
                      value={Math.min(settings.context_settings.max_tokens || 4000, 100000)}
                      onChange={(e) => updateContextSetting('max_tokens', parseInt(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Total context budget sent to LLM (1K - 1M tokens). Values automatically rounded to multiples of 8.
                    </div>
                  </div>

                  {/* Keep Recent Scenes */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Keep Recent Scenes: {settings.context_settings.keep_recent_scenes || 3}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={settings.context_settings.keep_recent_scenes || 3}
                      onChange={(e) => updateContextSetting('keep_recent_scenes', parseInt(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Always preserve this many recent scenes
                    </div>
                  </div>

                  {/* Summary Threshold */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Summary Threshold: {settings.context_settings.summary_threshold || 5} scenes
                    </label>
                    <input
                      type="range"
                      min="3"
                      max="20"
                      step="1"
                      value={settings.context_settings.summary_threshold || 5}
                      onChange={(e) => updateContextSetting('summary_threshold', parseInt(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Start summarizing when story exceeds this many scenes (OR condition)
                    </div>
                  </div>

                  {/* Summary Threshold Tokens */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Token Threshold: {(settings.context_settings.summary_threshold_tokens || 8000).toLocaleString()} tokens
                    </label>
                    <input
                      type="number"
                      min="1000"
                      max="50000"
                      step="8"
                      value={settings.context_settings.summary_threshold_tokens || 8000}
                      onChange={(e) => {
                        const value = parseInt(e.target.value) || 8000;
                        updateContextSetting('summary_threshold_tokens', value);
                      }}
                      onBlur={(e) => {
                        // Round to nearest multiple of 8 when user finishes editing
                        const value = parseInt(e.target.value) || 8000;
                        const rounded = roundToMultipleOf8(value);
                        if (value !== rounded) {
                          updateContextSetting('summary_threshold_tokens', rounded);
                        }
                      }}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white mb-2"
                    />
                    <input
                      type="range"
                      min="1000"
                      max="50000"
                      step="8"
                      value={settings.context_settings.summary_threshold_tokens}
                      onChange={(e) => updateContextSetting('summary_threshold_tokens', parseInt(e.target.value))}
                      className="w-full"
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      Start summarizing when total token count exceeds this threshold (OR condition with scenes). Values automatically rounded to multiples of 8.
                    </div>
                  </div>

                  {/* Semantic Memory Section */}
                  <div className="border-t border-gray-700 pt-6 mt-6">
                    <h3 className="text-lg font-semibold mb-4 flex items-center">
                      🧠 Semantic Memory
                      <span className="ml-2 px-2 py-1 text-xs bg-purple-600 rounded">Experimental</span>
                    </h3>
                    
                    {/* Enable Semantic Memory */}
                    <div className="mb-4">
                      <label className="flex items-center">
                        <input
                          type="checkbox"
                          checked={settings.context_settings.enable_semantic_memory !== false}
                          onChange={(e) => updateContextSetting('enable_semantic_memory', e.target.checked)}
                          className="mr-2"
                        />
                        Enable Semantic Memory
                      </label>
                      <div className="text-xs text-gray-400 mt-1">
                        Use vector embeddings to find semantically relevant past scenes, not just recent ones
                      </div>
                    </div>

                    {settings.context_settings.enable_semantic_memory !== false && (
                      <div className="space-y-4 ml-4 pl-4 border-l-2 border-purple-600">
                        
                        {/* Context Strategy */}
                        <div>
                          <label className="block text-sm font-medium mb-2">Context Strategy</label>
                          <select
                            value={settings.context_settings.context_strategy || 'hybrid'}
                            onChange={(e) => updateContextSetting('context_strategy', e.target.value)}
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

                        {settings.context_settings.context_strategy !== 'linear' && (
                          <>
                            {/* Semantic Scenes */}
                            <div>
                              <label className="block text-sm font-medium mb-2">
                                Semantic Scenes: {settings.context_settings.semantic_scenes_in_context || 5}
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="10"
                                step="1"
                                value={settings.context_settings.semantic_scenes_in_context || 5}
                                onChange={(e) => updateContextSetting('semantic_scenes_in_context', parseInt(e.target.value))}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Max semantically relevant scenes to include in context
                              </div>
                            </div>

                            {/* Semantic Search Top K */}
                            <div>
                              <label className="block text-sm font-medium mb-2">
                                Search Results: {settings.context_settings.semantic_search_top_k || 5}
                              </label>
                              <input
                                type="range"
                                min="1"
                                max="20"
                                step="1"
                                value={settings.context_settings.semantic_search_top_k || 5}
                                onChange={(e) => updateContextSetting('semantic_search_top_k', parseInt(e.target.value))}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Number of similar scenes to retrieve (higher = more options to choose from)
                              </div>
                            </div>

                            {/* Semantic Context Weight */}
                            <div>
                              <label className="block text-sm font-medium mb-2">
                                Semantic Weight: {((settings.context_settings.semantic_context_weight || 0.4) * 100).toFixed(0)}%
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.1"
                                value={settings.context_settings.semantic_context_weight || 0.4}
                                onChange={(e) => updateContextSetting('semantic_context_weight', parseFloat(e.target.value))}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Balance between recent vs semantic scenes (higher = more semantic)
                              </div>
                            </div>

                            {/* Character Moments */}
                            <div>
                              <label className="block text-sm font-medium mb-2">
                                Character Moments: {settings.context_settings.character_moments_in_context || 3}
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="10"
                                step="1"
                                value={settings.context_settings.character_moments_in_context || 3}
                                onChange={(e) => updateContextSetting('character_moments_in_context', parseInt(e.target.value))}
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
                                checked={settings.context_settings.auto_extract_character_moments !== false}
                                onChange={(e) => updateContextSetting('auto_extract_character_moments', e.target.checked)}
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
                                checked={settings.context_settings.auto_extract_plot_events !== false}
                                onChange={(e) => updateContextSetting('auto_extract_plot_events', e.target.checked)}
                                className="mr-2"
                              />
                              Auto-extract plot events
                            </label>
                            <div className="text-xs text-gray-400 mt-1 ml-6">
                              Automatically identify and save significant plot points
                            </div>
                          </div>

                          {/* Extraction Confidence Threshold */}
                          {(settings.context_settings.auto_extract_character_moments !== false || 
                            settings.context_settings.auto_extract_plot_events !== false) && (
                            <div>
                              <label className="block text-sm font-medium mb-2">
                                Extraction Confidence: {settings.context_settings.extraction_confidence_threshold || 70}%
                              </label>
                              <input
                                type="range"
                                min="0"
                                max="100"
                                step="10"
                                value={settings.context_settings.extraction_confidence_threshold || 70}
                                onChange={(e) => updateContextSetting('extraction_confidence_threshold', parseInt(e.target.value))}
                                className="w-full"
                              />
                              <div className="text-xs text-gray-400 mt-1">
                                Minimum confidence threshold for auto-extraction (higher = fewer but more accurate)
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Generation Preferences */}
            {activeTab === 'generation' && (
              <div className="bg-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-semibold mb-6">Generation Preferences</h2>
                <div className="space-y-6">
                  
                  {/* Default Genre */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Default Genre</label>
                    <input
                      type="text"
                      value={settings.generation_preferences.default_genre}
                      onChange={(e) => updateGenerationPreference('default_genre', e.target.value)}
                      placeholder="e.g., fantasy, sci-fi, mystery"
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2"
                    />
                  </div>

                  {/* Default Tone */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Default Tone</label>
                    <input
                      type="text"
                      value={settings.generation_preferences.default_tone}
                      onChange={(e) => updateGenerationPreference('default_tone', e.target.value)}
                      placeholder="e.g., dark, humorous, epic"
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2"
                    />
                  </div>

                  {/* Scene Length */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Preferred Scene Length</label>
                    <select
                      value={settings.generation_preferences.scene_length}
                      onChange={(e) => updateGenerationPreference('scene_length', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2"
                    >
                      <option value="short">Short (100-200 words)</option>
                      <option value="medium">Medium (200-400 words)</option>
                      <option value="long">Long (400-600 words)</option>
                    </select>
                  </div>

                  {/* Auto Choices */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.generation_preferences.auto_choices}
                        onChange={(e) => updateGenerationPreference('auto_choices', e.target.checked)}
                        className="mr-2"
                      />
                      Automatically generate choices after each scene
                    </label>
                  </div>

                  {/* Choices Count */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Number of Choices: {settings.generation_preferences.choices_count}
                    </label>
                    <input
                      type="range"
                      min="2"
                      max="6"
                      step="1"
                      value={settings.generation_preferences.choices_count}
                      onChange={(e) => updateGenerationPreference('choices_count', parseInt(e.target.value))}
                      className="w-full"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Prompt Inspector (Read-only) */}
            {activeTab === 'prompts' && (
              <div className="bg-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-semibold mb-2">👁️ Prompt Inspector</h2>
                <div className="mb-6 p-4 bg-blue-900/30 border border-blue-700 rounded-lg">
                  <p className="text-sm text-blue-200">
                    <strong>ℹ️ Read-Only View:</strong> This shows the prompt structure used by the app.
                    <br/>
                    To customize <strong>how the AI writes</strong> (style, tone, NSFW settings), use the <strong>Writing Styles</strong> tab.
                    <br/>
                    User prompts (the template structure) are locked for app stability.
                  </p>
                </div>
                
                <div className="space-y-6">
                  
                  {/* Prompt System Overview */}
                  <div className="bg-gray-700 rounded-lg p-6">
                    <h3 className="text-lg font-semibold mb-4">📋 How the Prompt System Works</h3>
                    <div className="space-y-4 text-sm text-gray-300">
                      <div>
                        <h4 className="font-semibold text-white mb-2">Two-Tier Prompt System:</h4>
                        <div className="ml-4 space-y-2">
                          <div>
                            <strong className="text-green-400">1. System Prompts</strong> (User-Customizable)
                            <ul className="ml-6 mt-1 space-y-1 text-gray-400">
                              <li>• Controlled by your <strong>Writing Style Presets</strong></li>
                              <li>• Defines HOW the AI writes (tone, style, NSFW settings)</li>
                              <li>• You can create multiple presets and switch between them</li>
                              <li>• Applied to all generation types (scenes, choices, summaries)</li>
                            </ul>
                          </div>
                          <div>
                            <strong className="text-blue-400">2. User Prompts</strong> (Locked in YAML)
                            <ul className="ml-6 mt-1 space-y-1 text-gray-400">
                              <li>• Stored in <code className="bg-gray-800 px-1 rounded">prompts.yml</code></li>
                              <li>• Defines WHAT to do (generate scene, create choices, etc.)</li>
                              <li>• Locked for app stability and consistency</li>
                              <li>• Contains template variables like {`{context}`}, {`{scene_content}`}</li>
                            </ul>
                          </div>
                        </div>
                      </div>

                      <div className="border-t border-gray-600 pt-4">
                        <h4 className="font-semibold text-white mb-2">Available Prompt Templates:</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 ml-4">
                          <div className="bg-gray-800 p-3 rounded">
                            <strong className="text-purple-400">Scene Generation</strong>
                            <p className="text-xs text-gray-400 mt-1">Creates immersive story scenes</p>
                          </div>
                          <div className="bg-gray-800 p-3 rounded">
                            <strong className="text-purple-400">Choice Generation</strong>
                            <p className="text-xs text-gray-400 mt-1">Creates meaningful story choices</p>
                          </div>
                          <div className="bg-gray-800 p-3 rounded">
                            <strong className="text-purple-400">Story Summary</strong>
                            <p className="text-xs text-gray-400 mt-1">Summarizes chapters and stories</p>
                          </div>
                          <div className="bg-gray-800 p-3 rounded">
                            <strong className="text-purple-400">Character Generation</strong>
                            <p className="text-xs text-gray-400 mt-1">Creates and expands characters</p>
                          </div>
                        </div>
                      </div>

                      <div className="border-t border-gray-600 pt-4">
                        <h4 className="font-semibold text-white mb-2">🎨 Want to Customize?</h4>
                        <p className="text-gray-400">
                          Go to the <button 
                            onClick={() => setActiveTab('writing')}
                            className="text-blue-400 hover:text-blue-300 underline"
                          >Writing Styles</button> tab to create custom presets that control:
                        </p>
                        <ul className="ml-6 mt-2 space-y-1 text-gray-400">
                          <li>• Writing style and tone (epic, cozy, dark, comedic)</li>
                          <li>• Descriptiveness level</li>
                          <li>• NSFW/content policies</li>
                          <li>• Narrative voice and pacing</li>
                          <li>• Character development approach</li>
                        </ul>
                      </div>
                    </div>
                  </div>

                  {/* Example of Prompt Assembly */}
                  <div className="bg-gray-700 rounded-lg p-6">
                    <h3 className="text-lg font-semibold mb-4">🔍 Example: Scene Generation</h3>
                    <div className="space-y-4">
                      <div>
                        <div className="text-sm font-semibold text-green-400 mb-2">System Prompt (from your active Writing Style Preset):</div>
                        <div className="bg-gray-800 p-4 rounded text-sm text-gray-300 font-mono">
                          "You are a creative storytelling assistant. Write in an engaging narrative style that:<br/>
                          - Uses vivid, descriptive language...<br/>
                          - Creates immersive scenes...<br/>
                          [Your custom style settings]"
                        </div>
                      </div>
                      <div className="text-center text-gray-500 text-2xl">+</div>
                      <div>
                        <div className="text-sm font-semibold text-blue-400 mb-2">User Prompt (locked template from YAML):</div>
                        <div className="bg-gray-800 p-4 rounded text-sm text-gray-300 font-mono">
                          "Story Context: {`{context}`}<br/>
                          <br/>
                          Generate the next scene in this story. Make it engaging and immersive...<br/>
                          [Template structure]"
                        </div>
                      </div>
                      <div className="text-center text-gray-500 text-2xl">=</div>
                      <div>
                        <div className="text-sm font-semibold text-purple-400 mb-2">Final Prompt sent to LLM:</div>
                        <div className="bg-gray-800 p-4 rounded text-sm text-gray-300">
                          System + User prompts combined with your story context, creating a complete instruction for scene generation.
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* UI Preferences */}
            {activeTab === 'ui' && (
              <div className="bg-gray-800 rounded-lg p-6">
                <h2 className="text-xl font-semibold mb-6">Interface Preferences</h2>
                <div className="space-y-6">
                  
                  {/* Theme */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Theme</label>
                    <select
                      value={settings.ui_preferences.theme}
                      onChange={(e) => updateUIPreference('theme', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2"
                    >
                      <option value="dark">Dark</option>
                      <option value="light">Light</option>
                      <option value="auto">Auto</option>
                    </select>
                  </div>

                  {/* Font Size */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Font Size</label>
                    <select
                      value={settings.ui_preferences.font_size}
                      onChange={(e) => updateUIPreference('font_size', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2"
                    >
                      <option value="small">Small</option>
                      <option value="medium">Medium</option>
                      <option value="large">Large</option>
                    </select>
                  </div>

                  {/* Show Token Info */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.show_token_info}
                        onChange={(e) => updateUIPreference('show_token_info', e.target.checked)}
                        className="mr-2"
                      />
                      Show token usage information
                    </label>
                  </div>

                  {/* Show Context Info */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.show_context_info}
                        onChange={(e) => updateUIPreference('show_context_info', e.target.checked)}
                        className="mr-2"
                      />
                      Show context management details
                    </label>
                  </div>

                  {/* Notifications */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.notifications}
                        onChange={(e) => updateUIPreference('notifications', e.target.checked)}
                        className="mr-2"
                      />
                      Enable notifications
                    </label>
                  </div>

                  {/* Scene Display Format */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Scene Display Format</label>
                    <select
                      value={settings.ui_preferences.scene_display_format}
                      onChange={(e) => updateUIPreference('scene_display_format', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2"
                    >
                      <option value="default">Default</option>
                      <option value="bubble">Bubble</option>
                      <option value="card">Card</option>
                      <option value="minimal">Minimal</option>
                    </select>
                    <p className="text-sm text-gray-400 mt-1">
                      Choose how story scenes are displayed
                    </p>
                  </div>

                  {/* Show Scene Titles */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.show_scene_titles}
                        onChange={(e) => updateUIPreference('show_scene_titles', e.target.checked)}
                        className="mr-2"
                      />
                      Show scene titles (e.g., "Scene 5: The Heart of Darkness")
                    </label>
                  </div>

                  {/* Auto-Open Last Story */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.auto_open_last_story || false}
                        onChange={(e) => updateUIPreference('auto_open_last_story', e.target.checked)}
                        className="mr-2"
                      />
                      Auto-open last story on login
                    </label>
                    <p className="text-sm text-gray-400 mt-1 ml-6">
                      Automatically navigate to your most recently accessed story when you log in
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Info Panel */}
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="font-semibold mb-4">Current Settings Summary</h3>
              <div className="space-y-2 text-sm">
                <div>Temperature: {settings.llm_settings.temperature}</div>
                <div>Max Tokens: {settings.llm_settings.max_tokens}</div>
                <div>Context Budget: {settings.context_settings.max_tokens}</div>
                <div>Recent Scenes: {settings.context_settings.keep_recent_scenes}</div>
                <div>Theme: {settings.ui_preferences.theme}</div>
              </div>
            </div>

            <div className="bg-blue-900/50 border border-blue-500/50 rounded-lg p-6">
              <h3 className="font-semibold mb-2">💡 Tips</h3>
              <ul className="text-sm space-y-2 text-blue-200">
                <li>• Higher temperature = more creative but less predictable</li>
                <li>• Lower top_p = more focused responses</li>
                <li>• Increase context budget for longer stories</li>
                <li>• Use presets for quick configuration</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}