'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/store';
import apiClient from '@/lib/api';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  
  const router = useRouter();
  const { login } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      console.log('=== LOGIN PROCESS STARTING ===');
      console.log('API Base URL:', process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');
      console.log('Attempting login with email:', email);
      
      const response = await apiClient.login(email, password);
      console.log('✅ Login API call successful');
      console.log('Response keys:', Object.keys(response));
      console.log('Token received:', response.access_token ? 'Yes' : 'No');
      console.log('User data:', response.user ? 'Yes' : 'No');
      
      // Set token in API client immediately
      apiClient.setToken(response.access_token);
      console.log('✅ Token set in API client');
      
      // Update auth store
      login(response.user, response.access_token);
      console.log('✅ Auth store updated');
      
      // Check if user wants to auto-open last story
      try {
        console.log('Checking for auto-redirect settings...');
        const lastStoryResponse = await apiClient.getLastAccessedStory();
        console.log('Last story settings:', lastStoryResponse);
        
        if (lastStoryResponse.auto_open_last_story && lastStoryResponse.last_accessed_story_id) {
          console.log('Auto-redirecting to last story:', lastStoryResponse.last_accessed_story_id);
          router.push(`/story/${lastStoryResponse.last_accessed_story_id}`);
        } else {
          console.log('Redirecting to dashboard');
          router.push('/dashboard');
        }
      } catch (settingsError) {
        console.error('❌ Failed to check auto-redirect settings:', settingsError);
        console.log('Falling back to dashboard redirect');
        router.push('/dashboard');
      }
    } catch (err) {
      console.error('=== LOGIN FAILED ===');
      console.error('Error type:', err instanceof Error ? 'Error' : typeof err);
      console.error('Error message:', err instanceof Error ? err.message : String(err));
      console.error('Full error:', err);
      
      let errorMessage = 'Login failed';
      if (err instanceof Error) {
        errorMessage = err.message;
      } else if (typeof err === 'string') {
        errorMessage = err;
      }
      
      console.error('Setting error message:', errorMessage);
      setError(errorMessage);
    } finally {
      console.log('Login process complete, loading:', false);
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
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
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
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
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="Enter your password"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className={`w-full py-3 px-4 rounded-lg font-semibold transition-all duration-200 ${
                isLoading
                  ? 'bg-white/20 text-white/50 cursor-not-allowed'
                  : 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600 transform hover:scale-105'
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