'use client';

import { useEffect } from 'react';

/**
 * Loads Eruda console for mobile debugging
 * Only loads on mobile devices to avoid affecting desktop
 */
export const MobileDebugger: React.FC = () => {
  useEffect(() => {
    // Dev-only: NEXT_PUBLIC_APP_ENV is inlined at build time via Dockerfile ARG
    if (process.env.NEXT_PUBLIC_APP_ENV !== 'development') return;

    // Only load on mobile devices
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

    if (isMobile && typeof window !== 'undefined') {
      // Load Eruda script
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/eruda';
      document.body.appendChild(script);
      
      script.onload = () => {
        // Initialize Eruda
        if ((window as any).eruda) {
          (window as any).eruda.init();
        }
      };
      
      script.onerror = () => {
        console.error('[MobileDebugger] Failed to load Eruda console');
      };
    }
  }, []);
  
  return null; // This component doesn't render anything
};

