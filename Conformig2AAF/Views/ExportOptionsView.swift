import SwiftUI

/// Step 3: frame rate (EDL only), start timecode and session sample rate.
struct ExportOptionsView: View {
    @Bindable var model: ConformModel

    var body: some View {
        Form {
            Picker("Fotogramas", selection: $model.fps) {
                ForEach(ConformModel.frameRates, id: \.self) { Text($0) }
            }
            .disabled(!model.isEDL)
            .help(model.isEDL ? "La EDL no indica la velocidad" : "XML y FCPXML ya indican la velocidad")

            TextField("TC de inicio", text: $model.startTC, prompt: Text("El de la lista"))
                .help("Opcional, p. ej. 00:59:50:00")

            Picker("Lista de imagen", selection: $model.pictureMode) {
                ForEach(ConformModel.PictureMode.allCases) { Text($0.label).tag($0) }
            }
            .help("Una lista solo con cortes de imagen se concilia con el sonido directo de cada corte, enlazado por TC y por escena, toma y cinta. Automático lo detecta si la lista no tiene audio.")

            Picker("Frecuencia de muestreo", selection: $model.sampleRate) {
                ForEach(ConformModel.sampleRates, id: \.self) { Text("\($0) Hz") }
            }

            Picker("Medios", selection: $model.mediaMode) {
                ForEach(ConformModel.MediaMode.allCases) { Text($0.label).tag($0) }
            }
            .help("Copiar crea la carpeta '<nombre> Media' junto al AAF. Embeber guarda el audio dentro del AAF (solo PCM 16/24 bits).")

            Toggle("Partir polifónicos a mono", isOn: Binding(
                get: { model.splitMono || model.mediaMode == .embed },
                set: { model.splitMono = $0 }
            ))
            .disabled(model.mediaMode == .embed)
            .help(model.mediaMode == .embed ? "Al embeber siempre se parte a mono"
                                            : "Un WAV mono por canal usado, con los metadatos del original")
        }
        .formStyle(.columns)
    }
}
