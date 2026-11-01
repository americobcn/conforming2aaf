import Foundation

nonisolated enum EngineError: LocalizedError {
    case notFound(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let path): "No se encuentra el motor de conversión en \(path)"
        }
    }
}

/// Runs the bundled Python engine and streams its JSON-line events.
nonisolated struct EngineClient: Sendable {
    let python: URL
    let environment: [String: String]

    /// Bundled engine, or the repo's venv when `CONFORM2AAF_ENGINE` points at `engine/`.
    static func locate() throws -> EngineClient {
        var env = ProcessInfo.processInfo.environment
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if let dev = env["CONFORM2AAF_ENGINE"], !dev.isEmpty {
            let py = URL(fileURLWithPath: dev).appendingPathComponent(".venv/bin/python")
            guard FileManager.default.isExecutableFile(atPath: py.path) else { throw EngineError.notFound(py.path) }
            return EngineClient(python: py, environment: env)
        }
        let root = Bundle.main.resourceURL!.appendingPathComponent("engine")
        let py = root.appendingPathComponent("python/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: py.path) else { throw EngineError.notFound(py.path) }
        env["PYTHONPATH"] = root.appendingPathComponent("lib").path
        return EngineClient(python: py, environment: env)
    }

    func run(_ arguments: [String]) -> AsyncThrowingStream<EngineEvent, Error> {
        AsyncThrowingStream { continuation in
            let process = Process()
            process.executableURL = python
            process.arguments = ["-m", "conform2aaf"] + arguments
            process.environment = environment
            let out = Pipe()
            let err = Pipe()
            process.standardOutput = out
            process.standardError = err

            let task = Task.detached {
                do {
                    try process.run()
                    let stderrTask = Task.detached { err.fileHandleForReading.readDataToEndOfFile() }
                    for try await line in out.fileHandleForReading.bytes.lines {
                        guard let data = line.data(using: .utf8), !data.isEmpty else { continue }
                        if let event = try? EngineEvent.decode(line: data) {
                            continuation.yield(event)
                        }
                    }
                    process.waitUntilExit()
                    let stderr = String(decoding: await stderrTask.value, as: UTF8.self)
                    if process.terminationStatus != 0, !stderr.isEmpty {
                        continuation.yield(.error(String(stderr.suffix(800))))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in
                task.cancel()
                if process.isRunning { process.terminate() }
            }
        }
    }
}
