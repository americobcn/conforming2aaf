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
    """picture: True/False force the mode; None conforms the production sound to the picture
    cuts and only falls back to the list's audio tracks when it has no picture cuts."""
    path = Path(path)
    if picture is not None:
        return _read(path, rate, picture)
    pic = _read(path, rate, True)
    if any(True for _ in pic.clips()):
        return pic
    tl = _read(path, rate, False)
    tl.warnings.insert(0, "Lista sin cortes de imagen: se conforman sus pistas de audio")
    return tl
