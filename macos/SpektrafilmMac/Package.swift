// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "SpektrafilmMac",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "SpektrafilmMac", targets: ["SpektrafilmMac"]),
        .library(name: "SpektrafilmMacCore", targets: ["SpektrafilmMacCore"])
    ],
    targets: [
        .executableTarget(
            name: "SpektrafilmMac",
            dependencies: ["SpektrafilmMacCore"]
        ),
        .target(name: "SpektrafilmMacCore"),
        .testTarget(
            name: "SpektrafilmMacCoreTests",
            dependencies: ["SpektrafilmMacCore"]
        )
    ]
)
