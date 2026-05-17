/**
 * Native TTS plugin — iOS-only wrapper around the AVAudioEngine-backed
 * Capacitor plugin (NativeTTSPlugin.swift / .m). Provides a typed JS
 * surface that mirrors the Web Audio PCM streaming API used by
 * audioContextManager, so the routing code in GlobalTTSContext can swap
 * paths cleanly.
 *
 * Use isAvailable() to gate: returns true only inside the Capacitor iOS
 * shell. Web browsers (mobile or desktop) and Android Capacitor get false.
 */

import { registerPlugin, type PluginListenerHandle } from '@capacitor/core';
import { isIOS, isNative } from '@/lib/capacitor';

interface PrepareOptions {
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
}

interface FeedFrameOptions {
  pcmBase64: string;
}

interface MetadataOptions {
  title?: string;
  artist?: string;
  album?: string;
  artworkUrl?: string;
}

interface RemoteCommandEvent {
  action: 'play' | 'pause' | 'stop' | 'togglePlayPause';
}

interface InterruptionEvent {
  state: 'began' | 'ended';
  shouldResume?: boolean;
}

interface RouteChangeEvent {
  reason:
    | 'oldDeviceUnavailable'
    | 'newDeviceAvailable'
    | 'categoryChange'
    | 'override'
    | 'wakeFromSleep'
    | 'noSuitableRoute'
    | 'configChange'
    | 'unknown';
}

interface NativeTTSPluginShape {
  prepare(opts: PrepareOptions): Promise<void>;
  feedFrame(opts: FeedFrameOptions): Promise<void>;
  markStreamEnd(): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  stop(): Promise<void>;
  setMetadata(opts: MetadataOptions): Promise<void>;
  addListener(
    eventName: 'remoteCommand',
    listenerFunc: (event: RemoteCommandEvent) => void,
  ): Promise<PluginListenerHandle>;
  addListener(
    eventName: 'interruption',
    listenerFunc: (event: InterruptionEvent) => void,
  ): Promise<PluginListenerHandle>;
  addListener(
    eventName: 'routeChange',
    listenerFunc: (event: RouteChangeEvent) => void,
  ): Promise<PluginListenerHandle>;
  addListener(
    eventName: 'playbackEnded',
    listenerFunc: () => void,
  ): Promise<PluginListenerHandle>;
}

const NativeTTS = registerPlugin<NativeTTSPluginShape>('NativeTTS');

/**
 * Higher-level adapter that matches the Web Audio PCM streaming API
 * shape (beginPcmStream / queuePcmFrame / endPcmStream) so GlobalTTSContext
 * can route to native vs Web Audio with one boolean gate.
 */
class NativeTTSPlayer {
  private currentStreamId: string | null = null;

  /** True only inside the Capacitor iOS app. False everywhere else. */
  isAvailable(): boolean {
    return isNative() && isIOS();
  }

  async beginStream(streamId: string, format: PrepareOptions): Promise<void> {
    this.currentStreamId = streamId;
    await NativeTTS.prepare(format);
  }

  async queueFrame(streamId: string, pcmBase64: string): Promise<void> {
    if (this.currentStreamId !== streamId) {
      // Late frame for a stream we already abandoned — drop silently.
      return;
    }
    await NativeTTS.feedFrame({ pcmBase64 });
  }

  /**
   * Marks the stream complete from the JS side. Tells native that no
   * more frames are coming, so it can fire "playbackEnded" once all
   * already-scheduled buffers finish draining. Does NOT stop playback.
   */
  async endStream(streamId: string): Promise<void> {
    if (this.currentStreamId !== streamId) return;
    try {
      await NativeTTS.markStreamEnd();
    } catch (e) {
      console.warn('[NativeTTS] markStreamEnd() failed:', e);
    }
  }

  /**
   * Pause playback without dropping queued buffers. Resume picks up at the
   * exact sample where pause landed. Newly-arrived frames keep accumulating.
   */
  async pause(): Promise<void> {
    try {
      await NativeTTS.pause();
    } catch (e) {
      console.warn('[NativeTTS] pause() failed:', e);
    }
  }

  /** Resume from a previous pause(). No-op if not paused. */
  async resume(): Promise<void> {
    try {
      await NativeTTS.resume();
    } catch (e) {
      console.warn('[NativeTTS] resume() failed:', e);
    }
  }

  /**
   * Hard stop: drops all scheduled buffers and tears down the engine.
   * Equivalent to audioContextManager.stopAll().
   */
  async stop(): Promise<void> {
    this.currentStreamId = null;
    try {
      await NativeTTS.stop();
    } catch (e) {
      console.warn('[NativeTTS] stop() failed:', e);
    }
  }

  async setMetadata(opts: MetadataOptions): Promise<void> {
    try {
      await NativeTTS.setMetadata(opts);
    } catch (e) {
      console.warn('[NativeTTS] setMetadata() failed:', e);
    }
  }

  /**
   * Subscribe to lock-screen / Bluetooth / CarPlay control taps.
   * Returns the listener handle so callers can remove it on unmount.
   */
  onRemoteCommand(handler: (action: RemoteCommandEvent['action']) => void): Promise<PluginListenerHandle> {
    return NativeTTS.addListener('remoteCommand', (event) => handler(event.action));
  }

  onInterruption(handler: (event: InterruptionEvent) => void): Promise<PluginListenerHandle> {
    return NativeTTS.addListener('interruption', handler);
  }

  onRouteChange(handler: (event: RouteChangeEvent) => void): Promise<PluginListenerHandle> {
    return NativeTTS.addListener('routeChange', handler);
  }

  /**
   * Fires once after endStream() has been signalled AND the native
   * engine has finished playing all already-scheduled buffers. Use this
   * to flip the play/pause UI back without polling.
   */
  onPlaybackEnded(handler: () => void): Promise<PluginListenerHandle> {
    return NativeTTS.addListener('playbackEnded', handler);
  }
}

export const nativeTTSPlayer = new NativeTTSPlayer();
