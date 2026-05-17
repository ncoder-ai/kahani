/**
 * Settings API module
 *
 * Handles user settings, text completion templates, and presets.
 */

import { BaseApiClient } from './base';

export interface UserSettings {
  settings: {
    llm_settings?: {
      model?: string;
      temperature?: number;
      max_tokens?: number;
      timeout_total?: number;
      timeout_connect?: number;
    };
    context_settings?: {
      max_tokens?: number;
      keep_recent_scenes?: number;
      summary_threshold?: number;
    };
    ui_settings?: {
      theme?: string;
      font_size?: number;
    };
    sampler_settings?: {
      n?: {
        enabled: boolean;
        value: number;
      };
    };
  };
}

export interface LastAccessedStoryResponse {
  auto_open_last_story: boolean;
  last_accessed_story_id?: number;
}

export interface TextCompletionPreset {
  key: string;
  name: string;
  description: string;
  compatible_models: string[];
}

export interface TextCompletionPresetsResponse {
  presets: TextCompletionPreset[];
}

export interface PresetTemplate {
  template: any;
}

export interface TestRenderResponse {
  valid: boolean;
  error: string | null;
  rendered_prompt: string | null;
  prompt_length?: number;
}

export class SettingsApi extends BaseApiClient {
  /**
   * Get user settings
   */
  async getUserSettings(): Promise<UserSettings> {
    return this.request<UserSettings>('/api/settings/');
  }

  /**
   * Get last accessed story info for auto-open feature
   */
  async getLastAccessedStory(): Promise<LastAccessedStoryResponse> {
    return this.request<LastAccessedStoryResponse>('/api/settings/last-story');
  }

  /**
   * Get available text completion presets
   */
  async getTextCompletionPresets(): Promise<TextCompletionPresetsResponse> {
    return this.request<TextCompletionPresetsResponse>('/api/settings/text-completion/presets');
  }

  /**
   * Get a specific preset template
   */
  async getPresetTemplate(presetName: string): Promise<PresetTemplate> {
    return this.request<PresetTemplate>(`/api/settings/text-completion/template/${presetName}`);
  }

  /**
   * Test rendering a template with sample data
   */
  async testTemplateRender(
    template: any,
    testSystem: string,
    testUser: string
  ): Promise<TestRenderResponse> {
    return this.request<TestRenderResponse>('/api/settings/text-completion/test-render', {
      method: 'POST',
      body: JSON.stringify({ template, test_system: testSystem, test_user: testUser })
    });
  }
}
