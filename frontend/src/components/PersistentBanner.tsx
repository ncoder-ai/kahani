'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { HomeIcon, ArrowLeftIcon, Menu as MenuIcon, Users, Sparkles } from 'lucide-react';
import { useEffect, useState, useCallback } from 'react';
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
  const { storyActions } = useStoryActions();
  const pathname = usePathname();
  const [canGoBack, setCanGoBack] = useState(false);
  const [showUnifiedMenu, setShowUnifiedMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showTTSSettings, setShowTTSSettings] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isClient, setIsClient] = useState(false);
  const [audioUnlocked, setAudioUnlocked] = useState(false);
  
  // Mark as client-side only after hydration
  useEffect(() => {
    setIsClient(true);
    
    // Check if mobile device (client-side only)
    if (typeof window !== 'undefined') {
      setIsMobile(/iPhone|iPad|iPod|Android/i.test(navigator.userAgent));
    }
  }, []);
  
  // Check AudioContext state periodically
  useEffect(() => {
    const checkAudioState = () => {
      const isUnlocked = audioContextManager.isAudioUnlocked();
      setAudioUnlocked(isUnlocked);
    };
    
    // Check immediately
    checkAudioState();
    
    // Check periodically (AudioContext can be suspended by iOS at any time)
    const interval = setInterval(checkAudioState, 1000);
    
    return () => clearInterval(interval);
  }, []);
  
  // Audio needs permission if AudioContext is not in 'running' state
  const needsPermission = !audioUnlocked;
  
  const handleEnableTTS = useCallback(async () => {
    console.log('[TTS Permission] Attempting to unlock AudioContext...');
    const success = await audioContextManager.unlock();
    setAudioUnlocked(success);
    
    if (success) {
      console.log('[TTS Permission] ✓ AudioContext unlocked successfully');
    } else {
      console.warn('[TTS Permission] ✗ Failed to unlock AudioContext');
    }
  }, []);

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

              {/* TTS Audio Unlock Button - Mobile Only */}
              {isMobile && (
                <button
                  onClick={handleEnableTTS}
                  className={`flex items-center justify-center p-1.5 rounded-lg transition-all duration-200 leading-none ${
                    needsPermission
                      ? 'text-orange-400 hover:bg-orange-600/30 animate-pulse'
                      : 'text-green-400 hover:bg-green-600/30'
                  }`}
                  title={needsPermission ? 'Tap to enable audio' : 'Audio enabled'}
                >
                  {/* Speaker icon */}
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    {needsPermission ? (
                      // Speaker with X (muted)
                      <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM12.293 7.293a1 1 0 011.414 0L15 8.586l1.293-1.293a1 1 0 111.414 1.414L16.414 10l1.293 1.293a1 1 0 01-1.414 1.414L15 11.414l-1.293 1.293a1 1 0 01-1.414-1.414L13.586 10l-1.293-1.293a1 1 0 010-1.414z" clipRule="evenodd" />
                    ) : (
                      // Speaker with waves (unmuted)
                      <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clipRule="evenodd" />
                    )}
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