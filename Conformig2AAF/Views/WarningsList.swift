import SwiftUI

/// Engine warnings, collapsed. Lazy because the engine can emit hundreds.
struct WarningsList: View {
    let warnings: [String]

    var body: some View {
        DisclosureGroup("^[\(warnings.count) aviso](inflect: true)") {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(warnings.enumerated()), id: \.offset) { Text($0.element) }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
            }
            .frame(maxHeight: 120)
        }
    }
}
