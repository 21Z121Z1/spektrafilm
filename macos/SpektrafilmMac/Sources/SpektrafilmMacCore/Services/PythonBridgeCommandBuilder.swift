import Foundation

public struct ProcessConfiguration: Equatable, Sendable {
    public var executableURL: URL
    public var arguments: [String]
    public var currentDirectoryURL: URL
}

public struct PythonBridgeCommandBuilder: Equatable, Sendable {
    public var repoRoot: URL
    public var pythonExecutablePath: String?

    public init(
        repoRoot: URL,
        pythonExecutablePath: String? = ProcessInfo.processInfo.environment["SPEKTRAFILM_PYTHON"]
    ) {
        self.repoRoot = repoRoot
        if pythonExecutablePath?.isEmpty == false {
            self.pythonExecutablePath = pythonExecutablePath
        } else {
            let bundledVenv = repoRoot
                .appendingPathComponent("macos")
                .appendingPathComponent("SpektrafilmMac")
                .appendingPathComponent(".venv-macos")
                .appendingPathComponent("bin")
                .appendingPathComponent("python")
            self.pythonExecutablePath = FileManager.default.isExecutableFile(atPath: bundledVenv.path)
                ? bundledVenv.path
                : nil
        }
    }

    public func describeCommand() -> ProcessConfiguration {
        let bridge = bridgeInvocation(command: "describe")
        return ProcessConfiguration(
            executableURL: bridge.executableURL,
            arguments: bridge.arguments,
            currentDirectoryURL: repoRoot
        )
    }

    public func renderCommand(for request: RenderRequest) -> ProcessConfiguration {
        let c = request.configuration
        let bridge = bridgeInvocation(command: "render")
        var arguments = bridge.arguments + [
            "--input", request.inputURL.path,
            "--preview-output", request.previewOutputURL.path,
            "--mode", request.mode.rawValue,
            "--input-kind", "auto",
            "--film-stock", c.filmStock,
            "--print-paper", c.printPaper,
            "--input-color-space", c.inputColorSpace,
            booleanFlag("apply-cctf-decoding", c.applyCCTFDecoding),
            "--output-color-space", c.outputColorSpace,
            "--saving-color-space", c.savingColorSpace,
            booleanFlag("saving-cctf-encoding", c.savingCCTFEncoding),
            "--preview-max-size", String(c.previewMaxSize),
            "--compute-backend", c.computeBackend,
            "--gpu-precision", c.gpuPrecision,
            booleanFlag("scan-film", c.scanFilm),
            booleanFlag("auto-exposure", c.autoExposure),
            "--exposure-compensation-ev", String(c.exposureCompensationEV),
            "--print-exposure", String(c.printExposure),
            "--print-y-filter-shift", String(c.printYFilterShift),
            "--print-m-filter-shift", String(c.printMFilterShift),
            booleanFlag("grain-active", c.grainActive),
            booleanFlag("halation-active", c.halationActive),
            booleanFlag("couplers-active", c.couplersActive)
        ]
        if let outputURL = request.outputURL {
            arguments.append(contentsOf: ["--output", outputURL.path])
        }
        return ProcessConfiguration(
            executableURL: bridge.executableURL,
            arguments: arguments,
            currentDirectoryURL: repoRoot
        )
    }

    private func bridgeInvocation(command: String) -> (executableURL: URL, arguments: [String]) {
        if let pythonExecutablePath {
            return (
                URL(fileURLWithPath: pythonExecutablePath),
                ["-m", "spektrafilm_gui.macos_bridge", command]
            )
        }
        return (
            URL(fileURLWithPath: "/usr/bin/env"),
            ["uv", "run", "python", "-m", "spektrafilm_gui.macos_bridge", command]
        )
    }

    private func booleanFlag(_ name: String, _ value: Bool) -> String {
        value ? "--\(name)" : "--no-\(name)"
    }
}

public enum RepoRootResolver {
    public static func resolve(
        infoDictionary: [String: Any]? = Bundle.main.infoDictionary,
        bundleURL: URL = Bundle.main.bundleURL,
        currentDirectoryURL: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true),
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> URL {
        if let path = environment["SPEKTRAFILM_REPO_ROOT"], !path.isEmpty {
            return URL(fileURLWithPath: path, isDirectory: true)
        }

        if let path = infoDictionary?["SpektrafilmRepoRoot"] as? String, !path.isEmpty {
            return URL(fileURLWithPath: path, isDirectory: true)
        }

        let distURL = bundleURL.deletingLastPathComponent()
        if distURL.lastPathComponent == "dist" {
            return distURL
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
        }

        if FileManager.default.fileExists(atPath: currentDirectoryURL.appendingPathComponent("pyproject.toml").path) {
            return currentDirectoryURL
        }
        return currentDirectoryURL
    }
}
