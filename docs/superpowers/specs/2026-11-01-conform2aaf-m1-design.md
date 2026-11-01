# Conformig2AAF — Plan (Hito 1: EDL / Premiere XML / FCPXML → AAF)

## Context
El repo es una plantilla SwiftUI vacía (`Conformig2AAF/ContentView.swift`, `Conformig2AAF/Conformig2AAFApp.swift`; macOS 15.8, sandbox ON con acceso read-only, Swift 5, MainActor por defecto). CLAUDE.md describe una app de conformado de audio de producción a AAF preservando metadatos (BWF/iXML/RIFF INFO/axml/XMP). SPECS.md describe la arquitectura de una app existente (Python + pyaaf2 + ffmpeg embebidos). La implementación será independiente y se basará en las especificaciones públicas de los formatos.

Decisiones del usuario:
- Stack: **UI SwiftUI nativa + motor en Python con pyaaf2**, embebido en el .app.
- Primer hito de punta a punta: **EDL / Premiere XML (xmeml) / FCPXML → AAF** enlazando WAV de producción.
- **Ableton (.als) queda fuera** del alcance.

Éxito del Hito 1: dada una EDL/XML/FCPXML y una carpeta de WAV de producción, la app genera un AAF que se abre en Pro Tools con los clips en la posición exacta a nivel de muestra, enlazados a los WAV originales con sus metadatos intactos, y con un informe de los clips enlazados, ambiguos y no encontrados.

## Arquitectura
```
Conformig2AAF.app
├─ SwiftUI (UI, ficheros, progreso)  ──Process + JSON lines──▶  Resources/engine/
│                                                              ├─ python/ (python-build-standalone 3.12, arm64)
│                                                              └─ conform2aaf/ (+ pyaaf2 en site-packages)
```
- El motor es un paquete Python con una CLI. La UI lo lanza con `Process` y lee por stdout eventos JSON línea a línea: `{"type":"progress"|"warning"|"report"|"result"|"error", ...}`.
- Para desarrollo, la variable de entorno `CONFORM2AAF_ENGINE` apunta a un venv del repo y así no hace falta reconstruir el bundle.

## Estructura del repo (nuevo)
```
engine/
  pyproject.toml              # pyaaf2==1.7.1, pytest
  conform2aaf/
    timecode.py               # rates 23.976/24/25/29.97 NDF+DF/30/50/59.94 NDF+DF/60; TC↔frames↔samples con Fraction
    model.py                  # dataclasses Timeline, Track, Clip (reel, clip name, src in/out, rec in/out, canal, gain, fades), MediaFile
    readers/edl.py            # CMX3600: FCM DF/NDF, eventos AUD A1–A4, reel, "* FROM CLIP NAME", "* SOURCE FILE", disolvencias, M2 de velocidad (aviso)
    readers/xmeml.py          # Premiere/FCP7 XML: pistas de audio, clipitem, file/pathurl, sourcetrack/canal, pares estéreo enlazados
    readers/fcpxml.py         # FCPXML 1.8–1.11 (+ .fcpxmld/Info.fcpxml): tiempos racionales, spine, asset-clip, clip, sync-clip, ref-clip, lanes, roles→pistas, solapes→pistas extra
    media/riff.py             # parser RIFF/RF64 en Python puro: fmt, bext (TimeReference, Description, Originator), iXML, LIST/INFO, axml, _PMX (XMP)
    media/scanner.py          # indexa carpetas (opción subcarpetas), caché por mtime
    media/matcher.py          # enlace clip→fichero: nombre (sin extensión/case), reel/tape+rango TC de bext, desempate de nombres duplicados por TC; estados matched/ambiguous/missing
    writers/aaf.py            # pyaaf2: CompositionMob, TimelineMobSlots por pista, MasterMob→SourceMob con WAVE/PCM descriptor + NetworkLocator al WAV (bit-exact, metadatos intactos); pista de TC con TC de inicio; handles; clip gain; fades/crossfades (OperationGroup Mono Audio Dissolve); TaggedValues scene/take/tape en mobs
    cli.py                    # `inspect <input> --media DIR...` → JSON timeline + informe; `convert ... --out x.aaf --fps --start-tc --handles --json`
  tests/                      # pytest; fixtures EDL/XML/FCPXML pequeñas + WAV sintéticos con bext/iXML generados en el test
scripts/build_engine.sh       # descarga python-build-standalone, instala engine+pyaaf2, firma dylibs; Xcode Run Script lo copia a Resources/engine
Conformig2AAF/
  Engine/EngineClient.swift   # localiza intérprete, lanza Process, AsyncStream<EngineEvent>, cancelación
  Engine/EngineEvent.swift    # Codable de los eventos JSON
  Views/ContentView.swift     # flujo de pasos: Lista → Medios → Revisión → Exportar
  Views/DropZoneView.swift    # soltar/abrir .edl/.xml/.fcpxml/.fcpxmld
  Views/MediaFoldersView.swift# carpetas de medios + "incluir subcarpetas"
  Views/MatchReportView.swift # tabla: clip, pista, TC, fichero, estado (filtrable)
  Views/ExportOptionsView.swift # fps, TC inicio, handles, destino
docs/superpowers/specs/2026-11-01-conform2aaf-m1-design.md  # este diseño, versionado
```

