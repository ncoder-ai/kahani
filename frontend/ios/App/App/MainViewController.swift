//
//  MainViewController.swift
//  Kahani — custom CAPBridgeViewController subclass that registers
//  local (in-app) Capacitor plugins.
//
//  Capacitor 7's auto-discovery (`registerPlugins()` in CapacitorBridge)
//  only picks up plugins listed in `capacitor.config.json`'s
//  `packageClassList` — which is populated by `npx cap sync ios` from
//  the `@capacitor/*` npm dependencies. Plugins defined directly inside
//  the App target (like NativeTTSPlugin) are NOT in that list, so they
//  need to be registered manually via `bridge.registerPluginInstance(...)`
//  during `capacitorDidLoad()`. Without this hook, JS calls to our
//  plugin's methods return `{code: "UNIMPLEMENTED"}`.
//
//  Wired in via Main.storyboard — the storyboard's initial view
//  controller is set to this class (customClass="MainViewController",
//  customModule="App") instead of the default CAPBridgeViewController.
//

import UIKit
import Capacitor

class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(NativeTTSPlugin())
        bridge?.registerPluginInstance(NativePinLockPlugin())
    }
}
