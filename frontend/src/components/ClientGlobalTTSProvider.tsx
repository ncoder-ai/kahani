'use client';

import { useEffect, useState } from 'react';
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext';
import { getApiBaseUrl } from '@/lib/apiUrl';

export default function ClientGlobalTTSProvider({ children }: { children: React.ReactNode }) {
  const [apiBaseUrl, setApiBaseUrl] = useState('http://localhost:9876');
  
  useEffect(() => {
    // This runs only on the client side after mount
    setApiBaseUrl(getApiBaseUrl());
  }, []);
  
  return (
    <GlobalTTSProvider apiBaseUrl={apiBaseUrl}>
      {children}
    </GlobalTTSProvider>
  );
}
