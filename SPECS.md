# Conformig2AAF — especificaciones

**Propósito:** conformar el audio de producción (WAV/BWF) a partir de una lista de montaje (EDL, XML de Premiere/FCP7, FCPXML) y generar un **AAF** que Pro Tools importa con los clips en su posición exacta (precisión de muestra), enlazados a los WAV y con sus metadatos.

Estado: funcional de punta a punta para listas **con audio** y listas **solo de imagen**. Probado con Pro Tools 26.4.1 (ver §9). Lo que no está hecho está en §11.

## 1. Arquitectura

```
Conformig2AAF.app (SwiftUI, macOS 15.8, arm64)
├─ Conformig2AAF/              interfaz: ConformModel (estado), vistas, EngineClient
│    └─ Process + eventos JSON por líneas (stdout)
└─ Contents/Resources/engine/
     ├─ python/                CPython 3.12.13 relocatable (python-build-standalone, vía uv)
     ├─ lib/                   paquete `conform2aaf` + pyaaf2 1.7.1
     └─ bin/audioconv          ejecutable Swift con AudioToolbox (conversión de muestras)
```

- La app Swift no sabe de formatos: lanza `python -m conform2aaf inspect|convert …` y lee eventos JSON (§8).
- Python lee las listas, enlaza los medios, prepara los WAV (partir, copiar, convertir) y escribe el AAF con pyaaf2.
- `audioconv` solo convierte muestras. Los frameworks de Apple no conservan chunks BWF (`bext`, `iXML`, `axml`), así que **el contenedor WAV lo monta siempre Python** y copia todos los chunks.
- Sin sandbox (`ENABLE_APP_SANDBOX = NO`): el motor es un proceso hijo que lee carpetas arbitrarias. Distribución fuera de la App Store.

## 2. Stack tecnológico

| Componente | Uso | Detalle |
|---|---|---|
| Swift / SwiftUI | Interfaz | macOS 15.8, Xcode 26.3, `@Observable`, `Table`, `NSOpenPanel`/`NSSavePanel` |
| Python | Motor | 3.12.13 embebido; solo librería estándar salvo pyaaf2 (`struct`, `array`, `xml.etree`, `fractions`…) |
| pyaaf2 | Escritura de AAF | 1.7.1 (única dependencia de Python) |
| AudioToolbox | Conversión float → PCM 24 bits | `ExtAudioFile` (lectura) + `AudioConverter` (conversión), en `tools/audioconv/main.swift` |
| AVFoundation | Previsto | Extraer audio de MOV/MP4 (§11) |
| ffmpeg / numpy / sox | **No se usan** | Decisión: frameworks nativos de Apple para procesar audio |

## 3. Flujo de la aplicación

Ventana con dos paneles: pasos a la izquierda, tabla de enlace a la derecha.

1. **Lista de montaje**: soltar o elegir `.edl`, `.xml` (xmeml o FCPXML), `.fcpxml` o `.fcpxmld`.
2. **Audio de producción**: una o más carpetas (soltar o elegir), opción «Incluir subcarpetas».
3. **Opciones**:
   - *Fotogramas* (solo EDL, que no indica la velocidad): 23.976, 24, 25, 29.97 / 29.97DF, 30, 50, 59.94 / 59.94DF, 60.
   - *TC de inicio* (opcional), *Lista de imagen* (Automático / Sí / No), *Frecuencia de muestreo* (44.1 / 48 / 88.2 / 96 kHz).
   - *Medios*: Enlazar a los originales / Copiar junto al AAF / Embeber en el AAF.
   - *Bajar el nivel de los canales que pasen de 0 dBFS* (activado) y *Partir polifónicos a mono* (activado; bloqueado al embeber).
4. **Exportar**: «Exportar AAF…» (⌘E), «Volver a analizar», «Mostrar en Finder».

