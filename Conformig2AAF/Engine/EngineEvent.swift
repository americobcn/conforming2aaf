import Foundation

/// One JSON line printed by the Python engine (`conform2aaf` CLI).
nonisolated enum EngineEvent: Sendable {
    case progress(stage: String, message: String)
    case warning(String)
    case report(EngineReport)
    case result(EngineResult)
    case error(String)

    static func decode(line: Data) throws -> EngineEvent {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        struct Head: Decodable { let type: String; let stage: String?; let message: String? }
        let head = try decoder.decode(Head.self, from: line)
        switch head.type {
        case "progress": return .progress(stage: head.stage ?? "", message: head.message ?? "")
        case "warning": return .warning(head.message ?? "")
        case "report": return .report(try decoder.decode(EngineReport.self, from: line))
        case "result": return .result(try decoder.decode(EngineResult.self, from: line))
        default: return .error(head.message ?? "Evento desconocido: \(head.type)")
        }
    }
}

nonisolated struct EngineReport: Decodable, Sendable {
    struct TimelineInfo: Decodable, Sendable {
        let name: String
        let rate: String
        let startTc: String?
        let tracks: [TrackInfo]
    }
    struct TrackInfo: Decodable, Sendable {
        let name: String
        let clips: Int
    }
    let timeline: TimelineInfo
    let counts: [String: Int]
    let clips: [ClipRow]
}

nonisolated struct ClipRow: Decodable, Identifiable, Hashable, Sendable {
    let id: String
    let track: String
    let name: String
    let recordIn: String?
    let recordOut: String?
    let sourceIn: String?
    let channel: Int?
    let status: String
    let note: String
    let file: String?
    let candidates: [String]
}

nonisolated struct EngineResult: Decodable, Sendable {
    let output: String
    let clipsWritten: Int
    let clipsSkipped: Int
    let mediaDir: String?
    let mediaFiles: Int
    let mediaBytes: Int
}
