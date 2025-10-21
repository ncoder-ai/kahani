'use client';

import { useState, useEffect } from 'react';
import { useAutoplayPermission } from '@/hooks/useAutoplayPermission';

export default function AutoplayPermissionBanner() {
  const { hasPermission, requestPermission } = useAutoplayPermission();
  const [isDismissed, setIsDismissed] = useState(false);
  const [isRequesting, setIsRequesting] = useState(false);
  const [permissionGranted, setPermissionGranted] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  // Don't show if already has permission, user dismissed, or permission just granted
  if (hasPermission || isDismissed || permissionGranted) {
    return null;
  }

  const handleEnableAutoplay = async () => {
    setIsRequesting(true);
    const granted = await requestPermission();
    setIsRequesting(false);
    
    if (granted) {
      console.log('[Autoplay] Permission granted!');
      // Start closing animation
      setIsClosing(true);
      // Wait for animation, then hide
      setTimeout(() => {
        setPermissionGranted(true);
      }, 500); // Match animation duration
    } else {
      alert('Failed to enable autoplay. Please check your browser settings and try again.');
    }
  };

  const handleDismiss = () => {
    setIsDismissed(true);
  };

  return (
    <div className={`fixed top-20 right-4 left-4 md:left-auto md:w-96 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg shadow-lg p-4 z-[100] transition-all duration-500 ${
      isClosing ? 'opacity-0 translate-y-4 scale-95' : 'opacity-100 translate-y-0 scale-100 animate-slide-down'
    }`}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15.536a5 5 0 001.414 1.414m-2.828-9.9a9 9 0 0112.728 0M12 18v.01" />
          </svg>
        </div>
        
        <div className="flex-1">
          <h3 className="font-semibold text-sm mb-1">
            Enable Audio Autoplay
          </h3>
          <p className="text-xs text-white/90 mb-3">
            Click below to enable automatic audio playback for text-to-speech. This is required only once.
          </p>
          
          <div className="flex gap-2">
            <button
              onClick={handleEnableAutoplay}
              disabled={isRequesting}
              className="px-4 py-2 bg-white text-purple-600 rounded-md text-sm font-medium hover:bg-purple-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRequesting ? 'Enabling...' : 'Enable Autoplay'}
            </button>
            
            <button
              onClick={handleDismiss}
              className="px-3 py-2 text-white/90 hover:text-white text-sm"
            >
              Dismiss
            </button>
          </div>
        </div>
        
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 text-white/70 hover:text-white"
          aria-label="Close"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}

