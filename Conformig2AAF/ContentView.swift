//
//  ContentView.swift
//  Conformig2AAF
//
//  Created by Américo Cot on 1/11/26.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var model = ConformModel()

    var body: some View {
        HSplitView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    step(1, "Lista de montaje") { DropZoneView(model: model) }
                    step(2, "Audio de producción") { MediaFoldersView(model: model) }
                    step(3, "Opciones") { ExportOptionsView(model: model) }
                    step(4, "Exportar") { exportSection }
                }
                .padding(20)
            }
            .frame(minWidth: 340, idealWidth: 380, maxWidth: 460)

            MatchReportView(model: model)
                .frame(minWidth: 600, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 980, minHeight: 620)
        .task(id: model.inspectKey) {
            if model.canInspect { await model.inspect() }
        }
    }

    private func step<Content: View>(_ n: Int, _ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label {
                Text(title).font(.headline)
            } icon: {
                Text("\(n)")
                    .font(.caption.bold())
                    .frame(width: 20, height: 20)
                    .background(.tint, in: .circle)
                    .foregroundStyle(.white)
            }
            content()
        }
    }

    private var exportSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Button("Volver a analizar") { Task { await model.inspect() } }
                    .disabled(!model.canInspect || model.isRunning)
                Spacer()
                Button("Exportar AAF…", action: export)
                    .keyboardShortcut("e")
                    .buttonStyle(.borderedProminent)
                    .disabled(!model.canExport)
            }
            if !model.status.isEmpty {
                Text(model.status).font(.callout).foregroundStyle(.secondary)
            }
            if let out = model.lastOutput {
                Button("Mostrar en Finder") { NSWorkspace.shared.activateFileViewerSelecting([out]) }
                    .buttonStyle(.link)
            }
        }
    }

    private func export() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "aaf") ?? .data]
        let stem = model.inputURL?.deletingPathExtension().lastPathComponent ?? "Conform"
        panel.nameFieldStringValue = "\(stem).aaf"
        panel.message = "Si ya existe un AAF con ese nombre no se sobrescribe: se añade la fecha y hora al nombre."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let target = ConformModel.uniqueOutputURL(url)
        Task { await model.convert(to: target) }
    }
}

#Preview {
    ContentView()
}