- El análisis arranca solo cuando hay lista y al menos una carpeta, y se repite al cambiar lista, carpetas, velocidad, modo de lista de imagen o elecciones manuales.
- **Tabla de enlace**: estado (enlazado / dudoso / no encontrado), pista, clip, entrada, TC origen, escena, toma, canal y fichero. Filtro por estado. En los dudosos, un menú elige el fichero a mano.
- **Nunca sobrescribe**: si el AAF o su carpeta `<nombre> Media` existen, añade `_yyyy-MM-dd_HH-mm-ss` al nombre.
- **Nueva importación** (⇧⌘N, barra de herramientas): vacía lista, carpetas, análisis, avisos y elecciones manuales; conserva las opciones de exportación. Desactivada mientras algo se ejecuta.

## 4. Listas de entrada

Todas producen el mismo modelo (`model.py`): `Timeline` → `Track` → `Clip`, con tiempos como fracciones exactas de segundo.

| Formato | Lector | Qué lee |
|---|---|---|
| EDL CMX3600 | `readers/edl.py` | Eventos de audio (`A`, `A2`, `AA`, `AUD`), `FCM` DF/NDF, reel, `* FROM CLIP NAME`, `* SOURCE FILE`, `* SCENE/TAKE/TAPE`, nivel (`AUDIO LEVEL`), disolvencias (`D`) → crossfade o fundido desde/hacia negro. Cambios de velocidad (`M2`) y *wipes/keys*: aviso. |
| Premiere / FCP7 XML (xmeml) | `readers/xmeml.py` | Pistas de audio y estéreo, `clipitem`, `file`/`pathurl`/timecode, transiciones (alineación centro/inicio/fin), nivel constante (automatización: aviso), pistas y clips desactivados omitidos |
| FCPXML 1.8–1.11 y `.fcpxmld` | `readers/fcpxml.py` | `spine`, `asset-clip`, `clip`, `sync-clip`, `ref-clip`, `mc-clip` (ángulo de audio activo), conectados, roles → pistas, solapes → pistas extra, transiciones, volumen y fundidos; `timeMap`: aviso |

- **Canal de origen en EDL**: la EDL nombra la pista de destino (A3…A6), no el canal de origen. Los eventos simultáneos del mismo fichero y rango toman los canales 1, 2, 3… en el orden de las pistas.
- **Listas de imagen**: si la lista no tiene clips de audio, se pasa a **modo imagen** (automático, o forzado). Cada corte de imagen es un clip sin canal que lleva `reel`, escena, toma y cinta si la lista los trae (EDL `* SCENE/TAKE/TAPE`, xmeml `logginginfo`, FCPXML `md scene/take/reel`). El AAF final tiene una pista por canal del WAV (`picture.py`), nombrada con el iXML (`1 MixL`, `3 BOOM`); los cortes solapados van a pistas `#2`.
- **Timecode** (`timecode.py`): con fotogramas omitidos (29.97 y 59.94 DF), exacto con `Fraction`.

## 5. Enlace clip ↔ fichero (`media/matcher.py`)

Orden de evidencias:

1. **Nombre**: fichero de la lista, nombre del clip o reel igual al nombre del WAV (sin extensión de audio, sin distinguir mayúsculas).
2. **TC**: el rango de TC del clip se solapa con el del WAV (`bext` TimeReference + duración). Se admite solape parcial y se avisa de los fotogramas que faltan. Sin solape: no encontrado.
3. **Fecha** (`clipdate.py`): el nombre del clip trae la fecha (`A001C012_261009_RNU8` → 2026-10-09; también `YYYYMMDD` y `YYYY-MM-DD`); el WAV, la del `bext`. Los ficheros de otro día se **descartan**; si ninguno coincide, el clip queda «no encontrado» con las fechas en la nota.
4. **Hora**: el bloque `HHMMSS` tras la fecha (`A_0002C012_251111_115104_…`). Entre candidatos del mismo día, gana el que estaba grabando (±1 min). Solo desempata.
5. **Cinta**, luego **escena + toma** (normalizadas: `5 12` = `5/12` = `05-12`). Salen del iXML y, si faltan, de la descripción del `bext` (`aSCENE=`, `aTAKE=`, `aTAPE=`). Solo cuentan si existen en ambos lados; un reel de cámara distinto de la cinta de sonido no es un conflicto.
6. Un único candidato con escena/toma contradictoria: **dudoso**. Varios sin resolver: **dudoso**, con el motivo. Sin TC en el clip: enlace por escena/toma (o cinta) solo con acuerdo positivo.

