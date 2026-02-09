/**
 * Hook for managing audio autoplay permissions
 * 
 * Provides a simple mute/unmute toggle for audio autoplay.
 * Users can control audio on/off as needed.
 */

import { useState, useEffect, useCallback } from 'react';

const AUTOPLAY_ENABLED_KEY = 'kahani_autoplay_enabled';

export const useAutoplayPermission = () => {
  const [isEnabled, setIsEnabled] = useState(false);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    // Check if autoplay was previously enabled
    const stored = localStorage.getItem(AUTOPLAY_ENABLED_KEY);
    setIsEnabled(stored === 'true');
    setIsChecking(false);
  }, []);

  /**
   * Toggle autoplay on/off
   */
  const toggleAutoplay = useCallback(() => {
    const newState = !isEnabled;
    setIsEnabled(newState);
    localStorage.setItem(AUTOPLAY_ENABLED_KEY, newState.toString());
  }, [isEnabled]);

  /**
   * Enable autoplay (for compatibility with existing code)
   */
  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!isEnabled) {
      toggleAutoplay();
    }
    return true; // Always return true since we're just toggling a preference
  }, [isEnabled, toggleAutoplay]);

  /**
   * Disable autoplay
   */
  const disableAutoplay = useCallback(() => {
    if (isEnabled) {
      toggleAutoplay();
    }
  }, [isEnabled, toggleAutoplay]);

  return {
    hasPermission: isEnabled, // For compatibility with existing code
    isEnabled,
    isChecking,
    toggleAutoplay,
    requestPermission, // For compatibility
    disableAutoplay
  };
};

