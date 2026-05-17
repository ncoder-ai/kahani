'use client';

import { BookOpen, Zap } from 'lucide-react';

interface StoryModeSelectionProps {
  selected: 'dynamic' | 'structured' | '';
  onSelect: (mode: 'dynamic' | 'structured') => void;
}

export default function StoryModeSelection({ selected, onSelect }: StoryModeSelectionProps) {
  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="text-center mb-4 sm:mb-8">
        <h2 className="text-xl sm:text-3xl font-bold mb-2 sm:mb-3 text-white">Choose Your Story Mode</h2>
        <p className="text-white/80 text-sm sm:text-base">
          Select how you want to structure your story
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-3 sm:gap-6 max-w-4xl mx-auto">
        {/* Dynamic Mode Card */}
        <button
          onClick={() => onSelect('dynamic')}
          className={`p-4 sm:p-8 rounded-2xl border-2 transition-all text-left hover:scale-105 relative ${
            selected === 'dynamic'
              ? 'border-2 shadow-lg'
              : 'border-gray-700 theme-bg-secondary hover:border-opacity-50'
          }`}
          style={selected === 'dynamic' ? {
            borderColor: 'var(--color-accentPrimary)',
            boxShadow: '0 10px 15px -3px rgba(var(--color-accentPrimary-rgb), 0.3), 0 4px 6px -2px rgba(var(--color-accentPrimary-rgb), 0.3)'
          } as React.CSSProperties : {}}
        >
          {selected === 'dynamic' && (
            <div className="absolute inset-0 rounded-2xl pointer-events-none" style={{ backgroundColor: 'var(--color-accentPrimary)', opacity: 0.1 }} />
          )}
          <div className="flex items-start gap-3 sm:gap-4 mb-3 sm:mb-4 relative z-10">
            <div className={`p-2 sm:p-3 rounded-xl relative ${
              selected === 'dynamic' ? '' : 'bg-gray-700'
            }`}>
              {selected === 'dynamic' && (
                <div className="absolute inset-0 rounded-xl pointer-events-none" style={{ backgroundColor: 'var(--color-accentPrimary)', opacity: 0.2 }} />
              )}
              <Zap className={`w-6 h-6 sm:w-8 sm:h-8 relative z-10 ${
                selected === 'dynamic' ? '' : 'text-gray-400'
              }`}
              style={selected === 'dynamic' ? {
                color: 'var(--color-accentPrimary)'
              } as React.CSSProperties : {}} />
            </div>
            <div className="flex-1">
              <h3 className="text-lg sm:text-2xl font-bold mb-1 sm:mb-2 text-white">Dynamic Mode</h3>
              <span className="inline-block px-2 py-1 text-xs font-semibold rounded bg-green-500/20 text-green-400 border border-green-500/30">
                RECOMMENDED
              </span>
            </div>
          </div>
          
          <p className="text-white text-sm sm:text-base mb-3 sm:mb-4 relative z-10">
            Perfect for exploration and organic storytelling. Let your story evolve naturally!
          </p>

          <div className="space-y-1.5 sm:space-y-2 text-xs sm:text-sm relative z-10">
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-white/90">Start writing immediately</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-white/90">No pre-planning required</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-white/90">Automatic chapter breaks when needed</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-white/90">Flexible, organic story development</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-white/90">Auto-generated chapter summaries</span>
            </div>
          </div>
        </button>

        {/* Structured Mode Card */}
        <button
          onClick={() => onSelect('structured')}
          className={`p-4 sm:p-8 rounded-2xl border-2 transition-all text-left hover:scale-105 ${
            selected === 'structured'
              ? 'border-blue-500 bg-blue-500/10 shadow-lg shadow-blue-500/20'
              : 'border-gray-700 theme-bg-secondary hover:border-blue-500/50'
          }`}
        >
          <div className="flex items-start gap-3 sm:gap-4 mb-3 sm:mb-4">
            <div className={`p-2 sm:p-3 rounded-xl ${
              selected === 'structured' ? 'bg-blue-500/20' : 'bg-gray-700'
            }`}>
              <BookOpen className={`w-6 h-6 sm:w-8 sm:h-8 ${
                selected === 'structured' ? 'text-blue-400' : 'text-gray-400'
              }`} />
            </div>
            <div className="flex-1">
              <h3 className="text-lg sm:text-2xl font-bold mb-1 sm:mb-2">Structured Mode</h3>
              <span className="inline-block px-2 py-1 text-xs font-semibold rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
                ADVANCED
              </span>
            </div>
          </div>
          
          <p className="text-white text-sm sm:text-base mb-3 sm:mb-4">
            Perfect for planned narratives with clear plot points and chapters.
          </p>

          <div className="space-y-1.5 sm:space-y-2 text-xs sm:text-sm">
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-white/90">Define plot points upfront</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-white/90">Each chapter maps to a plot point</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-white/90">Rewrite entire chapters</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-white/90">Maintain narrative structure</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-white/90">Clear story arc from start</span>
            </div>
          </div>
        </button>
      </div>

      <div className="text-center mt-4 sm:mt-8">
        <p className="text-sm text-gray-500">
          Don't worry - you can always edit your story details and structure later
        </p>
      </div>
    </div>
  );
}
