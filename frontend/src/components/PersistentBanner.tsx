'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { HomeIcon, ArrowLeftIcon, Menu as MenuIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import UnifiedMenu from './UnifiedMenu';
import SettingsModal from './SettingsModal';
import TTSSettingsModal from './TTSSettingsModal';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { audioContextManager } from '@/utils/audioContextManager';

export default function PersistentBanner() {
  const router = useRouter();
  const { user } = useAuthStore();
  const { audioPermissionBlocked } = useGlobalTTS();
  const pathname = usePathname();
  const [canGoBack, setCanGoBack] = useState(false);
  const [showUnifiedMenu, setShowUnifiedMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showTTSSettings, setShowTTSSettings] = useState(false);
  const [ttsPermissionEnabled, setTtsPermissionEnabled] = useState(false);
  
  // Sync with AudioContext state
  useEffect(() => {
    const checkAudioState = () => {
      const isUnlocked = audioContextManager.isAudioUnlocked();
      setTtsPermissionEnabled(isUnlocked);
    };
    
    // Check immediately
    checkAudioState();
    
    // Check periodically to sync with manual unlocks
    const interval = setInterval(checkAudioState, 1000);
    
    return () => clearInterval(interval);
  }, []);
  
  // Compute actual permission state
  const needsPermission = audioPermissionBlocked || !ttsPermissionEnabled;
  
  const handleEnableTTS = async () => {
    console.log('[TTS Permission] Unlocking AudioContext...');
    
    const success = await audioContextManager.unlock();
    
    if (success) {
      setTtsPermissionEnabled(true);
      console.log('[TTS Permission] ✅ AudioContext unlocked! All TTS will now work.');
      // NO ALERT - just visual feedback
    } else {
      console.error('[TTS Permission] ❌ Failed to unlock AudioContext');
    }
  };

  useEffect(() => {
    // Check if we can go back in history
    setCanGoBack(window.history.length > 1);
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
    <div className="fixed top-0 left-0 right-0 z-50 theme-banner backdrop-blur-md border-b border-white/20 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 py-3">
        <div className="flex justify-between items-center">
          {/* Left side - App name and user info */}
          <div className="flex items-center space-x-4">
            {canGoBack && (
              <button
                onClick={handleBack}
                className="flex items-center text-white/80 hover:text-white hover:bg-white/10 px-2 py-2 rounded-lg transition-all duration-200"
                title="Go back"
              >
                <ArrowLeftIcon className="w-5 h-5" />
              </button>
            )}
            <button
              onClick={handleHome}
              className="flex items-center space-x-2 text-white hover:text-purple-200 transition-colors"
            >
              <span className="text-xl font-bold">✨ Kahani</span>
            </button>
            <span className="text-white/60 hidden sm:inline">•</span>
            <span className="text-white/80 text-sm hidden sm:inline">
              Welcome, <span className="text-white font-medium">{user.display_name}</span>
            </span>
          </div>

          {/* Right side - Action buttons */}
          <div className="flex items-center space-x-2">
            {/* TTS Permission Button - Mobile Only */}
            {/iPhone|iPad|iPod|Android/i.test(navigator.userAgent) && (
              <button
                onClick={handleEnableTTS}
                className={`flex items-center space-x-1 px-3 py-2 rounded-lg transition-all duration-200 ${
                  needsPermission
                    ? 'bg-orange-600/20 text-orange-400 hover:bg-orange-600/30 animate-pulse'
                    : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
                }`}
                title={needsPermission ? 'Click to enable TTS' : 'TTS Ready'}
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                  <path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
                </svg>
                <span className="text-xs font-medium">
                  {needsPermission ? '⚠️ Enable TTS' : '✓ TTS Ready'}
                </span>
              </button>
            )}
            
          </div>
        </div>
      </div>

      {/* Floating Menu Button (Bottom-Left) */}
      <button
        onClick={() => setShowUnifiedMenu(true)}
        className="fixed left-4 bottom-4 z-40 theme-btn-primary p-4 rounded-full shadow-2xl transition-all hover:scale-110"
        aria-label="Open menu"
      >
        <MenuIcon className="w-6 h-6 text-white" />
      </button>

      {/* Unified Menu */}
      <UnifiedMenu 
        isOpen={showUnifiedMenu} 
        onClose={() => setShowUnifiedMenu(false)}
        onOpenSettings={() => {
          setShowUnifiedMenu(false);
          setShowSettings(true);
        }}
        isStoryPage={pathname?.startsWith('/story/')}
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
    </div>
  );
}