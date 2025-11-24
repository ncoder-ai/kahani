// API configuration and utilities

import { getApiBaseUrl as getApiBaseUrlFromConfig, getApiBaseUrlSync as getApiBaseUrlSyncFromConfig } from './apiUrl';

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

// Runtime API URL detection - uses config API
async function getApiBaseUrl(): Promise<string> {
  // First check environment variable
  if (process.env.NEXT_PUBLIC_API_URL) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }
  
  // Use config API to get backend port
  try {
    return await getApiBaseUrlFromConfig();
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
  return getApiBaseUrlSyncFromConfig();
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
    // Try to get from config API
    try {
      this.baseURL = await getApiBaseUrl();
    } catch (error) {
      console.error('Failed to initialize API URL from config:', error);
      throw error; // Fail fast - config must be available
    }
  }

  private loadToken() {
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('auth_token');
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

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_token', token);
    }
  }

  removeToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
    }
    // Clear cached timeout when token is removed
    this.cachedTimeoutMs = null;
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
        console.log(`[API] Using user timeout: ${timeoutTotal}s (+10s buffer = ${this.cachedTimeoutMs}ms)`);
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
    console.log('[API] Using default timeout: 300s');
    return this.cachedTimeoutMs;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    // Ensure baseURL is initialized before making request
    if (!this.baseURL) {
      await this.initialize();
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

    console.log(`[API] ${options.method || 'GET'} ${url}`);
    console.log('[API] Base URL:', this.baseURL);
    console.log('[API] Endpoint:', endpoint);
    console.log('[API] Headers:', Object.keys(headers));

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
      console.log(`[API] Response status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        if (response.status === 401) {
          // Skip token refresh for login endpoint to avoid retry loops
          if (endpoint.includes('/api/auth/login')) {
            console.log('[API] 401 on login endpoint - skipping token refresh');
            this.removeToken();
            throw new Error('Authentication failed. Please check your credentials.');
          }
          
          console.log('[API] 401 Unauthorized - attempting token refresh');
          const refreshSuccess = await this.handleTokenRefresh();
          if (refreshSuccess) {
            console.log('[API] Token refreshed, retrying request');
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
                const retryData = await retryResponse.json();
                console.log('[API] Retry successful');
                return retryData;
              }
            } catch (retryError) {
              clearTimeout(retryTimeoutId);
              if (retryError instanceof Error && retryError.name === 'AbortError') {
                throw new Error('Request timed out. Please check your connection and try again.');
              }
              throw retryError;
            }
          }
          
          console.log('[API] Token refresh failed or not available - redirecting to login');
          this.removeToken();
          if (typeof window !== 'undefined') {
            window.location.href = '/login';
          }
          throw new Error('Authentication required');
        }

        let errorData: any;
        try {
          errorData = await response.json();
          console.log('[API] Error response data:', errorData);
        } catch (e) {
          console.error('[API] Failed to parse error response:', e);
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        if (errorData.detail && Array.isArray(errorData.detail)) {
          const errorMessages = errorData.detail.map((err: any) => {
            const location = err.loc ? err.loc.slice(1).join(' -> ') : 'Field';
            return `${location}: ${err.msg}`;
          }).join(', ');
          throw new Error(errorMessages);
        }

        const errorMessage = errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`;
        throw new Error(typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage));
      }

      const data = await response.json();
      console.log('[API] Response data received successfully');
      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error) {
        // Handle timeout specifically
        if (error.name === 'AbortError') {
          const timeoutSeconds = Math.round(requestTimeoutMs / 1000);
          console.error(`[API] Request timed out after ${timeoutSeconds} seconds`);
          throw new Error(`Request timed out after ${timeoutSeconds} seconds. Please check your connection and try again.`);
        }
        console.error('[API] Request failed:', error.message);
      } else {
        console.error('[API] Request failed with unknown error:', error);
      }
      throw error;
    }
  }

  // Authentication
  async login(email: string, password: string, rememberMe: boolean = false) {
    return this.request<{
      access_token: string;
      token_type: string;
      refresh_token?: string;
      user: any;
    }>(`/api/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password, remember_me: rememberMe }),
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

  async getStory(id: number) {
    return this.request<any>(`/api/stories/${id}`);
  }

  async createStory(data: { title: string; description?: string; genre?: string; tone?: string; world_setting?: string; initial_premise?: string; }) {
    return this.request<any>(`/api/stories/`, { method: 'POST', body: JSON.stringify(data) });
  }

  async updateStory(id: number, data: { title?: string; description?: string; genre?: string; tone?: string; world_setting?: string; initial_premise?: string; scenario?: string; }) {
    return this.request<any>(`/api/stories/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async generateScene(storyId: number, customPrompt = '', userContent?: string, contentMode: 'ai_generate' | 'user_scene' | 'user_prompt' = 'ai_generate') {
    const formData = new FormData();
    formData.append('custom_prompt', customPrompt);
    if (userContent) {
      formData.append('user_content', userContent);
    }
    formData.append('content_mode', contentMode);
    return this.request<any>(`/api/stories/${storyId}/scenes`, { method: 'POST', headers: {}, body: formData });
  }

  async generateSceneStreaming(
    storyId: number,
    customPrompt = '',
    userContent?: string,
    contentMode: 'ai_generate' | 'user_scene' | 'user_prompt' = 'ai_generate',
    onChunk?: (chunk: string) => void,
    onComplete?: (sceneId: number, choices: any[], autoPlay?: { enabled: boolean; session_id: string; scene_id: number }) => void,
    onError?: (error: string) => void,
    onAutoPlayReady?: (sessionId: string, sceneId: number) => void,
    onExtractionStatus?: (status: 'extracting' | 'complete' | 'error', message: string) => void
  ) {
    let fullStreamedContent = '';  // Track all streamed content for verification
    let receivedComplete = false;  // Track if we received the complete event
    const formData = new FormData();
    formData.append('custom_prompt', customPrompt);
    if (userContent) {
      formData.append('user_content', userContent);
    }
    formData.append('content_mode', contentMode);
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      // Get timeout from user settings (with generous buffer for streaming)
      const requestTimeoutMs = await this.getRequestTimeout(`/api/stories/${storyId}/scenes/stream`);
      // Add extra buffer for streaming (double the timeout for streaming endpoints)
      const streamingTimeoutMs = requestTimeoutMs * 2;
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        if (!receivedComplete) {
          console.warn('[STREAMING] Timeout reached but complete event not received yet');
          controller.abort();
        }
      }, streamingTimeoutMs);
      
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/stream`, { 
        method: 'POST', 
        headers, 
        body: formData,
        signal: controller.signal
      });
      
      if (!response.ok) {
        clearTimeout(timeoutId);
        throw new Error(`HTTP error! status: ${response.status}`);
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
            console.log('[STREAMING] Stream ended, receivedComplete:', receivedComplete);
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
                console.log('[STREAMING] Received [DONE] marker');
                clearTimeout(timeoutId);
                return;
              }
              if (!data) continue;  // Skip empty lines
              
              try {
                const parsed = JSON.parse(data);
                console.log('[STREAMING] Received event:', parsed.type);
                
                if (parsed.type === 'content' && onChunk) {
                  fullStreamedContent += parsed.chunk;
                  onChunk(parsed.chunk);
                }
                else if (parsed.type === 'auto_play_ready' && onAutoPlayReady) {
                  // Connect to TTS immediately when session is ready
                  onAutoPlayReady(parsed.auto_play_session_id, parsed.scene_id);
                }
                else if (parsed.type === 'complete' && onComplete) {
                  receivedComplete = true;
                  clearTimeout(timeoutId);
                  // Log verification info
                  console.log('=== SCENE GENERATION COMPLETE ===');
                  console.log('Full streamed content length:', fullStreamedContent.length);
                  console.log('Contains ###CHOICES###:', fullStreamedContent.includes('###CHOICES###'));
                  console.log('Parsed choices count:', parsed.choices?.length || 0);
                  console.log('Scene ID:', parsed.scene_id);
                  console.log('================================');
                  onComplete(parsed.scene_id, parsed.choices || [], parsed.auto_play);
                  return;  // Exit after complete event
                }
                else if (parsed.type === 'error' && onError) {
                  clearTimeout(timeoutId);
                  onError(parsed.message);
                  return;
                }
                else if (parsed.type === 'extraction_status' && onExtractionStatus) {
                  onExtractionStatus(parsed.status, parsed.message);
                }
                else if (parsed.type === 'start') {
                  console.log('[STREAMING] Generation started, sequence:', parsed.sequence);
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
        const errorMsg = receivedComplete 
          ? 'Stream timeout after completion' 
          : 'Stream timeout - generation may still be in progress';
        console.error('[STREAMING]', errorMsg);
        if (onError) onError(errorMsg);
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
  async createSceneVariant(storyId: number, sceneId: number, customPrompt?: string) {
    return this.request<{ message: string; variant: any; auto_play_session_id?: string }>(`/api/stories/${storyId}/scenes/${sceneId}/variants`, {
      method: 'POST',
      body: JSON.stringify({ custom_prompt: customPrompt }),
    });
  }

  async createSceneVariantStreaming(
    storyId: number,
    sceneId: number,
    customPrompt = '',
    variantId?: number,
    onChunk?: (chunk: string) => void,
    onComplete?: (variant: any) => void,
    onError?: (error: string) => void,
    onAutoPlayReady?: (sessionId: string) => void
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
          variant_id: variantId
        })
      });
      
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      
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

  async regenerateSceneVariantChoices(storyId: number, sceneId: number, variantId: number) {
    return this.request<{ message: string; choices: Array<{ id: number | null; text: string; order: number }> }>(`/api/stories/${storyId}/scenes/${sceneId}/variants/${variantId}/regenerate-choices`, {
      method: 'POST',
    });
  }

  // Scene Continuation
  async continueScene(storyId: number, sceneId: number, customPrompt?: string) {
    return this.request<{ message: string; scene: any }>(`/api/stories/${storyId}/scenes/${sceneId}/continue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_prompt: customPrompt }),
    });
  }

  async continueSceneStreaming(
    storyId: number,
    sceneId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (sceneId: number, newContent: string) => void,
    onError?: (error: string) => void
  ) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/${sceneId}/continue/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ custom_prompt: customPrompt }),
      });

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
              else if (parsed.type === 'complete' && onComplete) onComplete(parsed.scene_id, parsed.new_content);
              else if (parsed.type === 'error' && onError) onError(parsed.message);
            } catch (e) {
              // ignore non-JSON lines
            }
          }
        }
      }
    } catch (error) {
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
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/${characterId}`);
  }

  async getCharacters(skip = 0, limit = 50, includePublic = true, templatesOnly = false) {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit), include_public: String(includePublic), templates_only: String(templatesOnly) });
    return this.request<Array<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>>(`/api/characters/?${params}`);
  }

  async deleteCharacter(characterId: number) {
    return this.request<{ message: string; }>(`/api/characters/${characterId}`, { method: 'DELETE' });
  }

  async updateCharacter(characterId: number, data: { name?: string; description?: string; personality_traits?: string[]; background?: string; goals?: string; fears?: string; appearance?: string; is_template?: boolean; is_public?: boolean; }) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/${characterId}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async createCharacter(data: { name: string; description?: string; personality_traits?: string[]; background?: string; goals?: string; fears?: string; appearance?: string; is_template?: boolean; is_public?: boolean; }) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/`, { method: 'POST', body: JSON.stringify(data) });
  }

  async generateCharacterWithAI(prompt: string, storyContext?: { genre?: string; tone?: string; world_setting?: string }, previousGeneration?: any) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; background_structured?: Record<string, any>; goals_structured?: Record<string, any>; fears_structured?: Record<string, any>; appearance_structured?: Record<string, any> }>(`/api/characters/generate-with-ai`, {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        story_context: storyContext || null,
        previous_generation: previousGeneration || null
      })
    });
  }

  // Character Assistant API
  async checkCharacterImportance(storyId: number, chapterId?: number) {
    const params = chapterId ? `?chapter_id=${chapterId}` : '';
    return this.request<{ new_character_detected: boolean }>(`/api/stories/${storyId}/character-importance-check${params}`);
  }

  async getCharacterSuggestions(storyId: number, chapterId?: number) {
    const params = chapterId ? `?chapter_id=${chapterId}` : '';
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
    }>(`/api/stories/${storyId}/character-suggestions${params}`);
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
      confidence: number;
      scenes_analyzed: number[];
    }>(`/api/stories/${storyId}/character-suggestions/${encodeURIComponent(characterName)}/analyze`, {
      method: 'POST'
    });
  }

  async createCharacterFromSuggestion(storyId: number, characterName: string, characterData: {
    name: string;
    description: string;
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
  }) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
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
  }) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      pov: string | null;
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
    }>(`/api/writing-presets/default/template`);
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

  async updateChapter(storyId: number, chapterId: number, data: {
    title?: string;
    description?: string;
    story_so_far?: string;
    auto_summary?: string;
    plot_point?: string;
    story_character_ids?: number[];
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
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

  async addCharacterToChapter(storyId: number, chapterId: number, characterId?: number, storyCharacterId?: number) {
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
    }>(`/api/stories/${storyId}/chapters/${chapterId}/characters`, {
      method: 'POST',
      body: JSON.stringify({ character_id: characterId, story_character_id: storyCharacterId }),
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
