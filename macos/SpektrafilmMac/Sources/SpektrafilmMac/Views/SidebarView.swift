import SpektrafilmMacCore
import SwiftUI

public struct SidebarView: View {
    @Binding private var selection: WorkflowSection?

    public init(selection: Binding<WorkflowSection?>) {
        self._selection = selection
    }

    public var body: some View {
        List(selection: $selection) {
            ForEach(WorkflowSection.allCases) { section in
                HStack(spacing: 10) {
                    Image(systemName: section.systemImage)
                        .foregroundStyle(.secondary)
                        .frame(width: 16)
                    Text(section.title)
                        .lineLimit(1)
                }
                .tag(section)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Spektrafilm")
    }
}
