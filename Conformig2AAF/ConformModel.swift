import Foundation
import Observation

/// State of one conform job: inputs, options, engine report and export.
@Observable
final class ConformModel {
    static let frameRates = ["23.976", "24", "25", "29.97", "29.97DF", "30", "50", "59.94", "59.94DF", "60"]
    static let sampleRates = [44100, 48000, 88200, 96000]

    var inputURL: URL?
    var mediaFolders: [URL] = []
    var includeSubfolders = true
    var fps = "25"
    var startTC = ""
    var sampleRate = 48000
    var choices: [String: String] = [:]  // clip id -> chosen file path

    var report: EngineReport?
    var warnings: [String] = []
    var status = ""
    var errorMessage: String?
    var isRunning = false
    var lastOutput: URL?

    var isEDL: Bool { inputURL?.pathExtension.lowercased() == "edl" }
    var canInspect: Bool { inputURL != nil && !mediaFolders.isEmpty }
    var canExport: Bool { canInspect && !isRunning && (report?.counts["matched"] ?? 0) > 0 }

    /// Changes that require a new analysis.
    var inspectKey: String {
        let picks = choices.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }
        return ([inputURL?.path ?? "", "\(includeSubfolders)", isEDL ? fps : ""]
                + mediaFolders.map(\.path) + picks).joined(separator: "|")
    }

    func setInput(_ url: URL) {
        inputURL = url
        choices = [:]
        report = nil
        lastOutput = nil
    }

    func addMediaFolders(_ urls: [URL]) {
        for url in urls where !mediaFolders.contains(url) {
            mediaFolders.append(url)
        }
    }

    func choose(_ path: String, for clipID: String) {
        choices[clipID] = path
    }

    func inspect() async {
        await run(["inspect"] + baseArguments())
    }

    func convert(to url: URL) async {
        await run(["convert"] + baseArguments() + ["--out", url.path, "--sample-rate", String(sampleRate)])
    }

    private func baseArguments() -> [String] {
        guard let input = inputURL else { return [] }
        var args = [input.path]
        for folder in mediaFolders { args += ["--media", folder.path] }
        if !includeSubfolders { args.append("--no-recursive") }
        if isEDL { args += ["--fps", fps] }
        let tc = startTC.trimmingCharacters(in: .whitespaces)
        if !tc.isEmpty { args += ["--start-tc", tc] }
        for (id, path) in choices.sorted(by: { $0.key < $1.key }) { args += ["--choose", "\(id)=\(path)"] }
        return args
    }

    private func run(_ args: [String]) async {
        isRunning = true
        errorMessage = nil
        warnings = []
        defer { isRunning = false }
        do {
            for try await event in try EngineClient.locate().run(args) {
                switch event {
                case .progress(_, let message): status = message
                case .warning(let message): warnings.append(message)
                case .report(let r): report = r; status = "Análisis completado"
                case .result(let r):
                    lastOutput = URL(fileURLWithPath: r.output)
                    status = "AAF exportado: \(r.clipsWritten) clips, \(r.clipsSkipped) omitidos"
                case .error(let message): errorMessage = message; status = ""
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
