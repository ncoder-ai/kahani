'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { X, Settings as SettingsIcon, Check, AlertCircle } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';
import { applyTheme } from '@/lib/themes';
import { useAuthStore } from '@/store';
import { useConfig } from '@/contexts/ConfigContext';
import { UIPreferences, GenerationPreferences, SamplerSettings, DEFAULT_SAMPLER_SETTINGS } from '@/types/settings';

// Import tab components
import {
  InterfaceSettingsTab,
  WritingSettingsTab,
  LLMSettingsTab,
  ContextSettingsTab,
  VoiceSettingsTab,
  ImageGenSettingsTab,
  LLMSettings,
  ContextSettings,
  ExtractionModelSettings,
  EmbeddingModelSettings,
  ImageGenSettings,
} from './settings';
import type { ConfiguredProviders } from './settings/types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { token } = useAuthStore();
  const config = useConfig();
  const [activeTab, setActiveTab] = useState<'interface' | 'writing' | 'llm' | 'context' | 'voice' | 'image'>('interface');

  // UI Settings
  const [uiSettings, setUiSettings] = useState<UIPreferences>({
    color_theme: 'pure-dark',
    font_size: 'medium',
    show_token_info: false,
    show_context_info: false,
    notifications: true,
    scene_display_format: 'default',
    show_scene_titles: true,
    scene_edit_mode: 'textarea',
    auto_open_last_story: false,
  });

  // Provider Registry — single source of truth for credentials + per-role params
  const [configuredProviders, setConfiguredProviders] = useState<ConfiguredProviders>({});

  // LLM Settings - Engine-specific storage (legacy, kept for backward compat)
  const [engineSettings, setEngineSettings] = useState<Record<string, LLMSettings>>({});
  const [currentEngine, setCurrentEngine] = useState<string>('');
  const [samplerSettings, setSamplerSettings] = useState<SamplerSettings>(DEFAULT_SAMPLER_SETTINGS);
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
    reasoning_effort: null,
    show_thinking_content: true,
  });

  // Context Settings
  const [contextSettings, setContextSettings] = useState<ContextSettings>({
    max_tokens: 8000,
    keep_recent_scenes: 2,  // Number of complete batches (now batch-aligned for cache stability)
    summary_threshold: 10,
    summary_threshold_tokens: 4000,
    enable_summarization: true,
    character_extraction_threshold: 5,
    scene_batch_size: 5,  // Scenes per batch (smaller = more stable cache)
    enable_semantic_memory: false,
    context_strategy: 'linear',
    semantic_search_top_k: 5,
    semantic_scenes_in_context: 3,
    semantic_context_weight: 0.7,
    character_moments_in_context: 2,
    auto_extract_character_moments: false,
    auto_extract_plot_events: false,
    extraction_confidence_threshold: 0.8,
    plot_event_extraction_threshold: 5,
    fill_remaining_context: true,
    // Contradiction settings
    enable_working_memory: true,
    enable_contradiction_detection: true,
    contradiction_severity_threshold: 'medium',
    enable_relationship_graph: true,
    enable_contradiction_injection: true,
    enable_inline_contradiction_check: false,
    auto_regenerate_on_contradiction: false,
  });

  // Extraction Model Settings
  const [extractionModelSettings, setExtractionModelSettings] = useState<ExtractionModelSettings>({
    enabled: false,
    url: 'http://localhost:1234/v1',
    api_key: '',
    model_name: 'qwen2.5-3b-instruct',
    api_type: 'openai-compatible',
    temperature: 0.3,
    max_tokens: 1000,
    fallback_to_main: true,
    use_context_aware_extraction: false,
    top_p: 1.0,
    repetition_penalty: 1.0,
    min_p: 0.0,
    thinking_disable_method: 'none',
    thinking_disable_custom: '',
    thinking_enabled_extractions: false,
    thinking_enabled_memory: true,
  });

  // Extraction Engine-Specific Settings (mirrors main LLM engine pattern)
  const [extractionEngineSettings, setExtractionEngineSettings] = useState<Record<string, ExtractionModelSettings>>({});
  const [currentExtractionEngine, setCurrentExtractionEngine] = useState<string>('');

  // Embedding Model Settings
  const [embeddingSettings, setEmbeddingSettings] = useState<EmbeddingModelSettings>({
    provider: 'local',
    api_url: '',
    api_key: '',
    model_name: 'sentence-transformers/all-mpnet-base-v2',
    dimensions: 768,
    needs_reembed: false,
  });

  // Generation Preferences
  const [generationPrefs, setGenerationPrefs] = useState<GenerationPreferences>({
    default_genre: 'fantasy',
    default_tone: 'balanced',
    scene_length: 'medium',
    auto_choices: true,
    choices_count: 4,
    enable_streaming: true,
    alert_on_high_context: true,
    use_extraction_llm_for_summary: false,
    separate_choice_generation: false,
    enable_chapter_plot_tracking: true,
    default_plot_check_mode: '1' as const,
  });

  // Image Generation Settings
  const [imageGenSettings, setImageGenSettings] = useState<ImageGenSettings>({
    enabled: false,
    comfyui_server_url: '',
    comfyui_api_key: '',
    comfyui_checkpoint: '',
    comfyui_model_type: 'sdxl',
    width: 1024,
    height: 1024,
    steps: 4,
    cfg_scale: 1.5,
    default_style: 'illustrated',
    use_extraction_llm_for_prompts: false,
  });

  // Messages
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  const showMessage = useCallback((msg: string, type: 'success' | 'error') => {
    setMessage(msg);
    setMessageType(type);
    setTimeout(() => setMessage(''), 3000);
  }, []);

  // --- Auto-save ---
  const loadedRef = useRef(false);        // true once initial load completes
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  // Build the full save payload (same shape as the old saveEngineSettings)
  const buildSavePayload = useCallback(() => {
    const updatedEngineSettings = { ...engineSettings };
    if (currentEngine && currentEngine.trim() !== '') {
      updatedEngineSettings[currentEngine] = { ...llmSettings };
    }
    const updatedExtractionEngineSettings = { ...extractionEngineSettings };
    if (currentExtractionEngine && currentExtractionEngine.trim() !== '') {
      updatedExtractionEngineSettings[currentExtractionEngine] = { ...extractionModelSettings };
    }
    return {
      configured_providers: { configured_providers: configuredProviders },
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
      },
      extraction_model_settings: {
        ...extractionModelSettings,
        api_type: extractionModelSettings.api_type || 'openai-compatible',
      },
      extraction_engine_settings: {
        extraction_engine_settings: updatedExtractionEngineSettings,
        current_extraction_engine: currentExtractionEngine || '',
      },
      sampler_settings: samplerSettings,
      context_settings: contextSettings,
      generation_preferences: generationPrefs,
      embedding_model_settings: {
        provider: embeddingSettings.provider,
        api_url: embeddingSettings.api_url,
        api_key: embeddingSettings.api_key,
        model_name: embeddingSettings.model_name,
        dimensions: embeddingSettings.dimensions,
      },
      ui_preferences: uiSettings,
      image_generation_settings: imageGenSettings,
    };
  }, [configuredProviders, engineSettings, currentEngine, llmSettings,
      extractionEngineSettings, currentExtractionEngine, extractionModelSettings,
      samplerSettings, contextSettings, generationPrefs, embeddingSettings,
      uiSettings, imageGenSettings]);

  const doAutoSave = useCallback(async () => {
    if (!token || !loadedRef.current) return;
    setSaveStatus('saving');
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(buildSavePayload()),
      });
      if (response.ok) {
        setSaveStatus('saved');
        window.dispatchEvent(new CustomEvent('kahaniSettingsChanged'));
        setTimeout(() => setSaveStatus('idle'), 1500);
      } else {
        setSaveStatus('error');
        setTimeout(() => setSaveStatus('idle'), 3000);
      }
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  }, [token, buildSavePayload]);

  // Debounced auto-save: fire 800ms after the last state change
  useEffect(() => {
    if (!loadedRef.current) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => doAutoSave(), 800);
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); };
  }, [configuredProviders, llmSettings, samplerSettings, extractionModelSettings,
      currentEngine, currentExtractionEngine, embeddingSettings,
      contextSettings, generationPrefs, uiSettings, imageGenSettings, doAutoSave]);

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
      loadedRef.current = false;
      loadAllSettings();
    }
  }, [isOpen]);

  const loadAllSettings = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        const settings = data.settings;

        // Load configured providers
        if (settings?.configured_providers) {
          setConfiguredProviders(settings.configured_providers);
        }

        // Load UI preferences
        if (settings?.ui_preferences) {
          setUiSettings(prev => ({
            ...prev,
            ...settings.ui_preferences,
          }));
          // Apply theme
          applyTheme(settings.ui_preferences.color_theme || 'pure-dark');
        }

        // Load engine-specific LLM settings
        if (settings?.llm_settings) {
          if (settings.engine_settings && Object.keys(settings.engine_settings).length > 0) {
            setEngineSettings(settings.engine_settings);
            if (settings.current_engine && settings.current_engine.trim() !== '') {
              setCurrentEngine(settings.current_engine);
              const engineSettingsVal = settings.engine_settings[settings.current_engine];
              if (engineSettingsVal) {
                setLlmSettings(engineSettingsVal);
              } else {
                setLlmSettings(settings.llm_settings);
              }
            } else if (settings.llm_settings.api_type && settings.llm_settings.api_type.trim() !== '') {
              setCurrentEngine(settings.llm_settings.api_type);
              setLlmSettings(settings.llm_settings);
            } else {
              setLlmSettings(settings.llm_settings);
            }
          } else {
            setLlmSettings(prev => ({
              ...prev,
              ...settings.llm_settings,
            }));
            if (settings.llm_settings.api_type && settings.llm_settings.api_type.trim() !== '') {
              setCurrentEngine(settings.llm_settings.api_type);
            }
          }
        }

        // Load Context settings
        if (settings?.context_settings) {
          setContextSettings(prev => ({
            ...prev,
            ...settings.context_settings,
          }));
        }

        // Load Generation preferences
        if (settings?.generation_preferences) {
          setGenerationPrefs(prev => ({
            ...prev,
            ...settings.generation_preferences,
          }));
        }

        // Load Extraction Model settings
        if (settings?.extraction_model_settings) {
          let defaultExtractionUrl = '';
          try {
            defaultExtractionUrl = await config.getExtractionDefaultUrl();
          } catch (error) {
            console.error('Failed to load extraction default URL from config:', error);
          }

          // Load extraction engine settings (per-engine persistence)
          if (settings.extraction_engine_settings && Object.keys(settings.extraction_engine_settings).length > 0) {
            setExtractionEngineSettings(settings.extraction_engine_settings);
            if (settings.current_extraction_engine && settings.current_extraction_engine.trim() !== '') {
              setCurrentExtractionEngine(settings.current_extraction_engine);
              const savedEngineSettings = settings.extraction_engine_settings[settings.current_extraction_engine];
              if (savedEngineSettings) {
                setExtractionModelSettings(prev => ({
                  ...prev,
                  ...savedEngineSettings,
                  url: savedEngineSettings.url || defaultExtractionUrl,
                }));
              } else {
                setExtractionModelSettings(prev => ({
                  ...prev,
                  ...settings.extraction_model_settings,
                  url: settings.extraction_model_settings.url || defaultExtractionUrl,
                }));
              }
            } else {
              // No current engine set, use flat settings
              const apiType = settings.extraction_model_settings.api_type || 'openai-compatible';
              setCurrentExtractionEngine(apiType);
              setExtractionModelSettings(prev => ({
                ...prev,
                ...settings.extraction_model_settings,
                url: settings.extraction_model_settings.url || defaultExtractionUrl,
              }));
            }
          } else {
            // No engine settings, use flat settings (backward compat)
            const apiType = settings.extraction_model_settings.api_type || 'openai-compatible';
            setCurrentExtractionEngine(apiType);
            setExtractionModelSettings(prev => ({
              ...prev,
              ...settings.extraction_model_settings,
              url: settings.extraction_model_settings.url || defaultExtractionUrl,
            }));
          }
        }

        // Load Embedding Model settings
        if (settings?.embedding_model_settings) {
          setEmbeddingSettings(prev => ({
            ...prev,
            ...settings.embedding_model_settings,
          }));
        }

        // Load sampler settings
        if (settings?.sampler_settings) {
          setSamplerSettings({
            ...DEFAULT_SAMPLER_SETTINGS,
            ...settings.sampler_settings,
          });
        }

        // Load Image Generation settings
        if (settings?.image_generation_settings) {
          setImageGenSettings(prev => ({
            ...prev,
            ...settings.image_generation_settings,
          }));
        }
      }

      // Mark loaded AFTER a tick so React batches all the setState calls above
      // before the auto-save effect sees them
      setTimeout(() => { loadedRef.current = true; }, 100);
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  // Legacy save function — kept as a no-op in case child components still reference it.
  // Auto-save handles everything now.
  const saveEngineSettings = async () => { doAutoSave(); };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-2 sm:p-4">
      <div className="theme-card rounded-lg shadow-xl max-w-4xl w-full max-h-[95vh] sm:max-h-[90vh] overflow-hidden border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-3 sm:p-6 border-b border-gray-700 theme-banner">
          <div className="flex items-center gap-2 sm:gap-3">
            <SettingsIcon className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
            <h2 className="text-lg sm:text-xl font-bold text-white">Settings</h2>
            {saveStatus === 'saving' && (
              <span className="text-xs text-gray-400 ml-2">Saving...</span>
            )}
            {saveStatus === 'saved' && (
              <span className="text-xs text-green-400 ml-2 flex items-center gap-1">
                <Check className="w-3 h-3" /> Saved
              </span>
            )}
            {saveStatus === 'error' && (
              <span className="text-xs text-red-400 ml-2 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" /> Save failed
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-300 hover:text-white active:text-gray-100 transition-colors p-1"
          >
            <X className="w-5 h-5 sm:w-6 sm:h-6" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-gray-700 bg-gray-800/50 overflow-x-auto">
          {[
            { id: 'interface', name: 'Interface' },
            { id: 'writing', name: 'Writing' },
            { id: 'llm', name: 'LLM' },
            { id: 'context', name: 'Context' },
            { id: 'voice', name: 'Voice' },
            { id: 'image', name: 'Images' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex-shrink-0 py-2.5 sm:py-3 px-3 sm:px-4 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'theme-btn-primary border-b-2 theme-border-accent'
                  : 'text-gray-300 hover:text-white active:bg-white/10 hover:bg-white/5'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-3 sm:p-6 overflow-y-auto max-h-[calc(95vh-140px)] sm:max-h-[calc(90vh-180px)]">
          {/* Messages */}
          {message && (
            <div className={`mb-3 sm:mb-4 p-3 sm:p-4 rounded-lg flex items-start gap-2 sm:gap-3 ${
              messageType === 'success'
                ? 'bg-green-500/10 border border-green-500/50'
                : 'bg-red-500/10 border border-red-500/50'
            }`}>
              {messageType === 'success' ? (
                <Check className="w-4 h-4 sm:w-5 sm:h-5 text-green-400 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 text-red-400 flex-shrink-0 mt-0.5" />
              )}
              <p className={`text-xs sm:text-sm ${messageType === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                {message}
              </p>
            </div>
          )}

          {/* Interface Tab */}
          {activeTab === 'interface' && (
            <InterfaceSettingsTab
              token={token || ''}
              showMessage={showMessage}
              uiSettings={uiSettings}
              setUiSettings={setUiSettings}
            />
          )}

          {/* Writing Styles Tab */}
          {activeTab === 'writing' && (
            <WritingSettingsTab
              token={token || ''}
              showMessage={showMessage}
            />
          )}

          {/* LLM Settings Tab */}
          {activeTab === 'llm' && (
            <LLMSettingsTab
              token={token || ''}
              showMessage={showMessage}
              llmSettings={llmSettings}
              setLlmSettings={setLlmSettings}
              samplerSettings={samplerSettings}
              setSamplerSettings={setSamplerSettings}
              extractionModelSettings={extractionModelSettings}
              setExtractionModelSettings={setExtractionModelSettings}
              engineSettings={engineSettings}
              setEngineSettings={setEngineSettings}
              currentEngine={currentEngine}
              setCurrentEngine={setCurrentEngine}
              extractionEngineSettings={extractionEngineSettings}
              setExtractionEngineSettings={setExtractionEngineSettings}
              currentExtractionEngine={currentExtractionEngine}
              setCurrentExtractionEngine={setCurrentExtractionEngine}
              embeddingSettings={embeddingSettings}
              setEmbeddingSettings={setEmbeddingSettings}
              configuredProviders={configuredProviders}
              setConfiguredProviders={setConfiguredProviders}
            />
          )}

          {/* Context Settings Tab */}
          {activeTab === 'context' && (
            <ContextSettingsTab
              token={token || ''}
              showMessage={showMessage}
              contextSettings={contextSettings}
              setContextSettings={setContextSettings}
              generationPrefs={generationPrefs}
              setGenerationPrefs={setGenerationPrefs}
              extractionModelSettings={extractionModelSettings}
            />
          )}

          {/* Voice Settings Tab */}
          {activeTab === 'voice' && (
            <VoiceSettingsTab
              token={token || ''}
              showMessage={showMessage}
            />
          )}

          {/* Image Generation Tab */}
          {activeTab === 'image' && (
            <ImageGenSettingsTab
              token={token || ''}
              showMessage={showMessage}
              imageGenSettings={imageGenSettings}
              setImageGenSettings={setImageGenSettings}
            />
          )}
        </div>
      </div>
    </div>
  );
}
