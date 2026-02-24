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

  // Helper to get status dot color
  const getStatusColor = () => {
    if (storyActions?.extractionStatus?.status === 'extracting') return 'bg-blue-400';
    if (storyActions?.generationStartTime) return 'bg-amber-400';
    if (storyActions?.lastGenerationTime !== null) return 'bg-green-400';
    return null;
  };

  if (!user) {
    return null;
  }

  return (
    <>
      {/* Top Banner */}
      <div className="fixed top-0 left-0 right-0 z-50 theme-banner backdrop-blur-md border-b border-white/20 shadow-sm" suppressHydrationWarning>
        <div className="max-w-7xl mx-auto px-2 md:px-4 py-0.5 md:py-1">
          <div className="flex justify-between items-center">
            {/* Left side - Back, App icon, story title */}
            <div className="flex items-center space-x-1 md:space-x-3 min-w-0 flex-1" suppressHydrationWarning>
              {/* Back button - compact */}
              {isClient && canGoBack && (
                <button
                  onClick={handleBack}
                  className="flex items-center text-white/80 hover:text-white hover:bg-white/10 p-1 rounded-md transition-all duration-200 flex-shrink-0"
                  title="Go back"
                >
                  <ArrowLeftIcon className="w-3 h-3 md:w-4 md:h-4" />
                </button>
              )}
              
              {/* App name - emoji only on mobile */}
              <button
                onClick={handleHome}
                className="flex items-center text-white hover:text-purple-200 transition-colors flex-shrink-0 leading-none"
              >
                <img src="/kahanilogo.png" alt="Make My Story" className="h-10 w-10 md:h-8 md:w-8 object-contain" />
                <span className="hidden md:inline text-sm font-bold leading-none ml-1">Make My Story</span>
              </button>
              
              {/* Story title - smaller on mobile */}
              {isClient && pathname?.startsWith('/story/') && storyActions?.storyTitle ? (
                <>
                  <span className="text-white/40 flex-shrink-0 leading-none">•</span>
                  <span 
                    className="text-white/90 text-[11px] md:text-sm font-medium truncate min-w-0 leading-none max-w-[100px] sm:max-w-[180px] md:max-w-none" 
                    title={storyActions.storyTitle}
                  >
                    {storyActions.storyTitle}
                  </span>
                </>
              ) : isClient && !pathname?.startsWith('/story/') ? (
                <span className="text-white/80 text-sm hidden md:inline leading-none">
                  <span className="text-white/40 mr-2">•</span>Welcome, <span className="text-white font-medium">{user.display_name}</span>
                </span>
              ) : null}
            </div>

            {/* Right side - Status dot, actions */}
            <div className="flex items-center space-x-1 md:space-x-2">
              {/* Status indicator - dot only on mobile, full on desktop */}
              {getStatusColor() && (
                <div 
                  className="flex items-center"
                  title={
                    storyActions?.extractionStatus?.message || 
                    (storyActions?.generationStartTime ? 'Generating...' : 
                     `Generated in ${storyActions?.lastGenerationTime?.toFixed(1)}s`)
                  }
                >
                  {/* Mobile: just animated dot */}
                  <span className={`md:hidden w-2 h-2 rounded-full ${getStatusColor()} ${
                    storyActions?.generationStartTime || storyActions?.extractionStatus?.status === 'extracting' 
                      ? 'animate-pulse' 
                      : ''
                  }`} />
                  
                  {/* Desktop: full status with text */}
                  <div className="hidden md:flex items-center gap-1.5 px-2 py-1 text-[10px] text-white/80">
                    <span className={`w-2 h-2 rounded-full ${getStatusColor()} ${
                      storyActions?.generationStartTime || storyActions?.extractionStatus?.status === 'extracting' 
                        ? 'animate-pulse' 
                        : ''
                    }`} />
                    {storyActions?.extractionStatus ? (
                      <span className="max-w-[120px] truncate">{storyActions.extractionStatus.message}</span>
                    ) : storyActions?.generationStartTime ? (
                      <span>Generating...</span>
                    ) : (
                      <span>{storyActions?.lastGenerationTime?.toFixed(1)}s</span>
                    )}
                  </div>
                </div>
              )}

              {/* Character Suggestion - icon only on mobile, with text on desktop */}
              {storyActions?.showCharacterBanner && storyActions?.onDiscoverCharacters && (
                <button
                  onClick={storyActions.onDiscoverCharacters}
                  className="relative flex items-center justify-center w-6 h-6 md:w-auto md:h-auto md:px-2.5 md:py-1.5 rounded-md transition-all hover:bg-white/10 text-amber-400"
                  title="New characters found - click to discover"
                >
                  <Sparkles className="w-3.5 h-3.5 md:w-4 md:h-4" />
                  <span className="hidden md:inline text-xs ml-1.5">New</span>
                  <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 md:w-2 md:h-2 bg-red-500 rounded-full animate-pulse" />
                </button>
              )}

              {/* Menu Button */}
              <button
                onClick={() => setShowUnifiedMenu(true)}
                className="flex items-center justify-center w-6 h-6 md:w-7 md:h-7 rounded-md transition-all hover:bg-white/10 text-white/80 hover:text-white"
                aria-label="Open menu"
              >
                <MenuIcon className="w-3.5 h-3.5 md:w-4 md:h-4" />
              </button>

              {/* TTS Audio Unlock - compact icon */}
              {isMobile && (
                <button
                  onClick={handleEnableTTS}
                  className={`flex items-center justify-center w-6 h-6 rounded-md transition-all duration-200 ${
                    needsPermission
                      ? 'text-orange-400 animate-pulse'
                      : 'text-green-400/70'
                  }`}
                  title={needsPermission ? 'Tap to enable audio' : 'Audio enabled'}
                >
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                    {needsPermission ? (
                      <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM12.293 7.293a1 1 0 011.414 0L15 8.586l1.293-1.293a1 1 0 111.414 1.414L16.414 10l1.293 1.293a1 1 0 01-1.414 1.414L15 11.414l-1.293 1.293a1 1 0 01-1.414-1.414L13.586 10l-1.293-1.293a1 1 0 010-1.414z" clipRule="evenodd" />
                    ) : (
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