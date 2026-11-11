/// Which clips the link table shows.
enum ReportFilter: CaseIterable, Identifiable {
    case all, matched, ambiguous, missing

    var id: Self { self }

    var status: ClipStatus? {
        switch self {
        case .all: nil
        case .matched: .matched
        case .ambiguous: .ambiguous
        case .missing: .missing
        }
    }

    var label: String { status?.plural ?? "Todos" }
}
