'use client';

import { useEffect, useState, useCallback, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore, useHasHydrated } from '@/store';
import PinLockGate from '@/components/security/PinLockGate';

// Constants for session expiry warnings
const SESSION_WARNING_MS = 60 * 1000; // Show warning 1 minute before expiry

interface RouteProtectionProps {
  children: ReactNode;
  requireAuth?: boolean;
  requireApproval?: boolean;
  requireAdmin?: boolean;
}

/**
 * Route Protection Component
 * 
 * Protects routes based on authentication and authorization requirements.
 * Also monitors session expiry and redirects to login when session expires.
 * 
 * @param requireAuth - Requires user to be logged in (default: true)
 * @param requireApproval - Requires user to be approved by admin (default: true)
 * @param requireAdmin - Requires user to be an admin (default: false)
 */
export default function RouteProtection({
  children,
  requireAuth = true,
  requireApproval = true,
  requireAdmin = false,
}: RouteProtectionProps) {
  const router = useRouter();
  const pathname = usePathname();
  const {
    user,
    isAuthenticated,
    refreshToken,
    accessTokenExpiresAt,
    refreshTokenExpiresAt,
    logout,
    refreshAccessToken,
  } = useAuthStore();
  const hasHydrated = useHasHydrated();

  // State for session expiry warning
  const [showSessionWarning, setShowSessionWarning] = useState(false);
  const [timeUntilExpiry, setTimeUntilExpiry] = useState<number | null>(null);
  const [isExtending, setIsExtending] = useState(false);
  const [extendError, setExtendError] = useState<string | null>(null);

  /**
   * Handle session expiry - redirect to login
   */
  const handleSessionExpired = useCallback(() => {
    console.warn('[RouteProtection] Session expired, redirecting to login. refreshToken:', !!refreshToken, 'refreshTokenExpiresAt:', refreshTokenExpiresAt, 'accessTokenExpiresAt:', accessTokenExpiresAt, 'now:', Date.now());
    logout();
    router.push(`/login?redirect=${encodeURIComponent(pathname)}&expired=true`);
  }, [logout, router, pathname, refreshToken, refreshTokenExpiresAt, accessTokenExpiresAt]);

  /**
   * Handler for the "Stay signed in" button on the warning banner.
   * If a refresh token is available, calls the refresh endpoint and
   * dismisses the warning on success. If no refresh token (the user
   * unticked "Keep me signed in" at login), redirect to /login so
   * they can re-enter their password — the only path that issues a
   * fresh access token in that case.
   */
  const handleExtendSession = useCallback(async () => {
    setExtendError(null);
    if (!refreshToken) {
      // No way to renew without re-login; preserve their place.
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }
    setIsExtending(true);
    try {
      const ok = await refreshAccessToken();
      if (ok) {
        setShowSessionWarning(false);
        setTimeUntilExpiry(null);
      } else {
        setExtendError('Could not extend session. Please sign in again.');
      }
    } catch (err) {
      setExtendError('Could not extend session. Please sign in again.');
    } finally {
      setIsExtending(false);
    }
  }, [refreshToken, refreshAccessToken, router, pathname]);

  /**
   * Monitor session expiry and show warnings
   */
  useEffect(() => {
    if (!hasHydrated || !requireAuth || !isAuthenticated) {
      return;
    }

    // Determine which expiration to monitor
    // If we have a refresh token, monitor that (it's the session end)
    // If no refresh token, monitor access token
    const sessionExpiresAt = refreshToken 
      ? refreshTokenExpiresAt 
      : accessTokenExpiresAt;

    if (!sessionExpiresAt) {
      return;
    }

    // Check current state
    const now = Date.now();
    const timeRemaining = sessionExpiresAt - now;

    // If already expired, redirect immediately
    if (timeRemaining <= 0) {
      handleSessionExpired();
      return;
    }

    // Browser setTimeout stores delay as a signed 32-bit int. A refresh-token
    // TTL of 30 days (~2.59B ms) exceeds INT32_MAX (~24.8 days) and fires
    // immediately, which previously logged the user out the moment they
    // landed on a protected route after ticking "Remember me". The 1s
    // interval below covers both the warning threshold and the expiry
    // trigger without needing long-horizon setTimeouts.
    const checkInterval = setInterval(() => {
      const currentTime = Date.now();
      const remaining = sessionExpiresAt - currentTime;

      if (remaining <= 0) {
        clearInterval(checkInterval);
        handleSessionExpired();
        return;
      }

      if (remaining <= SESSION_WARNING_MS && !showSessionWarning) {
        setShowSessionWarning(true);
      }

      if (showSessionWarning) {
        setTimeUntilExpiry(Math.ceil(remaining / 1000));
      }
    }, 1000);

    return () => {
      clearInterval(checkInterval);
    };
  }, [
    hasHydrated, 
    requireAuth, 
    isAuthenticated, 
    refreshToken,
    accessTokenExpiresAt, 
    refreshTokenExpiresAt, 
    handleSessionExpired,
    showSessionWarning
  ]);

  // Basic auth check effect
  useEffect(() => {
    // Wait for store to hydrate before checking authentication
    if (!hasHydrated) {
      return;
    }

    // Skip protection if not required
    if (!requireAuth) {
      return;
    }

    // Check authentication
    if (!isAuthenticated || !user) {
      console.warn('[RouteProtection] Auth check failed, redirecting. isAuthenticated:', isAuthenticated, 'user:', !!user);
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }

    // Check admin requirement
    if (requireAdmin && !user.is_admin) {
      router.push('/dashboard');
      return;
    }

    // Check approval requirement (skip for admins)
    if (requireApproval && !user.is_approved && !user.is_admin) {
      router.push('/pending-approval');
      return;
    }

  }, [hasHydrated, isAuthenticated, user, requireAuth, requireApproval, requireAdmin, router, pathname]);

  // Don't render anything if requirements not met
  if (requireAuth && (!hasHydrated || !isAuthenticated || !user)) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-white">
          <div className="w-12 h-12 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (requireAdmin && user && !user.is_admin) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-8 shadow-2xl text-center">
          <div className="w-20 h-20 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white mb-4">Access Denied</h1>
          <p className="text-white/70 mb-6">You don&apos;t have permission to access this page.</p>
          <button
            onClick={() => router.push('/dashboard')}
            className="w-full py-3 px-4 theme-btn-primary rounded-lg font-semibold transition-all"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (requireApproval && user && !user.is_approved && !user.is_admin) {
    return null; // Will redirect in useEffect
  }

  return (
    <>
      {/* Session Expiry Warning Banner */}
      {showSessionWarning && timeUntilExpiry !== null && timeUntilExpiry > 0 && (
        <div className="fixed top-0 left-0 right-0 z-[9999] bg-amber-600 text-white px-4 py-3 shadow-lg">
          <div className="flex flex-wrap items-center justify-center gap-3">
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="font-medium">
              Your session will expire in {timeUntilExpiry}s.
            </span>
            <button
              onClick={handleExtendSession}
              disabled={isExtending}
              className="px-3 py-1 text-sm font-semibold bg-white text-amber-700 rounded hover:bg-amber-50 disabled:opacity-60 disabled:cursor-wait shadow-sm"
            >
              {isExtending ? 'Extending…' : (refreshToken ? 'Stay signed in' : 'Sign in again')}
            </button>
            {extendError && (
              <span className="text-xs text-amber-100 font-normal">{extendError}</span>
            )}
          </div>
        </div>
      )}
      <PinLockGate>{children}</PinLockGate>
    </>
  );
}
