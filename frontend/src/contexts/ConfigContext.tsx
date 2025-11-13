'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { getFrontendConfig } from '@/lib/config';
import type { FrontendConfig } from '@/lib/config';
import { setContextConfig, clearContextConfig } from '@/lib/apiUrl';

interface ConfigContextType {
  // Config data
  config: FrontendConfig | null;
  isLoading: boolean;
  error: string | null;
  
  // Helper functions
  getApiBaseUrl: () => Promise<string>;
  getBackendPort: () => Promise<number>;
  getTTSProviderUrls: () => Promise<{
    openai_compatible: string;
    chatterbox: string;
    kokoro: string;
  }>;
  getExtractionDefaultUrl: () => Promise<string>;
  getSTTWebSocketPath: () => Promise<string>;
  getTTSWebSocketPath: () => Promise<string>;
  
  // Actions
  reloadConfig: () => Promise<void>;
}

const ConfigContext = createContext<ConfigContextType | undefined>(undefined);

interface ConfigProviderProps {
  children: React.ReactNode;
}

export function ConfigProvider({ children }: ConfigProviderProps) {
  const [config, setConfig] = useState<FrontendConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const loadedConfig = await getFrontendConfig();
      setConfig(loadedConfig);
      
      // Update apiUrl.ts with the backend port so it can use cached config
      setContextConfig(loadedConfig.server.backend.port);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load configuration';
      setError(errorMessage);
      console.error('[ConfigContext] Failed to load config:', err);
      // Clear context config on error
      clearContextConfig();
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Load config once on mount
  useEffect(() => {
    loadConfig();
    
    // Cleanup: clear context config on unmount
    return () => {
      clearContextConfig();
    };
  }, [loadConfig]);

  // Helper function to get API base URL
  const getApiBaseUrl = useCallback(async (): Promise<string> => {
    if (!config) {
      // If config not loaded yet, wait for it
      if (isLoading) {
        // Wait for config to load
        await new Promise<void>((resolve) => {
          const checkConfig = () => {
            if (config || error) {
              resolve();
            } else {
              setTimeout(checkConfig, 50);
            }
          };
          checkConfig();
        });
      }
      
      if (!config) {
        throw new Error('Configuration not available');
      }
    }

    // Server-side: use environment variable
    if (typeof window === 'undefined') {
      if (process.env.NEXT_PUBLIC_API_URL) {
        return process.env.NEXT_PUBLIC_API_URL;
      }
      return `http://localhost:${config.server.backend.port}`;
    }

    // Client-side: use window.location to build API URL
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;
    const port = window.location.port;

    // Check if we're using a reverse proxy (no port in URL or standard ports)
    const isReverseProxy = !port || port === '80' || port === '443';

    if (isReverseProxy) {
      // For reverse proxy: use /api on the same domain
      return `${protocol}//${hostname}`;
    }

    // For direct access: use backend port from config
    return `${protocol}//${hostname}:${config.server.backend.port}`;
  }, [config, isLoading, error]);

  // Helper functions that use cached config
  const getBackendPort = useCallback(async (): Promise<number> => {
    if (!config) {
      throw new Error('Configuration not loaded');
    }
    return config.server.backend.port;
  }, [config]);

  const getTTSProviderUrls = useCallback(async () => {
    if (!config) {
      throw new Error('Configuration not loaded');
    }
    return config.tts.default_providers;
  }, [config]);

  const getExtractionDefaultUrl = useCallback(async (): Promise<string> => {
    if (!config) {
      throw new Error('Configuration not loaded');
    }
    return config.extraction.default_url;
  }, [config]);

  const getSTTWebSocketPath = useCallback(async (): Promise<string> => {
    if (!config) {
      throw new Error('Configuration not loaded');
    }
    return config.websocket.stt_path;
  }, [config]);

  const getTTSWebSocketPath = useCallback(async (): Promise<string> => {
    if (!config) {
      throw new Error('Configuration not loaded');
    }
    return config.websocket.tts_path;
  }, [config]);

  const value = useMemo<ConfigContextType>(
    () => ({
      config,
      isLoading,
      error,
      getApiBaseUrl,
      getBackendPort,
      getTTSProviderUrls,
      getExtractionDefaultUrl,
      getSTTWebSocketPath,
      getTTSWebSocketPath,
      reloadConfig: loadConfig,
    }),
    [
      config,
      isLoading,
      error,
      getApiBaseUrl,
      getBackendPort,
      getTTSProviderUrls,
      getExtractionDefaultUrl,
      getSTTWebSocketPath,
      getTTSWebSocketPath,
      loadConfig,
    ]
  );

  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig(): ConfigContextType {
  const context = useContext(ConfigContext);
  if (!context) {
    throw new Error('useConfig must be used within ConfigProvider');
  }
  return context;
}

// Export the config type for use in other files
export type { FrontendConfig };

