import AppKit
import Foundation
import SpektrafilmMacCore

@MainActor
public final class SpektrafilmAppModel: ObservableObject {
    @Published public var catalog: ProfileCatalog
    @Published public var configuration: RenderConfiguration
    @Published public var selectedSection: WorkflowSection?
    @Published public var inputURL: URL?
    @Published public var previewImage: NSImage?
    @Published public var lastPreviewURL: URL?
    @Published public var lastOutputURL: URL?
    @Published public var statusText: String
    @Published public var isRendering: Bool
    @Published public var isInspectorPresented: Bool

    public let repoRoot: URL
    private let client: SpektrafilmPythonClient

    public init(repoRoot: URL = RepoRootResolver.resolve()) {
        self.repoRoot = repoRoot
        self.catalog = ProfileCatalog.load(from: repoRoot)
        self.configuration = .defaults
        self.selectedSection = .importImage
        self.statusText = "Ready"
        self.isRendering = false
        self.isInspectorPresented = true
        self.client = SpektrafilmPythonClient(
            commandBuilder: PythonBridgeCommandBuilder(repoRoot: repoRoot)
        )
    }

    public var canRender: Bool {
        inputURL != nil && !isRendering
    }

    public var canSave: Bool {
        inputURL != nil && !isRendering
    }

    public func selectInputFile() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.title = "Open Image"
        if panel.runModal() == .OK, let url = panel.url {
            inputURL = url
            previewImage = NSImage(contentsOf: url)
            lastPreviewURL = nil
            lastOutputURL = nil
            statusText = "Loaded \(url.lastPathComponent)"
            selectedSection = .profiles
        }
    }

    public func renderPreview() async {
        await render(mode: .preview, outputURL: nil)
    }

    public func renderScanWithSavePanel() async {
        guard let inputURL else {
            statusText = "Load an input image before scanning"
            return
        }
        let panel = NSSavePanel()
        panel.title = "Save Spektrafilm Output"
        panel.nameFieldStringValue = inputURL.deletingPathExtension().lastPathComponent + "-spektrafilm.png"
        guard panel.runModal() == .OK, let outputURL = panel.url else {
            return
        }
        await render(mode: .scan, outputURL: outputURL)
    }

    private func render(mode: RenderMode, outputURL: URL?) async {
        guard let inputURL else {
            statusText = "Load an input image before rendering"
            return
        }
        isRendering = true
        statusText = mode == .preview ? "Rendering preview..." : "Rendering scan..."
        defer { isRendering = false }

        let previewURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("spektrafilm-\(UUID().uuidString).png")
        let request = RenderRequest(
            inputURL: inputURL,
            previewOutputURL: previewURL,
            outputURL: outputURL,
            mode: mode,
            configuration: configuration
        )
        do {
            let result = try await client.render(request)
            if let image = NSImage(contentsOf: URL(fileURLWithPath: result.previewPath)) {
                previewImage = image
            }
            lastPreviewURL = URL(fileURLWithPath: result.previewPath)
            if let outputPath = result.outputPath {
                lastOutputURL = URL(fileURLWithPath: outputPath)
            }
            let sizeText = "\(result.width)x\(result.height)"
            let elapsed = String(format: "%.2fs", result.elapsedSeconds)
            if let warning = result.metadataWarning, !warning.isEmpty {
                statusText = "\(mode.title) completed: \(sizeText), \(elapsed). Metadata: \(warning)"
            } else {
                statusText = "\(mode.title) completed: \(sizeText), \(elapsed)"
            }
            selectedSection = .export
        } catch {
            statusText = error.localizedDescription
        }
    }
}

private extension RenderMode {
    var title: String {
        switch self {
        case .preview: "Preview"
        case .scan: "Scan"
        }
    }
}
