"""Index production audio folders."""
from __future__ import annotations

from pathlib import Path

from ..model import MediaFile
from .riff import NotAWav, read_wav

AUDIO_EXTS = {".wav", ".bwf"}


def scan(folders: list[Path], recursive: bool = True) -> tuple[list[MediaFile], list[str]]:
    files: list[MediaFile] = []
    warnings: list[str] = []
    seen: set[Path] = set()
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            warnings.append(f"Carpeta no encontrada: {folder}")
            continue
        paths = folder.rglob("*") if recursive else folder.iterdir()
        for p in sorted(paths):
            if p.suffix.lower() not in AUDIO_EXTS or p.name.startswith("._") or not p.is_file():
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                files.append(read_wav(p))
            except (NotAWav, OSError, ValueError) as e:
                warnings.append(f"No se pudo leer {p.name}: {e}")
    return files, warnings
