/**
 * Roleplay API module
 *
 * Handles roleplay session creation, turn generation, character management,
 * and settings updates.
 */

import { BaseApiClient } from './base';

// --- Types ---

export interface RoleplayCharacterConfig {
  character_id: number;
  role?: string;
  source_story_id?: number | null;
  source_branch_id?: number | null;
  talkativeness?: number;
  is_player?: boolean;
}

export interface RoleplayCreateData {
  title?: string;
  scenario?: string;
  setting?: string;
  tone?: string;
  content_rating?: string;
  characters: RoleplayCharacterConfig[];
  player_mode?: 'character' | 'narrator' | 'director';
  turn_mode?: 'natural' | 'round_robin' | 'manual';
  response_length?: 'concise' | 'detailed';
  auto_continue?: boolean;
  max_auto_turns?: number;
  narration_style?: 'minimal' | 'moderate' | 'rich';
  voice_mapping?: Record<string, unknown>;
  generate_opening?: boolean;
}

export interface RoleplayCreateResponse {
  message: string;
  story_id: number;
  branch_id: number;
  chapter_id: number;
  characters: {
    story_character_id: number;
    character_id: number;
    name: string;
    role: string;
    is_player: boolean;
  }[];
}

export interface RoleplayListItem {
  story_id: number;
  title: string;
  scenario: string;
  tone: string;
  content_rating: string;
  characters: string[];
  turn_count: number;
  created_at: string;
  updated_at: string;
}

export interface RoleplayCharacter {
  story_character_id: number;
  character_id: number;
  name: string;
  role: string;
  is_player: boolean;
  is_active: boolean;
  source_story_id: number | null;
}

export interface RoleplayTurn {
  sequence: number;
  scene_id: number;
  variant_id: number;
  content: string;
  generation_method: string;
  created_at: string | null;
}

export interface RoleplayDetail {
  story_id: number;
  title: string;
  scenario: string;
  setting: string;
  tone: string;
  content_rating: string;
  status: string;
  branch_id: number;
  roleplay_settings: Record<string, unknown>;
  characters: RoleplayCharacter[];
  turns: RoleplayTurn[];
  turn_count: number;
  created_at: string;
  updated_at: string;
}

export interface RoleplaySettings {
  turn_mode?: string;
  response_length?: string;
  auto_continue?: boolean;
  max_auto_turns?: number;
  narration_style?: string;
}

export interface CharacterStoryEntry {
  story_id: number;
  title: string;
  timeline_order: number | null;
}

