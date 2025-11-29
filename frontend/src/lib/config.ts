/**
 * Frontend Configuration Service
 * Fetches configuration from backend API and caches it
 */

export interface FrontendConfig {
  server: {
    backend: {
      port: number;
      host: string;
    };
    frontend: {
      port: number;
    };
  };
  tts: {
    default_providers: {
      openai_compatible: string;
      chatterbox: string;
      kokoro: string;
    };
  };
  extraction: {
    default_url: string;
  };
  websocket: {
    stt_path: string;
    tts_path: string;
  };
}

let configCache: FrontendConfig | null = null;
let configLoadPromise: Promise<FrontendConfig> | null = null;

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
 * Get API base URL for fetching config
 * Uses window.location to detect current host
 */
function getConfigApiBaseUrl(): string {
  if (typeof window === 'undefined') {
    // Server-side: require environment variable (no hardcoded default)
    if (!process.env.NEXT_PUBLIC_API_URL) {
      throw new Error('NEXT_PUBLIC_API_URL environment variable must be set for server-side rendering');
    }
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }

  // Client-side: use window.location to build API URL
  const protocol = window.location.protocol;
  const hostname = window.location.hostname;
  const port = window.location.port;

  // Check if we're using a reverse proxy (no port in URL or standard ports)
  const isReverseProxy = !port || port === '80' || port === '443';

  if (isReverseProxy) {
    // For reverse proxy: use /api on the same domain
    return `${protocol}//${hostname}`;
  }

  // For direct access: check NEXT_PUBLIC_API_URL first
  if (process.env.NEXT_PUBLIC_API_URL) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
  }

  // If no NEXT_PUBLIC_API_URL and not reverse proxy, we cannot determine backend URL
  // User must set NEXT_PUBLIC_API_URL environment variable for direct access
  throw new Error(
    'NEXT_PUBLIC_API_URL environment variable must be set for direct access (non-reverse-proxy) deployments. ' +
    'Set it to the full backend URL (e.g., http://hostname:9876) or use a reverse proxy.'
  );
}

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Fetch config with retry logic
 */
async function fetchConfigWithRetry(configUrl: string, maxRetries: number = 3): Promise<FrontendConfig> {
  let lastError: Error | null = null;
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
      
      const response = await fetch(configUrl, {
        signal: controller.signal,
        mode: 'cors'
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`Failed to load config: ${response.status} ${response.statusText}`);
      }
      
      const config = await response.json();
      return config;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Unknown error');
      
      // Don't retry on non-retryable errors
      if (lastError.message.includes('404') || lastError.message.includes('403')) {
        throw lastError;
      }
      
      // Wait before retrying (exponential backoff)
      if (attempt < maxRetries - 1) {
        const delay = 1000 * Math.pow(2, attempt);
        console.warn(`[Config] Retry ${attempt + 1}/${maxRetries} in ${delay}ms: ${lastError.message}`);
        await sleep(delay);
      }
    }
  }
  
  throw lastError || new Error('Failed to load config after retries');
}

/**
 * Load configuration from backend API
 */
