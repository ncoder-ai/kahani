import { useEffect } from 'react';
import { useAuthStore } from '@/store';
import { applyTheme } from '@/lib/themes';
import { UIPreferences } from '@/types/settings';

export const useUISettings = (settings: UIPreferences | null) => {
  useEffect(() => {
    if (!settings || typeof window === 'undefined') return;

    // Apply color theme
    applyTheme(settings.color_theme);

    // Apply font size
    const root = document.documentElement;
    root.classList.remove('text-small', 'text-medium', 'text-large');
    root.classList.add(`text-${settings.font_size}`);

    // Store preferences for other components to use
    window.kahaniUISettings = {
      showContextInfo: settings.show_context_info,
      show_token_info: settings.show_token_info,
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
      showContextInfo: boolean;
      show_token_info: boolean;
      notifications: boolean;
    };
  }
}