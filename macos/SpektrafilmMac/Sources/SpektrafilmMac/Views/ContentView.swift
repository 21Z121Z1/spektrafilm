import SpektrafilmMacCore
import SwiftUI

public struct ContentView: View {
    @StateObject private var model: SpektrafilmAppModel

    public init(model: SpektrafilmAppModel = SpektrafilmAppModel()) {
        self._model = StateObject(wrappedValue: model)
    }

    public var body: some View {
        NavigationSplitView {
            SidebarView(selection: $model.selectedSection)
        } detail: {
            PreviewCanvasView(model: model)
                .navigationTitle(detailTitle)
                .toolbar {
                    ToolbarItemGroup(placement: .primaryAction) {
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

                        Button {
                            model.isInspectorPresented.toggle()
                        } label: {
                            Label("Inspector", systemImage: "sidebar.right")
                        }
                    }
                }
                .inspector(isPresented: $model.isInspectorPresented) {
                    InspectorView(model: model)
                }
        }
        .frame(minWidth: 1100, minHeight: 720)
    }

    private var detailTitle: String {
        model.inputURL?.lastPathComponent ?? "Spektrafilm"
    }
}
