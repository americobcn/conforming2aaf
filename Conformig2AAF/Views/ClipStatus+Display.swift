import SwiftUI

/// How each clip status is shown: name, symbol and color.
extension ClipStatus {
    var singular: String {
        switch self {
        case .matched: "Enlazado"
        case .ambiguous: "Dudoso"
        case .missing: "No encontrado"
        }
    }

    var plural: String {
        switch self {
        case .matched: "Enlazados"
        case .ambiguous: "Dudosos"
        case .missing: "No encontrados"
        }
    }

    var symbol: String {
        switch self {
        case .matched: "checkmark.circle.fill"
        case .ambiguous: "questionmark.circle.fill"
        case .missing: "xmark.circle.fill"
        }
    }

    var color: Color {
        switch self {
        case .matched: .green
        case .ambiguous: .orange
        case .missing: .red
        }
    }
}
