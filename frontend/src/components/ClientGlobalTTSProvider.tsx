'use client';

import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext';

// GlobalTTSProvider now gets the API URL internally via getApiBaseUrl()
// This wrapper is kept for backward compatibility
export default function ClientGlobalTTSProvider({ children }: { children: React.ReactNode }) {
  return (
    <GlobalTTSProvider>
      {children}
    </GlobalTTSProvider>
  );
}
