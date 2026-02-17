/**
 * Settings Types
 * 
 * Centralized type definitions for user settings to ensure consistency
 * across all components and avoid interface duplication.
 */

export interface UIPreferences {
  color_theme: string;
  font_size: string;
  show_token_info: boolean;
  show_context_info: boolean;
  notifications: boolean;
  scene_display_format: string; // 'default', 'bubble', 'card', 'minimal'
  show_scene_titles: boolean;
  scene_edit_mode: string; // 'textarea', 'contenteditable'
  auto_open_last_story: boolean;
  last_accessed_story_id?: number;
}

export interface GenerationPreferences {
  default_genre: string;
  default_tone: string;
  scene_length: string;
  auto_choices: boolean;
  choices_count: number;
  enable_streaming?: boolean;
  alert_on_high_context?: boolean;
  use_extraction_llm_for_summary?: boolean;
  separate_choice_generation?: boolean;
  enable_chapter_plot_tracking?: boolean;  // Track plot progress and guide LLM pacing (default: true)
  default_plot_check_mode?: '1' | '3' | 'all';  // How many events to check: "1" (strict), "3", "all"
}

export interface ExportSettings {
  format: string;
  include_metadata: boolean;
  include_choices: boolean;
}

export interface CharacterAssistantSettings {
  enable_suggestions: boolean;
  importance_threshold: number;
  mention_threshold: number;
}

/**
 * Individual sampler configuration with enabled flag and value
 */
export interface SamplerSettingValue<T = number | boolean | string | number[]> {
  enabled: boolean;
  value: T;
}

/**
 * Advanced sampler settings for TabbyAPI and OpenAI-compatible APIs.
 * Each sampler can be individually enabled/disabled.
 * Only enabled samplers are sent to the API via extra_body.
 */
export interface SamplerSettings {
  // Basic Sampling
  temperature_last: SamplerSettingValue<boolean>;
  smoothing_factor: SamplerSettingValue<number>;
  min_p: SamplerSettingValue<number>;
  top_a: SamplerSettingValue<number>;
  
  // Token Control
  min_tokens: SamplerSettingValue<number>;
  token_healing: SamplerSettingValue<boolean>;
  add_bos_token: SamplerSettingValue<boolean>;
  ban_eos_token: SamplerSettingValue<boolean>;
  
  // Penalties
  frequency_penalty: SamplerSettingValue<number>;
  presence_penalty: SamplerSettingValue<number>;
  penalty_range: SamplerSettingValue<number>;
  repetition_decay: SamplerSettingValue<number>;
  
  // Advanced Sampling
  tfs: SamplerSettingValue<number>;
  typical: SamplerSettingValue<number>;
  skew: SamplerSettingValue<number>;
  
  // XTC (Exclude Top Choices)
  xtc_probability: SamplerSettingValue<number>;
  xtc_threshold: SamplerSettingValue<number>;
  
  // DRY (Don't Repeat Yourself)
  dry_multiplier: SamplerSettingValue<number>;
  dry_base: SamplerSettingValue<number>;
  dry_allowed_length: SamplerSettingValue<number>;
  dry_range: SamplerSettingValue<number>;
  dry_sequence_breakers: SamplerSettingValue<string>;
  
  // Mirostat
  mirostat_mode: SamplerSettingValue<number>;
  mirostat_tau: SamplerSettingValue<number>;
  mirostat_eta: SamplerSettingValue<number>;
  
  // Dynamic Temperature
  max_temp: SamplerSettingValue<number>;
  min_temp: SamplerSettingValue<number>;
  temp_exponent: SamplerSettingValue<number>;
  
  // Constraints
  banned_strings: SamplerSettingValue<string>;
  banned_tokens: SamplerSettingValue<number[]>;
  allowed_tokens: SamplerSettingValue<number[]>;
  stop: SamplerSettingValue<string>;
  
  // Other
  cfg_scale: SamplerSettingValue<number>;
  negative_prompt: SamplerSettingValue<string>;
  speculative_ngram: SamplerSettingValue<boolean>;
  
  // Multi-generation
  n: SamplerSettingValue<number>;  // Number of completions to generate (1-5)
}

/**
 * Default sampler settings with all samplers disabled
 */
export const DEFAULT_SAMPLER_SETTINGS: SamplerSettings = {
  // Basic Sampling
  temperature_last: { enabled: false, value: true },
  smoothing_factor: { enabled: false, value: 0.0 },
  min_p: { enabled: false, value: 0.0 },
  top_a: { enabled: false, value: 0.0 },
  
  // Token Control
  min_tokens: { enabled: false, value: 0 },
  token_healing: { enabled: false, value: true },
  add_bos_token: { enabled: false, value: true },
  ban_eos_token: { enabled: false, value: false },
  
  // Penalties
  frequency_penalty: { enabled: false, value: 0.0 },
  presence_penalty: { enabled: false, value: 0.0 },
  penalty_range: { enabled: false, value: 0 },
  repetition_decay: { enabled: false, value: 0 },
  
  // Advanced Sampling
  tfs: { enabled: false, value: 1.0 },
  typical: { enabled: false, value: 1.0 },
  skew: { enabled: false, value: 0.0 },
  
  // XTC (Exclude Top Choices)
  xtc_probability: { enabled: false, value: 0.0 },
  xtc_threshold: { enabled: false, value: 0.0 },
  
  // DRY (Don't Repeat Yourself)
  dry_multiplier: { enabled: false, value: 0.0 },
  dry_base: { enabled: false, value: 0.0 },
  dry_allowed_length: { enabled: false, value: 0 },
  dry_range: { enabled: false, value: 0 },
  dry_sequence_breakers: { enabled: false, value: '' },
  
  // Mirostat
  mirostat_mode: { enabled: false, value: 0 },
  mirostat_tau: { enabled: false, value: 1.5 },
  mirostat_eta: { enabled: false, value: 0.3 },
  
  // Dynamic Temperature
  max_temp: { enabled: false, value: 1.0 },
  min_temp: { enabled: false, value: 1.0 },
  temp_exponent: { enabled: false, value: 1.0 },
  
  // Constraints
  banned_strings: { enabled: false, value: '' },
  banned_tokens: { enabled: false, value: [] },
  allowed_tokens: { enabled: false, value: [] },
  stop: { enabled: false, value: '' },
  
  // Other
  cfg_scale: { enabled: false, value: 1.0 },
  negative_prompt: { enabled: false, value: '' },
  speculative_ngram: { enabled: false, value: true },
  
  // Multi-generation
  n: { enabled: false, value: 1 },  // Number of completions to generate (1-5)
};

export interface UserSettings {
  id: number;
  user_id: number;
  llm_temperature: number;
  llm_top_p: number;
  llm_top_k: number;
  llm_repetition_penalty: number;
  llm_max_tokens: number;
  context_max_tokens: number;
  context_keep_recent_scenes: number;
  context_summary_threshold: number;
  context_enable_summarization: boolean;
  generation_preferences: GenerationPreferences;
  ui_preferences: UIPreferences;
  export_settings: ExportSettings;
  character_assistant_settings: CharacterAssistantSettings;
  created_at: string;
  updated_at: string;
}
