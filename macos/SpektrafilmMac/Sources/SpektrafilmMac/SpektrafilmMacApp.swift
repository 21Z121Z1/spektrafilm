import AppKit
import Darwin
import SpektrafilmMacCore
import SwiftUI

@main
@MainActor
final class SpektrafilmMacApp: NSObject, NSApplicationDelegate {
    private static var retainedDelegate: SpektrafilmMacApp?
    private var window: NSWindow?

    static func main() {
        AppEntrySupport.runSelfCheckIfRequested()

        let app = NSApplication.shared
        let delegate = SpektrafilmMacApp()
        retainedDelegate = delegate
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let contentView = ContentView()
        let hostingController = NSHostingController(rootView: contentView)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1180, height: 760),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Spektrafilm"
        window.titlebarAppearsTransparent = true
        window.toolbarStyle = .unifiedCompact
        window.isReleasedWhenClosed = false
        window.contentMinSize = NSSize(width: 1100, height: 720)
        window.center()
        window.contentViewController = hostingController
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        self.window = window
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false
    }
}

private enum AppEntrySupport {
    static func runSelfCheckIfRequested() {
        guard CommandLine.arguments.contains("--self-check") else {
            return
        }
        runSelfCheck()
    }

    private static func runSelfCheck() {
        do {
            let message = try AppSelfCheck.run(repoRoot: RepoRootResolver.resolve())
            print(message)
            exit(EXIT_SUCCESS)
        } catch {
            let message = "SpektrafilmMac self-check failed: \(error.localizedDescription)\n"
            FileHandle.standardError.write(Data(message.utf8))
            exit(EXIT_FAILURE)
        }
    }
}
