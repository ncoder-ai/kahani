'use client';

/**
 * SecuritySettingsTab — App Lock (PIN) configuration.
 *
 * Three states the tab can be in, derived from native truth:
 *   1. Platform is not iOS Capacitor: render a tiny info card explaining
 *      the feature is iOS-only and the section is otherwise inert.
 *   2. iOS, PIN not set: render an "Enable App Lock" CTA. Tapping opens
 *      the PinSetupScreen overlay; on success the toggle flips on.
 *   3. iOS, PIN set: render the timeout dropdown + "Change PIN" and
 *      "Disable App Lock" buttons. Both destructive actions require a
 *      successful PIN verification first.
 *
 * The Lock-now button is intentionally always available when a PIN is
 * set — useful when handing the phone to someone or for quick testing.
 */

import { useEffect, useState } from 'react';
import { Lock, Unlock, KeyRound, ShieldOff, ShieldCheck } from 'lucide-react';
import { isNative, isIOS } from '@/lib/capacitor';
import nativePinLock from '@/utils/nativePinLock';
import {
  usePinLockSettings,
  usePinLockSession,
  refreshPinStatus,
  type LockTimeoutOption,
} from '@/store/pinLock';
import PinSetupScreen from '@/components/security/PinSetupScreen';
import PinLockScreen from '@/components/security/PinLockScreen';
import { SettingsTabProps } from '../types';

type Overlay =
  | { kind: 'none' }
  | { kind: 'setup' }
  | { kind: 'verify-then-clear' }
  | { kind: 'verify-then-change' };

export default function SecuritySettingsTab({ showMessage }: SettingsTabProps) {
  const pinEnabled = usePinLockSettings((s) => s.pinEnabled);
  const timeout = usePinLockSettings((s) => s.timeout);
  const setTimeoutPref = usePinLockSettings((s) => s.setTimeout);
  const lockNow = usePinLockSession((s) => s.lock);

  const [supported, setSupported] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>({ kind: 'none' });

  useEffect(() => {
    const ok = isNative() && isIOS();
    setSupported(ok);
    if (ok) {
      // Make sure the persisted "pinEnabled" hint matches native truth
      // before rendering the toggle state.
      refreshPinStatus();
    }
  }, []);

  const handleSetupComplete = async () => {
    await refreshPinStatus();
    setOverlay({ kind: 'none' });
    showMessage('App Lock enabled', 'success');
  };

  const handleVerifyAndClear = async () => {
    try {
      await nativePinLock.clearPin();
      await refreshPinStatus();
      showMessage('App Lock disabled', 'success');
    } catch (e) {
      console.error('[SecuritySettings] clearPin failed:', e);
      showMessage('Failed to disable App Lock', 'error');
    } finally {
      setOverlay({ kind: 'none' });
    }
  };

  const handleVerifyAndStartChange = () => {
    setOverlay({ kind: 'setup' });
  };

  if (!supported) {
    return (
      <div className="space-y-4">
        <div className="bg-white/5 border border-white/10 rounded-lg p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <Lock className="w-5 h-5 text-white/60 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-base font-semibold text-white">App Lock</h3>
              <p className="mt-1 text-sm text-white/60">
                Require a 6-digit PIN to open Saga. Currently available
                only in the Saga iOS app — your web browser uses the
                normal login flow.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Status card */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-4 sm:p-6">
        <div className="flex items-start gap-3">
          {pinEnabled ? (
            <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
          ) : (
            <ShieldOff className="w-5 h-5 text-white/60 flex-shrink-0 mt-0.5" />
          )}
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-white">
              App Lock {pinEnabled ? 'is on' : 'is off'}
            </h3>
            <p className="mt-1 text-sm text-white/60">
              {pinEnabled
                ? 'A 6-digit PIN is required to open Saga after the app is closed or backgrounded for longer than the lock timeout.'
                : 'Add a 6-digit PIN to require an extra unlock when opening the app. Separate from your account password.'}
            </p>
          </div>
        </div>
      </div>

      {!pinEnabled && (
        <button
          type="button"
          onClick={() => setOverlay({ kind: 'setup' })}
          className="w-full py-3 px-4 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 rounded-lg text-emerald-200 font-medium flex items-center justify-center gap-2 transition-colors"
        >
          <Lock className="w-4 h-4" />
          Enable App Lock
        </button>
      )}

      {pinEnabled && (
        <>
          {/* Timeout dropdown */}
          <div className="bg-white/5 border border-white/10 rounded-lg p-4">
            <label className="block text-sm font-medium text-white mb-2">
              Re-lock after
            </label>
            <select
              value={timeout}
              onChange={(e) => setTimeoutPref(e.target.value as LockTimeoutOption)}
              className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white"
            >
              <option value="immediate">Immediately when backgrounded</option>
              <option value="1">1 minute</option>
              <option value="5">5 minutes</option>
              <option value="15">15 minutes</option>
              <option value="never">Never re-lock once unlocked</option>
            </select>
            <p className="mt-2 text-xs text-white/50">
              The PIN is always required on cold app launch. This setting
              controls only what happens when you switch away and come back.
            </p>
          </div>

          {/* Actions */}
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setOverlay({ kind: 'verify-then-change' })}
              className="w-full py-3 px-4 bg-white/10 hover:bg-white/15 border border-white/20 rounded-lg text-white font-medium flex items-center justify-center gap-2 transition-colors"
            >
              <KeyRound className="w-4 h-4" />
              Change PIN
            </button>
            <button
              type="button"
              onClick={lockNow}
              className="w-full py-3 px-4 bg-white/5 hover:bg-white/10 border border-white/15 rounded-lg text-white/80 font-medium flex items-center justify-center gap-2 transition-colors"
            >
              <Unlock className="w-4 h-4" />
              Lock Saga now
            </button>
            <button
              type="button"
              onClick={() => setOverlay({ kind: 'verify-then-clear' })}
              className="w-full py-3 px-4 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 font-medium flex items-center justify-center gap-2 transition-colors"
            >
              <ShieldOff className="w-4 h-4" />
              Disable App Lock
            </button>
          </div>
        </>
      )}

      {/* Overlays */}
      {overlay.kind === 'setup' && (
        <PinSetupScreen
          onComplete={handleSetupComplete}
          onCancel={() => setOverlay({ kind: 'none' })}
        />
      )}
      {overlay.kind === 'verify-then-clear' && (
        <PinLockScreen
          onUnlock={handleVerifyAndClear}
          onForgotPin={() => setOverlay({ kind: 'none' })}
        />
      )}
      {overlay.kind === 'verify-then-change' && (
        <PinLockScreen
          onUnlock={handleVerifyAndStartChange}
          onForgotPin={() => setOverlay({ kind: 'none' })}
        />
      )}
    </div>
  );
}
