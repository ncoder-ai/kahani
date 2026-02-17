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
  ImageGenSettingsTab,
  LLMSettings,
  ContextSettings,
  ExtractionModelSettings,
  ImageGenSettings,
} from './settings';

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
              thinking_model_type: settings.llm_settings.thinking_model_type ?? null,
              thinking_model_custom_pattern: settings.llm_settings.thinking_model_custom_pattern ?? '',
              thinking_enabled_generation: settings.llm_settings.thinking_enabled_generation ?? false,
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
            keep_recent_scenes: settings.context_settings.keep_recent_scenes ?? 2,  // Now = number of batches
            summary_threshold: settings.context_settings.summary_threshold ?? 10,
            summary_threshold_tokens: settings.context_settings.summary_threshold_tokens ?? 4000,
            enable_summarization: settings.context_settings.enable_summarization !== false,
            character_extraction_threshold: settings.context_settings.character_extraction_threshold ?? 5,
            scene_batch_size: settings.context_settings.scene_batch_size ?? 5,
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
            // Contradiction settings
            enable_working_memory: settings.context_settings.enable_working_memory !== false,
            enable_contradiction_detection: settings.context_settings.enable_contradiction_detection !== false,
            contradiction_severity_threshold: settings.context_settings.contradiction_severity_threshold || 'medium',
            enable_relationship_graph: settings.context_settings.enable_relationship_graph !== false,
            enable_contradiction_injection: settings.context_settings.enable_contradiction_injection !== false,
            enable_inline_contradiction_check: settings.context_settings.enable_inline_contradiction_check || false,
            auto_regenerate_on_contradiction: settings.context_settings.auto_regenerate_on_contradiction || false,
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
            enable_chapter_plot_tracking: settings.generation_preferences.enable_chapter_plot_tracking !== false,
            default_plot_check_mode: (settings.generation_preferences.default_plot_check_mode || '1') as '1' | '3' | 'all',
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
            use_context_aware_extraction: settings.extraction_model_settings.use_context_aware_extraction ?? false,
            top_p: settings.extraction_model_settings.top_p ?? 1.0,
            repetition_penalty: settings.extraction_model_settings.repetition_penalty ?? 1.0,
            min_p: settings.extraction_model_settings.min_p ?? 0.0,
            thinking_disable_method: settings.extraction_model_settings.thinking_disable_method ?? 'none',
            thinking_disable_custom: settings.extraction_model_settings.thinking_disable_custom ?? '',
            thinking_enabled_extractions: settings.extraction_model_settings.thinking_enabled_extractions ?? false,
            thinking_enabled_memory: settings.extraction_model_settings.thinking_enabled_memory ?? true,
          });
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
          setImageGenSettings({
            enabled: settings.image_generation_settings.enabled ?? false,
            comfyui_server_url: settings.image_generation_settings.comfyui_server_url || '',
            comfyui_api_key: settings.image_generation_settings.comfyui_api_key || '',
            comfyui_checkpoint: settings.image_generation_settings.comfyui_checkpoint || '',
            comfyui_model_type: settings.image_generation_settings.comfyui_model_type || 'sdxl',
            width: settings.image_generation_settings.width ?? 1024,
            height: settings.image_generation_settings.height ?? 1024,
            steps: settings.image_generation_settings.steps ?? 4,
            cfg_scale: settings.image_generation_settings.cfg_scale ?? 1.5,
            default_style: settings.image_generation_settings.default_style || 'illustrated',
            use_extraction_llm_for_prompts: settings.image_generation_settings.use_extraction_llm_for_prompts ?? false,
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-2 sm:p-4">
      <div className="theme-card rounded-lg shadow-xl max-w-4xl w-full max-h-[95vh] sm:max-h-[90vh] overflow-hidden border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-3 sm:p-6 border-b border-gray-700 theme-banner">
          <div className="flex items-center gap-2 sm:gap-3">
            <SettingsIcon className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
            <h2 className="text-lg sm:text-xl font-bold text-white">Settings</h2>
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
