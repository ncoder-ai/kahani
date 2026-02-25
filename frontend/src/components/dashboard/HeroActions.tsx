'use client';

import { useRouter } from 'next/navigation';

interface HeroActionsProps {
  isAdmin: boolean;
}

export default function HeroActions({ isAdmin }: HeroActionsProps) {
  const router = useRouter();

  return (
    <div className="text-center mb-8 sm:mb-12">
      <img src="/kahanilogo.png" alt="Kahani" className="h-20 sm:h-28 w-20 sm:w-28 object-contain mx-auto mb-4" />
      <h2 className="text-2xl sm:text-4xl font-bold text-white mb-2 sm:mb-4">Your Story Universe</h2>
      <p className="text-white/80 text-sm sm:text-lg mb-6 sm:mb-10 px-2">
        Create immersive stories with AI assistance
      </p>

      {/* Tier 1 — Primary Creation Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 max-w-3xl mx-auto mb-6 sm:mb-8">
        {/* Write a Story */}
        <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-4 sm:p-6 text-left">
          <h3 className="text-lg sm:text-xl font-bold text-white mb-1 sm:mb-2">Write a Story</h3>
          <p className="text-white/60 text-xs sm:text-sm mb-4 sm:mb-5">
            Craft an interactive narrative with AI-powered scene generation
          </p>
          <div className="flex flex-col gap-2 sm:gap-3">
            <button
              onClick={() => router.push('/create-story')}
              className="theme-btn-primary px-4 py-3 rounded-xl font-semibold text-sm sm:text-base transition-all duration-200 active:scale-95"
            >
              Start from Scratch
            </button>
            <button
              onClick={() => router.push('/brainstorm')}
              className="bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white px-4 py-3 rounded-xl font-semibold text-sm sm:text-base transition-all duration-200 active:scale-95"
            >
              Brainstorm First
            </button>
          </div>
        </div>

        {/* Start a Roleplay */}
        <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-4 sm:p-6 text-left">
          <h3 className="text-lg sm:text-xl font-bold text-white mb-1 sm:mb-2">Start a Roleplay</h3>
          <p className="text-white/60 text-xs sm:text-sm mb-4 sm:mb-5">
            Characters act on their own, you guide the scene
          </p>
          <button
            onClick={() => router.push('/roleplay/create')}
            className="w-full bg-gradient-to-r from-purple-500 to-pink-600 hover:from-purple-600 hover:to-pink-700 text-white px-4 py-3 rounded-xl font-semibold text-sm sm:text-base transition-all duration-200 active:scale-95"
          >
            Create Roleplay
          </button>
        </div>
      </div>

      {/* Tier 2 — Utility Bar */}
      <div className="flex justify-center gap-2 sm:gap-4 flex-wrap">
        <button
          onClick={() => router.push('/characters')}
          className="theme-btn-secondary px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl font-medium transition-all duration-200 text-xs sm:text-sm"
        >
          Characters
        </button>
        <button
          onClick={() => router.push('/worlds')}
          className="theme-btn-secondary px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl font-medium transition-all duration-200 text-xs sm:text-sm"
        >
          Worlds
        </button>
        {isAdmin && (
          <button
            onClick={() => router.push('/admin')}
            className="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl font-medium transition-all duration-200 text-xs sm:text-sm"
          >
            Admin
          </button>
        )}
      </div>
    </div>
  );
}
