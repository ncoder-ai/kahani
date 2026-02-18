/**
 * Shared types for API modules
 *
 * This module exports all shared type definitions used across API modules.
 */

// ========== Voice Style Types ==========
export interface VoiceStyle {
  preset?: string;
  formality?: 'formal' | 'casual' | 'streetwise' | 'archaic';
  vocabulary?: 'simple' | 'average' | 'sophisticated' | 'technical';
  tone?: 'cheerful' | 'sarcastic' | 'gruff' | 'nervous' | 'calm' | 'dramatic' | 'deadpan';
  profanity?: 'none' | 'mild' | 'moderate' | 'heavy';
  speech_quirks?: string;
  primary_language?: string;
  secondary_language?: string;
  language_mixing?: 'none' | 'light' | 'moderate' | 'heavy';
}

export interface VoiceStylePreset {
  name: string;
  description: string;
  category: 'neutral' | 'regional' | 'archetype' | 'fantasy';
  example: string;
}

export interface VoiceStyleAttribute {
  id: string;
  name: string;
  description: string;
}

export interface VoiceStylePresetsResponse {
  presets: Record<string, VoiceStylePreset>;
  attributes: {
    formality: VoiceStyleAttribute[];
    vocabulary: VoiceStyleAttribute[];
    tone: VoiceStyleAttribute[];
    profanity: VoiceStyleAttribute[];
    language_mixing_level: VoiceStyleAttribute[];
    secondary_languages: VoiceStyleAttribute[];
  };
}

// ========== Story Arc Types ==========
export interface ArcPhase {
  id: string;
  name: string;
  description: string;
  key_events: string[];
  characters_involved: string[];
  estimated_chapters: number;
  order: number;
}

export interface StoryArc {
  structure_type: 'three_act' | 'five_act' | 'hero_journey' | 'custom';
  phases: ArcPhase[];
  generated_at: string;
  last_modified_at: string;
}

// ========== Chapter Plot Types ==========
export interface CharacterArc {
  character_name: string;
  name?: string;
  development: string;
  dynamics?: string;
}

export interface NewCharacterSuggestion {
  name: string;
  role: string;
  description: string;
  reason: string;
  suggested_voice_style?: string;
}

export interface ChapterPlot {
  summary: string;
  opening_situation: string;
  key_events: string[];
  climax: string;
  resolution: string;
  character_arcs: CharacterArc[];
  new_character_suggestions: NewCharacterSuggestion[];
  recommended_characters: string[];
  mood?: string;
  location?: string;
  _characterIds?: number[];
}

export interface StructuredElements {
  overview: string;
  characters: CharacterArc[];
  tone: string;
  key_events: string[];
  ending: string;
}

export interface SuggestedElements {
  overview?: string;
  characters?: string;
  tone?: string;
  key_events?: string[];
  ending?: string;
}

export interface ChapterProgress {
  has_plot: boolean;
  completed_events: string[];
  total_events: number;
  progress_percentage: number;
  remaining_events: string[];
  climax_reached: boolean;
  resolution_reached: boolean;
  scene_count: number;
  climax?: string;
  resolution?: string;
  key_events: string[];
}

// ========== Story Types ==========
export interface Story {
  id: number;
  title: string;
  description?: string;
  genre?: string;
  tone?: string;
  world_setting?: string;
  initial_premise?: string;
  scenario?: string;
  status: string;
  content_rating: string;
  interaction_types?: string[];
  plot_check_mode?: '1' | '3' | 'all';  // How many events to check: "1" (strict), "3", "all"
  created_at: string;
  updated_at: string;
  scenes?: Scene[];
  flow_info?: {
    total_scenes: number;
    has_variants: boolean;
  };
  branch?: {
    id: number;
    name: string;
    is_main: boolean;
    total_branches: number;
  };
  current_branch_id?: number;
  story_arc?: StoryArc;
}

export interface Scene {
  id: number;
  chapter_id?: number;
  sequence_number: number;
  title: string;
  content: string;
  location?: string;
  characters_present?: string[];
  variant_id?: number;
  variant_number?: number;
  is_original?: boolean;
  has_multiple_variants?: boolean;
  choices?: Choice[];
}

export interface SceneVariant {
  id: number;
  variant_number: number;
  is_original: boolean;
  content: string;
  title?: string;
  generation_method?: string;
  user_edited?: boolean;
  choices?: Choice[];
}

export interface Choice {
  id: number;
  text: string;
  description?: string;
  order: number;
  is_user_created?: boolean;
}

