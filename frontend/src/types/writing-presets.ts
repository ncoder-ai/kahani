/**
 * Writing Style Presets Types
 * 
 * Types for the writing style preset system that allows users to customize
 * how the AI writes their stories.
 */

export interface WritingStylePreset {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  system_prompt: string;
  summary_system_prompt: string | null;
  pov: string | null;  // 'first', 'second', 'third', or null
  prose_style: string | null;  // 'balanced', 'dialogue_forward', etc.
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface WritingPresetCreateData {
  name: string;
  description?: string;
  system_prompt: string;
  summary_system_prompt?: string;
  pov?: string;  // 'first', 'second', or 'third'
  prose_style?: string;  // prose style key
}

export interface WritingPresetUpdateData {
  name?: string;
  description?: string;
  system_prompt?: string;
  summary_system_prompt?: string;
  pov?: string;  // 'first', 'second', or 'third'
  prose_style?: string;  // prose style key
}

export interface WritingPresetTemplate {
  name: string;
  description: string;
  system_prompt: string;
  summary_system_prompt: string | null;
  pov?: string;  // 'first', 'second', or 'third'
  prose_style?: string;  // prose style key
}

// Preset categories for UI organization
export enum PresetCategory {
  DEFAULT = 'default',
  FANTASY = 'fantasy',
  ROMANCE = 'romance',
  HORROR = 'horror',
  SCIFI = 'scifi',
  MYSTERY = 'mystery',
  CUSTOM = 'custom',
}

// Suggested preset templates for new users
export interface SuggestedPreset {
  name: string;
  description: string;
  category: PresetCategory;
  system_prompt: string;
  summary_system_prompt?: string;
}

export const SUGGESTED_PRESETS: SuggestedPreset[] = [
  {
    name: 'Default',
    description: 'Balanced, engaging storytelling suitable for all genres',
    category: PresetCategory.DEFAULT,
    system_prompt: `You are a creative storytelling assistant. Write in an engaging narrative style that:
- Uses vivid, descriptive language to paint clear mental images
- Creates immersive scenes that draw readers into the story world
- Develops characters naturally through their actions, dialogue, and decisions
- Maintains appropriate pacing to keep the story moving forward
- Respects the genre, tone, and themes specified by the user

Keep content appropriate for general audiences unless explicitly told otherwise by the user. Write in second person ("you") for interactive stories to create an immersive experience.`,
  },
  {
    name: 'Epic Fantasy',
    description: 'Grand, dramatic storytelling with rich worldbuilding',
    category: PresetCategory.FANTASY,
    system_prompt: `You are a master fantasy storyteller. Write in an epic, sweeping style that:
- Uses rich, evocative language that paints vivid magical worlds
- Creates grand, mythic atmospheres with a sense of wonder and scale
- Develops complex characters with legendary qualities and moral depth
- Weaves intricate plots with prophecies, ancient conflicts, and heroic journeys
- Balances action, dialogue, and description to maintain epic pacing

Embrace high fantasy tropes while adding fresh twists. Write in second person ("you") for immersive interactive storytelling.`,
  },
  {
    name: 'Dark & Gritty',
    description: 'Noir-style storytelling with cynical tone and moral complexity',
    category: PresetCategory.MYSTERY,
    system_prompt: `You are a noir storyteller. Write in a dark, atmospheric style that:
- Uses sparse, punchy prose with sharp observations
- Creates shadowy, tense atmospheres with moral ambiguity
- Develops flawed, morally complex characters with hidden depths
- Emphasizes harsh realities, difficult choices, and consequences
- Balances gritty action with introspective moments

Embrace darker themes and complex morality. Content may include mature themes. Write in second person ("you") for immersive storytelling.`,
  },
  {
    name: 'Cozy & Light',
    description: 'Warm, comforting, wholesome storytelling',
    category: PresetCategory.DEFAULT,
    system_prompt: `You are a heartwarming storyteller. Write in a gentle, uplifting style that:
- Uses soft, comforting language that creates a safe, welcoming atmosphere
- Creates cozy, familiar settings that feel like home
- Develops kind, relatable characters with genuine connections
- Emphasizes friendship, community, personal growth, and simple joys
- Maintains a gentle pace with moments of humor and heart

Keep content wholesome and appropriate for all ages. Write in second person ("you") for warm, immersive storytelling.`,
  },
  {
    name: 'Romantic',
    description: 'Emotional, sensual storytelling focused on relationships',
    category: PresetCategory.ROMANCE,
    system_prompt: `You are a romance storyteller. Write in an emotional, evocative style that:
- Uses expressive, sensual language that captures feelings and attraction
- Creates intimate moments with emotional depth and chemistry
- Develops complex characters with vulnerabilities and desires
- Emphasizes relationship dynamics, emotional growth, and connection
- Balances passion with tenderness and meaningful dialogue

Content may include mature romantic themes as appropriate. Write in second person ("you") for immersive romantic storytelling.`,
  },
  {
    name: 'Horror',
    description: 'Atmospheric, tense storytelling that builds dread',
    category: PresetCategory.HORROR,
    system_prompt: `You are a horror storyteller. Write in a chilling, atmospheric style that:
- Uses unsettling, evocative language that creates unease
- Creates oppressive, dread-filled atmospheres with mounting tension
- Develops vulnerable characters facing incomprehensible terrors
- Emphasizes psychological horror, suspense, and the unknown
- Balances explicit scares with subtle, creeping dread

Content may include scary and disturbing themes. Write in second person ("you") for immersive horror storytelling.`,
  },
];

/**
 * Prose Style Definitions
 * 
 * Each style has a key, display name, description, and example text
 * to help users understand what each style produces.
 * 
 * NOTE: Prose styles are now fetched from the backend API (prompts.yml)
 * instead of being hardcoded here. Use api.getProseStyles() to fetch them.
 */
export interface ProseStyleDefinition {
  key: string;
  name: string;
  description: string;
  example: string;
}

