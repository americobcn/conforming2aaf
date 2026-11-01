# Conforming2AAF specs

**Purpose:** convert audio timelines between post-production tools — Davinci Resolve / Avid Media Composer / Adobe Premiere / Final Cut Pro FCPXML / EDL ⇄ AAF "sample-accurate — works with any project frame rate"

## 1. Architecture

```
Conforming2AAF.app
├─ Contents/MacOS/Conforming2AAF         PyInstaller bootloader (arm64, thin)
│    └─ embedded PKG: entry script `conforming2aaf_app` + PYZ.pyz (404 pure-Python modules)
├─ Contents/Frameworks (Resources mirrors via symlinks)
│    ├─ Python.framework 3.14.5 + python3.14/lib-dynload
│    ├─ aaf2/ (pyaaf2 1.7.1)  objc/ AppKit/ Foundation/ WebKit/ CoreFoundation/ (PyObjC)
│    ├─ ffmpeg (arm64 CLI, invoked as subprocess)  libssl.3 libcrypto.3 libzstd liblzma libmpdec

```


## 2. Technology stack

| Component | Role | Version / detail | Tag | Evidence |
|---|---|---|---|---|
| Python | runtime | **3.14.5** (embedded framework) | O | `Python.framework/Versions/3.14/Resources/Info.plist` |
| PyInstaller | packaging/bootloader | pyver 314 archive; bootloader version U | O | E6 |
| Cython | compiled app modules | 3.2.9 | O | E5 |
| WKWebView (WebKit) | renders UI | via PyObjC `WebKit` | O | PYZ list (`WebKit`, `WebKit._metadata`) |
| bottle, proxy_tools | pywebview dependencies | versions U | O | PYZ list |
| **PyObjC** | Cocoa bridge | `objc`, `AppKit`, `Foundation`, `CoreFoundation`, `WebKit`, `UniformTypeIdentifiers`, `PyObjCTools.{AppHelper,KeyValueCoding,MachSignals}`; version U | O | PYZ list; `Frameworks/{objc,AppKit,Foundation,…}/*.so` |
| **pyaaf2** | read/write AAF | **1.7.1**, MIT, © 2018 Mark Reid; 32 `aaf2.*` modules | O | `pyaaf2-1.7.1.dist-info/METADATA`; PYZ list |
| **FFmpeg** | audio decode/transcode (separate executable) | libavcodec 61.19.101 (FFmpeg 7.1.x; notice says 7.1.1), arm64, `--enable-small`, LGPL, **not** GPL/non-free | O | `strings Frameworks/ffmpeg`; `licenses/THIRD-PARTY-LICENSES.txt` |
| OpenSSL 3 (`libssl.3`, `libcrypto.3`), zstd 1.5.7 (inferred from string), liblzma 5, libmpdec 4 | bundled native libs | OpenSSL patch version U | O/I | `Frameworks/*.dylib` |
| Python stdlib used | `argparse`, `asyncio`, `multiprocessing`, `xml.etree.ElementTree`, `wave`, `ssl`, `urllib.request`, `json`, `gzip`, `hashlib`, `subprocess`, `dataclasses`, `fractions`, `shutil`, … | | O/D | PYZ list; decoded module strings |
| Swift + SwiftUI host API | UI (cards, switches, drop zone, step bar, role rows) | min macOS 13.0, universal | O | E3, E7, E8 |


## 3. Features

### 3.1 Conversions

| Input | Output | Tag | Evidence |
|---|---|---|---|
| `.als` (Ableton Live set) | `.aaf`, Premiere XML (`.xml`), `.fcpxml`, `.fcpxmld`, `edl` bundle | D | `aafbridge.cli`, `export_als`, `export_xml`, `export_edl` |
| `.aaf`, `.xml` (Premiere/FCP7 xmeml), `.fcpxml`, `.fcpxmld`, `edl` | new `.als` (no template; embedded skeleton) | D | `cli`: "`.aaf/.xml/.fcpxml/.fcpxmld -> NEW .als (no template)`"; `readers` (`IMPORT_EXTS`) |
| EDL / AAF / FCPXML / Premiere XML | AAF / Premiere XML / FCPXML  | D | `aafe.convert` ("Premiere XML", "Final Cut Pro XML bundle", "AAF"); `write_aaf/fcp7/fcpxml/edl` |
| FCPXMLD bundle output = package with `Info.fcpxml` (v1.10, FCP 10.6+) | | D | `export_xml` |

