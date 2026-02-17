// API configuration and utilities

import { getApiBaseUrl as getApiBaseUrlFromConfig, getApiBaseUrlSync as getApiBaseUrlSyncFromConfig } from './apiUrl';
import { syncTokenToModularClients } from './api/base';

/**
 * Normalize API URL by adding default port if missing
 * @param url The API URL to normalize
 * @returns Normalized URL with port if it was missing
 */
function normalizeApiUrl(url: string): string {
  try {
    const urlObj = new URL(url);
    // If no port specified and it's HTTP, add default port 9876
    if (!urlObj.port && urlObj.protocol === 'http:') {
      urlObj.port = '9876';
    }
    // Remove trailing slash from origin (URL.href adds it when pathname is empty)
    let normalized = urlObj.href;
    if (normalized.endsWith('/')) {
      normalized = normalized.slice(0, -1);
    }
    return normalized;
  } catch {
    // Return as-is if invalid URL (let fetch handle the error)
    return url;
  }
}

/**
 * Simple Circuit Breaker to prevent hammering an unresponsive backend
 */
class CircuitBreaker {
  private failures = 0;
  private lastFailureTime = 0;
  private isOpen = false;
  
  // Configuration
  private readonly failureThreshold = 5;  // Open circuit after 5 consecutive failures
  private readonly resetTimeMs = 30000;   // Try again after 30 seconds
  
  /**
   * Check if circuit is open (should skip request)
   */
  shouldBlock(): boolean {
    if (!this.isOpen) return false;
    
    // Check if enough time has passed to try again
    if (Date.now() - this.lastFailureTime > this.resetTimeMs) {
      this.isOpen = false;
      this.failures = 0;
      console.log('[CircuitBreaker] Circuit closed, allowing requests');
      return false;
    }
    
    return true;
  }
  
  /**
   * Record a successful request
   */
  recordSuccess(): void {
    this.failures = 0;
    if (this.isOpen) {
      this.isOpen = false;
      console.log('[CircuitBreaker] Circuit closed after successful request');
    }
  }
  
  /**
   * Record a failed request
   */
  recordFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();
    
    if (this.failures >= this.failureThreshold && !this.isOpen) {
      this.isOpen = true;
      console.warn(`[CircuitBreaker] Circuit opened after ${this.failures} failures. Will retry in ${this.resetTimeMs / 1000}s`);
    }
  }
  
  /**
   * Get time until circuit resets (for user feedback)
   */
  getTimeUntilReset(): number {
    if (!this.isOpen) return 0;
    const elapsed = Date.now() - this.lastFailureTime;
    return Math.max(0, this.resetTimeMs - elapsed);
  }
}

// Global circuit breaker instance
const circuitBreaker = new CircuitBreaker();

/**
 * Error types for better error handling
 */
export enum ApiErrorType {
  NETWORK_ERROR = 'NETWORK_ERROR',
  TIMEOUT = 'TIMEOUT',
  SERVER_ERROR = 'SERVER_ERROR',
  AUTH_ERROR = 'AUTH_ERROR',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  CIRCUIT_OPEN = 'CIRCUIT_OPEN',
  UNKNOWN = 'UNKNOWN'
}

/**
 * Voice Style interfaces
 */
export interface VoiceStyle {
  preset?: string;  // Preset ID like "indian_english", "formal_noble", or "custom"
  formality?: 'formal' | 'casual' | 'streetwise' | 'archaic';
  vocabulary?: 'simple' | 'average' | 'sophisticated' | 'technical';
  tone?: 'cheerful' | 'sarcastic' | 'gruff' | 'nervous' | 'calm' | 'dramatic' | 'deadpan';
  profanity?: 'none' | 'mild' | 'moderate' | 'heavy';
  speech_quirks?: string;
  primary_language?: string;  // Primary language for dialogue (default: english)
  secondary_language?: string;  // Language to mix in
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

/**
 * Story Arc interfaces
 */
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

/**
 * Chapter Plot interfaces (from brainstorming)
 */
export interface CharacterArc {
  character_name: string;
  name?: string; // Alternative field for backwards compatibility
  development: string;
  dynamics?: string; // Alternative field for backwards compatibility
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
  _characterIds?: number[];  // Character IDs to add to the chapter (from character review)
}

export interface StructuredElements {
  overview: string;
  characters: CharacterArc[];
  tone: string;
  key_events: string[];
  ending: string;
}

// Suggested elements from AI - all fields optional since AI may only suggest some
export interface SuggestedElements {
  overview?: string;
  characters?: string;  // AI returns as string, not CharacterArc[]
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

/**
 * Custom API Error with additional context
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly type: ApiErrorType,
    public readonly statusCode?: number,
    public readonly retryable: boolean = false
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Check if an error is retryable
 */
function isRetryableError(error: unknown, statusCode?: number): boolean {
  // Network errors are retryable
  if (error instanceof TypeError && error.message === 'Load failed') {
    return true;
  }
  
  // Timeout errors are retryable
  if (error instanceof Error && error.name === 'AbortError') {
    return true;
  }
  
  // 5xx server errors are retryable
  if (statusCode && statusCode >= 500) {
    return true;
  }
  
  // 429 Too Many Requests is retryable
  if (statusCode === 429) {
    return true;
  }
  
  return false;
}

// Runtime API URL detection - uses config API
async function getApiBaseUrl(): Promise<string> {
  // First check environment variable
  if (process.env.NEXT_PUBLIC_API_URL) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }
  
