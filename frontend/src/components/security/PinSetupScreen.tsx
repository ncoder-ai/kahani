'use client';

/**
 * PinSetupScreen — two-step PIN creation flow. Used both when first
 * enabling App Lock from Settings and when the user chooses "Change PIN."
 *
 * Step 1: enter the new PIN.
 * Step 2: re-enter to confirm. If it matches, we call nativePinLock.setPin
 *         and tell the parent. If it doesn't, we restart from step 1 with
 *         an error indicator.
 *
 * No keyboard input persists across step transitions — once the user
 * commits step 1, the dots reset and they enter the confirmation fresh.
 */

import { useCallback, useState } from 'react';
import nativePinLock from '@/utils/nativePinLock';
import PinPadInput from './PinPadInput';

interface PinSetupScreenProps {
  /** Called after the PIN is successfully stored. */
  onComplete: () => void;
  /** Called if the user cancels mid-setup (Settings should re-show toggle). */
  onCancel: () => void;
}

export default function PinSetupScreen({ onComplete, onCancel }: PinSetupScreenProps) {
  const [stage, setStage] = useState<'enter' | 'confirm'>('enter');
  const [firstPin, setFirstPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetToken, setResetToken] = useState(0);

  const handleEnter = useCallback((pin: string) => {
    setFirstPin(pin);
    setError(null);
    setStage('confirm');
    setResetToken((n) => n + 1);
  }, []);

  const handleConfirm = useCallback(
    async (pin: string) => {
      if (pin !== firstPin) {
        setStage('enter');
        setFirstPin('');
        setError("PINs didn't match. Try again.");
        setResetToken((n) => n + 1);
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await nativePinLock.setPin(pin);
        onComplete();
      } catch (e) {
        console.error('[PinSetupScreen] setPin failed:', e);
        setError('Could not save PIN. Please try again.');
        setStage('enter');
        setFirstPin('');
        setResetToken((n) => n + 1);
      } finally {
        setBusy(false);
      }
    },
    [firstPin, onComplete],
  );

  return (
    <div className="fixed inset-0 z-[10000] theme-bg-primary flex flex-col items-center justify-center px-6 py-12">
      <div className="mb-8 text-center">
        <h1 className="text-xl font-semibold text-white">
          {stage === 'enter' ? 'Set a 6-digit PIN' : 'Confirm your PIN'}
        </h1>
        <p className="mt-2 text-sm text-white/60 max-w-xs mx-auto">
          {stage === 'enter'
            ? 'This PIN will be required to open Saga after you close or background the app.'
            : 'Enter the same PIN one more time to confirm.'}
        </p>
      </div>

      <PinPadInput
        onComplete={stage === 'enter' ? handleEnter : handleConfirm}
        error={error}
        disabled={busy}
        resetToken={resetToken}
      />

      <button
        type="button"
        onClick={onCancel}
        disabled={busy}
        className="mt-8 text-sm text-white/60 hover:text-white/90 disabled:opacity-50"
      >
        Cancel
      </button>
    </div>
  );
}
