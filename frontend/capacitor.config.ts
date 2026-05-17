import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.makemysaga.app',
  appName: 'Saga',
  webDir: 'capacitor-shell',
  backgroundColor: '#0a0a0f',
  server: {
    androidScheme: 'https',
    iosScheme: 'capacitor',
    allowNavigation: ['*'],
  },
  ios: {
    contentInset: 'always',
    backgroundColor: '#0a0a0f',
  },
  android: {
    backgroundColor: '#0a0a0f',
  },
  plugins: {
    Keyboard: {
      // 'native' resizes the WebView viewport when the on-screen
      // keyboard appears, so inputs above the keyboard stay visible
      // (and inputs below scroll into view via the browser's default
      // focus behavior). 'body' is an alternative that only changes
      // the body height — works for simple layouts but breaks
      // fixed/sticky elements. 'ionic' is for Ionic apps only.
      resize: 'native',
      // Match the dark theme so the keyboard frame doesn't flash
      // a white background on appearance.
      style: 'DARK',
      // Apply resize even when the app is presented full-screen
      // (no nav bar) — Kahani's auth screens cover the whole
      // viewport, and we still want resize behavior there.
      resizeOnFullScreen: true,
    },
  },
};

export default config;
