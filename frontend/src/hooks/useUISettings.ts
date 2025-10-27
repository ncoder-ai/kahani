import { useEffect } from 'react';
import { useAuthStore } from '@/store';
import { applyTheme } from '@/lib/themes';

interface UIPreferences {
  color_theme: string;
  font_size: string;
  show_token_info: boolean;
  show_context_info: boolean;
  notifications: boolean;
}

export const useUISettings = (settings: UIPreferences | null) => {
  useEffect(() => {
    if (!settings) return;

    // Apply color theme
    applyTheme(settings.color_theme);

    // Apply font size
    const root = document.documentElement;
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