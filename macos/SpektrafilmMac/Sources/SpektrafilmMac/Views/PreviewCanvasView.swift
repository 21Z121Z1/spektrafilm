import AppKit
import SpektrafilmMacCore
import SwiftUI

public struct PreviewCanvasView: View {
    @ObservedObject private var model: SpektrafilmAppModel

    public init(model: SpektrafilmAppModel) {
        self.model = model
    }

    public var body: some View {
        ZStack(alignment: .bottom) {
            previewSurface
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            LiquidGlassPanel {
                HStack(spacing: 8) {
                    Button {
                        model.selectInputFile()
                    } label: {
                        Label("Import", systemImage: "photo.badge.plus")
                    }

                    Button {
                        Task { await model.renderPreview() }
                    } label: {
                        Label("Preview", systemImage: "play.rectangle")
                    }
                    .disabled(!model.canRender)

                    Button {
                        Task { await model.renderScanWithSavePanel() }
                    } label: {
                        Label("Scan", systemImage: "film.stack")
                    }
                    .disabled(!model.canSave)

                    Divider()
                        .frame(height: 20)

                    Label(model.statusText, systemImage: model.isRendering ? "hourglass" : "checkmark.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .frame(maxWidth: 360, alignment: .leading)
                }
                .controlSize(.small)
            }
            .padding(14)
        }
    }

    @ViewBuilder
    private var previewSurface: some View {
        if let image = model.previewImage {
            Image(nsImage: image)
                .resizable()
                .interpolation(.high)
                .scaledToFit()
                .padding(18)
        } else {
            VStack(spacing: 10) {
                Image(systemName: "photo.on.rectangle.angled")
                    .font(.system(size: 44, weight: .light))
                    .foregroundStyle(.secondary)
                Text("No Image Loaded")
                    .font(.title3)
            }
            .frame(maxWidth: 420)
        }
    }
}
