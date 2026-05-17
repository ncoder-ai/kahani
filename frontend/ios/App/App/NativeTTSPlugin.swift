//
//  NativeTTSPlugin.swift
//  Kahani — Native TTS playback for iOS
//
//  Plays raw Int16-LE PCM frames pushed from JS via AVAudioEngine.
//  Replaces the Web Audio path on iOS Capacitor so we get real native
//  audio session behavior: lock-screen Now Playing widget, AirPlay,
//  Bluetooth routing, audio interruption handling, and background
//  playback (the WKWebView's Web Audio context suspends when the app
//  backgrounds — native AVAudioEngine doesn't).
//
//  Threading
//  - All audio engine ops happen on the main thread (CAPPlugin methods
//    are dispatched there by Capacitor by default).
//  - scheduleBuffer is thread-safe, but we keep everything on main for
//    simplicity. Frame rate is ~10/s so contention isn't a concern.
//
//  Format
//  - JS sends Int16 little-endian interleaved PCM as base64.
//  - We connect playerNode to mixerNode at Float32 non-interleaved
//    matching the source sample rate; samples are converted at copy time
//    (Int16 / 32768.0).
//

import AVFoundation
import Capacitor
import Foundation
import MediaPlayer

@objc(NativeTTSPlugin)
public class NativeTTSPlugin: CAPPlugin, CAPBridgedPlugin {
    // Capacitor 7 plugin registration — no .m file / CAP_PLUGIN macro needed
    // (that's the legacy approach). The runtime auto-discovers plugins that
    // conform to CAPBridgedPlugin and declare these three properties.
    public let identifier = "NativeTTSPlugin"
    public let jsName = "NativeTTS"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "prepare", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "feedFrame", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "markStreamEnd", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "pause", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "resume", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "stop", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "setMetadata", returnType: CAPPluginReturnPromise),
    ]

    private let engine = AVAudioEngine()
    private let playerNode = AVAudioPlayerNode()
    private var currentFormat: AVAudioFormat?
    private var hasAttached = false
    private var hasSetupRemoteCommands = false
    // Drain tracking: per scheduled buffer we increment pendingBuffers,
    // decrement in the completion handler. When markStreamEnd() has been
    // called AND pendingBuffers hits 0, we emit "playbackEnded" so the
    // JS side can flip the play/pause icon back without polling.
    private var pendingBuffers: Int = 0
    private var streamEnded: Bool = false
    private let drainLock = NSLock()

    // MARK: - Lifecycle

    override public func load() {
        // NOTE: the audio session is intentionally NOT configured/activated
        // here. Activating at app launch and never releasing it is what kept
        // the Dynamic Island lit forever and let the route list go stale so
        // Bluetooth stopped appearing. The session is now activated in
        // prepare() (start of playback) and deactivated in
        // teardownEngineAndSession() (end of playback).
        setupRemoteCommands()

        let nc = NotificationCenter.default
        nc.addObserver(
            self,
            selector: #selector(handleInterruption(_:)),
            name: AVAudioSession.interruptionNotification,
            object: AVAudioSession.sharedInstance()
        )
        nc.addObserver(
            self,
            selector: #selector(handleRouteChange(_:)),
            name: AVAudioSession.routeChangeNotification,
            object: AVAudioSession.sharedInstance()
        )
    }

    // MARK: - Audio session

    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        do {
            // .playback ignores the silent switch and is what you want for
            // long-form spoken-audio playback (Audible, Podcasts).
            // .spokenAudio mode tells iOS this is voice content for ducking
            // and CarPlay categorization.
            try session.setCategory(
                .playback,
                mode: .spokenAudio,
                options: [.allowAirPlay, .allowBluetoothA2DP]
            )
            try session.setActive(true, options: [])
        } catch {
            CAPLog.print("[NativeTTS] Audio session setup failed:", error.localizedDescription)
        }
    }

    /// Tear down the engine and release the audio session after playback
    /// completes — natural end OR explicit stop. Deactivating the session
    /// (with .notifyOthersOnDeactivation) is what clears the Dynamic
    /// Island / Now Playing indicator and frees the audio route, so the
    /// freshly-activated session in the next prepare() re-resolves
    /// Bluetooth / AirPlay correctly instead of inheriting a stale route.
    private func teardownEngineAndSession() {
        playerNode.stop()
        if engine.isRunning {
            engine.stop()
        }
        drainLock.lock()
        pendingBuffers = 0
        streamEnded = false
        drainLock.unlock()
        clearNowPlaying()
        do {
            try AVAudioSession.sharedInstance().setActive(
                false, options: [.notifyOthersOnDeactivation]
            )
        } catch {
            CAPLog.print("[NativeTTS] Audio session deactivate failed:", error.localizedDescription)
        }
    }

    private func ensureEngineRunning() throws {
        if !hasAttached {
            engine.attach(playerNode)
            hasAttached = true
        }
        if !engine.isRunning {
            try engine.start()
        }
    }

    // MARK: - Capacitor methods

    @objc func prepare(_ call: CAPPluginCall) {
        guard let sampleRate = call.getDouble("sampleRate"),
              let channels = call.getInt("channels"),
              sampleRate > 0, channels > 0
        else {
            call.reject("sampleRate and channels are required positive numbers")
            return
        }

        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: AVAudioChannelCount(channels),
            interleaved: false
        ) else {
            call.reject("Failed to construct AVAudioFormat for sr=\(sampleRate) ch=\(channels)")
            return
        }

        do {
            // Activate the audio session at the START of every playback.
            // A previous playback's teardown deactivated it, so this is
            // what re-resolves the current output route (Bluetooth /
            // AirPlay / speaker) with whatever is connected right now.
            configureAudioSession()

            // If a previous stream connected the player at a different
            // format, disconnect first — AVAudioEngine will reconnect at
            // the new format below.
            if hasAttached {
                engine.disconnectNodeOutput(playerNode)
            } else {
                engine.attach(playerNode)
                hasAttached = true
            }

            engine.connect(playerNode, to: engine.mainMixerNode, format: format)
            currentFormat = format

            // Reset drain tracking for the new stream.
            drainLock.lock()
            pendingBuffers = 0
            streamEnded = false
            drainLock.unlock()

            try ensureEngineRunning()
            if !playerNode.isPlaying {
                playerNode.play()
            }
            call.resolve()
        } catch {
            call.reject("Failed to prepare engine: \(error.localizedDescription)")
        }
    }

    @objc func feedFrame(_ call: CAPPluginCall) {
        guard let pcmBase64 = call.getString("pcmBase64"),
              let pcmData = Data(base64Encoded: pcmBase64),
              let format = currentFormat
        else {
            call.reject("pcmBase64 required; prepare() must be called first")
            return
        }

        let channelCount = Int(format.channelCount)
        let totalInt16 = pcmData.count / MemoryLayout<Int16>.size
        let frameCount = totalInt16 / channelCount
        guard frameCount > 0,
              let buffer = AVAudioPCMBuffer(
                pcmFormat: format,
                frameCapacity: AVAudioFrameCount(frameCount)
              )
        else {
            call.reject("Failed to allocate PCM buffer for \(frameCount) frames")
            return
        }
        buffer.frameLength = AVAudioFrameCount(frameCount)

        pcmData.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
            let int16Ptr = raw.bindMemory(to: Int16.self)
            for ch in 0..<channelCount {
                guard let channel = buffer.floatChannelData?[ch] else { continue }
                for i in 0..<frameCount {
                    let sample = int16Ptr[i * channelCount + ch]
                    channel[i] = Float(sample) / 32768.0
                }
            }
        }

        drainLock.lock()
        pendingBuffers += 1
        drainLock.unlock()

        playerNode.scheduleBuffer(buffer, at: nil, options: []) { [weak self] in
            guard let self = self else { return }
            self.drainLock.lock()
            self.pendingBuffers = max(0, self.pendingBuffers - 1)
            let shouldFire = self.streamEnded && self.pendingBuffers == 0
            self.drainLock.unlock()
            if shouldFire {
                DispatchQueue.main.async {
                    // Natural end: release the engine + audio session so
                    // the Dynamic Island clears, then tell JS.
                    self.teardownEngineAndSession()
                    self.notifyListeners("playbackEnded", data: [:])
                }
            }
        }
        call.resolve()
    }

    @objc func markStreamEnd(_ call: CAPPluginCall) {
        drainLock.lock()
        streamEnded = true
        let shouldFireImmediately = pendingBuffers == 0
        drainLock.unlock()
        if shouldFireImmediately {
            // No frames in flight — fire end now so the UI doesn't hang.
            DispatchQueue.main.async {
                self.teardownEngineAndSession()
                self.notifyListeners("playbackEnded", data: [:])
            }
        }
        call.resolve()
    }

    /// Pause playback without dropping scheduled buffers. Frames that arrived
    /// before pause stay in the player node's queue; resume() picks up at the
    /// exact sample where pause() landed. Newly-arrived frames during the
    /// paused window continue to accumulate via feedFrame().
    @objc func pause(_ call: CAPPluginCall) {
        if playerNode.isPlaying {
            playerNode.pause()
        }
        // Reflect the paused state in Now Playing so the lock-screen widget
        // shows the correct icon and time-position freezes.
        var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
        info[MPNowPlayingInfoPropertyPlaybackRate] = NSNumber(value: 0.0)
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        call.resolve()
    }

    @objc func resume(_ call: CAPPluginCall) {
        do {
            // An interruption (phone call, Siri) deactivates our session.
            // Re-activate before restarting the engine so resume works
            // after a call and re-resolves the current output route.
            configureAudioSession()
            try ensureEngineRunning()
            if !playerNode.isPlaying {
                playerNode.play()
            }
            var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
            info[MPNowPlayingInfoPropertyPlaybackRate] = NSNumber(value: 1.0)
            MPNowPlayingInfoCenter.default().nowPlayingInfo = info
            call.resolve()
        } catch {
            call.reject("Failed to resume engine: \(error.localizedDescription)")
        }
    }

    @objc func stop(_ call: CAPPluginCall) {
        teardownEngineAndSession()
        call.resolve()
    }

    @objc func setMetadata(_ call: CAPPluginCall) {
        var info: [String: Any] = [:]
        if let title = call.getString("title") { info[MPMediaItemPropertyTitle] = title }
        if let artist = call.getString("artist") { info[MPMediaItemPropertyArtist] = artist }
        if let album = call.getString("album") { info[MPMediaItemPropertyAlbumTitle] = album }
        info[MPNowPlayingInfoPropertyPlaybackRate] = NSNumber(value: 1.0)

        // Artwork from a URL provided by JS (the Kahani logo served by the
        // backend). Load asynchronously so we don't block the JS call.
        if let artworkUrlStr = call.getString("artworkUrl"),
           let url = URL(string: artworkUrlStr) {
            DispatchQueue.global(qos: .utility).async {
                if let data = try? Data(contentsOf: url),
                   let image = UIImage(data: data) {
                    let artwork = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
                    DispatchQueue.main.async {
                        var current = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
                        current[MPMediaItemPropertyArtwork] = artwork
                        MPNowPlayingInfoCenter.default().nowPlayingInfo = current
                    }
                }
            }
        }

        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        call.resolve()
    }

    private func clearNowPlaying() {
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }

    // MARK: - Remote commands (lock screen / AirPods / CarPlay buttons)

    private func setupRemoteCommands() {
        guard !hasSetupRemoteCommands else { return }
        hasSetupRemoteCommands = true

        let cc = MPRemoteCommandCenter.shared()
        cc.playCommand.isEnabled = true
        cc.pauseCommand.isEnabled = true
        cc.stopCommand.isEnabled = true
        cc.togglePlayPauseCommand.isEnabled = true

        cc.playCommand.addTarget { [weak self] _ in
            self?.notifyListeners("remoteCommand", data: ["action": "play"])
            return .success
        }
        cc.pauseCommand.addTarget { [weak self] _ in
            self?.notifyListeners("remoteCommand", data: ["action": "pause"])
            return .success
        }
        cc.stopCommand.addTarget { [weak self] _ in
            self?.notifyListeners("remoteCommand", data: ["action": "stop"])
            return .success
        }
        cc.togglePlayPauseCommand.addTarget { [weak self] _ in
            self?.notifyListeners("remoteCommand", data: ["action": "togglePlayPause"])
            return .success
        }
    }

    // MARK: - Audio session events

    @objc private func handleInterruption(_ notification: Notification) {
        guard let userInfo = notification.userInfo,
              let typeValue = userInfo[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: typeValue)
        else { return }

        switch type {
        case .began:
            notifyListeners("interruption", data: ["state": "began"])
        case .ended:
            let opts = userInfo[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
            let shouldResume = AVAudioSession.InterruptionOptions(rawValue: opts).contains(.shouldResume)
            notifyListeners("interruption", data: ["state": "ended", "shouldResume": shouldResume])
        @unknown default:
            break
        }
    }

    @objc private func handleRouteChange(_ notification: Notification) {
        guard let userInfo = notification.userInfo,
              let reasonValue = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue)
        else { return }

        // Reason names we care about reporting to JS:
        // - oldDeviceUnavailable: headphones unplugged → pause is typical
        // - newDeviceAvailable: headphones plugged in → keep playing
        let reasonStr: String
        switch reason {
        case .oldDeviceUnavailable: reasonStr = "oldDeviceUnavailable"
        case .newDeviceAvailable:   reasonStr = "newDeviceAvailable"
        case .categoryChange:       reasonStr = "categoryChange"
        case .override:             reasonStr = "override"
        case .wakeFromSleep:        reasonStr = "wakeFromSleep"
        case .noSuitableRouteForCategory: reasonStr = "noSuitableRoute"
        case .routeConfigurationChange:   reasonStr = "configChange"
        default: reasonStr = "unknown"
        }
        notifyListeners("routeChange", data: ["reason": reasonStr])
    }
}
