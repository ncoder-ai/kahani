import React, { useState, useEffect } from 'react';
import { X, Sparkles, Users } from 'lucide-react';

interface CharacterSuggestionBannerProps {
  storyId: number;
  chapterId?: number;
  onDiscoverCharacters: () => void;
  onDismiss: () => void;
  isVisible: boolean;
}

export default function CharacterSuggestionBanner({
  storyId,
  chapterId,
  onDiscoverCharacters,
  onDismiss,
  isVisible
}: CharacterSuggestionBannerProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  // Check if banner was dismissed for this story
  useEffect(() => {
    const dismissedKey = `character_suggestion_dismissed_${storyId}`;
    const dismissed = localStorage.getItem(dismissedKey);
    if (dismissed === 'true') {
      setIsDismissed(true);
    }
  }, [storyId]);

  const handleDismiss = () => {
    const dismissedKey = `character_suggestion_dismissed_${storyId}`;
    localStorage.setItem(dismissedKey, 'true');
    setIsDismissed(true);
    onDismiss();
  };

  if (!isVisible || isDismissed) {
    return null;
  }

  return (
    <div className="rounded-lg p-4 mb-6 border opacity-20"
         style={{
           background: `linear-gradient(to right, var(--color-accentPrimary), var(--color-accentSecondary))`,
           borderColor: 'var(--color-accentPrimary)',
           borderOpacity: 0.3
         } as React.CSSProperties & { borderOpacity?: number }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-full flex items-center justify-center"
                 style={{ background: 'linear-gradient(to right, var(--color-accentPrimary), var(--color-accentSecondary))' } as React.CSSProperties}>
              <Sparkles className="h-5 w-5 text-white" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-white mb-1">
              New Important Characters Detected!
            </h3>
            <p className="text-white/80 text-sm">
              Your story contains characters that might be worth adding to your character library.
            </p>
          </div>
        </div>
        
        <div className="flex items-center space-x-3">
          <button
            onClick={onDiscoverCharacters}
            className="flex items-center space-x-2 px-4 py-2 theme-btn-primary rounded-lg transition-colors"
          >
            <Users className="h-4 w-4" />
            <span>Discover Characters</span>
          </button>
          
          <button
            onClick={handleDismiss}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
            title="Dismiss"
          >
            <X className="h-4 w-4 text-white/70" />
          </button>
        </div>
      </div>
    </div>
  );
}
