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

// Format info for raw PCM streaming. Provider declares this in stream_start.
export interface PcmStreamFormat {
  sampleRate: number;       // e.g. 24000
  channels: number;         // 1 = mono
  bitsPerSample: number;    // 16
}

class AudioContextManager {
  private context: AudioContext | null = null;
  private isUnlocked: boolean = false;
  private nextStartTime: number = 0;
  private activeSources: Set<AudioBufferSourceNode> = new Set();
  private isPlaying: boolean = false;
  private onPlaybackEndCallback: PlaybackCallback | null = null;
  private pendingSourceCount: number = 0;
  // Default pre-buffer (seconds) used by beginPcmStream when no explicit
  // override is passed. Updated centrally via setDefaultBufferAheadSeconds()
  // when the user's TTS settings change. Both consumers of beginPcmStream
  // (GlobalTTSContext and useTTSWebSocket hook) read from this singleton
  // so we don't have to wire the value through every call site.
  private defaultBufferAheadSeconds: number = 1.0;

  setDefaultBufferAheadSeconds(seconds: number): void {
    if (Number.isFinite(seconds) && seconds >= 0) {
      this.defaultBufferAheadSeconds = Math.min(seconds, 30); // hard cap to avoid pathological values
    }
  }

  getDefaultBufferAheadSeconds(): number {
    return this.defaultBufferAheadSeconds;
  }
  // Active PCM streams keyed by stream_id. Each stream tracks its own
  // format and the set of scheduled sources so cancelPcmStream() can
  // stop just that stream without nuking other audio.
  private pcmStreams: Map<string, {
    format: PcmStreamFormat;
    sources: Set<AudioBufferSourceNode>;
    ended: boolean;
    // Pre-buffer (seconds) — first frame's start time is shifted by this
    // amount so subsequent frames pile up ahead of playback. Absorbs
    // generation jitter when upstream RTF is close to 1.0. Set on
    // beginPcmStream from the user's TTS settings; default 0 = play ASAP.
    bufferAheadSeconds: number;
    // Set true after the first frame is scheduled so we only apply the
    // buffer offset once (subsequent frames inherit the queue position).
    firstFrameScheduled: boolean;
  }> = new Map();
  
  constructor() {
    // Don't create AudioContext here - iOS requires it to be created during a user gesture
    // The context will be created lazily in unlock() or getOrCreateContext()
    console.log('[AudioContext] Manager initialized (context will be created on first user interaction)');
  }
  
  /**
   * Get or create the AudioContext
   * Should only be called during a user gesture on iOS
   */
  private getOrCreateContext(): AudioContext | null {
    if (this.context) {
      return this.context;
    }
    
    if (typeof window === 'undefined') {
      return null;
    }
    
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) {
      console.error('[AudioContext] Web Audio API not supported');
      return null;
    }
    
