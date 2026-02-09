'use client';

import { useEffect } from 'react';

/**
 * Fixes errors from browser extensions (like MetaMask) that try to access
 * window.ethereum.selectedAddress before it's initialized
 */
export default function BrowserExtensionFix() {
  useEffect(() => {
    // Only run on client side
    if (typeof window === 'undefined') return;

    // Safely handle window.ethereum access from browser extensions
    try {
      const ethereum = (window as any).ethereum;
      if (ethereum && typeof ethereum.selectedAddress === 'undefined') {
        // Define a safe getter that returns null instead of undefined
        Object.defineProperty(ethereum, 'selectedAddress', {
          get: function() { 
            return null; 
          },
          configurable: true,
          enumerable: true
        });
      }
    } catch (e) {
      // Silently ignore if property can't be defined
      // This is just a safety measure for browser extensions
    }

    // Also add a global error handler to catch any remaining ethereum-related errors
    const originalErrorHandler = window.onerror;
    window.onerror = function(message, source, lineno, colno, error) {
      // Ignore errors related to ethereum.selectedAddress
      if (typeof message === 'string' && message.includes('ethereum') && message.includes('selectedAddress')) {
        return true; // Suppress the error
      }
      // Call original handler if it exists
      if (originalErrorHandler) {
        return originalErrorHandler.call(this, message, source, lineno, colno, error);
      }
      return false;
    };

    return () => {
      // Restore original error handler on unmount
      if (originalErrorHandler) {
        window.onerror = originalErrorHandler;
      }
    };
  }, []);

  return null; // This component doesn't render anything
}

