'use client';

import { useState } from 'react';
import { useAutoplayPermission } from '@/hooks/useAutoplayPermission';

export default function AutoplayPermissionBanner() {
  const { isEnabled, toggleAutoplay, isChecking } = useAutoplayPermission();
  const [isDismissed, setIsDismissed] = useState(false);

  // Don't show if user dismissed or still checking
  if (isDismissed || isChecking) {
    return null;
  }

  const handleToggle = () => {
    toggleAutoplay();
  };

  const handleDismiss = () => {
    setIsDismissed(true);
  };

  return (
    <div className="fixed top-20 right-4 left-4 md:left-auto md:w-80 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg shadow-lg p-4 z-[100] animate-slide-down">
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0">
          {isEnabled ? (
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
            </svg>
          )}
        </div>
        
        <div className="flex-1">
          <h3 className="font-semibold text-sm mb-1">
            Audio Autoplay
          </h3>
          <p className="text-xs text-white/90">
            {isEnabled ? 'Audio is enabled for new scenes' : 'Audio is disabled for new scenes'}
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={handleToggle}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              isEnabled 
                ? 'bg-green-500 hover:bg-green-600 text-white' 
                : 'bg-gray-500 hover:bg-gray-600 text-white'
            }`}
          >
            {isEnabled ? 'ON' : 'OFF'}
          </button>
          
          <button
            onClick={handleDismiss}
            className="text-white/70 hover:text-white p-1"
            aria-label="Dismiss"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

