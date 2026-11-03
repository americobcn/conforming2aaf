"""Pick the right reader for an edit list."""
from __future__ import annotations

from pathlib import Path

from ..model import Timeline
from ..timecode import FrameRate

INPUT_EXTS = {".edl", ".xml", ".fcpxml", ".fcpxmld"}


def _read(path: Path, rate: FrameRate | None, picture: bool) -> Timeline:
    ext = path.suffix.lower()
    if ext == ".edl":
        if rate is None:
            raise ValueError("Las EDL no indican la velocidad: elige la frecuencia de fotogramas")
        from .edl import read_edl
        return read_edl(path, rate, picture)
    if ext in (".fcpxml", ".fcpxmld"):
        from .fcpxml import read_fcpxml
        return read_fcpxml(path, picture)
    if ext == ".xml":
        head = path.read_bytes()[:4096].decode("utf-8", "replace")
        if "<fcpxml" in head:
            from .fcpxml import read_fcpxml
            return read_fcpxml(path, picture)
        from .xmeml import read_xmeml
        return read_xmeml(path, picture)
    raise ValueError(f"Formato no soportado: {path.name}")


def read_timeline(path: Path, rate: FrameRate | None = None, picture: bool | None = None) -> Timeline:
    """picture: True/False force the mode; None reads audio and falls back to picture cuts
    (production sound is then conformed to them) when the list has no audio clips."""
    path = Path(path)
    tl = _read(path, rate, bool(picture))
    if picture is None and not any(True for _ in tl.clips()):
        pic = _read(path, rate, True)
        if any(True for _ in pic.clips()):
            pic.warnings.insert(0, "Lista de imagen: se conformará el sonido directo de cada corte")
            return pic
    return tl
