import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Step 1: drop or pick the EDL / Premiere XML / FCPXML.
struct DropZoneView: View {
    let model: ConformModel
    @State private var isTargeted = false

    private static let exts: Set<String> = ["edl", "xml", "fcpxml", "fcpxmld"]

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: model.inputURL == nil ? "doc.badge.plus" : "doc.text")
                .font(.system(size: 28))
                .foregroundStyle(.secondary)
            if let url = model.inputURL {
                Text(url.lastPathComponent).font(.headline).lineLimit(1).truncationMode(.middle)
            } else {
                Text("Suelta aquí una EDL, XML de Premiere o FCPXML").multilineTextAlignment(.center)
            }
            Button(model.inputURL == nil ? "Elegir…" : "Cambiar…", action: pick)
        }
        .frame(maxWidth: .infinity, minHeight: 120)
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [6]))
                .foregroundStyle(isTargeted ? Color.accentColor : Color.secondary.opacity(0.5))
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first(where: { Self.exts.contains($0.pathExtension.lowercased()) }) else { return false }
            model.setInput(url)
            return true
        } isTargeted: { isTargeted = $0 }
    }

    private func pick() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = Self.exts.compactMap { UTType(filenameExtension: $0) }
        panel.canChooseDirectories = true  // .fcpxmld is a bundle folder
        panel.treatsFilePackagesAsDirectories = false
        guard panel.runModal() == .OK, let url = panel.url,
              Self.exts.contains(url.pathExtension.lowercased()) else { return }
        model.setInput(url)
    }
}
