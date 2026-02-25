'use client';

import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { useConfig } from '@/contexts/ConfigContext';
import { SamplerSettings, DEFAULT_SAMPLER_SETTINGS } from '@/types/settings';
import TextCompletionTemplateEditor from '../../TextCompletionTemplateEditor';
import { SettingsTabProps, LLMSettings, ExtractionModelSettings, EmbeddingModelSettings, ReembedProgress, LLMProvider, THINKING_DISABLE_OPTIONS, ConfiguredProviders } from '../types';

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
  embeddingSettings: EmbeddingModelSettings;
  setEmbeddingSettings: (settings: EmbeddingModelSettings) => void;
  configuredProviders: ConfiguredProviders;
  setConfiguredProviders: (providers: ConfiguredProviders) => void;
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
  embeddingSettings,
  setEmbeddingSettings,
  configuredProviders,
  setConfiguredProviders,
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

  // Embedding model state
  const [embeddingProviders, setEmbeddingProviders] = useState<LLMProvider[]>([]);
  const [testingEmbedding, setTestingEmbedding] = useState(false);
  const [embeddingTestResult, setEmbeddingTestResult] = useState<{success: boolean; message: string; dimensions?: number} | null>(null);
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [loadingEmbeddingModels, setLoadingEmbeddingModels] = useState(false);
  const [reembedProgress, setReembedProgress] = useState<ReembedProgress | null>(null);
  const [pollingReembed, setPollingReembed] = useState(false);

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
    loadEmbeddingProviders();
    loadExtractionPresets();
    // Auto-fetch models silently if API URL is configured
    autoFetchModels();
    autoFetchExtractionModels();
    // Check if re-embed is running
    checkReembedProgress();
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

  const loadEmbeddingProviders = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/embedding-providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setEmbeddingProviders(data.providers || []);
      }
    } catch (error) {
      console.error('Failed to load embedding providers:', error);
    }
  };

  const testEmbeddingConnection = async () => {
    const creds = getProviderCredentials(embeddingSettings.provider);
    setTestingEmbedding(true);
    setEmbeddingTestResult(null);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/embedding-model/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider: embeddingSettings.provider,
          api_url: creds.api_url,
          api_key: creds.api_key,
          model_name: embeddingSettings.model_name,
        }),
      });
      const data = await response.json();
      setEmbeddingTestResult(data);
      if (data.success && data.dimensions) {
        setEmbeddingSettings({ ...embeddingSettings, dimensions: data.dimensions });
      }
    } catch (error) {
      setEmbeddingTestResult({ success: false, message: `Error: ${error}` });
    } finally {
      setTestingEmbedding(false);
    }
  };

  const fetchEmbeddingModels = async () => {
    const creds = getProviderCredentials(embeddingSettings.provider);
    setLoadingEmbeddingModels(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/embedding-model/available-models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          provider: embeddingSettings.provider,
          api_url: creds.api_url,
          api_key: creds.api_key,
        }),
      });
      const data = await response.json();
      if (data.success) {
        setEmbeddingModels(data.models || []);
      }
    } catch (error) {
      console.error('Failed to fetch embedding models:', error);
    } finally {
      setLoadingEmbeddingModels(false);
    }
  };

  const startReembed = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/embedding-model/reembed`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      });
      const data = await response.json();
      if (data.success) {
        setPollingReembed(true);
        pollReembedProgress();
      } else {
        showMessage(data.message || 'Failed to start re-embedding', 'error');
      }
    } catch (error) {
      showMessage('Failed to start re-embedding', 'error');
    }
  };

  const cancelReembed = async () => {
    try {
      await fetch(`${await getApiBaseUrl()}/api/settings/embedding-model/reembed/cancel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
    } catch (error) {
      console.error('Failed to cancel re-embedding:', error);
    }
  };

  const checkReembedProgress = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/embedding-model/reembed/progress`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'running') {
          setReembedProgress(data);
          setPollingReembed(true);
          pollReembedProgress();
        } else if (data.status !== 'idle') {
          setReembedProgress(data);
        }
      }
    } catch (error) {
      // Ignore — may not have started yet
    }
  };

  const pollReembedProgress = () => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${await getApiBaseUrl()}/api/settings/embedding-model/reembed/progress`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setReembedProgress(data);
          if (data.status !== 'running') {
            clearInterval(interval);
            setPollingReembed(false);
            if (data.status === 'completed') {
              showMessage('Re-embedding completed successfully!', 'success');
              setEmbeddingSettings({ ...embeddingSettings, needs_reembed: false });
            }
          }
        }
      } catch {
        clearInterval(interval);
        setPollingReembed(false);
      }
    }, 2000);
  };

  const embeddingCloudProviders = embeddingProviders.filter(p => p.category === 'cloud');
  const embeddingLocalProviders = embeddingProviders.filter(p => p.category === 'local');
  const isEmbeddingCloud = embeddingCloudProviders.some(p => p.id === embeddingSettings.provider);
  const isEmbeddingLocalApi = embeddingSettings.provider !== 'local' && !isEmbeddingCloud;
  const needsReembed = embeddingSettings.needs_reembed;

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
    if (!currentEngine) return;
    // Resolve credentials from configured providers
    const creds = getProviderCredentials(currentEngine);
    const isCloud = isCloudProvider(currentEngine);
    if (!isCloud && !creds.api_url) return;
    if (isCloud && !creds.api_key) return;
    setAutoLoading(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/available-models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          api_url: creds.api_url,
          api_key: creds.api_key,
          api_type: currentEngine,
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
    if (!extractionModelSettings.enabled || !currentExtractionEngine) return;
    const creds = getProviderCredentials(currentExtractionEngine);
    const isCloud = isCloudProvider(currentExtractionEngine);
    if (!isCloud && !creds.api_url) return;
    if (isCloud && !creds.api_key) return;
    setAutoLoadingExtraction(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/extraction-model/available-models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          url: creds.api_url,
          api_key: creds.api_key,
          api_type: currentExtractionEngine,
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
    if (!currentEngine) {
      showMessage('Please select a provider first', 'error');
      return;
    }
    const creds = getProviderCredentials(currentEngine);
    const isCloud = isCloudProvider(currentEngine);
    if (!isCloud && !creds.api_url) {
      showMessage('Provider has no API URL configured. Edit it in "Your Providers".', 'error');
      return;
    }
    if (isCloud && !creds.api_key) {
      showMessage('Provider has no API key configured. Edit it in "Your Providers".', 'error');
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
          api_url: creds.api_url,
          api_key: creds.api_key,
          api_type: currentEngine,
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
    if (!currentExtractionEngine) {
      showMessage('Please select a provider first', 'error');
      return;
    }
    const creds = getProviderCredentials(currentExtractionEngine);
    const isCloud = isCloudProvider(currentExtractionEngine);
    if (!isCloud && !creds.api_url) {
      showMessage('Provider has no API URL configured. Edit it in "Your Providers".', 'error');
      return;
    }
    if (isCloud && !creds.api_key) {
      showMessage('Provider has no API key configured. Edit it in "Your Providers".', 'error');
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
          url: creds.api_url,
          api_key: creds.api_key,
          api_type: currentExtractionEngine,
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

  // --- Provider Registry helpers ---

  // Resolve credentials from the unified provider registry
  const getProviderCredentials = (providerId: string) => {
    const p = configuredProviders[providerId];
    return { api_key: p?.api_key || '', api_url: p?.api_url || '' };
  };

  // Get list of configured provider IDs
  const configuredProviderIds = Object.keys(configuredProviders);

  // Add a new provider to the registry
  const addProvider = (providerId: string, apiKey: string, apiUrl: string) => {
    setConfiguredProviders({
      ...configuredProviders,
      [providerId]: { api_key: apiKey, api_url: apiUrl },
    });
  };

  // Remove a provider from the registry (blocked if assigned to any active role)
  const removeProvider = (providerId: string) => {
    if (providerId === 'local') return;
    if (currentEngine === providerId || currentExtractionEngine === providerId || embeddingSettings.provider === providerId) {
      showMessage('Cannot remove a provider that is assigned to an active role', 'error');
      return;
    }
    const updated = { ...configuredProviders };
    delete updated[providerId];
    setConfiguredProviders(updated);
  };

  // Update credentials for an existing provider
  const updateProviderCredentials = (providerId: string, apiKey: string, apiUrl: string) => {
    setConfiguredProviders({
      ...configuredProviders,
      [providerId]: { ...configuredProviders[providerId], api_key: apiKey, api_url: apiUrl },
    });
  };

  // State for inline provider add form
  const [addingProvider, setAddingProvider] = useState(false);
  const [newProviderType, setNewProviderType] = useState('');
  const [newProviderKey, setNewProviderKey] = useState('');
  const [newProviderUrl, setNewProviderUrl] = useState('');
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [editProviderKey, setEditProviderKey] = useState('');
  const [editProviderUrl, setEditProviderUrl] = useState('');

  // Legacy compat: findApiKeyForProvider / findApiUrlForProvider now resolve from configuredProviders
  const findApiKeyForProvider = (provider: string): string => {
    return configuredProviders[provider]?.api_key || '';
  };

  const findApiUrlForProvider = (provider: string): string => {
    return configuredProviders[provider]?.api_url || '';
  };

  // Unified provider change handler for all three roles
  const handleProviderChange = (role: 'llm' | 'extraction' | 'embedding', newProvider: string) => {
    const oldProvider = role === 'llm' ? currentEngine
      : role === 'extraction' ? currentExtractionEngine
      : embeddingSettings.provider;

    // Save current role params back to old provider in configuredProviders
    if (oldProvider && configuredProviders[oldProvider]) {
      const updated = { ...configuredProviders };
      if (role === 'llm') {
        updated[oldProvider] = {
          ...updated[oldProvider],
          llm: {
            model_name: llmSettings.model_name,
            temperature: llmSettings.temperature,
            top_p: llmSettings.top_p,
            top_k: llmSettings.top_k,
            repetition_penalty: llmSettings.repetition_penalty,
            max_tokens: llmSettings.max_tokens,
            completion_mode: llmSettings.completion_mode,
            reasoning_effort: llmSettings.reasoning_effort,
            thinking_model_type: llmSettings.thinking_model_type,
            thinking_enabled_generation: llmSettings.thinking_enabled_generation,
            text_completion_template: llmSettings.text_completion_template,
            text_completion_preset: llmSettings.text_completion_preset,
            sampler_settings: samplerSettings,
          }
        };
      } else if (role === 'extraction') {
        updated[oldProvider] = {
          ...updated[oldProvider],
          extraction: {
            model_name: extractionModelSettings.model_name,
            temperature: extractionModelSettings.temperature,
            max_tokens: extractionModelSettings.max_tokens,
            top_p: extractionModelSettings.top_p,
            repetition_penalty: extractionModelSettings.repetition_penalty,
            min_p: extractionModelSettings.min_p,
            thinking_disable_method: extractionModelSettings.thinking_disable_method,
            thinking_disable_custom: extractionModelSettings.thinking_disable_custom,
            thinking_enabled_extractions: extractionModelSettings.thinking_enabled_extractions,
            thinking_enabled_memory: extractionModelSettings.thinking_enabled_memory,
          }
        };
      } else {
        updated[oldProvider] = {
          ...updated[oldProvider],
          embedding: {
            model_name: embeddingSettings.model_name,
            dimensions: embeddingSettings.dimensions,
          }
        };
      }
      setConfiguredProviders(updated);
    }

    // Resolve credentials for new provider
    const creds = getProviderCredentials(newProvider);

    // Load role params from new provider (or defaults)
    if (role === 'llm') {
      const saved = configuredProviders[newProvider]?.llm;
      if (saved) {
        setLlmSettings({
          ...llmSettings,
          ...saved,
          completion_mode: (saved.completion_mode === 'text' ? 'text' : 'chat') as 'chat' | 'text',
          api_url: creds.api_url,
          api_key: creds.api_key,
          api_type: newProvider,
        });
        if (saved.sampler_settings) {
          setSamplerSettings({ ...DEFAULT_SAMPLER_SETTINGS, ...saved.sampler_settings });
        }
      } else {
        setLlmSettings({
          temperature: 0.7, top_p: 0.9, top_k: 40,
          repetition_penalty: 1.1, max_tokens: 2048,
          api_url: creds.api_url, api_key: creds.api_key,
          api_type: newProvider, model_name: '',
          completion_mode: 'chat', text_completion_template: '',
          text_completion_preset: 'llama3', reasoning_effort: null,
          show_thinking_content: true,
        });
      }
      setCurrentEngine(newProvider);
      setAvailableModels([]);
    } else if (role === 'extraction') {
      const saved = configuredProviders[newProvider]?.extraction;
      if (saved) {
        setExtractionModelSettings({
          ...extractionModelSettings,
          ...saved,
          thinking_disable_method: (saved.thinking_disable_method || 'none') as ExtractionModelSettings['thinking_disable_method'],
          url: creds.api_url,
          api_key: creds.api_key,
          api_type: newProvider,
        });
      } else {
        setExtractionModelSettings({
          ...extractionModelSettings,
          url: creds.api_url,
          api_key: creds.api_key,
          model_name: '',
          api_type: newProvider,
        });
      }
      setCurrentExtractionEngine(newProvider);
      setAvailableExtractionModels([]);
    } else {
      const saved = configuredProviders[newProvider]?.embedding;
      setEmbeddingSettings({
        ...embeddingSettings,
        provider: newProvider,
        api_url: creds.api_url,
        api_key: creds.api_key,
        model_name: saved?.model_name || embeddingSettings.model_name,
        dimensions: saved?.dimensions || embeddingSettings.dimensions,
      });
    }

    // Also save to legacy engineSettings for backward compat
    if (role === 'llm') {
      if (oldProvider && oldProvider !== '') {
        setEngineSettings({ ...engineSettings, [oldProvider]: { ...llmSettings } });
      }
    } else if (role === 'extraction') {
      if (oldProvider && oldProvider !== '') {
        setExtractionEngineSettings({ ...extractionEngineSettings, [oldProvider]: { ...extractionModelSettings } });
      }
    }
  };

  // Legacy wrappers for existing code that calls handleEngineChange/handleExtractionEngineChange
  const handleEngineChange = (newEngine: string) => handleProviderChange('llm', newEngine);
  const handleExtractionEngineChange = (newEngine: string) => handleProviderChange('extraction', newEngine);

  const testConnection = async () => {
    const creds = getProviderCredentials(currentEngine);
    setTestingConnection(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/test-api-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          api_url: creds.api_url,
          api_key: creds.api_key,
          api_type: currentEngine,
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
    const creds = getProviderCredentials(currentExtractionEngine);
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
          url: creds.api_url,
          api_key: creds.api_key,
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

  // Providers available for adding (not yet configured)
  const availableToAdd = providers.filter(p => !configuredProviderIds.includes(p.id));

  // Test & add a new provider
  const handleTestAndAdd = async () => {
    if (!newProviderType) return;
    const providerInfo = providers.find(p => p.id === newProviderType);
    if (!providerInfo) return;

    // For cloud providers, test the API key; for local, test the URL
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/test-api-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          api_url: newProviderUrl,
          api_key: newProviderKey,
          api_type: newProviderType,
        }),
      });
      const result = await response.json();
      if (result.success) {
        addProvider(newProviderType, newProviderKey, newProviderUrl);
        setAddingProvider(false);
        setNewProviderType('');
        setNewProviderKey('');
        setNewProviderUrl('');
        showMessage(`Added ${providerInfo.label}`, 'success');
      } else {
        showMessage(result.message || 'Connection test failed', 'error');
      }
    } catch (error) {
      showMessage(`Connection error: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error');
    }
  };

  // Skip test and just add (for users who want to configure later)
  const handleAddWithoutTest = () => {
    if (!newProviderType) return;
    const providerInfo = providers.find(p => p.id === newProviderType);
    if (!providerInfo) return;
    addProvider(newProviderType, newProviderKey, newProviderUrl);
    setAddingProvider(false);
    setNewProviderType('');
    setNewProviderKey('');
    setNewProviderUrl('');
    showMessage(`Added ${providerInfo.label}`, 'success');
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">LLM Settings</h3>
        <p className="text-sm text-gray-400 mb-4">
          Configure your language model providers and generation parameters
        </p>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* SECTION 1: YOUR PROVIDERS */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="mb-6 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-md font-semibold text-white">Your Providers</h4>
            {!addingProvider && (
              <button
                onClick={() => setAddingProvider(true)}
                className="px-3 py-1.5 text-sm theme-btn-primary rounded-md font-medium"
              >
                + Add Provider
              </button>
            )}
          </div>
          <p className="text-xs text-gray-400 mb-3">
            Configure providers once here. Each role (Main LLM, Extraction, Embedding) picks from your configured providers.
          </p>

          {/* Provider list */}
          {configuredProviderIds.length === 0 && !addingProvider && (
            <div className="text-sm text-gray-500 italic py-3">No providers configured yet. Click "Add Provider" to get started.</div>
          )}
          <div className="space-y-2">
            {configuredProviderIds.map(pid => {
              const providerInfo = providers.find(p => p.id === pid) || embeddingProviders.find(p => p.id === pid);
              const label = providerInfo?.label || pid;
              const category = providerInfo?.category || (pid === 'local' ? 'local' : 'unknown');
              const creds = configuredProviders[pid];
              const isEditing = editingProvider === pid;
              const isAssigned = currentEngine === pid || currentExtractionEngine === pid || embeddingSettings.provider === pid;
              const roles: string[] = [];
              if (currentEngine === pid) roles.push('LLM');
              if (currentExtractionEngine === pid) roles.push('Extraction');
              if (embeddingSettings.provider === pid) roles.push('Embedding');

              return (
                <div key={pid} className="flex items-center gap-3 p-2.5 bg-gray-700/50 rounded-lg">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{label}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${category === 'cloud' ? 'bg-blue-900/50 text-blue-300' : 'bg-green-900/50 text-green-300'}`}>
                        {category}
                      </span>
                      {roles.map(r => (
                        <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/50 text-purple-300">{r}</span>
                      ))}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {creds?.api_key ? `Key: ...${creds.api_key.slice(-4)}` : ''}
                      {creds?.api_key && creds?.api_url ? ' | ' : ''}
                      {creds?.api_url ? `URL: ${creds.api_url}` : ''}
                      {!creds?.api_key && !creds?.api_url && pid !== 'local' ? 'No credentials' : ''}
                      {pid === 'local' && !creds?.api_key && !creds?.api_url ? 'Local models' : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {pid !== 'local' && (
                      <>
                        <button
                          onClick={() => {
                            if (isEditing) {
                              updateProviderCredentials(pid, editProviderKey, editProviderUrl);
                              setEditingProvider(null);
                            } else {
                              setEditingProvider(pid);
                              setEditProviderKey(creds?.api_key || '');
                              setEditProviderUrl(creds?.api_url || '');
                            }
                          }}
                          className="px-2 py-1 text-xs text-gray-300 hover:text-white hover:bg-gray-600 rounded"
                        >
                          {isEditing ? 'Save' : 'Edit'}
                        </button>
                        <button
                          onClick={() => {
                            if (isEditing) {
                              setEditingProvider(null);
                            } else {
                              removeProvider(pid);
                            }
                          }}
                          disabled={!isEditing && isAssigned}
                          className="px-2 py-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-900/30 rounded disabled:opacity-30 disabled:cursor-not-allowed"
                          title={isAssigned ? 'Cannot remove — assigned to a role' : 'Remove provider'}
                        >
                          {isEditing ? 'Cancel' : 'Remove'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
            {/* Inline edit form */}
            {editingProvider && editingProvider !== 'local' && (
              <div className="p-3 bg-gray-700/30 rounded-lg border border-gray-600 space-y-2 mt-1">
                {(() => {
                  const providerInfo = providers.find(p => p.id === editingProvider);
                  const isCloud = providerInfo?.category === 'cloud';
                  return (
                    <>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          API Key{!isCloud ? ' (optional)' : ''}
                        </label>
                        <input
                          type="password"
                          value={editProviderKey}
                          onChange={(e) => setEditProviderKey(e.target.value)}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-2.5 py-1.5 text-sm text-white"
                          placeholder="sk-..."
                        />
                      </div>
                      {!isCloud && (
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">API URL</label>
                          <input
                            type="text"
                            value={editProviderUrl}
                            onChange={(e) => setEditProviderUrl(e.target.value)}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-2.5 py-1.5 text-sm text-white"
                            placeholder="http://localhost:1234"
                          />
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </div>

          {/* Add provider form */}
          {addingProvider && (
            <div className="mt-3 p-3 bg-gray-700/30 rounded-lg border border-gray-600 space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Provider</label>
                <select
                  value={newProviderType}
                  onChange={(e) => {
                    setNewProviderType(e.target.value);
                    setNewProviderKey('');
                    setNewProviderUrl('');
                  }}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-2.5 py-1.5 text-sm text-white"
                >
                  <option value="">Select provider...</option>
                  {(() => {
                    const cloudAvail = availableToAdd.filter(p => p.category === 'cloud');
                    const localAvail = availableToAdd.filter(p => p.category === 'local');
                    return (
                      <>
                        {cloudAvail.length > 0 && (
                          <optgroup label="Cloud">
                            {cloudAvail.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                          </optgroup>
                        )}
                        {localAvail.length > 0 && (
                          <optgroup label="Local / Self-Hosted">
                            {localAvail.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                          </optgroup>
                        )}
                      </>
                    );
                  })()}
                </select>
              </div>
              {newProviderType && (() => {
                const info = providers.find(p => p.id === newProviderType);
                const isCloud = info?.category === 'cloud';
                return (
                  <>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        API Key{!isCloud ? ' (optional)' : ''}
                      </label>
                      <input
                        type="password"
                        value={newProviderKey}
                        onChange={(e) => setNewProviderKey(e.target.value)}
                        className="w-full bg-gray-700 border border-gray-600 rounded px-2.5 py-1.5 text-sm text-white"
                        placeholder="sk-..."
                      />
                    </div>
                    {!isCloud && (
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">API URL</label>
                        <input
                          type="text"
                          value={newProviderUrl}
                          onChange={(e) => setNewProviderUrl(e.target.value)}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-2.5 py-1.5 text-sm text-white"
                          placeholder="http://localhost:1234"
                        />
                      </div>
                    )}
                  </>
                );
              })()}
              <div className="flex gap-2">
                <button
                  onClick={handleTestAndAdd}
                  disabled={!newProviderType}
                  className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-medium"
                >
                  Test & Add
                </button>
                <button
                  onClick={handleAddWithoutTest}
                  disabled={!newProviderType}
                  className="px-3 py-1.5 text-sm bg-gray-600 hover:bg-gray-500 disabled:opacity-50 text-white rounded font-medium"
                >
                  Add Without Test
                </button>
                <button
                  onClick={() => { setAddingProvider(false); setNewProviderType(''); setNewProviderKey(''); setNewProviderUrl(''); }}
                  className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

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

                {/* Provider selector — only configured providers */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Provider</label>
                  <select
                    value={currentEngine}
                    onChange={(e) => handleEngineChange(e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                  >
                    <option value="">Select Provider...</option>
                    {configuredProviderIds.filter(pid => pid !== 'local').map(pid => {
                      const info = providers.find(p => p.id === pid);
                      return <option key={pid} value={pid}>{info?.label || pid}</option>;
                    })}
                  </select>
                  {currentEngine && !configuredProviderIds.includes(currentEngine) && (
                    <div className="text-xs text-amber-400 mt-1">
                      Provider "{currentEngine}" is not configured. Add it in "Your Providers" above.
                    </div>
                  )}
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
                      disabled={loadingModels || autoLoading || !currentEngine}
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
                    {/* Extraction Provider Selector — configured providers only */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">Provider</label>
                      <select
                        value={currentExtractionEngine}
                        onChange={(e) => handleExtractionEngineChange(e.target.value)}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                      >
                        <option value="">Select Provider...</option>
                        {configuredProviderIds.filter(pid => pid !== 'local').map(pid => {
                          const info = providers.find(p => p.id === pid);
                          return <option key={pid} value={pid}>{info?.label || pid}</option>;
                        })}
                      </select>
                      {currentExtractionEngine && !configuredProviderIds.includes(currentExtractionEngine) && (
                        <div className="text-xs text-amber-400 mt-1">
                          Provider "{currentExtractionEngine}" is not configured. Add it in "Your Providers" above.
                        </div>
                      )}
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
                        <button
                          onClick={fetchExtractionModels}
                          disabled={loadingExtractionModels || autoLoadingExtraction || !currentExtractionEngine}
                          className="px-4 py-2 theme-btn-primary rounded-md font-medium disabled:opacity-50"
                        >
                          {loadingExtractionModels || autoLoadingExtraction ? 'Loading...' : 'Fetch Models'}
                        </button>
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

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* EMBEDDING MODEL SECTION */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <div className="border-t-2 border-gray-600 pt-6 mt-6">
              <h3 className="text-lg font-semibold text-white mb-4">Embedding Model</h3>
              <p className="text-sm text-gray-400 mb-4">
                Configure the model used for semantic search embeddings. Default uses local sentence-transformers (requires CPU/GPU). Switch to a cloud provider to offload embedding computation.
              </p>

              {/* Warning banner for needs_reembed */}
              {(needsReembed || (embeddingTestResult?.success && embeddingTestResult.dimensions && embeddingTestResult.dimensions !== embeddingSettings.dimensions)) && reembedProgress?.status !== 'running' && (
                <div className="mb-4 p-3 bg-amber-900/30 border border-amber-600/50 rounded-lg">
                  <p className="text-sm text-amber-300">
                    Embedding dimensions have changed. You need to re-process all embeddings for semantic search to work correctly.
                  </p>
                </div>
              )}

              {/* Re-embed progress */}
              {reembedProgress && reembedProgress.status === 'running' && (
                <div className="mb-4 p-4 bg-blue-900/20 border border-blue-700/30 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-blue-200 font-medium">Re-processing embeddings...</span>
                    <button
                      onClick={cancelReembed}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Cancel
                    </button>
                  </div>
                  <p className="text-xs text-gray-400 mb-2">
                    {reembedProgress.current_table}: {reembedProgress.processed}/{reembedProgress.total}
                    {reembedProgress.errors > 0 && ` (${reembedProgress.errors} errors)`}
                  </p>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all"
                      style={{ width: `${reembedProgress.total > 0 ? (reembedProgress.processed / reembedProgress.total) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Completed/error status */}
              {reembedProgress && (reembedProgress.status === 'completed' || reembedProgress.status === 'error' || reembedProgress.status === 'cancelled') && (
                <div className={`mb-4 p-3 rounded-lg ${
                  reembedProgress.status === 'completed' ? 'bg-green-900/20 border border-green-700/30' :
                  'bg-red-900/20 border border-red-700/30'
                }`}>
                  <p className={`text-sm ${reembedProgress.status === 'completed' ? 'text-green-300' : 'text-red-300'}`}>
                    {reembedProgress.message}
                  </p>
                </div>
              )}

              <div className="space-y-4">
                {/* Provider Selection — configured providers + local */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Provider</label>
                  <select
                    value={embeddingSettings.provider}
                    onChange={(e) => handleProviderChange('embedding', e.target.value)}
                    disabled={pollingReembed}
                    className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50"
                  >
                    {/* Always include local */}
                    <option value="local">Local (sentence-transformers)</option>
                    {configuredProviderIds.filter(pid => pid !== 'local').map(pid => {
                      const info = providers.find(p => p.id === pid) || embeddingProviders.find(p => p.id === pid);
                      return <option key={pid} value={pid}>{info?.label || pid}</option>;
                    })}
                  </select>
                  {embeddingSettings.provider !== 'local' && !configuredProviderIds.includes(embeddingSettings.provider) && (
                    <div className="text-xs text-amber-400 mt-1">
                      Provider "{embeddingSettings.provider}" is not configured. Add it in "Your Providers" above.
                    </div>
                  )}
                </div>

                {/* Model Name */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Model Name</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={embeddingSettings.model_name}
                      onChange={(e) => setEmbeddingSettings({ ...embeddingSettings, model_name: e.target.value })}
                      disabled={pollingReembed}
                      className="flex-1 bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50"
                      placeholder={embeddingSettings.provider === 'local' ? 'sentence-transformers/all-mpnet-base-v2' : 'text-embedding-3-small'}
                    />
                    {embeddingSettings.provider !== 'local' && (
                      <button
                        onClick={fetchEmbeddingModels}
                        disabled={loadingEmbeddingModels || pollingReembed}
                        className="px-3 py-2 bg-gray-600 hover:bg-gray-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded text-sm whitespace-nowrap"
                      >
                        {loadingEmbeddingModels ? '...' : 'Fetch Models'}
                      </button>
                    )}
                  </div>
                  {embeddingModels.length > 0 && (
                    <div className="mt-2">
                      <select
                        value={embeddingSettings.model_name}
                        onChange={(e) => setEmbeddingSettings({ ...embeddingSettings, model_name: e.target.value })}
                        disabled={pollingReembed}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white disabled:opacity-50"
                      >
                        <option value="">Select a model...</option>
                        {embeddingModels.map(m => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                      <div className="text-xs text-gray-400 mt-1">
                        {embeddingModels.length} models available
                      </div>
                    </div>
                  )}
                </div>

                {/* Dimensions display */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    Dimensions: {embeddingSettings.dimensions}
                  </label>
                  <div className="text-xs text-gray-400">
                    Detected after testing connection. All embedding tables use this dimension.
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-3 flex-wrap">
                  <button
                    onClick={testEmbeddingConnection}
                    disabled={testingEmbedding || pollingReembed || !embeddingSettings.model_name}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-medium"
                  >
                    {testingEmbedding ? 'Testing...' : 'Test Connection'}
                  </button>

                  <button
                    onClick={startReembed}
                    disabled={pollingReembed}
                    className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-medium"
                  >
                    Re-process All Embeddings
                  </button>

                  {embeddingTestResult && (
                    <span className={`text-sm ${embeddingTestResult.success ? 'text-green-400' : 'text-red-400'}`}>
                      {embeddingTestResult.success ? '✓' : '✗'} {embeddingTestResult.message}
                    </span>
                  )}
                </div>
              </div>
            </div>

          </>
        )}

        {/* Advanced Samplers Sub-tab */}
        {llmSubTab === 'samplers' && (
          <SamplersSettings
            samplerSettings={samplerSettings}
            setSamplerSettings={setSamplerSettings}
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
}

function SamplersSettings({ samplerSettings, setSamplerSettings }: SamplersSettingsProps) {
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
