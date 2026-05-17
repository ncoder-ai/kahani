import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?
    private var privacyCover: UIView?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Override point for customization after application launch.
        return true
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // iOS snapshots the app for the app switcher between
        // willResignActive and didEnterBackground. The JS-side PIN
        // lock can't react in time (visibilitychange fires after the
        // snapshot is taken), so any open story would leak through
        // the switcher preview. Cover the WebView with a splash-style
        // screen before the snapshot lands.
        showPrivacyCover()
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        hidePrivacyCover()
    }

    private func showPrivacyCover() {
        guard privacyCover == nil else { return }
        guard let host = keyWindow() else { return }

        let cover = UIView(frame: host.bounds)
        cover.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        // Matches capacitor.config.ts backgroundColor (#0a0a0f)
        cover.backgroundColor = UIColor(red: 0x0a/255.0, green: 0x0a/255.0, blue: 0x0f/255.0, alpha: 1.0)

        if let splash = UIImage(named: "Splash") {
            let imageView = UIImageView(image: splash)
            imageView.contentMode = .scaleAspectFill
            imageView.frame = cover.bounds
            imageView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            cover.addSubview(imageView)
        }

        host.addSubview(cover)
        host.bringSubviewToFront(cover)
        privacyCover = cover
    }

    private func hidePrivacyCover() {
        privacyCover?.removeFromSuperview()
        privacyCover = nil
    }

    private func keyWindow() -> UIWindow? {
        if let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive || $0.activationState == .foregroundInactive }) {
            if let key = scene.windows.first(where: { $0.isKeyWindow }) {
                return key
            }
            return scene.windows.first
        }
        return self.window
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // Called when the app was launched with a url. Feel free to add additional processing here,
        // but if you want the App API to support tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        // Feel free to add additional processing here, but if you want the App API to support
        // tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

}
