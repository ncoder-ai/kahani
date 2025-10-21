/**
 * Hook for managing audio autoplay permissions
 * 
 * Browsers block audio autoplay without user interaction.
 * This hook provides a one-time permission flow.
 */

import { useState, useEffect, useCallback } from 'react';

const AUTOPLAY_PERMISSION_KEY = 'kahani_autoplay_enabled';

export const useAutoplayPermission = () => {
  const [hasPermission, setHasPermission] = useState(false);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    // Check if permission was previously granted
    const stored = localStorage.getItem(AUTOPLAY_PERMISSION_KEY);
    setHasPermission(stored === 'true');
    setIsChecking(false);
  }, []);

  /**
   * Request autoplay permission by playing a silent audio clip
   * This must be called in response to a user gesture (click/tap)
   */
  const requestPermission = useCallback(async (): Promise<boolean> => {
    try {
      // Create a silent audio element and play it
      const audio = new Audio();
      audio.src = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAADhAC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAA4S/tqn/AAAAAAAAAAAAAAAAAAAAAP/7kGQAD/AAAGkAAAAIAAANIAAAAQAAAaQAAAAgAAA0gAAABExBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7kGQAj/AAAGkAAAAIAAANIAAAAQAAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV';
      audio.volume = 0.01; // Very quiet
      audio.muted = true; // Start muted
      
      // Play the audio
      const playPromise = audio.play();
      
      if (playPromise !== undefined) {
        await playPromise;
        
        // If we got here, autoplay is allowed
        localStorage.setItem(AUTOPLAY_PERMISSION_KEY, 'true');
        setHasPermission(true);
        
        // Stop and cleanup
        audio.pause();
        audio.src = '';
        
        return true;
      }
      
      return false;
    } catch (error) {
      console.error('[Autoplay] Permission denied:', error);
      return false;
    }
  }, []);

  /**
   * Reset permission (for testing or user preference)
   */
  const resetPermission = useCallback(() => {
    localStorage.removeItem(AUTOPLAY_PERMISSION_KEY);
    setHasPermission(false);
  }, []);

  return {
    hasPermission,
    isChecking,
    requestPermission,
    resetPermission
  };
};

