/**
 * Worlds, Chronicles & Lorebook API client
 */

import { BaseApiClient } from './base';
import type {
  World, WorldStory, WorldCharacter, WorldLocation,
  ChronicleEntry, LorebookEntry,
} from './types';

export class WorldsApi extends BaseApiClient {

  // --- Worlds CRUD ---

  async getWorlds(): Promise<World[]> {
    return this.request<World[]>('/api/worlds/');
  }

  async createWorld(name: string, description?: string): Promise<World> {
    return this.request<World>('/api/worlds/', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
  }

  async getWorld(worldId: number): Promise<World> {
    return this.request<World>(`/api/worlds/${worldId}`);
  }

  async updateWorld(worldId: number, data: { name?: string; description?: string }): Promise<World> {
    return this.request<World>(`/api/worlds/${worldId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteWorld(worldId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/worlds/${worldId}`, {
      method: 'DELETE',
    });
  }

  // --- World stories ---

  async getWorldStories(worldId: number): Promise<WorldStory[]> {
    return this.request<WorldStory[]>(`/api/worlds/${worldId}/stories`);
  }

  // --- Characters & Chronicles ---

  async getWorldCharacters(worldId: number): Promise<WorldCharacter[]> {
    return this.request<WorldCharacter[]>(`/api/worlds/${worldId}/characters`);
  }

  async getCharacterChronicle(
    worldId: number,
    characterId: number,
    storyId?: number,
    branchId?: number,
  ): Promise<ChronicleEntry[]> {
    const params = new URLSearchParams();
    if (storyId !== undefined) params.set('story_id', String(storyId));
    if (branchId !== undefined) params.set('branch_id', String(branchId));
    const qs = params.toString();
    return this.request<ChronicleEntry[]>(
      `/api/worlds/${worldId}/characters/${characterId}/chronicle${qs ? `?${qs}` : ''}`
    );
  }

  async updateChronicleEntry(
    entryId: number,
    data: { description?: string; entry_type?: string; is_defining?: boolean },
  ): Promise<ChronicleEntry> {
    return this.request<ChronicleEntry>(`/api/chronicles/${entryId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteChronicleEntry(entryId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/chronicles/${entryId}`, {
      method: 'DELETE',
    });
  }

  // --- Locations & Lorebook ---

  async getWorldLocations(worldId: number): Promise<WorldLocation[]> {
    return this.request<WorldLocation[]>(`/api/worlds/${worldId}/locations`);
  }

  async getLocationLorebook(
    worldId: number,
    locationName: string,
    storyId?: number,
    branchId?: number,
  ): Promise<LorebookEntry[]> {
    const params = new URLSearchParams();
    if (storyId !== undefined) params.set('story_id', String(storyId));
    if (branchId !== undefined) params.set('branch_id', String(branchId));
    const qs = params.toString();
    return this.request<LorebookEntry[]>(
      `/api/worlds/${worldId}/locations/${encodeURIComponent(locationName)}/lorebook${qs ? `?${qs}` : ''}`
    );
  }

  async updateLorebookEntry(
    entryId: number,
    data: { location_name?: string; event_description?: string },
  ): Promise<LorebookEntry> {
    return this.request<LorebookEntry>(`/api/lorebook/${entryId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteLorebookEntry(entryId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/lorebook/${entryId}`, {
      method: 'DELETE',
    });
  }
}
