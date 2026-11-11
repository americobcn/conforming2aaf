//
//  ContentView.swift
//  Conformig2AAF
//
//  Created by Américo Cot on 1/11/26.
//

import SwiftUI

struct ContentView: View {
    @State private var model = ConformModel()

    var body: some View {
        HSplitView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Group {
                        StepSection(number: 1, title: "Lista de montaje") { DropZoneView(model: model) }
                        StepSection(number: 2, title: "Audio de producción") { MediaFoldersView(model: model) }
                        StepSection(number: 3, title: "Opciones") { ExportOptionsView(model: model) }
                    }
                    .disabled(model.isExporting)
                    StepSection(number: 4, title: "Exportar") { ExportSection(model: model) }
                }
                .padding(20)
            }
            .frame(minWidth: 340, idealWidth: 380, maxWidth: 400)

            MatchReportView(model: model)
                .frame(minWidth: 600, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 980, minHeight: 620)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Nueva importación", systemImage: "arrow.counterclockwise") { model.reset() }
                    .keyboardShortcut("n", modifiers: [.command, .shift])
                    .help("Vacía la lista, las carpetas y el análisis para empezar de nuevo (⇧⌘N)")
                    .disabled(!model.hasWork || model.isRunning)
            }
        }
        .task(id: model.inspectKey) {
            if model.canInspect { await model.inspect() }
        }
    }
}

#Preview {
    ContentView()
}
