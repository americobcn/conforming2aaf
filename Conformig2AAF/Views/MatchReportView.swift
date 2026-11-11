import SwiftUI

/// Review: every clip of the edit list and the production file it links to.
struct MatchReportView: View {
    let model: ConformModel
    @State private var filter = ReportFilter.all

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let report = model.report {
                ReportHeader(report: report, isRunning: model.isRunning, filter: $filter)
                Table(rows(report)) {
                    TableColumn("") { row in StatusIcon(status: row.status) }.width(22)
                    TableColumn("Pista", value: \.track).width(min: 20, ideal: 30, max: 80)
                    TableColumn("Clip", value: \.name).width(min: 80, ideal: 140)
                    TableColumn("Entrada") { Text($0.recordIn ?? "–").monospacedDigit() }.width(90)
                    TableColumn("TC origen") { Text($0.sourceIn ?? "–").monospacedDigit() }.width(90)
                    TableColumn("Escena") { Text($0.scene ?? "") }.width(min: 40, ideal: 40, max: 70)
                    TableColumn("Toma") { Text($0.take ?? "") }.width(min: 40, ideal: 40, max: 50)
                    TableColumn("Canal") { Text($0.channel.map(String.init) ?? "–") }.width(40)
                    TableColumn("Fichero") { row in ClipFileCell(row: row, model: model) }.width(min: 160, ideal: 260)
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
                WarningsList(warnings: model.warnings)
            }
        }
        .padding(16)
    }

    private func rows(_ report: EngineReport) -> [ClipRow] {
        guard let status = filter.status else { return report.clips }
        return report.clips.filter { $0.status == status }
    }
}
