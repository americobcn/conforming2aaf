"""Link edit-list clips to production audio files.

Order of evidence:
1. Name: file hint, clip name or reel equals the file stem (case-insensitive).
   If nothing matches by name (e.g. a picture-only list with camera clip names),
   the candidates are the files whose bext timecode range overlaps the clip.
2. Timecode: partial overlap is accepted (the sound may start late or stop early);
   the missing frames are reported. No overlap -> not found.
3. Recording date (the clip name or reel carries it, e.g. _261009_; the WAV has the bext
   OriginationDate or, failing that, a tape written as a date, e.g. 26Y10M28) discards the files from another day. Then, as tie-breakers in order: start
   time (the name may carry it, e.g. _115104_; was the recorder rolling then, +-1 min), tape
   (iXML/bext TAPE vs the clip's tape or reel), scene+take (both normalised). Evidence only
   counts when present on both sides.
4. Candidates recorded on another day than the clip name says are discarded (a clip left
   without candidates is `missing`, with the dates in the note). If a file matched by name
   or a single remaining candidate has contradicting scene/take, the clip is `ambiguous`.
   A camera reel that differs from the sound tape is never a conflict.
5. A clip with no TC is matched by scene/take (or tape) alone, but only with a positive
   agreement on a single file.
"""
from __future__ import annotations

import re
from collections import defaultdict
from fractions import Fraction
from pathlib import PurePath
from typing import Callable

import datetime as dt

from ..clipdate import date_from_name, time_from_name
from ..model import Clip, MediaFile, Timeline
from ..timecode import FrameRate


def _norm(s: str) -> str:
    s = PurePath(s.replace("\\", "/")).name if s else ""
    for ext in (".wav", ".bwf", ".mxf", ".aif", ".aiff"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]
    return s.strip().lower()


def normalize_id(s: str) -> str:
    """Scene/take/tape id: lower case, alphanumeric tokens, leading zeros dropped per token.

    '5 12' == '5/12' == '05-12' -> '5-12'; '1 12' and '11 2' stay different.
    """
    return "-".join(t.lstrip("0") or "0" for t in re.findall(r"[0-9a-z]+", (s or "").lower()))


def _overlap(mf: MediaFile, clip: Clip) -> Fraction | None:
    """Seconds of the clip's source range inside the file's bext range (None without TC)."""
    if mf.start is None or clip.source_in is None:
        return None
    a = max(clip.source_in, mf.start)
    b = min(clip.source_in + clip.duration, mf.start + mf.duration)
    return max(b - a, Fraction(0))


TIME_TOLERANCE = 60  # seconds: camera and recorder clocks are never exactly together


def _stamp(clip: Clip) -> tuple[dt.date | None, dt.time | None]:
    """Shooting date and start time from the clip name, its file path or its reel."""
    for text in (clip.name, clip.file_hint, clip.reel):
        if text and (d := date_from_name(text)):
            return d, time_from_name(text)
    return None, None


def clip_date(clip: Clip) -> dt.date | None:
    """Shooting date (RED/ARRI names carry _YYMMDD_)."""
    return _stamp(clip)[0]


def _time_agrees(mf: MediaFile, clip: Clip) -> bool | None:
    """Was the recorder rolling when the camera clip started? (same day, +-TIME_TOLERANCE)"""
    day, at = _stamp(clip)
    if at is None or mf.time is None or (day is not None and file_date(mf) is not None and day != file_date(mf)):
        return None
    start = mf.time.hour * 3600 + mf.time.minute * 60 + mf.time.second
    t = at.hour * 3600 + at.minute * 60 + at.second
    return start - TIME_TOLERANCE <= t <= start + float(mf.duration) + TIME_TOLERANCE


def file_date(mf: MediaFile) -> dt.date | None:
    """Recording date: bext OriginationDate, else the tape when the recorder wrote the date there (26Y10M28)."""
    return mf.date or (date_from_name(mf.tape) if mf.tape else None)


