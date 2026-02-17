/**
 * Writing Presets API module
 *
 * Handles writing style presets and prose settings.
 */

import { BaseApiClient } from './base';
import { WritingPreset } from './types';

export interface WritingPresetCreateData {
  name: string;
  description?: string;
  prose_style?: string;
  scene_instructions?: string;
  choice_instructions?: string;
  character_voice_instructions?: string;
  pacing_instructions?: string;
  tone_instructions?: string;
  world_building_instructions?: string;
}

export interface WritingPresetUpdateData extends Partial<WritingPresetCreateData> {
  is_active?: boolean;
}

export interface ProseStyle {
  id: string;
  name: string;
  description: string;
  example: string;
}

export class WritingPresetsApi extends BaseApiClient {
  /**
   * List all writing presets for the current user
   */
  async listWritingPresets(): Promise<{
    presets: WritingPreset[];
    active_preset_id: number | null;
  }> {
    return this.request('/api/writing-presets/');
  }

  /**
   * Get a specific writing preset
   */
  async getWritingPreset(presetId: number): Promise<WritingPreset> {
    return this.request(`/api/writing-presets/${presetId}`);
  }

  /**
   * Create a new writing preset
   */
  async createWritingPreset(data: WritingPresetCreateData): Promise<{
    preset: WritingPreset;
    message: string;
  }> {
    return this.request('/api/writing-presets/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Update a writing preset
   */
  async updateWritingPreset(
    presetId: number,
    data: WritingPresetUpdateData
  ): Promise<{
    preset: WritingPreset;
    message: string;
  }> {
    return this.request(`/api/writing-presets/${presetId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * Delete a writing preset
   */
  async deleteWritingPreset(presetId: number): Promise<{ message: string }> {
    return this.request(`/api/writing-presets/${presetId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Activate a writing preset (make it the current active preset)
   */
  async activateWritingPreset(presetId: number): Promise<{
    preset: WritingPreset;
    message: string;
  }> {
    return this.request(`/api/writing-presets/${presetId}/activate`, {
      method: 'POST',
    });
  }

  /**
   * Duplicate a writing preset
   */
  async duplicateWritingPreset(presetId: number): Promise<{
    preset: WritingPreset;
    message: string;
  }> {
    return this.request(`/api/writing-presets/${presetId}/duplicate`, {
      method: 'POST',
    });
  }

  /**
   * Get the default writing preset template
   */
  async getDefaultWritingPresetTemplate(): Promise<{
    template: WritingPresetCreateData;
  }> {
    return this.request('/api/writing-presets/default-template');
  }

  /**
   * Get available prose styles
   */
  async getProseStyles(): Promise<{
    styles: ProseStyle[];
  }> {
    return this.request('/api/writing-presets/prose-styles');
  }
}
