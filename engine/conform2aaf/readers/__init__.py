"""Pick the right reader for an edit list."""
from __future__ import annotations

from pathlib import Path

from ..model import Timeline
from ..timecode import FrameRate

INPUT_EXTS = {".edl", ".xml", ".fcpxml", ".fcpxmld"}


def read_timeline(path: Path, rate: FrameRate | None = None) -> Timeline:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".edl":
        if rate is None:
            raise ValueError("Las EDL no indican la velocidad: elige la frecuencia de fotogramas")
        from .edl import read_edl
        return read_edl(path, rate)
    if ext in (".fcpxml", ".fcpxmld"):
        from .fcpxml import read_fcpxml
        return read_fcpxml(path)
    if ext == ".xml":
        head = path.read_bytes()[:4096].decode("utf-8", "replace")
        if "<fcpxml" in head:
            from .fcpxml import read_fcpxml
            return read_fcpxml(path)
        from .xmeml import read_xmeml
        return read_xmeml(path)
    raise ValueError(f"Formato no soportado: {path.name}")
