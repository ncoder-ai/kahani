'use client';

import { useState, useEffect, useCallback } from 'react';
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
  LLMSettings,
  ContextSettings,
  ExtractionModelSettings,
} from './settings';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { token } = useAuthStore();
  const config = useConfig();
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
    scene_edit_mode: 'textarea',
    auto_open_last_story: false,
  });

  // LLM Settings - Engine-specific storage
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
    keep_recent_scenes: 5,
    summary_threshold: 10,
    summary_threshold_tokens: 4000,
    enable_summarization: true,
    character_extraction_threshold: 5,
    scene_batch_size: 10,
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
  });

  // Extraction Model Settings
  const [extractionModelSettings, setExtractionModelSettings] = useState<ExtractionModelSettings>({
    enabled: false,
    url: 'http://localhost:1234/v1',
    api_key: '',
    model_name: 'qwen2.5-3b-instruct',
    temperature: 0.3,
    max_tokens: 1000,
    fallback_to_main: true,
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
  });

  // Messages
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  const showMessage = useCallback((msg: string, type: 'success' | 'error') => {
    setMessage(msg);
    setMessageType(type);
    setTimeout(() => setMessage(''), 3000);
  }, []);

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
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

        // Load UI preferences
        if (settings?.ui_preferences) {
          const newUiSettings = {
            color_theme: settings.ui_preferences.color_theme || 'pure-dark',
            font_size: settings.ui_preferences.font_size || 'medium',
            show_token_info: settings.ui_preferences.show_token_info || false,
            show_context_info: settings.ui_preferences.show_context_info || false,
            notifications: settings.ui_preferences.notifications !== false,
            scene_display_format: settings.ui_preferences.scene_display_format || 'default',
            show_scene_titles: settings.ui_preferences.show_scene_titles !== false,
            scene_edit_mode: settings.ui_preferences.scene_edit_mode || 'textarea',
            auto_open_last_story: settings.ui_preferences.auto_open_last_story || false,
          };
          setUiSettings(newUiSettings);
          // Apply theme
          applyTheme(newUiSettings.color_theme);
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
            setLlmSettings({
              temperature: settings.llm_settings.temperature ?? 0.7,
              top_p: settings.llm_settings.top_p ?? 0.9,
              top_k: settings.llm_settings.top_k ?? 40,
              repetition_penalty: settings.llm_settings.repetition_penalty ?? 1.1,
              max_tokens: settings.llm_settings.max_tokens ?? 2048,
              timeout_total: settings.llm_settings.timeout_total,
              api_url: settings.llm_settings.api_url || '',
              api_key: settings.llm_settings.api_key || '',
              api_type: settings.llm_settings.api_type || '',
              model_name: settings.llm_settings.model_name || '',
              completion_mode: settings.llm_settings.completion_mode || 'chat',
              text_completion_template: settings.llm_settings.text_completion_template || '',
              text_completion_preset: settings.llm_settings.text_completion_preset || 'llama3',
              reasoning_effort: settings.llm_settings.reasoning_effort || null,
              show_thinking_content: settings.llm_settings.show_thinking_content ?? true,
            });
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
            character_extraction_threshold: settings.context_settings.character_extraction_threshold ?? 5,
            scene_batch_size: settings.context_settings.scene_batch_size ?? 10,
            enable_semantic_memory: settings.context_settings.enable_semantic_memory || false,
            context_strategy: settings.context_settings.context_strategy || 'linear',
            semantic_search_top_k: settings.context_settings.semantic_search_top_k ?? 5,
            semantic_scenes_in_context: settings.context_settings.semantic_scenes_in_context ?? 3,
            semantic_context_weight: settings.context_settings.semantic_context_weight ?? 0.7,
            character_moments_in_context: settings.context_settings.character_moments_in_context ?? 2,
            auto_extract_character_moments: settings.context_settings.auto_extract_character_moments || false,
            auto_extract_plot_events: settings.context_settings.auto_extract_plot_events || false,
            extraction_confidence_threshold: settings.context_settings.extraction_confidence_threshold ?? 0.8,
            plot_event_extraction_threshold: settings.context_settings.plot_event_extraction_threshold ?? 5,
            fill_remaining_context: settings.context_settings.fill_remaining_context !== false,
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
            enable_streaming: settings.generation_preferences.enable_streaming !== false,
            alert_on_high_context: settings.generation_preferences.alert_on_high_context !== false,
            use_extraction_llm_for_summary: settings.generation_preferences.use_extraction_llm_for_summary || false,
            separate_choice_generation: settings.generation_preferences.separate_choice_generation || false,
          });
        }

        // Load Extraction Model settings
        if (settings?.extraction_model_settings) {
          let defaultExtractionUrl = '';
          try {
            defaultExtractionUrl = await config.getExtractionDefaultUrl();
          } catch (error) {
            console.error('Failed to load extraction default URL from config:', error);
          }
          setExtractionModelSettings({
            enabled: settings.extraction_model_settings.enabled ?? false,
            url: settings.extraction_model_settings.url || defaultExtractionUrl,
            api_key: settings.extraction_model_settings.api_key || '',
            model_name: settings.extraction_model_settings.model_name || 'qwen2.5-3b-instruct',
            temperature: settings.extraction_model_settings.temperature ?? 0.3,
            max_tokens: settings.extraction_model_settings.max_tokens ?? 1000,
            fallback_to_main: settings.extraction_model_settings.fallback_to_main !== false,
          });
        }

        // Load sampler settings
        if (settings?.sampler_settings) {
          setSamplerSettings({
            ...DEFAULT_SAMPLER_SETTINGS,
            ...settings.sampler_settings,
          });
        }
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const saveEngineSettings = async () => {
    try {
      const updatedEngineSettings = { ...engineSettings };

      if (currentEngine && currentEngine.trim() !== '') {
        updatedEngineSettings[currentEngine] = { ...llmSettings };
      }

      setEngineSettings(updatedEngineSettings);

      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
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
          },
          extraction_model_settings: extractionModelSettings,
          sampler_settings: samplerSettings,
        }),
      });

      if (response.ok) {
        showMessage('LLM and extraction model settings saved!', 'success');
        window.dispatchEvent(new CustomEvent('kahaniSettingsChanged'));
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to save settings' }));
        showMessage(`Failed to save settings: ${errorData.detail || 'Unknown error'}`, 'error');
      }
    } catch (error) {
      showMessage('Error saving engine settings', 'error');
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
              className={`flex-shrink-0 py-3 px-4 text-sm font-medium transition-colors whitespace-nowrap ${
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
              onSave={saveEngineSettings}
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
        </div>
      </div>
    </div>
  );
}
