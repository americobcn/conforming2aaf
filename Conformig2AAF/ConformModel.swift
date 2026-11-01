import Foundation
import Observation

/// State of one conform job: inputs, options, engine report and export.
@Observable
final class ConformModel {
    static let frameRates = ["23.976", "24", "25", "29.97", "29.97DF", "30", "50", "59.94", "59.94DF", "60"]
    static let sampleRates = [44100, 48000, 88200, 96000]

    enum MediaMode: String, CaseIterable, Identifiable {
        case link, copy, embed
        var id: Self { self }
        var label: String {
            switch self {
            case .link: "Enlazar a los originales"
            case .copy: "Copiar junto al AAF"
            case .embed: "Embeber en el AAF"
            }
        }
    }

    var inputURL: URL?
    var mediaFolders: [URL] = []
    var includeSubfolders = true
    var fps = "25"
    var startTC = ""
    var sampleRate = 48000
    var mediaMode = MediaMode.link
    var splitMono = true
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
        var args = ["--out", url.path, "--sample-rate", String(sampleRate), "--media-mode", mediaMode.rawValue]
        if splitMono || mediaMode == .embed { args.append("--split-mono") }
        await run(["convert"] + baseArguments() + args)
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
                    var text = "AAF exportado: \(r.clipsWritten) clips, \(r.clipsSkipped) omitidos"
                    if r.mediaFiles > 0 {
                        let size = ByteCountFormatter.string(fromByteCount: Int64(r.mediaBytes), countStyle: .file)
                        text += r.mediaDir == nil ? ". \(r.mediaFiles) ficheros embebidos (\(size))"
                                                  : ". \(r.mediaFiles) ficheros de audio (\(size)) en la carpeta de medios"
                    }
                    status = text
                case .error(let message): errorMessage = message; status = ""
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
