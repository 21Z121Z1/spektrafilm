import Foundation

public enum SpektrafilmPythonError: Error, LocalizedError, Equatable {
    case launchFailed(String)
    case processFailed(exitCode: Int32, stderr: String)
    case invalidJSON(String)

    public var errorDescription: String? {
        switch self {
        case .launchFailed(let message):
            "Could not launch Python bridge: \(message)"
        case .processFailed(let exitCode, let stderr):
            "Python bridge exited with \(exitCode): \(stderr)"
        case .invalidJSON(let message):
            "Python bridge returned invalid JSON: \(message)"
        }
    }
}

public actor SpektrafilmPythonClient {
    private let commandBuilder: PythonBridgeCommandBuilder

    public init(commandBuilder: PythonBridgeCommandBuilder) {
        self.commandBuilder = commandBuilder
    }

    public func render(_ request: RenderRequest) async throws -> RenderResult {
        let data = try await run(commandBuilder.renderCommand(for: request))
        do {
            return try JSONDecoder().decode(RenderResult.self, from: data)
        } catch {
            let text = String(data: data, encoding: .utf8) ?? "<non-utf8>"
            throw SpektrafilmPythonError.invalidJSON("\(error). Payload: \(text)")
        }
    }

    private func run(_ configuration: ProcessConfiguration) async throws -> Data {
        try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = configuration.executableURL
            process.arguments = configuration.arguments
            process.currentDirectoryURL = configuration.currentDirectoryURL

            let stdout = Pipe()
            let stderr = Pipe()
            process.standardOutput = stdout
            process.standardError = stderr

            do {
                try process.run()
            } catch {
                throw SpektrafilmPythonError.launchFailed(error.localizedDescription)
            }
            process.waitUntilExit()

            let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
            let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
            if process.terminationStatus != 0 {
                let errorText = String(data: errorData, encoding: .utf8) ?? ""
                throw SpektrafilmPythonError.processFailed(
                    exitCode: process.terminationStatus,
                    stderr: errorText.trimmingCharacters(in: .whitespacesAndNewlines)
                )
            }
            return outputData
        }.value
    }
}
