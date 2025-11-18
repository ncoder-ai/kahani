export interface ThemeColors {
  name: string;
  displayName: string;
  description: string;
  colors: {
    // Banner
    bannerFrom: string;
    bannerVia: string;
    bannerTo: string;
    
    // Backgrounds
    bgPrimary: string;
    bgSecondary: string;
    bgTertiary: string;
    
    // Cards & Surfaces
    cardBg: string;
    cardBorder: string;
    cardHoverBorder: string;
    
    // Buttons - Primary
    btnPrimary: string;
    btnPrimaryHover: string;
    btnPrimaryText: string;
    
    // Buttons - Secondary
    btnSecondary: string;
    btnSecondaryHover: string;
    btnSecondaryText: string;
    
    // Text
    textPrimary: string;
    textSecondary: string;
    textTertiary: string;
    
    // Accents
    accentPrimary: string;
    accentSecondary: string;
    borderAccent: string;
    
    // Scene bubbles (for bubble format)
    sceneBubbleFrom: string;
    sceneBubbleTo: string;
    sceneBubbleBorder: string;
  };
}

export const themes: Record<string, ThemeColors> = {
  'pure-dark': {
    name: 'pure-dark',
    displayName: 'Pure Dark',
    description: 'Minimal, distraction-free, OLED-friendly',
    colors: {
      bannerFrom: '#0a0a0a',
      bannerVia: '#171717',
      bannerTo: '#0a0a0a',
      bgPrimary: '#000000',
      bgSecondary: '#0a0a0a',
      bgTertiary: '#171717',
      cardBg: '#171717',
      cardBorder: 'rgba(115, 115, 115, 0.5)',
      cardHoverBorder: 'rgba(163, 163, 163, 0.5)',
      btnPrimary: '#404040',
      btnPrimaryHover: '#525252',
      btnPrimaryText: '#ffffff',
      btnSecondary: '#525252',
      btnSecondaryHover: '#737373',
      btnSecondaryText: '#ffffff',
      textPrimary: '#ffffff',
      textSecondary: '#d4d4d4',
      textTertiary: '#a3a3a3',
      accentPrimary: '#d4d4d4',
      accentSecondary: '#a3a3a3',
      borderAccent: 'rgba(115, 115, 115, 0.3)',
      sceneBubbleFrom: 'rgba(38, 38, 38, 0.5)',
      sceneBubbleTo: 'rgba(64, 64, 64, 0.5)',
      sceneBubbleBorder: 'rgba(115, 115, 115, 0.2)',
    }
  },
  'midnight-blue': {
    name: 'midnight-blue',
    displayName: 'Midnight Blue',
    description: 'Professional, calm, easy on the eyes',
    colors: {
      bannerFrom: '#020617',
      bannerVia: '#172554',
      bannerTo: '#020617',
      bgPrimary: '#020617',
      bgSecondary: '#0f172a',
      bgTertiary: '#1e293b',
      cardBg: '#0f172a',
      cardBorder: 'rgba(30, 58, 138, 0.3)',
      cardHoverBorder: 'rgba(59, 130, 246, 0.5)',
      btnPrimary: '#2563eb',
      btnPrimaryHover: '#1d4ed8',
      btnPrimaryText: '#ffffff',
      btnSecondary: '#334155',
      btnSecondaryHover: '#475569',
      btnSecondaryText: '#ffffff',
      textPrimary: '#ffffff',
      textSecondary: '#e2e8f0',
      textTertiary: '#94a3b8',
      accentPrimary: '#22d3ee',
      accentSecondary: '#06b6d4',
      borderAccent: 'rgba(6, 182, 212, 0.2)',
      sceneBubbleFrom: 'rgba(30, 58, 138, 0.3)',
      sceneBubbleTo: 'rgba(88, 28, 135, 0.3)',
      sceneBubbleBorder: 'rgba(59, 130, 246, 0.2)',
    }
  },
  'forest-night': {
    name: 'forest-night',
    displayName: 'Forest Night',
    description: 'Natural, calming, unique',
    colors: {
      bannerFrom: '#022c22',
      bannerVia: '#134e4a',
      bannerTo: '#022c22',
      bgPrimary: '#020617',
      bgSecondary: '#0f172a',
      bgTertiary: '#1e293b',
      cardBg: '#0f172a',
      cardBorder: 'rgba(6, 78, 59, 0.3)',
      cardHoverBorder: 'rgba(16, 185, 129, 0.5)',
      btnPrimary: '#10b981',
      btnPrimaryHover: '#059669',
      btnPrimaryText: '#ffffff',
      btnSecondary: '#0f766e',
      btnSecondaryHover: '#0d9488',
      btnSecondaryText: '#ffffff',
      textPrimary: '#ffffff',
      textSecondary: '#d1fae5',
      textTertiary: '#6ee7b7',
      accentPrimary: '#a3e635',
      accentSecondary: '#84cc16',
      borderAccent: 'rgba(16, 185, 129, 0.2)',
      sceneBubbleFrom: 'rgba(6, 78, 59, 0.3)',
      sceneBubbleTo: 'rgba(20, 83, 45, 0.3)',
      sceneBubbleBorder: 'rgba(16, 185, 129, 0.2)',
    }
  },
  'crimson-noir': {
    name: 'crimson-noir',
    displayName: 'Crimson Noir',
    description: 'Dramatic, intense, high contrast',
    colors: {
      bannerFrom: '#0a0a0a',
      bannerVia: '#450a0a',
      bannerTo: '#0a0a0a',
      bgPrimary: '#000000',
      bgSecondary: '#0a0a0a',
      bgTertiary: '#171717',
      cardBg: '#171717',
      cardBorder: 'rgba(127, 29, 29, 0.3)',
      cardHoverBorder: 'rgba(220, 38, 38, 0.5)',
      btnPrimary: '#b91c1c',
      btnPrimaryHover: '#991b1b',
      btnPrimaryText: '#ffffff',
      btnSecondary: '#404040',
      btnSecondaryHover: '#525252',
      btnSecondaryText: '#ffffff',
      textPrimary: '#ffffff',
      textSecondary: '#fecaca',
      textTertiary: '#fca5a5',
      accentPrimary: '#fb7185',
      accentSecondary: '#f43f5e',
      borderAccent: 'rgba(239, 68, 68, 0.2)',
      sceneBubbleFrom: 'rgba(127, 29, 29, 0.3)',
      sceneBubbleTo: 'rgba(153, 27, 27, 0.3)',
      sceneBubbleBorder: 'rgba(220, 38, 38, 0.2)',
    }
  },
  'amber-dusk': {
    name: 'amber-dusk',
    displayName: 'Amber Dusk',
    description: 'Cozy, warm, comfortable reading',
    colors: {
      bannerFrom: '#451a03',
      bannerVia: '#7c2d12',
      bannerTo: '#451a03',
      bgPrimary: '#0c0a09',
      bgSecondary: '#1c1917',
      bgTertiary: '#292524',
      cardBg: '#1c1917',
      cardBorder: 'rgba(120, 53, 15, 0.3)',
      cardHoverBorder: 'rgba(217, 119, 6, 0.5)',
      btnPrimary: '#d97706',
      btnPrimaryHover: '#b45309',
      btnPrimaryText: '#ffffff',
      btnSecondary: '#57534e',
      btnSecondaryHover: '#78716c',
      btnSecondaryText: '#ffffff',
      textPrimary: '#ffffff',
      textSecondary: '#fef3c7',
      textTertiary: '#fcd34d',
      accentPrimary: '#fbbf24',
      accentSecondary: '#f59e0b',
      borderAccent: 'rgba(217, 119, 6, 0.2)',
      sceneBubbleFrom: 'rgba(120, 53, 15, 0.3)',
      sceneBubbleTo: 'rgba(180, 83, 9, 0.3)',
      sceneBubbleBorder: 'rgba(217, 119, 6, 0.2)',
    }
  },
  'purple-dream': {
    name: 'purple-dream',
    displayName: 'Purple Dream',
    description: 'Original theme - vibrant and creative',
    colors: {
      bannerFrom: 'rgba(88, 28, 135, 0.95)',
      bannerVia: 'rgba(30, 58, 138, 0.95)',
      bannerTo: 'rgba(67, 56, 202, 0.95)',
      bgPrimary: '#0f172a',
      bgSecondary: '#1e293b',
      bgTertiary: '#334155',
      cardBg: '#1e293b',
      cardBorder: 'rgba(147, 51, 234, 0.3)',
      cardHoverBorder: 'rgba(168, 85, 247, 0.5)',
      btnPrimary: '#a855f7',
      btnPrimaryHover: '#9333ea',
      btnPrimaryText: '#ffffff',
      btnSecondary: '#4c1d95',
      btnSecondaryHover: '#5b21b6',
      btnSecondaryText: '#ffffff',
      textPrimary: '#ffffff',
      textSecondary: '#e9d5ff',
      textTertiary: '#c084fc',
      accentPrimary: '#c084fc',
      accentSecondary: '#a855f7',
      borderAccent: 'rgba(168, 85, 247, 0.2)',
      sceneBubbleFrom: 'rgba(30, 58, 138, 0.3)',
      sceneBubbleTo: 'rgba(88, 28, 135, 0.3)',
      sceneBubbleBorder: 'rgba(59, 130, 246, 0.2)',
    }
  }
};

export function applyTheme(themeName: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return; // Don't run during SSR
  }
  
  const theme = themes[themeName] || themes['pure-dark'];
  const root = document.documentElement;
  
  // Set data attribute for theme
  root.setAttribute('data-theme', theme.name);
  
  // Apply CSS variables
  Object.entries(theme.colors).forEach(([key, value]) => {
    root.style.setProperty(`--color-${key}`, value);
  });
}

export function getThemeList() {
  return Object.values(themes).map(t => ({
    value: t.name,
    label: t.displayName,
    description: t.description
  }));
}

// Apply default theme only on client-side to prevent hydration mismatch
// This is now handled in useUISettings hook instead of module load
// Theme will be applied when user settings are loaded or on first render
