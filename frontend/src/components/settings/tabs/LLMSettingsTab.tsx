'use client';

import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { useConfig } from '@/contexts/ConfigContext';
import { SamplerSettings, DEFAULT_SAMPLER_SETTINGS } from '@/types/settings';
import TextCompletionTemplateEditor from '../../TextCompletionTemplateEditor';
import { SettingsTabProps, LLMSettings, ExtractionModelSettings, LLMProvider, THINKING_DISABLE_OPTIONS } from '../types';

// Helper function to safely parse JSON template
const safeParseJSON = (jsonString: string | undefined | null): any => {
  if (!jsonString || jsonString.trim() === '') {
    return null;
  }
  try {
    return JSON.parse(jsonString);
  } catch (error) {
    console.error('Failed to parse text_completion_template:', error);
    return null;
  }
};

interface LLMSettingsTabProps extends SettingsTabProps {
  llmSettings: LLMSettings;
  setLlmSettings: (settings: LLMSettings) => void;
  samplerSettings: SamplerSettings;
  setSamplerSettings: (settings: SamplerSettings) => void;
  extractionModelSettings: ExtractionModelSettings;
  setExtractionModelSettings: (settings: ExtractionModelSettings) => void;
  engineSettings: Record<string, LLMSettings>;
  setEngineSettings: (settings: Record<string, LLMSettings>) => void;
  currentEngine: string;
  setCurrentEngine: (engine: string) => void;
  extractionEngineSettings: Record<string, ExtractionModelSettings>;
  setExtractionEngineSettings: (settings: Record<string, ExtractionModelSettings>) => void;
  currentExtractionEngine: string;
  setCurrentExtractionEngine: (engine: string) => void;
  onSave: () => Promise<void>;
}

