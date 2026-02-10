/**
 * Characters API module
 *
 * Handles character management, story characters, and voice styles.
 */

import { BaseApiClient } from './base';
import { Character, StoryCharacter, VoiceStyle, VoiceStylePresetsResponse } from './types';

export interface CharacterCreateData {
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
}

export interface CharacterUpdateData {
  name?: string;
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
}

export interface CharacterSuggestion {
  name: string;
  role: string;
  description: string;
  mentions: number;
  first_appearance: number;
  personality_traits?: string[];
  status: 'unknown' | 'active' | 'inactive';
}

export interface CharacterAnalysis {
  name: string;
  personality_traits: string[];
  background: string;
  goals: string;
  fears: string;
  appearance: string;
  voice_style_suggestion?: VoiceStyle;
}

export class CharactersApi extends BaseApiClient {
  /**
   * Get a single character by ID
   */
  async getCharacter(characterId: number): Promise<Character> {
    return this.request<Character>(`/api/characters/${characterId}`);
  }

  /**
   * Get list of characters with pagination and filters
   */
  async getCharacters(
    skip = 0,
    limit = 50,
    includePublic = true,
    templatesOnly = false
  ): Promise<Character[]> {
    return this.request<Character[]>(
      `/api/characters/?skip=${skip}&limit=${limit}&include_public=${includePublic}&templates_only=${templatesOnly}`
    );
  }

  /**
   * Create a new character
   */
  async createCharacter(data: CharacterCreateData): Promise<Character> {
    return this.request<Character>('/api/characters/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Update an existing character
   */
  async updateCharacter(characterId: number, data: CharacterUpdateData): Promise<Character> {
    return this.request<Character>(`/api/characters/${characterId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * Delete a character
   */
  async deleteCharacter(characterId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/characters/${characterId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Bulk delete multiple characters
   */
  async bulkDeleteCharacters(characterIds: number[]): Promise<{ message: string; deleted_count: number }> {
    return this.request<{ message: string; deleted_count: number }>('/api/characters/bulk-delete', {
      method: 'POST',
      body: JSON.stringify({ character_ids: characterIds }),
    });
  }

  /**
   * Get voice style presets
   */
  async getVoiceStylePresets(): Promise<VoiceStylePresetsResponse> {
    return this.request<VoiceStylePresetsResponse>('/api/characters/voice-style-presets');
  }

  /**
   * Get characters associated with a story
   * @param storyId - The story ID
   * @param branchId - Optional branch ID to filter characters by branch
   */
  async getStoryCharacters(storyId: number, branchId?: number): Promise<StoryCharacter[]> {
    const params = branchId !== undefined ? `?branch_id=${branchId}` : '';
    return this.request<StoryCharacter[]>(`/api/stories/${storyId}/characters${params}`);
  }

  /**
   * Remove a character from a story (deletes the StoryCharacter association)
   * This does NOT delete the underlying Character from the library
   */
  async removeStoryCharacter(
    storyId: number,
    storyCharacterId: number
  ): Promise<{
    message: string;
    deleted_story_character_id: number;
    character_id: number | null;
    branch_id: number | null;
  }> {
    return this.request(`/api/stories/${storyId}/characters/${storyCharacterId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Update voice style override for a story character
   */
  async updateStoryCharacterVoiceStyle(
    storyId: number,
    storyCharacterId: number,
    voiceStyleOverride: VoiceStyle | null
  ): Promise<{ message: string; story_character: StoryCharacter }> {
    return this.request<{ message: string; story_character: StoryCharacter }>(
      `/api/stories/${storyId}/characters/${storyCharacterId}/voice-style`,
      {
        method: 'PUT',
        body: JSON.stringify({ voice_style_override: voiceStyleOverride }),
      }
    );
  }

  /**
   * Clear voice style override for a story character
   */
  async clearStoryCharacterVoiceStyle(
    storyId: number,
    storyCharacterId: number
  ): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      `/api/stories/${storyId}/characters/${storyCharacterId}/voice-style`,
      {
        method: 'DELETE',
      }
    );
  }

  /**
   * Update role for a story character
   */
  async updateStoryCharacterRole(
    storyId: number,
    storyCharacterId: number,
    role: string
  ): Promise<{ message: string; story_character: StoryCharacter }> {
    return this.request<{ message: string; story_character: StoryCharacter }>(
      `/api/stories/${storyId}/characters/${storyCharacterId}/role`,
      {
        method: 'PUT',
        body: JSON.stringify({ role }),
      }
    );
  }

  /**
   * Generate a character using AI
   */
  async generateCharacterWithAI(
    prompt: string,
    storyContext?: { genre?: string; tone?: string; world_setting?: string },
    previousGeneration?: any
  ): Promise<{
    character: CharacterAnalysis;
    message: string;
  }> {
    return this.request<{ character: CharacterAnalysis; message: string }>(
      '/api/character-assistant/generate',
      {
        method: 'POST',
        body: JSON.stringify({
          prompt,
          story_context: storyContext,
          previous_generation: previousGeneration,
        }),
      }
    );
  }

  /**
   * Check character importance in a story
   */
  async checkCharacterImportance(
    storyId: number,
    chapterId?: number
  ): Promise<{
    characters: Array<{
      name: string;
      importance: 'high' | 'medium' | 'low';
      mentions: number;
    }>;
  }> {
    const params = chapterId ? `?chapter_id=${chapterId}` : '';
    return this.request(`/api/stories/${storyId}/character-importance${params}`);
  }

  /**
   * Get character suggestions based on story content
   */
  async getCharacterSuggestions(
    storyId: number,
    chapterId?: number
  ): Promise<{
    suggestions: CharacterSuggestion[];
    total_npcs_found: number;
    scene_range: { start: number; end: number };
  }> {
    const params = chapterId ? `?chapter_id=${chapterId}` : '';
    return this.request(`/api/stories/${storyId}/character-suggestions${params}`);
  }

  /**
   * Analyze character details from story content
   */
  async analyzeCharacterDetails(
    storyId: number,
    characterName: string
  ): Promise<{
    character_data: CharacterAnalysis;
    confidence: number;
    source_scenes: number[];
  }> {
    return this.request(`/api/stories/${storyId}/analyze-character`, {
      method: 'POST',
      body: JSON.stringify({ character_name: characterName }),
    });
  }

  /**
   * Create a character from an NPC suggestion
   */
  async createCharacterFromSuggestion(
    storyId: number,
    characterName: string,
    characterData: CharacterCreateData & { add_to_chapter?: number }
  ): Promise<{
    character: Character;
    story_character: StoryCharacter;
    message: string;
  }> {
    return this.request(`/api/stories/${storyId}/create-character-from-suggestion`, {
      method: 'POST',
      body: JSON.stringify({
        character_name: characterName,
        character_data: characterData,
      }),
    });
  }
}
