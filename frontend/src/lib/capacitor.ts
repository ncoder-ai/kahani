import { Capacitor } from '@capacitor/core';

export type NativePlatform = 'ios' | 'android';
export type Platform = NativePlatform | 'web';

export function isNative(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return Capacitor.isNativePlatform();
  } catch {
    return false;
  }
}

export function getPlatform(): Platform {
  if (typeof window === 'undefined') return 'web';
  try {
    return Capacitor.getPlatform() as Platform;
  } catch {
    return 'web';
  }
}

export function isIOS(): boolean {
  return getPlatform() === 'ios';
}

export function isAndroid(): boolean {
  return getPlatform() === 'android';
}

export function hasPlugin(name: string): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return Capacitor.isPluginAvailable(name);
  } catch {
    return false;
  }
}

const SERVER_URL_KEY = 'kahani.serverUrl';

/**
 * Disconnect the mobile app from its currently-stored backend server.
 * Clears the saved URL from Capacitor Preferences and navigates the
 * WebView back to the bundled launcher, which will then show the
 * server-URL entry form again.
 *
 * No-op outside the Capacitor native shell.
 */
export async function disconnect(): Promise<void> {
  if (!isNative()) return;

  try {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.remove({ key: SERVER_URL_KEY });
  } catch {
    // Preferences plugin missing or failed — launcher's ?reset=1 path
    // will clear localStorage as a fallback when it reboots.
  }

  const scheme = getPlatform() === 'ios' ? 'capacitor' : 'https';
  window.location.href = `${scheme}://localhost/?reset=1`;
}