Source-application detection from AAF metadata (labels): Adobe Premiere Pro, Avid Media Composer, Cubase (Steinberg), DaVinci Resolve (Blackmagic), Final Cut Pro, Logic Pro, Nuendo, Pro Tools (Avid), Reaper (Cockos), Samplitude/Sequoia (Magix) — D `aafbridge.aaf_io`. Output frame rates: 23.976, 24, 25, 29.97, 29.97 DF, 30, 50, 59.94, 60 (+ "none" = no timecode track, AAF only) — D `export_als`, `fcpxml_io`. Separately, the FCP writer notes that a **120 fps** source is not a Final Cut preset and is set to 60 fps (D `aafbridge.convert`), so 120 appears as an *input/session* rate but is not a selectable FCP output rate.

### 3.2 What travels (feature flags)

`aafbridge.features.Features` declares (D, E5 + decoded blob): `markers`, `clip_gain`, `fades`, `crossfades`, `volume_automation`, `pan`, `colors`, `video` (picture reference track). The code defines CLI flags for each (`transfer markers/locators`, `transfer clip gain`, `transfer clip fades`, `transfer crossfades`, `transfer volume automation`, `transfer static track pan`, `transfer track/clip colors (round trip)`, `transfer the picture reference track`) — **the CLI code exists (D) but whether the shipped app exposes it is U**: the entry script shows no argv routing to `aafbridge.cli`, and the bundle has no standalone interpreter. The GUI exposes matching checkboxes ("Markers", "Fades", "Crossfades", "Clip gain", "Volume automation", "Colors", "Video").

Documented per-format limits (D, `export_xml`/`export_als`/`convert`):
- Premiere XML: fades/crossfades → real transitions; gain → constant level; **no** pan, volume automation or colors.
- FCPXML: fades + gain; **no** pan/automation/colors; track names become audio **roles**.
- Colors travel in AAF only (for the return trip to Ableton).
- AAF cannot represent time-stretching/warp ("consolidate in Ableton (Cmd+J)"); neutrally-warped clips export correctly; non-linear fade curves approximated as linear; Live's ~4 ms auto click-protection fades are not exported.
- Muted tracks/clips excluded by default ("Include deactivated clips" / `--muted`).
- Speed changes/retimed clips don't travel (reported); 120 fps → 60 fps sequence for FCP; surround panner left out.

### 3.3 Source-reading intelligence (FCPXML, AAF, Premiere XML, EDL)

(D `aafe.read_fcpxml`, `aafe.read_aaf`, `aafbridge.fcpxml_io`, `aafe.edl`): compound / multicam / audition clips resolved to ordinary cuts (active angle/take); sync-clips and ref-clips; roles → tracks (muted roles kept at full mute); overlapping clips spread over multiple tracks; frame-rate-conformed clips detected; FCP lane nesting depth cap with a "break apart" hint; loose event clips rejected with guidance to export the *project*; AAF `ScopeReference`/`NestedScope`/`EssenceGroup`/`Selector` handling with warnings for unresolved scopes; Premiere linked stereo pairs merged; keyframes mapped to clip gain + edge fades.

### 3.4 Media handling

(D `aafbridge.essences`, `aafe.media`, `aafbridge.convert`)
- **Collect media next to the output** (self-contained, movable package; import → `Samples/Imported`, export → `<name> Media` folder); BWF `bext`/iXML preserved on bit-exact copy.
- **Embed media in AAF**; extract embedded AAF essence to WAV preserving audio metadata.
- **Transcode MXF audio → WAV** via the bundled ffmpeg (Live cannot read MXF); keep as MXF if transcoding off or ffmpeg missing preserving audio metadata.
- **Separate combined channels** (per-channel mono files, for Pro Tools) vs interleaved; multichannel/stereo handling; "Combine split stereo tracks" (`stereo_pairs`, name+length+channel-count matching, manual pairing).
- 32-bit float → fixed-point conversion; resample to 48 kHz where needed; "Handles" (frames/seconds).
- Relinking: missing media searched next to the source / user-picked folder ("Search a folder…", "Include subfolders"); offline clips preserved.
- Audio extracted from video containers (`.mp4/.mov/.m4v/.mkv`); video referenced, not copied for sound.
- ffmpeg as built here can decode: MXF, WAV, AIFF, MOV, MP3, AAC, FLAC, Ogg, W64, CAF, Matroska, AC-3, MPEG-TS, AVI, ASF, DV (D: configure line in `Frameworks/ffmpeg`).

