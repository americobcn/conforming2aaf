import SwiftUI

/// How many clips have one status. Singular and plural are given by hand:
/// automatic inflection reads «enlazado» as a verb.
struct StatusCount: View {
    let status: ClipStatus
    let count: Int

    var body: some View {
        Label("\(count) \(count == 1 ? status.singular : status.plural)", systemImage: "circle.fill")
            .foregroundStyle(status.color)
            .labelStyle(.titleAndIcon)
    }
}