async function loadConfig(): Promise<FrontendConfig> {
  if (configCache) {
    return configCache;
  }

  // If already loading, return the same promise
  if (configLoadPromise) {
    return configLoadPromise;
  }

  configLoadPromise = (async () => {
    try {
      let apiBaseUrl: string | undefined;
      try {
        apiBaseUrl = getConfigApiBaseUrl();
      } catch (error) {
        // If error is about NEXT_PUBLIC_API_URL not being set for direct access, try common backend ports
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        if (errorMsg.includes('NEXT_PUBLIC_API_URL') && typeof window !== 'undefined') {
          
          // Extract hostname and protocol from browser URL (already available)
          const hostname = window.location.hostname;
          let protocol = window.location.protocol; // Returns "http:" or "https:"
          
          // Ensure we have a valid protocol (default to http if missing or invalid)
          if (!protocol || !protocol.endsWith(':')) {
            protocol = 'http:';
          }
          
          // Try common backend ports: 9876 (default from config.yaml), 8000, 3000
          const commonPorts = [9876, 8000, 3000];
          
          for (const port of commonPorts) {
            // Construct absolute URL: protocol includes colon, so "http://" not "http:///"
            // Ensure it's a proper absolute URL starting with http:// or https://
            // Use new URL() to ensure proper URL construction
            let testUrl: string;
            try {
              testUrl = new URL(`${protocol}//${hostname}:${port}`).href;
            } catch (urlError) {
              // Fallback to string construction if URL constructor fails
              testUrl = `${protocol}//${hostname}:${port}`;
            }
            
            try {
              // Create abort controller for timeout
              const controller = new AbortController();
              const timeoutId = setTimeout(() => controller.abort(), 3000);
              
              // Use new URL() to ensure it's properly formatted
              const absoluteUrl = new URL('/api/config/frontend', testUrl).href;
              
              const testResponse = await fetch(absoluteUrl, {
                method: 'GET',
                signal: controller.signal,
                // Add mode to ensure it's treated as a cross-origin request if needed
                mode: 'cors'
              });
              
              clearTimeout(timeoutId);
              
              if (testResponse.ok) {
                apiBaseUrl = testUrl;
                break;
              }
            } catch (fetchError) {
              // Continue to next port (timeout, network error, etc.)
              continue;
            }
          }
          
          // If we found a working backend, use it; otherwise throw original error
          if (!apiBaseUrl) {
            throw new Error(
              `Cannot determine backend API URL for config fetch: ${errorMsg}. ` +
              `Tried common ports (9876, 8000, 3000) on ${hostname} but none responded. ` +
              `For direct access, set NEXT_PUBLIC_API_URL environment variable (e.g., http://${hostname}:9876). ` +
              `For reverse proxy deployments, ensure the frontend is accessed via standard ports (80/443) or set NEXT_PUBLIC_API_URL.`
            );
          }
        } else {
          // Re-throw other errors
          throw new Error(
            `Cannot determine backend API URL for config fetch: ${errorMsg}. ` +
            `For direct access, set NEXT_PUBLIC_API_URL environment variable (e.g., http://hostname:9876). ` +
            `For reverse proxy deployments, ensure the frontend is accessed via standard ports (80/443) or set NEXT_PUBLIC_API_URL.`
          );
        }
      }
      
      // Ensure apiBaseUrl is defined before using it
      if (!apiBaseUrl) {
        throw new Error('Failed to determine API base URL');
      }
      // Ensure apiBaseUrl is an absolute URL using URL constructor
      let configUrl: string;
      try {
        configUrl = new URL('/api/config/frontend', apiBaseUrl).href;
      } catch (urlError) {
        // Fallback to string concatenation if URL constructor fails
        configUrl = `${apiBaseUrl}/api/config/frontend`;
      }
      
      // Fetch config with retry logic
      const config = await fetchConfigWithRetry(configUrl);
      configCache = config;
      return config;
    } catch (error) {
      console.error('Failed to load frontend config:', error);
      // Provide a more helpful error message
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      throw new Error(`Configuration API unavailable: ${errorMsg}. Please ensure the backend server is running.`);
    } finally {
      configLoadPromise = null;
    }
  })();

  return configLoadPromise;
}

/**
 * Get frontend configuration
 * Returns cached config or loads it from API
 */
export async function getFrontendConfig(): Promise<FrontendConfig> {
  return loadConfig();
}

/**
 * Get backend port from config
 */
export async function getBackendPort(): Promise<number> {
  const config = await getFrontendConfig();
  return config.server.backend.port;
}

/**
 * Get TTS provider default URLs
 */
export async function getTTSProviderUrls(): Promise<{
  openai_compatible: string;
  chatterbox: string;
  kokoro: string;
}> {
  const config = await getFrontendConfig();
  return config.tts.default_providers;
}

/**
 * Get extraction model default URL
 */
export async function getExtractionDefaultUrl(): Promise<string> {
  const config = await getFrontendConfig();
  return config.extraction.default_url;
}

/**
 * Get STT WebSocket path
 */
export async function getSTTWebSocketPath(): Promise<string> {
  const config = await getFrontendConfig();
  return config.websocket.stt_path;
}

/**
 * Get TTS WebSocket path
 */
export async function getTTSWebSocketPath(): Promise<string> {
  const config = await getFrontendConfig();
  return config.websocket.tts_path;
}

/**
 * Clear config cache (useful for testing or reloading)
 */
export function clearConfigCache(): void {
  configCache = null;
  configLoadPromise = null;
}

