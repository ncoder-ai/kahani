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

// Re-export domain-specific API classes for direct usage
export { AuthApi } from './auth';
export { SettingsApi } from './settings';
export { CharactersApi } from './characters';
export { BranchesApi } from './branches';
export { AdminApi } from './admin';
export { WritingPresetsApi } from './writing-presets';

// Re-export base utilities (not in legacy api.ts)
export { circuitBreaker } from './base';

// Import domain clients for composition
import { AuthApi } from './auth';
import { SettingsApi } from './settings';
import { CharactersApi } from './characters';
import { BranchesApi } from './branches';
import { AdminApi } from './admin';
import { WritingPresetsApi } from './writing-presets';

// Create singleton instances of domain clients
export const authApi = new AuthApi();
export const settingsApi = new SettingsApi();
export const charactersApi = new CharactersApi();
export const branchesApi = new BranchesApi();
export const adminApi = new AdminApi();
export const writingPresetsApi = new WritingPresetsApi();

/**
 * For backward compatibility, we re-export the original ApiClient
 * from the legacy api.ts file. This allows gradual migration.
 *
 * New code should prefer using domain-specific clients:
 *   import { authApi, charactersApi } from '@/lib/api';
 *
 * Legacy code can continue using:
 *   import apiClient from '@/lib/api';
 *   // or
 *   import { apiClient } from '@/lib/api';
 */

// Re-export everything from the legacy api.ts for backward compatibility
// This includes ApiClient, apiClient (default), and all type exports
export * from '../api';
import LegacyApiClient from '../api';
export const apiClient = LegacyApiClient;
export default LegacyApiClient;
