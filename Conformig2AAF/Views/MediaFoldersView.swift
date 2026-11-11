import AppKit
import SwiftUI

/// Step 2: folders that hold the production audio.
struct MediaFoldersView: View {
    @Bindable var model: ConformModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.mediaFolders.isEmpty {
                Text("Añade las carpetas con el audio de producción (WAV/BWF).")
                    .foregroundStyle(.secondary)
            }
            ForEach(model.mediaFolders, id: \.self) { folder in
                HStack {
                    Image(systemName: "folder")
                    Text(folder.path).lineLimit(1).truncationMode(.head)
                    Spacer()
                    Button("Quitar carpeta", systemImage: "minus.circle") {
                        model.mediaFolders.removeAll { $0 == folder }
                    }
                    .labelStyle(.iconOnly)
                    .buttonStyle(.borderless)
                    .help("Quitar carpeta")
                }
            }
            HStack {
                Button("Añadir carpeta…", action: pick)
                Spacer()
                Toggle("Incluir subcarpetas", isOn: $model.includeSubfolders)
            }
        }
        .dropDestination(for: URL.self) { urls, _ in
            let dirs = urls.filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true }
            model.addMediaFolders(dirs)
            return !dirs.isEmpty
        }
    }

    private func pick() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = true
        guard panel.runModal() == .OK else { return }
        model.addMediaFolders(panel.urls)
    }
}