// ========== Character Types ==========
export interface Character {
  id: number;
  name: string;
  description?: string;
  gender?: string;
  personality_traits?: string[];
  background?: string;
  goals?: string;
  fears?: string;
  appearance?: string;
  is_template?: boolean;
  is_public?: boolean;
  voice_style?: VoiceStyle | null;
  portrait_image_id?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface StoryCharacter {
  id: number;
  story_id: number;
  character_id: number;
  branch_id?: number | null;
  role?: string;
  voice_style_override?: VoiceStyle | null;
  // Character details included in response
  name: string;
  description?: string | null;
  gender?: string | null;
  default_voice_style?: VoiceStyle | null;
  // Legacy field for backwards compatibility
  character?: Character;
}

// ========== Chapter Types ==========
export interface Chapter {
  id: number;
  story_id: number;
  chapter_number: number;
  title: string;
  status: 'planning' | 'active' | 'completed';
  scenes_count?: number;
  plot?: ChapterPlot;
  location_name?: string;
  created_at?: string;
  updated_at?: string;
}

// ========== Branch Types ==========
export interface Branch {
  id: number;
  story_id: number;
  name: string;
  description?: string;
  is_main: boolean;
  is_active: boolean;
  fork_sequence?: number;
  parent_branch_id?: number;
  created_at?: string;
}

// ========== Entity State Types ==========
export interface CharacterState {
  id: number;
  character_id: number;
  character_name: string;
  story_id: number;
  last_updated_scene: number | null;
  current_location: string | null;
  current_position: string | null;
  items_in_hand: string[];
  physical_condition: string | null;
  appearance: string | null;
  possessions: string[];
  emotional_state: string | null;
  current_goal: string | null;
  active_conflicts: string[];
  knowledge: string[];
  secrets: string[];
  relationships: Record<string, string>;
  arc_stage: string | null;
  arc_progress: number | null;
  recent_decisions: string[];
  recent_actions: string[];
  full_state: Record<string, unknown>;
  updated_at: string | null;
}

export interface LocationState {
  id: number;
  story_id: number;
  location_name: string;
  last_updated_scene: number | null;
  condition: string | null;
  atmosphere: string | null;
  notable_features: string[];
  current_occupants: string[];
  significant_events: string[];
  time_of_day: string | null;
  weather: string | null;
  full_state: Record<string, unknown>;
  updated_at: string | null;
}

export interface ObjectState {
  id: number;
  story_id: number;
  object_name: string;
  last_updated_scene: number | null;
  condition: string | null;
  current_location: string | null;
  current_owner_id: number | null;
  current_owner_name: string | null;
  significance: string | null;
  object_type: string | null;
  powers: string[];
  limitations: string[];
  origin: string | null;
  previous_owners: string[];
  recent_events: string[];
  full_state: Record<string, unknown>;
  updated_at: string | null;
}

export interface EntityStates {
  story_id: number;
  branch_id: number | null;
  character_states: CharacterState[];
  location_states: LocationState[];
  object_states: ObjectState[];
  counts: {
    characters: number;
    locations: number;
    objects: number;
  };
}

// ========== Brainstorm Types ==========
export interface BrainstormSession {
  id: number;
  status: string;
  story_id?: number;
  messages?: BrainstormMessage[];
  extracted_elements?: any;
  created_at?: string;
  updated_at?: string;
}

export interface BrainstormMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
}

// ========== Writing Preset Types ==========
export interface WritingPreset {
  id: number;
  name: string;
  description?: string;
  prose_style?: string;
  scene_instructions?: string;
  choice_instructions?: string;
  character_voice_instructions?: string;
  pacing_instructions?: string;
  tone_instructions?: string;
  world_building_instructions?: string;
  is_active: boolean;
  is_default: boolean;
  user_id: number;
  created_at: string;
  updated_at: string;
}

// ========== World & Chronicle Types ==========
export interface World {
  id: number;
  name: string;
  description?: string;
  story_count: number;
  created_at: string;
  updated_at?: string;
}

export interface WorldStory {
  id: number;
  title: string;
  description?: string;
  genre?: string;
  status: string;
  content_rating: string;
  timeline_order?: number;
  current_branch_id?: number;
  branches?: { id: number; name: string; is_main: boolean }[];
  scene_count?: number;
  chapter_count?: number;
  character_names?: string[];
  story_so_far?: string;
  created_at: string;
  updated_at: string;
}

export interface WorldCharacter {
  character_id: number;
  character_name: string;
  entry_count: number;
}

export interface WorldLocation {
  location_name: string;
  entry_count: number;
}

export interface ChronicleEntry {
  id: number;
  entry_type: string;
  description: string;
  is_defining: boolean;
  sequence_order: number;
  scene_id?: number;
  story_id: number;
  branch_id?: number;
  created_at: string;
}

export interface LorebookEntry {
  id: number;
  location_name: string;
  event_description: string;
  sequence_order: number;
  scene_id?: number;
  story_id: number;
  branch_id?: number;
  created_at: string;
}

export interface CharacterSnapshotData {
  snapshot_text: string | null;
  chronicle_entry_count: number;
  current_entry_count: number;
  is_stale: boolean;
  timeline_order?: number;
  up_to_story_id?: number;
  branch_id?: number;
  created_at?: string;
  updated_at?: string;
}

// ========== Interaction Types ==========
export interface Interaction {
  id: number;
  interaction_type: string;
  character_a: string;
  character_b: string;
  first_occurrence_scene: number;
  description: string | null;
}
