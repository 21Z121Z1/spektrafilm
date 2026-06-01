import Foundation
import Testing
@testable import SpektrafilmMacCore

@Test func renderConfigurationUsesPythonGuiDefaults() {
    let configuration = RenderConfiguration.defaults

    #expect(configuration.filmStock == "kodak_gold_200")
    #expect(configuration.printPaper == "kodak_supra_endura")
    #expect(configuration.inputColorSpace == "sRGB")
    #expect(configuration.outputColorSpace == "sRGB")
    #expect(configuration.previewMaxSize == 640)
    #expect(configuration.computeBackend == "cpu")
    #expect(configuration.gpuPrecision == "float32")
    #expect(configuration.autoExposure)
    #expect(configuration.grainActive)
    #expect(configuration.halationActive)
    #expect(configuration.couplersActive)
}

@Test func commandBuilderBuildsDescribeCommand() throws {
    let repoRoot = URL(fileURLWithPath: "/tmp/spektrafilm-main", isDirectory: true)
    let builder = PythonBridgeCommandBuilder(repoRoot: repoRoot)

    let command = builder.describeCommand()

    #expect(command.executableURL.path == "/usr/bin/env")
    #expect(command.currentDirectoryURL == repoRoot)
    #expect(command.arguments == [
        "uv",
        "run",
        "python",
        "-m",
        "spektrafilm_gui.macos_bridge",
        "describe"
    ])
}

@Test func commandBuilderAllowsExplicitPythonExecutable() throws {
    let repoRoot = URL(fileURLWithPath: "/tmp/spektrafilm-main", isDirectory: true)
    let builder = PythonBridgeCommandBuilder(
        repoRoot: repoRoot,
        pythonExecutablePath: "/opt/homebrew/bin/python3.14"
    )

    let command = builder.describeCommand()

    #expect(command.executableURL.path == "/opt/homebrew/bin/python3.14")
    #expect(command.currentDirectoryURL == repoRoot)
    #expect(command.arguments == [
        "-m",
        "spektrafilm_gui.macos_bridge",
        "describe"
    ])
}

@Test func commandBuilderBuildsPreviewRenderCommand() throws {
    let repoRoot = URL(fileURLWithPath: "/tmp/spektrafilm-main", isDirectory: true)
    let builder = PythonBridgeCommandBuilder(repoRoot: repoRoot)
    let request = RenderRequest(
        inputURL: URL(fileURLWithPath: "/tmp/in.tif"),
        previewOutputURL: URL(fileURLWithPath: "/tmp/preview.png"),
        outputURL: nil,
        mode: .preview,
        configuration: .defaults
    )

    let command = builder.renderCommand(for: request)

    #expect(command.currentDirectoryURL == repoRoot)
    #expect(command.arguments.contains("render"))
    #expect(command.arguments.contains("--mode"))
    #expect(command.arguments.contains("preview"))
    #expect(command.arguments.contains("--input"))
    #expect(command.arguments.contains("/tmp/in.tif"))
    #expect(command.arguments.contains("--preview-output"))
    #expect(command.arguments.contains("/tmp/preview.png"))
    #expect(!command.arguments.contains("--output"))
}

@Test func commandBuilderBuildsScanRenderCommandWithOutput() throws {
    let repoRoot = URL(fileURLWithPath: "/tmp/spektrafilm-main", isDirectory: true)
    let builder = PythonBridgeCommandBuilder(repoRoot: repoRoot)
    var configuration = RenderConfiguration.defaults
    configuration.filmStock = "kodak_portra_400"
    configuration.printPaper = "kodak_portra_endura"
    configuration.outputColorSpace = "Display P3"
    configuration.previewMaxSize = 512
    configuration.scanFilm = true
    configuration.grainActive = false
    let request = RenderRequest(
        inputURL: URL(fileURLWithPath: "/tmp/in.tif"),
        previewOutputURL: URL(fileURLWithPath: "/tmp/preview.png"),
        outputURL: URL(fileURLWithPath: "/tmp/out.png"),
        mode: .scan,
        configuration: configuration
    )

    let command = builder.renderCommand(for: request)

    #expect(command.arguments.contains("scan"))
    #expect(command.arguments.contains("--output"))
    #expect(command.arguments.contains("/tmp/out.png"))
    #expect(command.arguments.contains("--film-stock"))
    #expect(command.arguments.contains("kodak_portra_400"))
    #expect(command.arguments.contains("--print-paper"))
    #expect(command.arguments.contains("kodak_portra_endura"))
    #expect(command.arguments.contains("--output-color-space"))
    #expect(command.arguments.contains("Display P3"))
    #expect(command.arguments.contains("--preview-max-size"))
    #expect(command.arguments.contains("512"))
    #expect(command.arguments.contains("--scan-film"))
    #expect(command.arguments.contains("--no-grain-active"))
}

