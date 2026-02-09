/**
 * Base API client with shared HTTP infrastructure
 *
 * This module provides:
 * - Circuit breaker for fault tolerance
 * - Retry logic with exponential backoff
 * - Request timeout management
 * - Token refresh handling
 * - Error classification and handling
 */

import { getApiBaseUrl as getApiBaseUrlFromConfig, getApiBaseUrlSync as getApiBaseUrlSyncFromConfig } from '../apiUrl';

/**
 * Normalize API URL by adding default port if missing
 */
function normalizeApiUrl(url: string): string {
  try {
    const urlObj = new URL(url);
    if (!urlObj.port && urlObj.protocol === 'http:') {
      urlObj.port = '9876';
    }
    let normalized = urlObj.href;
    if (normalized.endsWith('/')) {
      normalized = normalized.slice(0, -1);
    }
    return normalized;
  } catch {
    return url;
  }
}

/**
 * Circuit Breaker to prevent hammering an unresponsive backend
 */
class CircuitBreaker {
  private failures = 0;
  private lastFailureTime = 0;
  private isOpen = false;

  private readonly failureThreshold = 5;
  private readonly resetTimeMs = 30000;

  shouldBlock(): boolean {
    if (!this.isOpen) return false;

    if (Date.now() - this.lastFailureTime > this.resetTimeMs) {
      this.isOpen = false;
      this.failures = 0;
      console.log('[CircuitBreaker] Circuit closed, allowing requests');
      return false;
    }

    return true;
  }

  recordSuccess(): void {
    this.failures = 0;
    if (this.isOpen) {
      this.isOpen = false;
      console.log('[CircuitBreaker] Circuit closed after successful request');
    }
  }

  recordFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();

    if (this.failures >= this.failureThreshold && !this.isOpen) {
      this.isOpen = true;
      console.warn(`[CircuitBreaker] Circuit opened after ${this.failures} failures. Will retry in ${this.resetTimeMs / 1000}s`);
    }
  }

  getTimeUntilReset(): number {
    if (!this.isOpen) return 0;
    const elapsed = Date.now() - this.lastFailureTime;
    return Math.max(0, this.resetTimeMs - elapsed);
  }
}

// Global circuit breaker instance
export const circuitBreaker = new CircuitBreaker();

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
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Check if an error is retryable
 */
export function isRetryableError(error: unknown, statusCode?: number): boolean {
  if (error instanceof TypeError && error.message === 'Load failed') {
    return true;
  }

  if (error instanceof Error && error.name === 'AbortError') {
    return true;
  }

  if (statusCode && statusCode >= 500) {
    return true;
  }

  if (statusCode === 429) {
    return true;
  }

  return false;
}

