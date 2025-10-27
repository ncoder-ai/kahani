/**
 * AudioContext Manager
 * 
 * Manages a singleton AudioContext for the entire application.
 * This is the proper way to handle audio on mobile browsers.
 * 
 * Key Concept:
 * - AudioContext starts in "suspended" state on mobile
 * - User must click a button to "unlock" it (call resume())
 * - Once unlocked, ALL audio through this context works programmatically
 * - No need for user interaction on subsequent audio plays
 */

class AudioContextManager {
  private context: AudioContext | null = null;
  private isUnlocked: boolean = false;
  
  constructor() {
    if (typeof window !== 'undefined') {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioContextClass) {
        this.context = new AudioContextClass();
        console.log('[AudioContext] Created, initial state:', this.context.state);
      } else {
        console.error('[AudioContext] Web Audio API not supported');
      }
    }
  }
  
  /**
   * Unlock the AudioContext - MUST be called from a user interaction (click/tap)
   * This is the "one-time unlock" that enables all subsequent audio
   */
  async unlock(): Promise<boolean> {
    if (!this.context) {
      console.error('[AudioContext] No context available');
      return false;
    }
    
    console.log('[AudioContext] Current state:', this.context.state);
    
    if (this.context.state === 'suspended') {
      try {
        await this.context.resume();
        console.log('[AudioContext] Resumed, new state:', this.context.state);
        
        // Play a silent buffer to confirm the context is truly active
        // This is a recommended practice to handle edge cases
        const buffer = this.context.createBuffer(1, 1, 22050);
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);
        source.start();
        
        this.isUnlocked = true;
        console.log('[AudioContext] ✅ Unlocked successfully!');
        console.log('[AudioContext] Sample rate:', this.context.sampleRate);
        console.log('[AudioContext] Base latency:', this.context.baseLatency);
        console.log('[AudioContext] Output latency:', (this.context as any).outputLatency);
        return true;
      } catch (err) {
        console.error('[AudioContext] ❌ Failed to unlock:', err);
        return false;
      }
    }
    
    // Already running
    if (this.context.state === 'running') {
      this.isUnlocked = true;
      console.log('[AudioContext] Already unlocked');
      return true;
    }
    
    return false;
  }
  
  /**
   * Get the AudioContext instance
   */
  getContext(): AudioContext | null {
    return this.context;
  }
  
  /**
   * Check if audio is unlocked and ready to play
   */
  isAudioUnlocked(): boolean {
    return this.isUnlocked && this.context?.state === 'running';
  }
  
  /**
   * Get current state for debugging
   */
  getState(): string {
    return this.context?.state || 'no-context';
  }
  
  /**
   * Test audio playback with a simple beep
   * Use this to verify audio is actually working
   */
  async testAudio(): Promise<void> {
    if (!this.context || !this.isAudioUnlocked()) {
      console.error('[AudioContext] Not unlocked, cannot test');
      return;
    }
    
    console.log('[AudioContext] Playing test beep...');
    
    // Create a 440Hz tone (A note) for 0.5 seconds
    const oscillator = this.context.createOscillator();
    const gainNode = this.context.createGain();
    
    oscillator.frequency.value = 440;
    oscillator.type = 'sine';
    
    gainNode.gain.value = 0.3; // 30% volume
    
    oscillator.connect(gainNode);
    gainNode.connect(this.context.destination);
    
    oscillator.start();
    oscillator.stop(this.context.currentTime + 0.5);
    
    console.log('[AudioContext] Test beep should be playing now');
  }
}

// Export singleton instance
export const audioContextManager = new AudioContextManager();

