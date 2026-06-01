import SpektrafilmMacCore
import SwiftUI

public struct InspectorView: View {
    @ObservedObject private var model: SpektrafilmAppModel

    public init(model: SpektrafilmAppModel) {
        self.model = model
    }

    public var body: some View {
        Form {
            Section("Profiles") {
                Picker("Film", selection: $model.configuration.filmStock) {
                    ForEach(model.catalog.filmProfiles, id: \.self) { profile in
                        Text(profile).tag(profile)
                    }
                }
                Picker("Print", selection: $model.configuration.printPaper) {
                    ForEach(model.catalog.printProfiles, id: \.self) { profile in
                        Text(profile).tag(profile)
                    }
                }
                Toggle("Scan film", isOn: $model.configuration.scanFilm)
            }

            Section("Color") {
                Picker("Input", selection: $model.configuration.inputColorSpace) {
                    ForEach(model.catalog.colorSpaces, id: \.self) { colorSpace in
                        Text(colorSpace).tag(colorSpace)
                    }
                }
                Toggle("Decode input CCTF", isOn: $model.configuration.applyCCTFDecoding)
                Picker("Output", selection: $model.configuration.outputColorSpace) {
                    ForEach(model.catalog.colorSpaces, id: \.self) { colorSpace in
                        Text(colorSpace).tag(colorSpace)
                    }
                }
                Picker("Saving", selection: $model.configuration.savingColorSpace) {
                    ForEach(model.catalog.colorSpaces, id: \.self) { colorSpace in
                        Text(colorSpace).tag(colorSpace)
                    }
                }
            }

            Section("Exposure") {
                Toggle("Auto exposure", isOn: $model.configuration.autoExposure)
                Stepper(value: $model.configuration.exposureCompensationEV, in: -6...6, step: 0.25) {
                    LabeledContent("Camera EV", value: model.configuration.exposureCompensationEV, format: .number.precision(.fractionLength(2)))
                }
                Stepper(value: $model.configuration.printExposure, in: 0...4, step: 0.02) {
                    LabeledContent("Print exposure", value: model.configuration.printExposure, format: .number.precision(.fractionLength(2)))
                }
                Stepper(value: $model.configuration.printYFilterShift, in: -100...100, step: 1) {
                    LabeledContent("Y filter", value: model.configuration.printYFilterShift, format: .number.precision(.fractionLength(0)))
                }
                Stepper(value: $model.configuration.printMFilterShift, in: -100...100, step: 1) {
                    LabeledContent("M filter", value: model.configuration.printMFilterShift, format: .number.precision(.fractionLength(0)))
                }
            }

            Section("Effects") {
                Toggle("Grain", isOn: $model.configuration.grainActive)
                Toggle("Halation", isOn: $model.configuration.halationActive)
                Toggle("Couplers", isOn: $model.configuration.couplersActive)
            }

            Section("Compute") {
                Picker("Backend", selection: $model.configuration.computeBackend) {
                    ForEach(model.catalog.computeBackends, id: \.self) { backend in
                        Text(backend).tag(backend)
                    }
                }
                Picker("Precision", selection: $model.configuration.gpuPrecision) {
                    ForEach(model.catalog.gpuPrecisions, id: \.self) { precision in
                        Text(precision).tag(precision)
                    }
                }
                Stepper(value: $model.configuration.previewMaxSize, in: 256...2048, step: 128) {
                    LabeledContent("Preview edge", value: "\(model.configuration.previewMaxSize) px")
                }
            }
        }
        .formStyle(.grouped)
        .frame(minWidth: 280)
        .padding(.vertical, 6)
    }
}
