'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { HomeIcon, ArrowLeftIcon, Menu as MenuIcon, Users, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { useStoryActions } from '@/contexts/StoryContext';
import { audioContextManager } from '@/utils/audioContextManager';

// Lazy load heavy modals - only load when opened
const UnifiedMenu = dynamic(() => import('./UnifiedMenu'), {
  loading: () => null, // No loading spinner - menu opens instantly
  ssr: false
});

const SettingsModal = dynamic(() => import('./SettingsModal'), {
  loading: () => null,
  ssr: false
});

const TTSSettingsModal = dynamic(() => import('./TTSSettingsModal'), {
  loading: () => null,
  ssr: false
});

export default function PersistentBanner() {
  const router = useRouter();
  const { user } = useAuthStore();
  const { audioPermissionBlocked } = useGlobalTTS();
  const { storyActions } = useStoryActions();
  const pathname = usePathname();
  const [canGoBack, setCanGoBack] = useState(false);
  const [showUnifiedMenu, setShowUnifiedMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showTTSSettings, setShowTTSSettings] = useState(false);
  const [ttsPermissionEnabled, setTtsPermissionEnabled] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isClient, setIsClient] = useState(false);
  
  // Mark as client-side only after hydration
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Sync with AudioContext state
  useEffect(() => {
    // Only run on client side to prevent hydration mismatch
    if (typeof window === 'undefined') return;
    
    const checkAudioState = () => {
      const isUnlocked = audioContextManager.isAudioUnlocked();
      setTtsPermissionEnabled(isUnlocked);
    };
    
    // Check if mobile device (client-side only)
    setIsMobile(/iPhone|iPad|iPod|Android/i.test(navigator.userAgent));
    
    // Check immediately
    checkAudioState();
    
    // Check periodically to sync with manual unlocks
    const interval = setInterval(checkAudioState, 1000);
    
    return () => clearInterval(interval);
  }, []);
  
  // Compute actual permission state
  const needsPermission = audioPermissionBlocked || !ttsPermissionEnabled;
  
  const handleEnableTTS = async () => {
    const success = await audioContextManager.unlock();
    
    if (success) {
      setTtsPermissionEnabled(true);
      // NO ALERT - just visual feedback
    } else {
      console.error('[TTS Permission] ❌ Failed to unlock AudioContext');
    }
  };

  useEffect(() => {
    // Check if we can go back in history (client-side only)
    if (typeof window !== 'undefined') {
      setCanGoBack(window.history.length > 1);
    }
  }, []);

  const handleHome = () => {
    router.push('/dashboard');
  };

  const handleBack = () => {
    router.back();
  };

  if (!user) {
    return null;
  }

  return (
    <>
      {/* Top Banner */}
      <div className="fixed top-0 left-0 right-0 z-50 theme-banner backdrop-blur-md border-b border-white/20 shadow-sm" suppressHydrationWarning>
        <div className="max-w-7xl mx-auto px-4 py-0.5 md:py-1">
          <div className="flex justify-between items-center">
            {/* Left side - App name, story title, and user info */}
            <div className="flex items-center space-x-2 md:space-x-4 min-w-0 flex-1" suppressHydrationWarning>
              {isClient && canGoBack && (
                <button
                  onClick={handleBack}
                  className="flex items-center text-white/80 hover:text-white hover:bg-white/10 px-1.5 py-0.5 rounded-lg transition-all duration-200 flex-shrink-0"
                  title="Go back"
                >
                  <ArrowLeftIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
                </button>
              )}
              <button
                onClick={handleHome}
                className="flex items-center space-x-2 text-white hover:text-purple-200 transition-colors flex-shrink-0 leading-none"
              >
                <span className="text-sm md:text-base font-bold leading-none">✨ Kahani</span>
              </button>
              {isClient && pathname?.startsWith('/story/') && storyActions?.storyTitle ? (
                <>
                  <span className="text-white/60 hidden sm:inline flex-shrink-0 leading-none">•</span>
                  <span className="text-white/90 text-sm md:text-base font-medium truncate min-w-0 leading-none" title={storyActions.storyTitle}>
                    {storyActions.storyTitle}
                  </span>
                </>
              ) : isClient && !pathname?.startsWith('/story/') ? (
                <>
                  <span className="text-white/60 hidden sm:inline flex-shrink-0 leading-none">•</span>
                  <span className="text-white/80 text-sm hidden sm:inline leading-none">
                    Welcome, <span className="text-white font-medium">{user.display_name}</span>
                  </span>
                </>
              ) : null}
            </div>

            {/* Right side - Action buttons */}
            <div className="flex items-center space-x-2">
              {/* Character Suggestion Button */}
              {storyActions?.showCharacterBanner && storyActions?.onDiscoverCharacters && (
                <button
                  onClick={storyActions.onDiscoverCharacters}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg transition-all hover:bg-white/10 theme-btn-primary hover:opacity-90 relative"
                  title="New characters found - click to discover"
                >
                  <Sparkles className="w-4 h-4" />
                  <span className="hidden sm:inline text-sm">New Characters</span>
                  <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                </button>
              )}

              {/* Generation/Extraction Status - Compact */}
              {(storyActions?.lastGenerationTime !== null || storyActions?.generationStartTime !== null || storyActions?.extractionStatus) && (
                <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] text-white/80">
                  <svg className="w-3.5 h-3.5 text-white/60 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {storyActions?.extractionStatus ? (
                    <span className={`max-w-[120px] truncate ${storyActions.extractionStatus.status === 'extracting' ? 'animate-pulse' : ''}`}>
                      {storyActions.extractionStatus.message}
                    </span>
                  ) : storyActions?.generationStartTime ? (
                    <span className="animate-pulse">Generating...</span>
                  ) : (
                    <span>
                      <span className="text-white/60">Generated in </span>
                      <span className="font-semibold text-white">{storyActions?.lastGenerationTime?.toFixed(1)}s</span>
                    </span>
                  )}
                </div>
              )}

              {/* Menu Button */}
              <button
                onClick={() => setShowUnifiedMenu(true)}
                className="flex items-center justify-center w-7 h-7 md:w-8 md:h-8 rounded-lg transition-all hover:bg-white/10 text-white/80 hover:text-white leading-none"
                aria-label="Open menu"
              >
                <MenuIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
              </button>

              {/* TTS Permission Button - Mobile Only */}
              {isMobile && (
                <button
                  onClick={handleEnableTTS}
                  className={`flex items-center justify-center p-0.5 rounded-lg transition-all duration-200 leading-none ${
                    needsPermission
                      ? 'text-orange-400 hover:bg-orange-600/30 animate-pulse'
                      : 'text-green-400 hover:bg-green-600/30'
                  }`}
                  title={needsPermission ? 'Click to enable TTS' : 'TTS Ready'}
                >
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                    <path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Unified Menu */}
      <UnifiedMenu 
        isOpen={showUnifiedMenu} 
        onClose={() => setShowUnifiedMenu(false)}
        onOpenSettings={() => {
          setShowUnifiedMenu(false);
          setShowSettings(true);
        }}
        isStoryPage={isClient && pathname?.startsWith('/story/') || false}
        storyActions={storyActions}
      />

      {/* Settings Modal */}
      <SettingsModal 
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
      />

      {/* TTS Settings Modal (Temporary - for Phase 2 migration) */}
      <TTSSettingsModal 
        isOpen={showTTSSettings}
        onClose={() => setShowTTSSettings(false)}
        onSaved={() => {
          setShowTTSSettings(false);
        }}
      />
    </>
  );
}