// Runtime API URL detection
async function getApiBaseUrl(): Promise<string> {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }

  try {
    const url = await getApiBaseUrlFromConfig();
    return normalizeApiUrl(url);
  } catch (error) {
    throw new Error(`Unable to determine API URL: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

// Synchronous version for backward compatibility
function getApiBaseUrlSync(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }
  const url = getApiBaseUrlSyncFromConfig();
  return normalizeApiUrl(url);
}

/**
 * Shared token storage for all BaseApiClient instances.
 * Ensures token updates (login, refresh) are visible to every API singleton.
 */
const sharedTokenStore = {
  token: null as string | null,

  load() {
    if (typeof window !== 'undefined') {
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
  },

  set(token: string) {
    this.token = token;
  },

  clear() {
    this.token = null;
  },
};

/**
 * Sync a token to the shared store so all modular API clients see it.
 * Called by the legacy ApiClient when its token is set/cleared.
 */
export function syncTokenToModularClients(token: string | null) {
  if (token) {
    sharedTokenStore.set(token);
  } else {
    sharedTokenStore.clear();
  }
}

/**
 * Base API Client class with shared HTTP infrastructure
 */
export class BaseApiClient {
  protected baseURL: string;
  private cachedTimeoutMs: number | null = null;
  private isFetchingTimeout: boolean = false;

  protected get token(): string | null {
    return sharedTokenStore.token;
  }

  constructor(baseURL?: string) {
    if (baseURL) {
      this.baseURL = baseURL;
    } else {
      try {
        this.baseURL = getApiBaseUrlSync();
      } catch {
        this.baseURL = '';
      }
    }
    sharedTokenStore.load();
  }

  async initialize(): Promise<void> {
    try {
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('API URL initialization timeout after 10 seconds')), 10000);
      });

      this.baseURL = await Promise.race([
        getApiBaseUrl(),
        timeoutPromise
      ]);
    } catch (error) {
      console.error('Failed to initialize API URL from config:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      throw new Error(`Failed to connect to backend: ${errorMessage}. Please ensure the backend server is running.`);
    }
  }

  private loadToken() {
    sharedTokenStore.load();
  }

  private async handleTokenRefresh() {
    if (typeof window !== 'undefined') {
      const { useAuthStore } = await import('@/store');
      const refreshAccessToken = useAuthStore.getState().refreshAccessToken;
      return await refreshAccessToken();
    }
    return false;
  }

  setToken(token: string) {
    sharedTokenStore.set(token);
  }

  removeToken() {
    sharedTokenStore.clear();
    this.cachedTimeoutMs = null;
  }

  /**
   * Clear the cached timeout to force re-fetch on next request
   */
  clearCachedTimeout() {
    this.cachedTimeoutMs = null;
  }

  protected async getRequestTimeout(endpoint?: string): Promise<number> {
    const isAuthEndpoint = endpoint && (endpoint.includes('/api/auth/login') || endpoint.includes('/api/auth/register'));

    if (isAuthEndpoint) {
      return 30000;
    }

    if (this.cachedTimeoutMs !== null) {
      return this.cachedTimeoutMs;
    }

    if (!this.token) {
      return 30000;
    }

    if (this.isFetchingTimeout) {
      return 300000;
    }

    if (endpoint && endpoint.includes('/api/settings')) {
      return 300000;
    }

    this.isFetchingTimeout = true;
    try {
      // Use a direct fetch to avoid circular dependency
      const url = `${this.baseURL}/api/settings/`;
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.token}`
        }
      });

      if (response.ok) {
        const settingsResponse = await response.json();
        const timeoutTotal = settingsResponse?.settings?.llm_settings?.timeout_total;

        if (timeoutTotal && typeof timeoutTotal === 'number' && timeoutTotal > 0) {
          this.cachedTimeoutMs = (timeoutTotal + 10) * 1000;
          this.isFetchingTimeout = false;
          return this.cachedTimeoutMs;
        }
      }
    } catch (error) {
      console.warn('[API] Failed to fetch user settings for timeout, using default:', error);
    } finally {
      this.isFetchingTimeout = false;
    }

    this.cachedTimeoutMs = 300000;
    return this.cachedTimeoutMs;
  }

  protected async request<T>(endpoint: string, options: RequestInit = {}, retryCount = 0): Promise<T> {
    const maxRetries = 3;
    const baseDelayMs = 1000;

    if (circuitBreaker.shouldBlock()) {
      const resetTime = Math.ceil(circuitBreaker.getTimeUntilReset() / 1000);
      throw new ApiError(
        `Server temporarily unavailable. Please try again in ${resetTime} seconds.`,
        ApiErrorType.CIRCUIT_OPEN,
        undefined,
        false
      );
    }

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

    const requestTimeoutMs = await this.getRequestTimeout(endpoint);

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

      circuitBreaker.recordSuccess();
      const data = await response.json();
      return data;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof ApiError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          circuitBreaker.recordFailure();
          const timeoutSeconds = Math.round(requestTimeoutMs / 1000);
          console.error(`[API] Request timed out after ${timeoutSeconds} seconds`);

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

        if (error.message === 'Load failed' || error.message === 'Failed to fetch' || error instanceof TypeError) {
          circuitBreaker.recordFailure();
          console.error('[API] Network error:', error.message);

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

  /**
   * Make a streaming request that returns a Response object for SSE handling
   */
  protected async streamingRequest(
    endpoint: string,
    options: RequestInit = {},
    abortSignal?: AbortSignal
  ): Promise<Response> {
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

    const requestTimeoutMs = await this.getRequestTimeout(endpoint);
    const streamingTimeoutMs = requestTimeoutMs * 2;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), streamingTimeoutMs);

    // Combine abort signals if provided
    if (abortSignal) {
      abortSignal.addEventListener('abort', () => controller.abort());
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal
      });

      // Don't clear timeout here - let the caller manage it via the response
      // The caller will handle streaming and cleanup

      if (!response.ok) {
        clearTimeout(timeoutId);
        throw new ApiError(
          `Request failed with status ${response.status}`,
          response.status >= 500 ? ApiErrorType.SERVER_ERROR : ApiErrorType.UNKNOWN,
          response.status,
          response.status >= 500
        );
      }

      // Return response for streaming - caller will handle reading
      return response;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof ApiError) {
        throw error;
      }

      if (error instanceof Error && error.name === 'AbortError') {
        throw new ApiError(
          'Request was cancelled or timed out',
          ApiErrorType.TIMEOUT,
          undefined,
          true
        );
      }

      throw new ApiError(
        error instanceof Error ? error.message : 'Unknown error',
        ApiErrorType.UNKNOWN,
        undefined,
        false
      );
    }
  }

  /**
   * Get the base URL (useful for WebSocket connections)
   */
  getBaseURL(): string {
    return this.baseURL;
  }

  /**
   * Get current token (useful for WebSocket connections)
   */
  getToken(): string | null {
    return this.token;
  }
}
