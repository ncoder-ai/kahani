/**
 * Image Generation API module
 *
 * Handles AI-powered image generation using ComfyUI.
 */

import { BaseApiClient } from './base';

// ============================================================================
// Types
// ============================================================================

export interface ServerStatus {
  online: boolean;
  queue_running: number;
  queue_pending: number;
  gpu_memory: Record<string, {
    name: string;
    type: string;
    vram_total: number;
    vram_free: number;
    torch_vram_total: number;
    torch_vram_free: number;
  }>;
  error?: string;
}

export interface AvailableModels {
  checkpoints: string[];
  samplers: string[];
  schedulers: string[];
}

export interface StylePreset {
  name: string;
  description: string;
  prompt_suffix: string;
  negative_prompt: string;
}

export interface StylePresetsResponse {
  presets: Record<string, StylePreset>;
}

export interface GeneratePortraitRequest {
  style?: string;
  checkpoint?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg_scale?: number;
}

export interface GenerateSceneImageRequest {
  style?: string;
  checkpoint?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg_scale?: number;
  custom_prompt?: string;
}

export interface GenerateCharacterImageRequest {
  character_id: number;
  style?: string;
  checkpoint?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg_scale?: number;
  custom_prompt?: string;
}

export interface GenerationJobResponse {
  job_id: string;
  status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  image_id?: number;
  error?: string;
  prompt?: string;
}

export interface GeneratedImage {
  id: number;
  story_id: number;
  branch_id?: number;
  scene_id?: number;
  character_id?: number;
  image_type: 'scene' | 'character_portrait';
  file_path: string;
  thumbnail_path?: string;
  prompt?: string;
  width?: number;
  height?: number;
  created_at: string;
}

export interface ImageGenerationSettings {
  enabled: boolean;
  comfyui_server_url: string;
  comfyui_api_key: string;
  comfyui_checkpoint: string;
  comfyui_model_type: string;
  width: number;
  height: number;
  steps: number;
  cfg_scale: number;
  default_style: string;
  use_extraction_llm_for_prompts: boolean;
}

// ============================================================================
// API Client
// ============================================================================

export class ImageGenerationApi extends BaseApiClient {
  /**
   * Check if the user's ComfyUI server is online and get status info
   */
  async getServerStatus(): Promise<ServerStatus> {
    return this.request<ServerStatus>('/api/image-generation/server-status');
  }

  /**
   * Get available models (checkpoints, samplers, schedulers) from ComfyUI
   */
  async getAvailableModels(): Promise<AvailableModels> {
    return this.request<AvailableModels>('/api/image-generation/available-models');
  }

  /**
   * Get available style presets
   */
  async getStylePresets(): Promise<StylePresetsResponse> {
    return this.request<StylePresetsResponse>('/api/image-generation/style-presets');
  }

  /**
   * Generate a portrait for a character
   */
  async generateCharacterPortrait(
    characterId: number,
    options: GeneratePortraitRequest = {}
  ): Promise<GenerationJobResponse> {
    return this.request<GenerationJobResponse>(
      `/api/image-generation/character/${characterId}/portrait`,
      {
        method: 'POST',
        body: JSON.stringify(options),
      }
    );
  }

  /**
   * Upload an existing image as a character's portrait
   */
  async uploadCharacterPortrait(
    characterId: number,
    file: File
  ): Promise<{ id: number; image_id?: number; file_path: string; message: string }> {
    const formData = new FormData();
    formData.append('file', file);

    // Ensure we have the base URL
    if (!this.baseURL) {
      await this.initialize();
    }

    // Use fetch directly for multipart form data
    const response = await fetch(
      `${this.baseURL}/api/image-generation/character/${characterId}/portrait/upload`,
      {
        method: 'POST',
        body: formData,
        headers: {
          'Authorization': `Bearer ${this.token}`,
        },
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Failed to upload portrait');
    }

    return response.json();
  }

  /**
   * Delete a character's portrait
   */
  async deleteCharacterPortrait(characterId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      `/api/image-generation/character/${characterId}/portrait`,
      {
        method: 'DELETE',
      }
    );
  }

  /**
   * Generate an image for a scene
   */
  async generateSceneImage(
    sceneId: number,
    options: GenerateSceneImageRequest = {}
  ): Promise<GenerationJobResponse> {
    return this.request<GenerationJobResponse>(
      `/api/image-generation/scene/${sceneId}`,
      {
        method: 'POST',
        body: JSON.stringify(options),
      }
    );
  }

  /**
   * Generate an in-context image for a character in a scene
   */
  async generateCharacterImage(
    sceneId: number,
    options: GenerateCharacterImageRequest
  ): Promise<GenerationJobResponse> {
    return this.request<GenerationJobResponse>(
      `/api/image-generation/scene/${sceneId}/character`,
      {
        method: 'POST',
        body: JSON.stringify(options),
      }
    );
  }

  /**
   * Get all generated images for a story
   */
  async getStoryImages(
    storyId: number,
    filters?: {
      scene_id?: number;
      character_id?: number;
      image_type?: 'scene' | 'character_portrait';
    }
  ): Promise<GeneratedImage[]> {
    const params = new URLSearchParams();
    if (filters?.scene_id) params.append('scene_id', filters.scene_id.toString());
    if (filters?.character_id) params.append('character_id', filters.character_id.toString());
    if (filters?.image_type) params.append('image_type', filters.image_type);

    const queryString = params.toString();
    const url = `/api/image-generation/story/${storyId}/images${queryString ? `?${queryString}` : ''}`;

    return this.request<GeneratedImage[]>(url);
  }

  /**
   * Get character portraits for all characters in a story
   * This fetches portraits regardless of which story_id they were saved under
   */
  async getStoryPortraits(storyId: number): Promise<GeneratedImage[]> {
    return this.request<GeneratedImage[]>(`/api/image-generation/story/${storyId}/portraits`);
  }

  /**
   * Get the URL for an image file (metadata endpoint)
   */
  getImageUrl(imageId: number): string {
    return `/api/image-generation/images/${imageId}`;
  }

  /**
   * Get the full URL for an image file (for use in <img src>)
   * This returns the complete URL including the backend base URL
   */
  async getImageFileUrl(imageId: number): Promise<string> {
    if (!this.baseURL) {
      await this.initialize();
    }
    return `${this.baseURL}/api/image-generation/images/${imageId}/file`;
  }

  /**
   * Get the full URL for an image file synchronously
   * Falls back to relative URL if base URL not available
   */
  getImageFileUrlSync(imageId: number): string {
    if (this.baseURL) {
      return `${this.baseURL}/api/image-generation/images/${imageId}/file`;
    }
    // Fallback - this may not work if frontend and backend are on different ports
    return `/api/image-generation/images/${imageId}/file`;
  }

  /**
   * Delete a generated image
   */
  async deleteImage(imageId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      `/api/image-generation/images/${imageId}`,
      {
        method: 'DELETE',
      }
    );
  }

  /**
   * Get job status for a generation job
   */
  async getJobStatus(jobId: string): Promise<GenerationJobResponse> {
    return this.request<GenerationJobResponse>(
      `/api/image-generation/status/${jobId}`
    );
  }

  /**
   * Get details of a generated image
   */
  async getImage(imageId: number): Promise<GeneratedImage> {
    return this.request<GeneratedImage>(
      `/api/image-generation/images/${imageId}`
    );
  }
}

// Type aliases for convenience
export type ImageGenServerStatus = ServerStatus;
export type ImageGenAvailableModels = AvailableModels;