La elección manual en los dudosos llega al motor como `--choose id=ruta`.

## 6. Preparación de medios (`media/prepare.py`, `media/audio.py`)

| Modo | Efecto |
|---|---|
| Enlazar | El AAF apunta a los originales. Con «Partir» activo, los polifónicos se parten a una carpeta de medios |
| Copiar | Carpeta `<nombre> Media` junto al AAF con los ficheros usados (copia exacta, o partidos/convertidos) |
| Embeber | PCM 16/24 mono dentro del AAF (siempre parte a mono; los float se convierten antes) |

- **Partir a mono** (`split_wav`): un WAV por canal usado, `<fichero>_<canal>.wav`. Si dos ficheros distintos tienen el mismo nombre, el segundo pasa a `nombre (2).wav`. Conserva todos los chunks (`bext` con TimeReference, `iXML`, `LIST/INFO`, `axml`, XMP, propietarios). El iXML se reduce a la pista extraída.
- **Identidad única por canal**: UMID del `bext` (material number = hash del UMID original y el canal), `OriginatorReference` y `FILE_UID` del iXML terminan en el canal. Pro Tools identifica los ficheros por ahí (§9).
- **RF64** si el resultado no cabe en un WAV normal.
- **Float de 32 bits → PCM de 24 bits** (siempre al copiar, partir o embeber), con `audioconv`:
  - los canales que superan 0 dBFS bajan **enteros** hasta dejar el pico en −1 dBFS, con una **bajada máxima de 6 dB** (`--max-reduction-db`); lo que aún sobrepase se recorta y se avisa con el número de muestras;
  - los canales que no se pasan no se tocan; sin dither; el redondeo es el de AudioConverter;
  - se actualizan `AUDIO_BIT_DEPTH` (iXML) y `W=` (historial del `bext`); la bajada queda en `CONFORM2AAF/GAIN_DB` (iXML) y en el comentario `GainReduction` del maestro del AAF.
- «Enlazar» sin partir con ficheros float: aviso de que Pro Tools se cierra.

## 7. AAF de salida (`writers/aaf.py`)

- Una `CompositionMob` (`Usage_TopLevel`) con una ranura de timecode (velocidad nominal, DF si procede) y una ranura de sonido por pista, **a la frecuencia de muestreo de la sesión**: posiciones exactas a nivel de muestra con cualquier velocidad de imagen.
- Huecos como `Filler`; clips como `SourceClip`; crossfades y fundidos con `Transition` + `OperationGroup` *Mono Audio Dissolve*; ganancia de clip con *Mono Audio Gain* (`Amplitude` constante).
- Por fichero: `MasterMob` → `SourceMob` con `WAVEDescriptor` + localizador → `SourceMob` de importación con ranura de timecode en el TimeReference original del BWF. Comentarios del maestro: `Scene`, `Take`, `Tape`, `Project`, `Description`, `Tracks`, `GainReduction`.
- **Localizador**: `file:///<Volumen>/ruta` (sin `/Volumes`); para el disco de arranque, `file:///<NombreDelDisco>/…`.
- **`Summary` del descriptor**: cabecera `fmt` PCM simple (un `fmt` extensible se aplana).
- Clips que salen del rango del fichero: se recortan con aviso; clips solapados en una pista: se recortan con aviso. Escritura a `.partial` y renombrado al final.

## 8. Protocolo motor ↔ app

