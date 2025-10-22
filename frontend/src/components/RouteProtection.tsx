'use client';

import { useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore, useHasHydrated } from '@/store';

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
  const { user, isAuthenticated } = useAuthStore();
  const hasHydrated = useHasHydrated();

  useEffect(() => {
    // Wait for store to hydrate before checking authentication
    if (!hasHydrated) {
      console.log('[RouteProtection] Waiting for store hydration...');
      return;
    }

    // Skip protection if not required
    if (!requireAuth) {
      return;
    }

    // Check authentication
    if (!isAuthenticated || !user) {
      console.log('[RouteProtection] User not authenticated, redirecting to login');
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }

    // Check admin requirement
    if (requireAdmin && !user.is_admin) {
      console.log('[RouteProtection] User is not admin, access denied');
      router.push('/dashboard');
      return;
    }

    // Check approval requirement (skip for admins)
    if (requireApproval && !user.is_approved && !user.is_admin) {
      console.log('[RouteProtection] User not approved, redirecting to pending approval page');
      router.push('/pending-approval');
      return;
    }

    console.log('[RouteProtection] Access granted');
  }, [hasHydrated, isAuthenticated, user, requireAuth, requireApproval, requireAdmin, router, pathname]);

  // Don't render anything if requirements not met
  if (requireAuth && (!hasHydrated || !isAuthenticated || !user)) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center">
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
          <p className="text-white/70 mb-6">You don't have permission to access this page.</p>
          <button
            onClick={() => router.push('/dashboard')}
            className="w-full py-3 px-4 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-semibold hover:from-purple-600 hover:to-pink-600 transition-all"
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

  return <>{children}</>;
}

