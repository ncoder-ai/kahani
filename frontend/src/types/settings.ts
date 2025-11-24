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