```
python -m conform2aaf inspect|convert LISTA [--media DIR]… [--no-recursive] [--fps 25]
        [--start-tc 01:00:00:00] [--choose ID=RUTA]… [--picture auto|on|off]
   convert: --out SALIDA.aaf [--sample-rate 48000] [--media-mode link|copy|embed]
            [--split-mono] [--peak-ceiling-db -1|off] [--max-reduction-db 6|off]
```

Salida: una línea JSON por evento en stdout: `progress {stage, message}`, `warning {message}`, `report {timeline{name, rate, start_tc, picture, tracks}, counts, clips[{id, track, name, record_in, record_out, source_in, channel, scene, take, tape, status, note, file, candidates}]}`, `result {output, clips_written, clips_skipped, media_dir, media_files, media_bytes}`, `error {message}`.

`audioconv --in FICHERO [--channel N] [--gain-db G] [--out RUTA|-]`: escribe PCM 24 bits empaquetado little-endian y, en stderr, `{"frames","channels","clipped","peak"}`.

## 9. Compatibilidad con Pro Tools (verificada, 26.4.1)

- El AAF **no puede enlazar WAV multicanal** (Pro Tools usa solo el canal 1 de cada pista): se parte a mono.
- Pro Tools **funde en uno** los ficheros con el mismo UMID/referencia: identidad única por canal (§6).
- Un localizador `file:///Volumes/…` deja los medios offline y su ventana de relink cierra Pro Tools: usar `file:///<Volumen>/…`.
- Un `Summary` con `fmt` extensible da «Error reading AAF WAVE Data».
- **Un AAF que enlaza WAV float de 32 bits cierra Pro Tools siempre** (cualquier cabecera, también en sesión de 32 bits float; importar el WAV directamente sí funciona). Se convierte a PCM 24 bits.
- Pro Tools **guarda en caché** los ficheros ya importados: reimportar un AAF que reutiliza ficheros o nombres puede dar «AAE error 35» o ruido hasta reiniciar Pro Tools. Usar nombres nuevos (la app ya no sobrescribe).
- Sin comprobar: ganancia de clip y crossfades en Pro Tools; embeber.

## 10. Compilación y pruebas

- `scripts/build_engine.sh`: construye `build/engine` (`python/`, `lib/`, `bin/audioconv`; requiere `uv` y Xcode). Fase de script de Xcode `scripts/embed_engine.sh`: copia el motor al `.app`, lo firma ad-hoc y lo reconstruye si cambian `engine/` o `tools/`.
- `xcodebuild -project Conformig2AAF.xcodeproj -scheme Conformig2AAF build`.
- Pruebas del motor: `cd engine && .venv/bin/pytest -q` (149 pruebas; un fixture compila `audioconv` si no está construido). La lógica Swift se comprueba con programas aparte; no hay target de pruebas en Xcode.
- Desarrollo: `CONFORM2AAF_ENGINE=<repo>/engine` usa el `.venv` del repo en lugar del motor embebido; `CONFORM2AAF_AUDIOCONV` fija la ruta de `audioconv`.

## 11. Pendiente

- Conformado: confirmar en Resolve el canal de origen de los eventos de EDL que salen solos (hoy, el canal 1).
- Medios: MXF y vídeo → WAV (AVFoundation), remuestreo (AudioConverter), reenlazado de medios, WAV estéreo sin partir (`VID-…wav` en A7), quitar chunks propietarios sobrantes en los WAV partidos (~3,7 MB cada uno).
- Formatos: leer AAF; escribir XML de Premiere y FCPXML; detectar la aplicación de origen.
- Producción: sincronización automática por TC y escena/toma más allá del enlace, canales prioritarios, alineación por forma de onda, disposiciones híbridas.
- Edición: reajuste tras cambios de imagen, modificaciones por lotes, atmósferas y tablero de ajedrez por escena, pistas para cambios de escena.
- Otros: TC que cruza medianoche; un corte de imagen que abarca varios WAV; sesiones de Pro Tools.
