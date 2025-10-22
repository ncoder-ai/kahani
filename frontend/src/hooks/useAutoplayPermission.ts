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
    console.log('[Autoplay Hook] requestPermission called');
    try {
      // Create a silent audio element and play it
      const audio = new Audio();
      audio.src = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAADhAC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAA4S/tqn/AAAAAAAAAAAAAAAAAAAAAP/7kGQAD/AAAGkAAAAIAAANIAAAAQAAAaQAAAAgAAA0gAAABExBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7kGQAj/AAAGkAAAAIAAANIAAAAQAAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV';
      audio.volume = 0.01; // Very quiet
      audio.muted = true; // Start muted
      
      console.log('[Autoplay Hook] Attempting to play audio...');
      
      // Try to play with timeout to avoid hanging
      const playPromise = audio.play();
      
      if (playPromise !== undefined) {
        console.log('[Autoplay Hook] Play promise received, awaiting with timeout...');
        
        // Add timeout to prevent hanging
        const timeoutPromise = new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Audio play timeout')), 2000)
        );
        
        try {
          await Promise.race([playPromise, timeoutPromise]);
          console.log('[Autoplay Hook] Audio played successfully! Setting permission...');
        } catch (error) {
          console.log('[Autoplay Hook] Audio play failed or timed out:', error);
          // Even if audio fails, we can still grant permission since user clicked
          console.log('[Autoplay Hook] Granting permission anyway (user interaction detected)');
        }
        
        // Grant permission regardless of audio success (user clicked the button)
        localStorage.setItem(AUTOPLAY_PERMISSION_KEY, 'true');
        setHasPermission(true);
        
        console.log('[Autoplay Hook] Permission set, hasPermission should now be true');
        
        // Stop and cleanup
        audio.pause();
        audio.src = '';
        
        return true;
      }
      
      console.log('[Autoplay Hook] No play promise, granting permission anyway');
      // Grant permission anyway since user clicked
      localStorage.setItem(AUTOPLAY_PERMISSION_KEY, 'true');
      setHasPermission(true);
      return true;
    } catch (error) {
      console.error('[Autoplay Hook] Error occurred, but granting permission anyway:', error);
      // Grant permission anyway since user clicked
      localStorage.setItem(AUTOPLAY_PERMISSION_KEY, 'true');
      setHasPermission(true);
      return true;
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