export interface StreamCallbacks {
  onStart?: (data: Record<string, unknown>) => void;
  onContent?: (chunk: string) => void;
  onComplete?: (data: Record<string, unknown>) => void;
  onAutoTurnStart?: (turn: number) => void;
  onAutoTurnComplete?: (turn: number, sceneId: number, variantId: number) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

// --- API Client ---

export class RoleplayApi extends BaseApiClient {
  async createRoleplay(config: RoleplayCreateData): Promise<RoleplayCreateResponse> {
    return this.request<RoleplayCreateResponse>('/api/roleplay/', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async listRoleplays(): Promise<RoleplayListItem[]> {
    return this.request<RoleplayListItem[]>('/api/roleplay/');
  }

  async getRoleplay(id: number): Promise<RoleplayDetail> {
    return this.request<RoleplayDetail>(`/api/roleplay/${id}`);
  }

  async deleteRoleplay(id: number): Promise<void> {
    await this.request(`/api/roleplay/${id}`, { method: 'DELETE' });
  }

  async updateSettings(id: number, settings: RoleplaySettings): Promise<Record<string, unknown>> {
    return this.request(`/api/roleplay/${id}/settings`, {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  async addCharacter(
    id: number,
    config: { character_id: number; role?: string; source_story_id?: number; talkativeness?: number }
  ): Promise<Record<string, unknown>> {
    return this.request(`/api/roleplay/${id}/characters`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async removeCharacter(id: number, storyCharacterId: number): Promise<Record<string, unknown>> {
    return this.request(`/api/roleplay/${id}/characters/${storyCharacterId}`, {
      method: 'DELETE',
    });
  }

  async getCharacterStories(characterId: number): Promise<CharacterStoryEntry[]> {
    return this.request<CharacterStoryEntry[]>(`/api/roleplay/characters/${characterId}/stories`);
  }

  async editTurn(id: number, sceneId: number, content: string): Promise<{ scene_id: number; variant_id: number; content: string }> {
    return this.request(`/api/roleplay/${id}/turns/${sceneId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  }

  async deleteTurnsFrom(id: number, sequence: number): Promise<{ deleted_count: number }> {
    return this.request(`/api/roleplay/${id}/turns/from/${sequence}`, {
      method: 'DELETE',
    });
  }

  async regenerateTurnStream(
    id: number,
    sceneId: number,
    callbacks: StreamCallbacks,
    abortSignal?: AbortSignal
  ): Promise<void> {
    const response = await this.streamingRequest(
      `/api/roleplay/${id}/turns/${sceneId}/regenerate`,
      { method: 'POST' },
      abortSignal
    );
    await this._processSSEStream(response, callbacks);
  }

  async getRelationships(id: number): Promise<Record<string, Record<string, { type: string; strength: number; arc_summary: string }>>> {
    return this.request(`/api/roleplay/${id}/relationships`);
  }

  async updateRelationship(
    id: number,
    storyCharacterId: number,
    data: { target_character_name: string; relationship_type: string; strength: number; description?: string }
  ): Promise<Record<string, unknown>> {
    return this.request(`/api/roleplay/${id}/characters/${storyCharacterId}/relationships`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getVoiceMapping(id: number): Promise<{ voice_mapping: Record<string, { voice_id: string; speed: number }> }> {
    return this.request(`/api/roleplay/${id}/voices`);
  }

  async updateVoiceMapping(
    id: number,
    voiceMapping: Record<string, { voice_id: string; speed: number }>
  ): Promise<Record<string, unknown>> {
    return this.request(`/api/roleplay/${id}/voices`, {
      method: 'PUT',
      body: JSON.stringify({ voice_mapping: voiceMapping }),
    });
  }

  /**
   * Stream an auto-generated player turn via SSE.
   */
  async autoPlayerStream(
    id: number,
    callbacks: StreamCallbacks,
    abortSignal?: AbortSignal
  ): Promise<void> {
    const response = await this.streamingRequest(
      `/api/roleplay/${id}/auto-player/stream`,
      { method: 'POST' },
      abortSignal
    );
    await this._processSSEStream(response, callbacks);
  }

  /**
   * Stream an opening scene generation via SSE.
   */
  async generateOpeningStream(
    id: number,
    callbacks: StreamCallbacks,
    abortSignal?: AbortSignal
  ): Promise<void> {
    const response = await this.streamingRequest(
      `/api/roleplay/${id}/opening/stream`,
      { method: 'POST' },
      abortSignal
    );
    await this._processSSEStream(response, callbacks);
  }

  /**
   * Stream an AI turn response via SSE.
   */
  async generateTurnStream(
    id: number,
    content: string,
    inputMode: string = 'character',
    callbacks: StreamCallbacks,
    activeCharacterIds?: number[],
    abortSignal?: AbortSignal
  ): Promise<void> {
    const body: Record<string, unknown> = { content, input_mode: inputMode };
    if (activeCharacterIds) {
      body.active_character_ids = activeCharacterIds;
    }

    const response = await this.streamingRequest(
      `/api/roleplay/${id}/turns/stream`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
      abortSignal
    );
    await this._processSSEStream(response, callbacks);
  }

  /**
   * Stream auto-continue (characters talk among themselves) via SSE.
   */
  async autoContinueStream(
    id: number,
    numTurns: number,
    callbacks: StreamCallbacks,
    abortSignal?: AbortSignal
  ): Promise<void> {
    const response = await this.streamingRequest(
      `/api/roleplay/${id}/auto-continue/stream`,
      {
        method: 'POST',
        body: JSON.stringify({ num_turns: numTurns }),
      },
      abortSignal
    );
    await this._processSSEStream(response, callbacks);
  }

  /**
   * Process an SSE stream response, dispatching to callbacks.
   */
  private async _processSSEStream(response: Response, callbacks: StreamCallbacks): Promise<void> {
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();

          if (payload === '[DONE]') {
            callbacks.onDone?.();
            return;
          }

          try {
            const data = JSON.parse(payload);
            switch (data.type) {
              case 'start':
                callbacks.onStart?.(data);
                break;
              case 'content':
                callbacks.onContent?.(data.chunk);
                break;
              case 'complete':
                callbacks.onComplete?.(data);
                break;
              case 'auto_turn_start':
                callbacks.onAutoTurnStart?.(data.turn);
                break;
              case 'auto_turn_complete':
                callbacks.onAutoTurnComplete?.(data.turn, data.scene_id, data.variant_id);
                break;
              case 'error':
                callbacks.onError?.(data.message);
                break;
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}
