import SwiftUI

/// Review: every clip of the edit list and the production file it links to.
struct MatchReportView: View {
    let model: ConformModel
    @State private var filter = Filter.all

    enum Filter: String, CaseIterable, Identifiable {
        case all = "Todos", matched = "Enlazados", ambiguous = "Dudosos", missing = "No encontrados"
        var id: Self { self }
        var status: String? {
            switch self {
            case .all: nil
            case .matched: "matched"
            case .ambiguous: "ambiguous"
            case .missing: "missing"
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let report = model.report {
                header(report)
                Table(rows(report)) {
                    TableColumn("") { row in StatusIcon(status: row.status) }.width(22)
                    TableColumn("Pista", value: \.track).width(min: 60, ideal: 90)
                    TableColumn("Clip", value: \.name).width(min: 80, ideal: 140)
                    TableColumn("Entrada") { Text($0.recordIn ?? "–").monospacedDigit() }.width(90)
                    TableColumn("TC origen") { Text($0.sourceIn ?? "–").monospacedDigit() }.width(90)
                    TableColumn("Canal") { Text($0.channel.map(String.init) ?? "–") }.width(44)
                    TableColumn("Fichero") { row in fileCell(row) }.width(min: 160, ideal: 260)
                }
            } else {
                ContentUnavailableView(
                    model.isRunning ? "Analizando…" : "Sin análisis",
                    systemImage: "waveform",
                    description: Text("Elige una lista de montaje y las carpetas de audio de producción.")
                )
            }
            if let error = model.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            }
            if !model.warnings.isEmpty {
                DisclosureGroup("\(model.warnings.count) avisos") {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(Array(model.warnings.enumerated()), id: \.offset) { Text($0.element) }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                    }
                    .frame(maxHeight: 120)
                }
            }
        }
        .padding(16)
    }

    private func rows(_ report: EngineReport) -> [ClipRow] {
        guard let status = filter.status else { return report.clips }
        return report.clips.filter { $0.status == status }
    }

    private func header(_ report: EngineReport) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(report.timeline.name).font(.title2.bold())
                Text("\(report.timeline.rate) fps · inicio \(report.timeline.startTc ?? "–") · \(report.timeline.tracks.count) pistas")
                    .foregroundStyle(.secondary)
                Spacer()
                if model.isRunning { ProgressView().controlSize(.small) }
            }
            HStack(spacing: 16) {
                count("matched", "Enlazados", .green, report)
                count("ambiguous", "Dudosos", .orange, report)
                count("missing", "No encontrados", .red, report)
                Spacer()
                Picker("Mostrar", selection: $filter) {
                    ForEach(Filter.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 380)
            }
        }
    }

    private func count(_ key: String, _ label: String, _ color: Color, _ report: EngineReport) -> some View {
        Label("\(report.counts[key] ?? 0) \(label)", systemImage: "circle.fill")
            .foregroundStyle(color)
            .labelStyle(.titleAndIcon)
    }

    @ViewBuilder
    private func fileCell(_ row: ClipRow) -> some View {
        if row.status == "ambiguous", !row.candidates.isEmpty {
            Menu("Elegir fichero (\(row.candidates.count))") {
                ForEach(row.candidates, id: \.self) { path in
                    Button(path) { model.choose(path, for: row.id) }
                }
            }
            .help(row.note)
        } else if let file = row.file {
            Text(URL(fileURLWithPath: file).lastPathComponent)
                .help(row.note.isEmpty ? file : "\(file)\n\(row.note)")
        } else {
            Text(row.note).foregroundStyle(.secondary)
        }
    }
}

private struct StatusIcon: View {
    let status: String

    var body: some View {
        switch status {
        case "matched": Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case "ambiguous": Image(systemName: "questionmark.circle.fill").foregroundStyle(.orange)
        default: Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
        }
    }
}