  // Use config API to get backend port
  try {
    const url = await getApiBaseUrlFromConfig();
    // Always normalize to ensure port is added if missing
    return normalizeApiUrl(url);
  } catch (error) {
    // If config API unavailable, this is a critical error
    throw new Error(`Unable to determine API URL: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

// Synchronous version for backward compatibility (uses cached port)
function getApiBaseUrlSync(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }
  const url = getApiBaseUrlSyncFromConfig();
  // Always normalize to ensure port is added if missing
  return normalizeApiUrl(url);
}

class ApiClient {
  private baseURL: string;
  private token: string | null = null;
  private cachedTimeoutMs: number | null = null; // Cache user timeout in milliseconds
  private isFetchingTimeout: boolean = false; // Flag to prevent recursion

  constructor(baseURL?: string) {
    // Don't require baseURL immediately - allow lazy initialization
    // This allows ApiClient to be created before config is loaded
    if (baseURL) {
      this.baseURL = baseURL;
    } else {
      // Try to get sync, but don't throw if not available yet
      // Will be initialized via initialize() method
      try {
        this.baseURL = getApiBaseUrlSync();
      } catch {
        // Config not loaded yet - will be set via initialize()
        this.baseURL = '';
      }
    }
    this.loadToken();
  }
  
  // Method to update base URL after config is loaded
  async initialize(): Promise<void> {
    // Try to get from config API with timeout
    try {
      // Add a timeout wrapper to prevent hanging
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('API URL initialization timeout after 10 seconds')), 10000);
      });
      
      this.baseURL = await Promise.race([
        getApiBaseUrl(),
        timeoutPromise
      ]);
    } catch (error) {
      console.error('Failed to initialize API URL from config:', error);
      // For login/register, we can try to continue with fallback
      // But for other operations, we should fail
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      throw new Error(`Failed to connect to backend: ${errorMessage}. Please ensure the backend server is running.`);
    }
  }

  /**
   * Load token from auth store (single source of truth)
   * Called on initialization and when store changes
   */
  private loadToken() {
    if (typeof window !== 'undefined') {
      // Try to get token from Zustand persisted store
      try {
        const authStorage = localStorage.getItem('auth-storage');
        if (authStorage) {
          const parsed = JSON.parse(authStorage);
          this.token = parsed.state?.token || null;
        }
      } catch (e) {
        console.warn('[API] Failed to load token from auth store:', e);
        this.token = null;
      }
    }
  }

  private async handleTokenRefresh() {
    if (typeof window !== 'undefined') {
      // Import the auth store dynamically to avoid circular dependencies
      const { useAuthStore } = await import('@/store');
      const refreshAccessToken = useAuthStore.getState().refreshAccessToken;
      return await refreshAccessToken();
    }
    return false;
  }

  /**
   * Set token in API client memory
   * Note: Token persistence is handled by the auth store, not here
   */
  setToken(token: string) {
    this.token = token;
    syncTokenToModularClients(token);
  }

  /**
   * Remove token from API client memory
   * Note: Token persistence is handled by the auth store, not here
   */
  removeToken() {
    this.token = null;
    this.cachedTimeoutMs = null;
    syncTokenToModularClients(null);
  }

  /**
   * Get request timeout in milliseconds based on user settings
   * Fetches user settings if not cached, with fallback to 300 seconds (5 minutes)
   * For unauthenticated requests (login, register), uses a shorter default timeout
   * Prevents recursion when called from within getUserSettings()
   */
  private async getRequestTimeout(endpoint?: string): Promise<number> {
    // For unauthenticated endpoints, use a shorter default timeout
    const isAuthEndpoint = endpoint && (endpoint.includes('/api/auth/login') || endpoint.includes('/api/auth/register'));
    
    if (isAuthEndpoint) {
      // Use 30 seconds for login/register (no need to fetch settings)
      return 30000; // 30 seconds in milliseconds
    }

    // Return cached value if available
    if (this.cachedTimeoutMs !== null) {
      return this.cachedTimeoutMs;
    }

    // Only try to fetch user settings if we have a token
    if (!this.token) {
      // No token - use default timeout for unauthenticated requests
      return 30000; // 30 seconds in milliseconds
    }

    // Prevent recursion: if we're already fetching timeout (from within getUserSettings), use default
    if (this.isFetchingTimeout) {
      return 300000; // 300 seconds in milliseconds (default)
    }

    // Prevent recursion: if this is a settings endpoint, use default timeout
    if (endpoint && endpoint.includes('/api/settings')) {
      return 300000; // 300 seconds in milliseconds (default)
    }

    // Try to fetch user settings to get timeout_total
    this.isFetchingTimeout = true;
    try {
      const settingsResponse = await this.getUserSettings();
      const timeoutTotal = settingsResponse?.settings?.llm_settings?.timeout_total;
      
      if (timeoutTotal && typeof timeoutTotal === 'number' && timeoutTotal > 0) {
        // Add 10 second buffer for network overhead, convert to milliseconds
        this.cachedTimeoutMs = (timeoutTotal + 10) * 1000;
        this.isFetchingTimeout = false;
        return this.cachedTimeoutMs;
      }
    } catch (error) {
      console.warn('[API] Failed to fetch user settings for timeout, using default:', error);
    } finally {
      this.isFetchingTimeout = false;
    }

    // Fallback to 300 seconds (5 minutes) if settings unavailable or invalid
    this.cachedTimeoutMs = 300000; // 300 seconds in milliseconds
    return this.cachedTimeoutMs;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}, retryCount = 0): Promise<T> {
    const maxRetries = 3;
    const baseDelayMs = 1000;
    
    // Check circuit breaker first
    if (circuitBreaker.shouldBlock()) {
      const resetTime = Math.ceil(circuitBreaker.getTimeUntilReset() / 1000);
      throw new ApiError(
        `Server temporarily unavailable. Please try again in ${resetTime} seconds.`,
        ApiErrorType.CIRCUIT_OPEN,
        undefined,
        false
      );
    }
    
    // Ensure baseURL is initialized before making request
    if (!this.baseURL) {
      try {
        await this.initialize();
      } catch (initError) {
        const errorMsg = initError instanceof Error ? initError.message : 'Unknown error';
        throw new ApiError(
          `Failed to initialize API client: ${errorMsg}. Please ensure the backend server is running.`,
          ApiErrorType.NETWORK_ERROR,
          undefined,
          false
        );
      }
    }
    
    // Validate baseURL before constructing URL
    if (!this.baseURL || this.baseURL.trim() === '') {
      throw new ApiError(
        'API base URL is not set. Please ensure the backend server is running and accessible.',
        ApiErrorType.NETWORK_ERROR,
        undefined,
        false
      );
    }
    
    const url = `${this.baseURL}${endpoint}`;
    const isFormData = (typeof FormData !== 'undefined') && (options.body instanceof FormData);

    const headers: Record<string, string> = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers as Record<string, string>,
    };

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    // Get timeout from user settings (with fallback)
    const requestTimeoutMs = await this.getRequestTimeout(endpoint);

    // Add timeout to prevent infinite hanging
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), requestTimeoutMs);

    try {
      const response = await fetch(url, { 
        ...options, 
        headers,
        signal: controller.signal 
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        if (response.status === 401) {
          // Skip token refresh for login endpoint to avoid retry loops
          if (endpoint.includes('/api/auth/login')) {
            this.removeToken();
            throw new ApiError(
              'Authentication failed. Please check your credentials.',
              ApiErrorType.AUTH_ERROR,
              401,
              false
            );
          }
          
          const refreshSuccess = await this.handleTokenRefresh();
          if (refreshSuccess) {
            // Retry the request with the new token (with timeout)
            const retryController = new AbortController();
            const retryTimeoutId = setTimeout(() => retryController.abort(), requestTimeoutMs);
            try {
              const retryResponse = await fetch(url, { 
                ...options, 
                headers: { ...headers, Authorization: `Bearer ${this.token}` },
                signal: retryController.signal
              });
              clearTimeout(retryTimeoutId);
              if (retryResponse.ok) {
                circuitBreaker.recordSuccess();
                const retryData = await retryResponse.json();
                return retryData;
              }
            } catch (retryError) {
              clearTimeout(retryTimeoutId);
              if (retryError instanceof Error && retryError.name === 'AbortError') {
                throw new ApiError(
                  'Request timed out. Please check your connection and try again.',
                  ApiErrorType.TIMEOUT,
                  undefined,
                  true
                );
              }
              throw retryError;
            }
          }
          
          this.removeToken();
          if (typeof window !== 'undefined') {
            window.location.href = '/login';
          }
          throw new ApiError('Authentication required', ApiErrorType.AUTH_ERROR, 401, false);
        }

        // Check if error is retryable (5xx errors)
        if (isRetryableError(null, response.status) && retryCount < maxRetries) {
          circuitBreaker.recordFailure();
          const delay = baseDelayMs * Math.pow(2, retryCount);
          console.warn(`[API] Server error ${response.status}, retrying in ${delay}ms (attempt ${retryCount + 1}/${maxRetries})`);
          await sleep(delay);
          return this.request<T>(endpoint, options, retryCount + 1);
        }

        let errorData: any;
        try {
          errorData = await response.json();
        } catch (e) {
          console.error('[API] Failed to parse error response:', e);
          circuitBreaker.recordFailure();
          throw new ApiError(
            `Server error (${response.status}). Please try again later.`,
            ApiErrorType.SERVER_ERROR,
            response.status,
            response.status >= 500
          );
        }

        if (errorData.detail && Array.isArray(errorData.detail)) {
          const errorMessages = errorData.detail.map((err: any) => {
            const location = err.loc ? err.loc.slice(1).join(' -> ') : 'Field';
            return `${location}: ${err.msg}`;
          }).join(', ');
          throw new ApiError(errorMessages, ApiErrorType.VALIDATION_ERROR, response.status, false);
        }

        const errorMessage = errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`;
        const errorType = response.status >= 500 ? ApiErrorType.SERVER_ERROR : ApiErrorType.UNKNOWN;
        throw new ApiError(
          typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage),
          errorType,
          response.status,
          response.status >= 500
        );
      }

      // Success - record it and return data
      circuitBreaker.recordSuccess();
      const data = await response.json();
      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      
      // If it's already an ApiError, just rethrow
      if (error instanceof ApiError) {
        throw error;
      }
      
      if (error instanceof Error) {
        // Handle timeout specifically
        if (error.name === 'AbortError') {
          circuitBreaker.recordFailure();
          const timeoutSeconds = Math.round(requestTimeoutMs / 1000);
          console.error(`[API] Request timed out after ${timeoutSeconds} seconds`);
          
          // Retry timeout errors
          if (retryCount < maxRetries) {
            const delay = baseDelayMs * Math.pow(2, retryCount);
            console.warn(`[API] Retrying after timeout in ${delay}ms (attempt ${retryCount + 1}/${maxRetries})`);
            await sleep(delay);
            return this.request<T>(endpoint, options, retryCount + 1);
          }
          
          throw new ApiError(
            `Request timed out after ${timeoutSeconds} seconds. The server may be busy or unresponsive.`,
            ApiErrorType.TIMEOUT,
            undefined,
            true
          );
        }
        
        // Handle network errors ("Load failed" in Safari, "Failed to fetch" in Chrome)
        if (error.message === 'Load failed' || error.message === 'Failed to fetch' || error instanceof TypeError) {
          circuitBreaker.recordFailure();
          console.error('[API] Network error:', error.message);
          
          // Retry network errors
          if (retryCount < maxRetries) {
            const delay = baseDelayMs * Math.pow(2, retryCount);
            console.warn(`[API] Retrying after network error in ${delay}ms (attempt ${retryCount + 1}/${maxRetries})`);
            await sleep(delay);
            return this.request<T>(endpoint, options, retryCount + 1);
          }
          
          throw new ApiError(
            'Unable to connect to the server. Please check your connection and try again.',
            ApiErrorType.NETWORK_ERROR,
            undefined,
            true
          );
        }
        
        console.error('[API] Request failed:', error.message);
        throw new ApiError(error.message, ApiErrorType.UNKNOWN, undefined, false);
      }
      