def _date_agrees(mf: MediaFile, clip: Clip) -> bool | None:
    d, f = clip_date(clip), file_date(mf)
    return None if d is None or f is None else d == f


def _tape_agrees(mf: MediaFile, clip: Clip) -> bool | None:
    clip_tape = clip.tape or clip.reel
    a, b = normalize_id(clip_tape), normalize_id(mf.tape)
    if not (a and b):
        return None
    da, db = date_from_name(clip_tape), date_from_name(mf.tape)
    if da and db:  # both are dates, written differently (261028 / 26Y10M28)
        return da == db
    return a == b


def _scene_take_agrees(mf: MediaFile, clip: Clip) -> bool | None:
    pairs = [(normalize_id(x), normalize_id(y)) for x, y in ((clip.scene, mf.scene), (clip.take, mf.take))]
    pairs = [(x, y) for x, y in pairs if x and y]
    return None if not pairs else all(x == y for x, y in pairs)


def _narrow(pool: list[MediaFile], agrees: Callable[[MediaFile], bool | None]) -> list[MediaFile]:
    """Keep files that positively agree; else drop those that contradict; else leave unchanged."""
    agree = [f for f in pool if agrees(f) is True]
    if agree:
        return agree
    return [f for f in pool if agrees(f) is not False] or pool


