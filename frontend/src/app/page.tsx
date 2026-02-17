'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore, useHasHydrated } from '@/store';
import { applyTheme } from '@/lib/themes';
import apiClient from '@/lib/api';

export default function HomePage() {
  const router = useRouter();
  const { isAuthenticated, login } = useAuthStore();
  const hasHydrated = useHasHydrated();

  // Check for SSO auto-login
  const checkSSOLogin = async () => {
    if (typeof window === 'undefined') return;

    try {
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
        apiClient.setToken(data.access_token);
        login(data.user, data.access_token);

        // Wait for Zustand to persist
        await new Promise(resolve => setTimeout(resolve, 100));

        if (!data.user.is_approved && !data.user.is_admin) {
          window.location.href = '/pending-approval';
          return;
        }

        window.location.href = '/dashboard';
      }
    } catch {
      // SSO check failed silently
    }
  };

  useEffect(() => {
    // Apply default theme for landing page
    applyTheme('pure-dark');

    // Prefetch dashboard when authenticated for faster navigation
    if (hasHydrated && isAuthenticated) {
      router.prefetch('/dashboard');
      router.push('/dashboard');
    } else if (hasHydrated && !isAuthenticated) {
      // Check for SSO auto-login when not authenticated
      checkSSOLogin();
      // Prefetch login/register pages for faster navigation
      router.prefetch('/login');
      router.prefetch('/register');
    }
  }, [router, hasHydrated, isAuthenticated]);

  if (!hasHydrated) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen theme-bg-primary">
      {/* Header */}
      <header className="bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-4">
              <h1 className="text-2xl font-bold text-white">✨ Kahani</h1>
              <span className="text-white/60">•</span>
              <span className="text-white/80">Interactive Storytelling</span>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                href="/login"
                className="text-white/80 hover:text-white transition-colors px-4 py-2 rounded-lg hover:bg-white/10"
              >
                Sign In
              </Link>
              <Link
                href="/register"
                className="theme-btn-primary px-6 py-2 rounded-lg font-semibold transition-all duration-200"
              >
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="max-w-7xl mx-auto px-6 py-24">
        <div className="text-center mb-20">
          <h2 className="text-6xl font-bold text-white mb-6">
            Create Stories That
            <br />
            <span className="theme-accent-primary">
              Come Alive
            </span>
          </h2>
          <p className="text-xl text-white/80 mb-12 max-w-3xl mx-auto">
            Kahani is an interactive storytelling platform that combines your creativity with AI assistance 
            to create immersive, branching narratives that engage and captivate readers.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link
              href="/register"
              className="theme-btn-primary px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
            >
              Start Creating Now
            </Link>
            <Link
              href="/login"
              className="border-2 border-white/30 text-white px-8 py-4 rounded-2xl font-semibold text-lg hover:bg-white/10 transition-all duration-200"
            >
              Sign In
            </Link>
          </div>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-8 mb-20">
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-4">🤖</div>
            <h3 className="text-xl font-bold text-white mb-4">AI-Powered Writing</h3>
            <p className="text-white/70">
              Get intelligent suggestions and continue your story with AI assistance when you need inspiration.
            </p>
          </div>
          
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-4">🌟</div>
            <h3 className="text-xl font-bold text-white mb-4">Interactive Stories</h3>
            <p className="text-white/70">
              Create branching narratives where readers make choices that shape the story's direction.
            </p>
          </div>
          
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-4">👥</div>
            <h3 className="text-xl font-bold text-white mb-4">Collaborative</h3>
            <p className="text-white/70">
              Work together with other writers or let your readers contribute to the story's evolution.
            </p>
          </div>
        </div>

        {/* CTA Section */}
        <div className="theme-bg-secondary border theme-border-accent rounded-3xl p-12 text-center">
          <h3 className="text-3xl font-bold text-white mb-4">Ready to Begin Your Story?</h3>
          <p className="text-white/80 text-lg mb-8">
            Join thousands of creators who are bringing their imagination to life with Kahani
          </p>
          <Link
            href="/register"
            className="theme-btn-primary px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
          >
            Create Your First Story
          </Link>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white/5 backdrop-blur-md border-t border-white/20 mt-20">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="text-center text-white/60">
            <p>&copy; 2025 Kahani. Unleashing creativity through interactive storytelling.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}