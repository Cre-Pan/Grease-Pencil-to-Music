import AVFoundation
import UIKit
import WebKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Sound even with the silent switch, like a music app.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [])
        try? AVAudioSession.sharedInstance().setActive(true)
        return true
    }

    func application(_ application: UIApplication, configurationForConnecting session: UISceneSession, options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let config = UISceneConfiguration(name: "Main", sessionRole: session.role)
        config.delegateClass = SceneDelegate.self
        return config
    }
}

/// The scene life cycle, which apps built with the iOS 26 SDK and later must adopt.
/// One window, resizable in iPadOS windowing; the web app lays itself out to any size.
final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        scene.sizeRestrictions?.minimumSize = CGSize(width: 500, height: 400)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = WebViewController()
        window.makeKeyAndVisible()
        self.window = window
    }
}

/// The page reaches the bottom edge: no inset for the home indicator, which otherwise leaves a
/// band of empty space under the bottom bar. The other insets stay (the window controls when the
/// app is in a window).
final class FullScreenWebView: WKWebView {
    override var safeAreaInsets: UIEdgeInsets {
        var insets = super.safeAreaInsets
        insets.bottom = 0
        return insets
    }
}

/// Serves the bundled web app (the "app" folder, a copy of docs/app) at app://local/.
/// A custom scheme rather than file://, where fetch() of the samples is refused.
final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    private let root = Bundle.main.resourceURL!.appendingPathComponent("app", isDirectory: true)

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return }
        var path = url.path.removingPercentEncoding ?? url.path
        if path.isEmpty || path == "/" { path = "/index.html" }
        let file = root.appendingPathComponent(String(path.dropFirst()))
        guard file.path.hasPrefix(root.path), let data = try? Data(contentsOf: file) else {
            task.didReceive(HTTPURLResponse(url: url, statusCode: 404, httpVersion: "HTTP/1.1", headerFields: nil)!)
            task.didFinish()
            return
        }
        let headers = ["Content-Type": Self.mime(file.pathExtension), "Content-Length": String(data.count), "Access-Control-Allow-Origin": "*"]
        task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}

    static func mime(_ ext: String) -> String {
        switch ext.lowercased() {
        case "html": return "text/html; charset=utf-8"
        case "js": return "text/javascript; charset=utf-8"
        case "json", "webmanifest": return "application/json"
        case "css": return "text/css"
        case "png": return "image/png"
        case "svg": return "image/svg+xml"
        case "mp3": return "audio/mpeg"
        case "wav": return "audio/wav"
        default: return "application/octet-stream"
        }
    }
}

/// A transparent view over the web app's CTRL button. Touches on it stay in UIKit and never
/// reach WebKit, which on iPad lets no Pencil input through while a finger is down on the page:
/// here the finger holds CTRL and the Pencil still draws.
final class GripView: UIView {
    weak var web: WKWebView?
    private var finger: UITouch?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .clear
        isMultipleTouchEnabled = false
        isExclusiveTouch = false
    }
    required init?(coder: NSCoder) { fatalError() }

    private func call(_ js: String) { web?.evaluateJavaScript("window.__gp2mGrip && window.__gp2mGrip.\(js)", completionHandler: nil) }
    private func point(_ t: UITouch) -> CGPoint { t.location(in: web) }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard finger == nil, let t = touches.first else { return }
        finger = t
        let p = point(t)
        call("start(\(p.x), \(p.y))")
    }
    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let t = finger, touches.contains(t) else { return }
        let p = point(t)
        call("move(\(p.x), \(p.y))")
    }
    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let t = finger, touches.contains(t) else { return }
        finger = nil
        call("end()")
    }
    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchesEnded(touches, with: event)
    }
}

final class WebViewController: UIViewController, WKScriptMessageHandler, WKUIDelegate, WKNavigationDelegate, UIPencilInteractionDelegate {
    /// The published web app: every new version reaches the app without reinstalling it.
    /// Offline, or if the site can't be reached, the copy bundled in the app is used.
    static let live = URL(string: "https://cre-pan.github.io/Grease-Pencil-to-Music/app/")!
    static let bundled = URL(string: "app://local/index.html")!
    private var web: WKWebView!
    private var onBundle = false
    private let grip = GripView()

