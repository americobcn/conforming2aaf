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

            Picker("Frecuencia de muestreo", selection: $model.sampleRate) {
                ForEach(ConformModel.sampleRates, id: \.self) { Text("\($0) Hz") }
            }
        }
        .formStyle(.columns)
    }
}
