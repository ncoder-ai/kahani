'use client';

import { useEffect, useState } from 'react';
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext';
import { getApiBaseUrl } from '@/lib/apiUrl';

export default function ClientGlobalTTSProvider({ children }: { children: React.ReactNode }) {
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  
  useEffect(() => {
    // This runs only on the client side after mount
    // Load API URL from config API
    const loadApiUrl = async () => {
      try {
        const { getApiBaseUrl } = await import('@/lib/apiUrl');
        const url = await getApiBaseUrl();
        setApiBaseUrl(url);
      } catch (error) {
        console.error('Failed to load API URL from config:', error);
        // Will remain empty, which will cause errors - config must be available
      }
    };
    loadApiUrl();
  }, []);
  
  return (
    <GlobalTTSProvider apiBaseUrl={apiBaseUrl}>
      {children}
    </GlobalTTSProvider>
  );
}
