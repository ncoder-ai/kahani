'use client';

import { BookOpen, Zap } from 'lucide-react';

interface StoryModeSelectionProps {
  selected: 'dynamic' | 'structured' | '';
  onSelect: (mode: 'dynamic' | 'structured') => void;
}

export default function StoryModeSelection({ selected, onSelect }: StoryModeSelectionProps) {
  return (
    <div className="space-y-6">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold mb-3">Choose Your Story Mode</h2>
        <p className="text-gray-400">
          Select how you want to structure your story
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
        {/* Dynamic Mode Card */}
        <button
          onClick={() => onSelect('dynamic')}
          className={`p-8 rounded-2xl border-2 transition-all text-left hover:scale-105 ${
            selected === 'dynamic'
              ? 'border-purple-500 bg-purple-500/10 shadow-lg shadow-purple-500/20'
              : 'border-gray-700 bg-gray-800/50 hover:border-purple-500/50'
          }`}
        >
          <div className="flex items-start gap-4 mb-4">
            <div className={`p-3 rounded-xl ${
              selected === 'dynamic' ? 'bg-purple-500/20' : 'bg-gray-700'
            }`}>
              <Zap className={`w-8 h-8 ${
                selected === 'dynamic' ? 'text-purple-400' : 'text-gray-400'
              }`} />
            </div>
            <div className="flex-1">
              <h3 className="text-2xl font-bold mb-2">Dynamic Mode</h3>
              <span className="inline-block px-2 py-1 text-xs font-semibold rounded bg-green-500/20 text-green-400 border border-green-500/30">
                RECOMMENDED
              </span>
            </div>
          </div>
          
          <p className="text-gray-300 mb-4">
            Perfect for exploration and organic storytelling. Let your story evolve naturally!
          </p>
          
          <div className="space-y-2 text-sm">
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-gray-400">Start writing immediately</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-gray-400">No pre-planning required</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-gray-400">Automatic chapter breaks when needed</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-gray-400">Flexible, organic story development</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              <span className="text-gray-400">Auto-generated chapter summaries</span>
            </div>
          </div>
        </button>

        {/* Structured Mode Card */}
        <button
          onClick={() => onSelect('structured')}
          className={`p-8 rounded-2xl border-2 transition-all text-left hover:scale-105 ${
            selected === 'structured'
              ? 'border-blue-500 bg-blue-500/10 shadow-lg shadow-blue-500/20'
              : 'border-gray-700 bg-gray-800/50 hover:border-blue-500/50'
          }`}
        >
          <div className="flex items-start gap-4 mb-4">
            <div className={`p-3 rounded-xl ${
              selected === 'structured' ? 'bg-blue-500/20' : 'bg-gray-700'
            }`}>
              <BookOpen className={`w-8 h-8 ${
                selected === 'structured' ? 'text-blue-400' : 'text-gray-400'
              }`} />
            </div>
            <div className="flex-1">
              <h3 className="text-2xl font-bold mb-2">Structured Mode</h3>
              <span className="inline-block px-2 py-1 text-xs font-semibold rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
                ADVANCED
              </span>
            </div>
          </div>
          
          <p className="text-gray-300 mb-4">
            Perfect for planned narratives with clear plot points and chapters.
          </p>
          
          <div className="space-y-2 text-sm">
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-gray-400">Define plot points upfront</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-gray-400">Each chapter maps to a plot point</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-gray-400">Rewrite entire chapters</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-gray-400">Maintain narrative structure</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-blue-400">✓</span>
              <span className="text-gray-400">Clear story arc from start</span>
            </div>
          </div>
        </button>
      </div>

      <div className="text-center mt-8">
        <p className="text-sm text-gray-500">
          Don't worry - you can always edit your story details and structure later
        </p>
      </div>
    </div>
  );
}