@Test func repoRootResolverUsesInfoDictionaryValueFirst() throws {
    let expected = URL(fileURLWithPath: "/tmp/spektrafilm-main", isDirectory: true)
    let resolved = RepoRootResolver.resolve(
        infoDictionary: ["SpektrafilmRepoRoot": "/tmp/spektrafilm-main"],
        bundleURL: URL(fileURLWithPath: "/Applications/SpektrafilmMac.app"),
        currentDirectoryURL: URL(fileURLWithPath: "/"),
        environment: [:]
    )

    #expect(resolved == expected)
}

@Test func repoRootResolverUsesEnvironmentValueBeforeBundleValues() throws {
    let expected = URL(fileURLWithPath: "/tmp/spektrafilm-env", isDirectory: true)
    let resolved = RepoRootResolver.resolve(
        infoDictionary: ["SpektrafilmRepoRoot": "/tmp/spektrafilm-main"],
        bundleURL: URL(fileURLWithPath: "/Applications/SpektrafilmMac.app"),
        currentDirectoryURL: URL(fileURLWithPath: "/"),
        environment: ["SPEKTRAFILM_REPO_ROOT": "/tmp/spektrafilm-env"]
    )

    #expect(resolved == expected)
}

@Test func repoRootResolverUsesBundleDistParentWhenInfoValueIsMissing() throws {
    let bundle = URL(fileURLWithPath: "/repo/macos/SpektrafilmMac/dist/SpektrafilmMac.app")
    let resolved = RepoRootResolver.resolve(
        infoDictionary: [:],
        bundleURL: bundle,
        currentDirectoryURL: URL(fileURLWithPath: "/"),
        environment: [:]
    )

    #expect(resolved.path == "/repo")
}

@Test func appSelfCheckPassesForMinimalValidRepo() throws {
    let repoRoot = try makeTemporaryRepo()

    let message = try AppSelfCheck.run(repoRoot: repoRoot)

    #expect(message.contains("self-check OK"))
    #expect(message.contains("1 film profiles"))
    #expect(message.contains("1 print profiles"))
}

@Test func appSelfCheckRejectsMissingRepoRoot() throws {
    let missingRoot = FileManager.default.temporaryDirectory
        .appendingPathComponent("spektrafilm-missing-\(UUID().uuidString)", isDirectory: true)

    do {
        _ = try AppSelfCheck.run(repoRoot: missingRoot)
        Issue.record("Self-check should fail for a missing repo root")
    } catch let error as AppSelfCheckError {
        #expect(error == .missingRepoRoot(missingRoot.path))
    }
}

private func makeTemporaryRepo() throws -> URL {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("spektrafilm-test-\(UUID().uuidString)", isDirectory: true)
    let profiles = root
        .appendingPathComponent("src", isDirectory: true)
        .appendingPathComponent("spektrafilm", isDirectory: true)
        .appendingPathComponent("data", isDirectory: true)
        .appendingPathComponent("profiles", isDirectory: true)
    try FileManager.default.createDirectory(at: profiles, withIntermediateDirectories: true)
    try Data().write(to: root.appendingPathComponent("pyproject.toml"))
    try writeProfile(named: "kodak_gold_200", support: "film", in: profiles)
    try writeProfile(named: "kodak_supra_endura", support: "paper", in: profiles)
    return root
}

private func writeProfile(named name: String, support: String, in directory: URL) throws {
    let json = """
    {
      "info": {
        "stock": "\(name)",
        "support": "\(support)"
      }
    }
    """
    try Data(json.utf8).write(to: directory.appendingPathComponent("\(name).json"))
}
