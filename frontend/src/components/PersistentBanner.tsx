'use client';

import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import { HomeIcon, ArrowLeftIcon, Bars3Icon } from '@heroicons/react/24/outline';
import { useEffect, useState } from 'react';
import GlobalMenu from './GlobalMenu';
import TTSSettingsModal from './TTSSettingsModal';

export default function PersistentBanner() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [canGoBack, setCanGoBack] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showTTSSettings, setShowTTSSettings] = useState(false);

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
    <div className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-r from-purple-900/95 via-blue-900/95 to-indigo-900/95 backdrop-blur-md border-b border-white/20 shadow-lg">
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
            {/* Menu Button */}
            <button
              onClick={() => setShowMenu(true)}
              className="flex items-center space-x-1 text-white/80 hover:text-white hover:bg-white/10 px-3 py-2 rounded-lg transition-all duration-200"
              title="Menu"
            >
              <Bars3Icon className="w-5 h-5" />
              <span className="hidden sm:inline text-sm">Menu</span>
            </button>
          </div>
        </div>
      </div>

      {/* Global Menu */}
      <GlobalMenu 
        isOpen={showMenu} 
        onClose={() => setShowMenu(false)}
        onOpenTTSSettings={() => setShowTTSSettings(true)}
      />

      {/* TTS Settings Modal */}
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