/**
 * AudioContext Manager
 * 
 * Manages a singleton AudioContext for the entire application.
 * This is the proper way to handle audio on mobile browsers, especially iOS.
 * 
 * Key Concept:
 * - AudioContext starts in "suspended" state on mobile
 * - User must click a button to "unlock" it (call resume())
 * - Once unlocked, ALL audio through this context works programmatically
 * - No need for user interaction on subsequent audio plays
 * 
 * For TTS:
 * - Use queueBuffer() to schedule audio chunks for gapless playback
 * - Use resetQueue() when stopping/restarting playback
 * - Use stopAll() to stop all scheduled audio
 */

// Callback types for playback events
type PlaybackCallback = () => void;

class AudioContextManager {
  private context: AudioContext | null = null;
  private isUnlocked: boolean = false;
  private nextStartTime: number = 0;
  private activeSources: Set<AudioBufferSourceNode> = new Set();
  private isPlaying: boolean = false;
  private onPlaybackEndCallback: PlaybackCallback | null = null;
  private pendingSourceCount: number = 0;
  
  constructor() {
    if (typeof window !== 'undefined') {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioContextClass) {
        this.context = new AudioContextClass();
        console.log('[AudioContext] Created with sample rate:', this.context.sampleRate);
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
    
    console.log('[AudioContext] Attempting to unlock, current state:', this.context.state);
    
    if (this.context.state === 'suspended') {
      try {
        await this.context.resume();
        
        // Play a silent buffer to confirm the context is truly active
        // This is a recommended practice to handle edge cases on iOS
        const buffer = this.context.createBuffer(1, 1, this.context.sampleRate);
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);
        source.start();
        
        this.isUnlocked = true;
        console.log('[AudioContext] ✓ Unlocked successfully');
        return true;
      } catch (err) {
        console.error('[AudioContext] ❌ Failed to unlock:', err);
        return false;
      }
    }
    
    // Already running
    if (this.context.state === 'running') {
      this.isUnlocked = true;
      console.log('[AudioContext] Already running');
      return true;
    }
    
    return false;
  }
  
  /**
   * Ensure context is ready for playback (resume if suspended)
   * Call this before any playback operation
   */
  async ensureReady(): Promise<boolean> {
    if (!this.context) {
      console.error('[AudioContext] No context available');
      return false;
    }
    
    if (this.context.state === 'suspended') {
      console.log('[AudioContext] Context suspended, attempting to resume...');
      try {
        await this.context.resume();
        console.log('[AudioContext] Resumed successfully');
        return true;
      } catch (err) {
        console.error('[AudioContext] Failed to resume:', err);
        return false;
      }
    }
    
    return this.context.state === 'running';
  }
  
  /**
   * Get the AudioContext instance
   */
  getContext(): AudioContext | null {
    return this.context;
  }
  
  /**
   * Check if audio is unlocked and ready to play
   * Always checks actual AudioContext state (not cached flag) since iOS can suspend context at any time
   */
  isAudioUnlocked(): boolean {
    // Always check actual state - don't rely on cached flag
    // iOS can suspend AudioContext even after it's been unlocked
    return this.context?.state === 'running';
  }
  
  /**
   * Get current state for debugging
   */
  getState(): string {
    return this.context?.state || 'no-context';
  }
  
  /**
   * Check if currently playing audio
   */
  getIsPlaying(): boolean {
    return this.isPlaying;
  }
  
  /**
   * Convert base64 string to ArrayBuffer
   * Handles both raw base64 and data URL formats
   */
  base64ToArrayBuffer(base64: string): ArrayBuffer {
    // Remove data URL prefix if present
    const base64Data = base64.includes(',') ? base64.split(',')[1] : base64;
    
    const binaryString = window.atob(base64Data);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  }
  
  /**
   * Decode and play audio buffer immediately
   * Returns a promise that resolves when playback ends
   */
  async playBuffer(audioData: ArrayBuffer): Promise<void> {
    if (!this.context) {
      throw new Error('[AudioContext] No context available');
    }
    
    // Ensure context is ready
    if (!(await this.ensureReady())) {
      throw new Error('[AudioContext] Context not ready - user gesture required');
    }
    
    // Decode the audio data (use slice to avoid detached buffer issues)
    const audioBuffer = await this.context.decodeAudioData(audioData.slice(0));
    
    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);
    
