import SwiftUI

/// Status of one clip in the link table.
struct StatusIcon: View {
    let status: ClipStatus

    var body: some View {
        Image(systemName: status.symbol)
            .foregroundStyle(status.color)
            .accessibilityLabel(status.singular)
    }
}
