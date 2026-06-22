import Foundation
import CoreImage
import ImageIO

enum EncoderError: Error, CustomStringConvertible {
    case usage
    case badInteger(String)
    case badFloat(String)
    case unsupportedColorSpace(String)
    case badInputSize(label: String, expected: Int, actual: Int)
    case representationFailed
    case writeFailed(String)

    var description: String {
        switch self {
        case .usage:
            return "usage: hdr_heif_encoder.swift <sdr-rgba-f32-raw> <hdr-rgba-f32-raw> <output.heic> <width> <height> <color-space> <headroom> <quality> [gain-map-mode]"
        case .badInteger(let value):
            return "invalid integer argument: \(value)"
        case .badFloat(let value):
            return "invalid float argument: \(value)"
        case .unsupportedColorSpace(let name):
            return "unsupported HEIC HDR color space: \(name)"
        case .badInputSize(let label, let expected, let actual):
            return "\(label) raw RGBA float payload has \(actual) bytes; expected \(expected)"
        case .representationFailed:
            return "CoreImage failed to create HEIF HDR representation"
        case .writeFailed(let message):
            return "failed to write HEIF output: \(message)"
        }
    }
}

func parseInt(_ value: String) throws -> Int {
    guard let parsed = Int(value), parsed > 0 else {
        throw EncoderError.badInteger(value)
    }
    return parsed
}

func parseFloat(_ value: String) throws -> Float {
    guard let parsed = Float(value), parsed.isFinite else {
        throw EncoderError.badFloat(value)
    }
    return parsed
}

func encodedColorSpace(named name: String) -> CGColorSpace? {
    switch name {
    case "sRGB":
        return CGColorSpace(name: CGColorSpace.sRGB)
    case "Display P3":
        return CGColorSpace(name: CGColorSpace.displayP3)
    case "ITU-R BT.2020":
        return CGColorSpace(name: CGColorSpace.itur_2020)
    default:
        return nil
    }
}

func linearColorSpace(named name: String) -> CGColorSpace? {
    switch name {
    case "sRGB":
        return CGColorSpace(name: CGColorSpace.extendedLinearSRGB)
    case "Display P3":
        return CGColorSpace(name: CGColorSpace.extendedLinearDisplayP3)
    case "ITU-R BT.2020":
        return CGColorSpace(name: CGColorSpace.extendedLinearITUR_2020)
    default:
        return nil
    }
}

func main() throws {
    guard CommandLine.arguments.count == 9 || CommandLine.arguments.count == 10 else {
        throw EncoderError.usage
    }

    let sdrInputURL = URL(fileURLWithPath: CommandLine.arguments[1])
    let hdrInputURL = URL(fileURLWithPath: CommandLine.arguments[2])
    let outputURL = URL(fileURLWithPath: CommandLine.arguments[3])
    let width = try parseInt(CommandLine.arguments[4])
    let height = try parseInt(CommandLine.arguments[5])
    let colorSpaceName = CommandLine.arguments[6]
    let headroom = try parseFloat(CommandLine.arguments[7])
    let quality = max(0.0, min(1.0, try parseFloat(CommandLine.arguments[8])))

    let gainMapMode = CommandLine.arguments.count > 9 ? CommandLine.arguments[9] : "rgb"
    if gainMapMode != "luma" && gainMapMode != "rgb" {
        throw EncoderError.usage
    }
    let useRGBGainMap = (gainMapMode == "rgb")

    guard let encodedColorSpace = encodedColorSpace(named: colorSpaceName),
          let linearColorSpace = linearColorSpace(named: colorSpaceName) else {
        throw EncoderError.unsupportedColorSpace(colorSpaceName)
    }

    let sdrData = try Data(contentsOf: sdrInputURL, options: .mappedIfSafe)
    let hdrData = try Data(contentsOf: hdrInputURL, options: .mappedIfSafe)
    let expectedSize = width * height * 4 * MemoryLayout<Float>.size
    guard sdrData.count == expectedSize else {
        throw EncoderError.badInputSize(label: "SDR", expected: expectedSize, actual: sdrData.count)
    }
    guard hdrData.count == expectedSize else {
        throw EncoderError.badInputSize(label: "HDR", expected: expectedSize, actual: hdrData.count)
    }

    let size = CGSize(width: width, height: height)
    let bytesPerRow = width * 4 * MemoryLayout<Float>.size
    let sdrImage = CIImage(
        bitmapData: sdrData,
        bytesPerRow: bytesPerRow,
        size: size,
        format: .RGBAf,
        colorSpace: linearColorSpace
    ).settingContentHeadroom(1.0)
    let hdrImage = CIImage(
        bitmapData: hdrData,
        bytesPerRow: bytesPerRow,
        size: size,
        format: .RGBAf,
        colorSpace: linearColorSpace
    ).settingContentHeadroom(headroom)

    let context = CIContext(options: [
        .workingColorSpace: linearColorSpace,
        .outputColorSpace: encodedColorSpace,
    ])
    let options: [CIImageRepresentationOption: Any] = [
        CIImageRepresentationOption.hdrImage: hdrImage,
        CIImageRepresentationOption.hdrGainMapAsRGB: useRGBGainMap,
        kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: quality,
    ]

    guard let representation = context.heifRepresentation(
        of: sdrImage,
        format: .RGBA8,
        colorSpace: encodedColorSpace,
        options: options
    ) else {
        throw EncoderError.representationFailed
    }

    do {
        try representation.write(to: outputURL, options: [.atomic])
    } catch {
        throw EncoderError.writeFailed(error.localizedDescription)
    }
}

do {
    try main()
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
