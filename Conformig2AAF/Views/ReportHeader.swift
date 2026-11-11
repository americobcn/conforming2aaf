import SwiftUI

/// Above the link table: timeline name and rate, counts per status and the filter.
struct ReportHeader: View {
    let report: EngineReport
    let isRunning: Bool
    @Binding var filter: ReportFilter

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(report.timeline.name).font(.title2.bold())
                Text("\(report.timeline.rate) fps · inicio \(report.timeline.startTc ?? "–") · ^[\(report.timeline.tracks.count) pista](inflect: true)")
                    .foregroundStyle(.secondary)
                Spacer()
                if isRunning { ProgressView().controlSize(.small) }
            }
            if report.timeline.picture == true {
                Label("Lista de imagen: se concilia el sonido directo de cada corte, todos los canales", systemImage: "film")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 16) {
                ForEach(ClipStatus.allCases, id: \.self) { status in
                    StatusCount(status: status, count: report.count(of: status))
                }
                Spacer()
                Picker("Mostrar", selection: $filter) {
                    ForEach(ReportFilter.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 380)
            }
        }
    }
}