    override var prefersStatusBarHidden: Bool { true }
    override var prefersHomeIndicatorAutoHidden: Bool { true }
    override var preferredScreenEdgesDeferringSystemGestures: UIRectEdge { .all }

    override func loadView() {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(BundleSchemeHandler(), forURLScheme: "app")
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        let content = WKUserContentController()
        content.add(self, name: "gripRect")
        content.add(self, name: "save")
        config.userContentController = content

        web = FullScreenWebView(frame: .zero, configuration: config)
        web.uiDelegate = self
        web.navigationDelegate = self
        web.allowsLinkPreview = false
        web.isOpaque = false
        web.backgroundColor = .black
        web.scrollView.isScrollEnabled = false
        web.scrollView.bounces = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        if #available(iOS 16.4, *) { web.isInspectable = true }  // Safari → Develop, to debug on the iPad

        let root = UIView()
        root.backgroundColor = .black
        web.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(web)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            web.topAnchor.constraint(equalTo: root.topAnchor),
            web.bottomAnchor.constraint(equalTo: root.bottomAnchor),
        ])
        grip.web = web
        grip.frame = .zero
        root.addSubview(grip)

        let pencil = UIPencilInteraction()
        pencil.delegate = self
        root.addInteraction(pencil)
        view = root
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        web.load(URLRequest(url: Self.live, cachePolicy: .reloadRevalidatingCacheData, timeoutInterval: 8))
    }

    private func fallBack() {
        guard !onBundle else { return }
        onBundle = true
        web.load(URLRequest(url: Self.bundled))
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { fallBack() }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled, webView.url?.scheme != "app" { fallBack() }
    }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let http = response.response as? HTTPURLResponse, response.isForMainFrame, http.statusCode >= 400 {
            decisionHandler(.cancel); fallBack(); return
        }
        decisionHandler(.allow)
    }
    // Links to other sites open in Safari, not in place of the app.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, action.navigationType == .linkActivated,
           url.host != Self.live.host || !url.path.hasPrefix(Self.live.path) {
            UIApplication.shared.open(url); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }

    // MARK: messages from the page

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        switch message.name {
        case "gripRect":
            guard let r = message.body as? [Double], r.count == 4 else { return }
            // a little larger than the button, as a finger is
            grip.frame = r[2] > 0 ? CGRect(x: r[0], y: r[1], width: r[2], height: r[3]).insetBy(dx: -8, dy: -8) : .zero
        case "save":
            guard let body = message.body as? [String: Any], let name = body["name"] as? String,
                  let b64 = body["data"] as? String, let data = Data(base64Encoded: b64) else { return }
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
            try? data.write(to: url)
            let share = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            share.popoverPresentationController?.sourceView = view
            share.popoverPresentationController?.sourceRect = CGRect(x: view.bounds.midX, y: 60, width: 1, height: 1)
            present(share, animated: true)
        default: break
        }
    }

    // MARK: Apple Pencil: double tap (2nd gen, Pro) toggles CTRL, squeeze (Pro) plays or pauses

    private func grip(_ call: String) {
        web.evaluateJavaScript("window.__gp2mGrip && window.__gp2mGrip.\(call)()", completionHandler: nil)
    }

    func pencilInteractionDidTap(_ interaction: UIPencilInteraction) { grip("toggle") }

    @available(iOS 17.5, *)
    func pencilInteraction(_ interaction: UIPencilInteraction, didReceiveSqueeze squeeze: UIPencilInteraction.Squeeze) {
        if squeeze.phase == .ended { grip("playPause") }
    }

    @available(iOS 17.5, *)
    func pencilInteraction(_ interaction: UIPencilInteraction, didReceiveTap tap: UIPencilInteraction.Tap) { grip("toggle") }

    // MARK: alert / confirm / prompt from the page

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "Annulla", style: .cancel) { _ in completionHandler(false) })
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        a.addTextField { $0.text = defaultText }
        a.addAction(UIAlertAction(title: "Annulla", style: .cancel) { _ in completionHandler(nil) })
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(a.textFields?.first?.text) })
        present(a, animated: true)
    }

    // Camera and microphone (voice, video): granted once the system asked.
    @available(iOS 15.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(.grant)
    }
}
