'use client';

import { useState, useEffect, Suspense, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/store';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import { applyTheme } from '@/lib/themes';

function LoginForm() {
  const [identifier, setIdentifier] = useState('');  // Can be email or username
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState(false);

  // Refs to handle mobile autofill race condition
  // On iOS/mobile, autofill may not trigger onChange events, leaving React state empty
  const identifierRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuthStore();

  useEffect(() => {
    // Check if redirected due to session expiry
    if (searchParams.get('expired') === 'true') {
      setSessionExpiredMessage(true);
      return;
    }

    // Clear any stale tokens when landing on login page
    const { logout } = useAuthStore.getState();
    logout();
    // Apply default theme for login page
    applyTheme('pure-dark');

    // Check for SSO auto-login (non-blocking)
    checkSSOLogin();
  }, [searchParams]);

  const checkSSOLogin = async () => {
    // Skip SSO check if not in browser
    if (typeof window === 'undefined') return;

    try {
      // Add timeout to prevent hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const response = await fetch('/api/auth/sso-check', {
        method: 'GET',
        credentials: 'include',
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) return;

      const data = await response.json();

      if (data.access_token && data.user) {
        // SSO login successful - set token and auth state
        apiClient.setToken(data.access_token);
        login(data.user, data.access_token);

        // Wait for Zustand persist to write to localStorage
        await new Promise(resolve => setTimeout(resolve, 100));

        // Redirect based on approval status
        if (!data.user.is_approved && !data.user.is_admin) {
          window.location.href = '/pending-approval';
          return;
        }

        window.location.href = '/dashboard';
      }
    } catch {
      // SSO check failed silently - show login form
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    // CRITICAL: Read values directly from DOM refs to handle mobile autofill
    // On iOS/mobile browsers, password managers may autofill without triggering onChange,
    // leaving React state empty. Reading from refs ensures we get the actual input values.
    const actualIdentifier = identifierRef.current?.value || identifier;
    const actualPassword = passwordRef.current?.value || password;

    // Sync React state with actual values (for UI consistency)
    if (actualIdentifier !== identifier) setIdentifier(actualIdentifier);
    if (actualPassword !== password) setPassword(actualPassword);

    // Validate that we have credentials
    if (!actualIdentifier || !actualPassword) {
      setError('Please enter both email/username and password.');
      setIsLoading(false);
      return;
    }

    try {
      // Initialize API client if needed (this will fetch API URL with timeout)
      try {
        await apiClient.initialize();
      } catch (initError) {
        console.error('Failed to initialize API client:', initError);
        const errorMsg = initError instanceof Error ? initError.message : 'Unknown error';
        // If initialization fails, show a helpful error message
        if (errorMsg.includes('timeout') || errorMsg.includes('connect') || errorMsg.includes('backend')) {
          setError('Unable to connect to the backend server. Please ensure the backend is running and accessible.');
          setIsLoading(false);
          return;
        }
        // For other errors, continue and let login attempt show the error
      }
      
      const response = await apiClient.login(actualIdentifier, actualPassword, rememberMe);
      
      // Set token in API client immediately
      apiClient.setToken(response.access_token);
      
      // Update auth store
      login(response.user, response.access_token, response.refresh_token);
      
      // Check if user is approved
      if (!response.user.is_approved && !response.user.is_admin) {
        router.push('/pending-approval');
        return;
      }
      
      // Check if user wants to auto-open last story (with timeout to prevent hanging)
      try {
        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Settings fetch timeout')), 5000); // 5 second timeout
        });
        
        const lastStoryResponse = await Promise.race([
          apiClient.getLastAccessedStory(),
          timeoutPromise
        ]);
        
        if (lastStoryResponse.auto_open_last_story && lastStoryResponse.last_accessed_story_id) {
          const storyMode = (lastStoryResponse as any).story_mode;
          if (storyMode === 'roleplay') {
            router.push(`/roleplay/${lastStoryResponse.last_accessed_story_id}`);
          } else {
            router.push(`/story/${lastStoryResponse.last_accessed_story_id}`);
          }
        } else {
          router.push('/dashboard');
        }
      } catch (settingsError) {
        console.error('❌ Failed to check auto-redirect settings:', settingsError);
        // Always redirect to dashboard even if settings fetch fails
        router.push('/dashboard');
      }
    } catch (err) {
      console.error('=== LOGIN FAILED ===');
      console.error('Error type:', err instanceof Error ? 'Error' : typeof err);
      console.error('Error message:', err instanceof Error ? err.message : String(err));
      console.error('Full error:', err);
      
      let errorMessage = 'Login failed';
      if (err instanceof Error) {
        const message = err.message.toLowerCase();
        // Check for specific error types
        if (message.includes('timeout') || message.includes('timed out') || message.includes('request timed out')) {
          errorMessage = 'Connection timed out after 30 seconds. The backend server may not be running or is not responding. Please:\n\n' +
            '1. Check if the backend server is running\n' +
            '2. Verify the backend URL is correct\n' +
            '3. Check your network connection\n' +
            '4. Review backend server logs for errors';
        } else if (message.includes('failed to fetch') || message.includes('network error') || message.includes('networkerror') || message.includes('load failed')) {
          errorMessage = 'Network error: Unable to reach the backend server. Please:\n\n' +
            '1. Ensure the backend server is running\n' +
            '2. Check if the backend URL is correct\n' +
            '3. Verify your network connection\n' +
            '4. Check for firewall or CORS issues';
        } else if (message.includes('cors')) {
          errorMessage = 'CORS error: The backend server is blocking the request. Please check backend CORS configuration.';
        } else if (message.includes('unable to connect') || message.includes('connect to backend')) {
          errorMessage = err.message; // Use the detailed error message from initialization
        } else {
          errorMessage = err.message;
        }
      } else if (typeof err === 'string') {
        errorMessage = err;
      }
      
      console.error('Setting error message:', errorMessage);
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen theme-bg-primary flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-8">
        <img src="/kahanilogo.png" alt="Make My Story" className="h-40 w-40 md:h-36 md:w-36 object-contain mx-auto mb-4" />
        <h1 className="text-4xl font-bold text-white mb-2">Make My Story</h1>
        <p className="text-white/80 text-lg">Interactive Storytelling Platform</p>
      </div>

      {/* Login Form */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white/10 backdrop-blur-md border border-white/20 py-8 px-6 shadow-2xl rounded-2xl">
          <h2 className="text-center text-2xl font-bold text-white mb-8">
            Welcome Back
          </h2>

          {sessionExpiredMessage && (
            <div className="mb-6 bg-amber-500/20 border border-amber-400/30 text-amber-100 px-4 py-3 rounded-lg flex items-center gap-2">
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>Your session has expired. Please sign in again.</span>
            </div>
          )}

          {error && (
            <div className="mb-6 bg-red-500/20 border border-red-400/30 text-red-100 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="identifier" className="block text-sm font-medium text-white/80 mb-2">
                Email or Username
              </label>
              <input
                ref={identifierRef}
                id="identifier"
                name="identifier"
                type="text"
                autoComplete="username"
                required
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Enter your email or username"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-white/80 mb-2">
                Password
              </label>
              <input
                ref={passwordRef}
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Enter your password"
              />
            </div>

            <div className="flex items-center">
              <input
                id="remember-me"
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="h-4 w-4 text-gray-600 focus:ring-gray-500 border-gray-300 rounded"
              />
              <label htmlFor="remember-me" className="ml-2 block text-sm text-white/80">
                Remember me for 30 days
              </label>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className={`w-full py-3 px-4 rounded-lg font-semibold transition-all duration-200 ${
                isLoading
                  ? 'bg-white/20 text-white/50 cursor-not-allowed'
                  : 'theme-btn-primary transform hover:scale-105'
              }`}
            >
              {isLoading ? (
                <div className="flex items-center justify-center space-x-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  <span>Signing in...</span>
                </div>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="mt-8">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/30" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-3 bg-white/10 text-white/80 rounded">New to Make My Story?</span>
              </div>
            </div>

            <div className="mt-6">
              <Link
                href="/register"
                className="w-full flex justify-center py-3 px-4 border border-white/30 rounded-lg text-white hover:bg-white/10 transition-colors font-medium"
              >
                Create New Account
              </Link>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-white/60 text-sm">
            Start creating interactive stories with AI assistance
          </p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-white">
          <div className="w-12 h-12 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p>Loading...</p>
        </div>
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}