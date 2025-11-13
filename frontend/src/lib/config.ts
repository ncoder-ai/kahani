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
 * Get API base URL for fetching config
 * Uses window.location to detect current host
 */
function getConfigApiBaseUrl(): string {
  if (typeof window === 'undefined') {
    // Server-side: require environment variable (no hardcoded default)
    if (!process.env.NEXT_PUBLIC_API_URL) {
      throw new Error('NEXT_PUBLIC_API_URL environment variable must be set for server-side rendering');
    }
    return process.env.NEXT_PUBLIC_API_URL;
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
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // If no NEXT_PUBLIC_API_URL and not reverse proxy, we cannot determine backend URL
  // User must set NEXT_PUBLIC_API_URL environment variable for direct access
  throw new Error(
    'NEXT_PUBLIC_API_URL environment variable must be set for direct access (non-reverse-proxy) deployments. ' +
    'Set it to the full backend URL (e.g., http://hostname:9876) or use a reverse proxy.'
  );
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
      let apiBaseUrl: string;
      try {
        apiBaseUrl = getConfigApiBaseUrl();
      } catch (error) {
        // Cannot determine API URL - configuration must be set up properly
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        throw new Error(
          `Cannot determine backend API URL for config fetch: ${errorMsg}. ` +
          `For direct access, set NEXT_PUBLIC_API_URL environment variable (e.g., http://hostname:9876). ` +
          `For reverse proxy deployments, ensure the frontend is accessed via standard ports (80/443) or set NEXT_PUBLIC_API_URL.`
        );
      }
      const response = await fetch(`${apiBaseUrl}/api/config/frontend`);

      if (!response.ok) {
        throw new Error(`Failed to load config: ${response.status} ${response.statusText}`);
      }

      const config = await response.json();
      configCache = config;
      return config;
    } catch (error) {
      console.error('Failed to load frontend config:', error);
      // Return empty config object - caller should handle this
      throw new Error(`Configuration API unavailable: ${error instanceof Error ? error.message : 'Unknown error'}`);
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

