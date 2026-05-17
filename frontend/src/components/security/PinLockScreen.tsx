'use client';

/**
 * PinLockScreen — full-screen PIN entry gate shown on cold app launch
 * and on resume from background after the lock timeout has elapsed.
 *
 * Renders only the PIN pad (no app chrome) so the user has no path
 * forward except entering the correct PIN or tapping "Forgot PIN".
 * On a wrong PIN, shakes the dots and decrements the displayed
 * attempts-remaining counter. After 5 wrong attempts the native
 * plugin returns `locked: true` and we trigger the forgot-PIN flow
 * automatically.
 */

import { useCallback, useEffect, useState } from 'react';
import nativePinLock from '@/utils/nativePinLock';
import PinPadInput from './PinPadInput';

interface PinLockScreenProps {
  /** Called when the entered PIN verifies successfully. */
  onUnlock: () => void;
  /**
   * Called when the user taps "Forgot PIN" OR exceeds the wrong-attempt
   * cap (5 strikes). The parent is expected to log out + clear the
   * stored PIN so the user can re-set it after re-auth.
   */
  onForgotPin: () => void;
}

export default function PinLockScreen({
  onUnlock,
  onForgotPin,
}: PinLockScreenProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetToken, setResetToken] = useState(0);
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);

  // On mount, read the current failure counter so a returning user who
  // already exhausted attempts on the previous session sees the lockout
  // state immediately instead of having to enter a wrong PIN first.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await nativePinLock.getFailedAttempts();
        if (cancelled) return;
        if (status.locked) {
          // User was already locked out from a prior session.
          onForgotPin();
          return;
        }
        if (status.count > 0) {
          setAttemptsRemaining(status.remaining);
        }
      } catch (e) {
        // Non-fatal — fall through to live entry.
        console.warn('[PinLockScreen] getFailedAttempts failed:', e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onForgotPin]);

  const handleComplete = useCallback(
    async (pin: string) => {
      setBusy(true);
      setError(null);
      try {
        const result = await nativePinLock.verifyPin(pin);
        if (result.valid) {
          onUnlock();
          return;
        }
        if (result.locked) {
          // Hit the cap with this attempt — force logout flow.
          onForgotPin();
          return;
        }
        setAttemptsRemaining(result.attemptsRemaining);
        setError(
          result.attemptsRemaining === 1
            ? 'Wrong PIN. 1 attempt remaining.'
            : `Wrong PIN. ${result.attemptsRemaining} attempts remaining.`,
        );
        setResetToken((n) => n + 1);
      } catch (e) {
        console.error('[PinLockScreen] verifyPin failed:', e);
        setError('Could not verify PIN. Please try again.');
        setResetToken((n) => n + 1);
      } finally {
        setBusy(false);
      }
    },
    [onUnlock, onForgotPin],
  );

  return (
    <div className="fixed inset-0 z-[10000] theme-bg-primary flex flex-col items-center justify-center px-6 py-12">
      <div className="mb-8 text-center">
        <img
          src="/kahani-logo.jpg"
          alt="Saga"
          className="h-24 w-24 object-contain mx-auto mb-4 rounded-2xl"
        />
        <h1 className="text-xl font-semibold text-white">Saga is locked</h1>
      </div>

      <PinPadInput
        onComplete={handleComplete}
        subtitle="Enter your 6-digit PIN to continue"
        error={error}
        disabled={busy}
        resetToken={resetToken}
      />

      <button
        type="button"
        onClick={onForgotPin}
        className="mt-8 text-sm text-white/60 hover:text-white/90 underline-offset-2 hover:underline"
      >
        Forgot PIN? Sign in again
      </button>

      {attemptsRemaining !== null && attemptsRemaining > 0 && !error && (
        <div className="mt-4 text-xs text-white/50">
          {attemptsRemaining} attempt{attemptsRemaining === 1 ? '' : 's'} remaining
        </div>
      )}
    </div>
  );
}