    this.context = new AudioContextClass();
    console.log('[AudioContext] Created with sample rate:', this.context.sampleRate);
    return this.context;
  }
  
  /**
   * Unlock the AudioContext - MUST be called from a user interaction (click/tap)
   * This is the "one-time unlock" that enables all subsequent audio
   * On iOS, this also creates the AudioContext if it doesn't exist
   * 
   * IMPORTANT: On iOS, we first play through HTMLAudioElement to switch
   * the audio session to "media playback" mode, which ignores the silent switch.
   */
  async unlock(): Promise<boolean> {
    console.log('[AudioContext] Unlock requested');
    
    // Step 1: Play through HTMLAudioElement to switch iOS audio session to media mode
    // This makes audio play even when the silent switch is on
    try {
      await this.unlockMediaSession();
    } catch (err) {
      console.warn('[AudioContext] Media session unlock failed (continuing):', err);
    }
    
    // Step 2: Create context during user gesture if it doesn't exist
    const context = this.getOrCreateContext();
    if (!context) {
      console.error('[AudioContext] Failed to create context');
      return false;
    }
    
    console.log('[AudioContext] Attempting to unlock, current state:', context.state);
    
    if (context.state === 'suspended') {
      try {
        // iOS bug: when the audio session is in `interrupted` state
        // (screen lock, backgrounding, phone call), `context.resume()`
        // can hang forever — never resolves, never rejects. Race it
        // against a 1.5s timeout so unlock can proceed even if iOS
        // is sitting on the resume promise.
        await Promise.race([
          context.resume(),
          new Promise<void>(resolve => setTimeout(() => {
            console.warn('[AudioContext] resume() timed out after 1.5s — proceeding anyway');
            resolve();
          }, 1500))
        ]);

        // Play a short actual tone to TRULY unlock on iOS
        // Silent buffers sometimes don't fully unlock the audio session
        const oscillator = context.createOscillator();
        const gainNode = context.createGain();
        
        oscillator.frequency.value = 1; // Very low frequency (inaudible)
        oscillator.type = 'sine';
        gainNode.gain.value = 0.001; // Nearly silent
        
        oscillator.connect(gainNode);
        gainNode.connect(context.destination);
        
        oscillator.start();
        oscillator.stop(context.currentTime + 0.1);
        
        this.isUnlocked = true;
        console.log('[AudioContext] ✓ Unlocked successfully, state:', context.state);
        return true;
      } catch (err) {
        console.error('[AudioContext] ❌ Failed to unlock:', err);
        return false;
      }
    }
    
    // Already running
    if (context.state === 'running') {
      this.isUnlocked = true;
      console.log('[AudioContext] Already running');
      return true;
    }
    
    return false;
  }
  
  /**
   * Play a brief audio through HTMLAudioElement to switch iOS audio session
   * from "ambient" (respects silent switch) to "playback" (ignores silent switch)
   * This is the trick that makes Web Audio work like Spotify/YouTube on iOS
   */
  private async unlockMediaSession(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        // Create a short silent MP3 data URL
        // This is a valid MP3 file that's essentially silent
        const silentMp3 = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7v////////////////////////////////////////////////////////////////////////////////////////////////AAAABUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7v////////////////////////////////////////////////////////////////////////////////////////////////AAAABUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV';
        
        const audio = new Audio(silentMp3);
        
        // These attributes help with iOS
        audio.setAttribute('playsinline', 'true');
        audio.setAttribute('webkit-playsinline', 'true');
        
        audio.volume = 0.01; // Very quiet but not silent (silent might not work)
        
        const cleanup = () => {
          audio.remove();
        };
        
        audio.onended = () => {
          console.log('[AudioContext] Media session unlocked via HTMLAudioElement');
          cleanup();
          resolve();
        };
        
        audio.onerror = (e) => {
          console.warn('[AudioContext] HTMLAudioElement error:', e);
          cleanup();
          reject(e);
        };
        
        // Set a timeout in case play() hangs
        const timeout = setTimeout(() => {
          console.log('[AudioContext] Media session unlock timed out (continuing)');
          cleanup();
          resolve();
        }, 500);
        
        audio.play().then(() => {
          console.log('[AudioContext] HTMLAudioElement playing');
        }).catch((err) => {
          clearTimeout(timeout);
          console.warn('[AudioContext] HTMLAudioElement play failed:', err);
          cleanup();
          reject(err);
        });
        
      } catch (err) {
        reject(err);
      }
    });
  }
  
  /**
   * Ensure context is ready for playback (resume if suspended)
   * Call this before any playback operation
   * Note: This will NOT create the context - use unlock() first
   */
  async ensureReady(): Promise<boolean> {
    if (!this.context) {
      console.error('[AudioContext] No context available - call unlock() first during a user gesture');
      return false;
    }
    
    if (this.context.state === 'suspended') {
      console.log('[AudioContext] Context suspended, attempting to resume...');
      try {
        await this.context.resume();
        console.log('[AudioContext] Resumed successfully, state:', this.context.state);
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
      throw new Error('[AudioContext] No context available - call unlock() first');
    }
    
    console.log(`[AudioContext] queueBuffer called, data size: ${audioData.byteLength} bytes, context state: ${this.context.state}`);
    
    // Ensure context is ready
    if (!(await this.ensureReady())) {
      throw new Error('[AudioContext] Context not ready - user gesture required');
    }
    
    // Decode the audio data (use slice to avoid detached buffer issues)
    let audioBuffer: AudioBuffer;
    try {
      audioBuffer = await this.context.decodeAudioData(audioData.slice(0));
      console.log(`[AudioContext] Decoded audio: duration=${audioBuffer.duration.toFixed(2)}s, channels=${audioBuffer.numberOfChannels}, sampleRate=${audioBuffer.sampleRate}`);
    } catch (decodeError) {
      console.error('[AudioContext] Failed to decode audio data:', decodeError);
      throw new Error(`Failed to decode audio: ${decodeError}`);
    }
    
    // Check if buffer has actual content
    if (audioBuffer.duration === 0) {
      console.warn('[AudioContext] Warning: decoded audio has 0 duration');
    }
    
    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);
    
    // Calculate start time for gapless playback
    const currentTime = this.context.currentTime;
    const startTime = Math.max(currentTime + 0.05, this.nextStartTime); // Small buffer to prevent overlap issues
    
    // Update next start time
    this.nextStartTime = startTime + audioBuffer.duration;
    
    // Track this source
    this.activeSources.add(source);
    this.pendingSourceCount++;
    this.isPlaying = true;
    
    // Clean up when done
    source.onended = () => {
      console.log('[AudioContext] Source ended');
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
    console.log(`[AudioContext] ▶ Scheduled: now=${currentTime.toFixed(2)}s, start=${startTime.toFixed(2)}s, duration=${audioBuffer.duration.toFixed(2)}s`);
    
    return { duration: audioBuffer.duration, startTime };
  }
  
  // ────────────────────────────────────────────────────────────────────
  // PCM streaming API (used by `frame` WebSocket messages)
  //
  // Three calls per stream:
  //   beginPcmStream(id, fmt)   — register the format, no audio yet
  //   queuePcmFrame(id, bytes)  — schedule one PCM frame, gapless
  //   endPcmStream(id)          — mark stream complete; onPlaybackEnd
  //                               fires once final source's onended runs
  //
  // PCM is raw signed 16-bit little-endian (the only format we currently
  // support; widely the lowest-common-denominator across providers and
  // browsers). Float32 conversion + scheduling reuses the same gapless
  // cursor (`nextStartTime`) as queueBuffer, so PCM streams interleave
  // cleanly with `chunk_ready`-style providers.
  //
  // Every queue call funnels through ensureReady() — iOS can re-suspend
  // the AudioContext at any moment, and we must defend against that
  // before EVERY frame batch.
  // ────────────────────────────────────────────────────────────────────

  beginPcmStream(
    streamId: string,
    format: PcmStreamFormat,
    bufferAheadSeconds?: number,
  ): void {
    if (this.pcmStreams.has(streamId)) {
      console.warn('[AudioContext] beginPcmStream: stream already exists, overwriting:', streamId);
    }
    // If no explicit value, use the per-user default set via
    // setDefaultBufferAheadSeconds(). Clamp to non-negative.
    const requested = bufferAheadSeconds ?? this.defaultBufferAheadSeconds;
    const clampedBuffer = Math.max(0, requested);
    this.pcmStreams.set(streamId, {
      format,
      sources: new Set(),
      ended: false,
      bufferAheadSeconds: clampedBuffer,
      firstFrameScheduled: false,
    });
    console.log(
      `[AudioContext] PCM stream begin id=${streamId} fmt=${format.sampleRate}Hz ${format.channels}ch ` +
      `${format.bitsPerSample}bit bufferAhead=${clampedBuffer.toFixed(2)}s`
    );
  }

  async queuePcmFrame(streamId: string, pcmBytes: ArrayBuffer): Promise<{ duration: number; startTime: number }> {
    const stream = this.pcmStreams.get(streamId);
    if (!stream) {
      throw new Error(`[AudioContext] queuePcmFrame: unknown stream ${streamId}`);
    }
    if (!this.context) {
      throw new Error('[AudioContext] No context available - call unlock() first');
    }
    // iOS may have suspended the context between frames — re-resume.
    if (!(await this.ensureReady())) {
      throw new Error('[AudioContext] Context not ready - user gesture required');
    }

    const { format } = stream;
    if (format.bitsPerSample !== 16) {
      throw new Error(`[AudioContext] PCM bit depth ${format.bitsPerSample} not supported (only 16)`);
    }

    // s16le → Float32 [-1.0, 1.0). Interleaved samples for multi-channel.
    const int16 = new Int16Array(pcmBytes);
    const totalSamples = int16.length;
    const samplesPerChannel = Math.floor(totalSamples / format.channels);
    if (samplesPerChannel === 0) {
      return { duration: 0, startTime: this.nextStartTime };
    }

    // Create an AudioBuffer at the SOURCE sample rate. The browser
    // handles up/down-sampling at playback time — important on iOS
    // Safari, where context.sampleRate is usually 44100 or 48000.
    const audioBuffer = this.context.createBuffer(
      format.channels,
      samplesPerChannel,
      format.sampleRate,
    );
    for (let ch = 0; ch < format.channels; ch++) {
      const channelData = audioBuffer.getChannelData(ch);
      for (let i = 0; i < samplesPerChannel; i++) {
        const sample = int16[i * format.channels + ch];
        // Divide by 32768 (NOT 32767) so the sign maps symmetrically.
        channelData[i] = sample / 32768;
      }
    }

    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);

    const currentTime = this.context.currentTime;
    // Same gapless scheduling logic as queueBuffer — except the +0.05
    // safety pad only applies on the very first frame of any stream
    // sequence (when nextStartTime is in the past). Subsequent frames
    // pick up exactly where the previous one ended.
    //
    // Pre-buffer: on the FIRST frame of this PCM stream, push the start
    // time forward by stream.bufferAheadSeconds. Subsequent frames pile
    // up against `nextStartTime` and inherit the offset naturally — we
    // end up with bufferAheadSeconds of audio queued ahead of playback,
    // which absorbs upstream generation jitter when RTF is close to 1.0.
    let startTime = Math.max(currentTime + 0.02, this.nextStartTime);
    if (!stream.firstFrameScheduled && stream.bufferAheadSeconds > 0) {
      startTime += stream.bufferAheadSeconds;
      console.log(
        `[AudioContext] First frame of ${streamId} delayed by ` +
        `${stream.bufferAheadSeconds.toFixed(2)}s pre-buffer (start=${startTime.toFixed(2)}s)`
      );
    }
    stream.firstFrameScheduled = true;
    this.nextStartTime = startTime + audioBuffer.duration;

    this.activeSources.add(source);
    stream.sources.add(source);
    this.pendingSourceCount++;
    this.isPlaying = true;

    source.onended = () => {
      this.activeSources.delete(source);
      stream.sources.delete(source);
      this.pendingSourceCount--;
      if (this.activeSources.size === 0 && this.pendingSourceCount <= 0) {
        this.isPlaying = false;
        if (this.onPlaybackEndCallback) {
          this.onPlaybackEndCallback();
        }
      }
    };

    source.start(startTime);
    return { duration: audioBuffer.duration, startTime };
  }

  endPcmStream(streamId: string): void {
    const stream = this.pcmStreams.get(streamId);
    if (!stream) return;
    stream.ended = true;
    // We don't delete from the map until the last source ends — keeps
    // the format around for any in-flight frames that might still
    // arrive (shouldn't happen, but defensive). GC of the entry
    // happens in cancelPcmStream() or the next beginPcmStream() of
    // the same id.
    if (stream.sources.size === 0) {
      this.pcmStreams.delete(streamId);
    }
    console.log(`[AudioContext] PCM stream end id=${streamId}`);
  }

  cancelPcmStream(streamId: string): void {
    const stream = this.pcmStreams.get(streamId);
    if (!stream) return;
    stream.sources.forEach((source) => {
      try { source.stop(); } catch { /* already stopped */ }
      this.activeSources.delete(source);
    });
    stream.sources.clear();
    this.pcmStreams.delete(streamId);
    console.log(`[AudioContext] PCM stream cancel id=${streamId}`);
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
    console.log('[AudioContext] Stopping all audio, active sources:', this.activeSources.size, 'pending:', this.pendingSourceCount);
    
    // Stop all active sources
    this.activeSources.forEach(source => {
      try {
        source.stop();
      } catch (e) {
        // Source may have already stopped
      }
    });
    
    this.activeSources.clear();
    // Forget any in-flight PCM stream state — sources were already
    // stopped above via activeSources iteration.
    this.pcmStreams.clear();
    this.resetQueue();
    this.isPlaying = false;
    // Clear callback to prevent stale callbacks from triggering
    this.onPlaybackEndCallback = null;
    console.log('[AudioContext] All audio stopped and queue cleared');
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

