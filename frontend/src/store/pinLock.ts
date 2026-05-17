/**
 * App PIN lock store.
 *
 * Two distinct concerns intentionally kept separate:
 *
 * 1. `pinLockSettings` — PERSISTED to localStorage. Holds the user's
 *    preferences (timeout in minutes). The fact a PIN is *set* lives
 *    in the iOS Keychain via the native plugin; we just mirror its
 *    presence here so the UI can render the right toggle state.
 *
 * 2. `pinLockSession` — IN-MEMORY only. Holds the unlocked/locked
 *    state and the timestamp of the last successful unlock. Persisting
 *    these would defeat the lock entirely, since closing+reopening
 *    the app would restore "isUnlocked: true" from disk. The session
 *    store is wiped on any cold start.
 *
 * Lifecycle wiring lives in `useAppLockLifecycle()` (see below): it
 * listens to Capacitor's `appStateChange` event and re-locks the
 * session if the app was backgrounded longer than the user's timeout.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useEffect } from 'react';
import nativePinLock from '@/utils/nativePinLock';

export type LockTimeoutOption = 'immediate' | '1' | '5' | '15' | 'never';

const TIMEOUT_MINUTES: Record<LockTimeoutOption, number | null> = {
  immediate: 0,
  '1': 1,
  '5': 5,
  '15': 15,
  never: null,
};

// ---------------- PERSISTED settings ----------------

interface PinLockSettingsState {
  /** Last-known presence of a PIN in the native keychain. Refreshed
   *  via refreshPinStatus(); kept in sync with native truth. */
  pinEnabled: boolean;
  /** How long to wait before re-locking after backgrounding. */
  timeout: LockTimeoutOption;
  setPinEnabled: (v: boolean) => void;
  setTimeout: (t: LockTimeoutOption) => void;
}

export const usePinLockSettings = create<PinLockSettingsState>()(
  persist(
    (set) => ({
      pinEnabled: false,
      timeout: '5',
      setPinEnabled: (v) => set({ pinEnabled: v }),
      setTimeout: (t) => set({ timeout: t }),
    }),
    {
      name: 'pin-lock-settings',
    },
  ),
);

// ---------------- SESSION state (never persisted) ----------------

interface PinLockSessionState {
  /**
   * True once the user has entered the correct PIN this session.
   * Starts as `false` on every cold launch so the lock screen shows.
   */
  isUnlocked: boolean;
  /** Wall-clock time of last successful unlock (or app launch when no PIN). */
  lastUnlockAt: number | null;
  /** Wall-clock time when app last became inactive. */
  lastBackgroundedAt: number | null;
  /** Mark the session as unlocked (called by PinLockScreen on success). */
  markUnlocked: () => void;
  /** Force-lock the session (called on resume-after-timeout, on logout, etc). */
  lock: () => void;
  /** Record that app went to background. */
  markBackgrounded: () => void;
  /** Record that app came back to foreground (clears the backgrounded timestamp). */
  markForegrounded: () => void;
}

export const usePinLockSession = create<PinLockSessionState>((set) => ({
  isUnlocked: false,
  lastUnlockAt: null,
  lastBackgroundedAt: null,
  markUnlocked: () =>
    set({ isUnlocked: true, lastUnlockAt: Date.now(), lastBackgroundedAt: null }),
  lock: () => set({ isUnlocked: false, lastBackgroundedAt: null }),
  markBackgrounded: () => set({ lastBackgroundedAt: Date.now() }),
  markForegrounded: () => set({ lastBackgroundedAt: null }),
}));

// ---------------- Helpers ----------------

/**
 * Check if the gate should currently block the app.
 * Returns true when: PIN is enabled AND session is not unlocked.
 */
export function shouldShowLockScreen(): boolean {
  const { pinEnabled } = usePinLockSettings.getState();
  const { isUnlocked } = usePinLockSession.getState();
  return pinEnabled && !isUnlocked;
}

/**
 * Decide whether a resume-from-background event should re-lock.
 * Returns true when the configured timeout has elapsed.
 */
export function shouldRelockOnResume(): boolean {
  const { pinEnabled, timeout } = usePinLockSettings.getState();
  if (!pinEnabled) return false;
  const minutes = TIMEOUT_MINUTES[timeout];
  if (minutes === null) return false; // "never"
  if (minutes === 0) return true; // "immediate" — lock on every foreground
  const { lastBackgroundedAt } = usePinLockSession.getState();
  if (!lastBackgroundedAt) return false;
  const elapsed = Date.now() - lastBackgroundedAt;
  return elapsed >= minutes * 60_000;
}

/**
 * Pull the latest PIN-enabled state from the native keychain. Call at
 * app boot and after any setPin/clearPin to keep the settings store
 * in sync with native truth.
 */
export async function refreshPinStatus(): Promise<void> {
  try {
    const enabled = await nativePinLock.hasPin();
    usePinLockSettings.getState().setPinEnabled(enabled);
    // If a PIN is set, default the session to locked. Conversely, if no
    // PIN is set, mark unlocked so the gate never appears.
    if (!enabled) {
      usePinLockSession.getState().markUnlocked();
    }
  } catch (e) {
    // On web/Android the plugin throws — that's expected and we just
    // disable the feature in the UI.
    console.debug('[pinLock] refreshPinStatus failed (likely non-iOS):', e);
    usePinLockSettings.getState().setPinEnabled(false);
    usePinLockSession.getState().markUnlocked();
  }
}

/**
 * Hook: wires page visibility events to the session store.
 * When the WebView hides (app backgrounded, screen lock, app switch) →
 * record backgrounded time. When it shows again → if past timeout,
 * force re-lock.
 *
 * `document.visibilitychange` is fired by WKWebView when the iOS app
 * backgrounds — same firing condition as `@capacitor/app`'s
 * `appStateChange` but with no extra plugin dependency.
 *
 * Call once from the top-level lock gate component (mount-only effect).
 */
export function useAppLockLifecycle() {
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const handler = () => {
      if (document.visibilityState === 'visible') {
        if (shouldRelockOnResume()) {
          usePinLockSession.getState().lock();
        }
        usePinLockSession.getState().markForegrounded();
      } else {
        usePinLockSession.getState().markBackgrounded();
      }
    };
    document.addEventListener('visibilitychange', handler);
    // Also listen to page-hide / page-show as a backup — Safari sometimes
    // fires those without visibilitychange when restoring from BFCache.
    window.addEventListener('pagehide', handler);
    window.addEventListener('pageshow', handler);
    return () => {
      document.removeEventListener('visibilitychange', handler);
      window.removeEventListener('pagehide', handler);
      window.removeEventListener('pageshow', handler);
    };
  }, []);
}
