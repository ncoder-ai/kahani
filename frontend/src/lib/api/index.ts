/**
 * Unified API Client
 *
 * This module provides a unified API client that composes all domain-specific
 * API modules while maintaining backward compatibility with the existing apiClient usage.
 *
 * Usage:
 *   // Legacy usage (backward compatible)
 *   import apiClient from '@/lib/api';
 *   import { apiClient } from '@/lib/api';
 *
 *   // New modular usage (recommended for new code)
 *   import { authApi, charactersApi } from '@/lib/api';
 *
 * The unified apiClient exposes all methods from the original api.ts file.
 * Domain-specific clients (authApi, etc.) provide typed, focused interfaces.
 */

// Import domain clients for composition
import { AuthApi } from './auth';
import { SettingsApi } from './settings';
import { CharactersApi } from './characters';
import { BranchesApi } from './branches';
import { AdminApi } from './admin';
import { WritingPresetsApi } from './writing-presets';
import { ImageGenerationApi } from './imageGeneration';
import { WorldsApi } from './worlds';
import { RoleplayApi } from './roleplay';
import LegacyApiClient from '../api';

// Create singleton instances of domain clients
const authApiInstance = new AuthApi();
const settingsApiInstance = new SettingsApi();
const charactersApiInstance = new CharactersApi();
const branchesApiInstance = new BranchesApi();
const adminApiInstance = new AdminApi();
const writingPresetsApiInstance = new WritingPresetsApi();
const imageGenerationApiInstance = new ImageGenerationApi();
const worldsApiInstance = new WorldsApi();
const roleplayApiInstance = new RoleplayApi();

// Re-export everything from the legacy api.ts for backward compatibility
export * from '../api';

// Export domain-specific API classes
export { AuthApi } from './auth';
export { SettingsApi } from './settings';
export { CharactersApi } from './characters';
export { BranchesApi } from './branches';
export { AdminApi } from './admin';
export { WritingPresetsApi } from './writing-presets';
export { ImageGenerationApi } from './imageGeneration';
export { WorldsApi } from './worlds';
export { RoleplayApi } from './roleplay';
export type {
  RoleplayCreateData,
  RoleplayCreateResponse,
  RoleplayListItem,
  RoleplayDetail,
  RoleplayCharacter,
  RoleplayTurn,
  RoleplaySettings,
  RoleplayCharacterConfig,
  CharacterStoryEntry,
  StreamCallbacks as RoleplayStreamCallbacks,
} from './roleplay';

// Export types from imageGeneration
export type {
  ServerStatus as ImageGenServerStatus,
  AvailableModels as ImageGenAvailableModels,
  StylePreset,
  StylePresetsResponse,
  GeneratePortraitRequest,
  GenerateSceneImageRequest,
  GenerateCharacterImageRequest,
  GenerationJobResponse,
  GeneratedImage,
  ImageGenerationSettings,
} from './imageGeneration';

// Re-export base utilities
export { circuitBreaker } from './base';

// Export singleton instances
export const authApi = authApiInstance;
export const settingsApi = settingsApiInstance;
export const charactersApi = charactersApiInstance;
export const branchesApi = branchesApiInstance;
export const adminApi = adminApiInstance;
export const writingPresetsApi = writingPresetsApiInstance;
export const imageGenerationApi = imageGenerationApiInstance;
export const worldsApi = worldsApiInstance;
export const roleplayApi = roleplayApiInstance;

// Export legacy client
export const apiClient = LegacyApiClient;
export default LegacyApiClient;
