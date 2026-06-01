import Foundation

public enum RenderMode: String, Codable, CaseIterable, Sendable {
    case preview
    case scan
}

public struct RenderConfiguration: Equatable, Sendable {
    public var filmStock: String
    public var printPaper: String
    public var inputColorSpace: String
    public var applyCCTFDecoding: Bool
    public var outputColorSpace: String
    public var savingColorSpace: String
    public var savingCCTFEncoding: Bool
    public var previewMaxSize: Int
    public var computeBackend: String
    public var gpuPrecision: String
    public var scanFilm: Bool
    public var autoExposure: Bool
    public var exposureCompensationEV: Double
    public var printExposure: Double
    public var printYFilterShift: Double
    public var printMFilterShift: Double
    public var grainActive: Bool
    public var halationActive: Bool
    public var couplersActive: Bool

    public static let defaults = RenderConfiguration(
        filmStock: "kodak_gold_200",
        printPaper: "kodak_supra_endura",
        inputColorSpace: "sRGB",
        applyCCTFDecoding: false,
        outputColorSpace: "sRGB",
        savingColorSpace: "sRGB",
        savingCCTFEncoding: true,
        previewMaxSize: 640,
        computeBackend: "cpu",
        gpuPrecision: "float32",
        scanFilm: false,
        autoExposure: true,
        exposureCompensationEV: 0.0,
        printExposure: 1.0,
        printYFilterShift: 0.0,
        printMFilterShift: 0.0,
        grainActive: true,
        halationActive: true,
        couplersActive: true
    )
}

public struct RenderRequest: Equatable, Sendable {
    public var inputURL: URL
    public var previewOutputURL: URL
    public var outputURL: URL?
    public var mode: RenderMode
    public var configuration: RenderConfiguration

    public init(
        inputURL: URL,
        previewOutputURL: URL,
        outputURL: URL?,
        mode: RenderMode,
        configuration: RenderConfiguration
    ) {
        self.inputURL = inputURL
        self.previewOutputURL = previewOutputURL
        self.outputURL = outputURL
        self.mode = mode
        self.configuration = configuration
    }
}

public struct RenderResult: Decodable, Equatable, Sendable {
    public var ok: Bool
    public var mode: String
    public var previewPath: String
    public var outputPath: String?
    public var width: Int
    public var height: Int
    public var elapsedSeconds: Double
    public var displayStatus: String
    public var metadataWarning: String?
    public var timings: [String: Double]

    enum CodingKeys: String, CodingKey {
        case ok
        case mode
        case previewPath = "preview_path"
        case outputPath = "output_path"
        case width
        case height
        case elapsedSeconds = "elapsed_seconds"
        case displayStatus = "display_status"
        case metadataWarning = "metadata_warning"
        case timings
    }
}

public struct ProfileCatalog: Equatable, Sendable {
    public var filmProfiles: [String]
    public var printProfiles: [String]
    public var colorSpaces: [String]
    public var computeBackends: [String]
    public var gpuPrecisions: [String]

    public static let fallback = ProfileCatalog(
        filmProfiles: [
            "kodak_gold_200",
            "kodak_portra_400",
            "kodak_ektar_100",
            "kodak_ektachrome_100",
            "fujifilm_provia_100f"
        ],
        printProfiles: [
            "kodak_supra_endura",
            "kodak_portra_endura",
            "kodak_ektacolor_edge",
            "fujifilm_crystal_archive_typeii"
        ],
        colorSpaces: [
            "sRGB",
            "Display P3",
            "DCI-P3",
            "Adobe RGB (1998)",
            "ITU-R BT.2020",
            "ProPhoto RGB",
            "ACES2065-1",
            "ACEScg"
        ],
        computeBackends: ["cpu", "auto", "mlx", "cupy", "halide"],
        gpuPrecisions: ["float32", "float64"]
    )

    public static func load(from repoRoot: URL) -> ProfileCatalog {
        let profilesURL = repoRoot
            .appendingPathComponent("src")
            .appendingPathComponent("spektrafilm")
            .appendingPathComponent("data")
            .appendingPathComponent("profiles")
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: profilesURL,
            includingPropertiesForKeys: nil
        ) else {
            return .fallback
        }

        var films: [String] = []
        var papers: [String] = []
        for fileURL in files where fileURL.pathExtension == "json" {
            guard
                let data = try? Data(contentsOf: fileURL),
                let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let info = object["info"] as? [String: Any]
            else {
                continue
            }
            let stock = (info["stock"] as? String) ?? fileURL.deletingPathExtension().lastPathComponent
            if (info["support"] as? String) == "paper" {
                papers.append(stock)
            } else {
                films.append(stock)
            }
        }

        var catalog = fallback
        if !films.isEmpty {
            catalog.filmProfiles = films.sorted()
        }
        if !papers.isEmpty {
            catalog.printProfiles = papers.sorted()
        }
        return catalog
    }
}

public enum WorkflowSection: String, CaseIterable, Identifiable, Sendable {
    case importImage
    case profiles
    case render
    case export

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .importImage: "Import"
        case .profiles: "Profiles"
        case .render: "Render"
        case .export: "Export"
        }
    }

    public var systemImage: String {
        switch self {
        case .importImage: "photo.badge.plus"
        case .profiles: "camera.filters"
        case .render: "play.rectangle"
        case .export: "square.and.arrow.down"
        }
    }
}
