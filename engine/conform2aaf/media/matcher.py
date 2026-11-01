"""Link edit-list clips to production audio files.

Order of evidence:
1. Name: file hint, clip name or reel equals the file stem (case-insensitive).
2. Timecode: the clip's source range must lie inside the file's bext range.
   Used to break ties between duplicate names, and alone when no name matches.
3. Tape: an iXML tape equal to the reel breaks remaining timecode ties.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from pathlib import PurePath

from ..model import Clip, MediaFile, Timeline


def _norm(s: str) -> str:
    s = PurePath(s.replace("\\", "/")).name if s else ""
    for ext in (".wav", ".bwf", ".mxf", ".aif", ".aiff"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]
    return s.strip().lower()


def _covers(mf: MediaFile, start: Fraction, dur: Fraction) -> bool:
    return mf.start is not None and mf.start <= start and start + dur <= mf.start + mf.duration


class Matcher:
    def __init__(self, files: list[MediaFile]):
        self.files = files
        self.by_stem: dict[str, list[MediaFile]] = defaultdict(list)
        for f in files:
            self.by_stem[f.stem.lower()].append(f)

    def match_clip(self, clip: Clip) -> None:
        keys = [k for k in (_norm(clip.file_hint), _norm(clip.name), _norm(clip.reel)) if k]
        named: list[MediaFile] = []
        for k in dict.fromkeys(keys):
            named += [f for f in self.by_stem.get(k, []) if f not in named]

        has_tc = clip.source_in is not None
        if named:
            if len(named) == 1:
                f = named[0]
                if has_tc and f.start is not None and not _covers(f, clip.source_in, clip.duration):
                    return self._set(clip, "ambiguous", [f], "El nombre coincide pero el TC está fuera del fichero")
                note = "" if (has_tc and f.start is not None) else "Enlazado solo por nombre (sin TC)"
                return self._set(clip, "matched", [f], note)
            if has_tc:
                inside = [f for f in named if _covers(f, clip.source_in, clip.duration)]
                if len(inside) == 1:
                    return self._set(clip, "matched", inside, "Nombre duplicado resuelto por TC")
                if inside:
                    named = inside
            return self._set(clip, "ambiguous", named, f"{len(named)} ficheros con el mismo nombre")

        if has_tc:
            inside = [f for f in self.files if _covers(f, clip.source_in, clip.duration)]
            if len(inside) > 1 and clip.reel:
                by_tape = [f for f in inside if f.tape and f.tape.lower() == clip.reel.lower()]
                inside = by_tape or inside
            if len(inside) == 1:
                return self._set(clip, "matched", inside, "Enlazado por TC")
            if inside:
                return self._set(clip, "ambiguous", inside, f"{len(inside)} ficheros cubren este TC")
        return self._set(clip, "missing", [], "No se encontró fichero")

    @staticmethod
    def _set(clip: Clip, status: str, cands: list[MediaFile], note: str) -> None:
        clip.match_status = status
        clip.candidates = cands
        clip.media = cands[0] if status == "matched" else None
        clip.match_note = note

    def match_timeline(self, tl: Timeline) -> dict[str, int]:
        counts = {"matched": 0, "ambiguous": 0, "missing": 0}
        for clip in tl.clips():
            self.match_clip(clip)
            counts[clip.match_status] += 1
        return counts
