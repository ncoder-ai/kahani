'use client';

import { useState } from 'react';
import { StoryData } from '@/app/create-story/page';
import { useAuthStore } from '@/store';

interface GenreSelectionProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  isFirstStep: boolean;
}

const GENRES = [
  {
    id: 'fantasy',
    name: 'Fantasy',
    description: 'Magic, mythical creatures, and epic adventures',
    icon: '🏰',
    gradient: 'from-purple-500 to-pink-500'
  },
  {
    id: 'sci-fi',
    name: 'Science Fiction',
    description: 'Future technology, space exploration, and innovation',
    icon: '🚀',
    gradient: 'from-blue-500 to-cyan-500'
  },
  {
    id: 'mystery',
    name: 'Mystery',
    description: 'Puzzles, investigations, and hidden secrets',
    icon: '🔍',
    gradient: 'from-gray-600 to-gray-800'
  },
  {
    id: 'romance',
    name: 'Romance',
    description: 'Love stories, relationships, and emotional journeys',
    icon: '💝',
    gradient: 'from-rose-400 to-pink-600'
  },
  {
    id: 'thriller',
    name: 'Thriller',
    description: 'Suspense, danger, and edge-of-your-seat excitement',
    icon: '⚡',
    gradient: 'from-red-500 to-orange-600'
  },
  {
    id: 'adventure',
    name: 'Adventure',
    description: 'Exploration, quests, and exciting journeys',
    icon: '🗺️',
    gradient: 'from-green-500 to-emerald-600'
  },
  {
    id: 'horror',
    name: 'Horror',
    description: 'Fear, supernatural elements, and dark themes',
    icon: '👻',
    gradient: 'from-gray-800 to-black'
  },
  {
    id: 'drama',
    name: 'Drama',
    description: 'Emotional stories, character development, and real-life situations',
    icon: '🎭',
    gradient: 'from-amber-500 to-orange-500'
  }
];

const NSFW_GENRES = [
  {
    id: 'erotica',
    name: 'Erotica',
    description: 'Adult romantic and sensual stories with mature themes',
    icon: '🔥',
    gradient: 'from-red-600 to-rose-700'
  },
  {
    id: 'violence',
    name: 'Violence/Action',
    description: 'Intense action, combat, and violent confrontations',
    icon: '⚔️',
    gradient: 'from-red-700 to-black'
  },
  {
    id: 'dark-fantasy',
    name: 'Dark Fantasy',
    description: 'Gothic, disturbing, and morally complex fantasy elements',
    icon: '🩸',
    gradient: 'from-purple-900 to-black'
  },
  {
    id: 'psychological',
    name: 'Psychological',
    description: 'Mind-bending, disturbing psychological themes',
    icon: '🧠',
    gradient: 'from-gray-800 to-red-900'
  }
];

const TONES = [
  { id: 'lighthearted', name: 'Lighthearted', icon: '😊' },
  { id: 'serious', name: 'Serious', icon: '🎯' },
  { id: 'dark', name: 'Dark', icon: '🌙' },
  { id: 'humorous', name: 'Humorous', icon: '😄' },
  { id: 'mysterious', name: 'Mysterious', icon: '🔮' },
  { id: 'epic', name: 'Epic', icon: '⚔️' },
  { id: 'melancholic', name: 'Melancholic', icon: '🌧️' },
  { id: 'romantic', name: 'Romantic', icon: '💕' },
  { id: 'suspenseful', name: 'Suspenseful', icon: '⏰' },
  { id: 'philosophical', name: 'Philosophical', icon: '🤔' },
  { id: 'nostalgic', name: 'Nostalgic', icon: '📸' },
  { id: 'satirical', name: 'Satirical', icon: '🎭' }
];

export default function GenreSelection({ storyData, onUpdate, onNext, isFirstStep }: GenreSelectionProps) {
  const { user } = useAuthStore();
  
  // Check if user has NSFW permission
  const canAccessNSFW = user?.allow_nsfw ?? false;
  
  const handleGenreSelect = (genreId: string) => {
    onUpdate({ genre: genreId });
  };

  const handleToneSelect = (toneId: string) => {
    onUpdate({ tone: toneId });
  };

  const canProceed = storyData.genre && storyData.tone;

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Choose Your Story's Genre</h2>
        <p className="text-white/80 text-lg">
          Select the genre that best fits your vision
        </p>
      </div>

      {/* Genre Selection */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {GENRES.map((genre) => (
          <button
            key={genre.id}
            onClick={() => handleGenreSelect(genre.id)}
            className={`p-6 rounded-2xl border transition-all duration-200 text-left group hover:scale-105 ${
              storyData.genre === genre.id
                ? 'border-white bg-white/20 scale-105'
                : 'border-white/30 bg-white/10 hover:bg-white/15'
            }`}
          >
            <div className={`text-3xl mb-3 bg-gradient-to-r ${genre.gradient} bg-clip-text text-transparent`}>
              {genre.icon}
            </div>
            <h3 className="text-white font-semibold mb-2">{genre.name}</h3>
            <p className="text-white/70 text-sm">{genre.description}</p>
          </button>
        ))}
      </div>

      {/* NSFW Genres - Show directly if user has permission */}
      {canAccessNSFW && (
        <div className="space-y-4">
          <div className="text-center">
            <h3 className="text-2xl font-bold text-white mb-2">Mature Content</h3>
            <p className="text-white/70 text-sm">
              Genres with mature themes and adult content
            </p>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {NSFW_GENRES.map((genre) => (
              <button
                key={genre.id}
                onClick={() => handleGenreSelect(genre.id)}
                className={`p-6 rounded-2xl border transition-all duration-200 text-left group hover:scale-105 ${
                  storyData.genre === genre.id
                    ? 'border-white bg-white/20 scale-105'
                    : 'border-white/30 bg-white/10 hover:bg-white/15'
                }`}
              >
                <div className={`text-3xl mb-3 bg-gradient-to-r ${genre.gradient} bg-clip-text text-transparent`}>
                  {genre.icon}
                </div>
                <h3 className="text-white font-semibold mb-2">{genre.name}</h3>
                <p className="text-white/70 text-sm">{genre.description}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tone Selection */}
      {storyData.genre && (
        <div className="space-y-4">
          <h3 className="text-2xl font-bold text-white text-center">Select the Tone</h3>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {TONES.map((tone) => (
              <button
                key={tone.id}
                onClick={() => handleToneSelect(tone.id)}
                className={`p-4 rounded-xl border transition-all duration-200 text-center ${
                  storyData.tone === tone.id
                    ? 'border-white bg-white/20'
                    : 'border-white/30 bg-white/10 hover:bg-white/15'
                }`}
              >
                <div className="text-2xl mb-2">{tone.icon}</div>
                <span className="text-white text-sm font-medium">{tone.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-end pt-6">
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={`px-8 py-3 rounded-xl font-semibold transition-all duration-200 ${
            canProceed
              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600'
              : 'bg-white/20 text-white/50 cursor-not-allowed'
          }`}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}