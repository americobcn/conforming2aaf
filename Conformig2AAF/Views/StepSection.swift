import SwiftUI

/// One numbered step of the left column.
struct StepSection<Content: View>: View {
    let number: Int
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label {
                Text(title).font(.headline)
            } icon: {
                Text("\(number)")
                    .font(.caption.bold())
                    .frame(width: 20, height: 20)
                    .background(.tint, in: .circle)
                    .foregroundStyle(.white)
            }
            content
        }
    }
}
