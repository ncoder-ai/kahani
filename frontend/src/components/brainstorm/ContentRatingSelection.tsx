'use client';

import { useState, useEffect } from 'react';
import apiClient from '@/lib/api';

interface ContentRatingSelectionProps {
  onContinue: (contentRating: 'sfw' | 'nsfw') => void;
}

export default function ContentRatingSelection({ onContinue }: ContentRatingSelectionProps) {
  const [selectedRating, setSelectedRating] = useState<'sfw' | 'nsfw'>('sfw');
  const [userAllowsNsfw, setUserAllowsNsfw] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkNsfwPermission = async () => {
      try {
        const user = await apiClient.getCurrentUser();
        const allowsNsfw = user.permissions?.allow_nsfw || false;
        setUserAllowsNsfw(allowsNsfw);
        // Default to NSFW if user has permission, otherwise SFW
        setSelectedRating(allowsNsfw ? 'nsfw' : 'sfw');
      } catch (error) {
        console.error('Failed to check NSFW permission:', error);
        setUserAllowsNsfw(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkNsfwPermission();
  }, []);

  const handleContinue = () => {
    onContinue(selectedRating);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-white/70">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      {/* Header */}
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-3">
          What type of story are you creating?
        </h2>
        <p className="text-white/70">
          This helps the AI understand how to handle mature themes like violence, romance, or dark topics appropriately.
        </p>
      </div>

      {/* Rating Options */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* SFW Option */}
        <button
          onClick={() => setSelectedRating('sfw')}
          className={`p-6 rounded-xl border-2 text-left transition-all ${
            selectedRating === 'sfw'
              ? 'border-green-500 bg-green-500/10'
              : 'border-white/20 bg-white/5 hover:border-white/40'
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl">📚</span>
            <div>
              <h3 className="text-xl font-bold text-white">Family Friendly</h3>
              <span className="text-xs text-green-400 font-medium">SFW</span>
            </div>
          </div>
          <p className="text-white/70 text-sm mb-3">
            Suitable for all ages. Think young adult fiction, adventure stories, or light fantasy.
          </p>
          <ul className="text-white/60 text-xs space-y-1">
            <li>• Fantasy violence handled tastefully (like Harry Potter)</li>
            <li>• Romance limited to hand-holding and light flirting</li>
            <li>• Dark themes presented with hope and resolution</li>
            <li>• No explicit content, gore, or strong language</li>
          </ul>
        </button>

        {/* NSFW Option */}
        <button
          onClick={() => userAllowsNsfw && setSelectedRating('nsfw')}
          disabled={!userAllowsNsfw}
          className={`p-6 rounded-xl border-2 text-left transition-all ${
            selectedRating === 'nsfw'
              ? 'border-red-500 bg-red-500/10'
              : userAllowsNsfw
                ? 'border-white/20 bg-white/5 hover:border-white/40'
                : 'border-white/10 bg-white/5 opacity-50 cursor-not-allowed'
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl">🔞</span>
            <div>
              <h3 className="text-xl font-bold text-white">Mature Content</h3>
              <span className="text-xs text-red-400 font-medium">NSFW</span>
            </div>
          </div>
          <p className="text-white/70 text-sm mb-3">
            Adult themes and content. Think Game of Thrones, horror, or romance novels.
          </p>
          <ul className="text-white/60 text-xs space-y-1">
            <li>• Graphic violence and intense action</li>
            <li>• Explicit romantic and sexual content</li>
            <li>• Dark themes without content restrictions</li>
            <li>• Strong language and mature situations</li>
          </ul>
          {!userAllowsNsfw && (
            <p className="text-yellow-500 text-xs mt-3">
              ⚠️ NSFW content requires permission. Contact an admin to enable.
            </p>
          )}
        </button>
      </div>

      {/* Info Box */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-4">
        <p className="text-white/60 text-sm">
          <span className="text-white font-medium">💡 Tip:</span> You can change this setting later in Story Settings. 
          The AI will adjust its approach based on this choice - for example, a "dark fantasy" story in SFW mode 
          will have thrilling battles without graphic gore, while in NSFW mode it can be more visceral.
        </p>
      </div>

      {/* Continue Button */}
      <div className="flex justify-center pt-4">
        <button
          onClick={handleContinue}
          className="px-8 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-bold rounded-xl transition-all shadow-lg hover:shadow-purple-500/25"
        >
          Continue →
        </button>
      </div>
    </div>
  );
}

