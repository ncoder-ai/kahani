/**
 * Get the dynamic API base URL based on the current environment
 * Uses React context if available, otherwise falls back to config API
 */
import { getBackendPort } from './config';

let cachedBackendPort: number | null = null;

// Export cached port for synchronous access
export function getCachedBackendPort(): number | null {
  return cachedBackendPort;
}

// Global variable to store config from React context
// This is set by ConfigProvider when it loads config
let contextConfig: { backendPort: number } | null = null;

/**
 * Set config from React context (called by ConfigProvider)
 * This allows apiUrl.ts to use cached config without React dependencies
 */
export function setContextConfig(backendPort: number): void {
  contextConfig = { backendPort };
  cachedBackendPort = backendPort; // Also update cached port for sync version
}

/**
 * Clear context config (useful for testing)
 */
export function clearContextConfig(): void {
  contextConfig = null;
  cachedBackendPort = null;
}

async function detectBackendPort(): Promise<number> {
  // First check if we have config from React context (fastest path - no API call)
  if (contextConfig) {
    return contextConfig.backendPort;
  }

  // Check cached port (from previous direct API call)
  if (cachedBackendPort !== null) {
    return cachedBackendPort;
  }

  // Fallback: Get from config API (only if context not available)
  // This should rarely happen if ConfigProvider is mounted
  // Add timeout to prevent hanging
  try {
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Config fetch timeout')), 5000); // 5 second timeout
    });
    
    cachedBackendPort = await Promise.race([
      getBackendPort(),
      timeoutPromise
    ]);
    return cachedBackendPort;
  } catch (error) {
    // If config fetch fails, try common ports as fallback
    console.warn('[API URL] Config fetch failed, trying common ports:', error);
    
    if (typeof window !== 'undefined') {
      const hostname = window.location.hostname;
      const protocol = window.location.protocol;
      const commonPorts = [9876, 8000, 3000]; // Common backend ports
      
      for (const port of commonPorts) {
        try {
          const testUrl = `${protocol}//${hostname}:${port}`;
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout per port
          
          const response = await fetch(`${testUrl}/api/config/frontend`, {
            signal: controller.signal,
            mode: 'cors'
          });
          
          clearTimeout(timeoutId);
          
          if (response.ok) {
            const config = await response.json();
            const detectedPort = config.server?.backend?.port || port;
            cachedBackendPort = detectedPort;
            return detectedPort;
          }
        } catch (testError) {
          // Continue to next port
          continue;
        }
      }
    }
    
    // If all attempts failed, throw with helpful message
    throw new Error(
      'Unable to connect to backend server. Please ensure the backend is running. ' +
      'Tried to fetch config and common ports (9876, 8000, 3000) but none responded.'
    );
  }
}

export const getApiBaseUrl = async (): Promise<string> => {
  // Server-side: use environment variable
  if (typeof window === 'undefined') {
    if (process.env.NEXT_PUBLIC_API_URL) {
      return process.env.NEXT_PUBLIC_API_URL;
    }
    // Server-side without env var: try to get from config
    try {
      const port = await detectBackendPort();
      return `http://localhost:${port}`;
    } catch {
      throw new Error('NEXT_PUBLIC_API_URL must be set for server-side rendering');
    }
  }

  // Client-side: use window.location to build API URL
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;
  const port = window.location.port;

  // Check if we're using a reverse proxy (no port in URL or standard ports)
  const isReverseProxy = !port || port === '80' || port === '443';

  if (isReverseProxy) {
    // For reverse proxy: use /api on the same domain
    return `${protocol}//${hostname}`;
  }

  // For direct access: get backend port from config
  const backendPort = await detectBackendPort();
  return `${protocol}//${hostname}:${backendPort}`;
};

// Synchronous version for backward compatibility (uses cached port or throws)
export const getApiBaseUrlSync = (): string => {
  if (typeof window === 'undefined') {
    if (process.env.NEXT_PUBLIC_API_URL) {
      return process.env.NEXT_PUBLIC_API_URL;
    }
    throw new Error('NEXT_PUBLIC_API_URL must be set for server-side rendering, or call async getApiBaseUrl()');
  }

  const hostname = window.location.hostname;
  const protocol = window.location.protocol;
  const port = window.location.port;

  const isReverseProxy = !port || port === '80' || port === '443';

  if (isReverseProxy) {
    return `${protocol}//${hostname}`;
  }

  // If port not cached yet (neither from context nor direct load), throw error
  if (cachedBackendPort === null) {
    throw new Error('Backend port not yet loaded. Ensure ConfigProvider is mounted or config API is available.');
  }

  return `${protocol}//${hostname}:${cachedBackendPort}`;
};