export default function LLMSettingsTab({
  token,
  showMessage,
  llmSettings,
  setLlmSettings,
  samplerSettings,
  setSamplerSettings,
  extractionModelSettings,
  setExtractionModelSettings,
  engineSettings,
  setEngineSettings,
  currentEngine,
  setCurrentEngine,
  extractionEngineSettings,
  setExtractionEngineSettings,
  currentExtractionEngine,
  setCurrentExtractionEngine,
  onSave,
}: LLMSettingsTabProps) {
  const config = useConfig();
  const [llmSubTab, setLlmSubTab] = useState<'main' | 'samplers'>('main');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [testingConnection, setTestingConnection] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [availableExtractionModels, setAvailableExtractionModels] = useState<string[]>([]);
  const [loadingExtractionModels, setLoadingExtractionModels] = useState(false);
  const [testingExtractionConnection, setTestingExtractionConnection] = useState(false);
  const [connectionTestResult, setConnectionTestResult] = useState<{success: boolean; message: string} | null>(null);
  const [extractionPresets, setExtractionPresets] = useState<Record<string, any>>({});

  const [autoLoading, setAutoLoading] = useState(false);
  const [autoLoadingExtraction, setAutoLoadingExtraction] = useState(false);
  const [providers, setProviders] = useState<LLMProvider[]>([]);

  const cloudProviders = providers.filter(p => p.category === 'cloud');
  const localProviders = providers.filter(p => p.category === 'local');

  // Check if a provider is a cloud provider (no URL needed)
  const isCloudProvider = (apiType: string) => {
    const provider = providers.find(p => p.id === apiType);
    return provider?.category === 'cloud';
  };

  // Check if current extraction engine is cloud
  const isExtractionCloud = isCloudProvider(currentExtractionEngine);

  useEffect(() => {
    loadProviders();
    loadExtractionPresets();
    // Auto-fetch models silently if API URL is configured
    autoFetchModels();
    autoFetchExtractionModels();
  }, []);

  const loadProviders = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/llm-providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setProviders(data.providers || []);
      }
    } catch (error) {
      console.error('Failed to load LLM providers:', error);
    }
  };

  const loadExtractionPresets = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/extraction-model/presets`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setExtractionPresets(data.presets || {});
      }
    } catch (error) {
      console.error('Failed to load extraction model presets:', error);
    }
  };

  const autoFetchModels = async () => {
    // Cloud providers don't need URL, local providers do
    const isCloud = isCloudProvider(llmSettings.api_type);
    if (!isCloud && !llmSettings.api_url) return;
    if (isCloud && !llmSettings.api_key) return;
    setAutoLoading(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/available-models`, {
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
        }
      }
    } catch (error) {
      // Silent failure on auto-load
    } finally {
      setAutoLoading(false);
    }
  };

  const autoFetchExtractionModels = async () => {
    if (!extractionModelSettings.enabled) return;
    const extIsCloud = isCloudProvider(currentExtractionEngine);
    if (!extIsCloud && !extractionModelSettings.url) return;
    if (extIsCloud && !extractionModelSettings.api_key) return;
    setAutoLoadingExtraction(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/extraction-model/available-models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          url: extractionModelSettings.url,
          api_key: extractionModelSettings.api_key,
          api_type: currentExtractionEngine || 'openai-compatible',
        }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setAvailableExtractionModels(data.models);
        }
      }
    } catch (error) {
      // Silent failure on auto-load
    } finally {
      setAutoLoadingExtraction(false);
    }
  };

  const fetchAvailableModels = async () => {
    const isCloud = isCloudProvider(llmSettings.api_type);
    if (!isCloud && !llmSettings.api_url) {
      showMessage('Please enter an API URL first', 'error');
      return;
    }
    if (isCloud && !llmSettings.api_key) {
      showMessage('Please enter an API key first', 'error');
      return;
    }

    setLoadingModels(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/available-models`, {
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

  const fetchExtractionModels = async () => {
    const extIsCloud = isCloudProvider(currentExtractionEngine);
    if (!extIsCloud && !extractionModelSettings.url) {
      showMessage('Please enter an API URL first', 'error');
      return;
    }
    if (extIsCloud && !extractionModelSettings.api_key) {
      showMessage('Please enter an API key first', 'error');
      return;
    }

    setLoadingExtractionModels(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/extraction-model/available-models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          url: extractionModelSettings.url,
          api_key: extractionModelSettings.api_key,
          api_type: currentExtractionEngine || 'openai-compatible',
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setAvailableExtractionModels(data.models);
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
      setLoadingExtractionModels(false);
    }
  };

  const handleEngineChange = (newEngine: string) => {
    // Save current settings to the current engine
    if (currentEngine && currentEngine !== '') {
      setEngineSettings({
        ...engineSettings,
        [currentEngine]: { ...llmSettings }
      });
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
        timeout_total: undefined,
        api_url: '',
        api_key: '',
        api_type: newEngine,
        model_name: '',
        completion_mode: 'chat',
        text_completion_template: '',
        text_completion_preset: 'llama3',
        reasoning_effort: null,
        show_thinking_content: true,
      });
    }

    setCurrentEngine(newEngine);
    setAvailableModels([]);
  };

  const handleExtractionEngineChange = (newEngine: string) => {
    // Save current extraction settings to the current engine
    if (currentExtractionEngine && currentExtractionEngine !== '') {
      setExtractionEngineSettings({
        ...extractionEngineSettings,
        [currentExtractionEngine]: { ...extractionModelSettings }
      });
    }

    // Load settings for the new engine
    if (newEngine && extractionEngineSettings[newEngine]) {
      setExtractionModelSettings({
        ...extractionEngineSettings[newEngine],
        api_type: newEngine,
      });
    } else {
      // Default settings for new engine
      setExtractionModelSettings({
        ...extractionModelSettings,
        url: '',
        api_key: '',
        model_name: '',
        api_type: newEngine,
      });
    }

    setCurrentExtractionEngine(newEngine);
    setAvailableExtractionModels([]);
  };

  const testConnection = async () => {
    setTestingConnection(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/test-api-connection`, {
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
  };

  const testExtractionConnection = async () => {
    setTestingExtractionConnection(true);
    setConnectionTestResult(null);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/extraction-model/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          url: extractionModelSettings.url,
          api_key: extractionModelSettings.api_key,
          model_name: extractionModelSettings.model_name,
          api_type: currentExtractionEngine || 'openai-compatible',
        }),
      });
      const result = await response.json();
      setConnectionTestResult({
        success: result.success,
        message: result.message,
      });
    } catch (error) {
      setConnectionTestResult({
        success: false,
        message: `Connection test failed: ${error}`,
      });
    } finally {
      setTestingExtractionConnection(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">LLM Settings</h3>
        <p className="text-sm text-gray-400 mb-4">
          Configure your language model provider and generation parameters
        </p>

        {/* LLM Sub-tabs */}
        <div className="flex gap-2 mb-6 border-b border-gray-700 pb-2">
          <button
            onClick={() => setLlmSubTab('main')}
            className={`px-4 py-2 rounded-t-lg font-medium transition-colors ${
              llmSubTab === 'main'
                ? 'bg-gray-700 text-white border-b-2 border-blue-500'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            Main Settings
          </button>
          <button
            onClick={() => setLlmSubTab('samplers')}
            className={`px-4 py-2 rounded-t-lg font-medium transition-colors ${
              llmSubTab === 'samplers'
                ? 'bg-gray-700 text-white border-b-2 border-blue-500'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            Advanced Samplers
          </button>
        </div>

        {/* Main LLM Sub-tab */}
        {llmSubTab === 'main' && (
          <>
            {/* Main LLM */}
            <div className="space-y-4 mb-8">
              <h4 className="text-md font-semibold text-white mb-3">Main LLM</h4>

              {/* API Configuration */}
              <div className="space-y-4">
                <h5 className="text-sm font-semibold text-white mb-2">API Configuration</h5>

                {/* API Type */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">API Engine</label>
                  <select
                    value={currentEngine}
                    onChange={(e) => handleEngineChange(e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                  >
                    <option value="">Select API Engine...</option>
                    {cloudProviders.length > 0 && (
                      <optgroup label="Cloud Providers">
                        {cloudProviders.map(p => (
                          <option key={p.id} value={p.id}>{p.label}</option>
                        ))}
                      </optgroup>
                    )}
                    {localProviders.length > 0 && (
                      <optgroup label="Local / Self-Hosted">
                        {localProviders.map(p => (
                          <option key={p.id} value={p.id}>{p.label}</option>
                        ))}
                      </optgroup>
                    )}
                    {providers.length === 0 && (
                      <>
                        <option value="openai-compatible">OpenAI Compatible</option>
                        <option value="openai">OpenAI Official</option>
                        <option value="ollama">Ollama</option>
                      </>
                    )}
                  </select>
                </div>

                {/* API URL - hidden for cloud providers */}
                {!isCloudProvider(currentEngine) && (
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">API URL</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={llmSettings.api_url}
                        onChange={(e) => setLlmSettings({ ...llmSettings, api_url: e.target.value })}
                        className="flex-1 bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        placeholder="http://localhost:1234"
                      />
                      <button
                        onClick={testConnection}
                        disabled={testingConnection}
                        className="px-4 py-2 theme-btn-secondary rounded-md font-medium disabled:opacity-50"
                      >
                        {testingConnection ? 'Testing...' : 'Test'}
                      </button>
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    API Key{isCloudProvider(currentEngine) ? ' (required)' : ' (optional)'}
                  </label>
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
                      placeholder={isCloudProvider(currentEngine) ? 'model-name' : 'gpt-4'}
                    />
                    <button
                      onClick={fetchAvailableModels}
                      disabled={loadingModels || autoLoading || (!isCloudProvider(currentEngine) && !llmSettings.api_url)}
                      className="px-4 py-2 theme-btn-primary rounded-md font-medium disabled:opacity-50"
                    >
                      {loadingModels || autoLoading ? 'Loading...' : 'Fetch Models'}
                    </button>
                  </div>
                </div>

                {/* Available Models Dropdown */}
                {availableModels.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Select Model</label>
                    <select
                      value={llmSettings.model_name ?? ''}
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

                {/* Completion Mode Toggle */}
                <div className="pt-4 border-t border-gray-700">
                  <label className="block text-sm font-medium text-white mb-3">Completion API Mode</label>
                  <div className="flex gap-4">
                    <label className="flex items-center cursor-pointer">
                      <input
                        type="radio"
                        value="chat"
                        checked={llmSettings.completion_mode === 'chat'}
                        onChange={() => setLlmSettings({ ...llmSettings, completion_mode: 'chat' })}
                        className="mr-2"
                      />
                      <span className="text-white">Chat Completion API</span>
                    </label>
                    <label className="flex items-center cursor-pointer">
                      <input
                        type="radio"
                        value="text"
                        checked={llmSettings.completion_mode === 'text'}
                        onChange={() => setLlmSettings({ ...llmSettings, completion_mode: 'text' })}
                        className="mr-2"
                      />
                      <span className="text-white">Text Completion API</span>
                    </label>
                  </div>
                  <p className="text-sm text-gray-400 mt-2">
                    Chat uses message format. Text uses raw prompts with templates (for instruction-tuned models).
                  </p>
                </div>

                {/* Text Completion Template Configuration */}
                {llmSettings.completion_mode === 'text' && (
                  <div className="pt-4 pb-4 px-4 bg-gray-800/50 rounded-lg border border-gray-700">
                    <h4 className="text-sm font-medium text-white mb-3">Text Completion Template</h4>
                    <TextCompletionTemplateEditor
                      value={safeParseJSON(llmSettings.text_completion_template)}
                      preset={llmSettings.text_completion_preset || 'llama3'}
                      onChange={(template, preset) => {
                        setLlmSettings({
                          ...llmSettings,
                          text_completion_template: JSON.stringify(template),
                          text_completion_preset: preset
                        });
                      }}
                    />
                    <div className="mt-4 p-3 bg-blue-900/20 border border-blue-700 rounded">
                      <p className="text-sm text-gray-300">
                        ℹ️ <strong>Thinking Tag Removal:</strong> Thinking/reasoning tags are automatically detected and removed from responses.
                      </p>
                    </div>
                  </div>
                )}

                {/* Reasoning/Thinking Settings */}
                <div className="pt-4 pb-4 px-4 bg-gray-800/50 rounded-lg border border-gray-700">
                  <h4 className="text-sm font-medium text-white mb-3">Reasoning / Thinking</h4>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">Reasoning Effort</label>
                      <select
                        value={llmSettings.reasoning_effort || 'auto'}
                        onChange={(e) => setLlmSettings({
                          ...llmSettings,
                          reasoning_effort: e.target.value === 'auto' ? null : e.target.value
                        })}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg p-2.5 text-white focus:border-pink-500 focus:ring-1 focus:ring-pink-500"
                      >
                        <option value="auto">Auto (Model Default)</option>
                        <option value="disabled">Disabled</option>
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                      <p className="text-xs text-gray-400 mt-1">
                        Controls how much the model "thinks" before responding. Higher = better quality but more tokens/cost.
                      </p>
                    </div>

                    {llmSettings.reasoning_effort !== 'disabled' && (
                      <div>
                        <label className="flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={llmSettings.show_thinking_content ?? true}
                            onChange={(e) => setLlmSettings({
                              ...llmSettings,
                              show_thinking_content: e.target.checked
                            })}
                            className="mr-2 rounded border-gray-600 bg-gray-700 text-pink-500 focus:ring-pink-500"
                          />
                          <span className="text-white text-sm">Show Thinking Content</span>
                        </label>
                        <p className="text-xs text-gray-400 mt-1 ml-6">
                          When enabled, shows the model's reasoning in an expandable box.
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Local Thinking Model Settings */}
                <div className="pt-4 pb-4 px-4 bg-gray-800/50 rounded-lg border border-gray-700">
                  <h4 className="text-sm font-medium text-white mb-3">Thinking Control</h4>
                  <p className="text-xs text-gray-400 mb-3">
                    For local thinking models (Qwen3, DeepSeek, etc.) that produce &lt;think&gt; tags. Not needed for API providers.
                  </p>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">Thinking Model Type</label>
                      <select
                        value={llmSettings.thinking_model_type || 'none'}
                        onChange={(e) => setLlmSettings({
                          ...llmSettings,
                          thinking_model_type: e.target.value === 'none' ? null : e.target.value
                        })}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg p-2.5 text-white focus:border-pink-500 focus:ring-1 focus:ring-pink-500"
                      >
                        {THINKING_DISABLE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <div className="text-xs text-gray-400 mt-1">
                        {THINKING_DISABLE_OPTIONS.find(o => o.value === (llmSettings.thinking_model_type || 'none'))?.description}
                      </div>
                    </div>

                    {/* Custom Pattern Input */}
                    {llmSettings.thinking_model_type === 'custom' && (
                      <div>
                        <label className="block text-sm font-medium text-white mb-2">
                          Custom Pattern (Regex)
                        </label>
                        <input
                          type="text"
                          value={llmSettings.thinking_model_custom_pattern ?? ''}
                          onChange={(e) => setLlmSettings({
                            ...llmSettings,
                            thinking_model_custom_pattern: e.target.value
                          })}
                          className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-sm"
                          placeholder="<think>[\s\S]*?</think>"
                        />
                        <div className="text-xs text-gray-400 mt-1">
                          Regex pattern to strip from responses
                        </div>
                      </div>
                    )}

                    {/* Per-task thinking toggle */}
                    {llmSettings.thinking_model_type && llmSettings.thinking_model_type !== 'none' && (
                      <div>
                        <label className="flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={llmSettings.thinking_enabled_generation ?? false}
                            onChange={(e) => setLlmSettings({
                              ...llmSettings,
                              thinking_enabled_generation: e.target.checked
                            })}
                            className="mr-2 rounded border-gray-600 bg-gray-700 text-pink-500 focus:ring-pink-500"
                          />
                          <span className="text-white text-sm">Thinking for story generation</span>
                        </label>
                        <p className="text-xs text-gray-400 mt-1 ml-6">
                          Scenes, variants, choices, summaries. Adds latency but may improve quality.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
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
                    step="0.05"
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
                    Top K: {llmSettings.top_k}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    value={llmSettings.top_k}
                    onChange={(e) => setLlmSettings({ ...llmSettings, top_k: parseInt(e.target.value) })}
                    className="w-full"
                  />
                  <p className="text-xs text-gray-400 mt-1">Limits token pool size</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    Repetition Penalty: {llmSettings.repetition_penalty}
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="2"
                    step="0.05"
                    value={llmSettings.repetition_penalty}
                    onChange={(e) => setLlmSettings({ ...llmSettings, repetition_penalty: parseFloat(e.target.value) })}
                    className="w-full"
                  />
                  <p className="text-xs text-gray-400 mt-1">Penalizes repeated tokens</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-white mb-2">Max Tokens</label>
                  <input
                    type="number"
                    value={llmSettings.max_tokens ?? ''}
                    onChange={(e) => setLlmSettings({ ...llmSettings, max_tokens: e.target.value === '' ? '' as any : parseInt(e.target.value) })}
                    onBlur={(e) => { const v = parseInt(e.target.value); if (isNaN(v)) setLlmSettings({ ...llmSettings, max_tokens: 2048 }); }}
                    className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    min="256"
                    max="32000"
                  />
                  <p className="text-xs text-gray-400 mt-1">Maximum tokens to generate per response</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-white mb-2">Timeout (seconds)</label>
                  <input
                    type="number"
                    value={llmSettings.timeout_total ?? ''}
                    onChange={(e) => setLlmSettings({ ...llmSettings, timeout_total: e.target.value === '' ? '' as any : parseInt(e.target.value) })}
                    onBlur={(e) => { const v = parseInt(e.target.value); if (isNaN(v)) setLlmSettings({ ...llmSettings, timeout_total: 120 }); }}
                    className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    min="30"
                    max="600"
                  />
                  <p className="text-xs text-gray-400 mt-1">Maximum time to wait for API response</p>
                </div>
              </div>

              {/* Extraction Model Settings */}
              <div className="space-y-4 pt-6 border-t border-gray-700">
                <h4 className="text-md font-semibold text-white mb-3">Extraction Model (Optional)</h4>
                <p className="text-sm text-gray-400 mb-4">
                  Configure a separate, smaller LLM for extraction tasks (character moments, summaries, etc.)
                </p>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={extractionModelSettings.enabled}
                    onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, enabled: e.target.checked })}
                    className="w-4 h-4 rounded"
                  />
                  <span className="text-sm text-white">Enable separate extraction model</span>
                </label>

                {extractionModelSettings.enabled && (
                  <div className="space-y-4 mt-4 p-4 bg-gray-800/50 rounded-lg border border-gray-600">
                    {/* Extraction Engine Selector */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">API Engine</label>
                      <select
                        value={currentExtractionEngine}
                        onChange={(e) => handleExtractionEngineChange(e.target.value)}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                      >
                        <option value="">Select API Engine...</option>
                        {cloudProviders.length > 0 && (
                          <optgroup label="Cloud Providers">
                            {cloudProviders.map(p => (
                              <option key={p.id} value={p.id}>{p.label}</option>
                            ))}
                          </optgroup>
                        )}
                        {localProviders.length > 0 && (
                          <optgroup label="Local / Self-Hosted">
                            {localProviders.map(p => (
                              <option key={p.id} value={p.id}>{p.label}</option>
                            ))}
                          </optgroup>
                        )}
                        {providers.length === 0 && (
                          <>
                            <option value="openai-compatible">OpenAI Compatible</option>
                            <option value="openai">OpenAI Official</option>
                            <option value="ollama">Ollama</option>
                          </>
                        )}
                      </select>
                    </div>

                    {/* API URL - hidden for cloud providers */}
                    {!isExtractionCloud && (
                      <div>
                        <label className="block text-sm font-medium text-white mb-2">API URL</label>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={extractionModelSettings.url}
                            onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, url: e.target.value })}
                            className="flex-1 bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                            placeholder="http://localhost:1234/v1"
                          />
                          <button
                            onClick={fetchExtractionModels}
                            disabled={loadingExtractionModels || autoLoadingExtraction}
                            className="px-4 py-2 theme-btn-secondary rounded-md font-medium disabled:opacity-50"
                          >
                            {loadingExtractionModels || autoLoadingExtraction ? 'Loading...' : 'Fetch'}
                          </button>
                        </div>
                      </div>
                    )}

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        API Key{isExtractionCloud ? ' (required)' : ' (optional)'}
                      </label>
                      <input
                        type="password"
                        value={extractionModelSettings.api_key}
                        onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, api_key: e.target.value })}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        placeholder={isExtractionCloud ? 'sk-...' : 'Optional'}
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">Model Name</label>
                      <div className="flex gap-2">
                        <div className="flex-1">
                          {availableExtractionModels.length > 0 ? (
                            <select
                              value={extractionModelSettings.model_name}
                              onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, model_name: e.target.value })}
                              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                            >
                              <option value="">Select a model...</option>
                              {availableExtractionModels.map((model) => (
                                <option key={model} value={model}>{model}</option>
                              ))}
                            </select>
                          ) : (
                            <input
                              type="text"
                              value={extractionModelSettings.model_name}
                              onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, model_name: e.target.value })}
                              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                              placeholder="qwen2.5-3b-instruct"
                            />
                          )}
                        </div>
                        {isExtractionCloud && (
                          <button
                            onClick={fetchExtractionModels}
                            disabled={loadingExtractionModels || autoLoadingExtraction}
                            className="px-4 py-2 theme-btn-primary rounded-md font-medium disabled:opacity-50"
                          >
                            {loadingExtractionModels || autoLoadingExtraction ? 'Loading...' : 'Fetch Models'}
                          </button>
                        )}
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Temperature: {extractionModelSettings.temperature}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={extractionModelSettings.temperature}
                        onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, temperature: parseFloat(e.target.value) })}
                        className="w-full"
                      />
                      <div className="text-xs text-gray-400 mt-1">
                        Lower is better for extraction (0.1-0.3 recommended)
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-white mb-2">Max Tokens</label>
                      <input
                        type="number"
                        value={extractionModelSettings.max_tokens ?? ''}
                        onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, max_tokens: e.target.value === '' ? '' as any : parseInt(e.target.value) })}
                        onBlur={(e) => { const v = parseInt(e.target.value); if (isNaN(v)) setExtractionModelSettings({ ...extractionModelSettings, max_tokens: 1000 }); }}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                        min="256"
                        max="4000"
                      />
                      <div className="text-xs text-gray-400 mt-1">
                        Maximum tokens per extraction (1000 recommended)
                      </div>
                    </div>

                    {/* Fallback Toggle */}
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={extractionModelSettings.fallback_to_main}
                        onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, fallback_to_main: e.target.checked })}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Fallback to main LLM on failure</span>
                    </label>
                    <div className="text-xs text-gray-400 ml-6">
                      If enabled, uses main LLM if extraction model fails
                    </div>

                    {/* Use Main LLM for Plot Extraction */}
                    <label className="flex items-center gap-2 cursor-pointer mt-3">
                      <input
                        type="checkbox"
                        checked={extractionModelSettings.use_main_llm_for_plot_extraction || false}
                        onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, use_main_llm_for_plot_extraction: e.target.checked })}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Use main LLM for plot extraction</span>
                    </label>
                    <div className="text-xs text-gray-400 ml-6">
                      Plot event extraction requires higher accuracy - use main LLM instead of extraction model
                    </div>

                    {/* Advanced Sampling Settings */}
                    <div className="pt-4 border-t border-gray-600">
                      <h5 className="text-sm font-semibold text-white mb-3">Advanced Sampling</h5>

                      <div className="space-y-4">
                        {/* Top P */}
                        <div>
                          <label className="block text-sm font-medium text-white mb-2">
                            Top P: {extractionModelSettings.top_p ?? 1.0}
                          </label>
                          <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.05"
                            value={extractionModelSettings.top_p ?? 1.0}
                            onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, top_p: parseFloat(e.target.value) })}
                            className="w-full"
                          />
                          <div className="text-xs text-gray-400 mt-1">
                            Nucleus sampling (0.95 recommended for GLM)
                          </div>
                        </div>

                        {/* Repetition Penalty */}
                        <div>
                          <label className="block text-sm font-medium text-white mb-2">
                            Repetition Penalty: {extractionModelSettings.repetition_penalty ?? 1.0}
                          </label>
                          <input
                            type="range"
                            min="0"
                            max="2"
                            step="0.05"
                            value={extractionModelSettings.repetition_penalty ?? 1.0}
                            onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, repetition_penalty: parseFloat(e.target.value) })}
                            className="w-full"
                          />
                          <div className="text-xs text-gray-400 mt-1">
                            1.0 = disabled (recommended for GLM, Qwen)
                          </div>
                        </div>

                        {/* Min P */}
                        <div>
                          <label className="block text-sm font-medium text-white mb-2">
                            Min P: {(extractionModelSettings.min_p ?? 0).toFixed(3)}
                          </label>
                          <input
                            type="range"
                            min="0"
                            max="0.1"
                            step="0.001"
                            value={extractionModelSettings.min_p ?? 0}
                            onChange={(e) => setExtractionModelSettings({ ...extractionModelSettings, min_p: parseFloat(e.target.value) })}
                            className="w-full"
                          />
                          <div className="text-xs text-gray-400 mt-1">
                            Minimum probability threshold (0.01 for llama.cpp)
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Thinking Model Settings */}
                    <div className="pt-4 border-t border-gray-600">
                      <h5 className="text-sm font-semibold text-white mb-3">Thinking Control</h5>

                      <div className="space-y-4">
                        {/* Thinking Model Type Dropdown */}
                        <div>
                          <label className="block text-sm font-medium text-white mb-2">
                            Thinking Model Type
                          </label>
                          <select
                            value={extractionModelSettings.thinking_disable_method ?? 'none'}
                            onChange={(e) => setExtractionModelSettings({
                              ...extractionModelSettings,
                              thinking_disable_method: e.target.value as ExtractionModelSettings['thinking_disable_method']
                            })}
                            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                          >
                            {THINKING_DISABLE_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <div className="text-xs text-gray-400 mt-1">
                            {THINKING_DISABLE_OPTIONS.find(o => o.value === (extractionModelSettings.thinking_disable_method ?? 'none'))?.description}
                          </div>
                        </div>

                        {/* Custom Pattern Input (only shown when method is 'custom') */}
                        {extractionModelSettings.thinking_disable_method === 'custom' && (
                          <div>
                            <label className="block text-sm font-medium text-white mb-2">
                              Custom Pattern (Regex)
                            </label>
                            <input
                              type="text"
                              value={extractionModelSettings.thinking_disable_custom ?? ''}
                              onChange={(e) => setExtractionModelSettings({
                                ...extractionModelSettings,
                                thinking_disable_custom: e.target.value
                              })}
                              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-sm"
                              placeholder="<think>[\s\S]*?</think>"
                            />
                            <div className="text-xs text-gray-400 mt-1">
                              Regex pattern to strip from responses (e.g., &lt;think&gt;...&lt;/think&gt;)
                            </div>
                          </div>
                        )}

                        {/* Per-task thinking toggles (only when a thinking model is configured) */}
                        {extractionModelSettings.thinking_disable_method !== 'none' && (
                          <div className="space-y-3 mt-3 p-3 bg-gray-700/30 rounded-lg">
                            <p className="text-xs text-gray-400 font-medium">Choose which tasks use chain-of-thought reasoning</p>
                            <div>
                              <label className="flex items-center cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={extractionModelSettings.thinking_enabled_extractions ?? false}
                                  onChange={(e) => setExtractionModelSettings({
                                    ...extractionModelSettings,
                                    thinking_enabled_extractions: e.target.checked
                                  })}
                                  className="mr-2 rounded border-gray-600 bg-gray-700 text-pink-500 focus:ring-pink-500"
                                />
                                <span className="text-white text-sm">Thinking for extractions</span>
                              </label>
                              <p className="text-xs text-gray-400 mt-1 ml-6">
                                Entity, NPC, plot, scene event extractions. Usually unnecessary — adds latency.
                              </p>
                            </div>
                            <div>
                              <label className="flex items-center cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={extractionModelSettings.thinking_enabled_memory ?? true}
                                  onChange={(e) => setExtractionModelSettings({
                                    ...extractionModelSettings,
                                    thinking_enabled_memory: e.target.checked
                                  })}
                                  className="mr-2 rounded border-gray-600 bg-gray-700 text-pink-500 focus:ring-pink-500"
                                />
                                <span className="text-white text-sm">Thinking for memory & recall</span>
                              </label>
                              <p className="text-xs text-gray-400 mt-1 ml-6">
                                Query decomposition and agentic recall. Recommended — these tasks benefit from reasoning.
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Test Connection Button */}
                    <div className="flex items-center gap-3">
                      <button
                        onClick={testExtractionConnection}
                        disabled={testingExtractionConnection}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-medium"
                      >
                        {testingExtractionConnection ? 'Testing...' : 'Test Connection'}
                      </button>
                      {connectionTestResult && (
                        <span className={`text-sm ${connectionTestResult.success ? 'text-green-400' : 'text-red-400'}`}>
                          {connectionTestResult.success ? '✓' : '✗'} {connectionTestResult.message}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Save Button */}
            <div className="flex justify-end pt-4 border-t border-gray-700">
              <button
                onClick={onSave}
                className="px-6 py-2 theme-btn-primary rounded-lg font-semibold"
              >
                Save LLM Settings
              </button>
            </div>
          </>
        )}

        {/* Advanced Samplers Sub-tab */}
        {llmSubTab === 'samplers' && (
          <SamplersSettings
            samplerSettings={samplerSettings}
            setSamplerSettings={setSamplerSettings}
            onSave={onSave}
          />
        )}
      </div>
    </div>
  );
}

