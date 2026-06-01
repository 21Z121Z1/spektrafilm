import Foundation

public enum AppSelfCheck {
    public static func run(repoRoot: URL) throws -> String {
        let pyprojectURL = repoRoot.appendingPathComponent("pyproject.toml")
        guard FileManager.default.fileExists(atPath: pyprojectURL.path) else {
            throw AppSelfCheckError.missingRepoRoot(repoRoot.path)
        }

        let profilesURL = repoRoot
            .appendingPathComponent("src")
            .appendingPathComponent("spektrafilm")
            .appendingPathComponent("data")
            .appendingPathComponent("profiles")
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: profilesURL.path, isDirectory: &isDirectory), isDirectory.boolValue else {
            throw AppSelfCheckError.missingProfilesDirectory(profilesURL.path)
        }

        let catalog = ProfileCatalog.load(from: repoRoot)
        let defaults = RenderConfiguration.defaults
        guard catalog.filmProfiles.contains(defaults.filmStock) else {
            throw AppSelfCheckError.missingDefaultFilm(defaults.filmStock)
        }
        guard catalog.printProfiles.contains(defaults.printPaper) else {
            throw AppSelfCheckError.missingDefaultPaper(defaults.printPaper)
        }

        return "SpektrafilmMac self-check OK: \(catalog.filmProfiles.count) film profiles, \(catalog.printProfiles.count) print profiles"
    }
}

public enum AppSelfCheckError: Error, Equatable, LocalizedError {
    case missingRepoRoot(String)
    case missingProfilesDirectory(String)
    case missingDefaultFilm(String)
    case missingDefaultPaper(String)

    public var errorDescription: String? {
        switch self {
        case let .missingRepoRoot(path):
            "Missing spektrafilm repo root at \(path)"
        case let .missingProfilesDirectory(path):
            "Missing profile directory at \(path)"
        case let .missingDefaultFilm(name):
            "Default film profile is not available: \(name)"
        case let .missingDefaultPaper(name):
            "Default print profile is not available: \(name)"
        }
    }
}
