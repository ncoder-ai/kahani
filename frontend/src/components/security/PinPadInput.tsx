'use client';

/**
 * PinPadInput — reusable 6-digit numeric input with on-screen number pad.
 *
 * Renders a row of 6 indicator dots that fill as the user enters digits,
 * a 3×4 number pad (1-9, blank, 0, backspace), and auto-fires `onComplete`
 * once the 6th digit is entered. Touch-friendly large hit targets sized
 * for one-handed thumb reach on phone displays.
 *
 * No persistence and no validation — purely a controlled input layer.
 * Parent components decide what to do with the entered PIN.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const PIN_LENGTH = 6;

interface PinPadInputProps {
  /** Called with the full PIN once the user enters PIN_LENGTH digits. */
  onComplete: (pin: string) => void;
  /** Optional title above the dots (e.g. "Enter PIN" or "Confirm PIN"). */
  title?: string;
  /** Optional subtitle/help text. */
  subtitle?: string;
  /** When set, dots render in error tint and shake briefly. */
  error?: string | null;
  /** When true, all buttons are disabled (e.g. during async verify). */
  disabled?: boolean;
  /**
   * Reset signal — bumping this number wipes the in-progress entry without
   * remounting the component. Useful after a wrong-PIN attempt so the
   * dots clear while the error message stays visible.
   */
  resetToken?: number;
}

export default function PinPadInput({
  onComplete,
  title,
  subtitle,
  error,
  disabled = false,
  resetToken = 0,
}: PinPadInputProps) {
  const [pin, setPin] = useState('');

  // Track which pin value we've already fired onComplete for. Without
  // this guard, when the parent swaps the `onComplete` callback after
  // the first 6-digit entry (e.g. PinSetupScreen transitioning from
  // "enter" to "confirm"), the auto-fire effect re-runs with the new
  // callback ref and the OLD pin value still in state — causing step 2
  // to execute instantly with the first PIN and skip the confirm step.
  const firedForRef = useRef<string>('');

  // Clear the in-progress entry whenever resetToken changes. Don't
  // touch firedForRef here — the auto-fire effect resets it itself
  // when it observes pin === '' on its next run. Clearing it here
  // would race the queued setPin('') and re-arm a stale 6-digit fire.
  useEffect(() => {
    setPin('');
  }, [resetToken]);

  // Auto-fire when full. firedForRef guarantees we fire exactly once
  // per pin value even if the effect re-runs because the onComplete
  // prop reference changed. Re-arms automatically when pin returns to
  // empty (after backspace-to-zero or a resetToken bump).
  useEffect(() => {
    if (pin.length === 0) {
      firedForRef.current = '';
    } else if (pin.length === PIN_LENGTH && firedForRef.current !== pin) {
      firedForRef.current = pin;
      onComplete(pin);
    }
  }, [pin, onComplete]);

  const appendDigit = useCallback(
    (digit: string) => {
      if (disabled) return;
      setPin((prev) => (prev.length >= PIN_LENGTH ? prev : prev + digit));
    },
    [disabled],
  );

  const backspace = useCallback(() => {
    if (disabled) return;
    setPin((prev) => prev.slice(0, -1));
  }, [disabled]);

  // Hardware keyboard support — primarily for simulator / external keyboards.
  // Real device usage is always via the on-screen pad.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (disabled) return;
      if (e.key >= '0' && e.key <= '9') {
        appendDigit(e.key);
      } else if (e.key === 'Backspace') {
        backspace();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [disabled, appendDigit, backspace]);

  // Error visuals (red dots, shake, error message) only show until the
  // user starts typing again. As soon as the first digit lands the
  // context shifts to "entering a new PIN" — the dots return to their
  // normal fill rendering so the user can see their input progress, and
  // the lingering error message clears. Without this gate, all 6 dots
  // are uniformly red regardless of pin.length, which makes typing feel
  // unresponsive (no visual progress as digits land).
  const showError = !!error && pin.length === 0;

  return (
    <div className="w-full max-w-xs mx-auto flex flex-col items-center gap-8">
      {title && (
        <div className="text-center">
          <h2 className="text-2xl font-semibold text-white">{title}</h2>
          {subtitle && (
            <p className="mt-2 text-sm text-white/70">{subtitle}</p>
          )}
        </div>
      )}

      {/* 6 dot indicators */}
      <div
        className={`flex gap-4 ${showError ? 'animate-shake' : ''}`}
        aria-label={`${pin.length} of ${PIN_LENGTH} digits entered`}
      >
        {Array.from({ length: PIN_LENGTH }).map((_, i) => {
          const filled = i < pin.length;
          return (
            <div
              key={i}
              className={[
                'w-4 h-4 rounded-full border-2 transition-colors',
                showError
                  ? 'border-red-400 bg-red-400/20'
                  : filled
                    ? 'border-white bg-white'
                    : 'border-white/40 bg-transparent',
              ].join(' ')}
            />
          );
        })}
      </div>

      {showError && (
        <div className="text-sm text-red-300 text-center min-h-[1.25rem]">
          {error}
        </div>
      )}

      {/* Number pad */}
      <div className="grid grid-cols-3 gap-3 w-full">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
          <PadButton
            key={d}
            label={d}
            onClick={() => appendDigit(d)}
            disabled={disabled}
          />
        ))}
        {/* Spacer in the bottom-left to mimic iOS's 1-2-3, 4-5-6, 7-8-9, _-0-⌫ */}
        <div />
        <PadButton
          label="0"
          onClick={() => appendDigit('0')}
          disabled={disabled}
        />
        <PadButton
          label="⌫"
          onClick={backspace}
          disabled={disabled || pin.length === 0}
          aria="Delete last digit"
        />
      </div>
    </div>
  );
}

interface PadButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  aria?: string;
}

function PadButton({ label, onClick, disabled, aria }: PadButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={aria || label}
      className={[
        'aspect-square w-full rounded-full text-2xl font-light',
        'bg-white/10 active:bg-white/30 transition-colors',
        'text-white',
        'disabled:opacity-30 disabled:active:bg-white/10',
        'select-none touch-manipulation',
      ].join(' ')}
    >
      {label}
    </button>
  );
}
