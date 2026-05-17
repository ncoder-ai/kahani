/**
 * Native PIN lock plugin — iOS-only wrapper around the Keychain-backed
 * Capacitor plugin (NativePinLockPlugin.swift). Provides a typed JS
 * surface for the app's PIN entry / setup flow.
 *
 * The PIN is hashed (PBKDF2-HMAC-SHA256, 100k iterations) with a random
 * 16-byte salt on the native side before storage. The plaintext PIN
 * never touches disk — only the derived hash, in iOS Keychain Services.
 *
 * Use isAvailable() to gate: returns true only inside the Capacitor iOS
 * shell. Web browsers and Android shells get false; any UI that depends
 * on PIN lock must hide / disable itself when isAvailable() is false.
 */

import { registerPlugin } from '@capacitor/core';
import { isIOS, isNative } from '@/lib/capacitor';

interface SetPinOptions {
  pin: string;
}

interface VerifyPinOptions {
  pin: string;
}

interface VerifyPinResult {
  /** Whether the supplied PIN matched the stored hash. */
  valid: boolean;
  /**
   * Number of additional wrong-attempts the user has before lockout.
   * On a successful verify this is reset; on a wrong verify the
   * counter is incremented first, then the remaining count is returned.
   */
  attemptsRemaining: number;
  /**
   * True when this wrong attempt put the user at or past the cap (5).
   * The UI should redirect to the forgot-PIN / logout flow.
   */
  locked: boolean;
}

interface HasPinResult {
  enabled: boolean;
}

interface FailedAttemptsResult {
  count: number;
  remaining: number;
  locked: boolean;
}

interface NativePinLockPluginShape {
  setPin(opts: SetPinOptions): Promise<{ success: boolean }>;
  verifyPin(opts: VerifyPinOptions): Promise<VerifyPinResult>;
  hasPin(): Promise<HasPinResult>;
  clearPin(): Promise<{ success: boolean }>;
  getFailedAttempts(): Promise<FailedAttemptsResult>;
}

const NativePinLock = registerPlugin<NativePinLockPluginShape>('NativePinLock');

class NativePinLockClient {
  /** True only inside the Capacitor iOS app. False on web and Android. */
  isAvailable(): boolean {
    return isNative() && isIOS();
  }

  /**
   * Set or replace the stored PIN. The PIN is hashed natively before
   * storage; the plaintext does not persist anywhere.
   * Throws if the plugin is unavailable (web/android).
   */
  async setPin(pin: string): Promise<void> {
    if (!this.isAvailable()) {
      throw new Error('PIN lock is only available in the iOS app');
    }
    if (!pin || pin.length < 4) {
      throw new Error('PIN must be at least 4 characters');
    }
    await NativePinLock.setPin({ pin });
  }

  /**
   * Verify a candidate PIN against the stored hash.
   * On success, the failed-attempts counter is reset to 0.
   * On failure, the counter is incremented; if it reaches the cap (5),
   * `locked: true` is returned and the caller should trigger logout.
   */
  async verifyPin(pin: string): Promise<VerifyPinResult> {
    if (!this.isAvailable()) {
      throw new Error('PIN lock is only available in the iOS app');
    }
    return await NativePinLock.verifyPin({ pin });
  }

  /** Returns true if a PIN is currently stored. */
  async hasPin(): Promise<boolean> {
    if (!this.isAvailable()) {
      // On non-iOS surfaces the feature is intentionally absent — report
      // "no PIN" so the UI surfaces the empty/disabled state correctly.
      return false;
    }
    const { enabled } = await NativePinLock.hasPin();
    return enabled;
  }

  /** Delete the stored PIN and reset the failed-attempts counter. */
  async clearPin(): Promise<void> {
    if (!this.isAvailable()) {
      // No-op on non-iOS; nothing to clear.
      return;
    }
    await NativePinLock.clearPin();
  }

  /**
   * Read the current failed-attempts counter without trying a PIN.
   * Used by the lock screen on mount to render the lockout state if
   * the user already hit the cap on a prior session.
   */
  async getFailedAttempts(): Promise<FailedAttemptsResult> {
    if (!this.isAvailable()) {
      return { count: 0, remaining: 5, locked: false };
    }
    return await NativePinLock.getFailedAttempts();
  }
}

const nativePinLock = new NativePinLockClient();
export default nativePinLock;
export type { VerifyPinResult, FailedAttemptsResult };
