import Foundation

/// How a clip of the edit list was linked to a production sound file.
nonisolated enum ClipStatus: String, CaseIterable, Decodable, Sendable {
    case matched, ambiguous, missing

    /// Any other value (the engine's default is "unmatched") counts as missing,
    /// so one unexpected status can't make the whole report fail to decode.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ClipStatus(rawValue: raw) ?? .missing
    }
}
