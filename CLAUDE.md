# CLAUDE.md

## Visión general del proyecto
- **Propósito**: Aplicación MacOS nativa para conformar audio a partir de edit decision lists (EDLs), XMLs, FCPXmls a AAF preservando audio metadata (BWF, RIFF INFO, AXML, IXML, XMP).
- Manipulación, limpieza y filtrado exhaustivos y flexibles de listas de edición (EDL, AAF, XML y sesiones de Pro Tools).
- Gestionar proyectos complicados y con problemas (por ejemplo, nombres de archivos duplicados o falta del código de tiempo de la cámara) y sincronizar automáticamente el audio de producción.
- Montaje y disposición de pistas: ofrece opciones avanzadas de montaje, como disposiciones híbridas, canales prioritarios, alineación de la forma de onda de las pistas guía y generación de pistas para cambios de escena o cortes de imagen.
- Datos y reajuste: Ofrece herramientas robustas para reajustar sesiones tras cambios en la imagen, reenlazar archivos WAV, realizar modificaciones por lotes y automatizar ediciones de atmósfera o en tablero de ajedrez basadas en escenas.
- Compatibilidad: Admite código de tiempo con fotogramas omitidos

## Estado actual
**Hecho (probado con Pro Tools 26.4.1):**
- Entrada: EDL CMX3600, XML de Premiere/FCP7 (xmeml), FCPXML y `.fcpxmld`, con audio o **solo con cortes de imagen** (modo imagen: se conforma el sonido directo de cada corte, una pista por canal).
- Enlace clip ↔ WAV por nombre, TC (solape parcial), **fecha y hora del nombre del clip**, cinta y escena/toma (iXML o `bext`); descarte de candidatos de otro día; elección manual de los dudosos.
- Salida: AAF con precisión de muestra; medios enlazados, copiados junto al AAF o embebidos; WAV polifónicos partidos a mono con identidad única por canal; float de 32 bits convertido a PCM 24 bits con AudioToolbox (bajada de nivel de los canales que pasan de 0 dBFS, máximo 6 dB).
- Interfaz: tabla de enlace, filtros, «Nueva importación» (⇧⌘N), nombres de salida que no sobrescriben.

**Pendiente** (detalle en SPECS.md §11): leer AAF y sesiones de Pro Tools, escribir XML/FCPXML, MXF/vídeo → WAV, remuestreo, reenlazado, reajuste tras cambios de imagen, atmósferas y tablero de ajedrez, canales prioritarios y alineación por forma de onda.

## Stack
- **SwiftUI** (macOS 15.8, Xcode 26.3) para la interfaz + **motor en Python 3.12** embebido (`engine/`, solo librería estándar y `pyaaf2` 1.7.1) + **`audioconv`**, un ejecutable Swift con AudioToolbox (`tools/audioconv/`). Todo el detalle está en **SPECS.md**.
- Para procesar audio, usar los **frameworks nativos de Apple** (AudioToolbox, AVFoundation). No se usan `ffmpeg`, `numpy` ni `sox`.
- Sin sandbox (el motor es un proceso hijo que lee carpetas arbitrarias). Distribución fuera de la App Store.

## Estructura
- `Conformig2AAF/`: app SwiftUI. `ConformModel` (estado), `Engine/` (lanza el motor y decodifica sus eventos JSON), `Views/`.
- `engine/conform2aaf/`: `readers/` (EDL, xmeml, FCPXML), `media/` (RIFF, escáner, matcher, `prepare.py`, `audio.py`), `writers/aaf.py`, `picture.py`, `clipdate.py`, `timecode.py`, `cli.py`. Tests en `engine/tests/`.
- `tools/audioconv/`, `scripts/` (`build_engine.sh`, `embed_engine.sh`), `docs/superpowers/specs/` (diseño del hito 1).

## Comandos
- Pruebas del motor: `cd engine && .venv/bin/pytest -q`.
- Motor embebido: `scripts/build_engine.sh` (lo lanza también la fase de script de Xcode); compilar: `xcodebuild -project Conformig2AAF.xcodeproj -scheme Conformig2AAF build`.
- Probar el motor sin la app: `engine/.venv/bin/python -m conform2aaf inspect|convert LISTA --media CARPETA --fps 25` (opciones en SPECS.md §8).

## Reglas de trabajo
- **Pro Tools no da errores útiles, solo se cierra.** Antes de tocar el escritor de AAF o la preparación de medios, lee SPECS.md §9 (qué cierra Pro Tools y qué necesita). Ante un crash nuevo: lee su log en `~/Library/Logs/Avid/`, compara con un AAF que sí importa y prueba con variantes pequeñas que cambien una sola cosa. Para cada prueba, nombres de AAF y de carpeta de medios nuevos (Pro Tools guarda en caché los ficheros).
- Desarrollo con pruebas primero en el motor; la lógica Swift se verifica con un programa aparte (no hay target de pruebas en Xcode).
- No se modifican nunca los ficheros de audio originales.
- Los textos de la interfaz, avisos y notas van en español.
