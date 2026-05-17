/**
 * JWT utilities for client-side token handling
 * Note: This does NOT verify the token signature - that's the server's job.
 * This is only used to read expiration times for proactive refresh scheduling.
 */

export interface JWTPayload {
  sub: string;      // User ID
  exp: number;      // Expiration timestamp (seconds since epoch)
  type?: string;    // Token type (e.g., "refresh" for refresh tokens)
  iat?: number;     // Issued at timestamp
}

/**
 * Decode a JWT token without verification
 * @param token - The JWT token string
 * @returns The decoded payload or null if invalid
 */
export function decodeJWT(token: string): JWTPayload | null {
  try {
    // JWT format: header.payload.signature
    const parts = token.split('.');
    if (parts.length !== 3) {
      console.warn('[JWT] Invalid token format - expected 3 parts');
      return null;
    }

    // Decode the payload (second part)
    const payload = parts[1];
    
    // Base64Url decode (replace URL-safe chars and add padding)
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
    
    // Decode and parse
    const decoded = atob(padded);
    const parsed = JSON.parse(decoded);
    
    // Validate required fields
    if (typeof parsed.sub !== 'string' || typeof parsed.exp !== 'number') {
      console.warn('[JWT] Token missing required fields (sub, exp)');
      return null;
    }
    
    return parsed as JWTPayload;
  } catch (error) {
    console.error('[JWT] Failed to decode token:', error);
    return null;
  }
}

/**
 * Get the expiration time of a token in milliseconds since epoch
 * @param token - The JWT token string
 * @returns Expiration time in ms, or null if invalid
 */
export function getTokenExpirationMs(token: string): number | null {
  const payload = decodeJWT(token);
  if (!payload) return null;
  
  // exp is in seconds, convert to milliseconds
  return payload.exp * 1000;
}

/**
 * Check if a token is expired
 * @param token - The JWT token string
 * @param bufferMs - Buffer time in ms to consider token expired early (default: 0)
 * @returns true if expired (or will expire within buffer), false otherwise
 */
export function isTokenExpired(token: string, bufferMs: number = 0): boolean {
  const expirationMs = getTokenExpirationMs(token);
  if (expirationMs === null) return true; // Invalid token = expired
  
  return Date.now() + bufferMs >= expirationMs;
}

/**
 * Get time until token expires in milliseconds
 * @param token - The JWT token string
 * @returns Time until expiration in ms, or 0 if already expired, or null if invalid
 */
export function getTimeUntilExpiration(token: string): number | null {
  const expirationMs = getTokenExpirationMs(token);
  if (expirationMs === null) return null;
  
  const remaining = expirationMs - Date.now();
  return Math.max(0, remaining);
}

/**
 * Check if a token is a refresh token
 * @param token - The JWT token string
 * @returns true if it's a refresh token
 */
export function isRefreshToken(token: string): boolean {
  const payload = decodeJWT(token);
  return payload?.type === 'refresh';
}

/**
 * Get the current auth token from the Zustand store
 * This is a utility for components that need the token outside of React context
 * @returns The current access token or empty string if not authenticated
 */
export function getAuthToken(): string {
  if (typeof window === 'undefined') return '';
  
  try {
    const authStorage = localStorage.getItem('auth-storage');
    if (authStorage) {
      const parsed = JSON.parse(authStorage);
      return parsed.state?.token || '';
    }
  } catch (e) {
    console.warn('[JWT] Failed to get auth token from store:', e);
  }
  
  return '';
}

