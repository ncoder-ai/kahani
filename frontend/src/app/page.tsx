'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore, useHasHydrated } from '@/store';
import { applyTheme } from '@/lib/themes';
import apiClient from '@/lib/api';

export default function HomePage() {
  const router = useRouter();
  const { isAuthenticated, login } = useAuthStore();
  const hasHydrated = useHasHydrated();
  const [expandedCard, setExpandedCard] = useState<number | null>(null);

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
    <div className="min-h-screen theme-bg-primary relative">
      {/* Background image — shifted down to clear the fixed banner */}
      <div className="absolute inset-0 bg-contain bg-no-repeat" style={{ backgroundImage: 'url(/kahani-background.png)', backgroundPosition: 'center top', top: '48px' }} />
      {/* Gradient overlay — transparent at top to show image, darker below for text */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/60 to-black/80" />
      {/* Header */}
      <header className="relative z-10 bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-4">
              <h1 className="text-2xl font-bold text-white flex items-center gap-2"><img src="/kahanilogo.png" alt="" className="h-14 w-14 md:h-12 md:w-12 object-contain" /> Kahani</h1>
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
      <main className="relative z-10 max-w-7xl mx-auto px-6 pt-[34vw] sm:pt-[28vw] md:pt-[22vw] pb-24">
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

        {/* Features — ordered by user journey: Imagine → Create → Write → Explore → Expand → Experience */}
        <div className="grid md:grid-cols-2 gap-6 mb-20">
          {[
            {
              title: 'From Idea to Story',
              desc: 'Brainstorm with AI to develop characters, plot, and themes \u2014 then turn the session into a fully structured story.',
              howItWorks: 'Start a brainstorm session and chat freely about your idea. The AI helps you flesh out characters, plot arcs, and world details. When you\u2019re ready, one click converts the entire session into a structured story with chapters, characters, and plot milestones already laid out.',
              color: 'from-cyan-500 to-indigo-600',
              borderHover: 'hover:border-cyan-500/50',
              shadowHover: 'hover:shadow-cyan-500/20',
              iconBg: 'bg-cyan-500/20',
              iconColor: 'text-cyan-400',
              icon: (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                </svg>
              ),
            },
            {
              title: 'Characters That Feel Real',
              desc: 'Each character tracks their own emotions, relationships, and knowledge, and speaks with a distinct voice style you define.',
              howItWorks: 'Define a character with a personality, dialogue style, and backstory. As the story progresses, the system automatically tracks how their emotions shift, how their relationships evolve, and what they know. The AI writes their dialogue in their unique voice \u2014 not generic prose.',
              color: 'from-rose-500 to-pink-600',
              borderHover: 'hover:border-rose-500/50',
              shadowHover: 'hover:shadow-rose-500/20',
              iconBg: 'bg-rose-500/20',
              iconColor: 'text-rose-400',
              icon: (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                </svg>
              ),
            },
            {
              title: 'The AI Remembers Everything',
              desc: "Your AI recalls details from hundreds of scenes ago \u2014 a character\u2019s promise, a forgotten item, a location from chapters past.",
              howItWorks: 'Every scene is embedded into a semantic memory system. When you write \u201cshe\u2019s wearing the red dress from the party\u201d, the AI searches across your entire story history \u2014 decomposing your intent into sub-queries, cross-referencing events, and pulling the exact scenes where that dress appeared. No manual bookmarks needed.',
              color: 'from-violet-500 to-purple-600',
              borderHover: 'hover:border-violet-500/50',
              shadowHover: 'hover:shadow-violet-500/20',
              iconBg: 'bg-violet-500/20',
              iconColor: 'text-violet-400',
              icon: (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
                </svg>
              ),
            },
            {
              title: 'Branch Your Story',
              desc: 'Fork the narrative at any scene and explore \u201cwhat-if\u201d paths. Every branch maintains its own characters, plot, and world state.',
              howItWorks: 'At any scene, create a branch to explore an alternate path. Each branch gets its own independent copy of character states, relationships, plot progress, and world state. Switch between branches freely \u2014 they never bleed into each other.',
              color: 'from-sky-500 to-blue-600',
              borderHover: 'hover:border-sky-500/50',
              shadowHover: 'hover:shadow-sky-500/20',
              iconBg: 'bg-sky-500/20',
              iconColor: 'text-sky-400',
              icon: (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
                </svg>
              ),
            },
            {
              title: 'Build Shared Universes',
              desc: 'Create worlds where sequel stories automatically inherit lore, characters, and locations from previous tales.',
              howItWorks: 'Group stories into a shared world. When you start a sequel, the AI can recall scenes and lore from any previous story in that world \u2014 character histories, established locations, past events. A living lorebook is built automatically from your writing and stays consistent across stories.',
              color: 'from-emerald-500 to-teal-600',
              borderHover: 'hover:border-emerald-500/50',
              shadowHover: 'hover:shadow-emerald-500/20',
              iconBg: 'bg-emerald-500/20',
              iconColor: 'text-emerald-400',
              icon: (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5a17.92 17.92 0 0 1-8.716-2.247m0 0A8.966 8.966 0 0 1 3 12c0-1.264.26-2.466.732-3.558" />
                </svg>
              ),
            },
            {
              title: 'Roleplay With Your Characters',
              desc: 'Step into a scene and talk directly to any character. They respond in-character, drawing on everything that\u2019s happened in the story.',
              howItWorks: 'Pick a character and start a conversation. The AI embodies them with their personality, dialogue style, current emotional state, and full knowledge of the story so far \u2014 what they\u2019ve witnessed, who they trust, what they\u2019re hiding. Their responses stay consistent with the narrative, not generic chatbot filler.',
              color: 'from-amber-500 to-orange-600',
              borderHover: 'hover:border-amber-500/50',
              shadowHover: 'hover:shadow-amber-500/20',
              iconBg: 'bg-amber-500/20',
              iconColor: 'text-amber-400',
              icon: (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
                </svg>
              ),
            },
          ].map((feature, i) => (
            <div
              key={feature.title}
              className={`group relative bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-8 transition-all duration-300 cursor-pointer ${expandedCard === i ? `${feature.borderHover.replace('hover:', '')} ${feature.shadowHover.replace('hover:', '')} shadow-xl -translate-y-1` : `hover:-translate-y-1 hover:shadow-xl ${feature.borderHover} ${feature.shadowHover}`}`}
              onClick={() => setExpandedCard(expandedCard === i ? null : i)}
            >
              {/* Gradient accent line at top */}
              <div className={`absolute top-0 left-8 right-8 h-[2px] bg-gradient-to-r ${feature.color} rounded-full transition-all duration-300 ${expandedCard === i ? 'opacity-100 left-6 right-6' : 'opacity-60 group-hover:opacity-100 group-hover:left-6 group-hover:right-6'}`} />

              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className={`w-12 h-12 rounded-xl ${feature.iconBg} flex items-center justify-center mb-5 transition-transform duration-300 ${expandedCard === i ? 'scale-110' : 'group-hover:scale-110'}`}>
                    <div className={feature.iconColor}>{feature.icon}</div>
                  </div>
                  <h3 className="text-xl font-bold text-white mb-3">{feature.title}</h3>
                  <p className="text-white/60 leading-relaxed">{feature.desc}</p>
                </div>
                <div className={`mt-1 flex-shrink-0 transition-transform duration-300 ${expandedCard === i ? 'rotate-180' : ''}`}>
                  <svg className="w-5 h-5 text-white/30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                  </svg>
                </div>
              </div>

              {/* Expandable "How it works" section */}
              <div className={`grid transition-all duration-300 ease-in-out ${expandedCard === i ? 'grid-rows-[1fr] opacity-100 mt-5' : 'grid-rows-[0fr] opacity-0 mt-0'}`}>
                <div className="overflow-hidden">
                  <div className={`border-t border-white/10 pt-4`}>
                    <p className={`text-sm font-semibold uppercase tracking-wider mb-2 ${feature.iconColor}`}>How it works</p>
                    <p className="text-white/50 text-sm leading-relaxed">{feature.howItWorks}</p>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* CTA Section */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-3xl p-12 text-center">
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
      <footer className="relative z-10 bg-white/5 backdrop-blur-md border-t border-white/20 mt-20">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="text-center text-white/60">
            <p>&copy; 2025 Kahani. Unleashing creativity through interactive storytelling.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}