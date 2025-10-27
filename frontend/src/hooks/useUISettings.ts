import { useEffect } from 'react';
import { useAuthStore } from '@/store';
import { applyTheme } from '@/lib/themes';

interface UIPreferences {
  color_theme: string;
  font_size: string;
  show_context_info: boolean;
  notifications: boolean;
}

export const useUISettings = (settings: UIPreferences | null) => {
  useEffect(() => {
    console.log('useUISettings called with:', settings);
    if (!settings) return;

    // Apply color theme
    applyTheme(settings.color_theme);

    // Apply font size
    const root = document.documentElement;
    root.classList.remove('text-small', 'text-medium', 'text-large');
    root.classList.add(`text-${settings.font_size}`);

    // Store preferences for other components to use
    window.kahaniUISettings = {
      showContextInfo: settings.show_context_info,
      notifications: settings.notifications,
    };

    console.log('useUISettings setting window.kahaniUISettings:', window.kahaniUISettings);

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
      showContextInfo: boolean;
      notifications: boolean;
    };
  }
}