      console.error('[API] Request failed with unknown error:', error);
      throw new ApiError('An unexpected error occurred', ApiErrorType.UNKNOWN, undefined, false);
    }
  }

  // Authentication
  async login(identifier: string, password: string, rememberMe: boolean = false) {
    return this.request<{
      access_token: string;
      token_type: string;
      refresh_token?: string;
      user: any;
    }>(`/api/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ identifier, password, remember_me: rememberMe }),
    });
  }

  async refreshToken(refreshToken: string) {
    return this.request<{
      access_token: string;
      token_type: string;
    }>(`/api/auth/refresh`, {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  async ssoCheck() {
    // SSO check MUST use relative URL to go through the reverse proxy (NPM/Authelia)
    // so that the auth headers are added. Using this.baseURL would bypass the proxy.
    const response = await fetch('/api/auth/sso-check', {
      method: 'GET',
      credentials: 'include',  // Include cookies for Authelia session
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`SSO check failed: ${response.status}`);
    }

    return response.json() as Promise<{
      sso_enabled: boolean;
      authenticated?: boolean;
      user_exists?: boolean;
      active?: boolean;
      approved?: boolean;
      access_token?: string;
      token_type?: string;
      user?: any;
      message?: string;
    }>;
  }

  async register(data: { email: string; username: string; password: string; display_name?: string; }) {
    return this.request<{ access_token: string; token_type: string; user: any; }>(`/api/auth/register`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getCurrentUser() {
    return this.request<any>(`/api/auth/me`);
  }

  // User settings
  async getUserSettings() {
    return this.request<{ settings: any }>(`/api/settings/`);
  }

  // Settings
  async getLastAccessedStory() {
    // New path under settings API
    return this.request<{ auto_open_last_story: boolean; last_accessed_story_id?: number; }>(`/api/settings/last-story`);
  }

  // Text Completion Templates
  async getTextCompletionPresets() {
    return this.request<{ presets: Array<{ key: string; name: string; description: string; compatible_models: string[] }> }>(`/api/settings/text-completion/presets`);
  }

  async getPresetTemplate(presetName: string) {
    return this.request<{ template: any }>(`/api/settings/text-completion/template/${presetName}`);
  }

  async testTemplateRender(template: any, testSystem: string, testUser: string) {
    return this.request<{ valid: boolean; error: string | null; rendered_prompt: string | null; prompt_length?: number }>(`/api/settings/text-completion/test-render`, {
      method: 'POST',
      body: JSON.stringify({ template, test_system: testSystem, test_user: testUser })
    });
  }

  // Stories
  async getStories(skip = 0, limit = 10) {
    return this.request<any[]>(`/api/stories/?skip=${skip}&limit=${limit}`);
  }

  async getStory(id: number, branchId?: number, chapterId?: number) {
    const params = new URLSearchParams();
    if (branchId) params.append('branch_id', branchId.toString());
    if (chapterId) params.append('chapter_id', chapterId.toString());
    const queryString = params.toString();
    return this.request<any>(`/api/stories/${id}${queryString ? '?' + queryString : ''}`);
  }

  async createStory(data: { title: string; description?: string; genre?: string; tone?: string; world_setting?: string; initial_premise?: string; content_rating?: string; world_id?: number; timeline_order?: number; }) {
    return this.request<any>(`/api/stories/`, { method: 'POST', body: JSON.stringify(data) });
  }

  async updateStory(id: number, data: { title?: string; description?: string; genre?: string; tone?: string; world_setting?: string; initial_premise?: string; scenario?: string; content_rating?: string; interaction_types?: string[]; plot_check_mode?: '1' | '3' | 'all'; world_id?: number; }) {
    return this.request<any>(`/api/stories/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async getInteractionPresets() {
    return this.request<Record<string, { name: string; description: string; types: string[]; }>>(`/api/stories/interaction-presets`);
  }

  async extractInteractionsRetroactively(storyId: number) {
    return this.request<{ 
      message: string; 
      story_id: number; 
      scene_count: number; 
      batch_size: number;
      num_batches: number;
      interaction_types: string[];
      status: string; 
    }>(`/api/stories/${storyId}/extract-interactions`, { method: 'POST' });
  }

  async getStoryInteractions(storyId: number, branchId?: number) {
    const params = branchId !== undefined ? `?branch_id=${branchId}` : '';
    return this.request<{
      story_id: number;
      interaction_types_configured: string[];
      interactions: Array<{
        id: number;
        interaction_type: string;
        character_a: string;
        character_b: string;
        first_occurrence_scene: number;
        description: string | null;
      }>;
      interactions_not_occurred: string[];
      total_interactions: number;
      total_scenes: number;
    }>(`/api/stories/${storyId}/interactions${params}`);
  }

  async getExtractionProgress(storyId: number) {
    return this.request<{
      in_progress: boolean;
      batches_processed: number;
      total_batches: number;
      interactions_found: number;
    }>(`/api/stories/${storyId}/extraction-progress`);
  }

  async deleteInteraction(storyId: number, interactionId: number) {
    return this.request<{
      message: string;
      deleted_id: number;
    }>(`/api/stories/${storyId}/interactions/${interactionId}`, { method: 'DELETE' });
  }

  // Entity States API
  async getEntityStates(storyId: number, branchId?: number) {
    const params = branchId !== undefined ? `?branch_id=${branchId}` : '';
    return this.request<{
      story_id: number;
      branch_id: number | null;
      character_states: Array<{
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
      }>;
      location_states: Array<{
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
      }>;
      object_states: Array<{
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
      }>;
      counts: {
        characters: number;
        locations: number;
        objects: number;
      };
    }>(`/api/stories/${storyId}/entity-states${params}`);
  }

  async deleteEntityState(storyId: number, type: 'characters' | 'locations' | 'objects', stateId: number) {
    return this.request<{
      message: string;
      deleted_id: number;
    }>(`/api/stories/${storyId}/entity-states/${type}/${stateId}`, { method: 'DELETE' });
  }

  async updateCharacterState(storyId: number, stateId: number, data: {
    current_location?: string | null;
    current_position?: string | null;
    items_in_hand?: string[];
    physical_condition?: string | null;
    appearance?: string | null;
    possessions?: string[];
    emotional_state?: string | null;
    current_goal?: string | null;
    active_conflicts?: string[];
    knowledge?: string[];
    secrets?: string[];
    relationships?: Record<string, string>;
    arc_stage?: string | null;
    arc_progress?: number | null;
    recent_decisions?: string[];
    recent_actions?: string[];
  }) {
    return this.request<{
      message: string;
      state: Record<string, unknown>;
    }>(`/api/stories/${storyId}/entity-states/characters/${stateId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async updateLocationState(storyId: number, stateId: number, data: {
    location_name?: string;
    condition?: string | null;
    atmosphere?: string | null;
    notable_features?: string[];
    current_occupants?: string[];
    significant_events?: string[];
    time_of_day?: string | null;
    weather?: string | null;
  }) {
    return this.request<{
      message: string;
      state: Record<string, unknown>;
    }>(`/api/stories/${storyId}/entity-states/locations/${stateId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async updateObjectState(storyId: number, stateId: number, data: {
    object_name?: string;
    condition?: string | null;
    current_location?: string | null;
    current_owner_id?: number | null;
    significance?: string | null;
    object_type?: string | null;
    powers?: string[];
    limitations?: string[];
    origin?: string | null;
    previous_owners?: string[];
    recent_events?: string[];
  }) {
    return this.request<{
      message: string;
      state: Record<string, unknown>;
    }>(`/api/stories/${storyId}/entity-states/objects/${stateId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async generateSceneStreaming(
    storyId: number,
    customPrompt = '',
    userContent?: string,
    contentMode: 'ai_generate' | 'user_scene' | 'user_prompt' = 'ai_generate',
    onChunk?: (chunk: string) => void,
    onComplete?: (sceneId: number, variantId: number, choices: any[], autoPlay?: { enabled: boolean; session_id: string; scene_id: number }, multiGen?: { isMultiGeneration: boolean; totalVariants: number; variants: any[] }, chapterId?: number | null) => void,
    onError?: (error: string) => void,
    onAutoPlayReady?: (sessionId: string, sceneId: number) => void,
    onExtractionStatus?: (status: 'extracting' | 'complete' | 'error', message: string) => void,
    isConcluding?: boolean,
    abortSignal?: AbortSignal,
    // Thinking/reasoning callbacks
    onThinkingStart?: () => void,
    onThinkingChunk?: (chunk: string) => void,
    onThinkingEnd?: (totalChars: number) => void,
    onContradictionCheck?: (data: { status: string; contradictions?: Array<{
      id: number; type: string; character_name: string | null;
      previous_value: string | null; current_value: string | null;
      severity: string; scene_sequence: number;
    }>; auto_regenerating?: boolean }) => void
  ) {
    let fullStreamedContent = '';  // Track all streamed content for verification
    let receivedComplete = false;  // Track if we received the complete event
    const formData = new FormData();
    formData.append('custom_prompt', customPrompt);
    if (userContent) {
      formData.append('user_content', userContent);
    }
    formData.append('content_mode', contentMode);
    formData.append('is_concluding', isConcluding ? 'true' : 'false');
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      // Get timeout from user settings (with generous buffer for streaming)
      const requestTimeoutMs = await this.getRequestTimeout(`/api/stories/${storyId}/scenes/stream`);
      // Add extra buffer for streaming (double the timeout for streaming endpoints)
      const streamingTimeoutMs = requestTimeoutMs * 2;
      
      const timeoutController = new AbortController();
      const timeoutId = setTimeout(() => {
        if (!receivedComplete) {
          console.warn('[STREAMING] Timeout reached but complete event not received yet');
          timeoutController.abort();
        }
      }, streamingTimeoutMs);
      
      // Combine external abort signal with timeout signal
      let combinedSignal: AbortSignal;
      if (abortSignal) {
        // If both signals exist, create a combined signal that aborts when either does
        const combinedController = new AbortController();
        
        // Listen to external abort signal
        if (abortSignal.aborted) {
          combinedController.abort();
        } else {
          abortSignal.addEventListener('abort', () => {
            combinedController.abort();
          });
        }
        
        // Listen to timeout signal
        if (timeoutController.signal.aborted) {
          combinedController.abort();
        } else {
          timeoutController.signal.addEventListener('abort', () => {
            combinedController.abort();
          });
        }
        
        combinedSignal = combinedController.signal;
      } else {
        combinedSignal = timeoutController.signal;
      }
      
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/stream`, { 
        method: 'POST', 
        headers, 
        body: formData,
        signal: combinedSignal
      });
      
      if (!response.ok) {
        clearTimeout(timeoutId);
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Check if backend returned JSON (non-streaming mode)
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        clearTimeout(timeoutId);
        const data = await response.json();
        // Send content as a single chunk so UI can display it
        if (data.content && onChunk) {
          onChunk(data.content);
          fullStreamedContent = data.content;
        }
        // Call onComplete with the JSON data
        if (onComplete) {
          onComplete(
            data.scene_id,
            data.variant_id,
            data.choices || [],
            undefined, // autoPlay
            undefined, // multiGen
            data.chapter_id
          );
        }
        return;
      }

      if (!response.body) {
        clearTimeout(timeoutId);
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';  // Buffer for incomplete lines
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            if (!receivedComplete) {
              console.warn('[STREAMING] Stream closed before complete event received');
            }
            break;
          }
          
          // Decode and add to buffer
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          // Keep the last incomplete line in buffer
          buffer = lines.pop() || '';
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6).trim();
              if (data === '[DONE]') {
                clearTimeout(timeoutId);
                return;
              }
              if (!data) continue;  // Skip empty lines
              
              try {
                const parsed = JSON.parse(data);
                
                if (parsed.type === 'content' && onChunk) {
                  fullStreamedContent += parsed.chunk;
                  onChunk(parsed.chunk);
                }
                else if (parsed.type === 'thinking_start' && onThinkingStart) {
                  // LLM is starting to think/reason
                  onThinkingStart();
                }
                else if (parsed.type === 'thinking_chunk' && onThinkingChunk) {
                  // Streaming thinking content
                  onThinkingChunk(parsed.chunk);
                }
                else if (parsed.type === 'thinking_end' && onThinkingEnd) {
                  // Thinking phase complete
                  onThinkingEnd(parsed.total_chars || 0);
                }
                else if (parsed.type === 'auto_play_ready' && onAutoPlayReady) {
                  // Connect to TTS immediately when session is ready
                  onAutoPlayReady(parsed.auto_play_session_id, parsed.scene_id);
                }
                else if (parsed.type === 'complete' && onComplete) {
                  receivedComplete = true;
                  clearTimeout(timeoutId);
                  onComplete(parsed.scene_id, parsed.variant_id, parsed.choices || [], parsed.auto_play, undefined, parsed.chapter_id);
                  // Don't return — keep stream open for post-completion events (contradiction_check)
                }
                else if (parsed.type === 'multi_complete') {
                  // Multi-generation complete - handle multiple variants
                  receivedComplete = true;
                  clearTimeout(timeoutId);
                  // Call onComplete with first variant's data, plus multi-generation info
                  if (onComplete && parsed.variants && parsed.variants.length > 0) {
                    const firstVariant = parsed.variants[0];
                    // Extend the callback with multi-generation info via extra parameter
                    onComplete(
                      parsed.scene_id,
                      firstVariant.id,
                      firstVariant.choices || [],
                      undefined,
                      // Pass multi-generation info as 5th parameter
                      {
                        isMultiGeneration: true,
                        totalVariants: parsed.total_variants,
                        variants: parsed.variants
                      },
                      parsed.chapter_id
                    );
                  }
                  // Don't return — keep stream open for post-completion events (contradiction_check)
                }
                else if (parsed.type === 'error' && onError) {
                  clearTimeout(timeoutId);
                  onError(parsed.message);
                  return;
                }
                else if (parsed.type === 'extraction_status' && onExtractionStatus) {
                  onExtractionStatus(parsed.status, parsed.message);
                }
                else if (parsed.type === 'contradiction_check' && onContradictionCheck) {
                  onContradictionCheck(parsed);
                }
                else if (parsed.type === 'start') {
                }
              } catch (parseError) {
                // Log parse errors but continue processing
                console.warn('[STREAMING] Failed to parse line:', line.substring(0, 100), parseError);
              }
            }
          }
        }
      } finally {
        clearTimeout(timeoutId);
        reader.releaseLock();
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Check if abort was user-initiated (external signal) or timeout
        if (abortSignal?.aborted) {
          // User clicked stop - silently handle, don't show error
          console.log('[STREAMING] Generation stopped by user');
          return; // Exit silently without calling onError
        } else {
          // Timeout occurred
          const errorMsg = receivedComplete 
            ? 'Stream timeout after completion' 
            : 'Stream timeout - generation may still be in progress';
          console.error('[STREAMING]', errorMsg);
          if (onError) onError(errorMsg);
        }
      } else {
        console.error('[STREAMING] Error:', error);
        if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
      }
      throw error;
    }
  }

  async generateScenario(data: { genre?: string; tone?: string; elements: { opening?: string; setting?: string; conflict?: string; }; characters?: Array<{ name: string; role: string; description: string; }>; }) {
    return this.request<{ scenario: string; message: string; }>(`/api/stories/generate-scenario`, { method: 'POST', body: JSON.stringify(data) });
  }

  async generateTitles(data: { genre?: string; tone?: string; scenario?: string; characters?: Array<{ name: string; role: string; description: string; }>; story_elements?: Record<string, any>; }) {
    return this.request<{ titles: string[]; message: string; }>(`/api/stories/generate-title`, { method: 'POST', body: JSON.stringify(data) });
  }

  async generatePlot(data: { genre?: string; tone?: string; scenario?: string; characters?: Array<{ name: string; role: string; description: string; }>; world_setting?: string; plot_type?: 'complete' | 'single_point'; plot_point_index?: number; }) {
    return this.request<{ plot_points?: string[]; plot_point?: string; message: string; }>(`/api/stories/generate-plot`, { method: 'POST', body: JSON.stringify(data) });
  }

  async getStoryChoices(storyId: number) {
    return this.request<{ choices: Array<{ text: string; order: number; }>; }>(`/api/stories/${storyId}/choices`);
  }

  async generateMoreChoices(storyId: number, variantId: number) {
    return this.request<{ choices: Array<{ id: number; text: string; order: number; }>; }>(`/api/stories/${storyId}/generate-more-choices`, { 
      method: 'POST',
      body: JSON.stringify({ variant_id: variantId })
    });
  }

  async regenerateLastScene(storyId: number) {
    return this.request<{ message: string; scene: { id: number; sequence_number: number; title: string; content: string; location: string; characters_present: string[]; }; variant: { id: number; variant_number: number; is_original: boolean; generation_method: string; choices: Array<{ id: number; text: string; description: string; order: number; }>; }; }>(`/api/stories/${storyId}/regenerate-last-scene`, { method: 'POST' });
  }

  async regenerateLastSceneStreaming(
    storyId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (variant: any) => void,
    onError?: (error: string) => void
  ) {
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      const formData = new FormData();
      formData.append('custom_prompt', customPrompt);
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/regenerate-last-scene/stream`, { method: 'POST', headers, body: formData });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('Failed to get response reader');
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') return;
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
              else if (parsed.type === 'complete' && onComplete) onComplete(parsed.variant);
              else if (parsed.type === 'error' && onError) onError(parsed.message);
            } catch (e) {
              console.error('Failed to parse streaming data:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming regeneration failed:', error);
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  // Scene Variants
  async createSceneVariantStreaming(
    storyId: number,
    sceneId: number,
    customPrompt = '',
    variantId?: number,
    onChunk?: (chunk: string) => void,
    onComplete?: (variant: any) => void,
    onError?: (error: string) => void,
    onAutoPlayReady?: (sessionId: string) => void,
    isConcluding?: boolean,
    abortSignal?: AbortSignal
  ) {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    
    try {
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/${sceneId}/variants/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          custom_prompt: customPrompt,
          variant_id: variantId,
          is_concluding: isConcluding || false
        }),
        signal: abortSignal
      });
      
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      // Check if backend returned JSON (non-streaming mode)
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        const data = await response.json();
        // Send content as a single chunk
        if (data.content && onChunk) {
          onChunk(data.content);
        }
        // Call onComplete with structure matching streaming format (variant nested inside)
        if (onComplete) {
          onComplete({
            variant: {
              id: data.variant_id,
              variant_number: data.variant_number,
              content: data.content,
              choices: data.choices || []
            }
          });
        }
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Failed to get response reader');

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = new TextDecoder().decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;

              try {
                const parsed = JSON.parse(data);
                if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
                else if (parsed.type === 'auto_play_ready' && onAutoPlayReady) {
                  // Auto-play session is ready - connect immediately!
                  onAutoPlayReady(parsed.auto_play_session_id);
                }
                else if (parsed.type === 'complete' && onComplete) {
                  // Pass the entire parsed object (includes auto_play_session_id if present)
                  onComplete(parsed);
                }
                else if (parsed.type === 'multi_variant_complete' && onComplete) {
                  // Multi-generation variant complete - pass with multi-gen info
                  onComplete({
                    ...parsed,
                    isMultiGeneration: true,
                    variants: parsed.variants,
                    new_variants_count: parsed.new_variants_count,
                    active_variant_id: parsed.active_variant_id
                  });
                }
                else if (parsed.type === 'error' && onError) onError(parsed.message);
              } catch (e) {
                console.error('Failed to parse streaming data:', e);
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      // Check if abort was user-initiated
      if (error instanceof Error && error.name === 'AbortError' && abortSignal?.aborted) {
        // User clicked stop - silently handle, don't show error
        console.log('[STREAMING] Variant generation stopped by user');
        return; // Exit silently without calling onError
      }
      console.error('Streaming variant creation failed:', error);
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  async getSceneVariants(storyId: number, sceneId: number) {
    return this.request<{ scene_id: number; variants: any[] }>(`/api/stories/${storyId}/scenes/${sceneId}/variants`);
  }

  async activateSceneVariant(storyId: number, sceneId: number, variantId: number) {
    return this.request<{ message: string }>(`/api/stories/${storyId}/scenes/${sceneId}/variants/${variantId}/activate`, {
      method: 'POST',
    });
  }

  async updateSceneVariant(storyId: number, sceneId: number, variantId: number, content: string) {
    return this.request<{ message: string; variant: { id: number; content: string; user_edited: boolean; updated_at: string | null } }>(`/api/stories/${storyId}/scenes/${sceneId}/variants/${variantId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  }

  async updateManualChoice(storyId: number, variantId: number, choiceText: string) {
    const formData = new FormData();
    formData.append('choice_text', choiceText);
    
    const token = this.getToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(
      `${this.baseURL}/api/stories/${storyId}/variants/${variantId}/manual-choice`,
      {
        method: 'PUT',
        headers,
        body: formData
      }
    );
    
    if (!response.ok) {
      throw new Error('Failed to update manual choice');
    }
    
    return response.json();
  }

  async updateChoice(storyId: number, choiceId: number, choiceText: string) {
    const formData = new FormData();
    formData.append('choice_text', choiceText);
    
    const token = this.getToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(
      `${this.baseURL}/api/stories/${storyId}/choices/${choiceId}`,
      {
        method: 'PUT',
        headers,
        body: formData,
      }
    );
    
    if (!response.ok) {
      throw new Error('Failed to update choice');
    }
    
    return response.json() as Promise<{
      message: string;
      choice: {
        id: number;
        text: string;
        order: number;
        is_user_created: boolean;
      };
    }>;
  }

  async regenerateSceneVariantChoices(storyId: number, sceneId: number, variantId: number) {
    return this.request<{ message: string; choices: Array<{ id: number | null; text: string; order: number }> }>(`/api/stories/${storyId}/scenes/${sceneId}/variants/${variantId}/regenerate-choices`, {
      method: 'POST',
    });
  }

  // Scene Continuation
  async continueSceneStreaming(
    storyId: number,
    sceneId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (sceneId: number, newContent: string, choices?: any[]) => void,
    onError?: (error: string) => void,
    abortSignal?: AbortSignal
  ) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/${sceneId}/continue/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ custom_prompt: customPrompt }),
        signal: abortSignal
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      // Check if backend returned JSON (non-streaming mode)
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        const data = await response.json();
        // Call onComplete with the JSON data including choices
        if (onComplete) {
          onComplete(data.scene_id, data.new_content, data.choices);
        }
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Failed to get response reader');
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') return;
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
              else if (parsed.type === 'complete' && onComplete) onComplete(parsed.scene_id, parsed.new_content, parsed.choices);
              else if (parsed.type === 'error' && onError) onError(parsed.message);
            } catch (e) {
              // ignore non-JSON lines
            }
          }
        }
      }
    } catch (error) {
      // Check if abort was user-initiated
      if (error instanceof Error && error.name === 'AbortError' && abortSignal?.aborted) {
        // User clicked stop - silently handle, don't show error
        console.log('[STREAMING] Scene continuation stopped by user');
        return; // Exit silently without calling onError
      }
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  // Delete scenes from sequence
  async deleteScenesFromSequence(storyId: number, sequenceNumber: number) {
    return this.request<{ message: string }>(`/api/stories/${storyId}/scenes/from/${sequenceNumber}`, {
      method: 'DELETE',
    });
  }

  // Character API
  async getCharacter(characterId: number) {
    return this.request<{ id: number; name: string; description: string; gender?: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; voice_style: VoiceStyle | null; portrait_image_id: number | null; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/${characterId}`);
  }

  async getCharacters(skip = 0, limit = 50, includePublic = true, templatesOnly = false) {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit), include_public: String(includePublic), templates_only: String(templatesOnly) });
    return this.request<Array<{ id: number; name: string; description: string; gender?: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>>(`/api/characters/?${params}`);
  }

  async deleteCharacter(characterId: number) {
    return this.request<{ message: string; }>(`/api/characters/${characterId}`, { method: 'DELETE' });
  }

  async bulkDeleteCharacters(characterIds: number[]) {
    return this.request<{ message: string; deleted_ids: number[]; }>(`/api/characters/bulk-delete`, {
      method: 'DELETE',
      body: JSON.stringify({ character_ids: characterIds })
    });
  }

  async updateCharacter(characterId: number, data: { name?: string; description?: string; gender?: string; personality_traits?: string[]; background?: string; goals?: string; fears?: string; appearance?: string; is_template?: boolean; is_public?: boolean; voice_style?: VoiceStyle | null; }) {
    return this.request<{ id: number; name: string; description: string; gender?: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; voice_style: VoiceStyle | null; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/${characterId}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async createCharacter(data: { name: string; description?: string; gender?: string; personality_traits?: string[]; background?: string; goals?: string; fears?: string; appearance?: string; is_template?: boolean; is_public?: boolean; voice_style?: VoiceStyle | null; }) {
    return this.request<{ id: number; name: string; description: string; gender?: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; voice_style: VoiceStyle | null; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/`, { method: 'POST', body: JSON.stringify(data) });
  }

  // Get available voice style presets
  async getVoiceStylePresets() {
    return this.request<VoiceStylePresetsResponse>(`/api/characters/voice-style-presets`);
  }

  // Story Character Voice Style Management
  async getStoryCharacters(storyId: number, branchId?: number) {
    console.log('[API] getStoryCharacters called with storyId:', storyId, 'branchId:', branchId, 'type:', typeof branchId);
    const params = branchId !== undefined ? `?branch_id=${branchId}` : '';
    console.log('[API] getStoryCharacters URL params:', params);
    return this.request<Array<{
      id: number;  // story_character id
      character_id: number;
      story_id: number;
      branch_id: number | null;
      role: string | null;
      voice_style_override: VoiceStyle | null;
      name: string;
      description: string | null;
      gender: string | null;
      appearance: string | null;
      portrait_image_id: number | null;
      default_voice_style: VoiceStyle | null;
    }>>(`/api/characters/story/${storyId}/characters${params}`);
  }

  async updateStoryCharacterVoiceStyle(storyId: number, storyCharacterId: number, voiceStyleOverride: VoiceStyle | null) {
    return this.request<{
      id: number;
      character_id: number;
      story_id: number;
      role: string | null;
      voice_style_override: VoiceStyle | null;
      name: string;
      description: string | null;
      default_voice_style: VoiceStyle | null;
    }>(`/api/characters/story/${storyId}/characters/${storyCharacterId}/voice-style`, {
      method: 'PUT',
      body: JSON.stringify({ voice_style_override: voiceStyleOverride })
    });
  }

  async clearStoryCharacterVoiceStyle(storyId: number, storyCharacterId: number) {
    return this.request<{ message: string }>(`/api/characters/story/${storyId}/characters/${storyCharacterId}/voice-style`, {
      method: 'DELETE'
    });
  }

  async updateStoryCharacterRole(storyId: number, storyCharacterId: number, role: string) {
    return this.request<{
      id: number;
      character_id: number;
      story_id: number;
      role: string | null;
      voice_style_override: VoiceStyle | null;
      name: string;
      description: string | null;
      default_voice_style: VoiceStyle | null;
    }>(`/api/characters/story/${storyId}/characters/${storyCharacterId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role })
    });
  }

  async removeStoryCharacter(storyId: number, storyCharacterId: number) {
    return this.request<{
      message: string;
      deleted_story_character_id: number;
      character_id: number | null;
      branch_id: number | null;
    }>(`/api/characters/story/${storyId}/characters/${storyCharacterId}`, {
      method: 'DELETE'
    });
  }

  async generateCharacterWithAI(prompt: string, storyContext?: { genre?: string; tone?: string; world_setting?: string }, previousGeneration?: any) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; background_structured?: Record<string, any>; goals_structured?: Record<string, any>; fears_structured?: Record<string, any>; appearance_structured?: Record<string, any>; suggested_voice_style?: string }>(`/api/characters/generate-with-ai`, {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        story_context: storyContext || null,
        previous_generation: previousGeneration || null
      })
    });
  }

  // Character Assistant API
  async checkCharacterImportance(storyId: number, chapterId?: number, branchId?: number) {
    const params = new URLSearchParams();
    if (chapterId !== undefined) params.set('chapter_id', String(chapterId));
    if (branchId !== undefined) params.set('branch_id', String(branchId));
    const qs = params.toString();
    return this.request<{ new_character_detected: boolean }>(`/api/stories/${storyId}/character-importance-check${qs ? `?${qs}` : ''}`);
  }

  async getCharacterSuggestions(storyId: number, chapterId?: number, branchId?: number) {
    const params = new URLSearchParams();
    if (chapterId !== undefined) params.set('chapter_id', String(chapterId));
    if (branchId !== undefined) params.set('branch_id', String(branchId));
    const qs = params.toString();
    return this.request<{
      suggestions: Array<{
        name: string;
        mention_count: number;
        importance_score: number;
        first_appearance_scene: number;
        last_appearance_scene: number;
        is_in_library: boolean;
        preview: string;
        scenes: number[];
      }>;
      chapter_analyzed: number | null;
      total_scenes_analyzed: number;
    }>(`/api/stories/${storyId}/character-suggestions${qs ? `?${qs}` : ''}`);
  }

  async analyzeCharacterDetails(storyId: number, characterName: string) {
    return this.request<{
      name: string;
      description: string;
      personality_traits: string[];
      background: string;
      goals: string;
      fears: string;
      appearance: string;
      suggested_role: string;
      suggested_voice_style?: string;
      confidence: number;
      scenes_analyzed: number[];
    }>(`/api/stories/${storyId}/character-suggestions/${encodeURIComponent(characterName)}/analyze`, {
      method: 'POST'
    });
  }

  async createCharacterFromSuggestion(storyId: number, characterName: string, characterData: {
    name: string;
    description: string;
    gender?: string;
    personality_traits: string[];
    background: string;
    goals: string;
    fears: string;
    appearance: string;
    role: string;
  }) {
    return this.request<{
      id: number;
      name: string;
      description: string;
      personality_traits: string[];
      background: string;
      goals: string;
      fears: string;
      appearance: string;
      role: string;
    }>(`/api/stories/${storyId}/character-suggestions/${encodeURIComponent(characterName)}/create`, {
      method: 'POST',
      body: JSON.stringify(characterData)
    });
  }

  // Draft Stories
  async getDraftStory() {
    return this.request<{ id: number; title: string; scenario: string; characters: Array<{ id: number; name: string; description: string; }>; plot_points: string[]; created_at: string; updated_at: string; }>(`/api/stories/draft`);
  }

  async getSpecificDraftStory(storyId: number) {
    return this.request<{ id: number; title: string; scenario: string; characters: Array<{ id: number; name: string; description: string; }>; plot_points: string[]; created_at: string; updated_at: string; }>(`/api/stories/draft/${storyId}`);
  }

  async createOrUpdateDraftStory(data: { title?: string; scenario?: string; characters?: any[]; plot_points?: string[]; step?: number; story_id?: number; }) {
    return this.request<any>(`/api/stories/draft`, { method: 'POST', body: JSON.stringify(data) });
  }

  async finalizeDraftStory(draftStoryId: number) {
    return this.request<{ id: number; title: string; scenario: string; characters: Array<{ id: number; name: string; description: string; }>; plot_points: string[]; created_at: string; updated_at: string; }>(`/api/stories/draft/${draftStoryId}/finalize`, { method: 'POST' });
  }

  async deleteDraftStory(draftStoryId: number) {
    return this.request<{ message: string; }>(`/api/stories/draft/${draftStoryId}`, { method: 'DELETE' });
  }

  // Writing Style Presets
  async listWritingPresets() {
    return this.request<Array<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
      prose_style: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>>(`/api/writing-presets/`);
  }

  async getWritingPreset(presetId: number) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
      prose_style: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}`);
  }

  async createWritingPreset(data: {
    name: string;
    description?: string;
    system_prompt: string;
    summary_system_prompt?: string;
    pov?: string;
    prose_style?: string;
  }) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
      prose_style: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateWritingPreset(presetId: number, data: {
    name?: string;
    description?: string;
    system_prompt?: string;
    summary_system_prompt?: string;
    pov?: string;
    prose_style?: string;
  }) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
      prose_style: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteWritingPreset(presetId: number) {
    return this.request<void>(`/api/writing-presets/${presetId}`, {
      method: 'DELETE',
    });
  }

  async activateWritingPreset(presetId: number) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
      prose_style: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}/activate`, {
      method: 'POST',
    });
  }

  async duplicateWritingPreset(presetId: number) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
      prose_style: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}/duplicate`, {
      method: 'POST',
    });
  }

  async getDefaultWritingPresetTemplate() {
    return this.request<{
      name: string;
      description: string;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov?: string;
      prose_style?: string;
    }>(`/api/writing-presets/default/template`);
  }

  async getProseStyles() {
    return this.request<Array<{
      key: string;
      name: string;
      description: string;
      example: string;
    }>>(`/api/writing-presets/prose-styles`);
  }

  // Chapters
  async getChapters(storyId: number) {
    return this.request<Array<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>>(`/api/stories/${storyId}/chapters`);
  }

  async getChapter(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
      characters?: Array<{
        id: number;
        name: string;
        role: string | null;
        description: string | null;
      }>;
      location_name?: string | null;
      time_period?: string | null;
      scenario?: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}`);
  }

  async getActiveChapter(storyId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
      characters?: Array<{
        id: number;
        name: string;
        role: string | null;
        description: string | null;
      }>;
      location_name?: string | null;
      time_period?: string | null;
      scenario?: string | null;
    }>(`/api/stories/${storyId}/active-chapter`);
  }

  async createChapter(
    storyId: number,
    data: {
      title?: string;
      description?: string;
      plot_point?: string;
      plot_point_index?: number;
      story_so_far?: string;
      story_character_ids?: number[];
      character_ids?: number[];
      character_roles?: { [characterId: number]: string };
      location_name?: string;
      time_period?: string;
      scenario?: string;
      continues_from_previous?: boolean;
      chapter_plot?: any;  // Structured plot from brainstorming
      brainstorm_session_id?: number;  // Link to brainstorm session
    },
    onStatusUpdate?: (status: { message: string; step: string }) => void
  ) {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseURL}/api/stories/${storyId}/chapters`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    // Handle streaming response
    if (response.headers.get('content-type')?.includes('text/event-stream')) {
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let chapterData: any = null;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;

              try {
                const parsed = JSON.parse(data);

                if (parsed.type === 'status' && onStatusUpdate) {
                  onStatusUpdate({ message: parsed.message, step: parsed.step });
                } else if (parsed.type === 'complete') {
                  chapterData = parsed.chapter;
                } else if (parsed.type === 'enrichment_complete') {
                  // Story context generated successfully — update chapter data if we have it
                  if (onStatusUpdate) {
                    onStatusUpdate({ message: 'Story context generated', step: 'enrichment_complete' });
                  }
                } else if (parsed.type === 'enrichment_failed') {
                  // Non-fatal: chapter was created but story_so_far generation failed
                  console.warn('[createChapter] Enrichment failed (non-fatal):', parsed.message);
                  if (onStatusUpdate) {
                    onStatusUpdate({ message: 'Story context generation failed (can retry later)', step: 'enrichment_failed' });
                  }
                } else if (parsed.type === 'error') {
                  throw new Error(parsed.message);
                }
              } catch (e) {
                // Ignore JSON parse errors for non-JSON lines
                if (e instanceof SyntaxError) continue;
                throw e;
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

      if (!chapterData) {
        throw new Error('No chapter data received');
      }

      return chapterData;
    } else {
      // Fallback to regular JSON response
      return this.request<{
        id: number;
        story_id: number;
        chapter_number: number;
        title: string | null;
        description: string | null;
        plot_point: string | null;
        plot_point_index: number | null;
        story_so_far: string | null;
        auto_summary: string | null;
        status: 'draft' | 'active' | 'completed';
        context_tokens_used: number;
        scenes_count: number;
        last_summary_scene_count: number;
        created_at: string;
        updated_at: string | null;
      }>(`/api/stories/${storyId}/chapters`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    }
  }

  async resumeChapterCreation(
    storyId: number,
    chapterId: number,
    onStatusUpdate?: (status: { message: string; step: string }) => void
  ) {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const response = await fetch(
      `${this.baseURL}/api/stories/${storyId}/chapters/${chapterId}/resume-creation`,
      {
        method: 'POST',
        headers,
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    // Handle streaming response (same pattern as createChapter)
    if (response.headers.get('content-type')?.includes('text/event-stream')) {
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let chapterData: any = null;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;

              try {
                const parsed = JSON.parse(data);

                if (parsed.type === 'status' && onStatusUpdate) {
                  onStatusUpdate({ message: parsed.message, step: parsed.step });
                } else if (parsed.type === 'complete') {
                  chapterData = parsed.chapter;
                } else if (parsed.type === 'error') {
                  throw new Error(parsed.message);
                }
              } catch (e) {
                if (e instanceof SyntaxError) continue;
                throw e;
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

      if (!chapterData) {
        throw new Error('No chapter data received from resume');
      }

      return chapterData;
    } else {
      return response.json();
    }
  }

  async updateChapter(storyId: number, chapterId: number, data: {
    title?: string;
    description?: string;
    story_so_far?: string;
    auto_summary?: string;
    plot_point?: string;
    story_character_ids?: number[];
    character_ids?: number[];  // New characters from library to add to story
    character_roles?: { [characterId: number]: string };  // Roles for new characters
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
    chapter_plot?: any;  // Structured plot from brainstorming
    brainstorm_session_id?: number;  // Link to brainstorm session
    arc_phase_id?: string;  // Story arc phase this chapter belongs to
  }) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async completeChapter(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/complete`, {
      method: 'POST',
    });
  }

  async concludeChapter(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
      characters?: Array<{
        id: number;
        name: string;
        role: string | null;
        description: string | null;
      }>;
      location_name?: string | null;
      time_period?: string | null;
      scenario?: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/conclude`, {
      method: 'POST',
    });
  }

  async setActiveChapter(storyId: number, chapterId: number) {
    return this.request<Array<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
      characters?: Array<{
        id: number;
        name: string;
        role: string | null;
        description: string | null;
      }>;
      location_name?: string | null;
      time_period?: string | null;
      scenario?: string | null;
    }>>(`/api/stories/${storyId}/chapters/${chapterId}/activate`, {
      method: 'PUT',
    });
  }

  async addCharacterToChapter(storyId: number, chapterId: number, characterId?: number, storyCharacterId?: number, role?: string) {
    const params = new URLSearchParams();
    if (characterId !== undefined) params.set('character_id', String(characterId));
    if (storyCharacterId !== undefined) params.set('story_character_id', String(storyCharacterId));
    if (role !== undefined) params.set('role', role);
    const qs = params.toString();
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
      characters?: Array<{
        id: number;
        name: string;
        role: string | null;
        description: string | null;
      }>;
      location_name?: string | null;
      time_period?: string | null;
      scenario?: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/characters${qs ? `?${qs}` : ''}`, {
      method: 'POST',
    });
  }

  async getAvailableCharacters(storyId: number) {
    return this.request<{
      characters: Array<{
        story_character_id: number;
        character_id: number;
        name: string;
        role: string | null;
        description: string | null;
      }>;
    }>(`/api/stories/${storyId}/available-characters`);
  }

  async getAvailableLocations(storyId: number) {
    return this.request<{
      locations: string[];
    }>(`/api/stories/${storyId}/available-locations`);
  }

  async getChapterContextStatus(storyId: number, chapterId: number) {
    return this.request<{
      chapter_id: number;
      current_tokens: number;
      max_tokens: number;
      percentage_used: number;
      should_create_new_chapter: boolean;
      reason: string | null;
      scenes_count: number;
      avg_generation_time?: number | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/context-status`);
  }

  async generateChapterSummary(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/generate-summary`, {
      method: 'POST',
    });
  }

  async deleteChapterScenes(storyId: number, chapterId: number) {
    return this.request<{ message: string }>(`/api/stories/${storyId}/chapters/${chapterId}/scenes`, {
      method: 'DELETE',
    });
  }

  async deleteChapter(storyId: number, chapterId: number) {
    return this.request<{
      message: string;
      chapter_number: number;
      chapter_title: string;
      scenes_deleted: number;
      batches_deleted: number;
    }>(`/api/stories/${storyId}/chapters/${chapterId}`, {
      method: 'DELETE',
    });
  }

  // Branch API
  async getBranches(storyId: number) {
    return this.request<{
      branches: Array<{
        id: number;
        story_id: number;
        name: string;
        description: string | null;
        is_main: boolean;
        is_active: boolean;
        forked_from_branch_id: number | null;
        forked_at_scene_sequence: number | null;
        scene_count: number;
        chapter_count: number;
        created_at: string;
      }>;
      active_branch_id: number | null;
    }>(`/api/stories/${storyId}/branches`);
  }

  async getActiveBranch(storyId: number) {
    return this.request<{
      id: number;
      story_id: number;
      name: string;
      description: string | null;
      is_main: boolean;
      is_active: boolean;
      forked_from_branch_id: number | null;
      forked_at_scene_sequence: number | null;
      scene_count: number;
      chapter_count: number;
      created_at: string;
    }>(`/api/stories/${storyId}/branches/active`);
  }

  async createBranch(storyId: number, data: {
    name: string;
    description?: string;
    fork_from_scene_sequence: number;
    activate?: boolean;
  }) {
    return this.request<{
      branch: {
        id: number;
        story_id: number;
        name: string;
        description: string | null;
        is_main: boolean;
        is_active: boolean;
        forked_from_branch_id: number | null;
        forked_at_scene_sequence: number | null;
        scene_count: number;
        chapter_count: number;
        created_at: string;
      };
      stats: {
        scenes_cloned: number;
        chapters_cloned: number;
        characters_cloned: number;
        [key: string]: any;
      };
    }>(`/api/stories/${storyId}/branches`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async activateBranch(storyId: number, branchId: number) {
    return this.request<{
      success: boolean;
      message: string;
      branch: {
        id: number;
        story_id: number;
        name: string;
        description: string | null;
        is_main: boolean;
        is_active: boolean;
        forked_from_branch_id: number | null;
        forked_at_scene_sequence: number | null;
        scene_count: number;
        chapter_count: number;
        created_at: string;
      };
    }>(`/api/stories/${storyId}/branches/${branchId}/activate`, {
      method: 'PUT',
    });
  }

  async updateBranch(storyId: number, branchId: number, data: {
    name?: string;
    description?: string;
  }) {
    return this.request<{
      id: number;
      story_id: number;
      name: string;
      description: string | null;
      is_main: boolean;
      is_active: boolean;
      forked_from_branch_id: number | null;
      forked_at_scene_sequence: number | null;
      scene_count: number;
      chapter_count: number;
      created_at: string;
    }>(`/api/stories/${storyId}/branches/${branchId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteBranch(storyId: number, branchId: number) {
    return this.request<{ success: boolean; message: string }>(`/api/stories/${storyId}/branches/${branchId}`, {
      method: 'DELETE',
    });
  }

  async getBranchStats(storyId: number, branchId: number) {
    return this.request<{
      branch_id: number;
      branch_name: string;
      scene_count: number;
      chapter_count: number;
      character_count: number;
      [key: string]: any;
    }>(`/api/stories/${storyId}/branches/${branchId}/stats`);
  }

  // ====== BRAINSTORM METHODS ======
  
  async createBrainstormSession(preSelectedCharacterIds?: number[], contentRating?: 'sfw' | 'nsfw') {
    return this.request<{
      session_id: number;
      status: string;
      message_count: number;
      created_at: string;
    }>('/api/brainstorm/session', {
      method: 'POST',
      body: JSON.stringify({ 
        pre_selected_character_ids: preSelectedCharacterIds || [],
        content_rating: contentRating || 'sfw'
      })
    });
  }

  async getBrainstormSession(sessionId: number) {
    return this.request<{
      session_id: number;
      status: string;
      messages: Array<{ role: string; content: string; timestamp: string }>;
      extracted_elements: any;
      story_id: number | null;
      created_at: string;
      updated_at: string;
    }>(`/api/brainstorm/session/${sessionId}`);
  }

  async deleteBrainstormSession(sessionId: number) {
    return this.request<{
      success: boolean;
      message: string;
    }>(`/api/brainstorm/session/${sessionId}`, {
      method: 'DELETE'
    });
  }

  async deleteBrainstormSessions(sessionIds: number[]) {
    // Delete multiple sessions in parallel
    const results = await Promise.allSettled(
      sessionIds.map(id => this.deleteBrainstormSession(id))
    );
    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    const failed = results.filter(r => r.status === 'rejected').length;
    return { succeeded, failed, total: sessionIds.length };
  }

  async sendBrainstormMessage(sessionId: number, message: string, generateIdeas: boolean = false) {
    return this.request<{
      session_id: number;
      user_message: string;
      ai_response: string;
      message_count: number;
    }>('/api/brainstorm/chat', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message, generate_ideas: generateIdeas })
    });
  }

  async generateCharactersForSession(sessionId: number) {
    return this.request<{
      session_id: number;
      characters: Array<{
        name: string;
        role: string;
        description: string;
        personality_traits: string[];
      }>;
      count: number;
    }>(`/api/brainstorm/sessions/${sessionId}/generate-characters`, {
      method: 'POST'
    });
  }

  async extractBrainstormElements(sessionId: number) {
    return this.request<{
      session_id: number;
      elements: {
        genre: string;
        tone: string;
        characters: Array<{
          name: string;
          role: string;
          description: string;
          personality_traits?: string[];
        }>;
        scenario: string;
        world_setting: string;
        suggested_titles: string[];
        description: string;
        plot_points: string[];
        themes: string[];
        conflicts: string[];
      };
      status: string;
    }>('/api/brainstorm/extract', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId })
    });
  }

  async updateBrainstormElements(sessionId: number, elements: any) {
    return this.request<{
      session_id: number;
      elements: any;
    }>('/api/brainstorm/elements/update', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, elements })
    });
  }

  async completeBrainstormSession(sessionId: number, storyId: number) {
    return this.request<{
      session_id: number;
      status: string;
      story_id: number;
    }>('/api/brainstorm/complete', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, story_id: storyId })
    });
  }

  async listBrainstormSessions(skip: number = 0, limit: number = 10) {
    return this.request<Array<{
      session_id: number;
      status: string;
      message_count: number;
      has_elements: boolean;
      story_id: number | null;
      created_at: string;
      updated_at: string;
    }>>(`/api/brainstorm/sessions/list?skip=${skip}&limit=${limit}`);
  }

  async getBrainstormExtractedElements(sessionId: number) {
    const session = await this.getBrainstormSession(sessionId);
    return session.extracted_elements;
  }

  // Get user's brainstorm sessions with summaries (for dashboard)
  async getBrainstormSessions(includeCompleted: boolean = false) {
    return this.request<{
      sessions: Array<{
        id: number;
        status: string;
        message_count: number;
        summary: string;
        created_at: string;
        updated_at: string;
        story_id: number | null;
        has_extracted_elements: boolean;
      }>;
      count: number;
    }>(`/api/brainstorm/sessions?include_completed=${includeCompleted}`);
  }

  // ====== STORY ARC METHODS ======

  async generateArcFromSession(sessionId: number, structureType: string = 'three_act') {
    return this.request<{
      session_id: number;
      arc: StoryArc;
    }>(`/api/brainstorm/sessions/${sessionId}/generate-arc`, {
      method: 'POST',
      body: JSON.stringify({ structure_type: structureType })
    });
  }

  async generateStoryArc(storyId: number, structureType: string = 'three_act') {
    return this.request<{
      story_id: number;
      arc: StoryArc;
    }>(`/api/stories/${storyId}/arc/generate`, {
      method: 'POST',
      body: JSON.stringify({ structure_type: structureType })
    });
  }

  async updateStoryArc(storyId: number, arcData: StoryArc) {
    return this.request<{
      story_id: number;
      arc: StoryArc;
    }>(`/api/stories/${storyId}/arc`, {
      method: 'PUT',
      body: JSON.stringify({ arc_data: arcData })
    });
  }

  async getStoryArc(storyId: number) {
    return this.request<{
      story_id: number;
      arc: StoryArc | null;
    }>(`/api/stories/${storyId}/arc`);
  }

  // ====== CHAPTER BRAINSTORM METHODS ======

  async createChapterBrainstormSession(storyId: number, arcPhaseId?: string, chapterId?: number, priorChapterSummary?: string) {
    return this.request<{
      session_id: number;
      story_id: number;
      chapter_id: number | null;
      arc_phase_id: string | null;
      prior_chapter_summary: string | null;
      status: string;
      created_at: string;
    }>(`/api/stories/${storyId}/chapters/brainstorm`, {
      method: 'POST',
      body: JSON.stringify({ 
        arc_phase_id: arcPhaseId, 
        chapter_id: chapterId,
        prior_chapter_summary: priorChapterSummary 
      })
    });
  }

  async getChapterBrainstormContext(storyId: number, chapterId: number) {
    return this.request<{
      chapter_id: number;
      chapter_number: number;
      title: string | null;
      has_summary: boolean;
      summary: string | null;
      scene_count: number;
      total_words: number;
      scenes: Array<{
        sequence: number;
        content: string;
        word_count: number;
      }>;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/brainstorm-context`);
  }

  async getChapterBrainstormSessions(storyId: number) {
    return this.request<{
      story_id: number;
      sessions: Array<{
        id: number;
        story_id: number;
        chapter_id: number | null;
        arc_phase_id: string | null;
        status: string;
        message_count: number;
        has_extracted_plot: boolean;
        created_at: string;
        updated_at: string | null;
      }>;
      count: number;
    }>(`/api/stories/${storyId}/chapters/brainstorm/sessions`);
  }

  async getChapterBrainstormSession(storyId: number, sessionId: number) {
    return this.request<{
      session_id: number;
      story_id: number;
      chapter_id: number | null;
      arc_phase_id: string | null;
      status: string;
      messages: Array<{ role: string; content: string; timestamp: string }>;
      extracted_plot: ChapterPlot | null;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}`);
  }

  async sendChapterBrainstormMessage(storyId: number, sessionId: number, message: string) {
    return this.request<{
      session_id: number;
      user_message: string;
      ai_response: string;
      message_count: number;
      suggested_elements?: SuggestedElements;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}/message`, {
      method: 'POST',
      body: JSON.stringify({ message })
    });
  }

  /**
   * Send a message in chapter brainstorming with streaming response.
   * 
   * @param storyId - The story ID
   * @param sessionId - The brainstorm session ID
   * @param message - The user's message
   * @param onChunk - Callback for content chunks
   * @param onComplete - Callback when streaming is complete
   * @param onError - Callback for errors
   * @param onThinkingStart - Callback when LLM starts thinking
   * @param onThinkingChunk - Callback for thinking content chunks
   * @param onThinkingEnd - Callback when thinking ends
   * @param abortSignal - Optional abort signal to cancel the request
   */
  async sendChapterBrainstormMessageStreaming(
    storyId: number,
    sessionId: number,
    message: string,
    onChunk?: (chunk: string) => void,
    onComplete?: (aiResponse: string, messageCount: number) => void,
    onError?: (error: string) => void,
    onThinkingStart?: () => void,
    onThinkingChunk?: (chunk: string) => void,
    onThinkingEnd?: (totalChars: number) => void,
    onSuggestions?: (elements: SuggestedElements) => void,
    abortSignal?: AbortSignal
  ): Promise<void> {
    const baseUrl = getApiBaseUrlSync();
    const url = `${baseUrl}/api/stories/${storyId}/chapters/brainstorm/${sessionId}/message/stream`;
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.token}`,
        },
        body: JSON.stringify({ message }),
        signal: abortSignal,
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }
      
      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') {
              return;
            }
            if (!data) continue;
            
            try {
              const parsed = JSON.parse(data);
              
              switch (parsed.type) {
                case 'thinking_start':
                  onThinkingStart?.();
                  break;
                case 'thinking_chunk':
                  onThinkingChunk?.(parsed.chunk);
                  break;
                case 'thinking_end':
                  onThinkingEnd?.(parsed.total_chars);
                  break;
                case 'content':
                  fullContent += parsed.chunk;
                  onChunk?.(parsed.chunk);
                  break;
                case 'complete':
                  onComplete?.(parsed.ai_response, parsed.message_count);
                  break;
                case 'suggestions':
                  onSuggestions?.(parsed.elements);
                  break;
                case 'error':
                  onError?.(parsed.message);
                  break;
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // Request was aborted, don't call onError
      }
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      onError?.(errorMessage);
    }
  }

  async extractChapterPlot(storyId: number, sessionId: number) {
    return this.request<{
      session_id: number;
      extracted_plot: ChapterPlot;
      status: string;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}/extract`, {
      method: 'POST'
    });
  }

  async applyChapterBrainstorm(storyId: number, sessionId: number, chapterId: number) {
    return this.request<any>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}/apply`, {
      method: 'POST',
      body: JSON.stringify({ chapter_id: chapterId })
    });
  }

  async updateChapterBrainstormPlot(storyId: number, sessionId: number, plotData: ChapterPlot) {
    return this.request<{
      session_id: number;
      extracted_plot: ChapterPlot;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}/plot`, {
      method: 'PUT',
      body: JSON.stringify({ plot_data: plotData })
    });
  }

  async deleteChapterBrainstormSession(storyId: number, sessionId: number) {
    return this.request<{
      success: boolean;
      message: string;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}`, {
      method: 'DELETE'
    });
  }

  async getChapterBrainstormElements(storyId: number, sessionId: number) {
    return this.request<{
      session_id: number;
      structured_elements: StructuredElements;
      suggested_elements?: SuggestedElements;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}/elements`);
  }

  async updateChapterBrainstormElement(
    storyId: number, 
    sessionId: number, 
    elementType: 'overview' | 'characters' | 'tone' | 'key_events' | 'ending',
    value: string | CharacterArc[] | string[]
  ) {
    return this.request<{
      session_id: number;
      structured_elements: StructuredElements;
    }>(`/api/stories/${storyId}/chapters/brainstorm/${sessionId}/elements`, {
      method: 'PUT',
      body: JSON.stringify({ element_type: elementType, value })
    });
  }

  // Chapter Progress Methods
  async getChapterProgress(storyId: number, chapterId: number): Promise<ChapterProgress> {
    return this.request<ChapterProgress>(`/api/stories/${storyId}/chapters/${chapterId}/progress`);
  }

  async toggleEventCompletion(storyId: number, chapterId: number, event: string, completed: boolean): Promise<ChapterProgress> {
    return this.request<ChapterProgress>(`/api/stories/${storyId}/chapters/${chapterId}/progress/events`, {
      method: 'PUT',
      body: JSON.stringify({ event, completed })
    });
  }

  async toggleMilestoneCompletion(storyId: number, chapterId: number, milestone: 'climax' | 'resolution', completed: boolean): Promise<ChapterProgress> {
    return this.request<ChapterProgress>(`/api/stories/${storyId}/chapters/${chapterId}/progress/milestone`, {
      method: 'PUT',
      body: JSON.stringify({ milestone, completed })
    });
  }

  // Generic HTTP methods
  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  async post<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async put<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  // Contradictions API
  async getContradictions(storyId: number, options?: { resolved?: boolean; branchId?: number }) {
    const params = new URLSearchParams();
    if (options?.resolved) params.set('resolved', 'true');
    if (options?.branchId) params.set('branch_id', String(options.branchId));
    const qs = params.toString();
    return this.request<Array<{
      id: number;
      story_id: number;
      branch_id: number | null;
      scene_sequence: number;
      contradiction_type: string;
      character_name: string | null;
      previous_value: string | null;
      current_value: string | null;
      severity: string;
      resolved: boolean;
      resolution_note: string | null;
      detected_at: string | null;
      resolved_at: string | null;
    }>>(`/api/stories/${storyId}/contradictions${qs ? `?${qs}` : ''}`);
  }

  async resolveContradiction(contradictionId: number, note: string) {
    return this.request<{
      id: number;
      story_id: number;
      branch_id: number | null;
      scene_sequence: number;
      contradiction_type: string;
      character_name: string | null;
      previous_value: string | null;
      current_value: string | null;
      severity: string;
      resolved: boolean;
      resolution_note: string | null;
      detected_at: string | null;
      resolved_at: string | null;
    }>(`/api/contradictions/${contradictionId}/resolve`, {
      method: 'PATCH',
      body: JSON.stringify({ note }),
    });
  }

  async getContradictionsSummary(storyId: number, branchId?: number) {
    const params = branchId !== undefined ? `?branch_id=${branchId}` : '';
    return this.request<{
      total: number;
      unresolved: number;
      resolved: number;
      by_type: Record<string, number>;
      by_severity: Record<string, number>;
    }>(`/api/stories/${storyId}/contradictions/summary${params}`);
  }

  // Utility methods
  getBaseURL(): string {
    return this.baseURL;
  }

  getToken(): string | null {
    return this.token;
  }
}

// Export singleton instance as default
export default new ApiClient();

// Export getApiBaseUrl for direct URL construction when needed
export { getApiBaseUrl };
