'use client';

/**
 * PinLockGate — wraps app children with the PIN unlock screen when the
 * user has App Lock enabled AND the current session hasn't been unlocked
 * yet (or was re-locked by the background timeout).
 *
 * Place ABOVE the main app shell. Drilling it deeper into specific routes
 * is fine too — only routes wrapped by the gate enforce the lock. The
 * typical placement is inside RouteProtection, just before `{children}`.
 *
 * Forgot-PIN flow: clears the stored PIN in Keychain + logs the user
 * out so they have to re-authenticate against the backend. After login
 * the App Lock toggle defaults back to off (no PIN exists) and the user
 * can re-enable it in Settings.
 */

import { ReactNode, useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import nativePinLock from '@/utils/nativePinLock';
import {
  usePinLockSettings,
  usePinLockSession,
  refreshPinStatus,
  useAppLockLifecycle,
} from '@/store/pinLock';
import PinLockScreen from './PinLockScreen';

interface PinLockGateProps {
  children: ReactNode;
}

export default function PinLockGate({ children }: PinLockGateProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { logout } = useAuthStore();
  const pinEnabled = usePinLockSettings((s) => s.pinEnabled);
  const isUnlocked = usePinLockSession((s) => s.isUnlocked);
  const markUnlocked = usePinLockSession((s) => s.markUnlocked);

  // Track first-pass status sync. If the persisted store thinks a PIN is
  // enabled, we need to confirm against the keychain before rendering so
  // the children don't flash for one paint. If the persisted store says
  // no PIN, skip the wait — there's nothing to gate on.
  const [statusSynced, setStatusSynced] = useState(!pinEnabled);

  // Wire background/foreground re-lock for the lifetime of this gate.
  useAppLockLifecycle();

  // Sync the persisted "pinEnabled" hint with the native source of truth
  // on mount. After this resolves, statusSynced is true and we trust the
  // pinEnabled value to decide whether to gate.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshPinStatus();
      if (!cancelled) setStatusSynced(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleForgotPin = async () => {
    try {
      await nativePinLock.clearPin();
    } catch (e) {
      console.warn('[PinLockGate] clearPin failed during forgot flow:', e);
    }
    usePinLockSettings.getState().setPinEnabled(false);
    usePinLockSession.getState().lock();
    logout();
    router.push(`/login?redirect=${encodeURIComponent(pathname || '/')}`);
  };

  // First-render gating. If we know there's NO PIN configured, render the
  // app immediately. If there IS a PIN (per persisted hint), block until
  // we've confirmed via the native keychain to avoid a content flash.
  if (pinEnabled && !statusSynced) {
    return (
      <div className="fixed inset-0 z-[10000] theme-bg-primary flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (pinEnabled && !isUnlocked) {
    return (
      <PinLockScreen
        onUnlock={markUnlocked}
        onForgotPin={handleForgotPin}
      />
    );
  }

  return <>{children}</>;
}
