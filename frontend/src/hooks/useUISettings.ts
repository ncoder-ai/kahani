import { useEffect } from 'react';
import { useAuthStore } from '@/store';

interface UIPreferences {
  theme: string;
  font_size: string;
  show_token_info: boolean;
  show_context_info: boolean;
  notifications: boolean;
}

export const useUISettings = (settings: UIPreferences | null) => {
  useEffect(() => {
    if (!settings) return;

    // Apply theme
    const root = document.documentElement;
    if (settings.theme === 'light') {
      root.classList.remove('dark');
      root.classList.add('light');
    } else if (settings.theme === 'dark') {
      root.classList.remove('light');
      root.classList.add('dark');
    } else if (settings.theme === 'auto') {
      // Use system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.remove('light', 'dark');
      root.classList.add(prefersDark ? 'dark' : 'light');
    }

    // Apply font size
    root.classList.remove('text-small', 'text-medium', 'text-large');
    root.classList.add(`text-${settings.font_size}`);

    // Store preferences for other components to use
    window.kahaniUISettings = {
      showTokenInfo: settings.show_token_info,
      showContextInfo: settings.show_context_info,
      notifications: settings.notifications,
    };

    // Dispatch custom event for other components to listen to
    window.dispatchEvent(new CustomEvent('kahaniUISettingsChanged', {
      detail: settings
    }));

  }, [settings]);
};

// Global type for window
declare global {
  interface Window {
    kahaniUISettings?: {
      showTokenInfo: boolean;
      showContextInfo: boolean;
      notifications: boolean;
    };
  }
}