    // Track this source
    this.activeSources.add(source);
    this.isPlaying = true;
    
    return new Promise((resolve) => {
      source.onended = () => {
        this.activeSources.delete(source);
        if (this.activeSources.size === 0) {
          this.isPlaying = false;
        }
        resolve();
      };
      source.start(0);
    });
  }
  
  /**
   * Queue audio buffer for gapless playback
   * Schedules the buffer to play immediately after any previously queued audio
   * Returns duration for progress tracking
   */
  async queueBuffer(audioData: ArrayBuffer): Promise<{ duration: number; startTime: number }> {
    if (!this.context) {
      throw new Error('[AudioContext] No context available');
    }
    
    // Ensure context is ready
    if (!(await this.ensureReady())) {
      throw new Error('[AudioContext] Context not ready - user gesture required');
    }
    
    // Decode the audio data (use slice to avoid detached buffer issues)
    const audioBuffer = await this.context.decodeAudioData(audioData.slice(0));
    
    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);
    
    // Calculate start time for gapless playback
    const currentTime = this.context.currentTime;
    const startTime = Math.max(currentTime + 0.01, this.nextStartTime); // Small buffer to prevent overlap issues
    
    // Update next start time
    this.nextStartTime = startTime + audioBuffer.duration;
    
    // Track this source
    this.activeSources.add(source);
    this.pendingSourceCount++;
    this.isPlaying = true;
    
    // Clean up when done
    source.onended = () => {
      this.activeSources.delete(source);
      this.pendingSourceCount--;
      
      // Check if all audio is done
      if (this.activeSources.size === 0 && this.pendingSourceCount <= 0) {
        this.isPlaying = false;
        console.log('[AudioContext] All queued audio finished');
        if (this.onPlaybackEndCallback) {
          this.onPlaybackEndCallback();
        }
      }
    };
    
    // Schedule playback
    source.start(startTime);
    console.log(`[AudioContext] Queued buffer: duration=${audioBuffer.duration.toFixed(2)}s, startTime=${startTime.toFixed(2)}s`);
    
    return { duration: audioBuffer.duration, startTime };
  }
  
  /**
   * Set callback for when all queued playback ends
   */
  setOnPlaybackEnd(callback: PlaybackCallback | null): void {
    this.onPlaybackEndCallback = callback;
  }
  
  /**
   * Reset queue timing (call when stopping/restarting playback)
   */
  resetQueue(): void {
    this.nextStartTime = 0;
    this.pendingSourceCount = 0;
    console.log('[AudioContext] Queue reset');
  }
  
  /**
   * Stop all currently playing and scheduled audio
   */
  stopAll(): void {
    console.log('[AudioContext] Stopping all audio, active sources:', this.activeSources.size);
    
    // Stop all active sources
    this.activeSources.forEach(source => {
      try {
        source.stop();
      } catch (e) {
        // Source may have already stopped
      }
    });
    
    this.activeSources.clear();
    this.resetQueue();
    this.isPlaying = false;
  }
  
  /**
   * Get the current playback time position
   * Useful for progress tracking
   */
  getCurrentTime(): number {
    return this.context?.currentTime || 0;
  }
  
  /**
   * Get the scheduled end time of all queued audio
   */
  getScheduledEndTime(): number {
    return this.nextStartTime;
  }
  
  /**
   * Test audio playback with a simple beep
   * Use this to verify audio is actually working
   */
  async testAudio(): Promise<void> {
    if (!this.context) {
      console.error('[AudioContext] No context available');
      return;
    }
    
    // Try to ensure ready first
    if (!(await this.ensureReady())) {
      console.error('[AudioContext] Not unlocked, cannot test. Please tap the unlock button first.');
      return;
    }
    
    console.log('[AudioContext] Playing test tone...');
    
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
    
    console.log('[AudioContext] Test tone playing');
  }
}

// Export singleton instance
export const audioContextManager = new AudioContextManager();

