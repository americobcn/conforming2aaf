"""CMX3600 EDL reader (audio events only)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from ..model import Clip, Timeline, Track
from ..timecode import FrameRate, tc_to_frames

_TC = r"(\d\d[:;.]\d\d[:;.]\d\d[:;.,]\d\d)"
EVENT_RE = re.compile(
    rf"^(\d{{1,6}})\s+(\S+)\s+(\S+)\s+(C|D|W\d{{3}}|K[BO]?)\s+(?:(\d{{1,4}})\s+)?{_TC}\s+{_TC}\s+{_TC}\s+{_TC}\s*$"
)
AUD_RE = re.compile(r"^AUD\s+(\d+)(?:\s+(\d+))?\s*$")
M2_RE = re.compile(r"^M2\s+(\S+)\s+(-?\d+(?:\.\d+)?)\s+" + _TC)
LEVEL_RE = re.compile(r"AUDIO LEVEL AT \S+ IS ([-+]?\d+(?:\.\d+)?) DB.*?\(.*?(A\d+)\)", re.I)
BLACK = {"BL", "BLK", "BLACK"}


@dataclass
class _Line:
    event: str
    reel: str
    channels: list[int]
    trans: str
    trans_dur: int
    src_in: int
    src_out: int
    rec_in: int
    rec_out: int
    name: str = ""
    hint: str = ""
    gains: dict[int, float] = field(default_factory=dict)


def _channels(field_: str) -> list[int]:
    out: list[int] = []
    for part in field_.upper().split("/"):
        if part == "AA":
            out += [1, 2]
        elif part in ("A", "B"):
            out.append(1)
        elif m := re.fullmatch(r"A(\d+)", part):
            out.append(int(m.group(1)))
    return out


def read_edl(path: Path, rate: FrameRate) -> Timeline:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    title = Path(path).stem
    drop = False
    lines: list[_Line] = []
    warnings: list[str] = []

    def eff() -> FrameRate:
        return FrameRate(rate.fps, rate.nominal, rate.drop or (drop and rate.fps.denominator == 1001))

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("TITLE:"):
            title = s.split(":", 1)[1].strip() or title
        elif up.startswith("FCM:"):
            drop = "NON" not in up and "DROP" in up
        elif m := EVENT_RE.match(s):
            ev, reel, chans, trans, dur, si, so, ri, ro = m.groups()
            tcs = [tc_to_frames(t, eff()) for t in (si, so, ri, ro)]
            lines.append(_Line(ev, reel, _channels(chans), trans, int(dur or 0), *tcs))
            if trans[0] in "WK":
                warnings.append(f"Evento {ev}: transición {trans} tratada como corte")
        elif lines and (m := AUD_RE.match(up)):
            lines[-1].channels += [int(g) for g in m.groups() if g]
        elif m := M2_RE.match(s):
            warnings.append(f"Evento {lines[-1].event if lines else '?'}: cambio de velocidad {m.group(2)} fps no soportado")
        elif s.startswith("*") and lines:
            body = s.lstrip("*").strip()
            key, _, val = body.partition(":")
            key, val = key.strip().upper(), val.strip()
            group = [ln for ln in lines if ln.event == lines[-1].event]
            if key == "FROM CLIP NAME":
                group[0].name = val
            elif key == "TO CLIP NAME":
                group[-1].name = val
            elif key in ("SOURCE FILE", "SOURCE FILE NAME"):
                lines[-1].hint = val
            elif lm := LEVEL_RE.search(body):
                lines[-1].gains[int(lm.group(2)[1:])] = float(lm.group(1))

    eff_rate = eff()
    fps = eff_rate.fps
    tracks: dict[int, Track] = {}
    for i, ln in enumerate(lines):
        prev = lines[i - 1] if i and lines[i - 1].event == ln.event else None
        if ln.trans == "D" and ln.reel.upper() in BLACK and i:
            # dissolve to black: fade out the clips of the previous line
            for ch in lines[i - 1].channels:
                if ch in tracks and tracks[ch].clips:
                    tracks[ch].clips[-1].fade_out = Fraction(ln.trans_dur) / fps
        if not ln.channels or ln.reel.upper() in BLACK or ln.rec_out <= ln.rec_in:
            continue
        for ch in ln.channels:
            clip = Clip(
                name=ln.name or ln.reel,
                record_in=Fraction(ln.rec_in) / fps,
                duration=Fraction(ln.rec_out - ln.rec_in) / fps,
                source_in=Fraction(ln.src_in) / fps,
                reel=ln.reel,
                file_hint=ln.hint,
                channel=ch,
                gain_db=ln.gains.get(ch, 0.0),
            )
            if ln.trans == "D" and ln.trans_dur:
                d = Fraction(ln.trans_dur) / fps
                if prev and prev.reel.upper() in BLACK:
                    clip.fade_in = d
                else:
                    clip.crossfade_in = d
            tracks.setdefault(ch, Track(f"A{ch}")).clips.append(clip)

    for t in tracks.values():
        t.clips.sort(key=lambda c: c.record_in)
    ordered = [tracks[k] for k in sorted(tracks)]
    starts = [c.record_in for t in ordered for c in t.clips]
    return Timeline(
        name=title,
        rate=eff_rate,
        start=min(starts) if starts else Fraction(0),
        tracks=ordered,
        warnings=warnings,
    )