class Matcher:
    def __init__(self, files: list[MediaFile]):
        self.files = files
        self.by_stem: dict[str, list[MediaFile]] = defaultdict(list)
        for f in files:
            self.by_stem[f.stem.lower()].append(f)

    def _named(self, clip: Clip) -> list[MediaFile]:
        keys = [k for k in (_norm(clip.file_hint), _norm(clip.name), _norm(clip.reel)) if k]
        named: list[MediaFile] = []
        for k in dict.fromkeys(keys):
            named += [f for f in self.by_stem.get(k, []) if f not in named]
        return named

    @staticmethod
    def _missing_note(mf: MediaFile, clip: Clip, rate: FrameRate | None) -> str:
        head = max(mf.start - clip.source_in, Fraction(0))
        tail = max(clip.source_in + clip.duration - (mf.start + mf.duration), Fraction(0))

        def amount(sec: Fraction) -> str:
            return f"{round(sec * rate.fps)} fotogramas" if rate else f"{float(sec):.2f} s"

        parts = [f"faltan {amount(s)} {where}" for s, where in ((head, "al principio"), (tail, "al final")) if s > 0]
        return "; ".join(parts)

    def match_clip(self, clip: Clip, rate: FrameRate | None = None) -> None:
        has_tc = clip.source_in is not None
        named = self._named(clip)
        evidence: list[str] = []
        if named:
            mode, pool = "name", named
        elif has_tc:
            mode, pool = "tc", [f for f in self.files if f.start is not None]
        elif clip.scene or clip.take or clip.tape or clip.reel:
            mode = "meta"
            pool = [f for f in self.files
                    if _scene_take_agrees(f, clip) is True or _tape_agrees(f, clip) is True]
        else:
            return self._set(clip, "missing", [], "No se encontró fichero")

        if has_tc:
            covering = [f for f in pool if f.start is None or _overlap(f, clip) > 0]
            if mode == "name" and not covering:
                return self._set(clip, "ambiguous", pool, "El nombre coincide pero el TC está fuera del fichero")
            if len(covering) < len(pool) and mode == "name":
                evidence.append("TC")
            pool = covering
        if not pool:
            return self._set(clip, "missing", [], "No se encontró fichero")

        day = clip_date(clip)
        if day is not None:
            agree = [f for f in pool if _date_agrees(f, clip) is True]
            unknown = [f for f in pool if _date_agrees(f, clip) is None]
            other = [f for f in pool if _date_agrees(f, clip) is False]
            if agree:
                if len(agree) < len(pool):
                    evidence.append("fecha")
                pool = agree
            elif unknown:
                pool = unknown  # the files with another date are discarded
            elif mode != "name":
                # every candidate was recorded on another day: discard them all. Neighbouring days
                # overlap in free-run timecode, so a one-day difference is a coincidence, not a clock error.
                dates = ", ".join(sorted({file_date(f).isoformat() for f in other}))
                return self._set(clip, "missing", [],
                                 f"Solo hay ficheros con este TC de otra fecha (clip {day.isoformat()}; ficheros {dates})")
        if len(pool) > 1:
            before = len(pool)
            pool = _narrow(pool, lambda f: _time_agrees(f, clip))
            if len(pool) < before:
                evidence.append("hora")
        if len(pool) > 1:
            before = len(pool)
            pool = _narrow(pool, lambda f: _tape_agrees(f, clip))
            if len(pool) < before:
                evidence.append("cinta")
        if len(pool) > 1:
            before = len(pool)
            pool = _narrow(pool, lambda f: _scene_take_agrees(f, clip))
            if len(pool) < before:
                evidence.append("escena/toma")
        if len(pool) > 1 and has_tc:
            full = [f for f in pool if f.start is not None and _overlap(f, clip) == clip.duration]
            if len(full) == 1:
                pool = full

        if len(pool) > 1 and all(_date_agrees(f, clip) is False for f in pool):
            dates = ", ".join(sorted({file_date(f).isoformat() for f in pool}))
            return self._set(clip, "ambiguous", pool,
                             f"{len(pool)} ficheros cubren este TC pero ninguno coincide en fecha "
                             f"(clip {clip_date(clip).isoformat()}, ficheros {dates})")
        if len(pool) > 1:
            what = {"name": "con el mismo nombre", "tc": "cubren este TC", "meta": "con la misma escena/toma"}[mode]
            return self._set(clip, "ambiguous", pool, f"{len(pool)} ficheros {what}")

        f = pool[0]
        if _date_agrees(f, clip) is False:
            lead = "El nombre coincide pero" if mode == "name" else "TC cuadra pero"
            return self._set(clip, "ambiguous", [f],
                             f"{lead} la fecha difiere (clip {clip_date(clip).isoformat()}, "
                             f"fichero {file_date(f).isoformat()})")
        if _scene_take_agrees(f, clip) is False:
            lead = "El nombre coincide pero" if mode == "name" else "TC cuadra pero"
            note = (f"{lead} escena/toma difieren (clip {clip.scene.strip()}/{clip.take.strip()}, "
                    f"fichero {f.scene.strip()}/{f.take.strip()})")
            return self._set(clip, "ambiguous", [f], note)

        parts: list[str] = []
        if mode == "name":
            if len(named) > 1:
                parts.append("Nombre duplicado resuelto por " + " y ".join(evidence or ["TC"]))
            elif not (has_tc and f.start is not None):
                parts.append("Enlazado solo por nombre (sin TC)")
        elif mode == "tc":
            parts.append("Enlazado por " + " y ".join(["TC"] + evidence))
        else:
            parts.append("Enlazado por " + " y ".join(evidence or ["escena/toma"]))
        if has_tc and f.start is not None:
            missing = self._missing_note(f, clip, rate)
            if missing:
                parts.append(missing)
        return self._set(clip, "matched", [f], "; ".join(parts))

    @staticmethod
    def _set(clip: Clip, status: str, cands: list[MediaFile], note: str) -> None:
        clip.match_status = status
        clip.candidates = cands
        clip.media = cands[0] if status == "matched" else None
        clip.match_note = note

    def match_timeline(self, tl: Timeline) -> dict[str, int]:
        counts = {"matched": 0, "ambiguous": 0, "missing": 0}
        for clip in tl.clips():
            self.match_clip(clip, tl.rate)
            counts[clip.match_status] += 1
        return counts
