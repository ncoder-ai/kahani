'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/store';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import { applyTheme } from '@/lib/themes';

function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState(false);
  
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuthStore();

  useEffect(() => {
    // Check if redirected due to session expiry
    if (searchParams.get('expired') === 'true') {
      setSessionExpiredMessage(true);
    }
    
    // Clear any stale tokens when landing on login page
    const { logout } = useAuthStore.getState();
    logout();
    // Apply default theme for login page
    applyTheme('pure-dark');
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      const apiBaseUrl = await getApiBaseUrl();
      
      const response = await apiClient.login(email, password, rememberMe);
      
      // Set token in API client immediately
      apiClient.setToken(response.access_token);
      
      // Update auth store
      login(response.user, response.access_token, response.refresh_token);
      
      // Check if user is approved
      if (!response.user.is_approved && !response.user.is_admin) {
        router.push('/pending-approval');
        return;
      }
      
      // Check if user wants to auto-open last story
      try {
        const lastStoryResponse = await apiClient.getLastAccessedStory();
        
        if (lastStoryResponse.auto_open_last_story && lastStoryResponse.last_accessed_story_id) {
          router.push(`/story/${lastStoryResponse.last_accessed_story_id}`);
        } else {
          router.push('/dashboard');
        }
      } catch (settingsError) {
        console.error('❌ Failed to check auto-redirect settings:', settingsError);
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
        if (message.includes('timeout') || message.includes('timed out')) {
          errorMessage = 'Connection timed out. Please check your network connection and ensure the backend server is running.';
        } else if (message.includes('failed to fetch') || message.includes('network error') || message.includes('networkerror')) {
          errorMessage = 'Network error. Please check your connection and ensure the backend server is accessible.';
        } else if (message.includes('cors')) {
          errorMessage = 'CORS error. Please check backend CORS configuration.';
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
        <h1 className="text-4xl font-bold text-white mb-2">✨ Kahani</h1>
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
              <label htmlFor="email" className="block text-sm font-medium text-white/80 mb-2">
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Enter your email"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-white/80 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
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
                <span className="px-3 bg-white/10 text-white/80 rounded">New to Kahani?</span>
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