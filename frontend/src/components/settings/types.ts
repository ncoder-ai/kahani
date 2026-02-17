/**
 * Settings Types
 *
 * Shared type definitions for the Settings Modal components.
 */

import { UIPreferences, GenerationPreferences, SamplerSettings } from '@/types/settings';
import { ProseStyleDefinition } from '@/types/writing-presets';

// Re-export from @/types/settings for convenience
export type { UIPreferences, GenerationPreferences, SamplerSettings };
export type { ProseStyleDefinition };

export interface WritingPreset {
  id?: number;
  name: string;
  system_prompt: string;
  summary_system_prompt: string;
  pov?: string;
  prose_style?: string;
  is_active?: boolean;
}

export interface LLMSettings {
  temperature: number;
  top_p: number;
  top_k: number;
  repetition_penalty: number;
  max_tokens: number;
  timeout_total?: number;
  api_url: string;
  api_key: string;
  api_type: string;
  model_name: string;
  completion_mode: 'chat' | 'text';
  text_completion_template?: string;
  text_completion_preset?: string;
  reasoning_effort?: string | null;
  show_thinking_content?: boolean;
  thinking_model_type?: string | null;       // 'none'|'qwen3'|'deepseek'|etc.
  thinking_model_custom_pattern?: string;
  thinking_enabled_generation?: boolean;     // default false
}

export interface ContextSettings {
  max_tokens: number;
  keep_recent_scenes: number;  // Number of complete scene batches to include
  summary_threshold: number;
  summary_threshold_tokens: number;
  enable_summarization: boolean;
  character_extraction_threshold?: number;
  scene_batch_size?: number;
  enable_semantic_memory?: boolean;
  context_strategy?: string;
  semantic_search_top_k?: number;
  semantic_scenes_in_context?: number;
  semantic_context_weight?: number;
  character_moments_in_context?: number;
  auto_extract_character_moments?: boolean;
  auto_extract_plot_events?: boolean;
  extraction_confidence_threshold?: number;
  plot_event_extraction_threshold?: number;
  fill_remaining_context?: boolean;
  // Memory & Continuity Settings
  enable_working_memory?: boolean;
  enable_contradiction_detection?: boolean;
  contradiction_severity_threshold?: string;
  enable_relationship_graph?: boolean;
  enable_contradiction_injection?: boolean;
  enable_inline_contradiction_check?: boolean;
  auto_regenerate_on_contradiction?: boolean;
}

export interface ExtractionModelSettings {
  enabled: boolean;
  url: string;
  api_key: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  fallback_to_main: boolean;
  use_context_aware_extraction?: boolean;
  // Use main LLM for specific extraction types
  use_main_llm_for_plot_extraction?: boolean;
  // Advanced sampling settings
  top_p?: number;
  repetition_penalty?: number;
  min_p?: number;
  // Thinking disable settings
  thinking_disable_method?: 'none' | 'qwen3' | 'deepseek' | 'mistral' | 'gemini' | 'openai' | 'kimi' | 'glm' | 'custom';
  thinking_disable_custom?: string;
  thinking_enabled_extractions?: boolean;   // default false
  thinking_enabled_memory?: boolean;        // default true
}

// Thinking model type options — how to control <think> tags for local thinking models
export const THINKING_DISABLE_OPTIONS = [
  { value: 'none', label: 'None (not a thinking model)', description: 'Model does not produce thinking tags' },
  { value: 'qwen3', label: 'Qwen3', description: 'Uses /no_think prefix to suppress, strips <think> tags' },
  { value: 'deepseek', label: 'DeepSeek', description: 'Strips <think> tags from output' },
  { value: 'mistral', label: 'Mistral Magistral', description: 'Uses API parameter to control thinking' },
  { value: 'gemini', label: 'Gemini', description: 'Uses API parameter to control thinking' },
  { value: 'openai', label: 'OpenAI o1/o3', description: 'Uses API parameter to control thinking' },
  { value: 'kimi', label: 'Kimi K2', description: 'Strips thinking tags (use Instruct variant)' },
  { value: 'glm', label: 'GLM-4', description: 'API param + strips <think> tags' },
  { value: 'custom', label: 'Custom', description: 'Define custom regex pattern to strip thinking tags' },
] as const;

export interface TTSProvider {
  type: string;
  name: string;
  supports_streaming: boolean;
}

export interface TTSVoice {
  id: string;
  name: string;
  language?: string;
  description?: string;
}

export interface TTSSettings {
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

// Common props for all settings tabs
export interface SettingsTabProps {
  token: string | null;
  showMessage: (msg: string, type: 'success' | 'error') => void;
}
