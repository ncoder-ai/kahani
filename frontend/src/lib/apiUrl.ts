/**
 * Get the dynamic API base URL based on the current environment
 * This ensures API calls work for both localhost and remote access
 */
export const getApiBaseUrl = (): string => {
  // Server-side: use environment variable or container name
  if (typeof window === 'undefined') {
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9876';
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

  // For direct access: use explicit backend port
  return `${protocol}//${hostname}:9876`;
};

