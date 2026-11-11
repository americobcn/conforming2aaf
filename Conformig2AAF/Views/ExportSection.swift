import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Step 4: analyse again, export the AAF and show it in Finder.
struct ExportSection: View {
    let model: ConformModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Button("Volver a analizar", action: model.requestAnalysis)
                    .disabled(!model.canInspect || model.isRunning)
                Spacer()
                Button("Exportar AAF…", action: export)
                    .keyboardShortcut("e")
                    .buttonStyle(.borderedProminent)
                    .disabled(!model.canExport)
            }
            if !model.status.isEmpty {
                Text(model.status).font(.callout).foregroundStyle(.secondary)
            }
            if model.lastOutput != nil {
                Button("Mostrar en Finder", action: showInFinder)
                    .buttonStyle(.link)
            }
        }
    }

    private func showInFinder() {
        guard let out = model.lastOutput else { return }
        NSWorkspace.shared.activateFileViewerSelecting([out])
    }

    private func export() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "aaf") ?? .data]
        let stem = model.inputURL?.deletingPathExtension().lastPathComponent ?? "Conform"
        panel.nameFieldStringValue = "\(stem).aaf"
        panel.message = "Si ya existe un AAF con ese nombre no se sobrescribe: se añade la fecha y hora al nombre."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let target = ConformModel.uniqueOutputURL(url)
        Task { await model.convert(to: target) }
    }
}