// Separate component for samplers to keep file manageable
interface SamplersSettingsProps {
  samplerSettings: SamplerSettings;
  setSamplerSettings: (settings: SamplerSettings) => void;
  onSave: () => Promise<void>;
}

function SamplersSettings({ samplerSettings, setSamplerSettings, onSave }: SamplersSettingsProps) {
  return (
    <div className="space-y-6">
      <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-4 mb-4">
        <p className="text-sm text-blue-200">
          <strong>Advanced Samplers</strong> - These settings are passed to TabbyAPI and other OpenAI-compatible APIs via extra_body.
          Only enabled samplers will be sent. Disabled samplers use API defaults.
        </p>
      </div>

      {/* Basic Sampling */}
      <div className="space-y-4">
        <h4 className="text-md font-semibold text-white border-b border-gray-700 pb-2">Basic Sampling</h4>

        {/* Min P */}
        <SamplerSlider
          label="Min P"
          description="Minimum probability threshold. Tokens below this are excluded."
          enabled={samplerSettings.min_p.enabled}
          value={samplerSettings.min_p.value}
          min={0}
          max={1}
          step={0.01}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            min_p: { ...samplerSettings.min_p, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            min_p: { ...samplerSettings.min_p, value }
          })}
        />

        {/* Top A */}
        <SamplerSlider
          label="Top A"
          description="Top-A sampling. Considers tokens with probability above top_a * max_prob."
          enabled={samplerSettings.top_a.enabled}
          value={samplerSettings.top_a.value}
          min={0}
          max={1}
          step={0.01}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            top_a: { ...samplerSettings.top_a, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            top_a: { ...samplerSettings.top_a, value }
          })}
        />

        {/* Smoothing Factor */}
        <SamplerSlider
          label="Smoothing Factor"
          description="Quadratic sampling smoothing factor."
          enabled={samplerSettings.smoothing_factor.enabled}
          value={samplerSettings.smoothing_factor.value}
          min={0}
          max={10}
          step={0.1}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            smoothing_factor: { ...samplerSettings.smoothing_factor, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            smoothing_factor: { ...samplerSettings.smoothing_factor, value }
          })}
        />
      </div>

      {/* Advanced Sampling */}
      <div className="space-y-4">
        <h4 className="text-md font-semibold text-white border-b border-gray-700 pb-2">Advanced Sampling</h4>

        {/* TFS */}
        <SamplerSlider
          label="TFS (Tail Free Sampling)"
          description="Removes low-probability tail tokens. 1.0 = disabled."
          enabled={samplerSettings.tfs.enabled}
          value={samplerSettings.tfs.value}
          min={0}
          max={1}
          step={0.01}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            tfs: { ...samplerSettings.tfs, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            tfs: { ...samplerSettings.tfs, value }
          })}
        />

        {/* Typical */}
        <SamplerSlider
          label="Typical P"
          description="Locally typical sampling. 1.0 = disabled."
          enabled={samplerSettings.typical.enabled}
          value={samplerSettings.typical.value}
          min={0}
          max={1}
          step={0.01}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            typical: { ...samplerSettings.typical, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            typical: { ...samplerSettings.typical, value }
          })}
        />
      </div>

      {/* Penalties */}
      <div className="space-y-4">
        <h4 className="text-md font-semibold text-white border-b border-gray-700 pb-2">Penalties</h4>

        {/* Frequency Penalty */}
        <SamplerSlider
          label="Frequency Penalty"
          description="Penalizes tokens based on frequency in generated text."
          enabled={samplerSettings.frequency_penalty.enabled}
          value={samplerSettings.frequency_penalty.value}
          min={-2}
          max={2}
          step={0.1}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            frequency_penalty: { ...samplerSettings.frequency_penalty, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            frequency_penalty: { ...samplerSettings.frequency_penalty, value }
          })}
        />

        {/* Presence Penalty */}
        <SamplerSlider
          label="Presence Penalty"
          description="Penalizes tokens that have appeared at all."
          enabled={samplerSettings.presence_penalty.enabled}
          value={samplerSettings.presence_penalty.value}
          min={-2}
          max={2}
          step={0.1}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            presence_penalty: { ...samplerSettings.presence_penalty, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            presence_penalty: { ...samplerSettings.presence_penalty, value }
          })}
        />
      </div>

      {/* DRY Settings */}
      <div className="space-y-4">
        <h4 className="text-md font-semibold text-white border-b border-gray-700 pb-2">DRY (Don't Repeat Yourself)</h4>

        {/* DRY Multiplier */}
        <SamplerSlider
          label="DRY Multiplier"
          description="Strength of DRY penalty. 0 = disabled."
          enabled={samplerSettings.dry_multiplier.enabled}
          value={samplerSettings.dry_multiplier.value}
          min={0}
          max={5}
          step={0.1}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            dry_multiplier: { ...samplerSettings.dry_multiplier, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            dry_multiplier: { ...samplerSettings.dry_multiplier, value }
          })}
        />

        {/* DRY Base */}
        <SamplerSlider
          label="DRY Base"
          description="Base for exponential DRY penalty growth."
          enabled={samplerSettings.dry_base.enabled}
          value={samplerSettings.dry_base.value}
          min={0}
          max={5}
          step={0.1}
          onEnabledChange={(enabled) => setSamplerSettings({
            ...samplerSettings,
            dry_base: { ...samplerSettings.dry_base, enabled }
          })}
          onValueChange={(value) => setSamplerSettings({
            ...samplerSettings,
            dry_base: { ...samplerSettings.dry_base, value }
          })}
        />
      </div>

      {/* Save Button for Samplers */}
      <div className="flex justify-end pt-4 border-t border-gray-700">
        <button
          onClick={onSave}
          className="px-6 py-2 theme-btn-primary rounded-lg font-semibold"
        >
          Save Sampler Settings
        </button>
      </div>
    </div>
  );
}

// Reusable slider component for samplers
interface SamplerSliderProps {
  label: string;
  description: string;
  enabled: boolean;
  value: number;
  min: number;
  max: number;
  step: number;
  onEnabledChange: (enabled: boolean) => void;
  onValueChange: (value: number) => void;
}

function SamplerSlider({
  label,
  description,
  enabled,
  value,
  min,
  max,
  step,
  onEnabledChange,
  onValueChange,
}: SamplerSliderProps) {
  return (
    <div className="flex items-start gap-4 p-3 bg-gray-800/50 rounded-lg">
      <label className="flex items-center cursor-pointer mt-1">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onEnabledChange(e.target.checked)}
          className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-blue-500"
        />
      </label>
      <div className="flex-1">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-white">{label}: {value}</label>
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onValueChange(parseFloat(e.target.value))}
          disabled={!enabled}
          className="w-full disabled:opacity-50"
        />
        <p className="text-xs text-gray-400 mt-1">{description}</p>
      </div>
    </div>
  );
}
