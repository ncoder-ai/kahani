'use client';

import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import { CogIcon, ArrowLeftOnRectangleIcon, HomeIcon, ArrowLeftIcon, SpeakerWaveIcon, SpeakerXMarkIcon } from '@heroicons/react/24/outline';
import { useEffect, useState } from 'react';
import { useAutoplayPermission } from '@/hooks/useAutoplayPermission';

export default function PersistentBanner() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [canGoBack, setCanGoBack] = useState(false);
  const { isEnabled, toggleAutoplay } = useAutoplayPermission();

  useEffect(() => {
    // Check if we can go back in history
    setCanGoBack(window.history.length > 1);
  }, []);

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const handleSettings = () => {
    router.push('/settings');
  };

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
            <button
              onClick={handleHome}
              className="flex items-center space-x-1 text-white/80 hover:text-white hover:bg-white/10 px-3 py-2 rounded-lg transition-all duration-200"
              title="Dashboard"
            >
              <HomeIcon className="w-4 h-4" />
              <span className="hidden sm:inline text-sm">Dashboard</span>
            </button>
            
            {/* Audio Toggle Button */}
            <button
              onClick={toggleAutoplay}
              className={`flex items-center space-x-1 px-3 py-2 rounded-lg transition-all duration-200 ${
                isEnabled 
                  ? 'text-green-300 hover:text-green-200 hover:bg-green-500/20' 
                  : 'text-white/80 hover:text-white hover:bg-white/10'
              }`}
              title={isEnabled ? 'Audio enabled - click to disable' : 'Audio disabled - click to enable'}
            >
              {isEnabled ? (
                <SpeakerWaveIcon className="w-4 h-4" />
              ) : (
                <SpeakerXMarkIcon className="w-4 h-4" />
              )}
              <span className="hidden sm:inline text-sm">
                {isEnabled ? 'Audio ON' : 'Audio OFF'}
              </span>
            </button>
            
            <button
              onClick={handleSettings}
              className="flex items-center space-x-1 text-white/80 hover:text-white hover:bg-white/10 px-3 py-2 rounded-lg transition-all duration-200"
              title="Settings"
            >
              <CogIcon className="w-4 h-4" />
              <span className="hidden sm:inline text-sm">Settings</span>
            </button>
            
            <button
              onClick={handleLogout}
              className="flex items-center space-x-1 text-white/80 hover:text-white hover:bg-white/10 px-3 py-2 rounded-lg transition-all duration-200"
              title="Sign Out"
            >
              <ArrowLeftOnRectangleIcon className="w-4 h-4" />
              <span className="hidden sm:inline text-sm">Sign Out</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}