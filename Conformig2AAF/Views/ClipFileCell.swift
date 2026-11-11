import SwiftUI

/// File column of the link table: the linked file, or a menu to choose one when it's doubtful.
struct ClipFileCell: View {
    let row: ClipRow
    let model: ConformModel

    var body: some View {
        if row.status == .ambiguous, !row.candidates.isEmpty {
            Menu("Elegir fichero (\(row.candidates.count))") {
                ForEach(row.candidates, id: \.self) { path in
                    Button(path) { model.choose(path, for: row.id) }
                }
            }
            .help(row.note)
            .disabled(model.isExporting)
        } else if let file = row.file {
            Text(URL(fileURLWithPath: file).lastPathComponent)
                .help(row.note.isEmpty ? file : "\(file)\n\(row.note)")
        } else {
            Text(row.note).foregroundStyle(.secondary)
        }
    }
}