## Pasos (TDD en el motor, con verificación en cada paso)
0. `git init`, `.gitignore`, guardar este diseño en `docs/superpowers/specs/` → verify: primer commit.
1. Venv local con Python 3.12 (uv o python-build-standalone) + pyaaf2 1.7.1 → verify: `python -c "import aaf2"`.
2. `timecode.py` → verify: tests DF/NDF con valores conocidos (p. ej. 29.97 DF `00:10:00;00` = 17982 frames, 23.976 a muestras a 48 kHz).
3. `media/riff.py` + `scanner.py` → verify: tests que escriben WAV con bext/iXML/INFO y los leen igual; RF64.
4. Readers EDL, xmeml y FCPXML → modelo común → verify: fixtures con posiciones esperadas en muestras; casos de DF, canales y pistas solapadas.
5. `matcher.py` → verify: tests de nombres duplicados resueltos por TC, sin TC de cámara (enlace por nombre), y clips missing/ambiguous.
6. `writers/aaf.py` → verify: escribir AAF, releerlo con pyaaf2 y comprobar posiciones/longitudes/locators/TC por pista; comprobar con hash que el WAV no cambia.
7. `cli.py` (inspect/convert, JSON lines) → verify: test de extremo a extremo con subprocess.
8. `scripts/build_engine.sh` + Run Script de Xcode; ajustar entitlements → verify: `xcodebuild build` y el .app contiene un `engine/python` que arranca.
9. UI SwiftUI + `EngineClient` → verify: tests unitarios de decodificación de eventos; ejecutar la app, soltar fixture, ver informe, exportar AAF.
10. Verificación manual del usuario: abrir el AAF en Pro Tools (y en Resolve/Nuendo si hay) con material real.

## Decisiones mías (revisar)
- **Sandbox desactivado** (distribución fuera de la App Store, notarizada). Con sandbox, un proceso Python hijo que lee carpetas de medios arbitrarias necesita entitlements de herencia y bookmarks con ámbito de seguridad: es frágil. Se puede reactivar más tarde.
- **Python 3.12 embebido** (python-build-standalone, solo arm64 en el Hito 1). Nada de PyInstaller: la UI ya es Swift.
- Medios **enlazados** (no embebidos ni copiados) en el Hito 1. Así los metadatos se conservan por definición, porque el WAV no se toca.
- Hito 1 sin ffmpeg (solo WAV/BWF/RF64). Los WAV polifónicos se enlazan por canal según la EDL/XML (sin partir ficheros).
- Multicam/compound de FCPXML: un nivel de resolución en el Hito 1 (ángulo/toma activa); los anidamientos profundos generan un aviso.

## Fuera del Hito 1 (hoja de ruta)
- M2 Medios: MXF/vídeo→WAV con ffmpeg preservando metadatos, recopilar/embeber en AAF, partir polifónicos, 32f→PCM, remuestreo, reenlazado.
- M3 Formatos: leer AAF; escribir Premiere XML y FCPXML; detección de la app de origen.
- M4 Producción: sync automático por TC + escena/toma, canales prioritarios, alineación por forma de onda con pista guía, disposiciones híbridas.
- M5 Edición: reajuste tras cambios de imagen (change lists), modificaciones por lotes, ambientes/tablero de ajedrez por escena, pistas de cambio de escena/corte.
- Lectura de sesiones Pro Tools (.ptx): formato propietario y sin documentar, alto riesgo; se evaluará aparte.

## Verificación end-to-end
- `cd engine && pytest` en verde (unitarios + E2E de CLI).
- `xcodebuild -scheme Conformig2AAF build` correcto; lanzar la app, cargar las fixtures EDL/XML/FCPXML con su carpeta de WAV, revisar el informe, exportar.
- Releer el AAF exportado con pyaaf2 (script de comprobación) y abrirlo en Pro Tools: clips en posición, enlazados y con metadatos de escena/toma visibles en el WAV original.
